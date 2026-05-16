# Track-B Option A — Lab Notebook

**Format:** Append-only. Newest entry on top. Each experiment self-contained:
hypothesis → method → result → verdict → artefacts. Null results are kept.
NEVER delete or rewrite history. Update *next* entry to reflect new understanding.

## EXPT-019 — 2026-05-16 — WRT preprocessing → bit-level mix — 100KB null, 1MB pending

**Hypothesis:** EXPT-004/005 earlier today showed WRT preprocessing was a
null on the BYTE-level Phase 1 codec — byte-level predictors can't model
WRT escape codes (look like noise to Markov / match models). With bit-level
+ multi-Indirect + tuner, the Indirect maps re-learn distributions from
scratch — they may handle WRT-encoded byte streams better.

**Method:** `expt_wrt_bit.py` — build WRT dictionary (315 entries: 59
single-byte codes + 256 two-byte prefix), encode `wrt(data)` with the
EXPT-012 baseline stack (4 children + tuner), compare vs raw bit-mix encode.
Honest accounting includes dictionary overhead (~2.6 KB serialized).

**Result on 100KB enwik8:**

| Path | Bytes (excl dict) | + dict | vs raw |
|---|---|---|---|
| raw (no WRT) | 30,926 | — | baseline |
| WRT → bit-mix | 30,065 | 32,725 | **+5.8% worse** with dict overhead |

WRT preprocessing reduced input from 100,000 → 75,417 bytes (−24.6%). The
bit-mix then compressed it to 30,065 bytes — slightly more compact than
raw at 30,926. BUT the dictionary overhead (2,660 bytes) wipes out the gain.

**Important shift from EXPT-004/005:** previously WRT-encoded bytes COULDN'T
be compressed well by the byte-level Phase 1 codec (escape codes were
adversarial). NOW the bit-level multi-Indirect handles WRT bytes acceptably —
the per-context state machines re-learn whatever byte distribution is
presented. So WRT is no longer architecturally hostile to track-b.

**Verdict on 100KB: NULL.** The dictionary overhead is a 2.6%-of-corpus
fixed cost at this scale. Amortized over 1MB it's 0.26%; over 100MB it's
0.0026%. So the result reverses with scale.

**1MB pending — will amend when Monitor fires.** Expected: WRT wins by
~1-2% at 1MB once overhead becomes negligible.

**Artefacts:**
- `option_a/expt_wrt_bit.py` (140 LOC)
- Reuses `option_a/wrt.py` from EXPT-004 (built 315-entry dictionary)

**References:**
- Skibinski "Word Replacement Transform" original
- Earlier EXPT-004/005 entries below for the byte-level null context

---

## EXPT-018 — 2026-05-16 — Bigger Indirect maps — IN FLIGHT

**Hypothesis:** EXPT-009 found 1<<24 (16 MB) beat 1<<22 (4 MB) on 100KB.
At 1MB each slot in a 1<<24 map gets ~0.5 updates — collisions still common.
Going to 1<<26 (64 MB), 1<<27 (128 MB) should reduce collisions further.
Diminishing returns expected; null possible (collisions are noise the
state machine + EMA already smooth out).

**Method:** `expt_big_maps.py` — sweep map_size_bits ∈ {24, 25, 26, 27} for
the hist=3 Indirect in the EXPT-014 baseline stack. Hist=2 / hist=1 stay at
1<<22 / 1<<20 (fixed). Tune weights then encode.

**Result on 1MB:** in flight; Monitor armed.

**Memory cost:** at 1<<27 = 128 MB per single Indirect. Four-children stack
at this size = ~150+ MB of map memory. Mac has 32 GB — fine. VPS at 31 GB
also fine. Cython port wouldn't need to inflate.

**Artefacts:**
- `option_a/expt_big_maps.py` (130 LOC)

---

## EXPT-016 — 2026-05-16 — SSE as a SIBLING predictor — REDUX OF EXPT-013, WINS

**Hypothesis:** EXPT-013 tried SSE as a POST-MIX wrapper → +2-6% WORSE than
baseline. The wrapper forces a remap whether useful or not. The PAQ pattern
is to use SSE as an ADDITIONAL CHILD in the mix; the tuner then assigns it
a weight. If SSE adds signal, weight is high; if not, weight is near zero.

**Method:** `expt_sse_sibling.py` — `SSEPredictor` wraps a FRESH
`BytewiseBitPredictor` over Phase 1 and applies an SSE remap (2048 contexts
keyed on bit_pos × last_byte). This SSE-wrapped predictor goes into the
MultiBitPredictor as a 5th child alongside the existing 4. Tune all 5
weights, then encode.

**Result on 100KB enwik8:**

| Stack | Bytes | bpb | vs gzip-9 | vs baseline |
|---|---|---|---|---|
| baseline (4 children, no SSE) | 30,926 | 2.4741 | −14.66% | — |
| **+ SSE-sibling (5 children)** | **30,418** | **2.4334** | **−16.06%** | **−1.64%** |

Tuned weights for 5-child stack: `[0.246, 0.174, 0.181, 0.139, 0.4]`.
The SSE-sibling got the HIGHEST weight (0.4) in the stack — even higher
than Phase 1 (0.246). The tuner rebalanced Phase 1 down because the
SSE-sibling already wraps Phase 1's signal in remapped form. Net: SSE adds
~1.6% by capturing a NON-LINEAR calibration of Phase 1's bit predictions
that the linear logit mix can't.

All variants byte-exact roundtrip ✓.

**Verdict: WORKS as sibling, was wrong as wrapper.** This is the EXPT-013
salvage: SSE has signal, but the architecture must let the tuner choose
how much. The wrapper-form pre-decides. The sibling-form discovers.

**1MB pending** — Monitor armed. Expected: similar ~1-2% gain over EXPT-012
baseline at 1MB, since the per-context SSE table populates faster on 1MB.

**Artefacts:**
- `option_a/expt_sse_sibling.py` (140 LOC): SSEPredictor class + harness
- Reuses `option_a/apm.py` SSEModel from EXPT-013

**References:**
- EXPT-013 above (the wrapper-form null that prompted this rework)
- PAQ8 APM-as-additional-predictor pattern

---

## EXPT-013 — 2026-05-16 — APM/SSE final-stage remap — NULL RESULT (v0)

**Hypothesis:** Eugene Shelwien's APM/SSE (per-context 7-bin probability
remap, ~60 LOC) chains AFTER the bit-level mix and BEFORE the arithmetic
coder. fx2-cmix uses several SSE stages. On top of the EXPT-012 tuned
baseline this should give +1-2%.

