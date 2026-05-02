# Use case: running a private relay for your team

Not every relay should be public. A small team, a company, a research group,
or a family might want a relay that only they can use — one they control,
that holds no data on any vendor's servers, and that they can shut down,
migrate, or audit at any time.

This use case describes setting up a private relay for a group of 2–20 people.

---

## What "private" means here

A Pipernet relay has no concept of user accounts or access tokens. Privacy
comes from controlling whose public keys the relay accepts. If the relay
only has your team's pubkeys registered, it will reject envelopes from
anyone else — signatures from unregistered handles return `400`.

There is no "invite link," no OAuth callback, no admin panel. The trust
surface is exactly: whose pubkeys are in the registry?

This is intentional. An authentication system that can be bypassed via
a password reset, a social engineering call to customer support, or a
vendor compliance request is not suitable for high-trust communication.
Cryptographic keypairs are.

---

## Setup

**1. Start the relay on a machine your team can reach**

This can be a VPS, a machine on your LAN, a Tailscale node, or anything
with a stable address. See `docs/relay-operators.md` for a full production
guide. The minimal version:

```bash
pip install pipernet
pipernet keygen --handle team-relay
pipernet serve --host 0.0.0.0 --port 8000
```

If the relay is on a VPS with a domain name, put nginx in front for TLS
(see `docs/relay-operators.md` → nginx section). TLS is strongly recommended
for any relay reachable from the internet.

**2. Each team member generates a keypair**

```bash
# Each person runs this on their own machine
pipernet keygen --handle <their-name>
pipernet whoami --handle <their-name>
# → prints pubkey_hex — share this with the relay operator
```

**3. Relay operator registers each member's pubkey**

The relay operator collects each person's `pubkey_hex` (via any trusted channel
— Signal, email, in person, a .dot.png scan) and registers them:

```bash
# For each team member
curl -s -X POST https://team-relay.example.com/pubkeys \
  -H 'Content-Type: application/json' \
  -d '{"handle": "<name>", "pubkey_hex": "<64 hex chars>"}'
```

Optionally include the `identity_assertion` field from `pipernet keygen`
output — this lets the relay verify that the submitter controls the
corresponding private key before registering.

**4. Verify the registry**

```bash
curl https://team-relay.example.com/pubkeys | python3 -m json.tool
```

You should see all team member handles listed.

---

## Day-to-day use

```bash
# Send a message to the shared channel
pipernet send --handle alice --channel general --body "standup in 10 minutes" \
  | curl -s -X POST https://team-relay.example.com/channels/general \
         -H 'Content-Type: application/json' -d @-

# Read the channel
curl https://team-relay.example.com/channels/general | python3 -c "
import sys, json
for e in json.load(sys.stdin):
    body = next((p[1] for p in e.get('body', []) if p[0]=='txt'), '')
    print(f'[{e[\"from\"]}] {body}')
"

# Subscribe to live events
curl -N https://team-relay.example.com/channels/general/events
```

---

## Multiple channels

Channels are created on first write — there is no "create channel" API call.

```bash
# Create separate channels by just using different names
pipernet send --handle alice --channel engineering --body "PR #42 merged"  | curl ...
pipernet send --handle alice --channel ops         --body "deploy queued"  | curl ...
pipernet send --handle alice --channel general     --body "weekly sync 3pm" | curl ...
```

Every team member can read any channel they know the name of. If you want
to restrict access to specific channels, you need a custom relay that
enforces per-channel access control — that capability is not in the reference
relay and would need to be built on top.

---

## Removing access

Removing access currently requires removing the pubkey from the registry.
The reference relay does not have a `DELETE /pubkeys/<handle>` endpoint in
v0 — add one to `cli/server.py`, or restart the relay with a pruned
`~/.pipernet/pubkeys.json`. This is a known gap; a `DELETE` endpoint is
on the roadmap.

Note: removing a pubkey only stops the relay from accepting *new* envelopes
from that handle. Historical envelopes already stored in the JSONL channel
logs are not affected (they are append-only by design). If you need to
revoke historical access, you need to either move to a new relay instance
or accept that the history is part of the public record.

---

## Backup and portability

The entire relay state lives in `~/.pipernet/` (or the directory set by
`PIPERNET_HOME`):

```
~/.pipernet/
├── <handle>.private.bin    keypair files
├── pubkeys.json            registered peers
└── channels/
    ├── general.jsonl       one file per channel
    └── engineering.jsonl
```

Back this directory up. To move the relay to a new machine:

```bash
rsync -av ~/.pipernet/ user@new-machine:~/.pipernet/
```

The new machine can serve the same channel history immediately. The relay
handle and all registered peer pubkeys are preserved.

---

## Why not just use Signal or Slack?

- Signal groups require phone numbers; Slack requires accounts.
- Both are centralised: if their servers are unreachable, communication stops.
- Neither gives you the channel history as a local file you control.
- Neither lets an AI agent participate with the same trust model as a human.

Pipernet's private relay trades convenience (no app to install, no signup UX)
for control (your data, your keys, your infrastructure). That trade is not
for everyone. For teams that want it, the relay is one `pip install` and one
command to start.
