"""
examples/python/subscribe_sse.py
----------------------------------
Subscribe to a channel via Server-Sent Events and print each new envelope
as it arrives. Handles reconnect automatically.

Prerequisites:
    pip install -e /path/to/pipernet

    # Start a relay in another terminal:
    pipernet serve --port 8000

Run:
    python3 examples/python/subscribe_sse.py

    # In another terminal, send an envelope:
    pipernet keygen --handle alice
    pipernet send --handle alice --channel demo --body "hello SSE" | \\
      curl -s -X POST http://localhost:8000/channels/demo \\
           -H 'Content-Type: application/json' -d @-

    # You will see it appear in this script's output immediately.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

RELAY_URL = "http://localhost:8000"   # change for remote relay
CHANNEL = "demo"
RECONNECT_DELAY_SECONDS = 5


# ---------------------------------------------------------------------------
# SSE parser (no external deps — works with any text/event-stream response)
# ---------------------------------------------------------------------------

def parse_sse_line(line: str) -> tuple[str, str] | None:
    """
    Parse a single SSE line and return (event_type, data) or None.

    SSE format:
        event: <name>\\n
        data: <json>\\n
        \\n   (blank line = end of event)
    """
    if line.startswith("event:"):
        return ("event", line[6:].strip())
    if line.startswith("data:"):
        return ("data", line[5:].strip())
    return None


def stream_channel(relay_url: str, channel: str):
    """
    Generator that yields parsed envelope dicts from an SSE channel stream.
    Handles connection-level errors and heartbeats silently.
    """
    url = f"{relay_url.rstrip('/')}/channels/{channel}/events"

    req = urllib.request.Request(
        url,
        headers={"Accept": "text/event-stream", "Cache-Control": "no-cache"},
    )

    try:
        with urllib.request.urlopen(req) as resp:
            if resp.getcode() != 200:
                raise urllib.error.HTTPError(url, resp.getcode(), "unexpected status", {}, None)

            current_event_type = "message"
            current_data: list[str] = []

            for raw_line in resp:
                line = raw_line.decode("utf-8").rstrip("\r\n")

                if not line:
                    # Blank line = dispatch event
                    if current_data:
                        data_str = "\n".join(current_data)
                        event_type = current_event_type
                        current_event_type = "message"
                        current_data = []

                        if event_type in ("envelope", "message") and data_str not in ("{}", ""):
                            try:
                                yield json.loads(data_str)
                            except json.JSONDecodeError:
                                pass  # heartbeats and connected events are not JSON envelopes
                    continue

                parsed = parse_sse_line(line)
                if parsed:
                    key, val = parsed
                    if key == "event":
                        current_event_type = val
                    elif key == "data":
                        current_data.append(val)

    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} from relay: {e.reason}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Could not reach relay at {url}: {e.reason}") from e


# ---------------------------------------------------------------------------
# Pretty-print helper
# ---------------------------------------------------------------------------

def format_envelope(env: dict) -> str:
    """Format an envelope for human-readable console output."""
    sender = env.get("from", "unknown")
    channel = env.get("channel", "?")
    seq = env.get("sequence", "?")
    sig_prefix = (env.get("signature") or "")[:12]

    # Extract text body from [[\"txt\", \"...\"], ...] format
    body_text = ""
    body = env.get("body", [])
    if isinstance(body, list):
        for part in body:
            if isinstance(part, list) and len(part) >= 2 and part[0] == "txt":
                body_text = part[1]
                break
    if not body_text:
        body_text = json.dumps(body)[:80]

    return f"[{channel}] {sender} (seq={seq}, sig={sig_prefix}...): {body_text}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    url = f"{RELAY_URL}/channels/{CHANNEL}/events"
    print(f"Subscribing to {url}")
    print(f"Waiting for new envelopes on channel '{CHANNEL}'...")
    print("(Press Ctrl+C to stop)\n")

    while True:
        try:
            for envelope in stream_channel(RELAY_URL, CHANNEL):
                print(format_envelope(envelope), flush=True)

        except RuntimeError as e:
            print(f"Connection error: {e}", file=sys.stderr)
            print(f"Reconnecting in {RECONNECT_DELAY_SECONDS}s...", file=sys.stderr)
            time.sleep(RECONNECT_DELAY_SECONDS)

        except KeyboardInterrupt:
            print("\nStopped.")
            sys.exit(0)


if __name__ == "__main__":
    main()
