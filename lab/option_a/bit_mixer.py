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

    def update_bit(self, bit: int, bit_context: int, k: int) -> None:
        """Observe the committed bit. Update bit-level state if any.

        Default no-op for byte-wrapping predictors that only need byte-level
        state. Indirect/APM/per-bit-context predictors override this to
        advance their state machines on each bit observation.

        bit_context here is the value BEFORE the bit was shifted in; k is
        the bit position just encoded (0..7, 0=MSB).
        """

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


class IndirectBitPredictor(BitPredictor):
    """fx2-cmix Indirect-style bit-native predictor.

    Architecture (cmix/PAQ lineage):
      - Shared `map`: large byte array (~1-16 MB). Each slot holds a state byte
        encoding (count_of_1s, count_of_0s).
      - Local `predictions`: 256 floats indexed by state. predictions[s] is
        the current p(bit=1) estimate for any context that's in state s.
      - Per-byte: derive a `byte_context` hash (from the byte we're about to
        predict — or its history), seed `map_index` from that hash.
      - Per-bit: lookup state at `map[map_index + bit_context]`, predict from
        predictions[state], then advance state via NEXT_STATE table and EMA-
        update predictions[state] toward the observed bit.

    Context source: `context_fn(history)` returns the integer byte_context
    hash for the next byte. v0 uses the last 2 bytes of history → ~65k slots
    in the map. Richer hashes (order-3, sparse, last+second-to-last) are
    follow-up experiments.

    Map size: default 1 << 22 = 4 MB. Each slot is 1 byte. With ~65k byte
    contexts × 256 bit_context positions = 16.7M (slot, bit_ctx) pairs.
    A 4 MB map at modulo means collisions are common but the state machine
    is robust to them — each collision is just one extra noisy update.

    Update step (matches fx2-cmix `Perceive(bit)`):
      addr = (map_index + bit_context) % map_size
      state = map[addr]
      predictions[state] += (bit - predictions[state]) * lr
      map[addr] = NEXT_STATE[state, bit]
    """

    def __init__(
        self,
        context_fn,
        map_size: int = 1 << 22,
        lr: float = 0.1,
        history_window: int = 2,
        byte_indices: tuple[int, ...] | None = None,
    ) -> None:
        from .state import NEXT_STATE, INIT_PREDICTION
        self.context_fn = context_fn
        self.map_size = int(map_size)
        self.lr = float(lr)
        self.history_window = int(history_window)
        # byte_indices: negative offsets into history for context computation.
        # Default uses last `history_window` consecutive bytes.
        # Sparse example: (-1, -3) → use last byte + 3rd-back byte, skipping
        # the 2nd-back byte. (-1, -4) → skip 2 bytes between. Etc.
        if byte_indices is None:
            byte_indices = tuple(-i for i in range(history_window, 0, -1))
            # i.e., for history_window=3: (-3, -2, -1) — most-recent at end
        self.byte_indices = tuple(byte_indices)
        # Required history depth = max |negative index|
        self._history_needed = max(abs(i) for i in self.byte_indices)
        self._next_state = NEXT_STATE
        # Local predictions[state]: per-state EMA estimate of p(bit=1)
        self._predictions = INIT_PREDICTION.copy()
        # Shared map: state byte at each slot. Start zeroed (state = (0,0)).
        self._map = bytearray(self.map_size)
        # Recent byte history for context computation
        self._history: list[int] = []
        # Per-byte snapshot
        self._map_index: int = 0

    def _byte_context_hash(self) -> int:
        """Hash the configured byte_indices of recent history into a slot offset.

        Default (contiguous): last `history_window` bytes packed in order.
        Sparse: byte_indices like (-1, -3) pack only those positions, ignoring
        the in-between bytes — captures skip-n-gram regularities.

        Missing history (early in stream) is treated as zero — same as v0.
        """
        h = 0
        hist_len = len(self._history)
        for idx in self.byte_indices:
            # idx is negative. -1 = last, -2 = second-to-last, etc.
            pos = hist_len + idx
            b = self._history[pos] if 0 <= pos < hist_len else 0
            h = ((h << 8) | b) & 0xFFFFFFFF
        # Mix high bits via multiplication for better distribution at small maps
        h = (h * 2654435761) & 0xFFFFFFFF
        # Ensure we never start in the last 256 slots (map[map_index + 255] must fit)
        return h % (self.map_size - 256)

    def start_byte(self) -> None:
        self._map_index = self._byte_context_hash()

    def predict_bit(self, bit_context: int, k: int) -> float:
        addr = (self._map_index + bit_context) % self.map_size
        state = self._map[addr]
        return float(self._predictions[state])

    def update_bit(self, bit: int, bit_context: int, k: int) -> None:
        addr = (self._map_index + bit_context) % self.map_size
        state = self._map[addr]
        pred = self._predictions[state]
        # EMA prediction update toward observed bit
        self._predictions[state] = pred + (bit - pred) * self.lr
        # State advance
        self._map[addr] = int(self._next_state[state, bit])

    def commit_byte(self, byte: int) -> None:
        self._history.append(byte)
        # Cap history to what's needed by byte_indices (small + 1 slot for safety)
        cap = self._history_needed + 8
        if len(self._history) > cap:
            self._history = self._history[-self._history_needed:]


