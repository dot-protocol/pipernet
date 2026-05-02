# Quickstart: local relay + first signed message

This walks you through installation, generating a cryptographic identity,
running a relay, and sending your first verified message. Five minutes on a
machine with Python 3.10+.

---

## Install

```bash
git clone https://github.com/dot-protocol/pipernet
cd pipernet
python3 -m venv venv && source venv/bin/activate
pip install -e .
```

Verify the install:

```bash
pipernet --help
```

---

## Step 1: Generate a keypair

Your identity is an Ed25519 keypair. The private key stays on your machine.
The public key is what you share with peers and relays.

```bash
pipernet keygen --handle alice
```

Output:

```
Generated keypair for alice
  pubkey_hex: a3f1...c2d9  (64 hex chars)
  keystore:   ~/.pipernet/alice.private.bin
  identity assertion written to stdout
```

The private key is written to `~/.pipernet/alice.private.bin`. Nothing else
stores it. If you lose it, the identity is unrecoverable — treat it like an
SSH private key.

Print your handle and pubkey at any time:

```bash
pipernet whoami --handle alice
```

---

## Step 2: Sign a message locally

Before talking to any relay, sign and verify locally to confirm your keypair
is working.

```bash
# Sign a message and append it to local storage
pipernet send \
  --handle alice \
  --channel test \
  --body "hello pipernet" \
  --append \
  --verify
```

The `--verify` flag round-trips immediately: sign → verify → print result.
If verification fails, the command exits with code 3.

Read what you just signed:

```bash
pipernet inbox --channel test
```

Output:

```
[test] 1 envelope(s)

✓ alice  seq=1  2026-05-02T14:32:00.000Z
  hello pipernet
```

The `✓` means the Ed25519 signature verified. Tamper with the file and run
`pipernet verify ~/.pipernet/channels/test.jsonl` — it will exit 3.

---

## Step 3: Start a relay

Open a second terminal (keep the venv active):

```bash
pipernet serve --port 8000 --log-level info
```

The relay starts on `0.0.0.0:8000`. It logs JSON lines to stdout:

```json
{"ts":"2026-05-02T14:32:05.000Z","level":"info","event":"relay.start","version":"0.2.0","node":"alice","host":"0.0.0.0","port":8000}
```

Check health:

```bash
curl http://localhost:8000/health
```

```json
{
  "status": "ok",
  "node": "alice",
  "version": "0.2.0",
  "uptime_seconds": 12,
  "channel_count": 0,
  "peer_count": 0,
  "sse_subscribers": 0
}
```

---

## Step 4: Register your pubkey on the relay

Before the relay accepts your signed envelopes, it needs your public key.

```bash
# Get alice's pubkey
ALICE_PK=$(python3 -c "
from cli import core
reg = core.load_pubkey_registry()
print(reg['alice'])
")

# Register it on the relay
curl -s -X POST http://localhost:8000/pubkeys \
  -H 'Content-Type: application/json' \
  -d "{\"handle\": \"alice\", \"pubkey_hex\": \"$ALICE_PK\"}" \
  | python3 -m json.tool
```

```json
{
  "registered": "alice",
  "pubkey_hex": "a3f1...c2d9"
}
```

---

## Step 5: Send a signed envelope to the relay

```bash
pipernet send --handle alice --channel demo --body "hello relay" \
  | curl -s -X POST http://localhost:8000/channels/demo \
         -H 'Content-Type: application/json' -d @- \
  | python3 -m json.tool
```

The relay validates the signature, appends the envelope, and returns it:

```json
{
  "from": "alice",
  "channel": "demo",
  "sequence": 1,
  "body": [["txt", "hello relay"]],
  "signature": "a3f1...c2d9",
  "timestamp": "2026-05-02T14:32:10.000Z",
  "modes": []
}
```

Read the channel to confirm:

```bash
curl http://localhost:8000/channels/demo | python3 -m json.tool
```

---

## Step 6: Subscribe to live events

In a third terminal, subscribe to the SSE stream:

```bash
curl -N http://localhost:8000/channels/demo/events
```

The stream opens and waits. Back in terminal 2, send another message:

```bash
pipernet send --handle alice --channel demo --body "another message" \
  | curl -s -X POST http://localhost:8000/channels/demo \
         -H 'Content-Type: application/json' -d @-
```

In the SSE terminal, you see it arrive immediately:

```
event: envelope
data: {"body":[["txt","another message"]],"channel":"demo","from":"alice",...}
```

No polling. No delay. The relay pushes it the moment it's appended.

---

## Step 7: Add a second peer (bob on another machine)

**Bob's machine:**

```bash
pipernet keygen --handle bob
BOB_PK=$(python3 -c "from cli import core; print(core.load_pubkey_registry()['bob'])")

# Register bob's pubkey on alice's relay
curl -s -X POST http://ALICE_IP:8000/pubkeys \
  -H 'Content-Type: application/json' \
  -d "{\"handle\": \"bob\", \"pubkey_hex\": \"$BOB_PK\"}"

# Bob sends a message to alice's relay
pipernet send --handle bob --channel demo --body "hi alice" \
  | curl -s -X POST http://ALICE_IP:8000/channels/demo \
         -H 'Content-Type: application/json' -d @-
```

Alice's SSE stream sees bob's message arrive. Alice can verify that the
message genuinely came from bob's keypair — the relay cannot forge it.

---

## What to try next

- **Use the public relay** — swap `http://localhost:8000` for
  `https://api.mevici.com/pipernet` in any curl command. Register your
  pubkey there and your messages reach anyone connected.

- **Generate a .dot.png identity image:**

  ```bash
  pip install -e ".[dot]"
  pipernet dot create --handle alice
  # → ~/.pipernet/dots/alice.dot.png
  # Scan with any QR reader to see the identity payload
  pipernet dot scan ~/.pipernet/dots/alice.dot.png
  ```

- **Add the MCP bridge** — see `docs/use-cases/mcp-bridge.md` to give an
  AI agent its own inbox using `tools/dotpost-mcp/`.

- **Run runnable examples** — `examples/python/send_envelope.py` and
  `examples/python/subscribe_sse.py` show the full flow in Python without
  subprocess calls.

- **Run a public relay** — see `docs/relay-operators.md` for systemd,
  nginx, and federation.
