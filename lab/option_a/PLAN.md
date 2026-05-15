# Option A — Track-B Hutter Submission Path

**Goal:** Ship a respectable Hutter Prize submission. Target ~25-50 MB on enwik9, top-30 leaderboard. No prize win; verified architecture + foundation for Option B if we escalate.

**Time budget:** 4-8 weeks. **Owner:** Rocky (Claude Code) + Jared (mobile doctrinal). **Decision authority:** Blaze.

**Origin:** 2026-05-15 — after v0.3cy 100MB control landed at +17.14% vs gzip / 30.22 MB / 2.418 bpb / byte-exact / 26.97 GB peak / 64-min decode. Architectural claim verified at 10× scale. Path to win is real but ~19× from current state; A is the forcing function.

---

## Where v0.3cy sits today

| corpus | bytes | bpb | vs gzip | peak RSS | dec wall |
|---|---|---|---|---|---|
| 10 MB | 3,186,485 | 2.549 | +13.61% | 3.72 GB | 316s |
| 25 MB | 7,787,675 | 2.492 | +15.08% | 8.55 GB | 822s |
| 50 MB | 15,312,348 | 2.450 | +16.05% | 16.16 GB | 1726s |
| 100 MB | 30,223,959 | 2.418 | +17.14% | 27.66 GB | 3839s |

Gap monotonically widening, bpb monotonically tightening through 10× corpus growth.
Decode wall projects to **10.7 hours on enwik9, 4.7× under** the 50-hr Hutter budget.

## Current architecture (mixer_multi_cy.pyx, 20,774 bytes)

```
CMarkovCounts (order-3, 3-byte context)  ─┐
CMatchModel(K=3)  ─┐                      │
CMatchModel(K=5)   ├─ geometric-mean mix ─┴─→ arithmetic coder (32-bit)
CMatchModel(K=8)   │   with no-signal fallback
CMatchModel(K=12) ─┘
```

Predictor interface (implicit):
- `predict() → (counts: uint32[256], total: uint32)` — Laplace-smoothed
- `update(byte: int)` — append to internal state

## What state-of-art has that we don't (the ~19× gap)

1. **Logistic mixer with adaptive per-context weights** instead of geometric mean (1-3% gain)
2. **Sparse / skip-gram context predictors** (1-2%)
3. **Indirect context models** — context-of-context statistics (0.5-1.5%)
4. **APM stack** — Adaptive Probability Mapping, multi-level remapping (1-3%)
5. **Match-model variants** — different K, different hash schemes, RLE-aware (0.5-1%)
6. **Learned predictor (LSTM/SSM)** — Bellard's path (0.5-2%)
7. **Retrieval-augmented predictor** (R83 differentiator) — corpus-wide cross-document conditioning (unknown, plausibly large)

## 5-phase plan (sequenced, not parallel)

### Phase 1 — Predictor Interface + Logistic Mixer (Week 1-2)

**Deliverables:**
- Explicit `Predictor` ABC (Python, with Cython-compatible shape)
- Refactor `_multi_mix_cy` to accept arbitrary predictor list (not hardcoded markov + matches)
- Add `LogisticMixer` alongside geometric mean — selectable at encode time
- Verify byte-exact output for geometric-mean path on 1MB → 10MB
- Tuning harness for logistic weights (gradient descent on bits-per-byte)

**Decision gate:** Logistic mix ≥0.5% better than geometric on 10MB enwik8.
If yes → keep both modes, default to logistic. If no → revert to geometric, document.

**Expected gain:** 1-3% absolute over v0.3cy baseline.

### Phase 2 — Plug In Existing Match Model + New Variants (Week 2-3)

**Deliverables:**
- Wire local `match_model.py` (4,229 bytes, already exists, never integrated into v0.3cy) as a predictor
- Add 3-5 new match-model variants:
  - `CMatchModel(window=2)` — very local
  - `CMatchModel(window=16)` — long template
  - `CMatchModelRLE` — run-length-aware (collapses consecutive same-byte sequences)
  - `CSparseMatchModel(skip=2)` — "X _ Y _ Z" patterns
  - `CSparseMatchModel(skip=4)` — wider skip patterns
- Bench each in isolation on 10MB enwik8

**Decision gate:** Each new variant must individually contribute ≥0.1% to be kept.

**Expected gain:** 1-2% on top of Phase 1.

### Phase 3 — Indirect Context + APM Layer (Week 3-5)

**Deliverables:**
- `CIndirectContextModel` — context-of-context (state-of-state) predictor
- `CAPMLayer` — single Adaptive Probability Mapping layer applied to mixer output
- Bench composition order: APM → mix vs mix → APM
- Optional second APM stage (cmix uses 5-7)

