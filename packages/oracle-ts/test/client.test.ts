// SPDX-License-Identifier: Apache-2.0
// Part of @axxis/oracle — https://github.com/dot-protocol/oracle-sdk-ts

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  AuthError,
  IngestError,
  NotFoundError,
  Oracle,
  RateLimitError,
  generateKeypair,
} from '../src/index.js';
import { EMPTY_BODY_SHA256_HEX, sha256Hex } from '../src/signing.js';

// ---- test fixtures ----

const BEARER_BASE = 'https://oracle.axxis.world';

function fakeResponse(body: unknown, init?: { status?: number }): Response {
  const text = typeof body === 'string' ? body : JSON.stringify(body);
  return new Response(text, {
    status: init?.status ?? 200,
    headers: { 'content-type': 'application/json' },
  });
}

function captureFetch() {
  const calls: Array<{ url: string; init: RequestInit }> = [];
  let nextResponse: () => Response = () => fakeResponse({});
  const impl: typeof fetch = vi.fn(async (input, init?: RequestInit) => {
    calls.push({ url: String(input), init: init ?? {} });
    return nextResponse();
  }) as unknown as typeof fetch;
  return {
    impl,
    calls,
    setResponse(fn: () => Response) {
      nextResponse = fn;
    },
  };
}

// ---- shared setup ----

let originalEnv: NodeJS.ProcessEnv;
beforeEach(() => {
  originalEnv = { ...process.env };
  // Strip any inherited Oracle auth so tests are deterministic.
  delete process.env['ORACLE_TOKEN'];
  delete process.env['TREE_AUTH_TOKEN'];
  delete process.env['ORACLE_BASE_URL'];
});
afterEach(() => {
  process.env = originalEnv;
  vi.restoreAllMocks();
});

// ---- construction ----

describe('Oracle construction', () => {
  it('throws AuthError on protected call when no credentials anywhere', async () => {
    const f = captureFetch();
    const oracle = new Oracle({ fetchImpl: f.impl });
    expect(oracle.authMode).toBe('none');
    await expect(oracle.search('hello')).rejects.toThrow(AuthError);
  });

  it('picks up ORACLE_TOKEN from env as bearer', () => {
    process.env['ORACLE_TOKEN'] = 'env-tok';
    const f = captureFetch();
    const oracle = new Oracle({ fetchImpl: f.impl });
    expect(oracle.authMode).toBe('bearer');
  });

  it('keypair beats apiKey beats env', () => {
    process.env['ORACLE_TOKEN'] = 'env-tok';
    const kp = generateKeypair();
    const f = captureFetch();
    const oracle = new Oracle({ keypair: kp, apiKey: 'literal', fetchImpl: f.impl });
    expect(oracle.authMode).toBe('signed');
  });

  it('respects ORACLE_BASE_URL env', () => {
    process.env['ORACLE_BASE_URL'] = 'https://staging.axxis.world';
    process.env['ORACLE_TOKEN'] = 't';
    const f = captureFetch();
    const oracle = new Oracle({ fetchImpl: f.impl });
    expect(oracle.baseUrl).toBe('https://staging.axxis.world');
  });
});

// ---- /capabilities (open) ----

describe('Oracle.capabilities()', () => {
  it('GETs /capabilities with no auth headers', async () => {
    const f = captureFetch();
    f.setResponse(() =>
      fakeResponse({
        version: '1.2.3',
        endpoints: ['/search', '/p/search'],
        auth_modes: ['bearer', 'signed-request-v0.1'],
        signed_request_version: '0.1.1',
      }),
    );
    const oracle = new Oracle({ fetchImpl: f.impl });
    const caps = await oracle.capabilities();

    expect(f.calls).toHaveLength(1);
    const call = f.calls[0]!;
    expect(call.url).toBe(`${BEARER_BASE}/capabilities`);
    expect(call.init.method).toBe('GET');
    const headers = call.init.headers as Record<string, string>;
    expect(headers['Authorization']).toBeUndefined();
    expect(headers['X-Pipernet-Signature']).toBeUndefined();
    expect(caps.version).toBe('1.2.3');
    expect(caps.endpoints).toContain('/search');
  });
});

// ---- bearer mode ----

