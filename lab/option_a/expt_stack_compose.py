"""
Track-B Option A — EXPT-020: stack composition.

EXPT-014/016/019 each landed individual wins at 1MB:
  +sparse-4 (8 children):   +0.98% over baseline
  +SSE-sibling:             +2.42% over baseline
  +WRT (incl dict):         +0.38% over baseline

Question: do they stack additively, or sub-additively?

Stack variants tested:
  A. baseline 4-child                            (control)
  B. + sparse-4                                  (EXPT-014c)
  C. + SSE-sibling                               (EXPT-016)
  D. + sparse-4 + SSE-sibling                    (compose 2)
  E. WRT(data) → + sparse-4 + SSE-sibling        (compose 3)

Tuner picks per-child weights for each variant. Expectation: composition
saturates somewhere below 3.78% (additive sum), because both sparse and
SSE compete to capture the same residual signal — but at least 3.0%
combined is the floor we want to beat.

Usage:
    python3 expt_stack_compose.py [SLICE_BYTES]
"""

from __future__ import annotations

import gzip
import sys
import time
from pathlib import Path
from typing import Callable, List

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
from option_a.mixer import multi_mix_logistic  # type: ignore
from option_a.predictors import MarkovPredictor, MatchPredictor  # type: ignore
from option_a.wrt import build_dictionary, encode_wrt, decode_wrt  # type: ignore


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
    """SSE-as-sibling (from EXPT-016). Wraps a fresh P1 inner."""
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


def baseline_children():
    """EXPT-012 baseline: P1 + 3 contiguous Indirects."""
    return [
        BytewiseBitPredictor(make_byte_factory(), byte_mixer=byte_phase1_mixer),
        IndirectBitPredictor(context_fn=None, map_size=1 << 24, lr=0.05, history_window=3),
        IndirectBitPredictor(context_fn=None, map_size=1 << 22, lr=0.05, history_window=2),
        IndirectBitPredictor(context_fn=None, map_size=1 << 20, lr=0.05, history_window=1),
    ]


def stack_sparse():
    """EXPT-014c: baseline + 4 sparse Indirects."""
    return baseline_children() + [
        IndirectBitPredictor(context_fn=None, map_size=1 << 22, lr=0.05, byte_indices=(-3, -1)),
        IndirectBitPredictor(context_fn=None, map_size=1 << 22, lr=0.05, byte_indices=(-4, -1)),
        IndirectBitPredictor(context_fn=None, map_size=1 << 20, lr=0.05, byte_indices=(-3, -2)),
        IndirectBitPredictor(context_fn=None, map_size=1 << 22, lr=0.05, byte_indices=(-5, -1)),
    ]


def stack_sse():
    """EXPT-016: baseline + SSE-sibling."""
    return baseline_children() + [make_sse_sibling()]


def stack_sparse_sse():
    """Compose 2: baseline + 4 sparse + SSE-sibling (9 children)."""
    return baseline_children() + [
        IndirectBitPredictor(context_fn=None, map_size=1 << 22, lr=0.05, byte_indices=(-3, -1)),
        IndirectBitPredictor(context_fn=None, map_size=1 << 22, lr=0.05, byte_indices=(-4, -1)),
        IndirectBitPredictor(context_fn=None, map_size=1 << 20, lr=0.05, byte_indices=(-3, -2)),
        IndirectBitPredictor(context_fn=None, map_size=1 << 22, lr=0.05, byte_indices=(-5, -1)),
        make_sse_sibling(),
    ]


def make_factory(stack_fn, weights):
    def factory():
        return MultiBitPredictor(children=stack_fn(), weights=list(weights))
    return factory


def measure(label, data, stack_fn, initial):
    n = len(data)
    t0 = time.perf_counter()
    weights, _ = tune_bit_weights(
        data, stack_fn, num_passes=1, lr_init=0.01,
        initial_weights=initial, verbose=False,
    )
    tt = time.perf_counter() - t0
    t0 = time.perf_counter()
    blob = bit_encode(data, make_factory(stack_fn, weights.tolist()), precision=DEFAULT_BIT_PRECISION)
    et = time.perf_counter() - t0
    back = bit_decode(blob, make_factory(stack_fn, weights.tolist()), precision=DEFAULT_BIT_PRECISION)
    rt = "✓" if back == data else "✗"
    return label, len(blob), len(blob) * 8 / n, tt, et, rt, weights.tolist()


