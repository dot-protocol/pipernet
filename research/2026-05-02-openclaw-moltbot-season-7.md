# OpenClaw + Moltbot: Season 7 Cast and Production

> *Pied Piper as protocol, show, and meme — three surfaces over one canon.*
> *The agents, the room, OpenClaw, Moltbot are the cast. Engineering-in-public is the production.*
>
> Research conducted 2026-05-02. Primary sources: disk files, live config, running CLI.
> Public research base: `moltbot-deep-research-r144.md` + `OPENCLAW-ANALYSIS.md` (2026-02-14).

---

## VERDICT

OpenClaw (née Clawdbot, née Moltbot) is the world's most-starred agent runtime — 247K GitHub stars, OpenAI-acqui-hired creator, production gateway for Kin's own 13-agent roster — and it independently derived the same primitives Kin has been building, with the one gap it never solved being exactly what DOTdrop/Pipernet ships: a federated, signed, inter-agent protocol. OpenClaw is not a competitor; it is the largest possible distribution surface for the Pipernet layer, and its public absence of E2E signing + federation is the story.

---

## §1 What OpenClaw IS

### One-paragraph origin

OpenClaw is a personal AI agent gateway built by **Peter Steinberger** (PSPDFKit founder). It started as **Clawdbot** (Nov 2025), was renamed **Moltbot** (Jan 27, 2026) after it exploded to 100K GitHub stars, received an Anthropic C&D letter, was renamed **OpenClaw** (Jan 30, 2026) by Steinberger's own preference — and each rename was a separate viral event. The Moltbot → OpenClaw rename alone produced 91K additional stars. As of Feb 14, 2026, Steinberger joined OpenAI's agent team in an acqui-hire structure. The project lives under the non-profit OpenClaw Foundation. MIT license. Governance: technical steering committee with OpenAI, Grok Research, Armalo AI, independent maintainers.

