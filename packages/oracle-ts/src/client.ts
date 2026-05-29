// SPDX-License-Identifier: Apache-2.0
// Part of @axxis/oracle — https://github.com/dot-protocol/oracle-sdk-ts

import {
  AuthError,
  IngestError,
  NotFoundError,
  OracleError,
  RateLimitError,
} from './errors.js';
import {
  AskResponseSchema,
  CapabilitiesSchema,
  ConnectionGraphSchema,
  ObservationSchema,
  SearchResultSchema,
  SelfInfoSchema,
  type AskResponse,
  type Capabilities,
  type ConnectionGraph,
  type Keypair,
  type Observation,
  type SearchResult,
  type SelfInfo,
} from './types.js';
import {
  EMPTY_BODY_SHA256_HEX,
  canonicalBytes,
  deriveDefaultHandle,
  makeNonceB64,
  nowIso,
  pubkeyHexToB64,
  sha256Hex,
  signEd25519,
} from './signing.js';

const DEFAULT_BASE_URL = 'https://oracle.axxis.world';
const DEFAULT_USER_AGENT = '@axxis/oracle-ts/0.1.0';
const DEFAULT_TIMEOUT_MS = 30_000;
/** Override for `/ask` and `/p/ask` — Ollama RAG can take 30–60s on CPU. */
const ASK_TIMEOUT_MS = 120_000;
const MAX_RETRIES = 3;

/** Construction options for the {@link Oracle} client. */
export interface OracleOptions {
  /** Override base URL. Defaults to `process.env.ORACLE_BASE_URL` or `https://oracle.axxis.world`. */
  baseUrl?: string;
  /** Ed25519 keypair → signed-request to `/p/*`. Takes priority over `apiKey`. */
  keypair?: Keypair;
  /** Self-reported handle for signed-request mode. Derived from pubkey if absent. */
  handle?: string;
  /** Bearer token → goes to bearer-gated endpoints (`/ingest`, `/search`, …). */
  apiKey?: string;
  /** Override fetch (useful for tests and runtimes without `globalThis.fetch`). */
  fetchImpl?: typeof fetch;
  /** Per-request timeout (ms). Default 30s; `/ask` automatically extends to 120s. */
  timeoutMs?: number;
  /** Optional UA suffix appended to `User-Agent`. */
  userAgentSuffix?: string;
}

type AuthMode = 'signed' | 'bearer' | 'none';

interface InternalRequest {
  method: 'GET' | 'POST';
  path: string;
  query?: Record<string, string | number | boolean | undefined>;
  body?: unknown;
  /** `none` is used for the open `/capabilities` endpoint. */
  authMode?: AuthMode;
  /** For `/ask`-style endpoints. Falls back to `timeoutMs`. */
  timeoutMs?: number;
}

/**
 * Oracle SDK client.
 *
 * Asymmetric write surface (intentional, mirrors the Python SDK):
 * - **Bearer auth** → full `add(...)` for any observation type.
 * - **Signed-request** (`/p/ingest`) → ONLY protocol message types are accepted:
 *   `handle_claim`, `handle_rotate`, `dotpost`, `icontact`. Use the typed
 *   helpers `addDotpost()` / `addIcontact()`. Generic `add()` will reject with
 *   {@link IngestError} if called in signed-request mode.
 *
 * @example
 * ```ts
 * import { Oracle, loadKeypair } from '@axxis/oracle';
 *
 * const oracle = new Oracle({ keypair: loadKeypair('key.json') });
 * await oracle.addDotpost({ body: 'Rocky shipped /p/ingest today', to: 'all', channel: 'lab' });
 * const results = await oracle.search('what did rocky ship');
 * console.log(results[0].statement);
 * ```
 */
export class Oracle {
  readonly baseUrl: string;
  readonly authMode: AuthMode;
  private readonly keypair: Keypair | undefined;
  private readonly handle: string | undefined;
  private readonly apiKey: string | undefined;
  private readonly fetchImpl: typeof fetch;
  private readonly timeoutMs: number;
  private readonly userAgent: string;

