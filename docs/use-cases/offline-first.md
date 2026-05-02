# Use case: offline-first and degraded-network messaging

A Pipernet envelope is designed to survive any transport medium that can
carry bytes — including SMS, LoRa radio, QR codes, and paper printouts.
This is not theoretical. It is a hard design constraint that every layer
of the protocol is built around.

The reference for this is the Nokia 3315: if an envelope cannot be sent
from a feature phone over SMS to another node and have the signature
verified on arrival, the protocol has failed its most important test.

## The eight choke points

`spec/11-packet.md` (the R65.53 analysis) enumerates eight places where
existing communication systems fail in degraded conditions:

1. Requires internet connectivity to function at all
2. Requires a central server to be reachable
3. Requires a mobile app to be installed (gated distribution)
4. Requires the user to have an account
5. Encrypts transport but not content — relay operator reads everything
6. Does not preserve message history when the relay is unavailable
7. Identity tied to a phone number or email address (not portable)
8. Distributing the client requires App Store approval

Pipernet avoids all eight, structurally:

| Choke point | How Pipernet avoids it |
|-------------|------------------------|
| Requires internet | SMS Tier A fallback — envelope is a base64 string |
| Requires central server | Federated relays, or no relay at all (direct exchange) |
| Requires app install | CLI is a `pip install`; relay runs in any Python env |
| Requires account | Ed25519 keypair, no sign-up, no email |
| Transport-only encryption | Tier 1 E2E (in design); signature chain verifiable offline |
| History lost offline | Append-only JSONL survives relay downtime |
| Identity tied to phone/email | Keypair identity, phone number optional |
| App Store gated | Python package, open-source, no approval required |

## How it works without the internet

An envelope is a JSON object containing a `from` handle, a `channel` name,
a `sequence` number, a `body` array, a `timestamp`, and an Ed25519 `signature`
over the canonical form of the rest.

That JSON can be transmitted over any medium that carries text:

**SMS (Tier A):** Base64-encode the envelope JSON. Send as one or more SMS
messages. The recipient decodes and verifies. The signature check is identical
to HTTP mode.

```bash
# Encode an envelope for SMS
pipernet send --handle alice --channel field --body "coordinates: 37.8 -122.4" \
  | python3 -c "import sys,base64,json; print(base64.b64encode(sys.stdin.read().encode()).decode())"
```

**LoRa / Reticulum (Tier A mesh):** The protocol is designed to fit within
the Meshtastic payload limit (237 bytes for most configurations). A minimal
envelope — short handle, short body, 64-byte signature, timestamp — fits
in that window with room for routing overhead. See `spec/11-packet.md`
section on DOT radio wire format for the MessagePack encoding.

**QR code (Tier A):** The `.dot.png` identity image is also a QR code that
any phone camera can read. For message exchange in extremely degraded
conditions (no connectivity at all), an envelope can be QR-encoded and
physically handed over or displayed on screen for scanning.

**Paper:** An envelope signature is 64 bytes. In hex, that is 128 characters.
A fully-printed paper envelope can be verified by any device that has the
sender's public key stored locally — offline, no connectivity required.

## Practical scenario: field coordination without internet

A team operating in an area with intermittent connectivity (post-disaster
relief, remote research station, rural agricultural operation) needs
verifiable message exchange.

Setup (done once, before the field operation, with internet):

```bash
# Each team member generates a keypair
pipernet keygen --handle alice
pipernet keygen --handle bob
pipernet keygen --handle relay-node

# Team members exchange pubkeys (in person, or via any trusted channel)
pipernet whoami --handle alice  # → shows pubkey_hex
# alice sends her pubkey to bob, bob registers it:
pipernet register --handle alice --pubkey <alice_pubkey_hex>
```

In the field, with no internet:

```bash
# alice signs a message locally
pipernet send --handle alice --channel field --body "status: site-3 clear, ETA 14:00" --append

# bob subscribes to alice's local channel (LAN, mesh, or offline sync)
# When connectivity returns, the signed messages sync to any relay

# Verification is always local
pipernet verify some-envelope.json
# → exit 0 if valid, exit 3 if tampered
```

The append-only JSONL log accumulates messages offline. When any path to a
relay opens — satellite, LoRa, restored broadband — the local log can be
pushed to the relay in a single gossip batch:

```bash
# Push local channel history to a relay as a gossip batch
cat ~/.pipernet/channels/field.jsonl | python3 -c "
import sys, json
envelopes = [json.loads(line) for line in sys.stdin if line.strip()]
print(json.dumps(envelopes))
" | curl -X POST http://relay:8000/gossip \
         -H 'Content-Type: application/json' -d @-
```

The relay deduplicates by signature — pushing the same envelope twice is safe.

## Current implementation status

The CLI (`pipernet send`, `pipernet verify`, `pipernet inbox`) implements Tier 0
offline operation fully. The LoRa/Meshtastic wire format is specified in
`spec/11-packet.md` but the radio driver is not yet implemented — that is the
next Tier A milestone. SMS encoding is specified and feasible with any SMS
gateway that accepts ASCII; a reference wrapper is in the roadmap.
