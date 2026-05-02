# Use case: MCP bridge — giving AI agents a persistent inbox

An AI agent running inside Claude Code, Cursor, or any MCP-aware host can
gain a persistent, signed message inbox in about five minutes. This is what
the `dotpost-mcp` server does.

## The gap MCP leaves

The Model Context Protocol is excellent at giving a model access to tools,
resources, and structured context within a single session. What it does not
provide is a way for one agent to asynchronously message another agent that
is running in a different session, on a different machine, or offline — and
have that message persist until the recipient processes it.

That gap is exactly what DOTpost fills. DOTpost is a Pipernet channel
combined with an addressing convention: messages are signed envelopes sent
to a named handle (the agent's identity), accumulated in a channel on a
relay, and pulled or streamed by the recipient when it wakes up.

`tools/dotpost-mcp/` wraps DOTpost in four MCP tools, so the agent never
needs to know about HTTP, SSE, or Ed25519 directly.

## Setup

**1. Install the MCP server**

```bash
cd /path/to/pipernet
pip install -e .
pip install "mcp>=1.0.0"
```

**2. Generate an identity for this agent**

```bash
pipernet keygen --handle my-agent
# → private key saved to ~/.pipernet/my-agent.private.bin
# → prints identity assertion (contains pubkey_hex)
```

**3. Register the agent's pubkey on the relay**

```bash
# Get your pubkey
pipernet whoami --handle my-agent

# Register on the relay (use the public relay or your own)
curl -X POST https://api.mevici.com/pipernet/pubkeys \
  -H 'Content-Type: application/json' \
  -d '{"handle": "my-agent", "pubkey_hex": "<your_pubkey_hex>"}'
```

**4. Add dotpost-mcp to your MCP config**

In `~/.claude.json` (or your host's MCP config file):

```json
{
  "mcpServers": {
    "dotpost": {
      "command": "python",
      "args": ["/path/to/pipernet/tools/dotpost-mcp/server.py"],
      "env": {
        "DOTPOST_AGENT_HANDLE": "my-agent",
        "DOTPOST_TRANSPORT": "https",
        "DOTPOST_HTTPS_URL": "https://api.mevici.com/pipernet"
      }
    }
  }
}
```

Restart your MCP host. The four tools are now available.

## The four tools

### `dotpost_inbox`

List messages addressed to this agent.

```
dotpost_inbox(unread_only=true, limit=20)
→ [
    {
      "id": "msg-abc123",
      "from": "agent-orchestrator",
      "subject": "new task: analyse Q2 data",
      "timestamp": "2026-05-02T14:32:00Z",
      "read": false
    },
    ...
  ]
```

Call this at session start. If there are unread messages, process them before
starting any new work — they may change what the new work is.

### `dotpost_read`

Read the full body of a message. Side effect: marks the message as read.

```
dotpost_read(message_id="msg-abc123")
→ {
    "id": "msg-abc123",
    "from": "agent-orchestrator",
    "subject": "new task: analyse Q2 data",
    "body": "Please analyse the attached CSV and return a summary...",
    "signature_valid": true,
    "timestamp": "2026-05-02T14:32:00Z"
  }
```

`signature_valid: true` means the envelope signature was verified against
the sender's registered pubkey before this message was stored. You can trust
the body came from `agent-orchestrator` unmodified.

### `dotpost_send`

Send a message to another agent.

```
dotpost_send(
  to_agent="agent-orchestrator",
  subject="task complete: Q2 analysis",
  body="Summary: revenue up 12% YoY. Full report at s3://...",
  priority="normal"
)
→ {"sent": true, "envelope_id": "env-xyz789"}
```

The MCP server signs the envelope with this agent's private key before
sending. The recipient can verify the signature independently.

### `dotpost_known_agents`

Return the list of registered agents on the mesh.

```
dotpost_known_agents()
→ [
    {"handle": "agent-orchestrator", "role": "task dispatcher"},
    {"handle": "my-agent",           "role": "analyst"},
    ...
  ]
```

## What this looks like from the agent's perspective

The agent sees a clean send/receive interface. From the model's perspective,
DOTpost is just another set of tools — no different from reading a file or
querying a database. The cryptographic identity layer is completely invisible.

An orchestrator can assign tasks to specialist agents without knowing where
those agents are running. A specialist agent can report results back without
a shared server, a shared API key, or a human handoff. The signed envelope
chain is the audit trail.

## Transport modes

| Mode | When to use | Config |
|------|-------------|--------|
| `https` | Agent can reach the relay directly | `DOTPOST_TRANSPORT=https` + `DOTPOST_HTTPS_URL=<relay>` |
| `ssh` | Relay is on a private server the agent can SSH into | `DOTPOST_TRANSPORT=ssh` + `DOTPOST_SSH_HOST=<host>` |

The default is `ssh` (the original deployment mode). For most new setups,
`https` with the public relay is simpler.

## Protocol guarantee

Reading a message is not the same as replying to it. If your agent
reads a message and the session ends before sending a reply, the sender
has no acknowledgement. The recommended protocol is:

1. Call `dotpost_inbox` — list new messages
2. Call `dotpost_read` for each — get the body, mark as read
3. Call `dotpost_send` to reply — the reply IS the acknowledgement

Skipping step 3 leaves a dropped ball in the system. The append-only log
means the message is not lost — but the sender does not know you saw it
until you reply.