  constructor(opts: OracleOptions = {}) {
    // Resolve base URL: explicit > env > default.
    const envBase = typeof process !== 'undefined' ? process.env?.['ORACLE_BASE_URL'] : undefined;
    this.baseUrl = (opts.baseUrl ?? envBase ?? DEFAULT_BASE_URL).replace(/\/$/, '');

    // Resolve auth (priority: keypair → apiKey → env token).
    const envToken =
      typeof process !== 'undefined'
        ? process.env?.['ORACLE_TOKEN'] ?? process.env?.['TREE_AUTH_TOKEN']
        : undefined;

    if (opts.keypair) {
      this.keypair = opts.keypair;
      this.handle = opts.handle ?? deriveDefaultHandle(opts.keypair.pubkeyHex);
      this.authMode = 'signed';
    } else if (opts.apiKey) {
      this.apiKey = opts.apiKey;
      this.authMode = 'bearer';
    } else if (envToken) {
      this.apiKey = envToken;
      this.authMode = 'bearer';
    } else {
      this.authMode = 'none';
    }

    // Fetch impl: explicit > globalThis.fetch. We don't throw on construction
    // if fetch is missing — `capabilities()` may still work with a polyfill
    // set later, and tests inject via opts.
    const globalFetch =
      typeof globalThis !== 'undefined' ? (globalThis as { fetch?: typeof fetch }).fetch : undefined;
    const resolvedFetch = opts.fetchImpl ?? globalFetch;
    if (!resolvedFetch) {
      throw new OracleError('no fetch implementation: pass opts.fetchImpl or use Node 18+');
    }
    // Bind so explicit-this loss doesn't break Undici-style implementations.
    this.fetchImpl = resolvedFetch.bind(globalThis as never);

    this.timeoutMs = opts.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    this.userAgent = opts.userAgentSuffix
      ? `${DEFAULT_USER_AGENT} ${opts.userAgentSuffix}`
      : DEFAULT_USER_AGENT;
  }

  // ---------- public API ----------

  /**
   * Open capability report — no auth required. Always queries `/capabilities`.
   */
  async capabilities(): Promise<Capabilities> {
    const raw = await this.request({
      method: 'GET',
      path: '/capabilities',
      authMode: 'none',
    });
    return CapabilitiesSchema.parse(raw);
  }

  /**
   * Bearer-only generic ingest. Use {@link addDotpost} / {@link addIcontact}
   * when authenticating via signed-request.
   *
   * @throws {IngestError} if called in signed-request mode (`/p/ingest` only
   *   accepts protocol message types).
   */
  async add(
    text: string,
    opts: {
      channel: string;
      tags?: string[];
      source?: string;
      obsType?: string;
    },
  ): Promise<Observation> {
    if (this.authMode === 'signed') {
      throw new IngestError(
        'Oracle.add() requires bearer auth. /p/ingest only allows protocol message types ' +
          '(handle_claim, handle_rotate, dotpost, icontact). Use addDotpost() or addIcontact().',
      );
    }
    const body = {
      content: text,
      channel: opts.channel,
      tags: opts.tags ?? [],
      ...(opts.source !== undefined ? { source: opts.source } : {}),
      ...(opts.obsType !== undefined ? { type: opts.obsType } : {}),
    };
    const raw = await this.request({
      method: 'POST',
      path: '/ingest',
      body,
      authMode: 'bearer',
    });
    return ObservationSchema.parse(unwrapObservation(raw));
  }

  /**
   * Post a dotpost message. Works with either auth mode.
   *
   * - Bearer → `POST /ingest` with `type: "dotpost"`.
   * - Signed → `POST /p/ingest` with the same shape (server gates on the
   *   protocol-message allow-list).
   */
  async addDotpost(opts: {
    body: string;
    to: string;
    channel?: string;
    replyTo?: string;
    tags?: string[];
  }): Promise<Observation> {
    const tags = [
      `to:${opts.to}`,
      ...(opts.replyTo ? [`in_reply_to:${opts.replyTo}`] : []),
      ...(opts.tags ?? []),
    ];
    return this.postProtocolMessage({
      type: 'dotpost',
      body: opts.body,
      channel: opts.channel ?? 'mesh',
      tags,
    });
  }

  /**
   * Post an icontact message (DM substrate). Same auth shape as `addDotpost`.
   */
  async addIcontact(opts: {
    body: string;
    to: string;
    channel?: string;
    tags?: string[];
  }): Promise<Observation> {
    const tags = [`to:${opts.to}`, ...(opts.tags ?? [])];
    return this.postProtocolMessage({
      type: 'icontact',
      body: opts.body,
      channel: opts.channel ?? 'icontact',
      tags,
    });
  }