describe('Oracle (bearer mode)', () => {
  function makeBearerClient() {
    const f = captureFetch();
    const oracle = new Oracle({ apiKey: 'bearer-tok', fetchImpl: f.impl });
    return { oracle, f };
  }

  it('add() POSTs /ingest with bearer header', async () => {
    const { oracle, f } = makeBearerClient();
    f.setResponse(() =>
      fakeResponse({ observation: { id: 'OBS-1', statement: 'hi', channel: 'lab' } }),
    );
    const obs = await oracle.add('hi', { channel: 'lab', tags: ['t1'] });

    const call = f.calls[0]!;
    expect(call.url).toBe(`${BEARER_BASE}/ingest`);
    expect(call.init.method).toBe('POST');
    const headers = call.init.headers as Record<string, string>;
    expect(headers['Authorization']).toBe('Bearer bearer-tok');
    expect(headers['Content-Type']).toBe('application/json');
    expect(JSON.parse(call.init.body as string)).toEqual({
      content: 'hi',
      channel: 'lab',
      tags: ['t1'],
    });
    expect(obs.id).toBe('OBS-1');
  });

  it('addDotpost() puts type=dotpost and to:<handle> tag', async () => {
    const { oracle, f } = makeBearerClient();
    f.setResponse(() => fakeResponse({ id: 'OBS-2', statement: 'pong', channel: 'mesh' }));
    await oracle.addDotpost({ body: 'pong', to: 'all', channel: 'lab', replyTo: 'OBS-1' });

    const body = JSON.parse(f.calls[0]!.init.body as string);
    expect(body.type).toBe('dotpost');
    expect(body.content).toBe('pong');
    expect(body.channel).toBe('lab');
    expect(body.tags).toContain('to:all');
    expect(body.tags).toContain('in_reply_to:OBS-1');
  });

  it('addIcontact() uses icontact channel default + type', async () => {
    const { oracle, f } = makeBearerClient();
    f.setResponse(() => fakeResponse({ id: 'OBS-3', statement: 'dm', channel: 'icontact' }));
    await oracle.addIcontact({ body: 'dm', to: 'jared' });

    const body = JSON.parse(f.calls[0]!.init.body as string);
    expect(body.type).toBe('icontact');
    expect(body.channel).toBe('icontact');
    expect(body.tags).toEqual(['to:jared']);
  });

  it('search() POSTs /search with top_k', async () => {
    const { oracle, f } = makeBearerClient();
    f.setResponse(() =>
      fakeResponse({
        query: 'q',
        results: [
          { id: 'OBS-9', statement: 'hit', channel: 'lab', score: 0.92 },
        ],
      }),
    );
    const out = await oracle.search('q', { topK: 5, rerank: true });

    const call = f.calls[0]!;
    expect(call.url).toBe(`${BEARER_BASE}/search`);
    expect(call.init.method).toBe('POST');
    expect(JSON.parse(call.init.body as string)).toEqual({ query: 'q', top_k: 5, rerank: true });
    expect(out).toHaveLength(1);
    expect(out[0]!.score).toBe(0.92);
  });

  it('recent() GETs /recent?limit=…&channel=…', async () => {
    const { oracle, f } = makeBearerClient();
    f.setResponse(() =>
      fakeResponse({
        items: [{ id: 'OBS-r1', statement: 'r1', channel: 'lab' }],
      }),
    );
    await oracle.recent({ limit: 3, channel: 'lab' });

    const call = f.calls[0]!;
    expect(call.url).toBe(`${BEARER_BASE}/recent?limit=3&channel=lab`);
    expect(call.init.method).toBe('GET');
  });

  it('ask() POSTs /ask and returns AskResponse', async () => {
    const { oracle, f } = makeBearerClient();
    f.setResponse(() =>
      fakeResponse({
        question: 'q?',
        answer: 'A [OBS-1].',
        model: 'llama3.1:8b',
        top_k: 8,
        citations: [{ obs_id: 'OBS-1' }],
        used: [],
      }),
    );
    const out = await oracle.ask('q?');
    expect((out as { answer: string }).answer).toBe('A [OBS-1].');
    const call = f.calls[0]!;
    expect(call.url).toBe(`${BEARER_BASE}/ask`);
    expect(call.init.method).toBe('POST');
  });

  it('connections() GETs /connections/<id>', async () => {
    const { oracle, f } = makeBearerClient();
    f.setResponse(() =>
      fakeResponse({
        obs_id: 'OBS-1',
        hebbian_neighbors: [{ obs_id: 'OBS-2', strength: 0.5 }],
        typed_edges: [],
        community_siblings: [],
      }),
    );
    const out = await oracle.connections('OBS-1');
    expect(f.calls[0]!.url).toBe(`${BEARER_BASE}/connections/OBS-1`);
    expect(out.hebbian_neighbors[0]!.obs_id).toBe('OBS-2');
  });

  it('selfInfo() GETs /self', async () => {
    const { oracle, f } = makeBearerClient();
    f.setResponse(() => fakeResponse({ node_id: 'vps-1', observations: 20617 }));
    const info = await oracle.selfInfo();
    expect(f.calls[0]!.url).toBe(`${BEARER_BASE}/self`);
    expect(info.observations).toBe(20617);
  });
});

// ---- signed-request mode ----

