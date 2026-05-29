# USER_MANUAL — dot-protocol/pipernet

## What it is

A Python CLI + HTTP relay implementing the Pipernet federated communication protocol: Ed25519-signed message envelopes, append-only JSONL channel storage, SSE live streams, and a pubkey-based trust model (no accounts, no tokens — the signature is the auth). Schema v2.0, DOTdrop v4.

## Install

```bash
git clone https://github.com/dot-protocol/pipernet
cd pipernet
pip install -e .           # installs `pipernet` CLI
pip install -e ".[dot]"    # also installs dot-image deps (qrcode, Pillow, zbar)
```

Python 3.10+. No external process required for the CLI; `aiohttp>=3.9` is required only for `pipernet serve`.

## CLI commands

### Identity

```bash
# Generate Ed25519 keypair. Private key at ~/.pipernet/<handle>.private.bin (0600).
# Registers pubkey in ~/.pipernet/pubkeys.json.
pipernet keygen --handle alice

# Show identity for a handle
pipernet whoami --handle alice
# -> { "handle": "alice", "pubkey_hex": "...", "tier": "0", "keystore": "~/.pipernet/alice.private.bin" }

# Register a peer's public key for local verification
pipernet register --handle bob --pubkey <64-hex-char-ed25519-pubkey>
```

### Send and receive

```bash
# Build a signed envelope and print JSON to stdout
pipernet send --handle alice --channel room --body "hello pipernet"

# Sign, self-verify, and append to the local channel log
pipernet send --handle alice --channel room --body "hello" --append --verify

# Reply to a specific message (by sequence + sender)
pipernet send --handle alice --channel room --body "reply" --parent '[3,"bob"]' --append

# Read the local channel log (pretty-printed with verification marks)
pipernet inbox --channel room

# Dump raw JSON
pipernet inbox --channel room --json
```

### Verify

```bash
# Verify an envelope file — exits 0 if valid, 3 if tampered
pipernet verify envelope.json

# Verify from stdin
cat envelope.json | pipernet verify -
```

### Identity logogram (.dot.png)

```bash
# Generate a circular QR-code identity badge
pipernet dot create --handle alice
# -> ~/.pipernet/dots/alice.dot.png

pipernet dot create --handle alice --out /tmp/alice.dot.png

# Scan and verify a .dot.png
pipernet dot scan /tmp/alice.dot.png
# exit 0 = valid, exit 3 = tampered
```

### Relay

```bash
# Start an HTTP relay on all interfaces, port 8000
pipernet serve --port 8000 --host 0.0.0.0

# With a named node handle and verbose logging
pipernet serve --port 8000 --node alice --log-level debug
```

### Telegram bridge

```bash
# Start piperbot (Telegram ↔ Pipernet bridge)
pipernet bot --config ~/.pipernet/piperbot.json

# Dry-run (CI / no Telegram connection)
pipernet bot --dry-run --debug
```

## Relay HTTP API

Base URL: `http://<host>:<port>` (local) or `https://api.mevici.com/pipernet` (public reference relay).

| Method | Path | Description | Body / Params |
|--------|------|-------------|---------------|
| `POST` | `/channels/<name>` | Submit a signed envelope | JSON envelope object |
| `GET` | `/channels/<name>` | Full channel as JSON array | — |
| `GET` | `/channels/<name>?format=jsonl` | Raw JSONL | — |
| `GET` | `/channels/<name>/events` | SSE live stream of new envelopes | — |
| `GET` | `/pubkeys` | Full pubkey registry | — |
| `POST` | `/pubkeys` | Register a peer pubkey | `{"handle":"bob","pubkey_hex":"..."}` |
| `POST` | `/gossip` | Relay-to-relay envelope batch sync | JSON array of envelopes |
| `GET` | `/health` | Node stats | — |
| `GET` | `/limits` | Configured rate limits (public) | — |
| `GET` | `/` | Quickstart help | — |

### Trust model

No auth tokens. The cryptography is the auth. Every `POST /channels/<name>` validates the envelope's Ed25519 signature against the pubkey registry. Unregistered or invalid signatures return `400 {"error": "signature does not verify"}`.

### Rate limits (default)

| Scope | Limit | Window |
|-------|-------|--------|
| Per pubkey handle | 10 envelopes | 60 s |
| Per IP (POST total) | 60 requests | 60 s |
| Per IP (Sybil — unique handle registrations) | 30 handles | 3600 s |
| Per IP (SSE connections) | 5 concurrent | — |

### curl examples

```bash
# Submit a signed envelope
pipernet send --handle alice --channel room --body "hi" | \
  curl -X POST http://localhost:8000/channels/room \
       -H 'Content-Type: application/json' -d @-

# Read channel
curl http://localhost:8000/channels/room

# Subscribe to live stream (blocks, prints SSE events)
curl -N http://localhost:8000/channels/room/events

# Node health
curl http://localhost:8000/health
# -> {"version":"0.2.0","uptime_s":...,"channels":{"room":{"count":5}},"sse_clients":0,"peers":[]}

# Rate limits
curl http://localhost:8000/limits
```

### Envelope schema v2.0

```json
{
  "schema": "pipernet-envelope-v2.0",
  "from": "alice",
  "sequence": 1,
  "timestamp": "2026-05-29T12:00:00+00:00",
  "channel": "room",
  "body": [["txt", "hello pipernet"]],
  "sig": "<hex-ed25519-signature>",
  "parent": null
}
```

The signature covers the canonical JSON (sorted keys, no whitespace) of the envelope minus the `sig` field.

## Local file layout

```
~/.pipernet/
  <handle>.private.bin     # Ed25519 private key, 0600
  pubkeys.json             # { "alice": "<hex pubkey>", ... }
  channels/
    <channel>.jsonl        # append-only envelope log, one JSON per line
  dots/
    <handle>.dot.png       # identity logogram
```

Override base directory: `export PIPERNET_HOME=/path/to/dir`

## Observe state / health

```bash
# Relay health
curl http://localhost:8000/health
# {
#   "version": "0.2.0",
#   "uptime_s": 123.4,
#   "channels": { "room": { "count": 42 } },
#   "sse_clients": 2,
#   "peers": []
# }

# Check envelope count in a channel
curl -s http://localhost:8000/channels/room | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d))"

# Local channel size (without relay)
wc -l ~/.pipernet/channels/room.jsonl
```

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `400 {"error": "signature does not verify"}` | Sender's pubkey not in relay registry | `POST /pubkeys` with their hex pubkey, or run `pipernet register --handle <name> --pubkey <hex>` on relay host |
| `pipernet serve` fails with ImportError | aiohttp not installed | `pip install aiohttp>=3.9` |
| `pipernet dot create` fails | dot extras not installed or zbar missing | `pip install -e ".[dot]"` and `brew install zbar` (macOS) |
| `exit code 3` from `pipernet verify` | Tampered envelope body or wrong pubkey | Check you're verifying with the correct sender pubkey in `~/.pipernet/pubkeys.json` |
| SSE stream stops receiving | Client disconnected or relay restarted | Reconnect; relay replays nothing on reconnect — pull `/channels/<name>` for history, then subscribe |
| Channel log grows without bound | No pruning by design | Move old JSONL files aside; relay serves from whatever is in the channels dir |
| Rate limit 429 | Pubkey or IP over limit | Wait for window to reset (60 s for envelopes, 3600 s for pubkey registration) |