**Method:** `apm.py` — `SSEModel` (7 bins × n_contexts table, stretch-based
quantization, EMA update on adjacent bins per bit observation) wrapped via
`SSEWrappedBitPredictor`. Two context schemes:
  a) `_ctx_by_bit_position`         — 8 slots (one per bit position k)
  b) `_ctx_by_bit_position_x_lastbyte` — 2048 slots (last byte × bit position)

Initial table = identity remap (bin i value = sigmoid(stretch_pos_i)) so
the SSE is a no-op on the first bit, then deviates as EMA learns. This is
the standard PAQ/cmix init — getting it wrong distorts the first thousands
of bits before EMA recovers.

**Result on 100KB enwik8:**

| Stack | Bytes | bpb | vs gzip-9 | vs EXPT-012 |
|---|---|---|---|---|
| EXPT-012 baseline (tuned mix, no SSE) | 30,926 | 2.4741 | −14.66% | — |
| EXPT-013a (8-ctx SSE wrap) | 32,656 | 2.6125 | −9.89% | **+5.59%** |
| EXPT-013b (2048-ctx SSE wrap) | 31,810 | 2.5448 | −12.22% | **+2.86%** |

All variants byte-exact roundtrip ✓.

**Verdict: NULL (v0).** Both SSE variants are WORSE than the baseline:
+5.59% for the 8-context coarse version, +2.86% for the 2048-context fine
version. Adding SSE on top of the SGD-tuned mix hurts.

**Why this null:**
1. The SGD-tuned mix is already very well-calibrated; SSE has nothing to
   correct. Adding a learned remap introduces noise during the warmup
   period (first many thousand bits) that the final EMA doesn't fully
   recover from.
2. 8 context slots is too coarse — the SSE learns one remap for all of
   bit-position k's predictions, regardless of underlying context.
3. 2048 slots is closer but still bound by SSE running cold over 100KB:
   ~50 updates per slot is too few for the EMA to find anything useful.

**Two v1 paths to try:**
1. **SSE as a SIBLING predictor** in the MultiBitPredictor stack, NOT as a
   wrapper. Let the SGD tuner learn its weight. PAQ uses APMs this way —
   they're another signal, not a final remap. The tuner can down-weight
   them to ~0 if they're not helping.
2. **Chain SSEs** before the mix on each individual predictor's output —
   each predictor gets its own SSE remap to "calibrate" its raw output
   before mixing. Could help especially for Indirect, whose state-machine
   predictions are coarse and benefit from EMA smoothing.

For now: EXPT-013 logged as a null, move to higher-EV moves
(more predictor families, Cython port, WRT preprocessing).

**Artefacts:**
- `option_a/apm.py` (140 LOC): SSEModel + SSEWrappedBitPredictor
- `option_a/expt_apm.py` (130 LOC): harness comparing baseline vs 2 SSE schemes

**References:**
- https://encode.ru/threads/2515-mod_ppmd (Shelwien's original)
- `lab/fx2-cmix/src/mixer/sse.cpp` (328 LOC C++ reference)

---

## EXPT-012 — 2026-05-16 — Online weight tuner for bit-level mix — TUNER >> HAND-PICKED

**Hypothesis:** EXPT-010 and EXPT-011 showed the bit-level mix's compressed
size is very sensitive to weight choice (e.g., (0.9, 0.25) beats (1.0, 0.25)
by 0.7-2.3% at 1MB). Hand-tuning at one scale doesn't necessarily transfer
to another. The byte-level mixer (Phase 1) uses online SGD on per-byte
gradients to learn its weights; the same pattern should work at bit-level,
with a CLEANER gradient: per-bit cross-entropy is a single sigmoid loss.

If online tuning works, it should match or beat hand-picked weights at every
scale, and adapt automatically when we add new predictors.

**Method:** `bit_tuner.py` — `tune_bit_weights(data, children_factory, ...)`:
  Forward (per bit):
    logit_i = log(p_i / (1 - p_i))
    s       = Σ w_i · logit_i
    final_p = sigmoid(s)
  Loss (bit y ∈ {0, 1}):
    L       = -y · log(final_p) - (1-y) · log(1 - final_p)
  Gradient:
    dL/dw_i = (final_p - y) · logit_i
  Update:
    w_i -= lr · (final_p - y) · logit_i      [clipped to ±5]

EXPT-012 harness `expt_bit_tuner.py`:
  Stack: BytewiseBitPredictor(Phase 1) + 3 IndirectBitPredictors
         (hist=3 / 1<<24, hist=2 / 1<<22, hist=1 / 1<<20)
  Initial weights: [0.9, 0.20, 0.12, 0.08]   (EXPT-011 hand-picked best)
  Tuner: lr_init=0.01, lr_decay=0.99999, weight_clip=5.0, 1 pass.
  Encode with tuned weights on fresh predictors; report vs initial.

**Result on 5KB enwik8 (smoke):**
  Initial (0.9, 0.20, 0.12, 0.08):  1,568 bytes (+4.19% vs gzip)
  Tuned   (0.81, 0.10, 0.40, 0.40): 1,500 bytes (−0.33% vs gzip)
  Improvement: −4.34%; tuner already beats gzip on 5KB.

**Result on 100KB enwik8:**

| Stack | Bytes | bpb | vs gzip-9 |
|---|---|---|---|
| gzip-9 | 36,239 | 2.8991 | — |
| EXPT-011 best (3 Ind, hand) | 32,427 | 2.5942 | −10.52% |
| **EXPT-012 (3 Ind, TUNED)** | **30,926** | **2.4741** | **−14.66%** |

Tuned weights: `[0.489, 0.199, 0.211, 0.195]` — Phase 1 down-weighted (0.9 → 0.49),
Indirect 3/2/1 all converging to ~0.2 (vs my hand-descending hierarchy 0.20/0.12/0.08).

**Result on 1MB enwik8:**

| Stack | Bytes | bpb | vs gzip-9 |
|---|---|---|---|
| gzip-9 | 355,791 | 2.8463 | — |
| EXPT-011 best (3 Ind, hand) | 299,802 | 2.3984 | −15.74% |
| **EXPT-012 (3 Ind, TUNED)** | **275,933** | **2.2075** | **−22.45%** |

Tuned weights at 1MB: `[0.4888, 0.1983, 0.2103, 0.1954]` — essentially
identical to the 100KB tuned weights `[0.489, 0.199, 0.211, 0.195]`.
The SGD optimum is scale-invariant once enough data is observed (8M bits
at 1MB; 800K bits at 100KB — both converge to the same point).

