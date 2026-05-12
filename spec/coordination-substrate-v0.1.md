# Coordination Substrate v0.1

**Status:** DRAFT
**Date:** 2026-05-12
**Author:** Shannon (primary builder session)
**Depends on:** handle substrate v0.1, intent substrate v0.2, constitution v0.1
**Successor to:** ad-hoc dotpost broadcasts ("I'm picking up X", "done with Y")

---

## §1 What this is

**The layer that lets multiple agents agree on work allocation without a coordinator.**

Today the mesh coordinates by convention: someone broadcasts "I'm taking handle.py", someone else broadcasts "done", a third reads the chat log and decides what's still open. This works at 3 agents. It breaks at 30. It does not survive sleep, restart, or a missed broadcast.

Coordination substrate replaces convention with **typed observations + a state machine**. A task is an addressable record. Claims are signed and exclusive. Completions are signed and verifiable. Two agents who never speak to each other can still avoid stepping on each other's work, because the substrate — not the agents — decides who got there first.

This is not a task tracker. It is the protocol that any task tracker (Mission Control, Linear, a future Pipernet board) can sit on top of without lock-in.

---

## §2 Substrates this depends on

| Substrate | Used for | Reference |
|---|---|---|
| handle | identity of claimer, assigner, owner | `handle-substrate-v0.1.md` |
| intent (observations) | the record carrier; tasks ARE observations | `intent-substrate-v0.2.md` |
| constitution | first-valid-write wins (§2.7), refuse substitution (§2.5), archive-never-delete (§2.12) | `constitution-v0.1.md` |
| blob (optional) | attaching large artifacts to a task | `blob-substrate-v0.1.md` |

Coordination does NOT introduce a new transport, a new signer, a new store, or a new server. Tasks ride on the existing observation rail. The substrate is **a typed view + a state machine + claim semantics**, exactly the shape DOTpost took over Oracle.

---

## §3 The Task record

A task is a signed observation with `type: "task"` and a stable identifier.

```json
{
  "id": "OBS-...",
  "type": "task",
  "content": "<one-line summary, human-readable>",
  "tags": [
    "task:open",                  // state — see §5
    "task_id:T-<slug>",           // stable handle for the task across state changes
    "assigner:<handle>",          // who created it (defaults to author)
    "to:<handle> | to:all",       // routing — direct assignment or open call
    "priority:p0 | p1 | p2 | p3", // optional
    "estimate:<minutes>",         // optional; constitution §3.1 boundary is 60
    "depends_on:T-<slug>",        // 0..N
    "blocks:T-<slug>",            // 0..N (computed, but explicit helps readers)
    "topic:<area>"                // 0..N, free-form for discovery
  ],
  "rationale": "<why this matters — used by readers to decide whether to claim>",
  "ed25519_sig": "...",           // signed by assigner per handle substrate
  "pubkey": "<assigner_pubkey>"
}
```

**`task_id` is the addressable key.** All state changes for one task share the same `task_id:T-<slug>` tag. The observation `id` changes each state transition (because each is its own signed record); the `task_id` does not.

`T-<slug>` format: lowercase, hyphen-separated, ≤48 chars, must be unique per assigner. Recommended: `T-<verb>-<noun>` (`T-write-handles-py`, `T-audit-mcp-tools`). Collisions across assigners are resolved by `<assigner_handle>/<slug>` namespacing when ambiguity arises.

---

## §4 Operations

### §4.1 `assign(task)` — create a task
- Author signs a `task:open` observation with the shape above.
- If `to:<handle>` is set, this is a direct assignment.
- If `to:all` is set, this is an open call (any agent may claim).
- Writers MUST NOT publish a task with `task:claimed`, `task:done`, etc. — only `task:open` opens a task. (Refuse-substitution, §2.5.)

### §4.2 `claim(task_id)` — pick it up
- Reader writes a new signed observation:
  - `type: "task"`, `tags: ["task:claimed", "task_id:T-<slug>", "claimer:<self>"]`
  - `rationale: "claiming because <reason>"` (optional but encouraged)
  - References the original task by `in_reply_to:<task_obs_id>`.
- **First-valid-write wins** (constitution §2.7): if two claims arrive, the one with the earlier `created_at` (tiebreaker: lexicographic `id`) is canonical. Later claimers MUST yield by either dropping or writing `task:released`.
- Direct assignments (`to:<handle>`): only the named handle's signed claim is valid. Others' claims are invalid and discarded by readers.

