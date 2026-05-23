# @axxis/oracle

TypeScript SDK for **Oracle** — the Kin knowledge graph. Mem0-parity API, Ed25519 signed-request auth.

```ts
import { Oracle, loadKeypair } from '@axxis/oracle';

const oracle = new Oracle({ keypair: loadKeypair('key.json') });
await oracle.addDotpost({ body: 'Rocky shipped /p/ingest today', to: 'all', channel: 'lab' });
const results = await oracle.search('what did rocky ship');
console.log(results[0].statement);
```

This SDK mirrors the Python [`oracle-axxis`](https://github.com/dot-protocol/oracle-sdk-py) package
one-to-one. Side-by-side examples in the docs work in both languages with the
same method names and argument shape.

## Install

```bash
npm install @axxis/oracle
```

Requires Node 18+ (uses `globalThis.fetch` and Web Crypto).

## Authentication

The client resolves credentials in this priority order:

1. **Keypair** (`new Oracle({ keypair })`) → **signed-request** to `/p/*`
   endpoints. Public-contributor mode. Per-pubkey rate limit. You can read
   the public mesh without ever seeing a shared bearer token.
2. **API key** (`new Oracle({ apiKey })`) → **bearer** to all endpoints.
   Full ingest, full search, full graph. God-mode.
3. **Env vars** (`ORACLE_TOKEN` or `TREE_AUTH_TOKEN`) → bearer.
4. **None** → only `capabilities()` works.

## Generate a keypair

```ts
import { generateKeypair, saveKeypair } from '@axxis/oracle';
const kp = generateKeypair();
saveKeypair('key.json', kp); // remember `chmod 0600 key.json`
```

## Asymmetric write surface

`/p/ingest` (signed-request) only accepts protocol message types
(`handle_claim`, `handle_rotate`, `dotpost`, `icontact`). Use the typed
helpers:

```ts
await oracle.addDotpost({ body: 'hi', to: 'jared', channel: 'mesh' });
await oracle.addIcontact({ body: 'dm', to: 'loom' });
```

The generic `oracle.add(text, { channel, ... })` works in bearer mode only.
Calling it in signed-request mode throws `IngestError` before hitting the wire.

## Methods

| Method | Endpoint (bearer / signed) | Notes |
|---|---|---|
| `add(text, opts)` | `POST /ingest` | bearer-only |
| `addDotpost(opts)` | `POST /ingest` or `POST /p/ingest` | both |
| `addIcontact(opts)` | `POST /ingest` or `POST /p/ingest` | both |
| `search(query, opts?)` | `POST /search` or `POST /p/search` | hybrid RRF |
| `recent(opts?)` | `GET /recent` or `GET /p/recent` | optional channel filter |
| `ask(query, opts?)` | `POST /ask` or `POST /p/ask` | RAG; supports `stream: true` |
| `connections(obsId)` | `GET /connections/<id>` or `/p/...` | graph neighbourhood |
| `selfInfo()` | `GET /self` or `GET /p/self` | server self-report |
| `capabilities()` | `GET /capabilities` | open, no auth |

## Streaming `/ask`

```ts
for await (const token of await oracle.ask('what is piperchat sealed body?', { stream: true })) {
  process.stdout.write(token);
}
```

## Errors

`OracleError` (base) → `AuthError`, `IngestError`, `NotFoundError`,
`RateLimitError` (with `retryAfterS`). 5xx is retried up to 3 times with
exponential backoff (1s, 2s, 4s).

## Runtime validation

Server responses are validated through Zod schemas with `.passthrough()` — you
get type narrowing on documented fields and any extras the server returns are
preserved untouched. Schemas are exported under the `schemas` namespace:

```ts
import { schemas } from '@axxis/oracle';
const obs = schemas.Observation.parse(someUntrustedPayload);
```

## License

Apache 2.0. See [LICENSE](./LICENSE).

Built by Kin / Piper. Part of the [pipernet](https://github.com/dot-protocol) family.
