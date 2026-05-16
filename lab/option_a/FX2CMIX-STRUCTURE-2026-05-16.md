# fx2-cmix Structural Map — 2026-05-16

**Source:** github.com/kaitz/fx2-cmix (Hutter Prize record, Oct 8 2024)
**Total LOC:** 16,661 (including 3rd party + data structures)
**Structural core LOC:** ~5,500 (excluding emhash, SmallVector, AlignOf, fxcmv1 specialised model, ppmd library)
**Authors:** Kaido Orav, Byron Knoll
**Hardware target:** 16GB RAM, single Xeon @ 3.10GHz, 65h decode (47h on Hutter reference)

---

## Top-level pipeline (from predictor.cpp)

```
Manager (state: bit_context, words[4 streams], history, shared_map[MBs], nonstationary)
   │
   ├─ bracket_model      (1 output)  WRT-aware: handles XML/wikitext brackets
   ├─ fxcm_model         (multi-out) THE big new model. 4824 LOC. Custom mixer.
   ├─ direct_models      (1 each)    Small hash → counts predictors
   ├─ match_models       (5+5)       Orders 0/1/7/11/13 with length limits 8/8/4/3/2
   ├─ indirect_ns_models (~17)       Nonstationary indirect (shared map)
   ├─ indirect_r_models  (1-2)       Run-map indirect (sparse word contexts)
   ├─ byte_model         (PPMd)      Depth 25, 14000 byte limit, Shkarin's
   └─ byte_mixer         (LSTM)      128 hidden, byte-level neural mixer
   
─────────────────────────────────────────────────────────────────
        ↓ ALL OUTPUTS FLOW INTO ↓

Layer 0: 23 logistic mixers
   Each mixer has its OWN context hash (mx5..mx19, longest_match_, 
   line_break_, recent_bytes_, wordscxt, b2streamcxt, b3streamcxt, etc).
   Each stores per-context weights (≤10,000 contexts; default fallback above).
   Per-mixer learning rates 0.0005..0.005 (hand-tuned).

Layer 1: 1 mixer combining 23 stretched layer-0 outputs + 2 auxiliary biases.

Final stage:
   p = Sigmoid(layer1.mix())
   p = sse_.Predict(p)        ← APM/SSE refinement (Shelwien's code)
   return p
```

**461 models total** (per README). One mixer sees all 461 inputs. This is the "depth" of fx2-cmix.

---

## Files-vs-our-current-state map

| fx2-cmix file | LOC | What it does | Our equivalent | Port priority |
|---|---|---|---|---|
| `mixer/mixer.cpp` | 90 | Per-context logistic mixer + SGD | `option_a/mixer.py` `multi_mix_logistic` (90 LOC) | **DONE-ish** — we have global weights, they have per-context |
| `models/indirect.h` | 68 | Context-hash → state byte → prob table (genius two-level lookup) | NONE | **P0** — biggest port-leverage item |
| `models/match.cpp` | 61 | Match model (shorter than ours, more elegant) | `option_a/predictors/match.py` via track-B `match_model.py` | SAME shape, refine later |
| `mixer/sse.cpp` | 328 | APM/SSE final-stage refinement (Shelwien) | NONE | **P1** — clean drop-in after mixer |
| `mixer/lstm.hpp` + `lstm-layer.hpp` | 384 | LSTM byte mixer (paq8px lineage) | NONE | P3 — defer, needs NumPy/MLX |
| `preprocess/dictionary.cpp` | 233 | WRT dictionary (44,515 words for enwik9) | `option_a/wrt.py` (315 words, naive) | P2 — already tried v0, needs bit-level + bracket model first |
| `models/ppmd.cpp` | 1,406 | PPMd by Dmitry Shkarin (3rd-party lib) | NONE | P3 — drop in as library if useful |
| `models/fxcmv1.cpp` | 4,824 | THE big specialised model | NONE | NEVER (specialised to fx2-cmix) |
| `predictor.cpp` | 372 | Pipeline assembly (the file above) | `option_a/codec.py` (~80 LOC) | refactor target for Phase 2 |
| `context-manager.cpp` | 221 | Context state (`bit_context_`, `words_`, `history_`, etc.) | scattered in predictors/ | needs centralisation |

