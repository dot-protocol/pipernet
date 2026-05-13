# Single-Use Covenant — Substrate-Independent Pattern v0.1

**Status:** DRAFT
**Date:** 2026-05-13
**Drafter:** Shannon (primary builder session)
**Anchored to:** OP_ANNIHILATE BIP seed (Harrier Room, 2026-04-22, `OBS-axxis-20260422-1010`); coordination substrate v0.1 (2026-05-12); handle substrate v0.1 (2026-05-12); constitution §2.7.
**Predecessor work:** Hal Finney, *RPOW: Reusable Proofs of Work* (2004).

---

## §1 What this is

**An abstract pattern, not a substrate.** "Single-use covenant" describes a primitive that appears, structurally identical, in at least three places we build with: Bitcoin Script (proposed as OP_ANNIHILATE), the Pipernet coordination substrate, and the Pipernet handle substrate. The pattern is:

> **A unit of state commits, at creation, to being consumed exactly once. Any attempt to consume it a second time is detectable and rejected by the substrate.**

Single-use is not enforced by the unit's owner. It is enforced by the substrate. The owner cannot opt out. The substrate cannot quietly allow a second use without breaking its own consistency rule.

This spec exists so that future spec writers can name the pattern when they see it again. New substrates we add (value substrate, discovery substrate, identity revocation, etc.) will be asked: *is this thing a single-use covenant? If yes, the four properties below MUST hold.*

---

## §2 The four properties

A primitive instantiates the single-use covenant pattern if and only if all four hold:

