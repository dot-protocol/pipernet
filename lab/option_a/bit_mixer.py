"""
Track-B Option A — Phase 2C bit-level mixer (predictor interface + byte wrapper).

Bit-level codec layer. Required to climb toward fx2-cmix's architectural
shape (indirect context models keyed on bit_context, per-bit logistic mixers,
APM/SSE chains that quantize on bit-level state, two-layer mixers with
context-keyed weights).

v0 design: a BitPredictor protocol with start_byte / predict_bit / commit_byte
hooks. The reference implementation BytewiseBitPredictor wraps an existing
byte-level mixer so we can verify byte-exact roundtrip vs the byte-level
pipeline before adding any bit-native predictors. Equivalence is the gate —
if bit-level wrapping the same byte-level mixer doesn't produce a compressed
size within ~0.5% of the byte-level codec, there is a bug.

After this lands and verifies, the door is open to:
  - bit-native indirect context model (fx2-cmix's `indirect.h`, 68 LOC)
  - APM/SSE on bit-level probabilities (Shelwien, ~60 LOC)
  - per-context bit-level mixer weights at high cardinality (1k+ contexts)

Bit ordering: MSB first. bit_context starts at 1 (sentinel). After encoding
bit k, bit_context = (bit_context << 1) | bit. This matches PAQ convention.
At the moment of predicting bit k (k=0..7), bit_context has k+1 bits total
(sentinel + k bits already encoded for this byte).
"""

from __future__ import annotations

import abc
from typing import Callable, List, Sequence

import numpy as np

from .predictor import ALPHA, Predictor
from .mixer import multi_mix_geometric


class BitPredictor(abc.ABC):
    """Bit-level prediction interface.

    The codec calls these methods once per byte:
      start_byte()                — initialise per-byte state (snapshot mixers)
      predict_bit(bit_context, k) — return p(bit=1) as a float in (0, 1)
                                    k is bits encoded so far in this byte (0..7)
                                    bit_context has k+1 bits (sentinel + k bits)
      commit_byte(byte)           — finalise byte (update underlying predictors)

    Determinism contract: same as Predictor. predict_bit must be a pure
    function of (bit_context, k, snapshot taken at start_byte). No state
    mutation in predict_bit.
    """

    @abc.abstractmethod
    def start_byte(self) -> None:
        """Snapshot any state needed for the next 8 bits."""

    @abc.abstractmethod
    def predict_bit(self, bit_context: int, k: int) -> float:
        """Return p(bit_k = 1) given bit_context and bit position k (0=MSB)."""

    @abc.abstractmethod
    def commit_byte(self, byte: int) -> None:
        """Observe the committed byte. Update internal predictor state."""

    def name(self) -> str:
        return type(self).__name__


def _bit_interval(cum: List[int], bit_context: int, k: int) -> tuple[int, int, int, int]:
    """Compute byte-index window [base, mid, end) for the current bit decision.

    Given byte-level cum_freqs and current bit-tree state:
      prefix   = byte high k bits (the bits already encoded for this byte)
      remaining = 8 - k        (bits still to encode)
      base     = prefix << remaining        (low byte index in window)
      end      = (prefix+1) << remaining    (one past high byte index)
      mid      = base + (1 << (remaining-1))  (boundary between bit=0 and bit=1)

    bit=0 region: byte indices [base, mid)
    bit=1 region: byte indices [mid, end)

    Returns (base, mid, end, remaining).
    """
    prefix = bit_context ^ (1 << k)  # strip sentinel
    remaining = 8 - k
    base = prefix << remaining
    end = base + (1 << remaining)
    mid = base + (1 << (remaining - 1))
    return base, mid, end, remaining


class BytewiseBitPredictor(BitPredictor):
    """Reference BitPredictor: wraps a byte-level mixer.

    At start_byte, snapshot the byte-level mixer's cum_freqs. At predict_bit,
    compute p_one by walking the binary tree over the cum_freqs interval —
    bit=0 region is the lower half, bit=1 is the upper half of the current
    byte-index window.

    This is mathematically equivalent to the byte-level codec: 8 nested
    arithmetic-coder calls narrowing the interval to exactly the byte's
    sub-interval. Equivalent up to integer truncation in encode_symbol; the
    compressed-size delta should be sub-1% on real data.

    NB: Snapshot cum_freqs are *byte-level integers* (precision ~1e6 from the
    mixer). predict_bit returns a float in (0, 1) — the bit_codec quantizes
    this to its own bit-level precision (2^24 default) before encoding.
    """

    def __init__(
        self,
        predictors: Sequence[Predictor],
        byte_mixer: Callable = multi_mix_geometric,
    ) -> None:
        self.predictors = list(predictors)
        self.byte_mixer = byte_mixer
        self._cum: List[int] | None = None
        self._cum_total: int = 0

    def start_byte(self) -> None:
        self._cum, self._cum_total = self.byte_mixer(self.predictors)

    def predict_bit(self, bit_context: int, k: int) -> float:
        cum = self._cum
        if cum is None:
            raise RuntimeError("predict_bit called before start_byte")
        base, mid, end, _ = _bit_interval(cum, bit_context, k)
        r_zero = cum[mid] - cum[base]
        r_one = cum[end] - cum[mid]
        total = r_zero + r_one
        if total <= 0:
            return 0.5
        return r_one / total

    def commit_byte(self, byte: int) -> None:
        for p in self.predictors:
            p.update(byte)
        self._cum = None
        self._cum_total = 0


def make_bytewise_bit_factory(
    byte_predictor_factory: Callable[[], List[Predictor]],
    byte_mixer: Callable = multi_mix_geometric,
) -> Callable[[], BytewiseBitPredictor]:
    """Convenience: turn a byte-level predictor factory into a bit factory.

    Use this to drive the bit_codec with the existing v0.3cy predictor stack.
    """
    def factory() -> BytewiseBitPredictor:
        return BytewiseBitPredictor(byte_predictor_factory(), byte_mixer=byte_mixer)
    return factory


__all__ = [
    "BitPredictor",
    "BytewiseBitPredictor",
    "make_bytewise_bit_factory",
    "_bit_interval",
]
