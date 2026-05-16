"""
Track-B Option A — EXPT-013: APM/SSE final stage.

Take the EXPT-012 tuned mix (Phase 1 + 3 Indirects) and wrap its output in
an SSE remap. SSE has its own state and learns alongside the mix.

Two configurations:
  1. SSE with 8-context (bit position only) — simplest
  2. SSE with 2048-context (bit_position × last_byte) — finer

Hypothesis: SSE adds +1-2% on top of EXPT-012 tuned baseline at 100KB.

Usage:
    python3 expt_apm.py [SLICE_BYTES]
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
from option_a.apm import (  # type: ignore
    SSEWrappedBitPredictor,
    _ctx_by_bit_position,
    _ctx_by_bit_position_x_lastbyte,
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


def base_children():
    return [
        BytewiseBitPredictor(make_byte_factory(), byte_mixer=byte_phase1_mixer),
        IndirectBitPredictor(context_fn=None, map_size=1 << 24, lr=0.05, history_window=3),
        IndirectBitPredictor(context_fn=None, map_size=1 << 22, lr=0.05, history_window=2),
        IndirectBitPredictor(context_fn=None, map_size=1 << 20, lr=0.05, history_window=1),
    ]


def make_mix_factory(weights):
    def factory():
        return MultiBitPredictor(children=base_children(), weights=list(weights))
    return factory


def make_sse_wrapped_factory(weights, context_fn, n_contexts: int):
    def factory():
        inner = MultiBitPredictor(children=base_children(), weights=list(weights))
        return SSEWrappedBitPredictor(
            inner=inner,
            context_fn=context_fn,
            n_contexts=n_contexts,
            n_bins=7,
            lr=0.05,
        )
    return factory


def encode_and_verify(label, data, factory):
    n = len(data)
    t0 = time.perf_counter()
    blob = bit_encode(data, factory, precision=DEFAULT_BIT_PRECISION)
    enc_t = time.perf_counter() - t0
    back = bit_decode(blob, factory, precision=DEFAULT_BIT_PRECISION)
    rt = "✓" if back == data else "✗"
    return label, len(blob), len(blob) * 8 / n, enc_t, rt


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

    # 1. Tune the mix weights (no SSE — base 4-predictor stack)
    print(f"[tune] online SGD over base mix (no SSE)...")
    initial = [0.9, 0.20, 0.12, 0.08]
    t0 = time.perf_counter()
    weights, _ = tune_bit_weights(
        data, base_children, num_passes=1, lr_init=0.01,
        initial_weights=initial, verbose=False,
    )
    tune_t = time.perf_counter() - t0
    print(f"  tuned weights: {[round(w, 4) for w in weights.tolist()]}")
    print(f"  tune wall:     {tune_t:.1f}s\n")

    print(f"{'variant':<48}{'bytes':>10}{'bpb':>8}{'vs gzip':>10}{'enc s':>7}{'rt':>4}")
    print("-" * 87)

    # Baseline: tuned mix WITHOUT SSE
    label, b, bpb, et, rt = encode_and_verify(
        "EXPT-012 baseline (tuned mix, no SSE)",
        data, make_mix_factory(weights),
    )
    base_b = b
    base_delta = (b - gz) * 100 / gz
    print(f"{label:<48}{b:>10_}{bpb:>8.4f}{base_delta:>+9.3f}%{et:>7.1f}{rt:>4}")

    # SSE wrapping with bit-position context (8 slots)
    label, b, bpb, et, rt = encode_and_verify(
        "EXPT-013a SSE-wrapped (ctx=bit_pos, 8 slots)",
        data, make_sse_wrapped_factory(weights, _ctx_by_bit_position, 8),
    )
    delta = (b - gz) * 100 / gz
    vs_base = (b - base_b) * 100 / base_b
    print(f"{label:<48}{b:>10_}{bpb:>8.4f}{delta:>+9.3f}%{et:>7.1f}{rt:>4}  vs base {vs_base:+.3f}%")

    # SSE wrapping with bit_pos × last_byte context (2048 slots)
    label, b, bpb, et, rt = encode_and_verify(
        "EXPT-013b SSE-wrapped (ctx=bit×lastbyte, 2048 slots)",
        data, make_sse_wrapped_factory(weights, _ctx_by_bit_position_x_lastbyte, 2048),
    )
    delta = (b - gz) * 100 / gz
    vs_base = (b - base_b) * 100 / base_b
    print(f"{label:<48}{b:>10_}{bpb:>8.4f}{delta:>+9.3f}%{et:>7.1f}{rt:>4}  vs base {vs_base:+.3f}%")

    return 0


if __name__ == "__main__":
    slice_size = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
    sys.exit(main(slice_size))
