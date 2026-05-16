"""
Track-B Option A — EXPT-007: per-context mixer v2.

EXPT-006 won on 100KB (-3.5% vs Phase 1 global) but lost on 1MB (+1.6%).
Diagnosis: warm-start weights came from 100KB-tuned Phase 1; on 1MB the
global optimum shifts, and lr_init=0.05 is fast enough that per-context
rows drift from the warm-start before per-context signal accumulates.

EXPT-007 tests three variants on each slice size:
  A. Re-tune Phase 1 globally on the same slice, use as warm-start
  B. Warm-start from refit global, lower lr_init (0.005)
  C. Variant A + tighter weight clip (±2 not ±5)

Goal: identify whether per-context architecturally wins at scale, or
whether 100KB was a fortunate accident.

Usage:
    python3 expt_per_context_v2.py [SLICE_BYTES]
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

from option_a.codec import encode  # type: ignore
from option_a.mixer import multi_mix_geometric, multi_mix_logistic, DEFAULT_AC_PRECISION  # type: ignore
from option_a.predictor import ALPHA  # type: ignore
from option_a.predictors import MarkovPredictor, MatchPredictor  # type: ignore
from option_a.tuner import tune_weights  # type: ignore
from option_a.expt_per_context import (  # type: ignore
    tune_per_context_weights,
    encode_per_context,
    decode_per_context,
    make_factory,
)


def run_variant(label: str, data: bytes, warm_start: np.ndarray,
                lr_init: float, weight_clip: float = 5.0):
    n = len(data)
    t0 = time.perf_counter()
    weight_table, _, _ = tune_per_context_weights(
        data, num_passes=1, lr_init=lr_init, weight_clip=weight_clip,
        warm_start=warm_start, verbose=False,
    )
    train_t = time.perf_counter() - t0

    t0 = time.perf_counter()
    blob = encode_per_context(data, make_factory, weight_table)
    enc_t = time.perf_counter() - t0
    # Roundtrip
    back = decode_per_context(blob, make_factory, weight_table)
    if back != data:
        return None, None
    bpb = len(blob) * 8 / n
    return len(blob), bpb


def main(slice_bytes: int = 1_000_000) -> int:
    candidates = [Path("/tmp/enwik8_1mb"), Path("/tmp/enwik8")]
    src = next((p for p in candidates if p.exists()), None)
    if src is None:
        print("ERROR: enwik8 not found", file=sys.stderr)
        return 1
    data = src.read_bytes()[:slice_bytes]
    n = len(data)
    print(f"corpus: {src} [:{n:_}]\n")

    gz = len(gzip.compress(data, compresslevel=9))
    print(f"gzip-9                          {gz:_} bytes  bpb={gz*8/n:.4f}")

    # Baseline 1: geometric
    t0 = time.perf_counter()
    geom_blob = encode(data, make_factory, mixer=multi_mix_geometric)
    print(f"track-B geometric               {len(geom_blob):_} bytes  "
          f"bpb={len(geom_blob)*8/n:.4f}  enc={time.perf_counter()-t0:.1f}s")

    # Baseline 2: re-tune Phase 1 globally on THIS slice
    print(f"\n[refit Phase 1 global on {n:_} bytes]")
    t0 = time.perf_counter()
    refit_global, _, _ = tune_weights(data, num_passes=1, lr_init=0.05, verbose=False)
    print(f"  refit weights: {[f'{w:+.3f}' for w in refit_global]}  ({time.perf_counter()-t0:.1f}s)")

    def refit_mixer(predictors):
        return multi_mix_logistic(predictors, weights=refit_global.tolist())
    t0 = time.perf_counter()
    refit_blob = encode(data, make_factory, mixer=refit_mixer)
    print(f"  refit Phase 1 global encoded:   {len(refit_blob):_} bytes  "
          f"bpb={len(refit_blob)*8/n:.4f}  enc={time.perf_counter()-t0:.1f}s")

    refit_n = len(refit_blob)
    print()

    # Three variants
    variants = [
        ("A. PC warm from refit, lr=0.05, clip=5", 0.05, 5.0),
        ("B. PC warm from refit, lr=0.005, clip=5", 0.005, 5.0),
        ("C. PC warm from refit, lr=0.05, clip=2", 0.05, 2.0),
        ("D. PC warm from refit, lr=0.001, clip=5", 0.001, 5.0),
    ]

    print(f"{'variant':<48}{'bytes':>10}{'bpb':>8}{'vs refit':>10}")
    print("-" * 76)
    print(f"{'(refit Phase 1 global baseline)':<48}{refit_n:>10_}{refit_n*8/n:>8.4f}{'baseline':>10}")
    for label, lr, clip in variants:
        nb, bpb = run_variant(label, data, refit_global, lr, clip)
        if nb is None:
            print(f"{label:<48}  ROUNDTRIP FAILED")
            continue
        delta = (nb - refit_n) * 100.0 / refit_n
        print(f"{label:<48}{nb:>10_}{bpb:>8.4f}{delta:>+9.3f}%")

    return 0


if __name__ == "__main__":
    slice_size = int(sys.argv[1]) if len(sys.argv) > 1 else 1_000_000
    sys.exit(main(slice_size))