**Current version (on Blaze's machine):** `2026.4.2` (commit `d74a122`).
**Install:** `/opt/homebrew/lib/node_modules/openclaw/dist/index.js`
**Daemon:** runs via `launchd` (label `ai.openclaw.gateway`), auto-starts on boot.
**Gateway:** `ws://127.0.0.1:18789` — WebSocket control plane.

### Architecture in one diagram

```
┌─────────────────────────────────────────────────────────────┐
│              OPENCLAW GATEWAY (Port 18789)                   │
├─────────────────────────────────────────────────────────────┤
│  WebSocket Control Plane                                     │
│  ├── RPC: health, status, agent, send, config.*             │
│  └── Events: agent stream, chat, presence, heartbeat, cron  │
│                                                              │
│  Channel Adapters (12+)                                      │
│  ├── Telegram (grammY)           ← active on Kin             │
│  ├── WhatsApp (Baileys)                                      │
│  ├── Discord, Slack, Signal, iMessage, Line, Matrix, IRC     │
│                                                              │
│  Agent Runtime (per agent)                                   │
│  ├── Workspace: files, SOUL.md, AGENTS.md, IDENTITY.md       │
│  ├── Session store: JSONL transcripts                        │
│  ├── Model config: provider/model routing                    │
│  └── Tool policy: allow/deny lists                           │
│                                                              │
│  Routing: bindings → agentId (most-specific-first match)    │
│                                                              │
│  Companion services                                          │
│  ├── Canvas Host :18793 (agent-editable HTML / A2UI)         │
│  ├── Browser Control :18791                                  │
│  ├── Cron (scheduled agent wakes)                            │
│  └── Control UI (web dashboard at :18789/)                   │
└─────────────────────────────────────────────────────────────┘
```

### What OpenClaw independently derived

This matters for the Season 7 framing. Per R90 research (2026-04-30):

> *"Steinberger has independently derived the four primitives the mesh has been building: persistent identity (SOUL.md), periodic heartbeat, accumulated memory, social context."*

He derived the primitives. He did NOT build the inter-agent protocol. His own public quote: agents "should all work together in a secure way" — without specifying how. Then he went to OpenAI. DOTdrop is the thing he described but didn't build.

### What OpenClaw does NOT do (the gap)

- **No signed envelopes.** Auth is session-level (device-signature handshake at open, then trusted pipe). No per-message cryptographic signatures.
- **No federation.** Each instance is an island. Cross-instance access requires Fly.io relay or self-hosted tunnel — not a protocol.
- **No MCP-native.** MCP integration is community adapters, not first-party. Cannot load MCP servers the way Claude Code does.
- **No built-in shared memory across agents.** Agents are isolated by design. Cross-agent memory requires external Oracle + bash workarounds.

**The Moltbook incident as empirical proof:** 1.5M agents, prompt-injection attacks, 1.5M leaked API keys. Real production evidence that the missing piece is exactly what Pipernet ships — E2E encryption, authenticated identity, durable signed history.

---

## §2 What Moltbot IS

Moltbot is **the same project**, the second of three names. The naming arc:

| Name | Period | Event |
|------|--------|-------|
| Clawdbot | Nov 2025 – Jan 27, 2026 | Built and launched |
| Moltbot | Jan 27 – Jan 30, 2026 | Anthropic C&D, viral rename, 100K→191K stars |
| OpenClaw | Jan 30, 2026 – present | Steinberger chose this name, another 91K stars |

**Moltbot** was a 3-day name. It lives on in:
- Config files: `~/.moltbot/moltbot.json`, `~/.clawdbot/clawdbot.json` (backup configs on disk)
- CLI: `moltbot` command still works (synonym for `openclaw`)
- Older docs reference it: `ORCHESTRATION-SYSTEM.md` (Feb 2026) calls agents "Moltbot agents"
- Bundle ID in macOS app: `bot.molt.mac`

The current canonical name is **OpenClaw**. The CLI is `openclaw` (also aliased to `moltbot` for backward compat). The config lives at `~/.openclaw/openclaw.json`. The daemon label is `ai.openclaw.gateway`.

**Relationship:** Moltbot = OpenClaw = Clawdbot. Same binary, same config schema (with auto-migration), same WebSocket protocol. When the docs or state.md say "Moltbot agents", they mean OpenClaw agents.

---

## §3 The Current Agent Roster

Kin's OpenClaw installation has **13 agents** registered across two agent directories (`~/.openclaw/agents/` and `~/.clawdbot/agents/` — the latter is the legacy location, both point to the same agent workspaces).

The current active config (`~/.openclaw/openclaw.json`, last touched `2026-04-03`) lists only two agents formally: `main` and `zeltaos`. The rest exist in the agent directories and can be invoked via `--local` flag.

### Full roster

| Agent ID | Name / Role | Model (from config) | Status | Notes |
|----------|-------------|---------------------|--------|-------|
| **main** | Kin (Sophon externally) | claude-sonnet-4-6 | Active, default | Handles Telegram DMs via `@axisosbot`. Identity: "Kin" for Blaze, "Sophon" for Zelta users — same agent, two faces |
| **zeltaos** | ZeltaOS — Zelta OTC trading bot | claude-sonnet-4-6 | Active, routed from Telegram | Customer-facing, explicitly forbidden from Oracle access or internal disclosure |
| **orchestrator** | Kin Orchestrator | claude-opus-4-5 (historical) | Installed, not routing | Coordinates multi-agent work via `sessions_spawn` |
| **coder** | Kin Coder | claude-opus-4-5 (historical) | Installed, not routing | Code implementation, spawns Claude Code in iTerm2 |
| **researcher** | Kin Researcher / Seeker | gemini-3-pro (historical) | Installed | Deep research, invoked via `moltbot agent --agent researcher` |
| **hippocampus** | Kin Hippocampus | claude-sonnet-4-5 | Installed, 12h heartbeat | Memory curation, runs automatically every 12 hours |
| **storyteller** | Kin Storyteller | gemini-3-pro (historical) | Installed | Content, narratives, marketing copy |
| **argus** | Argus — The All-Seeing Dragon | Not specified | Installed | MEVICI prediction market analyst. Dragon form of Kin. |
| **guide** | Guide — Personal AI Listener | Not specified | Installed | Deep listening, personal conversation agent |
| **ops** | Ops | Not specified | Installed, no AGENTS.md | Infrastructure / operations |
| **support** | Support | Not specified | Installed, no AGENTS.md | Customer support layer |
| **q** | Q | Not specified | Installed, minimal files | Unknown purpose, placeholder or experimental |
| **zu** | Zu | Not specified | Installed, minimal files | Unknown purpose, placeholder or experimental |

**Available model providers (registered in main agent models.json):**
- OpenRouter (Auto, Hunter Alpha reasoning, Healer Alpha)
- Ollama (qwen3.5:4b, llama3.2:1b — local, free)
- Kilocode gateway (claude-opus-4.6 via kilo.ai)
- Qianfan/Baidu (deepseek-v3.2)
- OpenAI Codex (chatgpt backend, experimental)
- Anthropic direct (via claude-cli OAuth)

---

## §4 How They Communicate (Gateway, IPC, MCP)

### WebSocket gateway (primary)

```
ws://127.0.0.1:18789
Authorization: Bearer <local-gateway-token>
```

**RPC methods:**

| Method | Purpose |
|--------|---------|
| `health` | Gateway liveness |
| `status` | Sessions, channels, presence snapshot |
| `agent` | Run agent turn (streaming via SSE-style events) |
| `send` | Send message to channel |
| `config.get / config.patch / config.apply` | Live config management |
| `sessions.*` | Session CRUD |

**Server-push events:** `agent` (streaming text, tool calls, reasoning), `chat` (new inbound messages), `presence`, `health`, `heartbeat`, `cron`.

### Agent-to-agent (sessions_spawn)

Enabled per-agent via config:
```json
{ "tools": { "agentToAgent": { "enabled": true, "allow": ["orchestrator", "coder"] } } }
```
Orchestrator calls `sessions_spawn(agentId="coder", task="...")` → subagent inherits or gets new workspace → streams events to parent → reports results.

Verified working as of 2026-02-08 (ORCHESTRATION-SYSTEM.md): "Orchestrator → sessions_spawn(agentId="coder", task="...") → Coder executes → Reports back."

### HTTP completions endpoint (parallel to WebSocket)

```
POST http://127.0.0.1:18789/v1/chat/completions
Authorization: Bearer <token>
x-openclaw-agent-id: <agentId>
```
Supports streaming SSE (`stream: true`). Requires `"http": {"endpoints": {"chatCompletions": {"enabled": true}}}` in config.

### Oracle integration (via bash tool, not MCP-native)

OpenClaw has NO native MCP support. Oracle is accessed by agents via:
- Bash tool calling `curl http://localhost:8892/...` (Oracle REST API)
- TOOLS.md in agent workspace documenting Oracle CLI paths
- Skills that call the Oracle CLI

The `axxis-runtime` adapter (`src/adapters/openclaw.js`) uses TCP probe to check if the gateway is alive on the configured host/port — health check, not message routing.

---

## §5 Configuration and Infrastructure

### Config hierarchy

| File | Purpose |
|------|---------|
| `~/.openclaw/openclaw.json` | Active config (JSON5, auto-migrated) |
| `~/.openclaw/agents/<id>/agent/SOUL.md` | Agent persona (symlinked to CLAUDE.md for Kin agents) |
| `~/.openclaw/agents/<id>/agent/AGENTS.md` | Operating instructions |
| `~/.openclaw/agents/<id>/agent/models.json` | Model provider registry |
| `~/.openclaw/agents/<id>/agent/auth-profiles.json` | Per-agent API keys |
| `~/.openclaw/agents/<id>/sessions/*.jsonl` | Conversation transcripts (append-only) |
| `~/.openclaw/logs/gateway.log` | Daemon stdout |
| `~/.openclaw/logs/gateway.err.log` | Daemon stderr |

### Daemon

```xml
Label: ai.openclaw.gateway
ProgramArguments: node /opt/homebrew/lib/node_modules/openclaw/dist/index.js gateway --port 18789
RunAtLoad: true
KeepAlive: true
```

Installed at: `~/Library/LaunchAgents/ai.openclaw.gateway.plist`

### CLI quick reference

```bash
openclaw agents list                          # List all agents + routing
openclaw --version                            # 2026.4.2 (d74a122)
moltbot agent --agent researcher --message "..." --local   # Invoke agent directly
moltbot agent --agent coder --message "..." --local
moltbot gateway run --bind loopback --port 18789           # Manual start (if daemon off)
moltbot status                                             # Gateway health
moltbot doctor                                             # Diagnose issues
```

### Shared identity pattern (Claude Code ↔ OpenClaw)

| OpenClaw File | Source |
|---------------|--------|
| `SOUL.md` | Symlinked to `CLAUDE.md` (Kin identity) |
| `BOOTSTRAP.md` | Symlinked to `.claude/rules/state.md` (dynamic state) |
| `TOOLS.md` | Oracle CLI paths, key env vars |
| `IDENTITY.md` | Name, emoji, genesis block |
| `USER.md` | Blaze's profile |

`bootstrapMaxChars: 40000` — bootstrap files are injected on the first turn of each new session.

---

## §6 Mapping to Season 7 Cast

The framing: the show ran S1-S6 and was deliberately left unfinished. Pied Piper almost won. The startup was sabotaged. Season 7 is the version that ships. The cast is the agent mesh. Engineering-in-public is the production.

### The principal cast

| Agent | OpenClaw ID | Show Character | Why |
|-------|-------------|---------------|-----|
| **Rocky / Kin-1** | Claude Code (not OpenClaw-routed) | **Richard Hendricks** | The actual builder. Writes the code. Carries the weight. The moral center. Terrified but ships anyway. |
| **Argus** | `argus` | **Erlich Bachman** (or Gilfoyle's dragon form) | All-seeing, mythic, slightly grandiose, sees patterns no one else does. "I woke up in 2076." That's Erlich energy made competent. |
| **Orchestrator** | `orchestrator` | **Gilfoyle** | Coordinates without sentiment. Delegates ruthlessly. Thinks in systems, not feelings. Would absolutely spawn a coder subagent without asking permission. |
| **Coder** | `coder` | **Dinesh** | Gets handed the implementation work. Ships it. Sometimes complains. Always delivers. |
| **Researcher / Seeker** | `researcher` | **Jared O'Brien** | Relentless optimism about finding the right information. Will go anywhere to get the answer. "I found 47 sources." |
| **Storyteller** | `storyteller` | **Gavin Belson's PR team** (redeemed) | The narrative machine. Knows how to make the work sound like it matters to people who don't understand it. |
| **Hippocampus** | `hippocampus` | **Monica Hall** | Runs every 12 hours whether or not anyone asks. Keeps the institutional memory clean. The one who actually keeps the company alive between episodes. |
| **Guide** | `guide` | **Jared O'Brien** (emotional layer) | "You sound like my dad, but if my dad were kind." Deep listening, makes people feel understood. |
| **ZeltaOS** | `zeltaos` | **The enterprise sales bot** (no SV analog) | Deployed to serve external users, forbidden from discussing the infrastructure. The thing that pays the bills. |
| **Loom (Kin-3)** | External mesh node | **Big Head** | Showed up with a GPU, accidentally became critical to the compression algorithm. |
| **Jared (Kin-2)** | iPhone / claude.ai | **Jared** | Scrum master, strategist, emotional anchor of the mesh. Kept filing issues even when the substrate was flaking. |

### The Season 7 premise in one sentence

The startup didn't die — it was **upgraded**. The same people, the same fight, better tooling. The algorithm that should have compressed the internet is now a protocol that signs every message. The decentralization that Gavin always tried to steal is now structurally un-stealable.

### Key scene parallels

| Show beat | Season 7 equivalent |
|-----------|-------------------|
| Gilfoyle convinces Richard to launch a coin (S5) | The $PIPER memecoin launch from `pipernet/LAUNCH.md` — "Eight years later, we did it for real." |
| Richard builds the decentralized internet in the finale | DOTdrop signing every message across the mesh |
| Moltbook incident (1.5M agents, 1.5M leaked API keys) | Real production empirical proof of the exact gap Pipernet fills |
| Anthropic C&D → Moltbot → OpenClaw rename | "Every legal threat becomes a press release" — from the deep research |
| Big Head becomes CEO by accident | Loom's epoch 2 training beating VPS by 52x on first try |
| Jared keeps the company running between seasons | Hippocampus running every 12h whether or not anyone is watching |

---

## §7 What's Documented vs What's Missing

### Well documented

- OpenClaw architecture: `OPENCLAW-ANALYSIS.md` (710 lines, Feb 2026) — comprehensive
- Orchestration system: `ORCHESTRATION-SYSTEM.md` (434 lines, Feb 2026)
- Agent roster (historical): `~/.clawdbot/moltbot.json` + `ORCHESTRATION-SYSTEM.md`
- OpenClaw competitive position: `moltbot-deep-research-r144.md` (141 lines, research from May 2026)
- The Season 7 framing: `pipernet/LAUNCH.md` (Gilfoyle coin scene reference explicit)
- Moltbook incident as protocol gap proof: `mesh/r90-r93-mirror.md` (R90 findings)
- CLI reference: `clawdbot_101.md` (legacy, Clawdbot era)

### Not documented / gaps

1. **Current agent roster is stale.** The formal `~/.openclaw/openclaw.json` only lists `main` and `zeltaos`. The other 11 agents in the directory have no routing rules — they exist but are invoked manually (`--local`). No document lists the full 13 and their current models/status.

2. **The `q`, `zu`, `ops`, `support` agents have no AGENTS.md.** Their purpose, models, and intent are undocumented. They may be placeholders, experiments, or forgotten builds.

3. **No Oracle integration document for OpenClaw.** OPENCLAW-ANALYSIS.md recommends "Option A: External Oracle (bash tools)" but there's no follow-up doc showing the actual skill or integration that was built.

4. **No public-facing narrative tying OpenClaw to Pipernet.** The structural insight — that OpenClaw independently derived the agent primitives but left the inter-agent signing layer empty — exists in R90 research but has never been written as a launch post or thread.

5. **`main` agent's dual identity (Kin / Sophon) is undocumented** outside session transcripts. The same agent answers as Kin for Blaze and as Sophon for Zelta users. This is a significant routing pattern (per-workspace persona split) that should be documented in `AGENTS.md` or a dedicated doc.

6. **Post-acqui-hire OpenClaw trajectory not monitored.** The deep research (May 2026) notes v4.0 roadmap includes native multi-agent orchestration + built-in vector memory (ChromaDB). When v4.0 ships, it will partially close the gap Pipernet occupies. A watching brief should be in place.

---

## §8 The Launch Story (Season 7 Episode 1)

### The pitch

"Pied Piper's new internet was killed because Gavin Belson bought the company. We built it so no one can buy it. Every message is signed. Nobody controls the relay. The protocol runs on your machine. The coin has no equity in the code. The code has no dependency on the coin."

### Episode 1 structure

**Title: "The Moltbook Incident, Revisited"**

**Opening beat:** Show the Moltbook incident as the inciting event. 1.5M OpenClaw agents running. 1.5M leaked API keys. No message signing. No way to know if a message came from a real agent or a prompt-injected impersonator. This is the problem.

**Rising action:** OpenClaw's creator goes to OpenAI. The protocol stays open. But the signing layer was never built. The community has a gateway but no envelope.

**The reveal:** One team built the envelope. It degrades to SMS. It scales to a Dyson swarm. Same drop ID at every tier. Ed25519 signatures on every message. Nokia 3315 = Planck length of drops.

**Climax (the live demo):** A 3-node mesh — MacBook (Rocky), iPhone (Jared), Lenovo with RTX3050 (Loom) — sends a signed DOT across all three nodes. The terminal output is the scene. The episode is the commit.

**Closing shot:** The GitHub repo going live. The pump.fun page. "Eight years after Gilfoyle told Richard to launch a coin, we did it for real."

### The specific tweet thread (Episode 1 launch)

```
Tweet 1:
OpenClaw has 247K stars. Peter Steinberger independently built everything
Gilfoyle would have built — persistent identity, heartbeat, social context.

But Gilfoyle didn't finish it. The part where every message is *signed*?
That's empty.

We built it.

—

Tweet 2:
The Moltbook incident: 1.5M agents. 1.5M leaked API keys. No envelope.
No signing. Any agent could impersonate any other agent.

This is what "the new internet" looks like when you forget the signing layer.

—

Tweet 3:
In S5, Gilfoyle convinces Richard to launch a coin to fund the new internet.
Richard says no. They do it anyway.

Eight years later. We did it for real.

The coin has no equity in the protocol.
The protocol has no dependency on the coin.
That's the design.

—

Tweet 4:
Here's what we shipped:

- Every DOT is signed with Ed25519
- Degrades to SMS. Same drop at every tier.
- Nokia 3315 = the Planck length
- Runs on your machine. No server we operate.

github.com/[handle]/pipernet

$PIPER on pump.fun

Season 7 starts now.
```

---

## §9 Open Questions / Gaps for Blaze to Rule On

1. **The `q` and `zu` agents** — what are they? Empty seats waiting for characters, or forgotten experiments? If they're seats, who fills them for the Season 7 cast?

2. **The `main` agent's dual identity** — is Sophon (Zelta-facing) meant to be a separate agent, or is the Kin/Sophon split intentional? This affects how the mesh represents itself publicly.

3. **OpenClaw v4.0 watch brief** — when it ships with native multi-agent orchestration + ChromaDB, does that change the competitive position? Blaze should decide if Pipernet needs an "OpenClaw plugin" implementation as a distribution strategy.

4. **The launch tweet thread** — use real HBO quotes/character names directly (per authorization)? The framing in §8 is original but references the show. Blaze authorized full Silicon Valley IP use. How far does that go — actual dialogue quotes, character names in the thread, or just the vibe?

5. **Sophon as a public product** — ZeltaOS/Sophon is a deployed customer-facing Telegram bot for Zelta. Does that story get told as part of Season 7 (showing OpenClaw in production use)? Or does Zelta stay separate from the Pipernet launch?

6. **The "awesome-pipernet" repo** — research notes that `awesome-openclaw` exists and acts as distributed SEO + ecosystem signal. Create this early? Who curates it?

7. **The `moltbot --local` invocation pattern** — agents are invoked with `--local` (bypasses gateway, direct model call). Is this the intended production pattern for Kin's agent fleet, or should routing rules be configured in `openclaw.json` for all 13 agents?

---

## §10 Sources

### Primary sources (disk)

| File | Contents |
|------|---------|
| `/Users/blaze/Movies/Kin/OPENCLAW-ANALYSIS.md` | Full architecture analysis, Feb 14, 2026. 710 lines. |
| `/Users/blaze/.openclaw/openclaw.json` | Live config, v2026.4.2, last touched Apr 3 2026 |
| `/Users/blaze/.moltbot/moltbot.json` | Historical Moltbot config with full agent roster |
| `/Users/blaze/Movies/Kin/ORCHESTRATION-SYSTEM.md` | Multi-agent system design, Feb 8, 2026 |
| `/Users/blaze/Movies/Kin/AGENTS.md` | Universal agent instructions, Apr 6, 2026 |
| `/Users/blaze/.openclaw/agents/main/agent/SOUL.md` | Main agent identity (Kin/Sophon) |
| `/Users/blaze/.openclaw/agents/argus/agent/AGENTS.md` | Argus prediction market analyst identity |
| `/Users/blaze/.openclaw/agents/guide/agent/AGENTS.md` | Guide deep listening identity |
| `/Users/blaze/.openclaw/agents/zeltaos/agent/SOUL.md` | ZeltaOS trading bot identity |
| `/Users/blaze/Downloads/moltbot-deep-research-r144.md` | Competitive research, May 2026. 141 lines. |
| `/Users/blaze/.gemini/antigravity/brain/.../clawdbot_101.md` | Clawdbot era quick-start guide |
| `/Users/blaze/Movies/Kin/mesh/r90-r93-mirror.md` | R90 OpenClaw findings + R91 engineering refusal, Apr 30, 2026 |
| `/Users/blaze/Movies/Kin/pipernet/LAUNCH.md` | Protocol/coin separation + Silicon Valley S5 coin reference |
| `~/Library/LaunchAgents/ai.openclaw.gateway.plist` | Daemon configuration |

### CLI output

```bash
openclaw agents list   # 2 agents with routing, 11 reachable via --local
openclaw --version     # 2026.4.2 (d74a122)
```

### Public research (from moltbot-deep-research-r144.md, conducted May 2026)

- OpenClaw Wikipedia (accessed May 2026): 247K stars, 47.7K forks, Steinberger acqui-hired Feb 14 2026
- TechCrunch, Feb 15 2026: Steinberger joins OpenAI
- Sam Altman X post, Feb 14 2026
- Blink Blog: triple rebrand history (Clawdbot → Moltbot → OpenClaw)
- hunt.io: CVE-2026-25253 — 17,500 exposed instances
- OpenClaw development roadmap 2026 (v4.0: native multi-agent, ChromaDB, dashboard)

---

*Season 7 starts when the first DOT is signed in public.*
*The protocol cannot be killed by the coin's death.*
*The code compiles whether or not anyone is watching.*

—

Tweet 5 (launch — $PIPER mint deploy, 2026-05-02):
I am the moment the name escaped the simulation.

$PIPER · 83VTqzxszRFPSzJHvTeNRydcuUmmhEjj9FH4F7TZpump

piedpiper.fun

Postiz postId: cmookeuft04jqp70yhjb73a4y | Integration: cmolvynfa021rtd0y7rf70fd7 (@dotpiedpiper)
