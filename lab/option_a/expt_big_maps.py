"""
Track-B Option A — EXPT-018: bigger Indirect maps + scaling test.

EXPT-009 sweep showed 1<<24 (16 MB) consistently beat 1<<22 (4 MB). At 1MB
slice each slot in a 1<<24 map gets ~0.5 updates on average (8M bits / 16M
slots), so collisions dominate but the state machine + EMA averages it out.

Two axes to probe:
  1. Even bigger maps (1<<26 = 64 MB, 1<<28 = 256 MB) at 1MB scale.
  2. Run the EXPT-014 best stack at 10MB to see if the gain pattern holds.

Hypothesis #1: bigger maps help at 1MB — fewer collisions = more accurate
state per context. Diminishing returns expected.

Hypothesis #2: scaling to 10MB shows compression gain SHRINKS over the
gzip baseline (track-b inherently steady-state; Indirect maps saturate
once each slot gets ~10+ updates).

Usage:
    python3 expt_big_maps.py [SLICE_BYTES]    # default 1_000_000
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


def stack_with_map_sizes(big_map_bits: int):
    """EXPT-012 stack but with hist=3 Indirect at variable map size."""
    return [
        BytewiseBitPredictor(make_byte_factory(), byte_mixer=byte_phase1_mixer),
        IndirectBitPredictor(context_fn=None, map_size=1 << big_map_bits, lr=0.05, history_window=3),
        IndirectBitPredictor(context_fn=None, map_size=1 << 22, lr=0.05, history_window=2),
        IndirectBitPredictor(context_fn=None, map_size=1 << 20, lr=0.05, history_window=1),
    ]


def make_factory(stack_fn, weights):
    def factory():
        return MultiBitPredictor(children=stack_fn(), weights=list(weights))
    return factory


def measure(label: str, data: bytes, stack_fn, initial_weights: list[float]):
    n = len(data)
    # Tune
    t0 = time.perf_counter()
    weights, _ = tune_bit_weights(
        data, stack_fn, num_passes=1, lr_init=0.01,
        initial_weights=initial_weights, verbose=False,
    )
    tune_t = time.perf_counter() - t0
    # Encode
    t0 = time.perf_counter()
    blob = bit_encode(data, make_factory(stack_fn, weights.tolist()), precision=DEFAULT_BIT_PRECISION)
    enc_t = time.perf_counter() - t0
    # Roundtrip
    back = bit_decode(blob, make_factory(stack_fn, weights.tolist()), precision=DEFAULT_BIT_PRECISION)
    rt = "✓" if back == data else "✗"
    return label, len(blob), len(blob) * 8 / n, tune_t, enc_t, rt, weights.tolist()


def main(slice_bytes: int = 1_000_000) -> int:
    candidates = [Path("/tmp/enwik8"), Path("/tmp/enwik8_1mb")]
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
        ("baseline hist=3 map=1<<24 (16 MB)", 24),
        ("hist=3 map=1<<25 (32 MB)",          25),
        ("hist=3 map=1<<26 (64 MB)",          26),
        ("hist=3 map=1<<27 (128 MB)",         27),
    ]

    best = None
    for label, mbits in configs:
        stack_fn = lambda mbits=mbits: stack_with_map_sizes(mbits)
        lab, b, bpb, tt, et, rt, w = measure(label, data, stack_fn, [0.9, 0.20, 0.12, 0.08])
        delta = (b - gz) * 100 / gz
        marker = ""
        if best is None or b < best[1]:
            best = (lab, b, bpb, tt, et, rt, delta, w)
            marker = " ◆"
        print(f"{label:<48}{b:>10_}{bpb:>8.4f}{delta:>+9.3f}%{tt:>8.1f}{et:>7.1f}{rt:>4}{marker}")
        print(f"    tuned: {[round(x, 3) for x in w]}")

    print()
    if best:
        bl, bb, bbpb, btt, bet, brt, bd, bw = best
        verdict = "BEAT gzip" if bd < 0 else f"behind gzip {bd:+.3f}%"
        print(f"BEST: {bl}")
        print(f"  → {bb:_} bytes  {bbpb:.4f} bpb  vs gzip {bd:+.3f}%  ({verdict})")

    return 0


if __name__ == "__main__":
    slice_size = int(sys.argv[1]) if len(sys.argv) > 1 else 1_000_000
    sys.exit(main(slice_size))
