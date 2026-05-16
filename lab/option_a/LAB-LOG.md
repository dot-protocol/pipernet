# Track-B Option A — Lab Notebook

**Format:** Append-only. Newest entry on top. Each experiment self-contained:
hypothesis → method → result → verdict → artefacts. Null results are kept.
NEVER delete or rewrite history. Update *next* entry to reflect new understanding.

**Baseline state at log open (2026-05-16):**
- Architecture: 5 predictors (Markov, Match{3,5,8,12}) + geometric mixer + arithmetic coder
- v0.3cy parity: byte-exact between pure-Python `option_a/` and Cython `mixer_multi_cy`
- 100KB enwik8 with v0.3cy geometric mix: 37,502 bytes = 3.0002 bpb
- 100KB enwik8 with gzip-9: 36,239 bytes = 2.8991 bpb (track-B is +3.485% behind gzip)
- Hutter target on enwik9: 0.886 bpb (fx2-cmix, Oct 2024)
- Gap: track-B is ~3.4× away from Hutter record. Phase 2-5 plan exists in `RESEARCH-2026-05-16.md`.

---

## EXPT-003 — 2026-05-16 — Extended match windows (Match-16, Match-32)

**Hypothesis:** StateSMix (arXiv:2605.02904) reports 1-4% gain from long-range n-gram
tables at k=16, k=32 atop standard order-3 contexts. In track-B this maps cleanly
to adding `MatchPredictor(window=16)` and `MatchPredictor(window=32)` to the factory.
Expected gain: 1-2% on 100KB, larger on full enwik9 (more boilerplate).

**Method:** `expt_long_match.py 100000 1 0.05`. Two factories:
- 5-pred baseline: Markov + Match{3,5,8,12}
- 7-pred extended: 5-pred + Match{16,32}
Each factory tuned independently via online SGD (1 pass, lr_init=0.05).
Compare tuned-vs-tuned at 100KB enwik8.

**Result:**
| Config | Geometric (bytes) | Tuned (bytes) | bpb | vs gzip |
|---|---|---|---|---|
| 5-pred | 37,502 | 36,511 | 2.9209 | +0.751% |
| 7-pred | 37,284 | 36,388 | 2.9110 | +0.412% |
| **Δ (7−5)** | **−0.58%** | **−0.337%** | | |

Final weights (5-pred): `[0.63, 1.40, 0.99, 0.55, 2.03]`
Final weights (7-pred): `[0.63, 1.40, 0.99, 0.61, 1.27, 1.41, 0.99]`

**Verdict:** PARTIAL PASS. Gain is real (+0.337%) but below my 1% gate. The weight
diff reveals the mechanism: Match-12's weight dropped 2.03 → 1.27 when Match-16+32
joined — three long-context predictors are competing for the same signal.
Diminishing returns within the same architectural family.

**Decision:** Keep Match-16 in the default factory (weight 1.41 — meaningful).
Drop Match-32 from the default — weight 0.99 ≈ middle-of-pack, not earning its
encode cost. Try again on full enwik8 (100MB) once we have decode-budget headroom,
where 32-byte repetitions are more common.

**Artefacts:**
- `expt_long_match.py` — experiment harness
- Tuned 7-pred weights saved here, not yet shipped to default factory

---

## EXPT-002 — 2026-05-16 — AC precision upgrade (2^16 → 2^24)

**Hypothesis:** Nacrith (arXiv:2602.19626 §4) reports the single change of
arithmetic-coder cum_total precision from 2^16 → 2^24 eliminates ~75% of
quantisation overhead on large-vocab predictors, yielding 0.05-0.15 bpb free.
First-agent research called this "cheapest win, no decode penalty."

**Method:** Added `precision` parameter to `multi_mix_logistic`, default
`DEFAULT_AC_PRECISION = 1_000_000` (v0.3cy baseline), opt-in
`HIGH_AC_PRECISION = 16_777_216` (2^24). Run tuner on 100KB enwik8, A/B
final-encode pass at both precisions.

