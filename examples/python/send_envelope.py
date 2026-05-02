"""
examples/python/send_envelope.py
---------------------------------
Minimum viable signed-envelope send using the pipernet CLI.

Prerequisites:
    pip install -e /path/to/pipernet

    # Generate a keypair (once)
    pipernet keygen --handle alice

    # Register alice's pubkey on the relay (one-time per relay)
    ALICE_PK=$(python3 -c "
    from cli import core
    reg = core.load_pubkey_registry()
    print(reg.get('alice', ''))
    ")
    curl -X POST http://localhost:8000/pubkeys \\
         -H 'Content-Type: application/json' \\
         -d "{\"handle\": \"alice\", \"pubkey_hex\": \"$ALICE_PK\"}"

Run:
    # Start a relay in another terminal:  pipernet serve --port 8000
    python3 examples/python/send_envelope.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

RELAY_URL = "http://localhost:8000"  # change to https://api.mevici.com/pipernet for the public relay
HANDLE = "alice"
CHANNEL = "demo"
MESSAGE = "hello from the send_envelope.py example"


# ---------------------------------------------------------------------------
# Step 1: Build a signed envelope using the CLI
# ---------------------------------------------------------------------------

def build_envelope(handle: str, channel: str, body: str) -> dict:
    """
    Call `pipernet send` to sign an envelope and return it as a dict.

    `pipernet send` prints a JSON envelope to stdout.
    We capture it and parse it — no local key material touches this script.
    """
    result = subprocess.run(
        [
            "pipernet", "send",
            "--handle", handle,
            "--channel", channel,
            "--body", body,
            # --append also writes locally; omit if you only want to send to relay
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout.strip())


# ---------------------------------------------------------------------------
# Step 2: POST the envelope to the relay
# ---------------------------------------------------------------------------

def post_envelope(relay_url: str, channel: str, envelope: dict) -> dict:
    """
    POST a signed envelope to the relay and return the response.

    The relay validates the Ed25519 signature against its pubkey registry.
    If the signature is invalid, it returns 400.
    On success it returns the envelope back (useful for getting the server-assigned
    timestamp or any fields the relay may normalise).
    """
    url = f"{relay_url.rstrip('/')}/channels/{channel}"
    payload = json.dumps(envelope).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"Relay rejected envelope: HTTP {e.code} — {body}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Could not reach relay at {url}: {e.reason}", file=sys.stderr)
        print("Is `pipernet serve --port 8000` running?", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Step 3: Read back the channel to confirm delivery
# ---------------------------------------------------------------------------

def read_channel(relay_url: str, channel: str) -> list[dict]:
    """Fetch all envelopes in a channel from the relay."""
    url = f"{relay_url.rstrip('/')}/channels/{channel}"
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read())


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"Building signed envelope from handle '{HANDLE}'...")
    envelope = build_envelope(HANDLE, CHANNEL, MESSAGE)

    # The envelope contains: from, channel, sequence, body, signature, timestamp, modes
    print(f"  from:      {envelope['from']}")
    print(f"  channel:   {envelope['channel']}")
    print(f"  sequence:  {envelope['sequence']}")
    print(f"  signature: {envelope['signature'][:16]}...")

    print(f"\nPosting to relay at {RELAY_URL}/channels/{CHANNEL}...")
    response = post_envelope(RELAY_URL, CHANNEL, envelope)
    print(f"  relay accepted: {response.get('from')} seq={response.get('sequence')}")

    print(f"\nReading back channel '{CHANNEL}'...")
    envelopes = read_channel(RELAY_URL, CHANNEL)
    print(f"  {len(envelopes)} envelope(s) in channel")
    for e in envelopes[-3:]:  # show last 3
        body_text = ""
        if isinstance(e.get("body"), list):
            for part in e["body"]:
                if isinstance(part, list) and part[0] == "txt":
                    body_text = part[1]
        print(f"  [{e.get('from')}] {body_text}")

    print("\nDone.")


if __name__ == "__main__":
    main()