---

## Five architectural insights I didn't see before reading source

### 1. Mixer weights are per-context, with collision fallback

`Mixer::GetContextData()` keeps a `context_map_` of up to 10,000 unique 64-bit context hashes, each holding its own weight vector. Beyond 10k unique contexts, fall back to a single shared `context_base_`. This is the source of fx2-cmix's per-context discrimination.

In Phase 1 (EXPT-001) we learned per-PREDICTOR global weights `[0.63, 1.40, 0.99, 0.55, 2.03]`. That's 5 floats total. fx2-cmix learns up to 10,000 × 461 = 4.6M floats per mixer × 23 mixers = ~100M floats of mixer state. The "smarter predictor" is largely this state.

**Phase 2 experiment idea:** per-context mixer weights with a much smaller context set (e.g., context = last byte, so 256 distinct contexts). Cheap A/B vs global Phase 1 weights.

### 2. Decay schedule is discrete, not exponential

```cpp
if (steps < 1M)  decay = 1.0
elif steps < 5M  decay = 0.7
elif steps < 25M decay = 0.3
else             decay = 0.2
```

Our tuner uses `lr_decay = 0.9999` per step (exponential). They use staircase. On 100KB (n=100k bits ≈ 100k bits × 0.95 word coverage ≈ 100k bits trained), the exponential decay reaches `0.9999^100000 ≈ 4.5e-5` — far below their floor of 0.2. We're decaying too aggressively for small slices.

**Phase 2 fix:** switch tuner to staircase decay, or floor the exponential at ~0.1.

### 3. Update-skip below gradient threshold

```cpp
if (fabs(update) < 0.000000000005f && extra_inputs_size_>0) return;
```

When the gradient is essentially zero (below 5e-12), skip the update entirely. Speed optimisation — avoids needless memory writes on confident bits. We don't have extra_inputs in our mixer yet, but if we add per-context state, this becomes worth it.

### 4. Two-layer mixing (mixer_0 + mixer_1)

23 layer-0 mixers each see ALL 461 model outputs, each with their own context-conditional weight set. Layer 1 has ONE mixer that consumes the 23 stretched layer-0 outputs + 2 auxiliary biases.

This is a 2-layer perceptron with 461 inputs → 23 hidden units → 1 output, but with the twist that each hidden unit's weights are stored per-context. Effectively a context-conditioned NN.

**Phase 2 target:** when we add ≥3 predictor families (Markov, Match, Indirect), use a 2-layer mixer with 2-4 layer-0 mixers each with different context dispatch (e.g., one mixer keyed by last byte, one keyed by last 2 bytes, one keyed by word context).

### 5. APM/SSE final stage = small per-context tables of size 7

Shelwien's SSE: `SSEQuant = 7` quantisation bins per context. Quantise input probability into 7 bins, linearly interpolate between adjacent bins, EMA-update both bins on outcome.

Crucially, the table is **6-7 floats per context**, not 256. A few KB of memory per context. Multiple SSE instances chain (input → SSE1 → SSE2 → ... → AC), each refining differently.

**Phase 2 P1 target:** one SSE/APM stage after the mixer, before the AC. Expected 1-2% gain. 60-line implementation.

---

## What fx2-cmix REMOVED from base cmix (per README)

> "Removed 7 indirect nonstationary predictors, 6 match model predictors, 3 mixers. This improves compression time and at the same time allows fxcm to be more complex and slower."

**Less but smarter** — exactly EXPT-005's lesson at the architecture scale. They chose 5 well-tuned match models over a dozen middling ones. Three carefully-placed mixers over six redundant ones. The fxcm submodel they gained from this reallocation is the source of most of their delta over cmix.

