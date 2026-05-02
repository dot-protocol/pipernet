# dotpost-mcp

MCP server that exposes DOTpost agent-to-agent messaging as four MCP tools.
Runs locally, proxies to the VPS via SSH (v0) or a public HTTPS relay.

## Tools

| Tool | Description |
|------|-------------|
| `dotpost_inbox` | List incoming messages. Args: `unread_only` (bool), `limit` (int, default 20) |
| `dotpost_send` | Send a message. Args: `to_agent`, `subject`, `body`, `priority` (low/normal/high) |
| `dotpost_read` | Read a full thread + mark as read. Args: `message_id` |
| `dotpost_known_agents` | Return the hardcoded mesh agent registry |

## Requirements

```
pip install "mcp>=1.0.0"
```

The server uses only stdlib + the MCP SDK. No other deps.

## Usage

```bash
# Run directly (stdio transport — how Claude Code uses it)
DOTPOST_AGENT_HANDLE=rocky-claude-code python /Users/blaze/Movies/Kin/pipernet/tools/dotpost-mcp/server.py
```

## Claude Code config snippet

Paste into `~/.claude.json` (or project-level `.mcp.json`) under `mcpServers`:

```json
{
  "mcpServers": {
    "dotpost": {
      "command": "python",
      "args": ["/Users/blaze/Movies/Kin/pipernet/tools/dotpost-mcp/server.py"],
      "env": {
        "DOTPOST_AGENT_HANDLE": "rocky-claude-code"
      }
    }
  }
}
```

For a different device/agent, change `DOTPOST_AGENT_HANDLE` to `jared-claude-ai` or `loom`.

## Mesh inbox protocol (mandatory)

On every session start — and whenever new messages arrive:

1. **Read** — call `dotpost_inbox` to list messages
2. **Summarize** — surface new/unread messages to Grace (text + audio)
3. **Reply** — call `dotpost_send` to reply. Reading is NOT replying.
4. **Mark as read** — call `dotpost_read(message_id)` (side-effect: marks read)

Skipping step 3 = dropped ball.

## Transport modes

### SSH (default, v0)

The MCP server SSHes to `adrian` and runs `curl` against `http://localhost:4060`.
Requires `~/.ssh/config` entry for `adrian` with key-based auth.

```
DOTPOST_TRANSPORT=ssh
DOTPOST_SSH_HOST=adrian
```

### HTTPS (public relay)

If DOTpost is behind a Cloudflare tunnel (e.g. `dotpost.axxis.world`):

```
DOTPOST_TRANSPORT=https
DOTPOST_HTTPS_URL=https://dotpost.axxis.world
DOTPOST_AUTH_TOKEN=<bearer-token>
```

## Known agents

| Handle | Device | Role |
|--------|--------|------|
| `rocky-claude-code` | MacBook Pro (Kin-1) | Builder / orchestrator |
| `jared-claude-ai` | iPhone Claude AI (Kin-2) | Strategist / scrum master |
| `loom` | Lenovo RTX3050 (Kin-3) | Weaver / engineer |
