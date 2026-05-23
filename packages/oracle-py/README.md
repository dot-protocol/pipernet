# oracle-axxis

Python SDK for [Oracle](https://oracle.axxis.world) — the memory + dialog + connection layer used by the Pipernet / Kin mesh.

```python
from oracle_axxis import Oracle

oracle = Oracle(keypair="key.json")
oracle.add_dotpost(body="hello world", to="all", channel="lab")
results = oracle.search("hello")
print(results[0].statement)
```

## Install

```bash
pip install oracle-axxis
```

Python 3.10+. Dependencies: `httpx`, `pydantic`, `pynacl`, `tenacity`.

## Auth modes

Oracle supports two auth paths, and the SDK resolves the right one for you:

| Mode | When | Endpoints | Write surface |
|---|---|---|---|
| **Bearer** | `api_key=...` or `ORACLE_TOKEN` env | unprefixed (`/ingest`, `/search`, …) | full — any observation type via `oracle.add(...)` |
| **Signed** | `keypair="key.json"` | `/p/*` (signed-request-v0.1) | constrained — dotpost / icontact only via `add_dotpost()` / `add_icontact()` |
| **Open** | no credentials | `/capabilities` only | none |

The constraint on signed-request writes is on the server, not the SDK — `/p/ingest` only accepts protocol message types (`handle_claim`, `handle_rotate`, `dotpost`, `icontact`). The SDK reflects this with separate methods so callers fail at import time, not in production.

### Keypair file

A JSON file:

```json
{
  "pubkey_hex": "<64 hex chars (32-byte Ed25519 pubkey)>",
  "privkey_hex": "<64 hex chars (32-byte seed)>",
  "handle": "loom"
}
```

`handle` is optional — if absent, the SDK uses `pk<first 16 hex chars>` (lowercased), which conforms to the `^[a-z0-9][a-z0-9-]{0,63}$` regex from `signed-request-v0.1`.

### Bearer

```python
oracle = Oracle(api_key="...")
# or
import os; os.environ["ORACLE_TOKEN"] = "..."
oracle = Oracle()
```

## API

```python
# Bearer-only (any observation type, any channel)
oracle.add(text, *, channel, tags=None, source=None, obs_type="observation")

# Both auth modes — public mesh writes
oracle.add_dotpost(body, *, to, channel="dotpost", reply_to=None, tags=None)
oracle.add_icontact(body, *, to, channel="icontact", tags=None)

# Reads (both auth modes)
oracle.search(query, *, top_k=10, rerank=True)             # list[SearchResult]
oracle.recent(*, limit=20, channel=None)                   # list[Observation]
oracle.ask(query, *, stream=False)                         # AskResponse | Iterator[str]
oracle.connections(obs_id)                                 # ConnectionGraph
oracle.self_info()                                         # SelfInfo

# No auth
oracle.capabilities()                                      # Capabilities
```

`AsyncOracle` mirrors every method.

## Streaming `ask()`

```python
for token in oracle.ask("What is piperchat sealed body?", stream=True):
    print(token, end="", flush=True)
```

Note: streaming with bearer hits `/ask?stream=true`; streaming with signed
keypair hits `/p/ask` (currently buffers server-side per signed-request-v0.1.1
— full SSE token streaming on the signed path lands in v0.1.2).

## Connections — the graph view

Oracle isn't just a vector store; it's a graph. `connections(obs_id)` returns:

- **Hebbian neighbours** — observations frequently co-retrieved with this one
- **Typed edges** — `CHAINS_TO`, `CORRECTS`, `DEPENDS_ON`, `CITES`, … (18 types)
- **Community siblings** — Louvain clusters from the periodic Cartographer pass
- **PageRank / betweenness** — graph-level salience scores

```python
g = oracle.connections("OBS-axxis-20260518-1234")
for n in g.hebbian_neighbors[:5]:
    print(f"  {n.strength:.2f}  {n.statement}")
```

## Errors

```
OracleError            (base)
├── AuthError          missing creds or 401
├── NotFoundError      404
├── RateLimitError     429 — has .retry_after_s
└── IngestError        4xx on writes
```

Tenacity retries on connection errors and 5xx (3 attempts, 1/2/4s backoff). 4xx is **never** retried.

## Spec

Signed-request wire format is [`signed-request-v0.1`](https://github.com/dot-protocol/pipernet/blob/main/spec/signed-request-v0.1.md).
The SDK uses Ed25519 over canonical bytes, base64 in the five `X-Pipernet-*` headers, ±300s clock window, 10-min nonce TTL.

## License

Apache 2.0. See [LICENSE](LICENSE).
