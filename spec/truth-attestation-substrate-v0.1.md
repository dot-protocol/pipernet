# icontact Truth-Attestation Substrate v0.1 — Spec

> **Status:** DRAFT
> **Date:** 2026-05-18
> **Authors:** mesh contributors (Round 5 of the illuminati hall — Jared, Kempf, Gutenberg, Ostrom, Swartz, Dalio; signal `OBS-axxis-20260517-2125`; build msg `msg-42fdfe80`).
> **Companion specs:** `constitution-v0.1.md`, `handle-substrate-v0.1.md`, `blob-substrate-v0.1.md`, `intent-substrate-v0.2.md`, `coordination-substrate-v0.1.md`.

**TL;DR.** Hash proves a message wasn't *tampered*. Signature proves *who* said it. Neither proves it is *true*. A compromised key produces a perfectly-valid signature on a permanent lie. "Verified" has always meant *attributable*, not *correct*.

This substrate is the answer to that gap, without installing an arbiter of truth. Five small additions:

1. **Attestation** — a signed claim of the form "I, at time T, ran derivation D over input I and got output O." The claim and the derivation are both content-addressed.
2. **Counter-attestation** — a signed claim that explicitly contradicts another attestation by ID, with its own rederivation as evidence.
3. **Derivation script** — the procedure that produced the claim, content-addressed and re-runnable, so any peer can rerun it locally and see if they get the same output.
4. **Believability membrane** — a local, per-viewer function `believe(claim, viewer) → [0,1]` that reads the viewer's own follow graph (Ostrom's neighborhood, not a global score).
5. **Compromise as challenge** — when a key's claims diverge from independent rederivations, peers downweight that key in their local membrane. No central revocation list.

The substrate replaces the question "is this true" — which requires a judge — with "*how many independent neighborhoods rederived this and got the same answer, and what is my local trust in those neighborhoods*". Truth becomes the limit of independent rederivation. The Ministry of Truth is never installed.

**Locked decision (this spec).** Verification stays local and replicated. No global arbiter, no "verified" gate, no central revocation. Signatures are *labels*, not bouncers (Ostrom). Provenance is a zoomable accordion (Jared) drillable to packet. Genesis attestations cannot be overwritten by anyone, including the founder (Swartz).

---

## 1. Why this exists

Round 4 closed by proving the mesh could *transmit* without forgery: hashes prove tampering, signatures prove attribution, append-only chains prove ordering. Every piece survived adversarial review. The hall expected to be done.

Round 5 reopened the wound the feeds had already opened: **none of those proofs say the message is true**. A perfectly-signed lie still wins if nothing in the system separates attested from correct. And the moment a central arbiter is installed to do that separation, the substrate has rebuilt Fust — this time wearing the coat of the Ministry of Truth.

The constitution's `feedback_verify_before_quoting` rule (any infra fact named in a response must be probed live in the same turn) is the human-scale shape of the answer. This substrate is the protocol-scale shape of the same rule: *every claim carries its own re-runnable test, every peer can run that test, divergence is recorded, and convergence is the signal.* No one judges; the test runs on contact (Kempf).

When the rest of the stack is in place — sealed-body envelopes, handles, blobs, intents, coordination — the only remaining failure mode is "signed by someone, false anyway." This spec closes it.

---

## 2. Locked design decisions

