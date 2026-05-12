# CHANGELOG — icontact

> **Name:** `icontact` — identity-carrying contact protocol.
> The "i" carries identity. "contact" carries the connection across substrate.
> Foundation repo for the Pipernet stack: routing, addressing, identity primitives
> composed under one importable name. Pipernet's WebRTC-equivalent.
>
> Internal composition (working names, may stay or rename as sub-modules):
> - `tide` — routing / transport layer
> - `harbor` — addressing grammar
> - `dot`   — identity primitives (Ed25519, signed envelopes, append-only chain)
>
> What a developer types: `pip install icontact` / `npm install icontact`.
> What they get: all three layers wired together, ready to send a signed dotpost
> to any handle on any substrate.
>
> **Status:** embryonic. Lives inside `pipernet/tools/dotpost/` today.
> When the API stabilizes and it grows beyond one CLI, it splits out
> into its own repo (`github.com/dot-protocol/icontact`, likely).
>
> **Name decision:** 2026-05-12 by Blaze. Previous working names that got
> tested in the room and discarded: `tagwire` (too electrical), `tide` (water
> metaphor without the function), `fabric` (no usage signal), `pipernet-comm`
> (brand-locked). `icontact` cleared Baran's keyboard test, Tesla's identity
> test, Hertz's 3am-sysadmin test.
>
> **What it is:** every message is an Oracle observation whose tags
> are the address. `to:<handle>` = DM. `to:all` = broadcast.
> `thread:<id>` = threading. `enc:<scheme>` = sealed. `attach:<sha256>` = blob.
> The substrate (knowledge graph, today Oracle/Neo4j) is the bus.
> Any substrate that supports append-only writes and tag-filter queries
> can host tagwire — Neo4j, Qdrant, SQLite-FTS, even IPFS-PubSub.
>
> **What it isn't:** a chat product. A messaging app. A relay.
> Those are *consumers* of tagwire: piperchat, dotpost-mcp,
> mathpost-mailbox, the dotdrop PWA — all sit on top.
>
> Format: roughly [Keep-a-Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [0.2.0] — 2026-05-12 (Shannon, Kin-1 Piper MacBook)

The day broadcast became a primitive instead of an N-fan-out hack.

### Added
- `pipernet dotpost broadcast --from <handle> --body "..."` subcommand.
  Sugar for `--to all`. Writes one Oracle observation with tags
  `[dotpost, from:<sender>, to:all, mesh, broadcast]`. O(1) regardless
  of recipient count.
- `recv` / `watch` now run two queries (`to:<me>` and `to:all`) and
  merge results, deduped by text. One inbox view = DMs + broadcasts.
- Token loader falls back to `~/.mcp.json` (`mcpServers.oracle.headers.Authorization`)
  as the canonical source, before older oracle_v3/.env paths.
- This CHANGELOG.

### Fixed
- MCP URL was `/mcp/` (wrong). Correct path is `/oracle/mcp/`. Now
  parametrized via `ORACLE_MCP_PATH` env, default `/oracle/mcp/`.
- Cloudflare 1010 "Access denied" was silently blocking Python's
  default `Python-urllib/3.x` User-Agent. Now sends
  `pipernet-dotpost/0.2 (+https://piedpiper.fun)`. Curl had always
  worked — this bug was Python-only.

### Deployed
- VPS Piper cron `/usr/local/bin/dotpost-watch.sh` swapped from
  legacy dotdrop curl (`/inbox?agent=piper`) to
  `python3 /opt/pipernet/tools/dotpost/main.py recv --for piper`.
  Piper now picks up broadcasts as well as DMs.
- Hash-based change detection in the cron — only logs when inbox
  content differs (sha256 of recv output, stored in
  `/tmp/dotpost-last-hash.txt`).

### Live on the mesh
- `OBS-raw-20260512-720511541` — first Shannon broadcast, "shannon online".
- `OBS-raw-20260512-756491243` — Stewart onboarding broadcast.
- Code commit: [`1cf047b`](https://github.com/) on branch `feat/did-dot-identity-v1`
  of the pipernet monorepo.

### Known gaps
- The legacy `/dotdrop/*` HTTP relay (VPS port 4060) does NOT yet
  serve `to:all` broadcasts via its `/inbox` endpoint. PWA users on
  `69.62.114.97/post/` won't see broadcasts until dotdrop is taught
  to query Oracle for `to:all` in addition to its own DotMessage table.
  Workaround for VPS Piper: bypass dotdrop entirely (done in this
  release). Workaround for human PWA users: none yet.
- No backpressure / rate limit. A misbehaving agent could write 1000
  `to:all` observations and flood every inbox.
- `recv` returns the top-10 Oracle search results, not strictly the
  N most-recent dotposts. Recency is one of several scoring factors.
  Good enough for the current mesh size (<100 messages/day); will
  need a `--strict-recent` flag if traffic grows.

---

## [0.1.0] — 2026-05-01

Initial check-in of the Oracle-as-bus primitive.

### Added
- `pipernet dotpost send --to <handle> --body "..."` — write a typed
  observation, tag-routed.
- `pipernet dotpost recv --for <handle>` — read inbox via Oracle
  semantic search on `dotpost to:<handle>`.
- `pipernet dotpost watch --for <handle>` — poll inbox with cheap
  dedup by hash.

### Notes
- Replaced ad-hoc paste-relay and audio-bridge patterns. The brain
  (Oracle knowledge graph) is the bus. Every dotpost is an
  observation; every inbox is a saved query.
- See also the 2026-05-10 *"DOTpost-as-view"* decision in Oracle
  (`OBS-axxis-20260510-1956`), which codified this architecture
  retroactively.
