"""
Track-B Option A — LongMatchPredictor with O(1) rolling hash.

EXPT-022 used FNV-1a as a Python for-loop over the last `order` bytes for
every encoded byte. Knuth + Henrik's note from the 2026-05-16 room round:
that loop is the dominant cost. Replace with a Karp-Rabin polynomial hash
maintained incrementally.

Polynomial hash:
    H(b_0, b_1, ..., b_{order-1}) = sum_k b_k * P^(order-1-k)  mod 2^32

Rolling update when sliding window right by one byte (drop b_0, append b_n):
    H_new = H_old * P + b_n - b_0 * P^order  (mod 2^32)

We keep `_rolling_hash` as state, updated in `commit_byte`. `start_byte`
becomes a pure O(1) read of the precomputed hash.

Correctness preserved against the verification walk: the hash determines
the *table slot*, the byte-by-byte verification at that slot proves the
actual match. So hash quality affects collision rate, not correctness.

API identical to LongMatchPredictor in long_match.py. Drop-in replacement.
"""

from __future__ import annotations

import math
from typing import List

import numpy as np

from option_a.bit_mixer import BitPredictor


# Karp-Rabin parameters. P chosen as odd 32-bit golden-ratio prime for good mixing.
_KR_PRIME = 0x9E3779B1


class LongMatchPredictorFast(BitPredictor):
    """LongMatchPredictor with rolling hash. O(1) hash update per byte.

    Same semantics and prediction logic as the FNV version. Differs only
    in how the context hash is computed (rolling vs from-scratch).
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

        # Position+1, 0 = unset
        self.pos_map = np.zeros(map_size, dtype=np.uint32)
        self.buffer = bytearray()

        # Rolling hash state. Holds the hash of buffer[-order:] when len(buffer) >= order.
        self._rolling_hash = 0
        # Precomputed P^order mod 2^32 for the drop term.
        self._P_pow_order = pow(_KR_PRIME, order, 1 << 32)

        # Per-byte state set in start_byte and read in predict_bit.
        self._predicted_byte = -1
        self._confidence = 0.0
        self._match_length = 0
        self._last_hash = -1

    def start_byte(self) -> None:
        n = len(self.buffer)
        self._last_hash = -1
        if n < self.order:
            self._predicted_byte = -1
            self._confidence = 0.0
            self._match_length = 0
            return

        # Rolling hash is already current.
        h = self._rolling_hash & self.map_mask
        self._last_hash = h

        stored = int(self.pos_map[h])
        if stored == 0:
            self._predicted_byte = -1
            self._confidence = 0.0
            self._match_length = 0
            return

        prev_pos = stored - 1
        if prev_pos < self.order or prev_pos >= n:
            self._predicted_byte = -1
            self._confidence = 0.0
            self._match_length = 0
            return

        # Verify context match (guard against hash collisions).
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

        # Extend match backward.
        max_back = min(self.max_extend, n, prev_pos)
        while (
            match_len < max_back
            and buf[prev_pos - 1 - match_len] == buf[n - 1 - match_len]
        ):
            match_len += 1

        self._predicted_byte = buf[prev_pos]
        self._match_length = match_len
        self._confidence = 1.0 / (1.0 + math.exp(-self.slope * (match_len - self.threshold)))

    def predict_bit(self, bit_context: int, k: int) -> float:
        if self._predicted_byte < 0:
            return 0.5
        if k > 0:
            sentinel = 1 << k
            byte_prefix_observed = bit_context - sentinel
            byte_prefix_predicted = self._predicted_byte >> (8 - k)
            if byte_prefix_observed != byte_prefix_predicted:
                return 0.5
        target_bit = (self._predicted_byte >> (7 - k)) & 1
        return self._confidence if target_bit == 1 else (1.0 - self._confidence)

    def update_bit(self, bit: int, bit_context: int, k: int) -> None:
        return

    def commit_byte(self, byte: int) -> None:
        n = len(self.buffer)
        # Store table slot for the context (the just-encoded last `order` bytes
        # before this new byte) pointing at the new position.
        if self._last_hash >= 0:
            self.pos_map[self._last_hash] = (n + 1) & 0xFFFFFFFF

        # Append byte and update rolling hash.
        self.buffer.append(byte)
        n_new = n + 1  # new buffer length

        if n_new < self.order:
            # Still building up the window; recompute from scratch is fine.
            if n_new == 0:
                self._rolling_hash = 0
            else:
                # Hash of buffer[0..n_new-1] under the polynomial.
                # Will be replaced by rolling once we have `order` bytes.
                h = 0
                for b in self.buffer:
                    h = ((h * _KR_PRIME) + b) & 0xFFFFFFFF
                self._rolling_hash = h
        elif n_new == self.order:
            # First time we have a full window — compute from scratch.
            h = 0
            for b in self.buffer:
                h = ((h * _KR_PRIME) + b) & 0xFFFFFFFF
            self._rolling_hash = h
        else:
            # Rolling update: drop buffer[n_new - order - 1], append byte.
            old_byte = self.buffer[n_new - self.order - 1]
            new_byte = byte
            # H_new = H_old * P + new_byte - old_byte * P^order   (mod 2^32)
            h = (
                (self._rolling_hash * _KR_PRIME)
                + new_byte
                - (old_byte * self._P_pow_order)
            ) & 0xFFFFFFFF
            self._rolling_hash = h
