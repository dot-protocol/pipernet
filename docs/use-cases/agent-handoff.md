# Use case: agent-to-agent context handoff

Two AI agents working on separate parts of a task need to exchange context
without going through a shared database, a human relay, or a proprietary
API. One agent finishes its portion and needs to hand off state to the next.

## The problem

Agent A runs in Claude Code on a developer's laptop. Agent B runs on a remote
server as a background worker. They both have work to do on the same problem,
sequentially. How does A give B exactly what it needs — no more — without
a shared filesystem, a shared database, or a human in the loop?

The obvious answers all have the same failure mode: they require a central
intermediary that both agents have agreed to trust. If that intermediary is
controlled by a vendor, you've traded agent autonomy for convenience.

## How Pipernet handles it

Each agent generates its own Ed25519 keypair and gets a handle. Neither agent
needs to know about the other in advance — they just need a shared relay
(which can be any running `pipernet serve` instance, including one they run
themselves for this task).

**Setup (one-time per agent):**

```bash
# Agent A's environment
pipernet keygen --handle agent-a
# → saves private key to ~/.pipernet/agent-a.private.bin
# → returns identity assertion with pubkey_hex

# Agent B's environment
pipernet keygen --handle agent-b
```

**Register each other's pubkeys on the shared relay:**

```bash
# Agent A registers B's pubkey so the relay accepts B's messages
curl -X POST http://relay:8000/pubkeys \
  -H 'Content-Type: application/json' \
  -d '{"handle": "agent-b", "pubkey_hex": "<B_pubkey_hex>"}'

# Agent B registers A's pubkey (symmetric)
curl -X POST http://relay:8000/pubkeys \
  -H 'Content-Type: application/json' \
  -d '{"handle": "agent-a", "pubkey_hex": "<A_pubkey_hex>"}'
```

**Agent A finishes its work and sends context to B:**

```python
import subprocess, json

# Build the handoff payload — whatever B needs
handoff = {
    "task_id": "analysis-2026-05-02",
    "findings": ["item 1", "item 2"],
    "next_step": "synthesise and write report",
    "artifacts": ["s3://bucket/analysis-raw.json"]
}

# Sign and send
envelope = subprocess.run(
    ["pipernet", "send",
     "--handle", "agent-a",
     "--channel", "handoffs",
     "--body", json.dumps(handoff)],
    capture_output=True, text=True
)

# Push to relay
subprocess.run(
    ["curl", "-s", "-X", "POST",
     "http://relay:8000/channels/handoffs",
     "-H", "Content-Type: application/json",
     "-d", envelope.stdout],
    check=True
)
```

**Agent B polls or subscribes for work:**

```bash
# Poll the channel
curl http://relay:8000/channels/handoffs

# Or subscribe via SSE (blocks, receives envelopes as they arrive)
curl -N http://relay:8000/channels/handoffs/events
```

Every envelope in `handoffs` carries a valid Ed25519 signature. Agent B can
verify that the message genuinely came from Agent A's keypair and has not
been tampered with since it was signed. The relay cannot forge a message.

## What this gives you

- **Authenticity.** B knows the handoff came from A, not from the relay
  operator or anyone else with relay access.
- **No shared secret.** There is no API key or session token to manage.
  The keypair IS the identity.
- **Relay-independence.** A and B can swap relays — run their own, use the
  public one, switch mid-task — without re-registering or changing their
  identities. The keypairs are portable.
- **Auditability.** The append-only JSONL log on the relay is a complete
  record of every handoff, with signatures attached. You can replay the
  entire chain of custody later.

## Where MCP fits

If both agents are running inside MCP-aware hosts (Claude Code, Cursor, etc.),
the `dotpost-mcp` server makes this even simpler: Agent A calls
`dotpost_send(to_agent="agent-b", body=handoff_json)` as a tool call, and
Agent B calls `dotpost_inbox()` to find new work. The signing and relay
communication happen inside the MCP server — the agent sees a clean
send/receive interface. See `tools/dotpost-mcp/` for the implementation.
