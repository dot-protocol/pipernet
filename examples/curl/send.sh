#!/usr/bin/env bash
# examples/curl/send.sh
#
# Pure curl walkthrough: send a signed envelope to a Pipernet relay.
#
# Prerequisites:
#   pip install -e /path/to/pipernet
#   pipernet keygen --handle alice        # run once
#
# Usage:
#   # Start a relay first:  pipernet serve --port 8000
#   bash examples/curl/send.sh
#
#   # Point at a different relay:
#   RELAY=https://api.mevici.com/pipernet bash examples/curl/send.sh

set -euo pipefail

RELAY="${RELAY:-http://localhost:8000}"
HANDLE="${HANDLE:-alice}"
CHANNEL="${CHANNEL:-demo}"
BODY="${BODY:-hello from send.sh}"

echo "=== Pipernet curl example ==="
echo "Relay:   $RELAY"
echo "Handle:  $HANDLE"
echo "Channel: $CHANNEL"
echo ""

# ---------------------------------------------------------------------------
# 1. Register alice's pubkey on the relay (safe to run more than once)
# ---------------------------------------------------------------------------

echo "--- Step 1: Register pubkey ---"

ALICE_PK=$(python3 -c "
import sys
sys.path.insert(0, '.')
from cli import core
reg = core.load_pubkey_registry()
pk = reg.get('$HANDLE', '')
if not pk:
    print('ERROR: handle $HANDLE not found in pubkey registry', file=sys.stderr)
    sys.exit(1)
print(pk)
")

curl -s -X POST "$RELAY/pubkeys" \
  -H 'Content-Type: application/json' \
  -d "{\"handle\": \"$HANDLE\", \"pubkey_hex\": \"$ALICE_PK\"}" \
  | python3 -m json.tool

echo ""

# ---------------------------------------------------------------------------
# 2. Sign an envelope and send it to the relay
# ---------------------------------------------------------------------------

echo "--- Step 2: Sign + send ---"

# `pipernet send` prints the signed envelope JSON to stdout.
# We pipe it directly to curl.
pipernet send --handle "$HANDLE" --channel "$CHANNEL" --body "$BODY" \
  | curl -s -X POST "$RELAY/channels/$CHANNEL" \
         -H 'Content-Type: application/json' \
         -d @- \
  | python3 -m json.tool

echo ""

# ---------------------------------------------------------------------------
# 3. Read the channel to confirm delivery
# ---------------------------------------------------------------------------

echo "--- Step 3: Read channel ---"

curl -s "$RELAY/channels/$CHANNEL" | python3 -c "
import sys, json
envelopes = json.load(sys.stdin)
print(f'  {len(envelopes)} envelope(s) in channel')
for e in envelopes[-3:]:
    body_text = ''
    for part in (e.get('body') or []):
        if isinstance(part, list) and part[0] == 'txt':
            body_text = part[1]
    print(f'  [{e[\"from\"]}] {body_text}')
"

echo ""

# ---------------------------------------------------------------------------
# 4. Subscribe to live events (SSE) — Ctrl+C to stop
# ---------------------------------------------------------------------------

echo "--- Step 4: Subscribe to live events (Ctrl+C to exit) ---"
echo "Send another message in a second terminal to see it arrive instantly:"
echo "  pipernet send --handle $HANDLE --channel $CHANNEL --body 'hello again' \\"
echo "    | curl -s -X POST $RELAY/channels/$CHANNEL -H 'Content-Type: application/json' -d @-"
echo ""

curl -N "$RELAY/channels/$CHANNEL/events"
