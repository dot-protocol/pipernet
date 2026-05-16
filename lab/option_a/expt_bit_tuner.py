"""
Track-B Option A — EXPT-012: online weight tuner for bit-level mix.

Run tune_bit_weights once over the corpus to learn weights for the
[BytewiseBitPredictor(Phase1), IndirectBitPredictor(hist=3), IndirectBitPredictor(hist=2),
 IndirectBitPredictor(hist=1)] stack. Then encode with the learned weights.

Hand-picked optimum from EXPT-011 at 100KB: (0.9, 0.2, 0.12, 0.08). Online
tuning should find something close and ideally beat it.

Usage:
    python3 expt_bit_tuner.py [SLICE_BYTES]
"""

from __future__ import annotations

import gzip
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
LAB = HERE.parent
sys.path.insert(0, str(LAB))

from option_a.bit_codec import bit_encode, bit_decode, DEFAULT_BIT_PRECISION  # type: ignore
from option_a.bit_mixer import (  # type: ignore
    BytewiseBitPredictor,
    IndirectBitPredictor,
    MultiBitPredictor,
)
from option_a.bit_tuner import tune_bit_weights  # type: ignore
from option_a.mixer import multi_mix_logistic  # type: ignore
from option_a.predictors import MarkovPredictor, MatchPredictor  # type: ignore


PHASE1_WEIGHTS = np.array([0.630, 1.401, 0.995, 0.550, 2.035], dtype=np.float64)


def byte_phase1_mixer(predictors):
    return multi_mix_logistic(predictors, weights=PHASE1_WEIGHTS.tolist())


def make_byte_factory():
    return [
        MarkovPredictor(),
        MatchPredictor(window=3),
        MatchPredictor(window=5),
        MatchPredictor(window=8),
        MatchPredictor(window=12),
    ]


def children_factory():
    return [
        BytewiseBitPredictor(make_byte_factory(), byte_mixer=byte_phase1_mixer),
        IndirectBitPredictor(context_fn=None, map_size=1 << 24, lr=0.05, history_window=3),
        IndirectBitPredictor(context_fn=None, map_size=1 << 22, lr=0.05, history_window=2),
        IndirectBitPredictor(context_fn=None, map_size=1 << 20, lr=0.05, history_window=1),
    ]


def make_mix_factory(weights: list[float]):
    def factory() -> MultiBitPredictor:
        return MultiBitPredictor(children=children_factory(), weights=weights)
    return factory


def main(slice_bytes: int = 100_000) -> int:
    candidates = [Path("/tmp/enwik8_1mb"), Path("/tmp/enwik8")]
    src = next((p for p in candidates if p.exists()), None)
    if src is None:
        print("ERROR: enwik8 not found", file=sys.stderr)
        return 1
    data = src.read_bytes()[:slice_bytes]
    n = len(data)
    gz = len(gzip.compress(data, compresslevel=9))
    print(f"corpus: {src} [:{n:_}]   gzip-9: {gz:_} bytes ({gz*8/n:.4f} bpb)\n")

    # Step 1: tune weights
    print(f"[tune] online SGD over 4 children (P1 + Ind3 + Ind2 + Ind1)...")
    t0 = time.perf_counter()
    initial = [0.9, 0.20, 0.12, 0.08]  # EXPT-011 best hand-picked
    weights, train_bits = tune_bit_weights(
        data, children_factory,
        num_passes=1, lr_init=0.01,
        initial_weights=initial,
        verbose=False,  # silence per-step prints
    )
    tune_t = time.perf_counter() - t0
    print(f"  initial weights: {initial}")
    print(f"  tuned weights:   {[round(w, 4) for w in weights.tolist()]}")
    print(f"  tune wall time:  {tune_t:.1f}s")
    print(f"  online-learning bpb (during tune): {train_bits/n:.4f}")
    print()

    # Step 2: clean encode with tuned weights (fresh predictor state)
    print(f"[encode] using tuned weights on fresh predictors...")
    t0 = time.perf_counter()
    blob = bit_encode(data, make_mix_factory(weights.tolist()), precision=DEFAULT_BIT_PRECISION)
    enc_t = time.perf_counter() - t0
    bpb = len(blob) * 8 / n
    delta = (len(blob) - gz) * 100 / gz
    print(f"  tuned-mix encode: {len(blob):_} bytes  bpb={bpb:.4f}  vs gzip {delta:+.3f}%  enc={enc_t:.1f}s")

    # Step 3: clean encode with the hand-picked initial weights for comparison
    print(f"[reference] EXPT-011 hand-picked weights {initial}...")
    t0 = time.perf_counter()
    ref_blob = bit_encode(data, make_mix_factory(initial), precision=DEFAULT_BIT_PRECISION)
    ref_t = time.perf_counter() - t0
    ref_bpb = len(ref_blob) * 8 / n
    ref_delta = (len(ref_blob) - gz) * 100 / gz
    print(f"  initial-mix encode: {len(ref_blob):_} bytes  bpb={ref_bpb:.4f}  vs gzip {ref_delta:+.3f}%  enc={ref_t:.1f}s")

    # Step 4: roundtrip
    back = bit_decode(blob, make_mix_factory(weights.tolist()), precision=DEFAULT_BIT_PRECISION)
    rt = "✓" if back == data else "✗"
    print(f"\n[roundtrip] tuned blob byte-exact: {rt}")

    # Verdict
    print()
    print(f"{'='*70}")
    improvement = (len(blob) - len(ref_blob)) * 100 / len(ref_blob)
    if len(blob) < len(ref_blob):
        print(f"VERDICT: tuned beats hand-picked by {-improvement:.3f}% "
              f"({len(ref_blob):_} → {len(blob):_})")
    elif len(blob) == len(ref_blob):
        print(f"VERDICT: tuned equals hand-picked (no change)")
    else:
        print(f"VERDICT: tuned LOSES to hand-picked by {improvement:.3f}% "
              f"(hand-picked was already optimal at this scale)")

    return 0


if __name__ == "__main__":
    slice_size = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
    sys.exit(main(slice_size))