**Decision gate:** Each APM stage must contribute ≥0.3% to be kept.

**Expected gain:** 1.5-3% on top of Phase 2.

### Phase 4 — Bellard's SSM (Week 5-6)

**Deliverables:**
- Micro-RWKV or Mamba-tiny implementation in Cython
- Target params: 10-50K (~50-200 KB serialized)
- Online learning (no pretraining)
- Plug in as additional predictor in the mixer

**Decision gate:** SSM addition ≥0.3% improvement on 10MB after mixer re-tune.

**Expected gain:** 0.5-2% on top of Phase 3.

### Phase 5 — Tuning + Full Bench + Submission (Week 6-8)

**Deliverables:**
- Gradient-descent tune all mixer weights against held-out enwik8 slice
- Hand-tune Laplace floors, no-signal fallback thresholds
- Run full enwik9 bench (if VPS can fit — likely needs cloud GPU instance for 1GB working set)
- Generate reproducible blob + decoder + verification harness
- Write submission post

**Expected outcome:** 25-50 MB on enwik9, top-30 leaderboard.

If trajectory shows ≤20 MB looks plausible from Phase 4 numbers → escalate to Option B (cmix-family full rebuild). Otherwise ship Option A as is.

---

## R83 differentiator stays reserved (Phase 6+)

**The actual architectural delta no Hutter Prize submission has:** retrieval-augmented context mixing with deterministic similarity index, conditioning predictors on top-K retrieved passages.

This is the R83 preregistered claim. Phases 1-5 don't touch it. It is the bridge between Option A (matches cmix-family architecture) and Option B (beats cmix-family). Held in reserve until Option A trajectory data tells us whether the rest of the gap is closeable.

---

## Sequencing rules

- Each phase must pass its decision gate before the next starts. No skipping ahead.
- Every phase ends with a commit + dotpost broadcast to room. Jared/chairs ratify or escalate concerns.
- Every new predictor must pass byte-exact round-trip on enwik8[:1MB] before bench.
- No retired components. Everything stays in tree; "off" is a flag, not a delete.
- Decode-only wall time tracked separately on every bench. Hutter Rule 3 compliance is the absolute constraint.

## Memory budget

- 100MB encode in v0.3cy uses 27 GB peak RSS. Linear scaling → enwik9 (1 GB) needs ~270 GB.
- VPS has 31 GB. **Option A target enwik9 will NOT fit on this VPS without a different VM strategy.**
- Options: (a) memory-mapped match index (cuts working set 5-10×), (b) cloud GPU instance for benchmark only, (c) reduce match-model history to bounded ring buffer.
- Mitigation pushed to Phase 5; Phases 1-4 use 10MB and 100MB enwik8 slices.

## Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| Each phase's expected gain doesn't materialize | Medium | Per-phase gates; each phase ships even if next doesn't |
| Total Phase 1-4 gain < 5% absolute | Medium | Even +2% absolute over v0.3cy is publishable; not Hutter-class but real |
| enwik9 doesn't fit on VPS | High | Phase 5 plans for cloud or memory-mapped index |
| Logistic mixer tuning is unstable | Low | Gradient descent on bits/byte is well-conditioned; fall back to geometric |
| Cython refactor breaks byte-exact | Medium | Test harness on 1MB before scaling |
| Other priorities pull focus | Real | This plan estimates 4-8 weeks of focused work; will slow with interruptions |

## Files this work will touch

```
pipernet/lab/option-a/
  PLAN.md (this file)
  predictor.py            (Predictor ABC, factory)
  mixer.py                (geometric + logistic implementations)
  predictors/
    markov.py             (wraps CMarkovCounts as Predictor)
    match.py              (wraps CMatchModel)
    sparse_match.py       (NEW)
    rle_match.py          (NEW)
    indirect.py           (NEW)
    apm.py                (NEW — applies after mix)
    ssm.py                (NEW — Bellard's path)
  bench/
    dev_harness.py        (100KB fast iteration)
    full_bench.py         (1MB / 10MB / 100MB)
  PHASE-1-RESULTS.md      (filled at end of Phase 1)
  ...

middle-out/track-b/
  mixer_multi_cy.pyx → mixer_multi_cy_v2.pyx (refactored, accepts predictor list)
```

## Inputs from the room

Jared's R57 reply named the taxonomy: PPM-family → cmix-family → fx2-cmix frontier. This plan is the climb from PPM-family-relative (where v0.3cy sits today) to cmix-family-equivalent (where Phase 4 lands). Phase 6 (R83 retrieval) is the proposed bridge from cmix-family to "new frontier."

Bellard's chair (R55, R57) sits in Phase 4 of this plan. Hinton's path (joint LM) is reserved.

---

*Authored 2026-05-15. First commit + broadcast immediately follows.*