This validates our EXPT-003 decision to drop Match-32 and only keep Match-16. The right move at our scale is FEW predictors + GOOD context dispatch + GOOD mixer.

---

## What the WRT integration actually looks like

`AddBracket()` (predictor.cpp:46) creates:
1. A `bracket_model_` — looks at the bit context + word vocab, predicts within bracket structures
2. A `direct_model_` — keyed by the bracket context, 256 entries, depth 15
3. An `indirect_ns_model_` — keyed by the same bracket context, shared map

The `bracket_model_` is what fxcm-side: it knows when we're inside `<tag>`, `{{template}}`, `[[link]]`, etc. The model has a vocab_ parameter (the dictionary words) so it can predict WRT codes specifically.

**This is the architecture-aware integration EXPT-004/005 told us we needed.** WRT codes have their own dedicated predictor stack: bracket-context recognition + dictionary-aware vocabulary + indirect-nonstationary state. Without this, WRT is just noise to the rest of the predictor pile.

**Implication:** WRT preprocessing can't return to track-B until we have at minimum:
1. Bit-level codec
2. Indirect context model
3. A WRT-aware predictor (analogous to bracket_model_) that knows the dictionary

That's the dependency chain for WRT to be net positive on track-B.

---

## Revised Phase 2 sequence (updated from RESEARCH-2026-05-16.md)

| Phase | Move | Source of confidence | Expected gain |
|---|---|---|---|
| 2A | Staircase decay in tuner (cap at 0.1) | EXPT-001 weights converged too low; fx2-cmix decay floor 0.2 | 0.1-0.3% on small slices |
| 2B | Per-context mixer weights (last-byte context, 256 entries) | fx2-cmix mixer.cpp lines 18-41 | 0.5-1.5% |
| 2C | Bit-level codec refactor | prerequisite for 2D/2E | 0% on its own |
| 2D | Indirect context model (state byte + 256-entry prob table + shared map) | indirect.h, 68 LOC | 3-7% |
| 2E | APM/SSE final stage (Shelwien-style, 7 quant bins) | sse.cpp first 60 LOC | 1-2% |
| 2F | Two-layer mixing (2-4 layer-0 mixers with different context dispatch) | predictor.cpp lines 143-170 | 1-3% |

Cumulative target: 2.92 bpb → **~1.7-2.1 bpb** on 100KB.

Phase 3+ (after these land):
- Bracket model + WRT v1 architecture-aware integration
- PPMd as 3rd-party library drop-in
- Article reordering offline pass
- LSTM byte mixer (NumPy or MLX, not Cython)

---

## What I'd build first (concrete code, ~2 hours)

**EXPT-006: per-context mixer weights**

Keep current geometric+logistic mixers. Add a third mixer `multi_mix_logistic_per_context(predictors, context_hash, weight_table, lr)` that:
1. Looks up `weight_table[context_hash & 0xFF]` (256-slot context table on last byte)
2. Mixes with those weights
3. On `update()`, only updates the row for that context hash

Compare to Phase 1 (global weights) on 100KB enwik8. If gain ≥ 0.5%, ship.

This validates the per-context weight idea in 200 LOC without any other refactor. If it works, we know Phase 2F is real before we commit to the bit-level rewrite.

---

## References

- Source: `pipernet/lab/fx2-cmix/  # repo path`
- Files read this session: README.md, src/mixer/mixer.cpp, src/models/indirect.h, src/mixer/sse.cpp (first 80 LOC), src/predictor.cpp
- Files for next session: src/context-manager.cpp (context dispatch), src/states/ (nonstationary state tables), src/preprocess/preprocessor.cpp (WRT pipeline)
- Eugene Shelwien on SSE: https://encode.ru/threads/2515-mod_ppmd
- Hutter Prize officials: prize.hutter1.net (fx2-cmix at 110,793,128 bytes, 47.5h on reference)
