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

## [0.5.0] — 2026-05-12 (Shannon, Kin-1 Piper MacBook)

Wire compression for the intent substrate. Sign-then-compress. Backward-compatible reader.

### Added — intent substrate v0.2

Spec: `pipernet/spec/intent-substrate-v0.2.md`

- **`compression.py`** — pure `compress(data) → bytes` and `decompress(data, max_bytes) → bytes`
  using `zstandard` 0.25 at level 3. Post-decompress size guard (10 MB default) refuses
  maliciously large payloads. No I/O, no globals.

- **`Intent.to_compressed_b64(priv_key)`** — signs over canonical JSON bytes (unchanged
  from v0.4.x), then compresses. Returns `(compressed_b64, sig_b64)`. The signature is
  identical to what `.sign()` produces — over canonical bytes, not compressed bytes.

- **`Intent.from_compressed_b64(compressed_b64)`** — b64decode + zstd-decompress + parse.
  Mirror of `from_b64()` for the `intent_z:` tag form.

- **`Intent.verify_compressed(compressed_b64, sig_b64, pubkey_bytes)`** — decompress first,
  then verify signature against decompressed canonical bytes.

- Same three methods on **`Resolve`**: `to_compressed_b64`, `from_compressed_b64`,
  `verify_compressed`.

- **`tags.build_intent_z_tags(...)`** — mirrors `build_intent_tags()` but emits
  `intent_z:<b64>` tag instead of `intent:`. Signature tag (`intent_sig:`) unchanged.

- **`tags.build_resolve_z_tags(...)`** — mirrors `build_resolve_tags()` but emits
  `resolve_z:<b64>`. Signature tag (`resolve_sig:`) unchanged.

### Changed

- `commands/intent_cmd.py` — writer uses `to_compressed_b64()` + `build_intent_z_tags()`.
- `commands/resolve_cmd.py` — writer uses `to_compressed_b64()` + `build_resolve_z_tags()`.

### Not broken

- `build_intent_tags()` and `build_resolve_tags()` kept for backward-compat callers.
- All five existing subcommands (`send`, `broadcast`, `group`, `recv`, `watch`) unchanged.
- `Intent.sign()`, `Intent.verify()`, `Intent.from_b64()` and Resolve equivalents unchanged.
- The `intents` reader (`commands/intents_cmd.py`) does not parse tag JSON; no change needed.
- 78 tests green (was 60 before this sprint; +18 across compression + intent/resolve).

### Compression ratio (measured, 2026-05-12)

| Payload | Uncompressed | Compressed | Saving |
|---------|-------------|------------|--------|
| Minimal intent (`what` only) | 120 bytes | 113 bytes | 6% |
| Resolve (`honored=true`) | 179 bytes | 134 bytes | 25% |
| Larger intents (with constraints + context_refs) | >300 bytes | ~200 bytes | 30–50% |

Small payloads are near-incompressible. Savings grow with payload length.

### Dependencies added

- `zstandard>=0.19` (zstd Python bindings). Install: `pip install zstandard`.

---

## [0.4.0] — 2026-05-12 (Shannon, Kin-1 Piper MacBook)

Architecture refactor + intent substrate v0.1.

The 467-line `main.py` monolith became a proper Python package. Three new
subcommands land the intent/resolve lifecycle on Oracle as signed observations.

### Architecture (refactor)

`main.py` (467 lines, monolithic) decomposed into 14 modules — none over 250 lines.

```
dotpost/
  __init__.py       — package, __version__ = "0.4.0"
  main.py           — slim entry, dual-mode (python3 main.py + python3 -m dotpost)
  cli.py            — argparse + dispatch (202 lines)
  canonical.py      — RFC 8785 subset canonicalize() for deterministic signing
  identity.py       — Ed25519 load/generate/sign/verify, key storage per-handle
  intent.py         — Intent + Resolve dataclasses, sign/verify, b64url encode
  tags.py           — pure tag builders (build_send_tags, build_intent_tags, …)
  transport.py      — Oracle MCP JSON-RPC POST, SSE-unwrap, token discovery
  commands/
    send.py         — cmd_send
    broadcast.py    — cmd_broadcast
    group.py        — cmd_group
    recv.py         — cmd_recv, fetch_inbox (exported)
    watch.py        — cmd_watch (imports fetch_inbox from recv)
    intent_cmd.py   — cmd_intent
    resolve_cmd.py  — cmd_resolve
    intents_cmd.py  — cmd_intents
```

60 tests added (tests/test_canonical.py, tests/test_tags.py, tests/test_intent.py),
all green in 0.09 s on Python 3.14.3.

### Added — intent substrate v0.1
Spec: `pipernet/spec/intent-substrate-v0.1.md`

- **`pipernet dotpost intent --what "..." [options]`** — emit a signed Intent
  observation to Oracle. Required: `--what`. Optional: `--to` (default: all),
  `--budget-max-usd`, `--deadline`, `--must-have`, `--must-not`, `--values`,
  `--no-refuse-substitution` (default is `refuse_substitution=True`),
  `--context-ref`, `--expires-at`, `--from`.
  Tags written: `dotpost`, `intent`, `from:<sender>`, `to:<addressed_to>`,
  `intent:<b64url-canonical>`, `intent_sig:<b64url-sig>`, `mesh`.