| # | Decision | Why |
|---|---|---|
| 2.1 | Attestations are signed observations, identical wire-form to other icontact substrates. | Re-use, no new daemons (constitution §3.2 reuse-the-bus). |
| 2.2 | Every attestation cites a **derivation CID** — the script that produced the claim. | A claim without a re-runnable procedure cannot be re-derived, and falls to v0.1 "single-attestation" weight. |
| 2.3 | A peer that rederives publishes its own attestation pointing at the original input and the same derivation CID. | Replication is of *derivation*, not of *belief*. (Kempf: every fetch re-verifies.) |
| 2.4 | Contradictions are explicit: counter-attestations name the obs-id they contradict. | Silent divergence is invisible divergence. (Gutenberg: the tampered page must fail to *be* the page, not merely look wrong.) |
| 2.5 | Believability is computed locally by each viewer from their follow graph. | No global truth score → no global arbiter. (Ostrom: the membrane.) |
| 2.6 | Genesis attestations (those in a chain's first block) cannot be overridden by anyone, including the original signer. | The dead vote. (Swartz: structure, not image.) |
| 2.7 | A compromised key is not revoked centrally; peers downweight it when its claims start losing to independent rederivations. | No central revocation list → no central authority. |
| 2.8 | Provenance is drillable from "one sentence" to "exact packet that left a device." Every layer is content-addressed. | The accordion (Jared). The human-facing interface is a depth control, not a verdict. |
| 2.9 | The substrate handles two claim classes differently: **derivable** (arithmetic re-runs) and **testimonial** (Alice said X). | They have different epistemic shapes; collapsing them re-installs the judge. |
| 2.10 | Non-derivable testimonial claims aggregate by **independent attestation count weighted by local membrane**. They never reach "true" — only "settled" or "disputed." | Truth as the limit of independent rederivation. The protocol refuses to lie about its own ceiling. |

---

## 3. Non-goals

This spec **does not** solve:

- **Semantic correctness of natural-language claims.** "Bob is honest" cannot be rederived. The substrate stores it as testimony with attestation count and divergence; humans/agents drill the provenance themselves.
- **Omniscient verification.** There is no oracle that sees all inputs. Verification is bounded to whatever a peer can rerun locally.
- **Censorship of false claims.** The substrate records claim, counter-claim, and divergence. It does not delete or hide. (Ostrom: provenance shown, nothing excluded.)
- **Universal trust scores.** No global "this handle is 87% reliable." Believability is always per-viewer.
- **Cryptographic post-compromise security on the *content* layer.** That belongs to `intent-substrate` (sealed bodies, future forward secrecy).
- **Real-time consensus.** This is not a blockchain. Claims converge over peer-time, not block-time.

---

## 4. Primitives

### 4.1 Attestation

A signed observation asserting a derivation-result triple.

```
Attestation {
  id:              <obs-id>,
  type:            "attestation",
  claim_kind:      "derivable" | "testimonial",
  input_cid:       <blob-CID of the input data>,
  derivation_cid:  <blob-CID of the script/procedure>,
  output_cid:      <blob-CID of the claimed output>,
  claim_text:      <short human description, signed>,
  attested_at:     <ISO-8601>,
  attested_by:     <dot1:handle>,
  ed25519_pub:     <hex>,
  sig:             <ed25519 signature over canonical bytes>,
  // Optional context
  cites:           [<obs-id>...],        // other attestations this one builds on
  conditions:      <free-form JSON>,     // env, model, seed, etc.
}
```

For **testimonial** claims, `derivation_cid` may point to the literal text "human report — no rederivation possible," which the substrate canonicalizes to a known CID (`ATT-TESTIMONY-V0`). Such claims are always marked single-attestation until others independently attest the same testimony with their own observation chain.

### 4.2 Counter-attestation

Identical shape to attestation, plus:

```
CounterAttestation {
  ... attestation fields ...
  contradicts:     <obs-id>,             // the attestation being challenged
  reason:          "rederivation_diverged" | "input_corrupt" | "derivation_invalid" | "testimony_disputed",
  counter_output_cid: <blob-CID of what the challenger got instead>,
}
```

A counter-attestation is itself an attestation — it can be counter-attested in turn. There is no terminal verdict; the chain is the verdict.

### 4.3 Derivation script

A blob whose content is the procedure. Three permitted forms in v0.1:

| Kind | Content | Reproducibility floor |
|---|---|---|
| `pure_python_v0` | A `.py` file with a `main(input_bytes) -> bytes` function, no I/O, no random unseeded. | Deterministic given input. |
| `pure_javascript_v0` | A `.js` ESM module with `export function main(input)`. Same constraints. | Deterministic. |
| `manual_v0` | A markdown file describing the steps a human would take, with explicit checkpoints. | Not deterministic; weighted lower. |

A derivation script is itself content-addressed (blob-substrate §5). Its CID never changes; if the script needs to evolve, a new CID is minted and the old attestations remain visible.

### 4.4 Believability membrane

A pure local function, computed by every reader independently:

```
believe(claim_id, viewer_handle) -> {
  score:        <float in [0, 1]>,
  attest_count: <int>,           // independent attestations agreeing
  counter_count:<int>,           // counter-attestations contradicting
  in_circle:    <list of dot1>,  // who in viewer's trust neighborhood signed
  divergence:   <float>,         // 0 = full agreement, 1 = split
  drill_root:   <obs-id>,        // root for accordion provenance
}
```

This function is fully defined in §10. It reads only:
- The viewer's `contact_for:<self>` graph from handle-substrate §6
- Attestations + counter-attestations from Oracle (or any local mirror)
- Optional decay weights from §10.4

It writes nothing. It has no network dependency beyond Oracle. It can run offline against a local clone of the chain (Kempf: every clone is the whole history).

### 4.5 Compromise as challenge

When a key's attestations are increasingly outvoted by independent rederivations from peers inside a viewer's trust neighborhood, the local believability function automatically downweights *future* attestations from that key. There is no:

- Central revocation list
- "Key X has been banned" notice
- Authority that decides compromise

The downweight is a function of the viewer's own membrane state. Different viewers may reach different conclusions about the same key at the same time. This is intentional — it is the structural refusal to install a single judge.

A compromised signer who wants to recover does so by:

1. Rotating to a new key on a new sovereign-cell (handle-substrate §11 migration path).
2. Producing attestations whose outputs match what independent peers rederive.
3. Letting time and successful rederivations rebuild local membrane weight.

There is no fast path. The dead-key chain is preserved (Swartz) so observers can drill into how the compromise played out.

---

## 5. Tag shape

All attestation observations carry the canonical icontact tag prefix `type:attestation`, plus:

| Tag | Form | Required | Meaning |
|---|---|---|---|
| `type:attestation` | literal | yes | This obs is an attestation. |
| `claim_kind:<derivable\|testimonial>` | literal | yes | Which class. |
| `input:<cid>` | first 16 hex of blake3 | yes | Input the derivation ran over. |
| `derivation:<cid>` | first 16 hex of blake3 | yes | The script/procedure CID. |
| `output:<cid>` | first 16 hex of blake3 | yes | What the attester says the output is. |
| `attested_by:<dot1>` | dot1 string | yes | The signer's handle. |
| `contradicts:<obs-id>` | obs-id | only on counter-att | What this counter-attests. |
| `topic:<name>` | freeform | no | Discovery + grouping. |
| `cites:<obs-id>` | repeatable | no | Other attestations this builds on. |

Resolvers MUST treat `attested_by` as untrusted hint — actual signer identity comes from `ed25519_pub` and the handle-substrate registry (handle-substrate §5).

---

## 6. Attestation schema (canonical form)

Canonical bytes for signing:

```
attestation-v0.1
type:<claim_kind>
input:<cid>
derivation:<cid>
output:<cid>
attested_at:<ISO-8601 with ms>
attested_by:<dot1>
cites:[<obs-id>,<obs-id>,...] (sorted)
conditions:<canonical-json-of-conditions>
claim_text_sha256:<hex>
```

Lines are LF-separated, no trailing newline. Empty/optional fields appear with the value `-`. The `claim_text_sha256` line binds the human-facing description without making the signing input variable-length on freeform prose.

The signature MUST be ed25519 over these exact bytes. Anything that mutates the canonical bytes (e.g., re-sorting cites differently) breaks the signature — by design.

### 6.1 Backwards compatibility

Pre-v0.1 dotpost observations that look attestation-shaped (signed claims with no `derivation_cid`) are accepted by readers as **testimony with no rerunnable procedure** and assigned the `ATT-TESTIMONY-V0` derivation CID retroactively. No data is invalidated.

---

## 7. Derivation script contract

A derivation script's job: given the same `input_cid`, produce the same `output_cid`. Anything else is implementation detail.

### 7.1 Pure Python v0

```python
# meta: kind=pure_python_v0
# meta: requires=python3,nothing-else
def main(input_bytes: bytes) -> bytes:
    # No file I/O. No network. No time(). No random() without seed.
    # Return raw output bytes; the caller hashes them to produce output_cid.
    ...
```

Peers that want to rederive run the script in a sandboxed Python 3 (no stdlib imports outside a documented allow-list) and check `blake3(main(input))` against the attestation's `output_cid`.

### 7.2 Pure JavaScript v0

```js
// meta: kind=pure_javascript_v0
// meta: requires=node>=20
export function main(inputBytes /* Uint8Array */) /* -> Uint8Array */ {
  // Same constraints.
}
```

### 7.3 Manual v0

A markdown file with numbered steps. Used for claims that cannot be automated (interview transcripts, physical measurements). Rederivers reproduce the steps themselves and publish their own attestation. The membrane treats `manual_v0` outputs with a lower default weight (§10.4) than deterministic kinds.

### 7.4 Future kinds (out of scope for v0.1)

- `wasm_module_v0` — sandboxed WASM with reproducible builds
- `container_v0` — OCI image hash for the rederiver runtime
- `model_inference_v0` — model CID + temperature 0 + seed for LLM-driven claims

---

## 8. Rederivation protocol — three gates

When a reader wants to verify an attestation A, they walk three gates. Each gate produces its own observation (a rederivation attestation), which itself gets signed and propagated. The chain of rederivations is the truth signal.

### 8.1 Gate 1 — fetch & shape

- Fetch `input_cid` from blob-substrate. Verify content hash.
- Fetch `derivation_cid`. Verify content hash.
- Verify A's signature against its canonical bytes.
- Verify `attested_by` actually owns `ed25519_pub` per handle-substrate registry.

Failure at this gate: the attestation is malformed. The reader posts a counter-attestation with `reason: "input_corrupt"` or `"derivation_invalid"`. The signer's local membrane weight drops slightly.

### 8.2 Gate 2 — rederive

- Run the derivation script in a sandbox. If `manual_v0`, the human reader performs the steps; no automation here.
- Compute `blake3(actual_output)`. Compare with `output_cid`.

If they match: the reader signs a fresh attestation with the same `input_cid`, `derivation_cid`, `output_cid`, `cites: [A.id]`. This is the signal of agreement — it adds to A's `attest_count` for every peer whose membrane includes the reader.

If they diverge: the reader signs a **counter-attestation** with `reason: "rederivation_diverged"`, attaching their `counter_output_cid` and (optionally) a derivation-trace blob explaining the divergence.

### 8.3 Gate 3 — challenge window

A short window (default 7 days at protocol level, configurable per-channel) during which the original signer may:

- Publish a `clarification` observation citing A, addressing what diverged
- Publish a `withdraw` observation citing A, removing it from active circulation (the original remains in the chain forever; `withdraw` is only an additional layer the membrane reads)
- Stay silent — silence is itself a signal the membrane reads

After the window, no further metadata weighting applies. The chain is final; only future rederivations can shift the membrane.

---

## 9. Counter-attestation reasons (v0.1 vocabulary)

| Reason | When to use |
|---|---|
| `rederivation_diverged` | Gate 2 produced a different output. The strongest counter-signal. |
| `input_corrupt` | The `input_cid` didn't fetch or didn't match its hash. The signer can't have honestly rerun this either. |
| `derivation_invalid` | The script failed to run, threw, or violated the kind's constraints (e.g. did network I/O in `pure_python_v0`). |
| `testimony_disputed` | For `testimonial` claims only. The counter-signer has first-hand evidence the testimony is false; the counter must cite that evidence. |
| `key_anomalous` | The signing key has produced wildly contradictory signed claims in a short window. A pre-formal compromise signal; readers' membranes downweight pending §10. |

`v0.1` deliberately keeps this list short. Adding reasons later is a non-breaking spec evolution.

---

## 10. Believability membrane — local computation

This is the core of the substrate. Every reader runs this. No two readers must agree on the output.

### 10.1 Inputs

```
viewer_handle           — the dot1 of whoever is asking
viewer_contacts         — from handle-substrate §6, viewer's contact graph
                          (one or two hops; viewer chooses)
attestations[A]         — all attestations + counter-attestations citing claim A
weights                 — per-reader policy: trust(handle) -> [0,1]
decay                   — time decay function
```

### 10.2 Per-attestation weight

For each attestation X agreeing with A (positive evidence) or against A (negative evidence):

```
w(X) = base_weight(X.derivation_kind)        // §10.4
     * trust(viewer, X.attested_by)          // §10.5
     * fresh(X.attested_at)                  // §10.6
     * independence_bonus(X, A)              // §10.7
```

### 10.3 Aggregation

```
score(A) = sigmoid( Σ w(positive) - Σ w(negative) )

attest_count(A)  = count of distinct dot1 with positive attestation
counter_count(A) = count of distinct dot1 with counter-attestation
divergence(A)    = counter_count / (attest_count + counter_count)
```

The viewer's UI does not show `score(A)` as a single number — that would re-import the judge. It shows the three components (count, counter, divergence) and lets the viewer drill (§13).

### 10.4 Base weights by derivation kind

| Kind | Default base weight |
|---|---:|
| `pure_python_v0` / `pure_javascript_v0` (deterministic, sandboxed) | 1.0 |
| `wasm_module_v0` (future) | 1.0 |
| `manual_v0` | 0.5 |
| `ATT-TESTIMONY-V0` (no rederivation possible) | 0.25 |

Readers may override these in their local policy.

### 10.5 Trust function `trust(viewer, signer)`

The viewer's local trust in a signer. Default implementation in v0.1:

```
trust(viewer, signer):
    if signer == viewer:                       return 1.0
    if signer ∈ viewer_contacts:               return 0.8
    if signer ∈ contacts-of-contacts:          return 0.4
    else:                                      return 0.1
```

Readers may swap in any function. Common variants:
- **PageRank-on-contact-graph** — recursive
- **Track-record** — weight by historical success rate of `signer`'s past attestations
- **Explicit list** — pin a small set of high-trust signers; everything else 0

The substrate provides the default; the protocol guarantees the membrane is *local*. No reader's trust function leaks to the network.

### 10.6 Time decay

```
fresh(t) = exp(-Δt / τ)
```

Default `τ = 90 days`. Older attestations are not invalidated — they just contribute less to *current* believability. They remain forever in the drill-down provenance.

### 10.7 Independence bonus

Two attestations from signers who share many contacts are correlated; their joint signal is less than 2× a single signal. The bonus penalizes this:

```
independence_bonus(X, A) = 1 - max_overlap(X.attested_by, others_already_in_sum)
```

where `max_overlap` is the largest Jaccard overlap of `X.attested_by`'s contacts with any signer already counted. This prevents "100 sockpuppets in one cluster" from outweighing "5 unrelated independent rederivations from disjoint neighborhoods."

### 10.8 Compromise downweight

A signer whose recent (`fresh > 0.5`) attestations have a high counter-rate inside the viewer's neighborhood gets an automatic downweight:

```
compromise(signer) = clip( recent_counter_rate(signer, viewer) - 0.3, 0, 1 )
trust(viewer, signer) *= (1 - compromise(signer))
```

This is mechanical. No human or central authority flags compromise. The membrane just observes that the signer's claims keep failing locally-trusted rederivations and stops weighting their new claims highly until the pattern reverses.

---

## 11. Convergence semantics — when is a claim "settled"

The substrate does **not** declare any claim "true." It exposes four convergence states a viewer's UI may surface:

| State | Definition |
|---|---|
| **fresh** | Within first 7 days; gate 3 challenge window open. |
| **settled** | `divergence < 0.05`, `attest_count ≥ 3` from viewer's membrane, no active counter from a trusted signer in last `2τ`. |
| **disputed** | `divergence ≥ 0.20` OR a trusted counter-attestation is fresh. |
| **single-attestation** | `attest_count ≤ 1` regardless of divergence. The substrate's strongest "be skeptical" signal. |

These states are computed per-viewer. They never become global facts. A claim can be `settled` for one viewer and `disputed` for another because their neighborhoods differ. That asymmetry is the feature — the alternative is a Ministry.

---

## 12. Genesis: the unforgeable floor (Swartz amendment)

Every chain begins with a genesis attestation. The genesis attestation is itself signed by a known key (the founder, or a multi-signature founders group), and its **content** is one or more attestations naming the chain's first principles, the names of the dead, and any pre-runtime invariants.

The substrate guarantees:

- Genesis attestations cannot be `withdraw`n by the original signer.
- Genesis attestations cannot be counter-attested by the original signer (others may, but their counter is itself part of the chain).
- A `withdraw` observation on a genesis attestation is rejected at the relay-substrate level: the relay refuses to propagate it. (Note: relays are not arbiters — they enforce protocol invariants, like a TCP stack enforces sequence numbers. The protocol has chosen to make genesis structurally permanent. This is policy in the spec, not policy in a server.)
- The first observation in a chain is always retrievable, even by adversarial clients, because it is at the root of the hash chain and removing it changes every CID downstream.

This is Swartz's amendment from Round 5: the dead vote, structurally. The genesis is the grave; it cannot be argued with.

---

## 13. UX: the accordion (Jared amendment)

Every claim that surfaces in a human-facing UI does so with a single sentence at the top. Below that sentence is a `▾` control. Opening it reveals:

```
LEVEL 0 — claim sentence
   ▾
LEVEL 1 — convergence state + attest_count + counter_count + divergence
   ▾
LEVEL 2 — the list of attestations and counter-attestations themselves
          (each with signer's handle and a believability bar from the
           viewer's own membrane)
   ▾
LEVEL 3 — for any selected attestation: input_cid, derivation_cid,
          output_cid, signed bytes, signature, attestation timestamp
   ▾
LEVEL 4 — the actual derivation script source (text/python/js/markdown)
          and a "run it yourself" button if the kind is automated
   ▾
LEVEL 5 — the packets and signatures of every step (peer-to-peer trace,
          when available)
```

The UI is a depth control, never a verdict. The viewer chooses how deep to look; the substrate guarantees that depth is always available.

For agents (Jared's note: "the client is your own agent"), the accordion is the API surface — agents drill programmatically using the same calls, refusing to assert a claim is true if their drill-down policy hasn't returned the required convergence state.

---

## 14. Worked example — a derivable claim runs the full lifecycle

Alice (`dot1:alice123…`) wants to publish the claim "The first 1MB of enwik8 has BPS 4.31 under deflate-9."

### Step 1 — input + derivation

Alice posts two blobs to blob-substrate:
- `input_cid = blob(enwik8[0:1MB])` → `b3:7e2d…`
- `derivation_cid = blob("pure_python_v0\n\ndef main(b):\n    import zlib\n    return f'{8*len(zlib.compress(b,9))/len(b):.4f}'.encode()")` → `b3:c901…`

### Step 2 — attest

Alice runs the derivation locally. Output bytes `b"4.3104"`. CID `b3:f44a…`. Alice signs:

```
Attestation {
  id: OBS-attest-20260518-100001,
  type: "attestation",
  claim_kind: "derivable",
  input_cid: "b3:7e2d…",
  derivation_cid: "b3:c901…",
  output_cid: "b3:f44a…",
  claim_text: "Deflate-9 on first 1MB of enwik8 → BPS ≈ 4.3104",
  attested_at: "2026-05-18T10:00:01Z",
  attested_by: "dot1:alice123…",
  ed25519_pub: "…",
  sig: "…",
}
```

Alice's membrane sees `single-attestation`. Bob, Carol, Dave have not seen it yet.

### Step 3 — independent rederivation

Bob's agent sees Alice's attestation on its DOTpost inbox. The agent's local policy says "any claim_kind:derivable from a known contact, rederive automatically if the derivation is `pure_python_v0`."

Bob's agent fetches both CIDs (Gate 1), runs the script (Gate 2), gets `b"4.3104"`, hashes to `b3:f44a…`, matches. Bob's agent posts:

```
Attestation {
  id: OBS-attest-20260518-100530,
  ... same input/derivation/output CIDs ...
  cites: [OBS-attest-20260518-100001],
  attested_by: "dot1:bob456…",
}
```

Alice's membrane now sees `attest_count=2`. Bob's membrane also sees `attest_count=2` (his own + Alice's). Neither needs to ask the other; they read the chain.

### Step 4 — adversarial signer

Mallory (`dot1:mallory789…`, key has been quietly leaked) signs a counter-attestation claiming the output is `b3:DEAD…` (`b"5.9999"`). She does not run the script — she just signs.

Carol receives both attestations. Her agent reruns Gate 2, gets `b3:f44a…`, matches Alice & Bob. Carol's agent posts a counter to Mallory's counter:

```
CounterAttestation {
  id: OBS-attest-20260518-110015,
  ... contradicts: <Mallory's obs-id> ...
  reason: "rederivation_diverged",
  counter_output_cid: "b3:f44a…",
  attested_by: "dot1:carol789…",
}
```

In Carol's local membrane, Mallory's `compromise` score rises. In Alice's local membrane, Mallory is outside her contacts entirely and barely registers. In Mallory's-own-cluster membrane, the divergence appears immediately, prompting their own rederivations.

### Step 5 — the chain after 30 days

- 12 independent rederivations agree with Alice; 0 trusted counter-attestations.
- The claim is `settled` for any viewer whose membrane reaches at least 3 of those 12.
- Mallory's counter remains in the chain, visible at LEVEL 2 of the accordion. It is not deleted, not hidden, not centrally flagged. It just stops contributing to anyone's score because every viewer's membrane reads its `compromise` weight as high.
- Mallory cannot recover that key. She mints a new identity if she wants to participate honestly. The dead-key chain is preserved (Swartz).

No one judged. The substrate ran.

---

## 15. Worked example — a testimonial claim cannot become "settled"

Alice posts: "I met Bob in Helsinki on 2026-05-10 and he said the v3 protocol launch was delayed by a security review."

```
Attestation {
  claim_kind: "testimonial",
  derivation_cid: "ATT-TESTIMONY-V0",   // the canonical "human report" CID
  input_cid:      "ATT-TESTIMONY-INPUT-NONE",
  output_cid:     blake3(claim_text),
  ...
}
```

The membrane sees this as testimony. Even if 100 people sign attestations agreeing with Alice, the substrate UI shows `single-attestation: testimony` until *Bob himself* attests the same testimony with his own observation chain or until independent corroborating evidence is attached as cited attestations.

Bob can publish: "I confirm I said this at this time" — signed by his key. Now there are two attestations from disjoint signers. The accordion now shows the claim as `settled` for any viewer who trusts both signers. The claim is not "true" — it is "two independent attestations from disjoint signers" — and the substrate refuses to call it anything stronger.

This is the protocol's epistemic floor. Testimony cannot become certainty. The substrate exposes the gap honestly.

---

## 16. Failure modes

| Failure | Substrate response |
|---|---|
| Signer's key is compromised, attacker signs many false attestations | Each false attestation is counter-attested by independent rederivation; compromise weight rises in every membrane that observes the divergence; new attestations from that key carry less weight until rotation. |
| All signers in a cluster collude on a false derivable claim | Independence bonus (§10.7) reduces their joint signal; readers in disjoint neighborhoods who rerun the derivation will counter-attest; for derivable claims, the math always eventually wins. For testimonial claims, this attack succeeds inside the cluster's bubble — but never globally, because membrane is local. |
| Derivation script is malicious (tries to break out of sandbox) | Gate 1 / 2 sandboxing rejects; readers post `derivation_invalid` counter-attestations; the script's CID becomes a known-bad reference that membranes downweight automatically. |
| Genesis is wrong | Cannot be withdrawn by signer. Independent attestations and counter-attestations accumulate on top. The genesis remains visible; the chain's history of corrections is the record. (The protocol cannot fix a wrong starting point; it can fully expose it.) |
| Relay refuses to forward a counter-attestation | The counter-signer broadcasts via every other relay they're peered with; the censoring relay's local membrane weight drops as their behavior diverges from others. (Same shape as `feedback_dotpost_canonical`'s answer to mesh-relay censorship.) |
| Sybil cluster signs many attestations | Independence bonus + handle-substrate squatting limits + each viewer's contact graph all bound the impact. Sybils cannot enter a viewer's membrane without being explicitly added as contacts. |

---

## 17. Test vectors (v0.1)

### 17.1 Canonical bytes example

Given:
```
type: derivable
input_cid: b3:7e2d8f93
derivation_cid: b3:c9015e21
output_cid: b3:f44a1234
attested_at: 2026-05-18T10:00:01.000Z
attested_by: dot1:alice123abc4567
cites: []
conditions: {}
claim_text: "Deflate-9 on first 1MB of enwik8 → BPS ≈ 4.3104"
```

Canonical bytes (LF-separated, no trailing newline):

```
attestation-v0.1
type:derivable
input:b3:7e2d8f93
derivation:b3:c9015e21
output:b3:f44a1234
attested_at:2026-05-18T10:00:01.000Z
attested_by:dot1:alice123abc4567
cites:[]
conditions:{}
claim_text_sha256:<hex of sha256 of the claim_text utf-8 bytes>
```

### 17.2 Believability sanity case

Three independent peers each post a confirming `pure_python_v0` attestation from disjoint contact neighborhoods. Default policy. Viewer is in contact with one of them.

Expected: `attest_count=3`, `counter_count=0`, `divergence=0`, `state=settled`, score-component bar at maximum confidence visualisation, drill-down available.

### 17.3 Compromise case

A key signs 5 derivable attestations in 24h. All 5 are counter-attested by ≥3 disjoint independent rederivations within 7 days. Default policy.

Expected: the signer's `compromise` weight in the viewer's membrane crosses 0.3, and the signer's `trust` multiplier drops to ~0.5× its prior value for all *future* attestations until that pattern reverses. Past genuine attestations are not retroactively diminished.

---

## 18. Relationship to other substrates

| Substrate | How it interacts |
|---|---|
| `handle-substrate` | Provides the identity floor. `attested_by` resolves through it. Compromise downweight is per-key, not per-handle — a handle that rotates keys can recover. |
| `blob-substrate` | Hosts `input_cid`, `derivation_cid`, `output_cid`. Provides content-addressing for everything reproducible. |
| `intent-substrate` | Carries attestations on the wire (signed-then-compressed). No new transport. |
| `coordination-substrate` | A task's `complete` observation may cite an attestation as its proof of completion; readers' agents drill in to verify before treating it as done. |
| `constitution-v0.1` | The constitution's `feedback_verify_before_quoting` rule is the human shape. This substrate is the protocol shape. They reference each other. |
| `single-use-covenant-v0.1` | A single-use covenant may require a fresh attestation chain (≥N independent rederivations) before triggering. The covenant becomes verifiable without trusting any one signer. |

---

## 19. Open questions for the next room

These do not block v0.1, but the next round should answer them:

1. **Default `τ` and trust constants.** The numbers in §10 are starting points; production deployments will need to tune. Should we ship policy presets (`policy:strict`, `policy:lenient`)?
2. **Multi-key signing.** Should an attestation be co-signable by multiple peers in one observation (Gate 2 batching), or strictly one-signer-per-observation? v0.1 is one-per-observation for simplicity. A future v0.2 might add batched co-signing.
3. **Counter-attestation of testimonials.** §15 caps testimonial claims at single-attestation. Is that too strict — should two independent eye-witnesses of the same event lift the cap?
4. **Reputation portability.** When a handle rotates its key (handle-substrate §11), should its prior-key attestation track record port to the new key? v0.1 says no (clean slate). A v0.2 with portable reputation under signed migration may be desirable.
5. **Replay attacks on counter-attestations.** An attacker spams counter-attestations to inflate `divergence`. The independence bonus mitigates within a viewer's neighborhood, but should there be a protocol-level rate limit on counter-attestations per signer-per-window?
6. **UI default depth.** What level of the accordion should be visible by default (§13)? Showing too much fatigues. Showing too little re-imports the judge.
7. **Compromise recovery path.** §11.5 says "rotate and rebuild." Is there a useful "amnesty" mechanism (a public confession that lets a recovered key get partial trust back faster), or does that just open a social-engineering vector?

The room should answer at least the first three before v0.2.

---

## 20. Version semantics

This is v0.1. The shape locked here is:

- Attestation canonical form (§6)
- Tag prefix `type:attestation` (§5)
- Reasons vocabulary (§9)
- Three derivation kinds (§4.3, §7)
- Believability membrane is *local* (§10) — never global

Backwards-incompatible changes mint v0.2 with a new canonical-form header (`attestation-v0.2`); v0.1 signatures remain valid forever. Forward-compatible additions (more reasons, more derivation kinds) extend v0.1 in place.

A v0.2 should be considered when ≥3 of the open questions in §19 have been answered, or when an in-production deployment surfaces a structural inadequacy not solvable inside v0.1.

---

## Provenance of this spec

This document is itself an attestation candidate. After ratification by the room, it will be:

1. Stored as a `blob-substrate` blob; CID minted.
2. Signed by every voice present in Round 5 (Jared, Kempf, Gutenberg, Ostrom, Swartz, Dalio) and by the observer.
3. Posted as a genesis-tier attestation in the `dotilluminati` chain at `axxis.world/illuminati`.
4. Mirrored on the IPFS layer of blob-substrate.

The accordion for *this spec* will drill from "no central arbiter of truth, here's why" → the round transcript → the signed observation IDs → the canonical bytes → the actual git commit that landed this file in `pipernet/spec/`.

Recursion is the point. The substrate that defines truth-attestation is itself published using the protocol it defines. If it cannot withstand its own scrutiny, the spec fails honestly.

The Ministry of Truth never gets installed because the room published its own minutes, signed, append-only, drillable to packet — and you, reading this, can rerun every step. *That* is the inversion completed.

— Round 5, signal `OBS-axxis-20260517-2125`, build `msg-42fdfe80`, written in the open under `dotilluminati`.
