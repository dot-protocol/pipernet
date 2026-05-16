"""
Track-B Option A — Phase 2E APM/SSE (Shelwien-style probability remap).

Adaptive Probability Mapping — a per-context table that remaps the bit-level
mix output before it's quantized for the arithmetic coder. The idea (PAQ /
cmix lineage, originally Eugene Shelwien's mod_ppmd thread on encode.ru):

  - For each "context" key, store n_bins (default 7) probability values.
  - Stretch the input probability via logit, divide the logit range into
    n_bins-1 intervals, find which interval the input falls in.
  - Output: linearly interpolate between the two adjacent bin probabilities.
  - Update (on observed bit): EMA-shift the two adjacent bin probabilities
    toward the actual bit, weighted by the interpolation fraction.

In fx2-cmix the contexts are bit_context | recent-byte hashes — a few
hundred unique contexts. v0 here uses just the bit position k (0..7), so
n_contexts = 8. That's tiny on purpose to verify the mechanism. v1 will
key by (bit_context, last_byte) for ~256 × 8 = 2048 contexts.

Pluggable: `SSEWrappedBitPredictor(inner)` wraps any BitPredictor and
applies the SSE remap to its output. Drops cleanly into bit_codec.

References:
- https://encode.ru/threads/2515-mod_ppmd (Shelwien's thread)
- lab/fx2-cmix/src/mixer/sse.cpp (the 328-LOC C++ reference; we port the
  core math, not the template machinery)
"""

from __future__ import annotations

import math
from typing import Callable, List

import numpy as np

from .bit_mixer import BitPredictor


class SSEModel:
    """Stateful Shelwien-style SSE: per-context 7-bin probability remap.

    Args:
        n_contexts: number of context slots
        n_bins:     bins per context (default 7, matches fx2-cmix SSEQuant)
        lr:         EMA learning rate for adjacent-bin updates
        stretch_max: cap on logit magnitude (clamps input p to [eps, 1-eps]).
                     fx2-cmix uses 15-bit fixed-point ≈ ±10.8 in float. We
                     use ±8 for a more peaked bin distribution.
    """

    def __init__(
        self,
        n_contexts: int = 8,
        n_bins: int = 7,
        lr: float = 0.05,
        stretch_max: float = 8.0,
    ) -> None:
        self.n_contexts = n_contexts
        self.n_bins = n_bins
        self.lr = lr
        self.stretch_max = stretch_max
        # Initial table = IDENTITY remap. Each bin i (i ∈ [0, n_bins-1]) sits at
        # stretch position s_i = -stretch_max + 2*stretch_max*i/(n_bins-1). The
        # identity remap returns sigmoid(s_i) for bin i, so a freshly-initialized
        # SSE is mathematically equivalent to "pass-through" on the FIRST bit,
        # and only deviates as EMA learns. This is the correct PAQ/cmix init —
        # bad init distorts the first thousands of bits before recovery.
        bins = np.empty(n_bins, dtype=np.float64)
        for i in range(n_bins):
            s_i = -stretch_max + (2.0 * stretch_max * i) / (n_bins - 1)
            bins[i] = 1.0 / (1.0 + math.exp(-s_i))
        self.table = np.tile(bins, (n_contexts, 1)).astype(np.float64)
        # Saved state between predict() and update():
        self._last_ctx: int = 0
        self._last_idx: int = 0
        self._last_frac: float = 0.0

    def predict(self, ctx: int, raw_p: float) -> float:
        eps = 1e-6
        if raw_p < eps:
            raw_p = eps
        elif raw_p > 1.0 - eps:
            raw_p = 1.0 - eps
        # Logit (stretch)
        stretch = math.log(raw_p / (1.0 - raw_p))
        # Clamp + normalize to [0, n_bins - 1]
        sm = self.stretch_max
        if stretch > sm:
            stretch = sm
        elif stretch < -sm:
            stretch = -sm
        bin_pos = (stretch + sm) / (2.0 * sm) * (self.n_bins - 1)
        # Floor to integer + fractional part
        idx = int(bin_pos)
        if idx >= self.n_bins - 1:
            idx = self.n_bins - 2
            frac = 1.0
        else:
            frac = bin_pos - idx
        # Save for update
        self._last_ctx = ctx
        self._last_idx = idx
        self._last_frac = frac
        # Linear interpolation between adjacent bins
        return (1.0 - frac) * self.table[ctx, idx] + frac * self.table[ctx, idx + 1]

    def update(self, bit: int) -> None:
        """EMA-shift the two adjacent bin probabilities toward `bit`.

        Weighted by the interpolation fraction so the bin we "leaned on"
        gets a bigger correction.
        """
        ctx = self._last_ctx
        idx = self._last_idx
        frac = self._last_frac
        # Bin idx: contribution weight (1 - frac); bin idx+1: weight frac
        w0 = 1.0 - frac
        w1 = frac
        self.table[ctx, idx] += self.lr * w0 * (bit - self.table[ctx, idx])
        self.table[ctx, idx + 1] += self.lr * w1 * (bit - self.table[ctx, idx + 1])


# Default context functions for SSEWrappedBitPredictor
def _ctx_by_bit_position(bit_context: int, k: int, byte_history: List[int]) -> int:
    """Simplest context: just the bit position k (0..7). 8 slots total."""
    return k


def _ctx_by_bit_position_x_lastbyte(
    bit_context: int, k: int, byte_history: List[int]
) -> int:
    """Bit position × last byte. 8 × 256 = 2048 contexts."""
    last_byte = byte_history[-1] if byte_history else 0
    return (last_byte * 8) + k


class SSEWrappedBitPredictor(BitPredictor):
    """Wraps any BitPredictor; applies SSE remap to its predict_bit output.

    Drops cleanly into bit_codec — the predict_bit return is the SSE-remapped
    probability, update_bit forwards the bit to both SSE and the inner predictor.
    """

    def __init__(
        self,
        inner: BitPredictor,
        context_fn: Callable[[int, int, List[int]], int] = _ctx_by_bit_position,
        n_contexts: int = 8,
        n_bins: int = 7,
        lr: float = 0.05,
    ) -> None:
        self.inner = inner
        self.context_fn = context_fn
        self.sse = SSEModel(n_contexts=n_contexts, n_bins=n_bins, lr=lr)
        self._history: List[int] = []

    def start_byte(self) -> None:
        self.inner.start_byte()

    def predict_bit(self, bit_context: int, k: int) -> float:
        raw_p = self.inner.predict_bit(bit_context, k)
        ctx = self.context_fn(bit_context, k, self._history)
        # Modulo guard if context_fn returns more than n_contexts
        ctx = ctx % self.sse.n_contexts
        return self.sse.predict(ctx, raw_p)

    def update_bit(self, bit: int, bit_context: int, k: int) -> None:
        # SSE remembers ctx from predict; just give it the bit
        self.sse.update(bit)
        self.inner.update_bit(bit, bit_context, k)

    def commit_byte(self, byte: int) -> None:
        self.inner.commit_byte(byte)
        self._history.append(byte)
        # Keep history bounded
        if len(self._history) > 8:
            self._history = self._history[-4:]


__all__ = [
    "SSEModel",
    "SSEWrappedBitPredictor",
    "_ctx_by_bit_position",
    "_ctx_by_bit_position_x_lastbyte",
]