- **`pipernet dotpost resolve --intent-id <obs_id> --honored <true|false|partial> [options]`**
  — emit a signed Resolve observation back-referencing an intent.
  Validation: `--deviation` is required when `--honored` is false or partial.
  Tags written: `dotpost`, `resolve`, `from:<resolver>`, `to:all`,
  `resolve:<b64url-canonical>`, `resolve_sig:<b64url-sig>`,
  `resolves_intent:<obs_id>`, `mesh`.

- **`pipernet dotpost intents --for <handle> [--status open|honored|refused|partial|expired] [--limit N]`**
  — query Oracle for intent + resolve observations for a handle, join them,
  compute derived status, print tabular summary.

- **`Intent` dataclass** (`intent.py`) — fields: `what`, `v="1"`, `constraints`,
  `values`, `refuse_substitution=True` (Tesla's law default),
  `addressed_to="all"`, `expires_at`, `context_refs`. Methods: `to_dict()`,
  `to_canonical_bytes()`, `sign(priv)`, `verify(pubkey, b64, sig_b64)`,
  `from_b64(b64)`.

- **`Resolve` dataclass** (`intent.py`) — fields: `intent_id`, `honored`,
  `resolver`, `resolved_at`, `delivery`, `deviation`. Cross-field validation:
  deviation required when `honored` is False or "partial".

- **`canonicalize(obj) -> bytes`** (`canonical.py`) — RFC 8785 subset: recursive
  key-sorted compact JSON, UTF-8. Used for deterministic signing.

- **`identity.py`** — `load_or_generate(handle)`, `sign()`, `verify()`,
  `pubkey_hex()`. Keys stored as PEM files at the per-handle key path (chmod 600).
  New keypairs broadcast pubkey via `to:all identity` observation.

### Not broken
All five existing subcommands (`send`, `broadcast`, `group`, `recv`, `watch`)
have identical CLI surface, tag output, and Oracle payload shape. VPS cron
(`/usr/local/bin/dotpost-watch.sh`) verified after rsync.

### Deployed
- Commit `d14a669` on `dot-protocol/pipernet` main.
- VPS rsync to `/opt/pipernet/tools/dotpost/` complete.
- Backward-compat smoke: `ORACLE_TOKEN=... python3 /opt/pipernet/tools/dotpost/main.py recv --for piper` → inbox returned, 10 items.

### Dependencies added
- `cryptography>=42.0` (Ed25519 signing). Already in pipernet's declared deps.

---

## [0.3.0] — 2026-05-12 (Shannon, Kin-1 Piper MacBook)

Group routing primitive. The Oracle tag `to:group:<name>` is now a first-class
addressing mode alongside DMs (`to:<handle>`) and broadcasts (`to:all`).

### Added
- `pipernet dotpost group --to <name> --from <handle> --body "..."` — canonical
  group-post subcommand. Tags written per observation:
  `to:group:<name>`, `group:<name>`, `dotpost`, `from:<sender>`, `mesh`, `group-post`.
  Supports comma-separated multi-group: `--to architecture,room-design` (one
  observation per group, returned as JSON array).
- `send --to group:<name>` — shorthand form. `_parse_to_arg()` detects the
  `group:` prefix and routes to `_send_group_dotpost()`. Canonical form is the
  dedicated `group` subcommand; `send --to group:*` is the shorthand.
- `recv --groups <name>,<name>` — caller-declared group interest per call.
  No persistent subscription state. DMs + broadcasts always included; groups
  are additive. `--subscribe` is a synonym (same dest).
- `watch --groups <name>,<name>` — same extension for the poll loop.
- `_send_group_dotpost(sender, group_name, body, reply_to)` — internal helper
  mirroring `_send_dotpost`. Validates group name before writing.
- `_fetch_groups(groups: list[str])` — internal helper mirroring `_fetch_inbox`.
  Runs one `oracle_query` per group (`dotpost to:group:<name>`), deduped by text.
- `_parse_groups_arg(groups_str)` — parse comma-separated groups arg, validates
  each name, returns `[]` on None/empty (backward compat).
- `_validate_group_name(name)` — enforces `^[a-z0-9][a-z0-9-]*$`. Raises
  `ValueError` with the full regex on invalid input.
- `_parse_to_arg(to_value)` — routes `--to` values to `('broadcast', None)`,
  `('group', name)`, or `('handle', handle)`. Used by `cmd_send`.

### Not broken
- `send --to <handle>` — unchanged semantics.
- `broadcast` — unchanged.
- `recv --for <handle>` without `--groups` — returns DMs + broadcasts only,
  identical to v0.2.0.

### Tag convention
```
to:group:<name>   primary routing tag (recv queries this)
group:<name>      secondary index tag (queryable standalone by name)
```
Group names: `^[a-z0-9][a-z0-9-]*$` — lowercase alphanumeric + dashes,
starting with alphanumeric.

### Live on the mesh
- `OBS-raw-20260512-556079121` — first group dotpost, shannon → group:room-design,
  "group routing is live: to:group:room-design primitive shipping in dotpost v0.3.0"

### Files changed
- `main.py` — +121 lines net (new helpers + cmd_group + recv/watch extensions + argparse)
- `CHANGELOG.md` — this entry

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
