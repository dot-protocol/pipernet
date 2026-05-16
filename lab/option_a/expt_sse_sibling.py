"""
Track-B Option A — EXPT-016 redux: SSE as sibling predictor in the mix.

EXPT-013 tried SSE as a POST-MIX wrapper → null (+2-5% worse). The PAQ
pattern is to use APMs as ADDITIONAL CHILDREN in the mix, not as a remap
on top. The tuner then assigns it a weight; if SSE is useful, weight goes
up; if not, weight goes near zero.

Implementation: a thin `SSEAsPredictorWrapper(BitPredictor)` that takes
ONE child (e.g., the BytewiseBitPredictor wrapping Phase 1) and uses SSE
to produce a remapped p_one. The MultiBitPredictor sees this as a sibling
of the other 3 Indirects and the original Phase 1 child.

Hypothesis: SSE-as-sibling adds positive signal when the tuner can balance
it against the raw Phase 1 output. Expected +0-2% at 100KB.

Usage:
    python3 expt_sse_sibling.py [SLICE_BYTES]
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
    """SSE used as a STANDALONE predictor inside the mix.

    Wraps an inner BitPredictor (typically the BytewiseBitPredictor over
    Phase 1) and exposes the SSE-remapped output as its predict_bit. Updates
    both the inner predictor and the SSE table on each bit.

    This way the MultiBitPredictor sees SSE as ONE more sibling, and the
    tuner can choose to weight it more, less, or zero.
    """
    def __init__(
        self,
        inner: BitPredictor,
        context_fn: Callable[[int, int, List[int]], int],
        n_contexts: int,
        lr: float = 0.05,
    ) -> None:
        self.inner = inner
        self.context_fn = context_fn
        self.sse = SSEModel(n_contexts=n_contexts, n_bins=7, lr=lr)
        self._history: List[int] = []

    def start_byte(self) -> None:
        self.inner.start_byte()

    def predict_bit(self, bit_context: int, k: int) -> float:
        raw_p = self.inner.predict_bit(bit_context, k)
        ctx = self.context_fn(bit_context, k, self._history) % self.sse.n_contexts
        return self.sse.predict(ctx, raw_p)

    def update_bit(self, bit: int, bit_context: int, k: int) -> None:
        self.sse.update(bit)
        self.inner.update_bit(bit, bit_context, k)

    def commit_byte(self, byte: int) -> None:
        self.inner.commit_byte(byte)
        self._history.append(byte)
        if len(self._history) > 8:
            self._history = self._history[-4:]


def baseline_children():
    """EXPT-012 baseline: P1 + 3 contiguous Indirects."""
    return [
        BytewiseBitPredictor(make_byte_factory(), byte_mixer=byte_phase1_mixer),
        IndirectBitPredictor(context_fn=None, map_size=1 << 24, lr=0.05, history_window=3),
        IndirectBitPredictor(context_fn=None, map_size=1 << 22, lr=0.05, history_window=2),
        IndirectBitPredictor(context_fn=None, map_size=1 << 20, lr=0.05, history_window=1),
    ]


def stack_with_sse_sibling():
    """Add an SSE-as-predictor sibling that wraps a FRESH Phase 1 byte stack."""
    children = baseline_children()
    p1_inner = BytewiseBitPredictor(make_byte_factory(), byte_mixer=byte_phase1_mixer)
    sse_sibling = SSEPredictor(
        inner=p1_inner,
        context_fn=_ctx_by_bit_position_x_lastbyte,
        n_contexts=2048,
        lr=0.05,
    )
    children.append(sse_sibling)
    return children


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
    print(f"{'variant':<48}{'bytes':>10}{'bpb':>8}{'vs gzip':>10}{'tune s':>8}{'enc s':>7}{'rt':>4}")
    print("-" * 95)

    configs = [
        ("baseline (4 children, no SSE)", baseline_children, [0.9, 0.20, 0.12, 0.08]),
        ("+ SSE-sibling (5 children)", stack_with_sse_sibling,
         [0.9, 0.20, 0.12, 0.08, 0.15]),
    ]

    best = None
    for label, stack_fn, init in configs:
        lab, b, bpb, tt, et, rt, w = measure(label, data, stack_fn, init)
        delta = (b - gz) * 100 / gz
        marker = ""
        if best is None or b < best[1]:
            best = (lab, b, bpb, delta, w)
            marker = " ◆"
        print(f"{label:<48}{b:>10_}{bpb:>8.4f}{delta:>+9.3f}%{tt:>8.1f}{et:>7.1f}{rt:>4}{marker}")
        print(f"    tuned: {[round(x, 3) for x in w]}")

    print()
    if best:
        bl, bb, bbpb, bd, bw = best
        verdict = "BEAT gzip" if bd < 0 else f"behind {bd:+.3f}%"
        print(f"BEST: {bl} → {bb:_} bytes  vs gzip {bd:+.3f}%  ({verdict})")

    return 0


if __name__ == "__main__":
    slice_size = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
    sys.exit(main(slice_size))