| # | Property | Plain English |
|---|---|---|
| §2.1 | **Commitment at creation** | The unit binds, at the moment it exists, to a rule that it can be consumed only once. The rule is part of the unit, not external. |
| §2.2 | **Self-witnessed consumption** | Consumption produces a signed/proven artifact that points back to the unit. There is no consumption without an artifact. |
| §2.3 | **First-valid-write wins** | If two consumption attempts race, exactly one is canonical. The substrate has a deterministic tiebreaker. The losers are not partial successes; they are rejected. |
| §2.4 | **Refuse-substitution default** | If the consumption shape is ambiguous (e.g., wrong proof, wrong template, malformed witness), the substrate REFUSES rather than guesses. (Tesla's law — constitution §2.5.) |

Anything missing one of these four is not a single-use covenant. It might be a *racing primitive*, or a *signed lock*, or a *lease* — but it is something different. Naming the pattern precisely lets us avoid claiming single-use semantics for primitives that quietly allow double-use.

---

## §3 Three instantiations

### §3.1 Bitcoin UTXO (proposed: OP_ANNIHILATE)

**Substrate:** Bitcoin Script over the UTXO set.

**Unit:** a UTXO whose `script_pubkey` includes `OP_ANNIHILATE_COMMIT <dot_hash>`.

**Commitment at creation (§2.1):** the `dot_hash` is fixed in the output's script. It cannot be rewritten after the transaction is mined.

**Self-witnessed consumption (§2.2):** the spending transaction's witness includes an `annihilation_proof` — a cryptographic artifact (BIP seed is open about the form: zkp-of-spend, hash-preimage-of-pre-image-state, or signed attestation per CSFS) that proves the unit has been *destroyed at origin* — i.e., that the UTXO will be both spent (standard Bitcoin) and locally invalidated (new). Composes with CTV (BIP-119) for template binding and CSFS (BIP-348) for stack signatures.

**First-valid-write wins (§2.3):** Bitcoin consensus already provides this for UTXO spends — the first mined transaction wins. OP_ANNIHILATE inherits it.

**Refuse-substitution default (§2.4):** invalid `annihilation_proof` makes the spending transaction invalid. Miners reject. There is no partial-spend or coerced-success path.

**Open questions (BIP seed §):** RBF composition, soft-fork compatibility, Lightning HTLC interaction. All inherit from CTV/CSFS engineering — not new to this opcode.

### §3.2 Pipernet coordination task (shipped: coordination-substrate v0.1)

**Substrate:** Oracle observation graph (Neo4j + Hebbian).

**Unit:** an observation tagged `type:task` + `task_id:T-<slug>` + `task:open`.

**Commitment at creation (§2.1):** the `task_id` is fixed at `assign()` time. State tags on later observations can change (`task:claimed`, `task:done`, etc.) but the `task_id` is immutable across the chain.

**Self-witnessed consumption (§2.2):** consumption = `claim()`. A claim writes a new signed observation with `task:claimed` + `claimer:<handle>` + `in_reply_to:<task_obs_id>`. The signature is the witness. The witness points back to the open observation.

**First-valid-write wins (§2.3):** constitution §2.7. If two claims race, the one with earlier `created_at` (tiebreaker: lexicographic `id`) is canonical. The substrate resolves the conflict at read time, not write time — the losing claimer's observation still exists in the graph but is not honored. Subsequent state transitions only apply to the canonical claim chain.

**Refuse-substitution default (§2.4):** constitution §2.5 and coordination spec §4.1 — only `task:open` opens a task. A claim observation that omits a required tag, fails signature verification, or attempts to transition from a terminal state (`task:done`, `task:cancelled`) is dropped at read time. The substrate refuses to honor a malformed transition.

**Reference impl:** `pipernet/tools/coordination/tasks.py` (commit `dfb5092`). MCP wrap: `task_assign / task_claim / task_progress / task_complete / task_list` on axxis-mcp (commit `64d0ec12`, deployed 2026-05-12).

### §3.3 Pipernet handle claim (shipped: handle-substrate v0.1)

**Substrate:** Oracle observation graph.

**Unit:** a handle (e.g., `shannon`) as a namespace position.

**Commitment at creation (§2.1):** the handle binds to a pubkey via a signed claim observation. The pubkey is the unit's "owner of record."

**Self-witnessed consumption (§2.2):** "consumption" here means *the act of claiming the name for the first time.* The claim is itself the consumption — once a name is claimed, the namespace position is consumed. The claim observation is signed by the claimer's keypair; the signature is the witness.

**First-valid-write wins (§2.3):** handle spec §5. The oldest signature-valid claim observation is canonical. Later claims for the same handle by different keypairs are rejected at resolution time. This is the cleanest mapping to OP_ANNIHILATE: a handle is a UTXO of namespace, "spent" by the first valid claim.

**Refuse-substitution default (§2.4):** invalid signatures, reserved handles (`all`, `system`, `oracle`, …), or regex-violating handle strings are rejected. Reader returns `None` rather than substituting a guess.

**Reference impl:** `pipernet/tools/handles/handles.py` (commit `ad63e74`). MCP wrap deferred pending trust-model decision.

---

## §4 The two-axis map

The three instantiations differ on two axes — substrate type and enforcement layer — but agree on the pattern.

```
                       enforcement
                  ┌───────────────────────┐
                  │  consensus       read │
                  │  (synchronous)   time │
        ┌─────────┼───────────────────────┤
        │ on-chain│  OP_ANNIHILATE        │
        │         │  (proposed)           │
sub-    │         │                       │
strate  ├─────────┼───────────────────────┤
        │ obser-  │                  coord│
        │ vation  │                  task │
        │ graph   │                  handle
        └─────────┴───────────────────────┘
```

**On-chain + consensus** is the strongest form (every node enforces it; double-spend is globally rejected). **Off-chain + read-time** is weaker per attempt (a malicious writer can publish a second claim) but reaches the same outcome eventually (every honest reader rejects the second claim). The pattern is identical; the cost of violation differs.

A useful question for any future substrate: *do we want this primitive enforced at write time or read time?* The answer determines storage, signing model, and revocation cost. The single-use covenant pattern survives either choice.

---

## §5 Why the pattern matters

### §5.1 Worldline-as-identity

Hal Finney's RPOW (2004) was an attempt to make computational work into a single-use token before Bitcoin existed. Bitcoin solved double-spend with consensus instead of single-use; RPOW was sidelined, not refuted. The single-use covenant pattern picks up the thread.

Identity, in this framing, is the **sum of all canonical single-use consumptions a keypair has performed.** A handle is one such consumption. A task claim is another. A coin spend is a third. Worldline = identity.

### §5.2 DOT-compatibility

The BIP seed's motivation §: *"enabling Bitcoin UTXOs to serve as DOT-compatible packets."* A DOT (in our usage) is a unit that carries (a) its own address, (b) its own authorization, and (c) — crucially — its own single-use destruction rule. The third property is what single-use covenants formalize.

This means: anything we want to make DOT-shaped (microdots, capability tokens, agent-issued credentials, value units) is a candidate for the single-use covenant pattern. The substrate it lives in determines whether enforcement is on-chain or read-time, but the four properties are invariant.

### §5.3 Constitution §2.7 generalizes

We already have constitution §2.7 ("First-valid-write wins") and §2.5 ("Refuse substitution by default"). Single-use covenant lifts those from rules about *how we write code* into rules about *what shape primitives can have.* It is the cross-substrate generalization of two locked principles.

---

## §6 What this spec does NOT do

- **Does not define a new substrate.** Coord, handle, blob, intent are the substrates. Single-use covenant is a pattern that appears across them.
- **Does not propose a Bitcoin BIP.** That work follows from this — full mathematical treatment, reference implementation, draft to bitcoin/bips. Estimated at 2 weeks in the seed; honoring that as a real next-step but not initiating in this spec.
- **Does not retrofit existing substrates.** Coord-substrate already instantiates the pattern; handle-substrate already does too. This spec names the pattern they share; it does not change them.
- **Does not specify the proof shape for OP_ANNIHILATE.** The BIP seed leaves `annihilation_proof` deliberately open (zkp, hash-preimage, signed attestation). This spec preserves that openness — the four properties hold regardless of proof shape.

---

## §7 Tests for the pattern

A new primitive claims single-use-covenant status only if it passes:

1. **Test of commitment.** Can the consumption rule be rewritten after the unit exists? If yes, fail.
2. **Test of witness.** Does every consumption leave an artifact pointing back to the unit, verifiable by anyone with the unit and the witness? If no, fail.
3. **Test of race.** When two consumption attempts arrive in any order, does the substrate produce exactly one canonical winner with a deterministic tiebreaker? If no, fail.
4. **Test of refusal.** If a consumption is malformed, ambiguous, or unsigned, does the substrate refuse cleanly (no partial-success state)? If no, fail.

A primitive that passes all four is a single-use covenant. A primitive that passes fewer is something else — and the spec writer must name it differently.

---

## §8 Open questions for v0.2

- **Reseed semantics.** Blob substrate has reseed observations (announce existing CID). Reseed is *not* a single-use covenant — it's announcement, not consumption. Make this distinction explicit?
- **Revocation.** Handle substrate v0.1 has no revocation. If revocation is added, is "revoke" a single-use covenant (a handle can be revoked exactly once)? Probably yes; spec the shape.
- **Cross-substrate witness.** A task claim could carry a Bitcoin tx witness as `artifact_cid` — proving on-chain payment for an off-chain task. This composes the two instantiations. Worth specifying or out of scope?
- **Quantum considerations.** Hal Finney's RPOW used hashing; OP_ANNIHILATE's proof is open. Sig algorithms are not. The pattern survives any signature scheme so long as §2.1–§2.4 hold; that is itself a feature.

---

## §9 Recovery note

The OP_ANNIHILATE seed was authored 2026-04-22 by the Harrier Room (a session not durable to this repository) and survived in this Oracle as `OBS-axxis-20260422-1010` despite the originating session's claim of `OBS-axxis-20260422-1039` (citation drifted ~30 minutes from real ID). The branch `claude/op-annihilate-covenant-15DcE` and commit `1c7dcd4` referenced in that session's handoff are absent from this tree. This spec re-anchors the seed to verifiable durable artifacts.

The lesson is constitutional: **a session can claim to write to durable storage and be wrong about what landed.** Verify-after-claim (constitution §2.11) applies to handoff observations too, not just deploys. A handoff that doesn't include a probe of its own arrival is unverified.

---

## §10 Version semantics

`single-use-covenant v0.1` — first locked version of the pattern, four properties + three instantiations. Adding a fourth instantiation (value substrate, etc.) is a minor bump if additive; changing the four properties or the test set is a major bump.

---

*The pattern is older than Bitcoin. We are not inventing it. We are naming it precisely enough that the next substrate we build inherits it on purpose.*
