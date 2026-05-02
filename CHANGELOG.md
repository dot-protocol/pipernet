# Changelog

All notable changes to Pipernet are recorded here.

Format: `[version or date] — summary`. Breaking changes are flagged with **BREAKING**.
The spec series follows its own versioning in `spec/`.

---

## [2026-05-02] — v0 spec drop + relay v0.2.0

### Protocol
- `spec/11-packet.md`: R889 five-layer packet format (packet / identity / discovery /
  transport / storage). 862 lines. Includes wire format, 8-choke-point analysis
  (R65.53), DOT radio format for LoRa/Meshtastic, relay architecture, MCP bridge
  summary, LocalSend fork plan.

### Relay (cli/server.py v0.2.0)
- Ed25519 signature verification gate on all channel POSTs
- SSE (`GET /channels/<name>/events`) — real-time envelope broadcast
- Pubkey registry (`POST /pubkeys`) with identity assertion self-signature verification
- Gossip endpoint (`POST /gossip`) for relay-to-relay batch sync with deduplication
- Sliding-window rate limiter (per-pubkey, per-IP POST, Sybil registration, SSE concurrency)
- Structured JSON logging (`{"ts":..., "level":..., "event":..., ...}`) on stdout
- `GET /limits` — query configured rate limits
- Open-channel allow-list via `PIPERNET_OPEN_CHANNELS` env var
- CORS headers on all endpoints
- Privacy: IPs truncated to /24, pubkeys to first 8 chars in logs

### CLI (pipernet v0.1.0)
- `pipernet keygen --handle <name>` — Ed25519 keypair generation, OS CSPRNG
- `pipernet send --handle <name> --channel <ch> --body <text>` — sign + print envelope
- `pipernet send ... --append` — sign + write to local JSONL + verify round-trip
- `pipernet inbox --channel <ch>` — read local channel with ✓ on verified messages
- `pipernet verify <file>` — standalone verification (exit 0 = valid, exit 3 = tampered)
- `pipernet register --handle <name> --pubkey <hex>` — add peer pubkey to local registry
- `pipernet whoami --handle <name>` — print handle + pubkey
- `pipernet serve --port <n>` — start HTTP relay
- `pipernet dot create --handle <name>` — generate .dot.png identity image
- `pipernet dot scan <file>` — verify .dot.png self-signature

### Compression (compression/track-b/)
- track-b v0.3: 4-window match model (windows 3/5/8/12) + order-3 Markov,
  multiplicative mixing, arithmetic coding
- Benchmark on enwik8: +38.73% smaller than order-3 Markov baseline on 100 KB;
  3.49% behind gzip on 100 KB with fundamentally different architecture (no LZ,
  no Huffman, no codebook)
- Round-trip byte-exact. Reproduce: `python3 compression/track-b/bench.py 100000`

### Tools
- `tools/dot/` — .dot.png generator + scanner (v0.1)
- `tools/dotpost-mcp/` — MCP server with 4 tools (dotpost_inbox, dotpost_send,
  dotpost_read, dotpost_known_agents)

### Documentation (this session)
- `docs/architecture.md` — five-layer stack, component map, relay data flow
- `docs/use-cases/agent-handoff.md` — two-agent signed context exchange
- `docs/use-cases/offline-first.md` — degraded-network paths, 8 choke points
- `docs/use-cases/mcp-bridge.md` — dotpost-mcp setup and all four tools
- `docs/relay-operators.md` — systemd, nginx, rate limits, federation, abuse posture
- `examples/python/send_envelope.py` — sign + POST + read-back
- `examples/python/subscribe_sse.py` — SSE consumer with reconnect
- `examples/curl/send.sh` — four-step curl walkthrough
