"""
Track-B Option A — EXPT-006: per-context mixer weights.

Per fx2-cmix's Mixer::GetContextData() pattern (mixer.cpp:18-41), the
single biggest source of mixer intelligence in PAQ-class compressors
is per-context weight storage. Our Phase 1 learns 5 global weights;
fx2-cmix learns weights PER unique 64-bit context hash (up to 10k slots).

v0: simplest possible per-context scheme. Context = the previous byte
(256 distinct contexts). Each context has its own 5-weight vector,
trained by online SGD. Warm-started from Phase 1's global weights.

Hypothesis: when the previous byte was space, the optimal predictor mix
is different than when the previous byte was 'a' (letter mid-word) or
'.' (sentence boundary). The optimizer should learn this and route
weight mass to whichever predictor dominates in each context.

Metric: bpb vs Phase 1 global-weight tuned logistic on 100KB enwik8.

Risk: 256 × 5 = 1280 weights vs 5 global. On 100KB ≈ 100k bytes ≈
390 updates per context average. Sparse contexts will undertrain.
Mitigation: warm-start from global weights so cold contexts default
to the known-good Phase 1 result.

Usage:
    python3 expt_per_context.py [SLICE_BYTES]
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
from option_a.mixer import multi_mix_geometric, multi_mix_logistic, DEFAULT_AC_PRECISION  # type: ignore
from option_a.predictor import ALPHA, Predictor  # type: ignore
from option_a.predictors import MarkovPredictor, MatchPredictor  # type: ignore


def make_factory():
    return [
        MarkovPredictor(),
        MatchPredictor(window=3),
        MatchPredictor(window=5),
        MatchPredictor(window=8),
        MatchPredictor(window=12),
    ]


# Phase 1 global tuned weights (from EXPT-001, 100KB enwik8)
PHASE1_WEIGHTS = np.array([0.630, 1.401, 0.995, 0.550, 2.035], dtype=np.float64)


def tune_per_context_weights(
    data: bytes,
    num_passes: int = 1,
    lr_init: float = 0.05,
    lr_decay: float = 0.9999,
    weight_clip: float = 5.0,
    warm_start: np.ndarray = PHASE1_WEIGHTS,
    verbose: bool = True,
) -> Tuple[np.ndarray, np.ndarray, float]:
    """Online SGD over per-(previous-byte)-context weight rows.

    Returns:
        (weight_table: ndarray shape (256, n_pred),
         update_counts: ndarray shape (256,) — how many updates each context got,
         total_bits)
    """
    n = len(data)
    weight_table = np.broadcast_to(warm_start, (256, len(warm_start))).copy()
    update_counts = np.zeros(256, dtype=np.int64)

    for pass_idx in range(num_passes):
        predictors = make_factory()
        n_pred = len(predictors)
        lr = lr_init
        total_bits = 0.0
        snap = max(1, n // 20)
        prev_byte = 0  # context for byte i is data[i-1]; for i=0, use 0

        for i, byte in enumerate(data):
            log_p_per_predictor = np.zeros((n_pred, ALPHA), dtype=np.float64)
            for j, p in enumerate(predictors):
                counts, total = p.predict()
                log_p_per_predictor[j] = (
                    np.log(counts.astype(np.float64)) - np.log(float(total))
                )

            # Per-context weights
            w = weight_table[prev_byte]
            log_p_mixed = (w[:, None] * log_p_per_predictor).sum(axis=0)
            log_p_mixed -= log_p_mixed.max()
            p_mixed = np.exp(log_p_mixed)
            p_mixed /= p_mixed.sum()

            total_bits += -np.log2(max(p_mixed[byte], 1e-30))

            # Gradient: E_mixed[log p_j] - log p_j(true)
            expected_log_p = (p_mixed[None, :] * log_p_per_predictor).sum(axis=1)
            actual_log_p = log_p_per_predictor[:, byte]
            gradient = expected_log_p - actual_log_p

            # SGD step — only update this context's row
            weight_table[prev_byte] -= lr * gradient
            np.clip(weight_table[prev_byte], -weight_clip, weight_clip,
                    out=weight_table[prev_byte])
            update_counts[prev_byte] += 1
            lr *= lr_decay

            for p in predictors:
                p.update(byte)

            prev_byte = byte

            if verbose and (i + 1) % snap == 0:
                avg = total_bits / (i + 1)
                print(f"  pass {pass_idx+1}/{num_passes}  byte {i+1:>8_}/{n:_}  "
                      f"avg_bpb={avg:.4f}  lr={lr:.5f}  "
                      f"unique_ctx_seen={(update_counts > 0).sum()}")

        if verbose:
            print(f"  pass {pass_idx+1}: total_bits={total_bits:_.1f} bpb={total_bits/n:.4f}")

    return weight_table, update_counts, total_bits


def make_per_context_mixer(weight_table: np.ndarray, prev_byte_ref: List[int]):
    """Factory: returns a mixer fn that uses weight_table[prev_byte_ref[0]].

    The codec calls mixer(predictors) once per byte. We need to know the
    PREVIOUS byte at each call. The encode loop in codec.py doesn't expose
    that directly, so we track it via prev_byte_ref (a mutable [byte] list)
    and update it via a wrapper. For Phase 1 simplicity here, we just feed
    in pre-tuned weights and roll with the same byte from a side channel.
    """
    from option_a.mixer import multi_mix_logistic

    def mixer(predictors):
        return multi_mix_logistic(
            predictors,
            weights=weight_table[prev_byte_ref[0]].tolist(),
            precision=DEFAULT_AC_PRECISION,
        )
    return mixer


def encode_per_context(data: bytes, factory, weight_table: np.ndarray) -> bytes:
    """encode() with a closure-tracked previous-byte context for the mixer.

    The codec's `encode` calls `mixer(predictors)` once per byte. We use a
    mutable `prev_byte` container that the codec updates between calls (we
    use a custom encode loop here since codec.encode doesn't expose prev_byte
    to the mixer). The mixer reads weight_table[prev_byte[0]] each invocation.
    """
    from option_a.codec import _MIDDLEOUT  # ensures middle-out on path
    from src.baseline import ArithmeticEncoder, _header  # type: ignore
    from option_a.mixer import multi_mix_logistic

    predictors = factory()
    enc = ArithmeticEncoder()
    prev_byte = 0
    for byte in data:
        w = weight_table[prev_byte]
        cum, total = multi_mix_logistic(
            predictors, weights=w.tolist(), precision=DEFAULT_AC_PRECISION,
        )
        enc.encode_symbol(cum[byte], cum[byte + 1], total)
        for p in predictors:
            p.update(byte)
        prev_byte = byte
    return _header(len(data)) + enc.finish()


def decode_per_context(blob: bytes, factory, weight_table: np.ndarray) -> bytes:
    """Inverse of encode_per_context — required for roundtrip verification."""
    from option_a.codec import _MIDDLEOUT
    from src.baseline import ArithmeticDecoder, _unheader  # type: ignore
    from option_a.mixer import multi_mix_logistic

    n, payload = _unheader(blob)
    predictors = factory()
    dec = ArithmeticDecoder(payload)
    out = bytearray()
    prev_byte = 0
    for _ in range(n):
        w = weight_table[prev_byte]
        cum, total = multi_mix_logistic(
            predictors, weights=w.tolist(), precision=DEFAULT_AC_PRECISION,
        )
        byte = dec.decode_symbol(cum, total)
        out.append(byte)
        for p in predictors:
            p.update(byte)
        prev_byte = byte
    return bytes(out)


def main(slice_bytes: int = 100_000, num_passes: int = 1, lr: float = 0.05) -> int:
    candidates = [Path("/tmp/enwik8_1mb"), Path("/tmp/enwik8")]
    src = next((p for p in candidates if p.exists()), None)
    if src is None:
        print("ERROR: enwik8 not found", file=sys.stderr)
        return 1
    data = src.read_bytes()[:slice_bytes]
    n = len(data)
    print(f"corpus: {src} [:{n:_}]\n")

    gz_size = len(gzip.compress(data, compresslevel=9))
    print(f"gzip-9 baseline:                {gz_size:_} bytes  bpb={gz_size*8/n:.4f}")

    # Baseline 1: track-B geometric
    t0 = time.perf_counter()
    geom_blob = encode(data, make_factory, mixer=multi_mix_geometric)
    print(f"track-B geometric:              {len(geom_blob):_} bytes  "
          f"bpb={len(geom_blob)*8/n:.4f}  enc={time.perf_counter()-t0:.2f}s")

    # Baseline 2: track-B Phase 1 global tuned weights
    def global_tuned_mixer(predictors):
        return multi_mix_logistic(predictors, weights=PHASE1_WEIGHTS.tolist())
    t0 = time.perf_counter()
    global_blob = encode(data, make_factory, mixer=global_tuned_mixer)
    print(f"track-B Phase 1 global tuned:   {len(global_blob):_} bytes  "
          f"bpb={len(global_blob)*8/n:.4f}  enc={time.perf_counter()-t0:.2f}s")

    # EXPT-006: train per-context weights via SGD
    print(f"\n[EXPT-006] tuning per-context weights (256 contexts) via SGD...")
    t0 = time.perf_counter()
    weight_table, update_counts, sgd_bits = tune_per_context_weights(
        data, num_passes=num_passes, lr_init=lr,
        warm_start=PHASE1_WEIGHTS, verbose=False,
    )
    print(f"  training wall: {time.perf_counter()-t0:.2f}s")
    print(f"  SGD total bits: {sgd_bits:_.1f}  bpb={sgd_bits/n:.4f}")
    print(f"  contexts seen: {(update_counts > 0).sum()}/256")
    print(f"  median updates/context (seen): {int(np.median(update_counts[update_counts > 0]))}")
    print(f"  max updates/context: {update_counts.max()}")

    # Encode with the trained per-context weights
    t0 = time.perf_counter()
    pc_blob = encode_per_context(data, make_factory, weight_table)
    print(f"\ntrack-B per-context tuned:      {len(pc_blob):_} bytes  "
          f"bpb={len(pc_blob)*8/n:.4f}  enc={time.perf_counter()-t0:.2f}s")

    # Roundtrip verify (CRITICAL — both halves must produce same bytes)
    t0 = time.perf_counter()
    back = decode_per_context(pc_blob, make_factory, weight_table)
    dec_t = time.perf_counter() - t0
    if back != data:
        diff = next((i for i, (a, b) in enumerate(zip(back, data)) if a != b), len(back))
        print(f"  ✗ ROUNDTRIP FAILED at byte {diff}")
        return 2
    print(f"  ✓ Roundtrip verified byte-exact  (dec={dec_t:.2f}s)")

    # Comparisons
    print(f"\n{'='*78}")
    print(f"COMPARISON:")
    print(f"  vs geometric:        {(len(pc_blob)-len(geom_blob))*100/len(geom_blob):+.3f}%")
    print(f"  vs Phase 1 global:   {(len(pc_blob)-len(global_blob))*100/len(global_blob):+.3f}%")
    print(f"  vs gzip-9:           {(len(pc_blob)-gz_size)*100/gz_size:+.3f}%")

    delta = (len(global_blob) - len(pc_blob)) * 100.0 / len(global_blob)
    gate = 0.5
    verdict = "PASS" if delta >= gate else "FAIL"
    print(f"\nEXPT-006 gate: per-context vs Phase 1 global = {delta:+.3f}%  "
          f"(target ≥{gate}% → {verdict})")
    return 0 if delta >= gate else 1


if __name__ == "__main__":
    slice_size = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
    n_passes = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    learning_rate = float(sys.argv[3]) if len(sys.argv) > 3 else 0.05
    sys.exit(main(slice_size, n_passes, learning_rate))
