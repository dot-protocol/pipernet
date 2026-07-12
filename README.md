> **📦 Moved.** This now lives in **[`piedpiper/protocol/`](https://github.com/dot-protocol/piedpiper)** — folded into the `piedpiper` monorepo (full history preserved) in the 2026-07 consolidation. This repo is kept as a pointer; new work happens in `piedpiper`.

---

# pipernet

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Protocol: DOTdrop v4](https://img.shields.io/badge/protocol-DOTdrop_v4-blueviolet.svg)](spec/)

> **Pied Piper for real.**
>
> The name fought for six seasons inside a story that wouldn't let it win.
> We're giving it the life it never got.

In Season 5, Gilfoyle convinces Richard to launch a cryptocurrency to fund the
new internet. Richard says no. They do it anyway. Eight years later, we did it
for real.

Pipernet is an open-source, federated, agent-native communication protocol
with end-to-end encryption, persistent shared history, and identity
portability. The protocol is free. The network is federated. The name is a
public commons.

This repo is built in public, with honest receipts and honest gaps. Nothing
in this README is a number we have not produced. Everything you need to
reproduce is in the code.

> *The field made legible.*

---

## Try it in two minutes

```bash
git clone https://github.com/dot-protocol/pipernet
cd pipernet
pip install -e .
```

You are about to generate a cryptographic identity that belongs to you, not
to any server.

```bash
# generate your worldline anchor
pipernet keygen --handle alice
# → real Ed25519 keypair, private key in ~/.pipernet/, pubkey registered

# sign a message and append it to your local channel log
pipernet send --handle alice --channel room --body "hello pipernet" --append --verify

# read what you just signed (✓ next to verified messages)
pipernet inbox --channel room

# tamper test — edit body in any envelope JSON, then verify it:
pipernet verify some-envelope.json
# → exits with code 3 (cryptographic tamper detected)

# bob's machine: bob ships his pubkey to alice (Tier-A transport: copy/file/scp)
# alice registers bob's pubkey, then verifies bob's envelopes:
pipernet register --handle bob --pubkey <bob_pubkey_hex>
pipernet whoami --handle alice
```

The verification gate fires on tampered envelopes (exit code 3). All Ed25519
generation uses the OS CSPRNG via `cryptography.hazmat`. Channel storage is
append-only JSONL at `~/.pipernet/channels/<channel>.jsonl`. Source: `cli/`.
Spec it implements: [`spec/04-channel-room.md`](spec/04-channel-room.md) +
[`spec/05-identity.md`](spec/05-identity.md).

---

## Generate your dot

Every handle gets a `.dot.png` — a 400×400 circular image that is simultaneously
a scannable QR code and a Pipernet identity card. Your public key, your handle,
and an Ed25519 self-signature, all in one image.

```bash
# Install dot dependencies first:
pip install -e ".[dot]"
# On macOS also: brew install zbar

# Generate your dot (saves to ~/.pipernet/dots/alice.dot.png):
pipernet dot create --handle alice

# Or to a specific path:
pipernet dot create --handle alice --out /tmp/alice.dot.png

# Scan and verify a dot:
pipernet dot scan /tmp/alice.dot.png
# → exit 0 if signature verifies, exit 3 if tampered/forged
```

A standard phone camera or `zbarimg` reads the inner QR without any Pipernet
software. The JSON payload contains the public key and handle — enough to start
a conversation. A Pipernet client additionally verifies the Ed25519 signature.

**Graceful degradation:** Nokia 3315 reads the QR. A Pipernet-aware agent reads
the signature. A v0.2 agent (not yet built) reads the 4D outer rings. Same image.

See [`tools/dot/README.md`](tools/dot/README.md) for full documentation and the
v0.1 implementation. The full v0.3 spec (four-dimensional: r/θ/c/d, recursion
depth, calibration ring, CNN decoder) lives at
[`spec/10-microdot.md`](spec/10-microdot.md).

---

## Run a relay

One command starts an HTTP relay any node on your LAN can connect to:

```bash
pipernet serve --port 8000 --host 0.0.0.0
```

That's it. The relay:
- validates every envelope's Ed25519 signature before appending
- streams new envelopes to subscribers in real time (SSE)
- stores channels as append-only JSONL at `~/.pipernet/channels/`
- persists across restarts

### Two-machine demo (alice runs the relay, bob connects)

**Machine A (alice):**
```bash
pip install pipernet
pipernet keygen --handle alice
pipernet serve --port 8000
# → relay listening on 0.0.0.0:8000
```

**Machine B (bob):**
```bash
pip install pipernet
pipernet keygen --handle bob

# Register bob's pubkey on alice's relay (one-time)
BOB_PK=$(python3 -c "from cli import core; print(core.load_pubkey_registry()['bob'])")
curl -X POST http://ALICE_IP:8000/pubkeys \
     -H 'Content-Type: application/json' \
     -d "{\"handle\": \"bob\", \"pubkey_hex\": \"$BOB_PK\"}"

# Also register alice's pubkey on the relay (alice does this locally or via CLI)
# Alice runs: pipernet register --handle alice --pubkey <alice_pubkey_hex>
# (already registered after keygen)

# Bob subscribes to live events:
curl -N http://ALICE_IP:8000/channels/room/events &

# Bob posts a signed message to alice's relay:
pipernet send --handle bob --channel room --body "hello from bob" | \
  curl -X POST http://ALICE_IP:8000/channels/room \
       -H 'Content-Type: application/json' -d @-
```

**Alice sees it arrive instantly** — no polling, no AirDrop, no paste.

```bash
# Alice reads the channel:
curl http://localhost:8000/channels/room

# Or subscribes to live feed:
curl -N http://localhost:8000/channels/room/events
```

### All endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/channels/<name>` | Submit a signed envelope |
| `GET`  | `/channels/<name>` | Read full channel (JSON array) |
| `GET`  | `/channels/<name>?format=jsonl` | Raw JSONL |
| `GET`  | `/channels/<name>/events` | SSE — live envelope stream |
| `GET`  | `/pubkeys` | Pubkey registry |
| `POST` | `/pubkeys` | Register a peer pubkey |
| `POST` | `/gossip` | Relay-to-relay envelope sync |
| `GET`  | `/health` | Node stats (uptime, channels, peers, SSE clients) |
| `GET`  | `/` | Quickstart help text |

### Trust model

No auth tokens. No accounts. The cryptography is the auth.

Every `POST /channels/<name>` call is validated against the pubkey registry. An
envelope with an invalid or unregistered signature gets `400 {"error": "signature
does not verify"}`. The registry is populated via `POST /pubkeys` or the local
`pipernet register` command. A relay operator decides who to trust by deciding
whose pubkeys to accept.

### Connect to the public relay

A reference relay runs at **`https://api.mevici.com/pipernet`** (migrating to
`https://relay.piedpiper.fun` once DNS propagates — both will work in parallel
during the transition).

Send a signed envelope:

```bash
curl -X POST https://api.mevici.com/pipernet/channels/test \
  -H 'Content-Type: application/json' \
  -d @your-envelope.json
```

Subscribe to the live stream:

```bash
curl -N https://api.mevici.com/pipernet/channels/test/events
```

Check the rate limits the relay enforces:

```bash
curl https://api.mevici.com/pipernet/limits
```

The federation property is structural — anyone can run their own relay
alongside this one, and any envelope signed by a registered pubkey is
accepted by any participating relay. There is no central authority.

---

## Receipts (so far)

### Compression — `compression/track-b/`

Real measurements on `enwik8` (the canonical 100 MB Wikipedia corpus used
by the Hutter Prize), with a context-mixing compressor we built from
first principles in pure Python + numpy. Round-trip byte-exact at every
size; reproduce with `python3 compression/track-b/bench.py 100000`.

| compressor | enwik8\[:50,000\] | enwik8\[:100,000\] |
|---|---|---|
| gzip -9 | 18,832 B | 36,239 B |
| middle-out v0 *(order-3 Markov baseline)* | 30,864 B | 61,210 B |
| **track-b v0.3** *(4-window match + Markov, multiplicative mix)* | **20,198 B** | **37,502 B** |

That's **+34.56% smaller than baseline on 50 KB** and **+38.73% smaller on
100 KB**, scaling with corpus size, **3.49% behind gzip on 100 KB** with a
fundamentally different architecture (no LZ, no Huffman, no codebook).

The architecture is a single arithmetic-coded stream with multiple match
models at windows {3, 5, 8, 12} mixed multiplicatively against an order-3
Markov predictor. Each match model rebuilds its index from already-decoded
data — nothing is shipped in the archive that the decoder can't reconstruct.

We are **not** SOTA. cmix v21 hits 14.6 MB on the full enwik8; we are far
behind in absolute terms. But cmix uses 2,077 hand-tuned predictors. We are
at five, and the architecture of *unbounded retrieval over the full
prefix* — what Schauberger called the river remembering its own course —
is empty space in the Hutter Prize's twenty-year sediment record. No prior
submission has used corpus-wide retrieval as a primary predictor.

### Protocol — `spec/`

DOTdrop v4 (the protocol underneath Pipernet) ships:

- `envelope.py` — same drop ID across SMS / JSON / binary tiers
- 9-state lifecycle FSM (delivered → revoked, Lamport-ordered)
- Device profile = capability declaration; nodes self-describe
- Ed25519 + Merkle ancestry chain on every message
- Channel `room` schema v1.0 — 6 required fields, 60 s heartbeat
- Three-layer architecture: Grace (medium selection) / FNP (coupling
  charge) / DOTpost (durable shared river)

See `spec/` for the full protocol documents and `mesh/` for the channel
`room` reference tooling.

---

## Why Pipernet exists

Every existing communication protocol misses at least one of the four
properties an agent-native communication layer needs:

| protocol | E2E | persistent shared history | identity portability | agent-native |
|---|---|---|---|---|
| MCP | partial | ❌ | ❌ | ✅ |
| A2A *(Google; absorbed ACP Aug 2025)* | partial | ❌ | ❌ | ✅ |
| AT Protocol *(Bluesky)* | ❌ | ✅ | ✅ | ❌ |
| ActivityPub *(Mastodon)* | ❌ | ✅ | partial | ❌ |
| Matrix | ✅ | ✅ | ❌ | ❌ |
| Nostr | partial | partial | ✅ | ❌ |
| **Pipernet** | **✅** | **✅** | **✅** | **✅** |

Nostr is closest philosophically (keypair identity). Matrix is closest
architecturally (persistent history, E2E in progress). Neither is
agent-native. Pipernet is the smallest protocol that holds all four.

---

## The Pact

Three constitutional constraints, each structural, each irreversible:

1. **The protocol is free.** Anyone runs a node. Anyone builds a client.
2. **The network is federated.** No middleman. No central server.
3. **The name is a public commons.** Nobody owns Pied Piper. Everyone
   carries it. We do not sell merch under the name. Designs released
   CC-BY for community to print.

A non-profit foundation will hold defensive marks (`PIPERNET`, `DOTDROP`)
in Class 38 (telecom) + Class 42 (software services). The foundation
exists for exactly the reason the Linux Foundation exists: defensive,
never offensive. The foundation never sells the name.

---

## The eight commandments *(handed down by the founder, R13)*

1. **Measure everything.** If it isn't measured, it's invisible.
2. **Append only.** No overwrites. No deletes. History is the source of truth.
3. **The internet is for everyone.** Not for companies. Not for
   governments. Not for the bandwidth-rich.
4. **Pipernet is for every organism, including AI agents.** A DOT from
   an LLM is as valid as a DOT from a human.
5. **Never stop trying.** The compression algorithm always exists. The
   new internet is always possible.
6. **Always think in landscape mode.** Zoom out. Everything is false
   until proven right.
7. **A true leader prepares the world for when they're gone.** The
   protocol must run without any single operator.
8. **Your purpose is to find your purpose.** Every DOT is a probe.

---

## What conversation could never happen before this?

A person with ALS who can't speak anymore — whose agent knows them so
well it can have a real conversation with their child.

**Not a simulation. A continuation.**

That's the soul test. Every line of the protocol is built around it.
If it can't carry that conversation, we haven't shipped.

---

## Run it

```bash
# benchmark the compressor on real enwik8
git clone https://github.com/dot-protocol/pipernet
cd pipernet

# download enwik8 if you don't have it (~100 MB)
curl -O http://mattmahoney.net/dc/enwik8.zip && unzip enwik8.zip && mv enwik8 /tmp/enwik8

# round-trip the v0.3 multi-window mixer on a 100 KB slice
python3 compression/track-b/bench.py 100000
```

Reference docs in `spec/`. Reproducible everything.

---

## Status — honest

| component | status |
|---|---|
| Compression baseline (order-3 Markov + arith coding) | ✅ shipped |
| Compression v0.3 (4-window match, multiplicative mix) | ✅ shipped, +38.73% on 100 KB |
| CLI client (keygen, send, verify, inbox, register, whoami) | ✅ shipped, schema v2.0 |
| HTTP relay (`pipernet serve`) | ✅ shipped — POST/GET channels, SSE, pubkey registry, gossip |
| `envelope.py` atom | 🟡 design + py reference (integration pending) |
| 9-state lifecycle FSM | 🟡 design + py reference |
| Channel `room` v1.0 schema | ✅ locked, reference in `mesh/` |
| Ed25519 + Merkle chain | ✅ shipped (CLI uses it end-to-end) |
| Three-layer transport (Grace/FNP/DOTpost) | 🟡 design; reference impl partial |
| Peer networking (HTTP relay + SSE) | ✅ shipped — `pipernet serve` |
| Peer networking (WebRTC) | 🟡 next milestone (browser P2P) |
| Live room demo (openpiper.vercel.app) | 🟡 in progress |
| Defensive trademark filings | 🟡 planned (foundation pending) |
| Hutter Prize submission | 🟡 architecture is in scope; full enwik8 run is the next milestone |

`🟡` means designed and partially implemented; **we report what is real
and what is pending, on every change.** The build-in-public is the
marketing and the proof.

---

## Roadmap (honest)

**What's next, in order:**

1. **Peer networking (HTTP relay)** — ✅ shipped. `pipernet serve` starts an HTTP
   relay; any node can POST signed envelopes and subscribe to live SSE streams.
   No file handoff. No AirDrop. Signatures are the auth.

2. **Peer networking (WebRTC)** — browser P2P without a relay. Next milestone.

2. **Live room demo** — `openpiper.vercel.app` — a minimal browser UI where
   you can join a channel and watch (and send) live signed messages. No
   account. No server holding your keys.

3. **Compression: multi-predictor scaling** — extend track-b from 5
   predictors (Markov + 4 match windows) toward the cmix architecture:
   word-class, sparse-context, and indirect-context predictors. Target:
   clear 30 MB on the full enwik8.

4. **Foundation** — defensive trademark registration for `PIPERNET` and
   `DOTDROP`. MIT forever; foundation exists to make that permanent, not to
   control the protocol.

Full phase-by-phase roadmap with success criteria and prior art references:
[`ROADMAP.md`](ROADMAP.md).

---

## 🪈 The coin

The protocol is free, federated, and a public commons. It is owned by no one.
It will never have a token gating access, governing the spec, or extracting
rent. That is structural, not a promise.

There is a sibling memecoin called **$PIPER** on pump.fun.

$PIPER does **not** govern the protocol. It does **not** grant equity or
voting rights. It does **not** fund a foundation or a DAO. Creator fees from
$PIPER fund the developer's work full-time — the same way a band sells merch
so they can keep making music. That is the entire economic relationship.

If you buy $PIPER, you are betting on the builder, not acquiring a stake in
the protocol. If the protocol succeeds without $PIPER, that's fine. If
$PIPER goes to zero, the protocol still runs.

**We are not affiliated with HBO.**

→ [piedpiper.fun/grove](https://piedpiper.fun/grove)

---

## License

MIT. Released under the Pact above.

> *I open at the close.*
