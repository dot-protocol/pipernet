"""
Track-B Option A — long-range match predictor (LZ77-style, hash-of-context).

The gap the audit identified: every existing predictor sees ≤8 bytes back.
Wikipedia has structure at 50-500 byte ranges (repeated phrases, infobox
templates, link patterns, paragraph topics) that the Indirect/Match/SSE
stack cannot reach.

This predictor closes that gap.

Mechanism (per byte to encode):
  1. Hash the last `order` bytes (the "context").
  2. Look up that hash in pos_map → previous position N' where the same
     context was seen.
  3. The byte at buffer[N'] is what FOLLOWED that context last time. Use
     it as the prediction for the current byte.
  4. Walk back from N' to verify and extend the match length (handles
     hash collisions and gives us a confidence score).
  5. Confidence = sigmoid((match_length - threshold) * slope). Short
     match → near-uniform. Long match → near-deterministic.

Bit-level adaptation:
  At bit position k (after k bits of the current byte are known), the
  bit_context already locks in the top-k bits of any predicted byte.
  If predicted_byte's top-k bits match bit_context, we predict its bit-k
  with `confidence`. If they don't match, the prediction is dead → 0.5.

This sidesteps the bit-tree snapshot that BytewiseBitPredictor needs,
because the long-match prediction is naturally concentrated on a single
byte (not a distribution over 256).

Memory: one np.uint32[map_size] per order. Default map_size=1<<22 = 16 MB
per order. For 3 orders (4, 8, 16): ~48 MB total. Lookup is O(1) hash +
short verification walk.

Constructed as a `BitPredictor` so it plugs directly into
`MultiBitPredictor` and the tuner.
"""

from __future__ import annotations

import math
from typing import List

import numpy as np

from option_a.bit_mixer import BitPredictor


# FNV-1a-style multiplicative hash. Cheap, decent mixing.
_HASH_PRIME = 0x01000193
_HASH_SEED = 0x811C9DC5


class LongMatchPredictor(BitPredictor):
    """LZ77-style long-range match predictor.

    Args:
        order: number of bytes in the context to hash.
        map_size: must be power of two; controls hash table size.
        confidence_threshold: match length at which p ≈ 0.5 (typical 4).
        confidence_slope: how fast confidence ramps with match length
            (typical 0.5 → length=8 gives ~0.88, length=16 gives ~0.997).
        max_match_extend: cap on backward-walk to bound runtime.
    """

    def __init__(
        self,
        order: int = 8,
        map_size: int = 1 << 22,
        confidence_threshold: float = 4.0,
        confidence_slope: float = 0.5,
        max_match_extend: int = 64,
    ) -> None:
        assert (map_size & (map_size - 1)) == 0, "map_size must be power of 2"
        self.order = order
        self.map_size = map_size
        self.map_mask = map_size - 1
        self.threshold = confidence_threshold
        self.slope = confidence_slope
        self.max_extend = max_match_extend

        # Store position + 1, so 0 = unset (lets us use np.uint32 zero-init).
        self.pos_map = np.zeros(map_size, dtype=np.uint32)
        self.buffer = bytearray()

        # Per-byte state, set in start_byte() and read in predict_bit().
        self._predicted_byte = -1
        self._confidence = 0.0
        self._match_length = 0
        self._last_hash = -1  # cached for commit_byte

    def _hash_ctx(self, buf: bytes) -> int:
        """FNV-1a 32-bit over the last `order` bytes."""
        h = _HASH_SEED
        for b in buf:
            h = ((h ^ b) * _HASH_PRIME) & 0xFFFFFFFF
        return h & self.map_mask

    def start_byte(self) -> None:
        n = len(self.buffer)
        self._last_hash = -1
        if n < self.order:
            self._predicted_byte = -1
            self._confidence = 0.0
            self._match_length = 0
            return

        ctx = bytes(self.buffer[n - self.order:n])
        h = self._hash_ctx(ctx)
        self._last_hash = h

        stored = int(self.pos_map[h])
        if stored == 0:
            self._predicted_byte = -1
            self._confidence = 0.0
            self._match_length = 0
            return

        # stored = (position of the byte that followed this context) + 1
        prev_pos = stored - 1
        if prev_pos < self.order or prev_pos >= n:
            self._predicted_byte = -1
            self._confidence = 0.0
            self._match_length = 0
            return

        # Verify the context matches at prev_pos (guard against hash collisions).
        # Context at prev_pos is buffer[prev_pos - order : prev_pos]
        buf = self.buffer
        match_len = 0
        for k in range(self.order):
            if buf[prev_pos - 1 - k] != buf[n - 1 - k]:
                break
            match_len += 1
        if match_len < self.order:
            self._predicted_byte = -1
            self._confidence = 0.0
            self._match_length = 0
            return

        # Extend backward beyond `order` to get full match length.
        max_back = min(self.max_extend, n, prev_pos)
        while (
            match_len < max_back
            and buf[prev_pos - 1 - match_len] == buf[n - 1 - match_len]
        ):
            match_len += 1

        self._predicted_byte = buf[prev_pos]
        self._match_length = match_len
        # Sigmoid confidence on length.
        self._confidence = 1.0 / (1.0 + math.exp(-self.slope * (match_len - self.threshold)))

    def predict_bit(self, bit_context: int, k: int) -> float:
        if self._predicted_byte < 0:
            return 0.5
        # Check predicted_byte is still consistent with bit_context.
        # bit_context holds the top `k` bits of the byte being decoded
        # (left-extended by the sentinel 1-bit). Actually bit_context = 1 ◯
        # (k bits). The top k bits of the predicted byte should equal the
        # bottom k bits of bit_context (i.e., bit_context minus its sentinel).
        if k > 0:
            sentinel = 1 << k
            byte_prefix_observed = bit_context - sentinel  # the k bits seen
            byte_prefix_predicted = self._predicted_byte >> (8 - k)
            if byte_prefix_observed != byte_prefix_predicted:
                return 0.5
        # Predict bit k of predicted_byte.
        target_bit = (self._predicted_byte >> (7 - k)) & 1
        return self._confidence if target_bit == 1 else (1.0 - self._confidence)

    def update_bit(self, bit: int, bit_context: int, k: int) -> None:
        # Long-match predictor is stateless during the byte. The state update
        # happens once per byte in commit_byte.
        return

    def commit_byte(self, byte: int) -> None:
        # Record: the just-encoded context (last `order` bytes BEFORE this byte)
        # was followed by `byte` at position len(buffer). Store position+1.
        n = len(self.buffer)
        if self._last_hash >= 0:
            # The byte being committed lands at position n (current buffer length).
            self.pos_map[self._last_hash] = (n + 1) & 0xFFFFFFFF
        self.buffer.append(byte)


def make_long_match_stack(orders=(4, 8, 16), map_size: int = 1 << 22) -> List[LongMatchPredictor]:
    """Build a stack of LongMatchPredictors at multiple orders.

    Defaults to (4, 8, 16) which covers short→mid→long range.
    """
    return [LongMatchPredictor(order=o, map_size=map_size) for o in orders]