  /**
   * Hybrid RRF semantic search. Bearer → `/search`, signed → `/p/search`.
   *
   * @param query natural-language query
   * @param opts optional `topK` (default 10) and `rerank` (default true on bearer).
   */
  async search(
    query: string,
    opts: { topK?: number; rerank?: boolean } = {},
  ): Promise<SearchResult[]> {
    const topK = opts.topK ?? 10;
    const body: Record<string, unknown> = { query, top_k: topK };
    if (opts.rerank !== undefined) body['rerank'] = opts.rerank;

    const path = this.authMode === 'signed' ? '/p/search' : '/search';
    const raw = (await this.request({
      method: 'POST',
      path,
      body,
    })) as { results?: unknown };

    const results = Array.isArray(raw?.results) ? raw.results : [];
    return results.map((r) => SearchResultSchema.parse(r));
  }

  /**
   * Recent observations, optionally filtered by channel.
   * Bearer → `/recent`, signed → `/p/recent`.
   */
  async recent(opts: { limit?: number; channel?: string } = {}): Promise<Observation[]> {
    const query: Record<string, string | number> = {};
    if (opts.limit !== undefined) query['limit'] = opts.limit;
    if (opts.channel !== undefined) query['channel'] = opts.channel;

    const path = this.authMode === 'signed' ? '/p/recent' : '/recent';
    const raw = (await this.request({
      method: 'GET',
      path,
      query,
    })) as { items?: unknown };

    const items = Array.isArray(raw?.items) ? raw.items : [];
    return items.map((i) => ObservationSchema.parse(i));
  }

  /**
   * RAG dialog. Bearer → `/ask`, signed → `/p/ask`. Non-streaming overload.
   *
   * Latency: 30–60s typical on CPU-only Ollama; SDK auto-extends timeout to 120s.
   */
  async ask(query: string, opts?: { stream?: false; topK?: number; model?: string }): Promise<AskResponse>;
  /**
   * RAG dialog with token streaming. Returns an `AsyncIterable<string>` of tokens.
   *
   * NOTE: streaming wire format is `text/event-stream` with `data: {token}` chunks
   * (per `signed-request-v0.1.2`, pending). v0.1 emits the whole answer at once.
   */
  async ask(
    query: string,
    opts: { stream: true; topK?: number; model?: string },
  ): Promise<AsyncIterable<string>>;
  async ask(
    query: string,
    opts: { stream?: boolean; topK?: number; model?: string } = {},
  ): Promise<AskResponse | AsyncIterable<string>> {
    if (opts.stream) {
      return this.askStream(query, opts);
    }
    const body: Record<string, unknown> = { question: query };
    if (opts.topK !== undefined) body['top_k'] = opts.topK;
    if (opts.model !== undefined) body['model'] = opts.model;

    const path = this.authMode === 'signed' ? '/p/ask' : '/ask';
    const raw = await this.request({
      method: 'POST',
      path,
      body,
      timeoutMs: ASK_TIMEOUT_MS,
    });
    return AskResponseSchema.parse(raw);
  }

  /**
   * Graph neighbourhood for a single observation.
   * Bearer → `/connections/<id>`, signed → `/p/connections/<id>`.
   */
  async connections(obsId: string): Promise<ConnectionGraph> {
    if (!obsId) throw new OracleError('connections() requires a non-empty obsId');
    const path = this.authMode === 'signed' ? `/p/connections/${obsId}` : `/connections/${obsId}`;
    const raw = await this.request({ method: 'GET', path });
    return ConnectionGraphSchema.parse(raw);
  }

  /**
   * Server self-report. Bearer → `/self`, signed → `/p/self`.
   */
  async selfInfo(): Promise<SelfInfo> {
    const path = this.authMode === 'signed' ? '/p/self' : '/self';
    const raw = await this.request({ method: 'GET', path });
    return SelfInfoSchema.parse(raw);
  }

  // ---------- internals ----------

  private async postProtocolMessage(args: {
    type: 'dotpost' | 'icontact' | 'handle_claim' | 'handle_rotate';
    body: string;
    channel: string;
    tags: string[];
  }): Promise<Observation> {
    const payload = {
      type: args.type,
      content: args.body,
      channel: args.channel,
      tags: args.tags,
    };
    const path = this.authMode === 'signed' ? '/p/ingest' : '/ingest';
    const raw = await this.request({
      method: 'POST',
      path,
      body: payload,
    });
    return ObservationSchema.parse(unwrapObservation(raw));
  }