**Result:**
| Precision | Bytes | bpb | vs geometric |
|---|---|---|---|
| 1e6 (default) | 36,511 | 2.9209 | −2.643% |
| 2^24 (HP) | 36,511 | 2.9209 | −2.643% |
| **Δ** | **0 bytes** | **0** | **0%** |

**Verdict:** NULL RESULT. Zero gain on track-B.

**Why:** Nacrith's claim was for LM-based codecs where the predictor emits
very small probabilities (1e-6 to 1e-8 range) for rare tokens. Track-B with
5 predictors + Laplace floor of 256 cannot output probabilities below ~1/256.
After geometric/logistic mix, min p stays well above 1/1e6, so the quantisation
ceiling of 1e6 is not the binding constraint. Precision upgrade is correct in
the abstract — wrong architecture context to benefit here.

**Decision:** Keep `precision` parameter wired (it costs nothing) for future
phases where bit-level predictors and lower Laplace smoothing might exploit
the finer grid. Don't change default.

**Artefacts:**
- `option_a/mixer.py` now has `DEFAULT_AC_PRECISION` and `HIGH_AC_PRECISION`
  constants and validates `precision ∈ [256, 2^30]` (AC safe range)
- `option_a/tuner.py` runs section [4a] at default and [4b] at HP

**Reference:** [Nacrith arXiv:2602.19626](https://arxiv.org/abs/2602.19626)

---

## EXPT-001 — 2026-05-16 — Phase 1 Decision Gate: adaptive logistic vs geometric

**Hypothesis:** Replacing the geometric-mean mixer with logistic-style log-domain
weighted sum, with per-predictor weights learned online via SGD on negative
log-likelihood, will beat geometric by ≥0.5% (Phase 1 gate target).

**Method:** `tune_weights(data, num_passes=1, lr_init=0.05, lr_decay=0.9999)`.
Per-byte gradient: `∂L/∂w_j = E_{x~P_mix}[log p_j(x)] - log p_j(true)`.
SGD step: `w -= lr * gradient`, weight clip ±5.0, lr decay 0.9999 per byte.
Evaluated on 10KB and 100KB enwik8.

**Result:**
| Slice | Geometric | Tuned logistic | Delta |
|---|---|---|---|
| 10KB | 4,456 bytes (3.5648 bpb) | 4,215 bytes (3.3720 bpb) | **−5.408%** |
| 100KB | 37,502 bytes (3.0002 bpb) | 36,511 bytes (2.9209 bpb) | **−2.643%** |

Final learned weights (100KB):
- Markov(o3): 0.630
- Match(K=3): 1.401
- Match(K=5): 0.995
- Match(K=8): 0.550   ← weakest
- Match(K=12): 2.035  ← strongest

The optimizer learned the right predictor hierarchy: deepest context (K=12)
dominates, K=8 is redundant given K=5+K=12, Markov is useful but not dominant.

**Verdict:** PASS (5x target on 10KB, 5x target on 100KB). Switch default mixer
to logistic for Phase 2+. Ship tuned weights as default starting point.

**Decision:** Phase 1 closes. Phase 2 starts with priorities revised per
`RESEARCH-2026-05-16.md`: WRT preprocessing > bit-level refactor >
indirect contexts + nonstationary state map > APM/SSE.

**Artefacts:**
- `option_a/tuner.py` — adaptive weight learner + decision-gate harness
- `option_a/bench_dev.py` — sub-10s 100KB dev iteration harness
- Tuned weights `[0.630, 1.401, 0.995, 0.550, 2.035]` not yet shipped to default

---

## Format note (read on every append)

1. **Append on top.** Newest entry at line ~10, old entries pushed down.
2. **Never delete or rewrite.** If a result changes, write a new EXPT-### that
   cites the prior one and explains what changed.
3. **Null results are mandatory entries.** A 0% experiment is as valuable as a
   PASS — it documents that the path was explored.
4. **Hypothesis precedes method precedes result.** Discipline against
   retrofitting reasoning.
5. **Decision and artefacts always present.** Decision = what we ship next;
   artefacts = the files this experiment created/modified.
6. **Cite sources** with arxiv/github URLs when the hypothesis came from
   external work.
