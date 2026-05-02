# 01 — Envelope wire format

> **Status:** Active. Describes the schema v2.0 envelope format as implemented
> in `cli/core.py` (`build_envelope`, `verify_envelope`) and `cli/server.py`
> (`handle_post_channel`). This is the ground truth for interoperability.

---

## The envelope

An envelope is a signed JSON object. It is the atomic unit of the Pipernet
protocol — the smallest piece of data that carries meaning, authorship,
and verifiability.

### Required fields

| Field | Type | Description |
|-------|------|-------------|
| `from` | string | Sender handle (e.g. `"alice"`). Must match a registered pubkey. |
| `sequence` | integer | Monotonically increasing per sender per channel. Used for Lamport ordering and deduplication. |
| `parent` | `[seq, from]` or `null` | The envelope this replies to, or `null` for a root message. |
| `modes` | array of string | Content type tags. `["txt"]` for text-only messages. Empty array `[]` for the relay-normalised form. |
| `body` | array of `[mode, payload]` pairs | The message content. For text: `[["txt", "hello world"]]`. See Body encoding below. |
| `timestamp` | string | ISO 8601 UTC timestamp from the sender's clock. |
| `signature` | string | Base64-encoded Ed25519 signature over the canonical form. See Signing below. |

### Example

```json
{
  "from":      "alice",
  "sequence":  1,
  "parent":    null,
  "modes":     ["txt"],
  "body":      [["txt", "hello pipernet"]],
  "timestamp": "2026-05-02T14:32:00.000000+00:00",
  "signature": "base64encodedEd25519sig=="
}
```

---

## Body encoding

The `body` field is a list of `[mode, payload]` pairs. This structure supports
multiple content types in a single envelope (e.g., a text message with an
image attachment).

| Mode | Payload type | Description |
|------|-------------|-------------|
| `txt` | string | Plain text content |
| `img` | string | Base64-encoded image data or URI (future) |
| `bin` | string | Base64-encoded binary data (future) |

Current v0 implementations only produce and consume `txt` mode. Other modes
are reserved for future use. A receiver that encounters an unknown mode in
the body should skip that entry and process remaining entries it understands.

---

## Signing

The signature covers all fields **except** `signature` itself.

### Canonical form

Before signing, the envelope is serialised to **canonical JSON**:
- All keys sorted alphabetically
- No whitespace (no spaces, no newlines)
- UTF-8 encoded

Python reference (`cli/core.py`):

```python
def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
```

JavaScript reference (`examples/javascript/send_envelope.js`):

```javascript
function canonical(obj) {
  return JSON.stringify(obj, Object.keys(obj).sort());
}
```

### Sign

```python
# Python (cli/core.py — build_envelope)
body = {k: v for k, v in envelope.items() if k != "signature"}
signature = base64.b64encode(private_key.sign(canonical(body))).decode("ascii")
```

The private key is Ed25519 (32-byte raw seed, stored in `~/.pipernet/<handle>.private.bin`).
Signing uses the OS CSPRNG via `cryptography.hazmat.primitives.asymmetric.ed25519`.

### Verify

```python
# Python (cli/core.py — verify_envelope)
pk = Ed25519PublicKey.from_public_bytes(bytes.fromhex(pubkey_hex))
body = {k: v for k, v in envelope.items() if k != "signature"}
pk.verify(base64.b64decode(sig_b64), canonical(body))
```

Verification fails (raises an exception) if:
- The signature does not match the body
- The public key does not correspond to the private key that signed it
- The body has been modified after signing

---

## Open-mode envelopes

Channels in the relay's open-channel allow-list (configured via
`PIPERNET_OPEN_CHANNELS`) skip Ed25519 verification. These envelopes are
stored with:
- `"signature": null`
- `"modes": ["open"]`
- A `meta` field containing the original payload keys

Open-mode is a convenience for v0 demos (e.g., holder gated chat where the
auth is a wallet signature). It should not be used in production channels
where message authenticity matters.

---

## Relay normalisation

When the relay accepts an open-mode envelope, it normalises the payload
into the standard schema (`cli/server.py — _normalise_open_payload`):

- `from` — extracted from `handle`, `from`, or `author` fields; defaults to `anon`
- `body` — extracted from `content`, `body`, or `text`; converted to `[["txt", text]]`
- `timestamp` — extracted from `timestamp`, `createdAt`, or `ts`; defaults to now
- `sequence` — extracted from `sequence` or set to `int(time.time() * 1000)`
- Unknown fields are preserved in `meta.original_keys`

---

## Channel storage format

Channels are stored as JSONL (one envelope per line) at
`~/.pipernet/channels/<channel-name>.jsonl`. Each line is the canonical JSON
form of one envelope.

```
{"body":[["txt","hello"]],"from":"alice","modes":["txt"],"parent":null,"sequence":1,"signature":"...","timestamp":"2026-05-02T14:32:00Z"}
{"body":[["txt","hi alice"]],"from":"bob","modes":["txt"],"parent":[1,"alice"],"sequence":1,"signature":"...","timestamp":"2026-05-02T14:32:05Z"}
```

Files are append-only. There is no compaction or deletion. The append-only
property is structural — it is how the relay can safely restart and resume,
and how gossip deduplication by signature works.

---

## Sequence numbers

Sequence numbers are per-sender per-channel, monotonically increasing from 1.
They are Lamport-style logical clocks, not wall-clock timestamps.

A sender computes the next sequence by reading the channel log and finding
the highest sequence number from their own `from` handle:

```python
def next_sequence(handle: str, channel: str) -> int:
    seen = read_channel(channel)
    own = [e.get("sequence", 0) for e in seen if e.get("from") == handle]
    return (max(own) + 1) if own else 1
```

If two nodes produce envelopes with the same (handle, sequence) pair,
the relay accepts both — deduplication is by signature, not by sequence.
Duplicate sequences indicate a fork in the sender's history; the receiver
should handle this by showing both envelopes (append-only semantics).

---

## What this spec does not cover

- **Thread structure** — derived from the `parent` chain; not stored separately.
  See `spec/04-channel-room.md` for the `room` channel threading model.
- **Lifecycle states** — queued, delivered, revoked, etc. See `spec/02-lifecycle.md`.
- **Encryption** — Tier 1 E2E encryption wraps the `body` field.
  See `spec/05-identity.md`.
- **Binary wire format** — the JSON envelope is the canonical Tier B form.
  The MessagePack form for Tier A (SMS/LoRa) is in `spec/11-packet.md`.