def main(slice_bytes: int = 100_000) -> int:
    candidates = [Path("/tmp/enwik8"), Path("/tmp/enwik8_1mb")]
    src = next((p for p in candidates if p.exists()), None)
    if src is None:
        print("ERROR: enwik8 not found", file=sys.stderr)
        return 1
    data = src.read_bytes()[:slice_bytes]
    n = len(data)
    gz = len(gzip.compress(data, compresslevel=9))
    print(f"corpus: {src} [:{n:_}]   gzip-9: {gz:_} bytes ({gz*8/n:.4f} bpb)\n")

    # WRT preprocessing for the WRT-path variant
    print(f"[WRT preprocess]")
    t0 = time.perf_counter()
    dictionary = build_dictionary(data, max_entries=315, min_word_len=3)
    dict_t = time.perf_counter() - t0
    t0 = time.perf_counter()
    wrt_data = encode_wrt(data, dictionary)
    wrt_enc_t = time.perf_counter() - t0
    dict_overhead = sum(len(w) + 1 for w in dictionary)
    decoded_test = decode_wrt(wrt_data, dictionary)
    if decoded_test != data:
        print(f"WRT roundtrip BROKEN — abort")
        return 2
    print(f"  dictionary entries: {len(dictionary)}  wrt(data): {len(wrt_data):_} bytes  dict_overhead: {dict_overhead:_}")
    print()

    print(f"{'variant':<48}{'bytes':>10}{'bpb':>8}{'vs gzip':>10}{'tune s':>8}{'enc s':>7}{'rt':>4}")
    print("-" * 95)

    configs_raw = [
        ("A. baseline (4 children)",                 baseline_children,  [0.9, 0.20, 0.12, 0.08]),
        ("B. + sparse-4 (8 children)",               stack_sparse,       [0.9, 0.20, 0.12, 0.08, 0.10, 0.10, 0.08, 0.08]),
        ("C. + SSE-sibling (5 children)",            stack_sse,          [0.9, 0.20, 0.12, 0.08, 0.15]),
        ("D. + sparse-4 + SSE-sibling (9 children)", stack_sparse_sse,   [0.9, 0.20, 0.12, 0.08, 0.10, 0.10, 0.08, 0.08, 0.15]),
    ]

    results = []
    for label, stack_fn, init in configs_raw:
        lab, b, bpb, tt, et, rt, w = measure(label, data, stack_fn, init)
        delta = (b - gz) * 100 / gz
        print(f"{label:<48}{b:>10_}{bpb:>8.4f}{delta:>+9.3f}%{tt:>8.1f}{et:>7.1f}{rt:>4}")
        print(f"    tuned: {[round(x, 3) for x in w]}")
        results.append((label, b, delta))

    # E: WRT-encoded data through the compose-3 stack
    lab, b_wrt, bpb, tt, et, rt, w = measure(
        "E. WRT + sparse-4 + SSE-sibling (9 children)",
        wrt_data, stack_sparse_sse,
        [0.9, 0.20, 0.12, 0.08, 0.10, 0.10, 0.08, 0.08, 0.15],
    )
    total_wrt = b_wrt + dict_overhead
    delta_total = (total_wrt - gz) * 100 / gz
    print(f"{lab:<48}{b_wrt:>10_}{bpb:>8.4f}{(b_wrt - gz)*100/gz:>+9.3f}%{tt:>8.1f}{et:>7.1f}{rt:>4}")
    print(f"    + dict ({dict_overhead:_}) → total {total_wrt:_}, vs gzip {delta_total:+.3f}%")
    print(f"    tuned: {[round(x, 3) for x in w]}")
    results.append(("E. WRT + sparse-4 + SSE-sibling (total)", total_wrt, delta_total))

    print()
    print("=" * 80)
    base_bytes = results[0][1]
    for label, b, delta in results[1:]:
        improvement = (base_bytes - b) * 100 / base_bytes
        print(f"  {label:<48} {b:>10_}  Δ baseline: {improvement:+.3f}%")

    return 0


if __name__ == "__main__":
    slice_size = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
    sys.exit(main(slice_size))