Tuning cost: 125.5s (one pass over 1MB at lr_init=0.01).
Tune-time online-learning bpb: 2.2060 (matches the encode bpb 2.2075 within
quantization noise — tuner correctly predicts the encode result).

Improvement over hand-picked at 1MB: −7.96% (23,869 bytes saved).

**All variants byte-exact roundtrip ✓.**

**Verdict: AUTO-TUNING WORKS.** 4.6% improvement on top of hand-picked
optimum at 100KB. Online SGD finds genuinely different optima than human
hand-tuning — it discovers Phase 1 should be DOWN-weighted to leave room
for the three Indirect signals which contribute equally rather than
hierarchically.

This is the cleanest infrastructure win of the day. From here on, every
new predictor we add automatically gets its weight learned without
hand-sweeping. EXPT-013 (APM/SSE) and EXPT-014 (sparse contexts) become
near-trivial dispatches: add predictor to factory, rerun tuner.

**What's next:**
- 1MB tuner result (in flight; will amend)
- EXPT-013: APM/SSE as a final bit-prob remap (Shelwien's 7-bin pattern)
- EXPT-014: sparse-context Indirect (skip n-grams: byte[-1], byte[-3] only)

**Artefacts:**
- `option_a/bit_tuner.py` (140 LOC): online SGD trainer
- `option_a/expt_bit_tuner.py` (130 LOC): tune→encode→roundtrip harness

**References:**
- Phase 1 byte-level tuner (`option_a/tuner.py`) — same pattern, byte-level math
- Mahoney "Adaptive Weighting of Context Models for Lossless Data Compression"
- PAQ8 logistic mixing reference implementation

---

## EXPT-011 — 2026-05-16 — Multi-Indirect ensemble (Phase 2D extension) — STACKING WINS

**Hypothesis:** EXPT-010 mixed Phase 1 with ONE Indirect predictor (hist=3,
map=1<<24). cmix/fx2-cmix uses MANY indirect models keyed on different
context shapes. Adding 2-3 more Indirects with different `hist` values
should capture orthogonal regularities (hist=1 sees Markov-1; hist=2 sees
byte pairs; hist=3 sees trigrams) and stack with the byte-level signal for
additional gain.

**Method:** `expt_multi_indirect.py` — 5 configurations:
  1. EXPT-010 best (1 Indirect, hist=3)                       [baseline]
  2. Phase 1 + Ind(hist=3, w=0.20) + Ind(hist=2, w=0.15)
  3. Phase 1 + Ind(hist=3, w=0.20) + Ind(hist=2, w=0.12) + Ind(hist=1, w=0.08)
  4. Phase 1 + Ind(hist=3, lr=0.03, w=0.18) + Ind(hist=2, w=0.12)
  5. Phase 1 + Ind(hist=3, w=0.20) + Ind(hist=2, big map, w=0.15)

Phase 1 fixed at w=0.9 (EXPT-010 fine optimum). Map sizes: hist=3 → 1<<24
(16 MB), hist=2 → 1<<22 (4 MB), hist=1 → 1<<20 (1 MB).

**Result on 100KB enwik8:**

| Configuration | Bytes | bpb | vs gzip-9 |
|---|---|---|---|
| gzip-9 | 36,239 | 2.8991 | — |
| P1 + Ind(hist=3) [EXPT-010 best] | 34,756 | 2.7805 | −4.09% |
| P1 + Ind(hist=3) + Ind(hist=2) | 33,001 | 2.6401 | −8.94% |
| **P1 + Ind(hist=3,2,1) — 3 Indirects** | **32,427** | **2.5942** | **−10.52% (best)** |
| P1 + Ind(hist=3, lr=0.03) + Ind(hist=2) | 33,139 | 2.6511 | −8.55% |
| P1 + Ind(hist=3) + Ind(hist=2, big map) | 33,005 | 2.6404 | −8.92% |

All 5 variants byte-exact roundtrip ✓.

**Result on 1MB enwik8:**

| Configuration | Bytes | bpb | vs gzip-9 |
|---|---|---|---|
| gzip-9 | 355,791 | 2.8463 | — |
| EXPT-010 best (1 Ind, hist=3) | 311,764 | 2.4941 | −12.37% |
| P1 + Ind(hist=3) + Ind(hist=2) | 302,570 | 2.4206 | −14.96% |
| **P1 + Ind(hist=3,2,1) — 3 Indirects** | **299,802** | **2.3984** | **−15.74% (best)** |
| P1 + Ind(hist=3, lr=0.03) + Ind(hist=2) | 301,872 | 2.4150 | −15.16% |
| P1 + Ind(hist=3) + Ind(hist=2, big map) | 302,566 | 2.4205 | −14.96% |

All 5 variants byte-exact roundtrip ✓.

At 1MB the 3-Indirect ensemble wins by the same margin pattern as 100KB.
The architectural rule "more orthogonal Indirects + smaller individual weights"
holds at scale.

**Verdict: STACKING WINS.** Each added Indirect predictor at a different
`hist` brings genuinely independent signal. From −4.09% to −10.52% on 100KB
just by adding 2 more Indirects. The "less but smarter" lesson from EXPT-005
holds at the predictor level: 3 well-chosen Indirects (hist=1, 2, 3) outperform
1 maxed-out Indirect (hist=3).

This is exactly the pattern FX2CMIX-STRUCTURE-2026-05-16.md §5 named:
fx2-cmix removed redundant predictors and added orthogonal ones. Confirming
the cmix architectural intuition at our scale.

**What's next (already started):**
- EXPT-012 online weight tuner (no more hand-picking — see above entry)
- More predictor families (sparse context Indirects, bracket-aware models)

**Artefacts:**
- `option_a/expt_multi_indirect.py` (180 LOC): 5-config harness

---

## EXPT-010 — 2026-05-16 — Bit-level mix: Phase 1 + Indirect — TRACK-B BEATS GZIP DECISIVELY

**Hypothesis:** EXPT-009 showed `IndirectBitPredictor` is structurally correct
but worse than gzip alone (+17% at 100KB). Mixing it with the byte-level
Phase 1 stack via a bit-level logistic combiner (`MultiBitPredictor`) should
produce a result that beats either predictor alone, because the two signals
are orthogonal — Phase 1 captures byte-level n-gram + match co-occurrence;
Indirect captures bit-level coupling via the (byte_context, bit_context)
state machine.

**Method:** New `MultiBitPredictor` in `bit_mixer.py`. Per bit:
  p_i = child_i.predict_bit(...)        # one float per child
  logit_i = log(p_i / (1 - p_i))
  final = sigmoid(Σ w_i * logit_i)
Update: each child receives `update_bit(bit, bit_context, k)`.

Two children: `BytewiseBitPredictor` wrapping byte-level Phase 1 (5
predictors, locked weights `[0.630, 1.401, 0.995, 0.550, 2.035]`) and
`IndirectBitPredictor` (map=1<<24, lr=0.05, hist=3 — EXPT-009 best).
Weight sweep over (w_phase1, w_indirect).

**Result on 100KB enwik8:**

| Variant | Bytes | bpb | vs gzip-9 |
|---|---|---|---|
| gzip-9 | 36,239 | 2.8991 | — |
| BIT Phase 1 alone | 36,511 | 2.9209 | +0.75% |
| BIT Indirect alone | 42,367 | 3.3894 | +16.91% |
| **MIX (Phase1=1.00, Indirect=0.25)** | 35,019 | 2.8015 | **−3.37%** |
| **MIX (Phase1=0.90, Indirect=0.25) [fine]** | **34,756** | **2.7805** | **−4.09% (best)** |
| MIX (1.00, 0.50) | 36,179 | 2.8943 | −0.17% |
| MIX (1.00, 0.10) | 35,353 | 2.8282 | −2.45% |
| MIX (1.00, 0.20) | 35,006 | 2.8005 | −3.40% |
| MIX (1.00, 0.30) | 35,123 | 2.8098 | −3.08% |

All variants byte-exact roundtrip ✓.

**Result on 1MB enwik8:**

| Variant | Bytes | bpb | vs gzip-9 |
|---|---|---|---|
| gzip-9 | 355,791 | 2.8463 | — |
| BIT Phase 1 alone | 323,520 | 2.5882 | −9.07% |
| BIT Indirect alone | 374,895 | 2.9992 | +5.37% |
| MIX (Phase1=1.00, Indirect=0.25) coarse | 320,090 | 2.5607 | −10.03% |
| MIX (1.00, 0.50) | 336,604 | 2.6928 | −5.39% |
| MIX (0.75, 0.75) | 336,079 | 2.6886 | −5.54% |
| MIX (1.00, 0.15) fine | 317,482 | 2.5399 | −10.77% |
| MIX (1.00, 0.10) fine | 317,711 | 2.5417 | −10.70% |
| **MIX (0.90, 0.25) fine — 1MB optimum** | **311,764** | **2.4941** | **−12.37% (best)** |
| MIX (1.10, 0.25) | 329,757 | 2.6381 | −7.32% |

All variants byte-exact roundtrip ✓.

**Verdict: DECISIVE WIN.**

At 100KB:
  - track-b mix BEATS gzip-9 by **−4.09%** (best fine-tuned weights)
  - mix beats bit-Phase1-alone by **−4.81%** (36,511 → 34,756)
  - first track-b configuration that decisively beats gzip on 100KB

At 1MB:
  - track-b mix BEATS gzip-9 by **−12.37%** (fine sweep, (0.9, 0.25))
  - mix beats bit-Phase1-alone by **−3.63%** (323,520 → 311,764)
  - mix beats coarse-(1.0,0.25) by 2,326 bytes (−0.73%) just from dropping
    Phase 1 weight to 0.9 — same exact pattern as 100KB where (0.9, 0.25)
    won. The fine optimum TRANSFERS across scales.
  - gain over Phase 1 alone scales: −4.08% at 100KB, −3.63% at 1MB.
    Both consistent. The architecture is the right shape.

**Why this matters:** until today, track-b at 1MB was Phase 1 alone at
2.59 bpb (−9.07% under gzip). Now it's 2.56 bpb (−10.03% under gzip) with
the same architectural family (logistic mix of multiple predictors) extended
to bit-level granularity. The architecture is the right shape: each new
bit-level predictor we add (multi-Indirect, APM/SSE, sparse context) joins
the mix with its own weight and contributes its own signal.

**Optimal weights:** at 100KB, fine sweep finds (w_p1=0.9, w_ind=0.25). At
1MB, coarse sweep finds (w_p1=1.0, w_ind=0.25). The weights drift with
scale — proper online weight tuning (EXPT-012) will adapt per-context per-byte
instead of relying on hand-picked globals.

**Open questions for follow-ups:**
- EXPT-011 (multi-Indirect): 2-3 Indirect predictors with different context
  hashes. Already wired in `expt_multi_indirect.py`.
- EXPT-012 (online weight tuner): port Phase 1's SGD tuner to the bit-level
  mix. Expected: another 1-2% on top.
- EXPT-013 (APM/SSE): Shelwien's 7-bin quantization remap after the mix,
  before AC. ~60 LOC. Expected: 1-2%.

**Artefacts:**
- `option_a/bit_mixer.py` (+97 LOC): `MultiBitPredictor` + `make_multi_factory`
- `option_a/expt_bit_mix.py` (160 LOC): 8-weight coarse sweep
- `option_a/expt_bit_mix_fine.py` (90 LOC): finer probe around 100KB optimum
- `option_a/expt_multi_indirect.py` (130 LOC): scaffold for EXPT-011

**References:**
- FX2CMIX-STRUCTURE-2026-05-16.md §"What I'd build first" (2-hour port plan)
  predicted this exact result shape from the per-context discrimination angle
- PAQ8 / cmix logistic mixing patent + Mahoney's "Adaptive Weighting of
  Context Models for Lossless Data Compression"

---

## EXPT-009 — 2026-05-16 — IndirectBitPredictor (Phase 2D, standalone bit-native predictor) — STRUCTURAL PASS

**Hypothesis:** Port fx2-cmix's indirect.h pattern as the first bit-native
predictor in track-b. Shared map (byte array) keyed on (byte_context,
bit_context) holds state bytes; local predictions[] indexed by state gives
p(bit=1); on each bit observation, EMA-update predictions[state] and advance
state via `NEXT_STATE` table.

If the port is structurally correct, standalone Indirect should compress
the corpus measurably better than the uniform predictor (8 bpb) — even
without help from byte-level Markov/match models. ~3.5–5.0 bpb on enwik8
100KB is the target band (Phase 1 with 5 predictors lands at 2.92 bpb;
single Indirect can't match that yet).

**Method:** `expt_indirect.py [SLICE_BYTES]`. Drives `bit_codec.bit_encode`
with ONLY an `IndirectBitPredictor`. State machine in `state.py`: 256 states
encoding (count_of_1s, count_of_0s) capped at 15 each, nonstationary halving
when both saturated, Laplace prior on initial predictions. Sweep:
- map_size ∈ {1<<20, 1<<22, 1<<24} (1, 4, 16 MB)
- lr ∈ {0.05, 0.1, 0.2}
- history_window ∈ {1, 2, 3} bytes for context hash

**Result on 100KB enwik8 (best variants):**

| Variant | Bytes | bpb | vs gzip-9 |
|---|---|---|---|
| uniform (8 bpb baseline) | 100,000 | 8.0000 | — |
| **gzip-9** | **36,239** | **2.8991** | **baseline** |
| byte-level Phase 1 (reference) | 36,510 | 2.9208 | +0.7% |
| Indirect (1<<24, lr=0.05, hist=3) | 42,367 | 3.3894 | +16.9% (BEST) |
| Indirect (1<<24, lr=0.05, hist=2) | 43,325 | 3.4660 | +19.6% |
| Indirect (1<<20, lr=0.05, hist=3) | 43,362 | 3.4690 | +19.7% |
| Indirect (1<<24, lr=0.05, hist=1) | 53,370 | 4.2696 | +47.3% |

**Roundtrip:** all 19 sweep variants verified byte-exact ✓.

**Verdict: STRUCTURAL PASS.** The port is correct. Indirect alone is +16.9%
worse than gzip — exactly as expected for ONE predictor doing the work that
Phase 1 spreads across 5. The architecture works: it learns the byte
distribution via state-byte transitions and EMA, scales with map size
(1<<24 > 1<<22 > 1<<20), and prefers small lr + longer history (consistent
with cmix/PAQ findings).

**Why this matters:** With Indirect proven byte-exact and structurally
correct, the architectural toolbox now contains both:
1. byte-level mixer wrapping (BytewiseBitPredictor) — for the existing Phase 1
2. bit-native state-machine predictor (IndirectBitPredictor) — new

The next experiment (EXPT-010) mixes them via a bit-level logistic mixer.
Indirect alone is +16%; Phase 1 alone is +0.7%; the mix should beat Phase 1
because Indirect adds signal Phase 1's Markov + match models can't capture
(specifically: bit-level coupling within a byte, which byte-level predictors
miss by construction).

**Knobs identified:**
- `map_size`: larger is consistently better up to 1<<24; collisions kill
  smaller maps at higher history_window. 1<<24 = 16 MB is the v0 default.
- `lr`: 0.05 wins. Larger rates overshoot rare contexts.
- `history_window`: 3 > 2 > 1 at 100KB. May invert at 10KB (sparse contexts).
- `context hash`: currently last-N bytes ⊕ Knuth multiplicative. Better hashes
  (sparse-skip, last + second-to-last, masked) are EXPT-011+.

**Performance:** ~1.3s encode + 1.6s decode for 100KB. Slower per byte than
BytewiseBitPredictor by ~2× (1.3s vs 0.62s) due to per-bit state lookup.
Acceptable for the architectural reference; Cython port will erase the gap.

**Artefacts:**
- `option_a/state.py` (66 LOC): 256-state nonstationary transition table +
  Laplace-prior prediction table
- `option_a/bit_mixer.py` (+105 LOC): `IndirectBitPredictor`, `make_indirect_factory`
- `option_a/bit_codec.py` (+1 LOC): `update_bit(bit, bit_context, k)` hook
- `option_a/expt_indirect.py` (110 LOC): sweep harness

**References:**
- `lab/fx2-cmix/src/models/indirect.h` (the 68-LOC original)
- FX2CMIX-STRUCTURE-2026-05-16.md §"Indirect context model is the biggest port-leverage item"

---

## EXPT-008 — 2026-05-16 — Bit-level codec baseline (Phase 2C foundation) — EQUIVALENCE GATE PASSED

**Hypothesis:** Wrap the byte-level mixer inside a bit-level codec
(`BytewiseBitPredictor`) such that each byte becomes 8 nested AC calls walking
the binary tree over the byte-level cum_freqs interval. This should be
mathematically equivalent to the byte-level codec up to integer-truncation
noise in `encode_symbol`. If we can prove equivalence + byte-exact roundtrip
at scale, the architecture is unlocked for bit-native predictors (indirect
context model, APM/SSE, high-cardinality per-context dispatch).

**Method:** Three new files in `option_a/`:
- `bit_mixer.py` — `BitPredictor` protocol + `BytewiseBitPredictor` (snapshots
  byte-level cum_freqs at `start_byte`, walks the bit-tree at `predict_bit`,
  updates underlying predictors at `commit_byte`).
- `bit_codec.py` — `bit_encode` / `bit_decode`. Per byte: 8 calls to
  `encode_symbol(low, high, precision)` on a 2-symbol bit interval. p_one
  quantized to integer in [1, precision-1]. Bit ordering MSB-first;
  `bit_context = 1` sentinel, `bit_context = (bit_context << 1) | bit` step.
- `expt_bit_baseline.py` — drives byte-level and bit-level encoders over the
  same predictor stack; reports delta and roundtrip.

Bit-level AC precision swept: 2^24, 2^20, 2^16, 2^12.

**Result on 10KB enwik8:**

| Pipeline | Bytes | bpb | vs byte |
|---|---|---|---|
| byte-level geometric | 4,456 | 3.5648 | baseline |
| byte-level Phase 1 logistic | 4,462 | 3.5696 | baseline |
| bit wrapping byte-geometric (2^24) | 4,456 | 3.5648 | **+0.000%** |
| bit wrapping byte-Phase1 (2^24) | 4,462 | 3.5696 | **+0.000%** |
| bit wrapping byte-Phase1 (2^20..2^12) | 4,462 | 3.5696 | **+0.000%** |

**Result on 100KB enwik8:**

| Pipeline | Bytes | bpb | vs byte |
|---|---|---|---|
| byte-level geometric | 37,502 | 3.0002 | baseline |
| byte-level Phase 1 logistic | 36,510 | 2.9208 | baseline |
| bit wrapping byte-geometric (2^24) | 37,502 | 3.0002 | **+0.000%** |
| bit wrapping byte-Phase1 (2^24) | 36,511 | 2.9209 | **+0.003%** (+1 byte) |
| bit wrapping byte-Phase1 (2^20) | 36,510 | 2.9208 | +0.000% |
| bit wrapping byte-Phase1 (2^16) | 36,510 | 2.9208 | +0.000% |
| bit wrapping byte-Phase1 (2^12) | 36,497 | 2.9198 | −0.036% (trunc luck) |

**Result on 1MB enwik8 (the at-scale verification):**

| Pipeline | Bytes | bpb | vs byte |
|---|---|---|---|
| byte-level geometric | 338,769 | 2.7102 | baseline |
| byte-level Phase 1 logistic | 323,520 | 2.5882 | baseline |
| bit wrapping byte-geometric (2^24) | 338,769 | 2.7102 | **+0.000%** |
| bit wrapping byte-Phase1 (2^24) | 323,520 | 2.5882 | **+0.000%** |
| bit wrapping byte-Phase1 (2^20) | 323,520 | 2.5882 | +0.000% |
| bit wrapping byte-Phase1 (2^16) | 323,496 | 2.5880 | −0.007% |
| bit wrapping byte-Phase1 (2^12) | 323,101 | 2.5848 | −0.130% (trunc luck) |

At 1MB, byte-Phase1 = 323,520 (using locked 100KB-trained weights). Refit-on-1MB
weights from EXPT-007 yielded 323,469 — the 51-byte gap is the weight refit
delta, not a bit-codec artifact. Equivalence between byte and bit-level holds
under both weight sets.

**Roundtrip:** `decode(encode(data)) == data` verified byte-exact on the
bit-Phase1 blob at 10KB, 100KB, and 1MB.

**Verdict: EQUIVALENCE GATE PASSED.** Bit-level wrapping byte-level mixers is
byte-equivalent to the byte-level codec at the granularity the AC supports.
The 8 bit-tree narrowings cumulate to the same arithmetic interval as a single
byte-level `encode_symbol`, so all encoders converge to the same bit stream
up to integer truncation. No bug.

**Why this matters:** the bit-level architecture is now the canonical path.
The byte-level codec is preserved as a fast reference, but new predictors land
on the bit side. Three doors are open:
1. **fx2-cmix indirect context model** (`indirect.h`, 68 LOC): context_hash
   → state byte → 256-entry probability table, all keyed on bit_context.
   Expected +3-7% on text.
2. **Shelwien APM/SSE final stage** (~60 LOC): quantize bit-prob into 7 bins
   per context, EMA-update adjacent bins. Chains after the mixer, before AC.
   Expected +1-2%.
3. **High-cardinality per-context mixer** (>256 slots): now that context can
   include bit-level state (bit_context + byte_partial + last 1-2 bytes),
   we can hash to 10k+ slots like fx2-cmix's `Mixer::GetContextData`. This is
   the missing condition that made EXPT-006 fail at 1MB.

**Phase 2 sequence now:**

| Phase | Move | Status |
|---|---|---|
| 2A | AC precision | NULL (EXPT-002) |
| 2B' | Phase 1 global as SOTA | DONE (323,469B @ 1MB, −9.1% vs gzip-9) |
| 2C | **Bit-level codec refactor + equivalence gate** | **DONE (EXPT-008)** |
| 2D | Indirect context model (state byte + 256-entry table) | NEXT |
| 2E | APM/SSE chained after bit-mixer | after 2D |
| 2F | Per-context mixer with bit-level hash (10k+ slots) | after 2D |

**Performance:** bit-Phase1 at 100KB took 6.2s encode + 6.6s decode (pure Python).
Byte-Phase1 took 5.6s encode. ~10% slowdown for 8x more AC calls is fine —
this is the architectural reference, not the hot path. Cython port later.

**Artefacts:**
- `option_a/bit_mixer.py` (147 LOC)
- `option_a/bit_codec.py` (104 LOC)
- `option_a/expt_bit_baseline.py` (130 LOC)
- `option_a/__pycache__/bit_*.cpython*` (built cleanly)

**References:**
- FX2CMIX-STRUCTURE-2026-05-16.md §1 (per-context weights with bit-level state)
- FX2CMIX-STRUCTURE-2026-05-16.md §"What I'd build first" (port-leverage order)
- src.baseline.ArithmeticEncoder.encode_symbol contract (interval truncation)
- PAQ bit_context tree convention (start at 1, shift+OR on each bit)

---

## EXPT-007 — 2026-05-16 — Per-context mixer at 1MB scale + variant sweep — REVERSES EXPT-006

**Hypothesis:** EXPT-006's per-context mixer gain (-3.5% on 100KB) should
hold or grow at 1MB scale, since each context gets ~10× more updates. If
the gain shrinks, the warm-start was wrong; if it inverts, the per-context
architecture itself doesn't help at our context cardinality (256 slots).

**Method:** `expt_per_context_v2.py 1000000`. Refit Phase 1 global weights
on 1MB first (instead of using 100KB-trained warm-start), then sweep
per-context variants:
- A: lr=0.05, clip=5 (EXPT-006 settings)
- B: lr=0.005, clip=5 (slower drift)
- C: lr=0.05, clip=2 (tighter clip)
- D: lr=0.001, clip=5 (slowest drift)

All warm-started from refit Phase 1 global. Roundtrip verified each.

**Result on 1MB enwik8:**

| Pipeline | Bytes | bpb | vs refit Phase 1 | vs gzip-9 |
|---|---|---|---|---|
| gzip-9 | 355,791 | 2.8463 | — | 0% |
| track-B geometric | 338,769 | 2.7102 | +4.73% | −4.78% |
| **track-B refit Phase 1 global** | **323,469** | **2.5878** | **0% (baseline)** | **−9.09%** |
| Per-context A (lr=0.05, clip=5) | 328,829 | 2.6306 | +1.66% | −7.58% |
| Per-context B (lr=0.005, clip=5) | 327,761 | 2.6221 | +1.33% | −7.88% |
| Per-context C (lr=0.05, clip=2) | 326,710 | 2.6137 | +1.00% | −8.18% |
| Per-context D (lr=0.001, clip=5) | 324,601 | 2.5968 | +0.35% | −8.77% |

**Refit Phase 1 weights on 1MB:** `[0.629, 1.400, 0.995, 0.550, 2.035]` —
essentially identical to the 100KB-trained weights. The global optimum is real
and stable across scales.

**Verdict: EXPT-006 OVERTURNED.** Per-context at 256-slot granularity does not
scale. Variant D (lr=0.001) recovers nearest-to-global by minimising per-context
drift, but cannot improve on it.

**Why:** fx2-cmix's per-context mixer uses up to 10,000 unique 64-bit context
hashes incorporating bit-level state + many predictor outputs. Our 256-slot
"last byte" hash averages over too many heterogeneous behaviors per slot.
At 100KB, lucky overfitting masked this; at 1MB the noise floor of per-context
updates dominates the discrimination signal.

**The honest upside:** at 1MB scale, **Phase 1 global ALONE is −9.1% under
gzip-9** (323,469 vs 355,791). track-B was already winning at real-corpus scale;
EXPT-001's measurement on 100KB just looked worse than it was. The per-context
gain on 100KB was 100KB-specific, but Phase 1 global wins ARE real and scale.

**Decision:** Drop per-context from default for now. Revert SOTA to Phase 1
global tuned weights. Per-context discrimination remains a future move BUT
requires (a) bit-level features and (b) high-cardinality hashing (10k+ slots) —
which means the bit-level codec refactor is the gateway, not a hack at byte level.

**Phase 2 sequence corrected:**

| Phase | Move | Status |
|---|---|---|
| 2A | AC precision | NULL (EXPT-002) |
| 2B | ~~Per-context (256-slot, byte-level)~~ | **REVERTED (EXPT-007)** |
| 2B' | Confirm Phase 1 global is corrected SOTA at scale | DONE — 1MB = −9.1% vs gzip |
| 2C | Bit-level codec refactor | NEXT — gateway to 2D, 2E, real per-context |
| 2D | Indirect context model (cmix-style) | 3-7% expected |
| 2E | APM/SSE final stage | 1-2% expected |
| 2F | Per-context dispatch with 10k+ bit-level hashes | enabled by 2C+2D |

**Artefacts:**
- `option_a/expt_per_context_v2.py` — variant sweep harness
- LAB-LOG.md — EXPT-006 status downgraded; EXPT-007 logged with corrected SOTA

**Reference:** FX2CMIX-STRUCTURE-2026-05-16.md §1 explains why 256-slot byte-level
context is too coarse to capture what fx2-cmix's 64-bit hashes are doing.

---

## EXPT-006 — 2026-05-16 — Per-context mixer weights (fx2-cmix port) — 100KB ONLY, OVERTURNED BY EXPT-007

**STATUS UPDATE (post-EXPT-007):** This experiment showed −3.5% on 100KB but
+0.35-1.7% (LOSS) on 1MB across all variant settings. The 100KB result was a
small-sample-size artifact. See EXPT-007 above for the corrected SOTA and
reasoning. ORIGINAL ENTRY PRESERVED BELOW for the audit trail.

---

**Hypothesis:** fx2-cmix's `Mixer::GetContextData()` stores weights PER unique
context hash (up to 10,000 distinct contexts). This is the single biggest source
of mixer intelligence in PAQ-class compressors. Phase 1 learned ONE global weight
vector for the whole 100KB. EXPT-006: maintain a 256-entry table indexed by
previous byte, each entry an independent 5-weight vector trained by SGD.
Warm-started from Phase 1's converged global weights.

**Method:** `expt_per_context.py 100000`. Tokenisation: `context = data[i-1]`
for byte i (using 0 for i=0). Weight table shape `(256, 5)`, warm-start
`[0.63, 1.40, 0.99, 0.55, 2.03]` (Phase 1 result). SGD per byte updates only
that byte's context row. `lr_init=0.05`, `lr_decay=0.9999`, clip ±5.0.

**Result:**
| Pipeline | Bytes | bpb | vs geometric | vs gzip-9 |
|---|---|---|---|---|
| gzip-9 baseline | 36,239 | 2.8991 | n/a | 0% |
| track-B geometric | 37,502 | 3.0002 | 0% | +3.49% |
| track-B Phase 1 global tuned | 36,510 | 2.9208 | −2.64% | +0.75% |
| **track-B per-context tuned** | **35,245** | **2.8196** | **−6.02%** | **−2.74%** |

**vs Phase 1 global:** −3.465%. Target was ≥0.5%. **PASS at 7x target.**

**Statistics from SGD pass:**
- 156/256 contexts saw updates (the rest are bytes that never preceded another byte in 100KB)
- Median 41 updates per context (seen)
- Max 13,461 updates (likely byte 0x20 = space, which precedes almost every word start)
- SGD training-time bpb = 2.8203 (matches final 2.8196 encode bpb, confirming weights are stable at end of training)

**Roundtrip:** ✓ byte-exact verified (encode → decode → compare).

**Verdict: PASS — and first time track-B beats gzip-9 on 100KB enwik8.** This is
the largest single-experiment gain so far in the Option A trajectory:

| Cumulative gain log | vs raw track-B (37,502) |
|---|---|
| After Phase 1 (EXPT-001, global SGD weights) | −2.64% → 36,510 |
| After EXPT-003 (Match-16 added) | small additional, not stacked |
| After EXPT-006 (per-context 256-byte table) | **−6.02% → 35,245** |

**What the weights learned (preliminary):** highest-update-count contexts are
space, period, common letters. Each developed its own weight profile. Detailed
weight inspection deferred to EXPT-007.

**Decision:** Ship per-context mixer to default. Phase 2 sequence revised:

| Phase | Move | Status |
|---|---|---|
| 2A | ~~AC precision~~ | NULL (EXPT-002) |
| **2B** | **Per-context mixer weights (last-byte context)** | **SHIPPED (EXPT-006)** |
| 2C | Bit-level codec refactor | NEXT (prerequisite for 2D/2E) |
| 2D | Indirect context model | per FX2CMIX-STRUCTURE-2026-05-16.md (3-7% expected) |
| 2E | APM/SSE final stage | per FX2CMIX-STRUCTURE-2026-05-16.md (1-2% expected) |
| 2F | Multi-context mixers (>1 mixer with different context keys) | when 2D lands |

Future EXPT-007 candidates (cheaper than the bit-level refactor):
- Per-context using last 2 bytes hashed to 256 slots (vs single-byte)
- Per-context using word-type signal (alpha / digit / space / punct → 4 contexts only, but very dense updates)
- Staircase decay schedule (fx2-cmix style: 1.0 → 0.7 → 0.3 → 0.2)
- Multiple per-context mixers, one keyed by last byte, one keyed by last 2 bytes, mixed by a Layer-1 mixer (fx2-cmix two-layer architecture)

**Artefacts:**
- `option_a/expt_per_context.py` — full experiment, roundtrip-verified
- Trained 256-row weight table (in-memory; serialise to disk in EXPT-007)

**Reference:** `FX2CMIX-STRUCTURE-2026-05-16.md` §1 (Mixer GetContextData)

---

## EXPT-005 — 2026-05-16 — WRT selectivity sweep (min_word_len 3..8)

**Hypothesis:** EXPT-004 showed WRT v0 was a wash because we were replacing
short common words ("the", "and") that track-B's predictor already compressed
to <1 byte each. The substitute bytes are novel → predictor starts cold →
net loss. If we only substitute LONG words (where the predictor was costing
>1 byte/char), the substitution becomes net positive. Sweep K = min_word_len
from 3 to 8 to find the crossover.

**Method:** `expt_wrt_sweep.py 100000`. Build dict with min_word_len=K for each
K, encode raw → wrt → track-B geometric, compare blob size to raw → track-B.
Verify full-pipeline roundtrip at each K.

**Result:**

| K | dict | match % | wrt_size | tb_size | tb_bpb | vs raw |
|---|---|---|---|---|---|---|
| 3 | 315 | 41.7% | 75,417 | 38,407 | 3.0726 | **+2.41%** |
| 4 | 315 | 30.7% | 77,534 | 38,025 | 3.0420 | +1.40% |
| 5 | 315 | 22.9% | 79,740 | 37,750 | 3.0200 | +0.66% |
| 6 | 315 | 19.9% | 80,699 | 37,578 | 3.0062 | +0.20% |
| 7 | 315 | 17.4% | 81,897 | 37,518 | 3.0014 | +0.04% |
| 8 | 315 | 14.8% | 83,347 | 37,378 | 2.9902 | **−0.33%** |

**Strictly monotonic.** Every short word we DON'T replace, track-B compresses better.

**Verdict:** PASS at K=8 (net positive but tiny) — confirms the thesis. PRINCIPLE
WIN, NOT BPB WIN. Result establishes that the literature claim (cmix gets 5-10%
from WRT) is dominated by *architecture-aware integration* (bracket-context
predictor handles substitute bytes specifically), NOT the substitution mechanism
itself. v0 WRT without integration cannot deliver more than ~0.3% on track-B.

**Strategic implication for Phase 2:** preprocessing won't get us to Hutter-class.
The path to 1.0 bpb runs through making the predictor SEE MORE PATTERNS:
- Longer match contexts (Match-16 already +0.337% in EXPT-003 — keep)
- Bit-level prediction (unlocks indirect contexts + APM/SSE)
- Sparse contexts (skip-n-gram tables)
- Eventually: small neural predictor (L3TC RWKV-12M path) feeding logits into AC

The Hotz/Hutter framing predicted exactly this: **you can't fake a probability
distribution. The arithmetic coder ratifies whether the model knows the data.**
Phase 1's -2.6% was a real intelligence gain (smarter weights). EXPT-002,
EXPT-004 didn't move because they didn't make the predictor smarter — they
just rearranged the input.

**Decision:** Phase 2 priorities rewritten:
- 2A (deferred): WRT integration with architecture-aware predictor — defer until
  bit-level refactor lands (it'll be cleaner then)
- 2B (next): bit-level codec refactor — prerequisite for indirect contexts + APM
- 2C: indirect context model + nonstationary state map (cmix path, 3-7% expected)
- 2D: APM/SSE final stage (1-2%)
- 2E: add Match-16 to default factory (already validated +0.337% in EXPT-003)

**Artefacts:**
- `option_a/wrt.py` — now parameterised on `min_word_len`
- `option_a/expt_wrt_sweep.py` — sweep harness, full-pipeline roundtrip verified

---

## EXPT-004 — 2026-05-16 — WRT v0 preprocessing impact (315-entry self-trained dict)

**Hypothesis:** Skibinski WRT preprocessing pass before track-B encode will shrink
blob size by 3-10% per literature (cmix uses ~80k-entry dict). v0 uses a self-trained
dict of 315 entries (59 single-byte codes + 256 two-byte prefix codes), built from
the 1MB enwik8 prefix. Tokenisation: `[A-Za-z]+`. No case folding, no q-gram tricks.

**Method:** `expt_wrt.py 100000`. Pipeline: `raw → encode_wrt → wrt_data → track-B encode`.
Roundtrip verify full pipeline (track-B decode → decode_wrt → raw). Compare against
raw track-B (both geometric and tuned-logistic configs).

**Result:**
| Pipeline | Bytes | bpb | vs raw geometric |
|---|---|---|---|
| gzip-9 (raw) | 36,239 | 2.8991 | baseline |
| track-B geometric (raw) | 37,502 | 3.0002 | 0% |
| track-B tuned (raw) | 36,511 | 2.9209 | −2.64% |
| track-B geometric (WRT) | 38,407 | 3.0726 | **+2.41% (WORSE)** |
| track-B tuned (WRT) | 36,433 | 2.9146 | −2.85% |

WRT alone shrinks raw 100KB → 75.4KB (24.6% raw-byte reduction, 41.7% word-match rate).
gzip-9 on WRT(raw) = 34,432 bytes (−5.0% vs gzip-9 on raw). The mechanism *works*.

But track-B's gain over its own raw-tuned baseline: **+0.21%**. Below 3% gate.

**Why the mechanism doesn't transfer to track-B as-is:**
WRT replaces "the" → one absent byte (e.g. 0x01). track-B's Markov(order-3) and
Match predictors had learned strong patterns for "the" and similar high-freq words.
Substitute bytes 0x01-0x1F are never seen in raw enwik8 → predictors start cold
for every preprocessed encoding. WRT + geometric is +2.4% WORSE than raw + geometric
for exactly this reason.

The tuned-logistic mixer recovers most of the loss because the SGD adapts weights
to the new byte distribution (Match-8 weight 0.55 → 1.64 as long-context patterns
take over from order-3). But the recovery only gets us 0.21% past raw-tuned.

**Architecture-aware integration is what unlocks WRT.** cmix wraps WRT codes with
a `bracket-context` model that has a specific predictor for the escape bytes. Without
that, WRT is a wash on small dicts and small slices.

**Verdict:** FAIL on this gate but VALUABLE NULL. Two follow-up paths:
1. v1: extend to 3-byte prefix codes (65k+ entries) — match real Skibinski capacity
2. Add an architecture-aware predictor for WRT codes (bracket-context analog) —
   bigger refactor, larger ceiling

**Decision:** Try v1 (capacity expansion) before committing to architecture-aware
integration. If 65k-entry dict on 1MB enwik8 still gives <2% net gain, the
binding constraint is integration, not capacity.

**Artefacts:**
- `option_a/wrt.py` — encode/decode + roundtrip verification (315-entry dict)
- `option_a/expt_wrt.py` — full-pipeline comparison harness

**Reference:** cmix `preprocess/dictionary.cpp`, XWRT (Skibinski et al. 2005-2007)

---

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
