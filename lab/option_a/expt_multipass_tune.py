"""
Track-B Option A — EXPT-023: Carmack's multi-pass tune.

Hypothesis: existing compose-D + LongMatch stack is under-tuned. All
prior experiments used num_passes=1, lr_init=0.01. Mahoney's PAQ tuner
runs hundreds of passes with decaying LR.

Question: does multi-pass tuning move the result by ≥0.5% on the same
stack at 1MB?

If yes → the architecture has more headroom; existing predictors
under-utilized.
If no → architecture is genuinely saturated; need new predictor classes.

Variant: compose-D + LongMatch(8,16), 11 children
  T1: num_passes=1, lr_init=0.01            (baseline tune from EXPT-022)
  T3: num_passes=3, lr_init=0.02, decay=0.5
  T5: num_passes=5, lr_init=0.03, decay=0.5

Also: split tune (first half) from eval (second half) to check
generalization. If tune-split-eval is worse than tune-on-all by >0.3%,
we're overfitting and that's its own signal.

Usage:
    python3 expt_multipass_tune.py [SLICE_BYTES]    # default 1_000_000
"""

from __future__ import annotations

import gzip
import sys
import time
from pathlib import Path
from typing import List

import numpy as np

HERE = Path(__file__).resolve().parent
LAB = HERE.parent
sys.path.insert(0, str(LAB))

from option_a.bit_codec import bit_encode, bit_decode, DEFAULT_BIT_PRECISION  # type: ignore
from option_a.bit_mixer import (  # type: ignore
    BitPredictor,
    BytewiseBitPredictor,
    IndirectBitPredictor,
    MultiBitPredictor,
)
from option_a.bit_tuner import tune_bit_weights  # type: ignore
from option_a.apm import SSEModel, _ctx_by_bit_position_x_lastbyte  # type: ignore
from option_a.long_match import LongMatchPredictor  # type: ignore
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


class SSEPredictor(BitPredictor):
    def __init__(self, inner, context_fn, n_contexts, lr=0.05):
        self.inner = inner
        self.context_fn = context_fn
        self.sse = SSEModel(n_contexts=n_contexts, n_bins=7, lr=lr)
        self._history: List[int] = []

    def start_byte(self):
        self.inner.start_byte()

    def predict_bit(self, bit_context, k):
        raw_p = self.inner.predict_bit(bit_context, k)
        ctx = self.context_fn(bit_context, k, self._history) % self.sse.n_contexts
        return self.sse.predict(ctx, raw_p)

    def update_bit(self, bit, bit_context, k):
        self.sse.update(bit)
        self.inner.update_bit(bit, bit_context, k)

    def commit_byte(self, byte):
        self.inner.commit_byte(byte)
        self._history.append(byte)
        if len(self._history) > 8:
            self._history = self._history[-4:]


def make_sse_sibling():
    p1_inner = BytewiseBitPredictor(make_byte_factory(), byte_mixer=byte_phase1_mixer)
    return SSEPredictor(
        inner=p1_inner,
        context_fn=_ctx_by_bit_position_x_lastbyte,
        n_contexts=2048,
        lr=0.05,
    )


def stack_compose_d_plus_long():
    """Compose D + LongMatch(8, 16) — 11 children."""
    return [
        BytewiseBitPredictor(make_byte_factory(), byte_mixer=byte_phase1_mixer),
        IndirectBitPredictor(context_fn=None, map_size=1 << 24, lr=0.05, history_window=3),
        IndirectBitPredictor(context_fn=None, map_size=1 << 22, lr=0.05, history_window=2),
        IndirectBitPredictor(context_fn=None, map_size=1 << 20, lr=0.05, history_window=1),
        IndirectBitPredictor(context_fn=None, map_size=1 << 22, lr=0.05, byte_indices=(-3, -1)),
        IndirectBitPredictor(context_fn=None, map_size=1 << 22, lr=0.05, byte_indices=(-4, -1)),
        IndirectBitPredictor(context_fn=None, map_size=1 << 20, lr=0.05, byte_indices=(-3, -2)),
        IndirectBitPredictor(context_fn=None, map_size=1 << 22, lr=0.05, byte_indices=(-5, -1)),
        make_sse_sibling(),
        LongMatchPredictor(order=8,  map_size=1 << 22),
        LongMatchPredictor(order=16, map_size=1 << 22),
    ]


INIT_WEIGHTS = [0.9, 0.20, 0.12, 0.08, 0.10, 0.10, 0.08, 0.08, 0.15, 0.30, 0.30]


def make_factory(stack_fn, weights):
    def factory():
        return MultiBitPredictor(children=stack_fn(), weights=list(weights))
    return factory


def measure(label, data, stack_fn, num_passes, lr_init, lr_decay, initial):
    n = len(data)
    t0 = time.perf_counter()
    weights, _ = tune_bit_weights(
        data, stack_fn, num_passes=num_passes, lr_init=lr_init, lr_decay=lr_decay,
        initial_weights=initial, verbose=False,
    )
    tt = time.perf_counter() - t0
    t0 = time.perf_counter()
    blob = bit_encode(data, make_factory(stack_fn, weights.tolist()), precision=DEFAULT_BIT_PRECISION)
    et = time.perf_counter() - t0
    back = bit_decode(blob, make_factory(stack_fn, weights.tolist()), precision=DEFAULT_BIT_PRECISION)
    rt = "✓" if back == data else "✗"
    return label, len(blob), len(blob) * 8 / n, tt, et, rt, weights.tolist()


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
        ("T1 num_passes=1 lr=0.01 (control)",        1, 0.01, 1.0),
        ("T3 num_passes=3 lr=0.02 decay=0.5",        3, 0.02, 0.5),
        ("T5 num_passes=5 lr=0.03 decay=0.5",        5, 0.03, 0.5),
    ]

    results = []
    for label, np_, lr, decay in configs:
        lab, b, bpb, tt, et, rt, w = measure(
            label, data, stack_compose_d_plus_long,
            num_passes=np_, lr_init=lr, lr_decay=decay, initial=INIT_WEIGHTS,
        )
        delta = (b - gz) * 100 / gz
        print(f"{label:<48}{b:>10_}{bpb:>8.4f}{delta:>+9.3f}%{tt:>8.1f}{et:>7.1f}{rt:>4}")
        print(f"    tuned: {[round(x, 3) for x in w]}")
        results.append((label, b, delta))

    print()
    print("=" * 80)
    base_bytes = results[0][1]
    for label, b, delta in results[1:]:
        improvement = (base_bytes - b) * 100 / base_bytes
        print(f"  {label:<48} Δ T1-control: {improvement:+.3f}%")

    return 0


if __name__ == "__main__":
    slice_size = int(sys.argv[1]) if len(sys.argv) > 1 else 1_000_000
    sys.exit(main(slice_size))
