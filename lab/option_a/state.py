"""
Track-B Option A — Phase 2D bit-level state transition tables.

For the indirect context model (fx2-cmix indirect.h port), each context slot
in the shared map holds a "state byte" 0..255. On each bit observation the
state advances via a finite-state transition: state.next(state, bit). A
prediction array indexed by state byte gives p(bit=1) for any state.

We use a simple nonstationary table: state encodes (count_of_1s, count_of_0s)
packed in a byte. Capping each count at 15 → 16x16 = 256 states. Initial
prediction = (n1 + 0.5) / (n1 + n0 + 1). Update via EMA on prediction error.

When both counts saturate at 15, we halve them (decay) so the state keeps
moving — this is the "nonstationary" part. cmix uses precomputed nonstationary
tables (paq8/paq9 lineage); we approximate with this online halving rule.

State byte encoding: state = (n1 << 4) | n0  where 0 <= n0, n1 <= 15.

This is intentionally a v0 — we expect to graduate to a fx2-cmix-style
precomputed table later (see Phase 2D-mix). The v0 captures the *architectural*
pattern correctly so the rest of the pipeline can be wired up and verified.
"""

from __future__ import annotations

import numpy as np


# Number of states in the machine. Fits in a single byte.
STATE_COUNT = 256


def _decode_state(s: int) -> tuple[int, int]:
    """state byte → (n1, n0). High nibble = count of 1s, low nibble = count of 0s."""
    return (s >> 4) & 0xF, s & 0xF


def _encode_state(n1: int, n0: int) -> int:
    """(n1, n0) → state byte. Caller guarantees 0 <= n1, n0 <= 15."""
    return ((n1 & 0xF) << 4) | (n0 & 0xF)


def _next_state(s: int, bit: int) -> int:
    """Transition: observe `bit`, increment its count, halve if both saturated."""
    n1, n0 = _decode_state(s)
    if bit == 1:
        n1 = min(n1 + 1, 15)
    else:
        n0 = min(n0 + 1, 15)
    # Nonstationary halving: if both have saturated, halve to keep moving
    if n1 == 15 and n0 == 15:
        n1 >>= 1
        n0 >>= 1
    return _encode_state(n1, n0)


def build_transition_table() -> np.ndarray:
    """Return shape (256, 2) uint8 table: next_state[state, bit] = new state.

    Indexed as next_state[state, 0] = state on bit=0, next_state[state, 1] = on bit=1.
    """
    table = np.empty((STATE_COUNT, 2), dtype=np.uint8)
    for s in range(STATE_COUNT):
        table[s, 0] = _next_state(s, 0)
        table[s, 1] = _next_state(s, 1)
    return table


def build_initial_prediction_table() -> np.ndarray:
    """Return shape (256,) float64: prediction[state] = p(bit=1) for that state.

    Laplace prior: p(bit=1) = (n1 + 0.5) / (n1 + n0 + 1). At state 0 (n1=n0=0)
    this gives 0.5. At saturated states it gives values close to 1 or 0.
    """
    pred = np.empty(STATE_COUNT, dtype=np.float64)
    for s in range(STATE_COUNT):
        n1, n0 = _decode_state(s)
        pred[s] = (n1 + 0.5) / (n1 + n0 + 1.0)
    return pred


# Module-level singletons (immutable; readers can share)
NEXT_STATE = build_transition_table()
INIT_PREDICTION = build_initial_prediction_table()


__all__ = [
    "STATE_COUNT",
    "NEXT_STATE",
    "INIT_PREDICTION",
    "build_transition_table",
    "build_initial_prediction_table",
]
