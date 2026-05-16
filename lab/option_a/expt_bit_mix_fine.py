"""
EXPT-010 fine sweep — finer probe around the (1.0, 0.25) winner from EXPT-010.

Run on 100KB enwik8 (fast) to find the precise optimum weight ratio.
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


def make_mix_factory(w_p1: float, w_ind: float):
    def factory() -> MultiBitPredictor:
        children = [
            BytewiseBitPredictor(make_byte_factory(), byte_mixer=byte_phase1_mixer),
            IndirectBitPredictor(
                context_fn=None, map_size=1 << 24, lr=0.05, history_window=3,
            ),
        ]
        return MultiBitPredictor(children, weights=[w_p1, w_ind])
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
    print(f"{'(w_phase1, w_ind)':<22}{'bytes':>10}{'bpb':>8}{'vs gzip':>10}{'enc s':>7}")
    print("-" * 57)

    sweep = [
        (1.0, 0.10),
        (1.0, 0.15),
        (1.0, 0.20),
        (1.0, 0.25),
        (1.0, 0.30),
        (1.0, 0.35),
        (1.0, 0.40),
        (0.90, 0.25),
        (1.10, 0.25),
        (1.20, 0.30),
    ]
    best = None
    for w_p1, w_ind in sweep:
        factory = make_mix_factory(w_p1, w_ind)
        t0 = time.perf_counter()
        blob = bit_encode(data, factory, precision=DEFAULT_BIT_PRECISION)
        enc_t = time.perf_counter() - t0
        bpb = len(blob) * 8 / n
        delta = (len(blob) - gz) * 100 / gz
        marker = ""
        if best is None or len(blob) < best[2]:
            best = ((w_p1, w_ind), bpb, len(blob), enc_t, delta)
            marker = " ◆"
        print(
            f"({w_p1:.2f}, {w_ind:.2f}){'':>10}{len(blob):>10_}{bpb:>8.4f}"
            f"{delta:>+9.3f}%{enc_t:>7.1f}{marker}"
        )

    print()
    if best:
        w, bpb, b, et, d = best
        print(f"BEST: weights {w} → {b:_} bytes  {bpb:.4f} bpb  vs gzip {d:+.3f}%")

    return 0


if __name__ == "__main__":
    slice_size = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
    sys.exit(main(slice_size))