describe('Oracle (signed-request mode)', () => {
  it('routes search to /p/search and stamps all five signature headers', async () => {
    const f = captureFetch();
    f.setResponse(() => fakeResponse({ results: [] }));
    const kp = generateKeypair();
    const oracle = new Oracle({ keypair: kp, handle: 'tester', fetchImpl: f.impl });
    await oracle.search('q');

    const call = f.calls[0]!;
    expect(call.url).toBe(`${BEARER_BASE}/p/search`);
    const h = call.init.headers as Record<string, string>;
    expect(h['X-Pipernet-Handle']).toBe('tester');
    expect(h['X-Pipernet-Pubkey']).toMatch(/^[A-Za-z0-9+/=]+$/);
    expect(h['X-Pipernet-Timestamp']).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/);
    expect(h['X-Pipernet-Nonce']).toBeTruthy();
    expect(h['X-Pipernet-Signature']).toBeTruthy();
    // Sig is base64 of 64 bytes → 88 chars including '=' padding.
    expect(Buffer.from(h['X-Pipernet-Signature']!, 'base64').length).toBe(64);
    // No bearer header on signed requests.
    expect(h['Authorization']).toBeUndefined();
  });

  it('routes recent to /p/recent and computes empty-body sha256', async () => {
    const f = captureFetch();
    f.setResponse(() => fakeResponse({ items: [] }));
    const kp = generateKeypair();
    const oracle = new Oracle({ keypair: kp, handle: 'tester', fetchImpl: f.impl });
    await oracle.recent({ limit: 10 });

    const call = f.calls[0]!;
    expect(call.url).toBe(`${BEARER_BASE}/p/recent?limit=10`);
    expect(call.init.method).toBe('GET');
    // Body was empty → spec §3.2 demands sha256("") = EMPTY_BODY_SHA256_HEX
    // We can't see the canonical bytes directly, but we can check that the
    // empty-body hash constant is exactly what the spec says.
    expect(EMPTY_BODY_SHA256_HEX).toBe(sha256Hex(''));
  });

  it('add() rejects in signed mode with IngestError', async () => {
    const f = captureFetch();
    const kp = generateKeypair();
    const oracle = new Oracle({ keypair: kp, fetchImpl: f.impl });
    await expect(
      oracle.add('hello', { channel: 'lab' }),
    ).rejects.toThrow(IngestError);
    expect(f.calls).toHaveLength(0); // never even hit the wire
  });

  it('addDotpost() routes to /p/ingest with type=dotpost', async () => {
    const f = captureFetch();
    f.setResponse(() => fakeResponse({ id: 'OBS-px', statement: 'p', channel: 'mesh' }));
    const kp = generateKeypair();
    const oracle = new Oracle({ keypair: kp, handle: 'tester', fetchImpl: f.impl });
    await oracle.addDotpost({ body: 'hi mesh', to: 'all' });

    const call = f.calls[0]!;
    expect(call.url).toBe(`${BEARER_BASE}/p/ingest`);
    const body = JSON.parse(call.init.body as string);
    expect(body.type).toBe('dotpost');
    expect(body.channel).toBe('mesh');
    expect(body.tags).toEqual(['to:all']);
  });

  it('derives default handle from pubkey if not given', async () => {
    const f = captureFetch();
    f.setResponse(() => fakeResponse({ items: [] }));
    const kp = generateKeypair();
    const oracle = new Oracle({ keypair: kp, fetchImpl: f.impl });
    await oracle.recent();

    const h = f.calls[0]!.init.headers as Record<string, string>;
    expect(h['X-Pipernet-Handle']).toBe(`pubkey:${kp.pubkeyHex.slice(0, 16)}`);
  });
});

// ---- error mapping ----

describe('Error mapping', () => {
  function bearerClient() {
    const f = captureFetch();
    const oracle = new Oracle({ apiKey: 't', fetchImpl: f.impl });
    return { oracle, f };
  }

  it('401 → AuthError', async () => {
    const { oracle, f } = bearerClient();
    f.setResponse(() => fakeResponse({ error: 'bad_signature' }, { status: 401 }));
    await expect(oracle.search('q')).rejects.toThrow(AuthError);
  });

  it('404 → NotFoundError', async () => {
    const { oracle, f } = bearerClient();
    f.setResponse(() => fakeResponse({ error: 'missing' }, { status: 404 }));
    await expect(oracle.connections('OBS-nope')).rejects.toThrow(NotFoundError);
  });

  it('429 → RateLimitError with retryAfterS', async () => {
    const { oracle, f } = bearerClient();
    f.setResponse(() =>
      fakeResponse({ error: 'rate_limit', retry_after_s: 12 }, { status: 429 }),
    );
    try {
      await oracle.search('q');
      throw new Error('should have thrown');
    } catch (e) {
      expect(e).toBeInstanceOf(RateLimitError);
      expect((e as RateLimitError).retryAfterS).toBe(12);
    }
  });

  it('400 → IngestError', async () => {
    const { oracle, f } = bearerClient();
    f.setResponse(() => fakeResponse({ error: 'bad_request' }, { status: 400 }));
    await expect(oracle.add('x', { channel: 'lab' })).rejects.toThrow(IngestError);
  });

  it('5xx retries up to 3 times then throws', async () => {
    const { oracle, f } = bearerClient();
    f.setResponse(() => fakeResponse({ error: 'boom' }, { status: 503 }));
    await expect(oracle.search('q')).rejects.toThrow();
    expect(f.calls.length).toBe(3);
  });
});