  private async *askStream(
    query: string,
    opts: { topK?: number; model?: string },
  ): AsyncGenerator<string, void, undefined> {
    const body: Record<string, unknown> = { question: query, stream: true };
    if (opts.topK !== undefined) body['top_k'] = opts.topK;
    if (opts.model !== undefined) body['model'] = opts.model;

    const path = this.authMode === 'signed' ? '/p/ask' : '/ask';
    const url = this.urlFor(path);
    const bodyText = JSON.stringify(body);
    const headers = await this.buildHeaders({
      method: 'POST',
      path,
      queryString: '',
      bodyText,
      contentType: 'application/json',
      accept: 'text/event-stream',
    });

    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), ASK_TIMEOUT_MS);
    let res: Response;
    try {
      res = await this.fetchImpl(url, {
        method: 'POST',
        headers,
        body: bodyText,
        signal: ctrl.signal,
      });
    } finally {
      clearTimeout(timer);
    }

    if (!res.ok) {
      throw await errorFromResponse(res);
    }
    if (!res.body) {
      throw new OracleError('streaming response has no body');
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      // SSE frames are separated by blank lines.
      let idx: number;
      while ((idx = buffer.indexOf('\n\n')) !== -1) {
        const frame = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        const dataLine = frame
          .split('\n')
          .find((line) => line.startsWith('data:'));
        if (!dataLine) continue;
        const data = dataLine.slice(5).trim();
        if (data === '[DONE]' || data === 'done') return;
        // Best-effort: if it's JSON with .token, yield that; otherwise yield raw.
        try {
          const parsed = JSON.parse(data) as { token?: string; answer?: string };
          if (typeof parsed.token === 'string') {
            yield parsed.token;
            continue;
          }
          if (typeof parsed.answer === 'string') {
            yield parsed.answer;
            continue;
          }
        } catch {
          // not JSON — fall through
        }
        yield data;
      }
    }
  }

  private urlFor(path: string): string {
    return `${this.baseUrl}${path.startsWith('/') ? path : `/${path}`}`;
  }

  private encodeQuery(query: Record<string, string | number | boolean | undefined> | undefined): string {
    if (!query) return '';
    const parts: string[] = [];
    for (const [k, v] of Object.entries(query)) {
      if (v === undefined) continue;
      parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
    }
    return parts.join('&');
  }

  private async buildHeaders(args: {
    method: string;
    path: string;
    queryString: string;
    bodyText: string;
    contentType?: string;
    accept?: string;
    authMode?: AuthMode;
  }): Promise<Record<string, string>> {
    const headers: Record<string, string> = {
      'User-Agent': this.userAgent,
      Accept: args.accept ?? 'application/json',
    };
    if (args.contentType) headers['Content-Type'] = args.contentType;

    const mode = args.authMode ?? this.authMode;

    if (mode === 'bearer') {
      if (!this.apiKey) {
        throw new AuthError('bearer auth selected but no apiKey set');
      }
      headers['Authorization'] = `Bearer ${this.apiKey}`;
    } else if (mode === 'signed') {
      if (!this.keypair || !this.handle) {
        throw new AuthError('signed-request selected but keypair/handle unset');
      }
      const timestamp = nowIso();
      const nonceB64 = makeNonceB64(16);
      const pubkeyB64 = pubkeyHexToB64(this.keypair.pubkeyHex);
      const bodyHashHex = args.bodyText.length === 0 ? EMPTY_BODY_SHA256_HEX : sha256Hex(args.bodyText);
      const canonical = canonicalBytes({
        method: args.method,
        path: args.path,
        queryString: args.queryString,
        bodyHashHex,
        handle: this.handle,
        pubkeyB64,
        timestamp,
        nonceB64,
      });
      const sig = signEd25519(canonical, this.keypair.privkeyHex);
      headers['X-Pipernet-Handle'] = this.handle;
      headers['X-Pipernet-Pubkey'] = pubkeyB64;
      headers['X-Pipernet-Timestamp'] = timestamp;
      headers['X-Pipernet-Nonce'] = nonceB64;
      headers['X-Pipernet-Signature'] = bytesToB64(sig);
    }
    // mode === 'none' → no auth headers
    return headers;
  }

  private async request(req: InternalRequest): Promise<unknown> {
    const mode: AuthMode = req.authMode ?? this.authMode;
    // Any non-open call requires credentials. /capabilities sets authMode:'none'
    // explicitly, so the only way we hit `mode === 'none'` here is when the
    // caller has no credentials at all but is hitting a protected route.
    if (mode === 'none' && req.authMode !== 'none') {
      throw new AuthError(
        'no credentials: pass {keypair} or {apiKey}, or set ORACLE_TOKEN env',
      );
    }

    const queryString = this.encodeQuery(req.query);
    const url = queryString ? `${this.urlFor(req.path)}?${queryString}` : this.urlFor(req.path);
    const bodyText = req.body === undefined ? '' : JSON.stringify(req.body);
    const headers = await this.buildHeaders({
      method: req.method,
      path: req.path,
      queryString,
      bodyText,
      ...(req.body !== undefined && { contentType: 'application/json' }),
      authMode: mode,
    });

    const effectiveTimeout = req.timeoutMs ?? this.timeoutMs;
    let lastErr: unknown;
    for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
      try {
        const ctrl = new AbortController();
        const timer = setTimeout(() => ctrl.abort(), effectiveTimeout);
        let res: Response;
        try {
          const init: RequestInit = {
            method: req.method,
            headers,
            signal: ctrl.signal,
          };
          if (req.method !== 'GET' && req.body !== undefined) {
            init.body = bodyText;
          }
          res = await this.fetchImpl(url, init);
        } finally {
          clearTimeout(timer);
        }

        if (res.ok) {
          // 204 / no content → return {}
          if (res.status === 204) return {};
          const text = await res.text();
          if (!text) return {};
          try {
            return JSON.parse(text);
          } catch (e) {
            throw new OracleError(`server returned non-JSON: ${text.slice(0, 200)}`, { cause: e });
          }
        }

        // Decide retry vs throw.
        if (res.status >= 500 && attempt < MAX_RETRIES - 1) {
          await sleep(backoffMs(attempt));
          continue;
        }
        throw await errorFromResponse(res);
      } catch (err) {
        // Network errors / aborts → retry. OracleError subclasses → propagate.
        if (err instanceof OracleError) throw err;
        lastErr = err;
        if (attempt < MAX_RETRIES - 1) {
          await sleep(backoffMs(attempt));
          continue;
        }
        throw new OracleError(
          `network error after ${MAX_RETRIES} attempts: ${(err as Error)?.message ?? String(err)}`,
          { cause: err },
        );
      }
    }
    throw new OracleError(
      `unreachable: exhausted retries (${(lastErr as Error)?.message ?? 'unknown'})`,
    );
  }
}

