"""
Track-B Option A — adaptive weight tuner for the logistic mixer.

Trains per-predictor weights online via SGD on the negative log-likelihood
loss. This is "Logistic Mixing" (LR-Mixing) from PAQ/cmix literature.

Gradient derivation:
    P_mix(x) = (1/Z) · exp(Σ_i w_i · log p_i(x))
    L = -log P_mix(true) = log Z - Σ_i w_i · log p_i(true)
    ∂L/∂w_j = E_{x~P_mix}[log p_j(x)] - log p_j(true)

Intuition:
    If predictor j assigned HIGHER probability to the actual byte than its
    expected-log-prob under the current mix, that's evidence j is useful —
    its gradient is negative, we ADD to its weight (gradient descent
    subtracts gradient).

    If predictor j was systematically off (assigned lower prob to actuals
    than its average prediction), gradient is positive, we SUBTRACT weight.

Phase 1 ships GLOBAL weights — one scalar per predictor, learned online.
Per-context weights (cmix uses these) are a Phase 2 stretch goal.

Usage:
    python3 tuner.py [SLICE_BYTES] [NUM_PASSES] [LR]

    Default: 100000 bytes, 1 pass, lr=0.01

Reports learned weights and total cost in bits. Then runs a full
encode pass with the tuned weights and reports compressed blob size
for honest comparison against geometric baseline.
"""

from __future__ import annotations

import gzip
import sys
import time
from pathlib import Path
from typing import List, Tuple

import numpy as np

HERE = Path(__file__).resolve().parent
LAB = HERE.parent
sys.path.insert(0, str(LAB))

from option_a.codec import encode  # type: ignore
from option_a.mixer import (  # type: ignore
    multi_mix_logistic,
    multi_mix_geometric,
    DEFAULT_AC_PRECISION,
    HIGH_AC_PRECISION,
)
from option_a.predictor import ALPHA, Predictor  # type: ignore
from option_a.predictors import MarkovPredictor, MatchPredictor  # type: ignore


def make_factory():
    """v0.3cy baseline configuration."""
    return [
        MarkovPredictor(),
        MatchPredictor(window=3),
        MatchPredictor(window=5),
        MatchPredictor(window=8),
        MatchPredictor(window=12),
    ]