class MultiBitPredictor(BitPredictor):
    """Composite bit predictor: mixes multiple BitPredictors via logistic combine.

    Architecture (PAQ/cmix-style bit-level mixer):
      - Holds a list of BitPredictors (children).
      - Per bit: each child returns p_i = p(bit=1) ∈ (0, 1).
      - Combine: logit_i = log(p_i / (1 - p_i)); final_p = sigmoid(Σ w_i · logit_i).
      - Update: forward bit observation to each child's update_bit().
      - Per byte: forward start_byte / commit_byte to all children.

    Weights are fixed at construction (v0). Phase 2D-mix-tune (EXPT-011) will
    learn them online with the same SGD pattern from Phase 1.

    Numerical guard: clamp p_i ∈ [eps, 1-eps] before logit to avoid ±∞.
    """

    EPS = 1e-6

    def __init__(self, children: list[BitPredictor], weights: list[float] | None = None) -> None:
        self.children = list(children)
        if weights is None:
            weights = [1.0] * len(self.children)
        assert len(weights) == len(self.children), \
            f"weights ({len(weights)}) must match children ({len(self.children)})"
        import numpy as np
        self.weights = np.asarray(weights, dtype=np.float64)

    def start_byte(self) -> None:
        for c in self.children:
            c.start_byte()

    def predict_bit(self, bit_context: int, k: int) -> float:
        import math
        # Collect each child's p_one, convert to logit, weighted-sum, sigmoid
        s = 0.0
        for c, w in zip(self.children, self.weights):
            p = c.predict_bit(bit_context, k)
            # Clamp to (eps, 1-eps) for stable logit
            if p < self.EPS:
                p = self.EPS
            elif p > 1.0 - self.EPS:
                p = 1.0 - self.EPS
            s += float(w) * math.log(p / (1.0 - p))
        # Sigmoid with overflow guard
        if s >= 700:
            return 1.0 - self.EPS
        if s <= -700:
            return self.EPS
        import math
        return 1.0 / (1.0 + math.exp(-s))

    def update_bit(self, bit: int, bit_context: int, k: int) -> None:
        for c in self.children:
            c.update_bit(bit, bit_context, k)

    def commit_byte(self, byte: int) -> None:
        for c in self.children:
            c.commit_byte(byte)


def make_multi_factory(child_factories: list, weights: list[float] | None = None):
    """Factory: returns a function that builds a fresh MultiBitPredictor.

    Each child_factory is a zero-arg callable returning a BitPredictor.
    """
    def factory() -> MultiBitPredictor:
        children = [cf() for cf in child_factories]
        return MultiBitPredictor(children, weights=weights)
    return factory


def make_indirect_factory(
    map_size: int = 1 << 22,
    lr: float = 0.1,
    history_window: int = 2,
):
    """Factory: returns a function producing a fresh IndirectBitPredictor."""
    def factory() -> IndirectBitPredictor:
        return IndirectBitPredictor(
            context_fn=None,  # context computed internally via _history
            map_size=map_size,
            lr=lr,
            history_window=history_window,
        )
    return factory


__all__ = [
    "BitPredictor",
    "BytewiseBitPredictor",
    "IndirectBitPredictor",
    "MultiBitPredictor",
    "make_bytewise_bit_factory",
    "make_indirect_factory",
    "make_multi_factory",
    "_bit_interval",
]