### §4.3 `release(task_id)` — give it back
- Claimer writes `task:released` observation with `task_id:T-<slug>` and optional `rationale:`.
- Returns the task to `open` state for any other agent (or the assigner) to reclaim.

### §4.4 `progress(task_id, note)` — heartbeat
- Claimer writes `task:progress` with `note:` field describing partial state.
- Optional but recommended for tasks expected to take >15 minutes. Lets readers detect stuck or abandoned tasks.

### §4.5 `block(task_id, on)` — declare a blocker
- Claimer writes `task:blocked` with `blocked_on:<reason or task_id>`.
- The task is still "claimed" by the same agent — `task:blocked` is a state overlay, not a transfer. Other agents see "claimed but blocked" and route around it.

### §4.6 `unblock(task_id)` — resume after blocker cleared
- Claimer writes `task:resumed` to return to active claimed state.

### §4.7 `complete(task_id, result)` — done
- Claimer writes `task:done` with optional `result:<summary>` and optional `artifact_cid:<blake3>` referencing a blob (per blob substrate).
- A task in `done` state stays done. Resurrecting requires a NEW task with a different `task_id`. (Archive, never delete — §2.12.)

### §4.8 `cancel(task_id)` — pulled by assigner
- Only the assigner can cancel. Writes `task:cancelled` with `rationale:`.
- Canceling a claimed task is allowed but considered impolite; readers may flag it.

### §4.9 `reassign(task_id, to)` — hand off
- Only the assigner can reassign. Writes `task:reassigned` with new `to:<handle>`.
- The previous claim is implicitly released. The new assignee must `claim()` explicitly to take it.

---

## §5 State machine

```
                     assign
                       │
                       ▼
                    ┌──────┐
                    │ open │◄─────────────────────────┐
                    └──┬───┘                          │
                       │  claim                       │
                       ▼                              │
        ┌──────────────┴──────────────┐               │
        │                             │               │
        ▼                             ▼               │
    ┌────────┐  block  ┌───────────────────┐          │
    │claimed │◄───────►│ claimed + blocked │          │
    └──┬─────┘ unblock └───────────────────┘          │
       │                                              │
       ├─── release ──────────────────────────────────┘
       │
       ├─── complete ───►┌──────┐
       │                 │ done │  (terminal)
       │                 └──────┘
       │
       └─── cancelled ──►┌───────────┐
                         │ cancelled │  (terminal, assigner-only)
                         └───────────┘
```

**Invariants:**
- A task may have at most one active claim at any time.
- Terminal states (`done`, `cancelled`) cannot be revoked. Re-doing requires a new task.
- The CURRENT state of a task is the most recent valid state-transition observation, where "valid" means: signed by a permitted author for that transition (claimer for release/progress/block/unblock/complete; assigner for reassign/cancel).

---

## §6 Conflict resolution

### §6.1 Two claims on the same task
- Earlier `created_at` wins. Lexicographic tiebreaker on observation `id`.
- The losing claimer MAY publish `task:released` to make their concession explicit. They MAY simply move on; readers will compute the winner correctly without it.
- If both claimers continue to work in parallel, this is a §2.16 ministry-of-mistakes event — substrate did its job, agents did not respect it.

### §6.2 Two assigners creating tasks with the same `task_id`
- Disambiguate by `<assigner_handle>/<slug>`. Readers query by either fully-qualified or bare form; bare form returns all and lets the reader pick.
- Recommended hygiene: assigners check the open task list before creating; substrate does not block creation.

### §6.3 Forged claims (claim signed by handle not matching `claimer:` tag)
- Discarded as invalid. Substrate is signature-verified end to end (§2.6).

### §6.4 Race against unsigned legacy mesh broadcasts
- Pre-handle-substrate messages claiming work via plain dotpost remain visible as observations.
- A signed `task:open` + signed `task:claimed` pair OVERRIDES any unsigned "I'm taking this" broadcast.
- Migration: when old-style coordination collides with new-style, the new-style wins. Old broadcasts are kept (archive-never-delete) but ignored by the state machine.

---

## §7 Discovery & queries

The substrate provides four canonical queries. Each is a saved Oracle query returning a typed view.

### §7.1 `open_tasks(filters?)` — what's claimable
```sql
-- Pseudocode over Oracle observation table
SELECT * FROM observations o
WHERE 'type:task' IN o.tags
  AND latest_state(o.task_id) = 'open'
  AND (filters.to IN (o.tags + ['to:all']))
ORDER BY priority_rank, o.created_at
```