def tune_weights(
    data: bytes,
    num_passes: int = 1,
    lr_init: float = 0.05,
    lr_decay: float = 0.9999,
    weight_clip: float = 5.0,
    verbose: bool = True,
) -> Tuple[np.ndarray, float, List[float]]:
    """Online SGD on logistic mixer weights.

    Returns:
        (final_weights, total_bits, weight_history)
        weight_history is a list of weight snapshots taken every N bytes
        for plotting/diagnostics
    """
    n = len(data)
    snapshots: List[float] = []

    for pass_idx in range(num_passes):
        predictors = make_factory()
        n_pred = len(predictors)
        if pass_idx == 0:
            weights = np.ones(n_pred, dtype=np.float64)
        # else: weights persist from prior pass
        lr = lr_init
        total_bits = 0.0
        snap_interval = max(1, n // 20)

        for i, byte in enumerate(data):
            # Collect predictions
            log_p_per_predictor = np.zeros((n_pred, ALPHA), dtype=np.float64)
            counts_per_pred = []
            for j, p in enumerate(predictors):
                counts, total = p.predict()
                log_p_per_predictor[j] = (
                    np.log(counts.astype(np.float64)) - np.log(float(total))
                )
                counts_per_pred.append((counts, total))

            # Mixed log-probs in log-domain
            log_p_mixed = (weights[:, None] * log_p_per_predictor).sum(axis=0)  # (ALPHA,)
            # Softmax for numerical stability
            log_p_mixed -= log_p_mixed.max()
            p_mixed = np.exp(log_p_mixed)
            p_mixed /= p_mixed.sum()

            # Cost for this byte (in bits)
            byte_bits = -np.log2(max(p_mixed[byte], 1e-30))
            total_bits += byte_bits

            # Gradient: E_mixed[log p_j] - log p_j(true) per predictor
            expected_log_p = (p_mixed[None, :] * log_p_per_predictor).sum(axis=1)  # (n_pred,)
            actual_log_p = log_p_per_predictor[:, byte]  # (n_pred,)
            gradient = expected_log_p - actual_log_p

            # SGD step: w_j -= lr * gradient_j
            weights -= lr * gradient
            # Clip weights to keep mixer numerically sane
            np.clip(weights, -weight_clip, weight_clip, out=weights)
            lr *= lr_decay

            # Update all predictors with the actual byte
            for p in predictors:
                p.update(byte)

            if (i + 1) % snap_interval == 0:
                snapshots.append((i + 1, weights.copy(), total_bits))
                if verbose:
                    avg_bpb = total_bits / (i + 1)
                    print(f"  pass {pass_idx+1}/{num_passes}  byte {i+1:>8_}/{n:_}  "
                          f"avg_bpb={avg_bpb:.4f}  lr={lr:.5f}  "
                          f"weights=[{' '.join(f'{w:+.3f}' for w in weights)}]")

        if verbose:
            print(f"  pass {pass_idx+1} complete: total_bits={total_bits:_.1f}  bpb={total_bits/n:.4f}")
            print(f"  final weights: {weights}")

    return weights, total_bits, snapshots


def main(slice_bytes: int = 100_000, num_passes: int = 1, lr: float = 0.05) -> int:
    # Locate corpus
    candidates = [Path("/tmp/enwik8_1mb"), Path("/tmp/enwik8")]
    src = next((p for p in candidates if p.exists()), None)
    if src is None:
        print("ERROR: enwik8 not found", file=sys.stderr)
        return 1

    data = src.read_bytes()[:slice_bytes]
    n = len(data)
    print(f"corpus: {src} [:{n:_}]")
    print(f"passes: {num_passes}  initial_lr: {lr}")
    print("-" * 78)

    # Baselines
    gz_size = len(gzip.compress(data, compresslevel=9))
    print(f"gzip-9 baseline:        {gz_size:>10_} bytes  bpb={gz_size*8/n:.4f}")

    # Geometric (v0.3cy parity) — actual encode to get real byte count
    print(f"\n[1] geometric mix (v0.3cy parity)")
    t0 = time.perf_counter()
    geom_blob = encode(data, make_factory, mixer=multi_mix_geometric)
    geom_t = time.perf_counter() - t0
    print(f"  encode:               {len(geom_blob):>10_} bytes  bpb={len(geom_blob)*8/n:.4f}  enc={geom_t:.2f}s")
    print(f"  vs gzip:              {(len(geom_blob)-gz_size)*100/gz_size:+.3f}%")

    # Logistic with uniform weights — should equal geometric (or very close)
    print(f"\n[2] logistic mix, uniform weights, default precision (= geometric)")
    t0 = time.perf_counter()
    log_uniform_blob = encode(data, make_factory, mixer=multi_mix_logistic)
    log_uniform_t = time.perf_counter() - t0
    print(f"  encode:               {len(log_uniform_blob):>10_} bytes  bpb={len(log_uniform_blob)*8/n:.4f}  enc={log_uniform_t:.2f}s")
    print(f"  vs gzip:              {(len(log_uniform_blob)-gz_size)*100/gz_size:+.3f}%")
    print(f"  vs geometric:         {(len(log_uniform_blob)-len(geom_blob))*100/len(geom_blob):+.3f}%")

    # Tune weights via online SGD
    print(f"\n[3] training adaptive weights via online SGD")
    t0 = time.perf_counter()
    tuned_weights, total_bits, snapshots = tune_weights(
        data, num_passes=num_passes, lr_init=lr, verbose=True
    )
    tune_t = time.perf_counter() - t0
    print(f"  tuning wall:          {tune_t:.2f}s")
    print(f"  SGD total bits:       {total_bits:_.1f}  bpb={total_bits/n:.4f}")
    print(f"  tuned weights:        {tuned_weights}")

    # Encode with tuned weights at DEFAULT precision (1e6)
    print(f"\n[4a] encode with tuned weights @ default precision (1e6)")
    def tuned_mixer_default(predictors):
        return multi_mix_logistic(
            predictors, weights=tuned_weights.tolist(),
            precision=DEFAULT_AC_PRECISION,
        )
    t0 = time.perf_counter()
    tuned_blob = encode(data, make_factory, mixer=tuned_mixer_default)
    tuned_t = time.perf_counter() - t0
    print(f"  encode:               {len(tuned_blob):>10_} bytes  bpb={len(tuned_blob)*8/n:.4f}  enc={tuned_t:.2f}s")
    print(f"  vs gzip:              {(len(tuned_blob)-gz_size)*100/gz_size:+.3f}%")
    print(f"  vs geometric:         {(len(tuned_blob)-len(geom_blob))*100/len(geom_blob):+.3f}%")

    # Encode with tuned weights at HIGH precision (2^24)
    print(f"\n[4b] encode with tuned weights @ HIGH precision (2^24)")
    def tuned_mixer_hp(predictors):
        return multi_mix_logistic(
            predictors, weights=tuned_weights.tolist(),
            precision=HIGH_AC_PRECISION,
        )
    t0 = time.perf_counter()
    tuned_blob_hp = encode(data, make_factory, mixer=tuned_mixer_hp)
    tuned_hp_t = time.perf_counter() - t0
    print(f"  encode:               {len(tuned_blob_hp):>10_} bytes  bpb={len(tuned_blob_hp)*8/n:.4f}  enc={tuned_hp_t:.2f}s")
    print(f"  vs gzip:              {(len(tuned_blob_hp)-gz_size)*100/gz_size:+.3f}%")
    print(f"  vs geometric:         {(len(tuned_blob_hp)-len(geom_blob))*100/len(geom_blob):+.3f}%")
    print(f"  vs tuned@1e6:         {(len(tuned_blob_hp)-len(tuned_blob))*100/len(tuned_blob):+.3f}%")

    # Best of the two for the gate
    if len(tuned_blob_hp) < len(tuned_blob):
        best_blob = tuned_blob_hp
        best_label = "tuned@2^24"
    else:
        best_blob = tuned_blob
        best_label = "tuned@1e6"

    # Phase 1 decision gate (use BEST of default/HP precision)
    delta = (len(geom_blob) - len(best_blob)) * 100.0 / len(geom_blob)
    gate_target = 0.5
    verdict = "PASS" if delta >= gate_target else "FAIL"
    print()
    print("=" * 78)
    print(f"Phase 1 decision gate: best ({best_label}) vs geometric = {delta:+.3f}%")
    print(f"  Target: ≥{gate_target}% improvement → {verdict}")
    if verdict == "PASS":
        print(f"  → switch default mixer to logistic for Phase 2+")
        print(f"  → tuned weights: {tuned_weights.tolist()}")
        print(f"  → precision: {'HIGH (2^24)' if best_label == 'tuned@2^24' else 'DEFAULT (1e6)'}")
    else:
        print(f"  → geometric stays default; logistic kept as opt-in")

    return 0 if delta >= gate_target else 1


if __name__ == "__main__":
    slice_size = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
    n_passes = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    learning_rate = float(sys.argv[3]) if len(sys.argv) > 3 else 0.05
    sys.exit(main(slice_size, n_passes, learning_rate))
