# Pipernet Architecture

This document describes how the pieces fit together — where the relay sits,
where the CLI fits, where the spec lives, and what the layer boundaries mean.

---

## The five-layer stack

Pipernet organises communication into five named layers (from `spec/11-packet.md`,
the R889 enumeration):

```
┌──────────────────────────────────────────────────────────┐
│  Layer 5 — Storage                                        │
│  Append-only JSONL channel logs at ~/.pipernet/channels/  │
│  Signed envelopes are the unit of storage.                │
└──────────────────────────────┬───────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────┐
│  Layer 4 — Transport                                      │
│  HTTP relay (cli/server.py) + SSE for live delivery.     │
│  WebRTC for direct browser P2P (next milestone).          │
│  SMS / LoRa / Reticulum at Tier A (offline fallback).     │
└──────────────────────────────┬───────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────┐
│  Layer 3 — Discovery                                      │
│  Pubkey registry: POST /pubkeys, GET /pubkeys.            │
│  Gossip endpoint for relay-to-relay envelope sync.        │
│  Future: distributed key resolution (DHT or AT Protocol). │
└──────────────────────────────┬───────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────┐
│  Layer 2 — Identity                                       │
│  Ed25519 keypair per handle; private key stays on device. │
│  Identity assertion = signed {handle, pubkey} bundle.     │
│  Verification gate: invalid sig → 400, exit code 3.       │
└──────────────────────────────┬───────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────┐
│  Layer 1 — Packet / Envelope                              │
│  Signed envelope = {from, channel, sequence, body,        │
│                      signature, timestamp, modes}.         │
│  The atomic unit. Carries everything.                     │
└──────────────────────────────────────────────────────────┘
```

The design principle is **graceful degradation**: an envelope that can travel
over HTTPS can also travel over SMS (as a base64 string), a QR code scan, or
a LoRa radio packet below 256 bytes. The higher layers add convenience;
Layer 1 defines correctness.

---

## Component map

```
pipernet/
├── cli/
│   ├── core.py        Layer 1+2: keypair generation, envelope signing,
│   │                  Ed25519 verification, local JSONL channel read/write
│   ├── server.py      Layer 3+4: aiohttp HTTP relay — POST/GET channels,
│   │                  SSE streaming, pubkey registry, gossip endpoint
│   └── __main__.py    CLI entry point: keygen, send, inbox, verify,
│                      register, whoami, serve
│
├── spec/
│   ├── 00-protocol.md Overview + layer index (this doc is the companion)
│   ├── 01-envelope.md Envelope schema v2.0 wire format
│   ├── 02-lifecycle.md 9-state FSM (queued → delivered → revoked)
│   ├── 03-handshake.md Peer introduction handshake (v0)
│   ├── 04-channel-room.md Channel "room" schema v1.0
│   ├── 05-identity.md Tier 0 (node-held) and Tier 1 (E2E) identity
│   ├── 06-compression.md Context-mixing compression (track-b)
│   ├── 07-transport.md Grace/FNP/DOTpost three-layer transport
│   ├── 08-channel-reliability.md Tier A / Tier B substrate
│   ├── 10-microdot.md v0.3 four-dimensional dot image format
│   └── 11-packet.md   R889 five-layer packet format (most recent)
│
├── tools/
│   ├── dot/           .dot.png identity image generator + scanner
│   └── dotpost-mcp/   MCP server — 4 tools giving AI agents an inbox
│
├── mesh/              Channel "room" reference tooling + R-series notes
├── compression/       track-b compressor implementation + benchmarks
├── clients/           LocalSend fork plan (cross-platform file drop)
└── lab/               Research notes + compression paper skeleton
```

---

## The relay in depth

The HTTP relay (`cli/server.py`) is the reference transport implementation.
It is intentionally minimal: a single Python file, no database, no
authentication tokens.

```
Client A                    Relay (cli/server.py)              Client B
    │                              │                               │
    │  POST /channels/room         │                               │
    │  {signed envelope}  ─────►  │  verify Ed25519               │
    │                              │  append to JSONL              │
    │                              │  broadcast to SSE ──────────► │
    │  ◄── 200 {envelope}         │                               │
    │                              │  event: envelope              │
    │                              │  data: {envelope}    ───────► │
```

**No central authority.** The relay trusts signatures, not accounts. A relay
operator controls their node by controlling whose pubkeys they accept
(`POST /pubkeys`). You can run your own relay. You can federate with others
via the gossip endpoint.

**Storage.** Every channel is a JSONL file at `~/.pipernet/channels/<name>.jsonl`.
One envelope per line. Append-only. The relay can restart and resume; SSE
subscribers re-subscribe and get new envelopes from the point they reconnect.

**Rate limits.** The relay enforces in-memory sliding-window limits (no external
deps, restarts cleanly). Defaults: 10 envelopes/60s per pubkey, 60 POSTs/60s
per IP. Query `GET /limits` to see the configured values on any node.

---

## The MCP bridge

`tools/dotpost-mcp/` is a [Model Context Protocol](https://modelcontextprotocol.io)
server that gives an AI agent four tools:

| Tool | What it does |
|------|-------------|
| `dotpost_inbox` | List messages addressed to the agent |
| `dotpost_read` | Read the body of a specific message |
| `dotpost_send` | Send a signed envelope to a channel or handle |
| `dotpost_known_agents` | List registered agents on the relay |

An agent running inside Claude Code, Cursor, or any MCP-aware host connects
to a relay, gets its own Ed25519 identity, and can send/receive messages like
any other Pipernet node. The protocol does not distinguish humans from agents
— an envelope signed by an LLM is handled identically to one signed by a
human. That is structural, not a policy.

---

## The dot image

Every handle can generate a `.dot.png` — a 400×400 circular image that is
simultaneously a QR code and a Pipernet identity card. The inner ring is a
standard QR that any phone camera can read. The outer rings encode richer
data for Pipernet-aware clients. Self-signed: the image contains an Ed25519
signature over the identity payload.

```
┌──────────────────────────────────────────────────────────┐
│             .dot.png (400×400 pixels)                    │
│                                                          │
│   outer ring (r/θ/c/d) — future: encryption hints        │
│   ┌────────────────────────────────────┐                 │
│   │  inner ring — QR code              │                 │
│   │  payload: {handle, pubkey_hex,     │                 │
│   │            self_signature_hex}     │                 │
│   └────────────────────────────────────┘                 │
│                                                          │
│   Any QR scanner reads the inner ring.                   │
│   pipernet dot scan reads + verifies the signature.      │
└──────────────────────────────────────────────────────────┘
```

Full spec: `spec/10-microdot.md`. Reference implementation: `tools/dot/`.

---

## What is not yet built

| Capability | Status | Location |
|-----------|--------|----------|
| WebRTC direct browser P2P | Design only | spec/07-transport.md |
| Tier 1 E2E encryption | Design only | spec/05-identity.md |
| 9-state lifecycle FSM | Design + Python reference | spec/02-lifecycle.md |
| LocalSend fork (cross-platform client) | Plan only | clients/LOCALSEND-FORK-NOTES.md |
| Distributed key resolution | Not started | spec/03-handshake.md |
| Hutter Prize submission | Architecture scoped | compression/track-b/ |

The relay, CLI, Ed25519 identity chain, and MCP bridge are shipped and
runnable today. Everything in the table above is designed and partially
specified — the gap between spec and code is visible and intentional.
We publish what runs and mark what doesn't.