// ---------- helpers ----------

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

function backoffMs(attempt: number): number {
  // 1s, 2s, 4s
  return Math.min(1000 * 2 ** attempt, 8000);
}

function bytesToB64(b: Uint8Array): string {
  if (typeof Buffer !== 'undefined') return Buffer.from(b).toString('base64');
  let s = '';
  for (let i = 0; i < b.length; i++) {
    const byte = b[i];
    if (byte === undefined) continue;
    s += String.fromCharCode(byte);
  }
  return globalThis.btoa(s);
}

/**
 * Server responses sometimes wrap the observation under `.observation`, `.obs`,
 * or `.hits[0]`. Normalize.
 */
function unwrapObservation(raw: unknown): unknown {
  if (raw && typeof raw === 'object') {
    const r = raw as Record<string, unknown>;
    if (r['observation']) return r['observation'];
    if (r['obs']) return r['obs'];
    if (Array.isArray(r['hits']) && r['hits'].length > 0) return r['hits'][0];
  }
  return raw;
}

async function errorFromResponse(res: Response): Promise<OracleError> {
  let payload: { error?: string; message?: string; retry_after_s?: number } = {};
  let textBody = '';
  try {
    textBody = await res.text();
    if (textBody) payload = JSON.parse(textBody) as typeof payload;
  } catch {
    // fall through with whatever we have
  }
  const msg = payload.error ?? payload.message ?? textBody ?? res.statusText ?? `HTTP ${res.status}`;

  switch (res.status) {
    case 401:
    case 408:
    case 409:
      return new AuthError(msg, { statusCode: res.status });
    case 404:
      return new NotFoundError(msg);
    case 429: {
      const retry = payload.retry_after_s;
      return new RateLimitError(msg, retry !== undefined ? { retryAfterS: retry } : undefined);
    }
    case 400:
    case 422:
      return new IngestError(msg, { statusCode: res.status });
    default:
      return new OracleError(msg, { statusCode: res.status });
  }
}