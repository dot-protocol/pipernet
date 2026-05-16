"""
Track-B Option A — Experiment: extended match windows.

Phase 2 cheap-win candidate per research synthesis 2026-05-16:
StateSMix (arXiv:2605.02904) reports 1-4% gain from adding long-range
n-gram tables (k=16, k=32) on top of order-3/2-8 context layers.

In track-B's architecture this maps cleanly onto adding MatchPredictor(K=16)
and MatchPredictor(K=32) to the factory. The geometric mixer with Laplace
fallback handles missing-signal gracefully — long contexts will fire only
when a 16/32-byte string has been seen before, which on enwik8 happens for
Wikipedia template boilerplate, infobox patterns, and recurring phrases.

Method:
  1. Baseline = current 5-predictor system (Markov + Match{3,5,8,12})
  2. Extended = add Match(16) + Match(32)
  3. Tune weights on each for fair comparison
  4. Compare on 100KB enwik8

Usage:
    python3 expt_long_match.py [SLICE_BYTES] [PASSES] [LR]
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
from option_a.mixer import multi_mix_logistic, multi_mix_geometric  # type: ignore
from option_a.predictors import MarkovPredictor, MatchPredictor  # type: ignore
from option_a.tuner import tune_weights  # type: ignore


def factory_5pred():
    """Baseline: v0.3cy 5-predictor config."""
    return [
        MarkovPredictor(),
        MatchPredictor(window=3),
        MatchPredictor(window=5),
        MatchPredictor(window=8),
        MatchPredictor(window=12),
    ]


def factory_7pred():
    """Extended: 5 + Match(16) + Match(32)."""
    return factory_5pred() + [
        MatchPredictor(window=16),
        MatchPredictor(window=32),
    ]


def run(factory, label, data, num_passes, lr):
    n = len(data)
    print(f"\n{'='*78}\n[{label}]")
    print(f"  factory: {[type(p).__name__ + (f'(K={p.window})' if hasattr(p,'window') else '') for p in factory()]}")

    # Geometric baseline
    t0 = time.perf_counter()
    geom_blob = encode(data, factory, mixer=multi_mix_geometric)
    geom_t = time.perf_counter() - t0
    print(f"  geometric:  {len(geom_blob):>10_} bytes  bpb={len(geom_blob)*8/n:.4f}  enc={geom_t:.2f}s")

    # Tune weights
    import option_a.tuner as tuner
    orig_factory = tuner.make_factory
    tuner.make_factory = factory  # monkey-patch for this experiment
    try:
        t0 = time.perf_counter()
        tuned_weights, total_bits, _ = tune_weights(
            data, num_passes=num_passes, lr_init=lr, verbose=False
        )
        tune_t = time.perf_counter() - t0
    finally:
        tuner.make_factory = orig_factory

    print(f"  tune wall:  {tune_t:.2f}s  SGD bpb={total_bits/n:.4f}")
    print(f"  weights:    {[f'{w:+.3f}' for w in tuned_weights]}")

    # Encode with tuned weights
    def tuned_mixer(predictors):
        return multi_mix_logistic(predictors, weights=tuned_weights.tolist())
    t0 = time.perf_counter()
    tuned_blob = encode(data, factory, mixer=tuned_mixer)
    tuned_t = time.perf_counter() - t0
    print(f"  tuned:      {len(tuned_blob):>10_} bytes  bpb={len(tuned_blob)*8/n:.4f}  enc={tuned_t:.2f}s")
    print(f"  vs geom:    {(len(tuned_blob)-len(geom_blob))*100/len(geom_blob):+.3f}%")
    return geom_blob, tuned_blob, tuned_weights


def main(slice_bytes: int = 100_000, num_passes: int = 1, lr: float = 0.05) -> int:
    candidates = [Path("/tmp/enwik8_1mb"), Path("/tmp/enwik8")]
    src = next((p for p in candidates if p.exists()), None)
    if src is None:
        print("ERROR: enwik8 not found", file=sys.stderr)
        return 1
    data = src.read_bytes()[:slice_bytes]
    n = len(data)
    gz_size = len(gzip.compress(data, compresslevel=9))
    print(f"corpus: {src} [:{n:_}]   gzip-9 baseline: {gz_size:_} bytes ({gz_size*8/n:.4f} bpb)")

    # Run both configs
    g5, t5, w5 = run(factory_5pred, "5-predictor baseline", data, num_passes, lr)
    g7, t7, w7 = run(factory_7pred, "7-predictor extended (+Match16,+Match32)", data, num_passes, lr)

    # Cross comparison
    print(f"\n{'='*78}")
    print(f"COMPARISON (best of each config):")
    print(f"  gzip-9         : {gz_size:>10_} bytes  bpb={gz_size*8/n:.4f}")
    print(f"  5-pred tuned   : {len(t5):>10_} bytes  bpb={len(t5)*8/n:.4f}")
    print(f"  7-pred tuned   : {len(t7):>10_} bytes  bpb={len(t7)*8/n:.4f}")
    delta_pct = (len(t5) - len(t7)) * 100.0 / len(t5)
    gate = 1.0
    verdict = "PASS" if delta_pct >= gate else "FAIL"
    print(f"\n  7-pred vs 5-pred: {delta_pct:+.3f}%  (target ≥{gate}% → {verdict})")
    return 0 if delta_pct >= gate else 1


if __name__ == "__main__":
    slice_size = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
    n_passes = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    learning_rate = float(sys.argv[3]) if len(sys.argv) > 3 else 0.05
    sys.exit(main(slice_size, n_passes, learning_rate))
