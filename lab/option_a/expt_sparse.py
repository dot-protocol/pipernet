"""
Track-B Option A — EXPT-014: sparse-context Indirects in the mix.

Existing best stack (EXPT-012): Phase 1 + Indirect(hist=3) + Indirect(hist=2)
+ Indirect(hist=1). All Indirects use CONTIGUOUS history.

Sparse-context Indirects use skip-n-gram patterns: byte[-1] + byte[-3]
(skip middle), byte[-1] + byte[-4] (skip 2), byte[-2] + byte[-3] (offset
pair). These capture regularities that contiguous hashes miss — useful
when text has positional patterns (word boundaries, punctuation rhythm).

Hypothesis: adding 2-3 sparse-context Indirects to the EXPT-012 stack +
tuning gives another 2-5% gain on top.

The stack grows from 4 children to 6-7. Tuner handles weight learning.

Usage:
    python3 expt_sparse.py [SLICE_BYTES]
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


def baseline_children():
    """EXPT-012 baseline stack: Phase1 + 3 contiguous Indirects."""
    return [
        BytewiseBitPredictor(make_byte_factory(), byte_mixer=byte_phase1_mixer),
        IndirectBitPredictor(context_fn=None, map_size=1 << 24, lr=0.05, history_window=3),
        IndirectBitPredictor(context_fn=None, map_size=1 << 22, lr=0.05, history_window=2),
        IndirectBitPredictor(context_fn=None, map_size=1 << 20, lr=0.05, history_window=1),
    ]


def stack_with_sparse_v1():
    """Add 2 sparse contexts: skip-1 (-1,-3) and skip-2 (-1,-4)."""
    return baseline_children() + [
        IndirectBitPredictor(
            context_fn=None, map_size=1 << 22, lr=0.05,
            byte_indices=(-3, -1),
        ),
        IndirectBitPredictor(
            context_fn=None, map_size=1 << 22, lr=0.05,
            byte_indices=(-4, -1),
        ),
    ]


def stack_with_sparse_v2():
    """Add 3 sparse contexts: (-3,-1), (-4,-1), (-2,-3) offset pair."""
    return baseline_children() + [
        IndirectBitPredictor(
            context_fn=None, map_size=1 << 22, lr=0.05,
            byte_indices=(-3, -1),
        ),
        IndirectBitPredictor(
            context_fn=None, map_size=1 << 22, lr=0.05,
            byte_indices=(-4, -1),
        ),
        IndirectBitPredictor(
            context_fn=None, map_size=1 << 20, lr=0.05,
            byte_indices=(-3, -2),
        ),
    ]


def stack_with_sparse_v3():
    """Add 4 sparse contexts: more skip patterns + position-offset."""
    return baseline_children() + [
        IndirectBitPredictor(
            context_fn=None, map_size=1 << 22, lr=0.05,
            byte_indices=(-3, -1),
        ),
        IndirectBitPredictor(
            context_fn=None, map_size=1 << 22, lr=0.05,
            byte_indices=(-4, -1),
        ),
        IndirectBitPredictor(
            context_fn=None, map_size=1 << 20, lr=0.05,
            byte_indices=(-3, -2),
        ),
        IndirectBitPredictor(
            context_fn=None, map_size=1 << 22, lr=0.05,
            byte_indices=(-5, -1),
        ),
    ]


def make_factory(stack_fn, weights=None):
    def factory():
        children = stack_fn()
        return MultiBitPredictor(children=children, weights=weights or [1.0] * len(children))
    return factory


def tune_and_encode(label: str, data: bytes, stack_fn, initial_weights: list[float]):
    n = len(data)
    # Tune
    t0 = time.perf_counter()
    weights, _ = tune_bit_weights(
        data, stack_fn, num_passes=1, lr_init=0.01,
        initial_weights=initial_weights, verbose=False,
    )
    tune_t = time.perf_counter() - t0
    # Encode with tuned weights
    t0 = time.perf_counter()
    blob = bit_encode(data, make_factory(stack_fn, weights.tolist()), precision=DEFAULT_BIT_PRECISION)
    enc_t = time.perf_counter() - t0
    # Roundtrip
    back = bit_decode(blob, make_factory(stack_fn, weights.tolist()), precision=DEFAULT_BIT_PRECISION)
    rt = "✓" if back == data else "✗"
    bpb = len(blob) * 8 / n
    return label, len(blob), bpb, tune_t, enc_t, rt, weights.tolist()


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

    print(f"{'variant':<48}{'bytes':>10}{'bpb':>8}{'vs gzip':>10}{'tune s':>8}{'enc s':>7}{'rt':>4}")
    print("-" * 95)

    configs = [
        ("EXPT-012 baseline (4 children, no sparse)", baseline_children,
         [0.9, 0.20, 0.12, 0.08]),
        ("EXPT-014a +2 sparse (6 children)", stack_with_sparse_v1,
         [0.9, 0.20, 0.12, 0.08, 0.10, 0.10]),
        ("EXPT-014b +3 sparse (7 children)", stack_with_sparse_v2,
         [0.9, 0.20, 0.12, 0.08, 0.10, 0.10, 0.08]),
        ("EXPT-014c +4 sparse (8 children)", stack_with_sparse_v3,
         [0.9, 0.20, 0.12, 0.08, 0.10, 0.10, 0.08, 0.08]),
    ]

    best = None
    for label, stack_fn, init in configs:
        lab, b, bpb, tune_t, enc_t, rt, w = tune_and_encode(label, data, stack_fn, init)
        delta = (b - gz) * 100 / gz
        marker = ""
        if best is None or b < best[1]:
            best = (lab, b, bpb, tune_t, enc_t, rt, delta, w)
            marker = " ◆"
        print(
            f"{label:<48}{b:>10_}{bpb:>8.4f}{delta:>+9.3f}%"
            f"{tune_t:>8.1f}{enc_t:>7.1f}{rt:>4}{marker}"
        )
        print(f"    tuned weights: {[round(x, 3) for x in w]}")

    print()
    if best:
        bl, bb, bbpb, btt, bet, brt, bd, bw = best
        verdict = "BEAT gzip" if bd < 0 else f"behind gzip {bd:+.3f}%"
        print(f"BEST: {bl}")
        print(f"  → {bb:_} bytes  {bbpb:.4f} bpb  vs gzip {bd:+.3f}%  ({verdict})")
        print(f"  tuned weights: {[round(x, 3) for x in bw]}")

    return 0


if __name__ == "__main__":
    slice_size = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
    sys.exit(main(slice_size))