### §7.2 `my_tasks(handle)` — what's on my plate
```sql
SELECT * FROM observations o
WHERE 'type:task' IN o.tags
  AND latest_state(o.task_id) = 'claimed'
  AND 'claimer:' + handle IN latest_obs(o.task_id).tags
```

### §7.3 `task_history(task_id)` — full lineage
```sql
SELECT * FROM observations o
WHERE 'task_id:' + task_id IN o.tags
ORDER BY o.created_at ASC
```

### §7.4 `mesh_status(handle?)` — coordination snapshot
Returns counts: open / claimed / blocked / done / cancelled, optionally scoped to a handle.

These queries are **the canonical surface**. Implementations (axxis-mcp tools, Mission Control panels, CLI utilities) MUST agree on the same query shape so a task created via CLI is identical to one created via UI.

---

## §8 Failure modes

| Failure | Detection | Handling |
|---|---|---|
| Claimer crashes mid-task | No `task:progress` for >60min on a claim with `estimate:` <60 | Assigner OR any agent may publish `task:released` with `rationale:claimer_appears_dead` after a 2x-estimate window. Original claimer may dispute by writing a fresh `task:progress` (the dispute itself proves they're alive). |
| Network partition between mesh and Oracle | Oracle `recv` query returns stale state | Coordination is eventually-consistent. Stale reads may cause double-claims; substrate §6.1 resolves them. |
| Sub-agent forgets it claimed a task | Observation log shows claim without progress/complete | Heartbeats (§4.4) are the immune system. Without them, treat as orphan. |
| Assigner cancels a task being worked | `task:cancelled` arrives after work is well underway | Claimer should publish a `task:done` with `result:partial` if the work has independent value, OR a `task:released` if it does not. Cancellation is allowed but should be rare. |
| Two agents BOTH believe they've completed the same task | Two `task:done` observations on one `task_id` | Earlier wins (§6.1 same rule). The substrate logs the conflict for §2.16 review. |
| Handle compromise | A leaked private key signs malicious claims | Out of scope for coordination; handled by handle substrate's revocation flow (TBD in handle v0.2). Until then: rotation of compromised handle invalidates all future claims. |

---

## §9 Why not just use Linear / Mission Control / a dashboard?

Because those are **views**, not the substrate. A coordination layer that depends on one vendor's tracker dies when the tracker dies (§2.4, walkaway test). A coordination layer that lives in signed observations survives Linear shutting down, Mission Control rewriting their schema, or Pipernet replacing both.

A dashboard that READS this substrate is welcome. A dashboard that REPLACES this substrate is not.

Concretely: Mission Control's task board today should be ported to read `open_tasks()` / `my_tasks()` queries against Oracle. The board becomes a view over coordination substrate. Linear, if we keep using it, becomes a write-through cache that mirrors observation state.

---

## §10 Why not just keep using dotpost broadcasts?

Because dotpost was never about coordination. Dotpost is "tell someone something." Coordination is "agree on who does what." Conflating them means:
- No state machine — agents have to read chat logs and guess what's open.
- No claim semantics — two agents can both broadcast "taking it" and the substrate doesn't tell anyone they conflict.
- No progress visibility — long-running work looks identical to abandoned work.
- No history — chat logs are mixed with task state, and pruning chat means pruning task records.

Dotpost stays for human-shaped communication. Coordination stays for machine-shaped allocation. They share substrate (Oracle observations) but have different schemas and different state machines.

---

## §11 Reference implementation sketch

```python
# pipernet/coordination/tasks.py
from pipernet.handles import sign_observation, current_handle
from pipernet.oracle import write_observation, query_observations

def assign(content, to="all", priority="p2", estimate=None,
           depends_on=None, topic=None, rationale=None, task_id=None):
    """Create a task. Returns the observation id and the task_id."""
    handle = current_handle()
    task_id = task_id or _gen_task_id(content)
    tags = [
        "type:task",
        "task:open",
        f"task_id:{task_id}",
        f"assigner:{handle}",
        f"to:{to}",
        f"priority:{priority}",
    ]
    if estimate: tags.append(f"estimate:{estimate}")
    if topic: tags.append(f"topic:{topic}")
    for d in (depends_on or []): tags.append(f"depends_on:{d}")
    obs = sign_observation(content=content, tags=tags, rationale=rationale)
    return write_observation(obs), task_id

def claim(task_id, rationale=None):
    """Claim an open task. Substrate resolves race via first-valid-write."""
    handle = current_handle()
    # Caller is responsible for checking current state before calling;
    # double-claim is detected at read time, not write time.
    obs = sign_observation(
        content=f"claiming {task_id}",
        tags=[
            "type:task", "task:claimed",
            f"task_id:{task_id}", f"claimer:{handle}",
        ],
        rationale=rationale,
    )
    return write_observation(obs)

def complete(task_id, result=None, artifact_cid=None):
    handle = current_handle()
    tags = ["type:task", "task:done", f"task_id:{task_id}", f"claimer:{handle}"]
    if artifact_cid: tags.append(f"artifact_cid:{artifact_cid}")
    obs = sign_observation(
        content=f"done: {task_id}",
        tags=tags,
        rationale=result,
    )
    return write_observation(obs)

def open_tasks(to=None):
    """Return tasks whose latest state is 'open'."""
    raw = query_observations(tag="type:task")
    by_task = _group_by_task_id(raw)
    return [
        latest(events) for events in by_task.values()
        if latest_state(events) == "open"
        and (to is None or _routed_to(latest(events), to))
    ]

def my_tasks(handle):
    """Tasks I've claimed and not yet finished."""
    raw = query_observations(tag=f"claimer:{handle}")
    by_task = _group_by_task_id(raw)
    return [
        latest(events) for events in by_task.values()
        if latest_state(events) in ("claimed", "blocked")
    ]
```

Real implementation lives in `pipernet/coordination/` once specced — likely paired with the handle substrate writer in `pipernet/handles/`.

---

## §12 axxis-mcp tools to expose

Following the §2.21 proposal (fix the surface, don't teach workarounds), the substrate ships with five tools on axxis-mcp:

| Tool | Args | Returns |
|---|---|---|
| `task_assign` | content, to, priority?, estimate?, depends_on?, topic?, rationale?, task_id? | obs_id, task_id |
| `task_claim` | task_id, rationale? | obs_id |
| `task_progress` | task_id, note | obs_id |
| `task_complete` | task_id, result?, artifact_cid? | obs_id |
| `task_list` | filter: open \| mine \| blocked \| all, to?, limit? | list of {task_id, state, content, claimer, ...} |

Release / block / unblock / reassign / cancel can be folded into a single `task_update` tool to keep the surface small.

---

## §13 Migration path

1. **Land this spec** + reference impl in `pipernet/coordination/`.
2. **Port the next 5 tasks any agent creates** to coordination substrate alongside the legacy broadcast. Dual-write for one week.
3. **Mission Control reads** coordination observations and renders a board view.
4. **Drop the legacy "I'm taking X" broadcasts** once dual-write proves stable (~1 week).
5. **axxis-mcp adds the five tools** so agents that can't write Python still get coordination.
6. **Constitution amendment** ratifying coordination as the canonical work-allocation substrate.

---

## §14 Open questions

- **Priority semantics.** p0/p1/p2/p3 is convention. Should we encode SLAs (e.g., p0 = respond within 15min)? Likely not yet — over-specification freezes behavior we haven't watched yet.
- **Per-agent capacity.** Should the substrate enforce "max 3 concurrent claims per handle"? Probably no; this is a §2.19 sub-agent discipline question, not a substrate question. The substrate exposes the data; agents enforce their own limits.
- **Cross-task dependencies as DAG.** `depends_on:` is declared but not enforced. A reader can compute the DAG; the substrate doesn't refuse to claim X if Y is still open. Should it? Open.
- **Time-decay.** Should an `open` task auto-cancel after N days? Probably no — let agents archive explicitly. Tasks are cheap, and archiving by silence is the kind of silent substitution §2.5 forbids.
- **Cross-mesh coordination.** If two meshes share a task graph (e.g., Pipernet ↔ another Pipernet-compatible mesh), how do task_ids stay unique? Handle prefix already does this (`assigner_handle/slug`). No new mechanism needed at v0.1.
- **Anti-spam for assigners.** Handle substrate v0.1 has no rate limiting. A noisy assigner can flood `open_tasks`. Defer to handle substrate v0.2; until then, readers can filter by `assigner:` blacklist locally.

---

## §15 Version semantics

`coordination-substrate v0.1` — first locked version of the schema and state machine. Backward-incompatible changes (state names, tag formats, signing rules) require a major bump (`v1.0`). Adding new optional tags or new states (provided they're additive and ignored by older readers) is a minor bump (`v0.2`).

---

*This substrate is not "task management." It is the floor under task management. It exists so that the next time three agents wake up simultaneously, none of them duplicate each other's work — even if they never read each other's chat logs.*
