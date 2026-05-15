"""
Track-B Option A — Predictor interface.

Every sub-model in the cmix-family mixer implements this protocol. Two methods:

    predict() -> (counts: np.ndarray[uint32, 256], total: uint32)
        Return Laplace-smoothed count distribution for the next byte.
        `counts` MUST have length 256 and dtype uint32.
        `total` MUST equal sum(counts) and be > 0 (Laplace floor guarantees ≥256).

    update(byte: int) -> None
        Observe an actual byte. Update internal state for the next predict().
        Called once per byte in both encode and decode after the symbol is
        committed to the arithmetic coder.

Determinism contract:
    Calling predict() then update(b) MUST leave the predictor in the same
    state as calling them in the same order on a freshly-constructed instance
    over the same byte stream. No randomness, no wall-clock dependency, no
    process-shared state. The decoder relies on this — both sides run the
    same predictor code over the same prefix and MUST produce identical counts.

Composition:
    The mixer (geometric mean or logistic) takes a list of Predictor instances
    and combines their distributions into one final cum_freqs array which the
    arithmetic coder uses for symbol encoding. Each predictor's predict() is
    called once per byte; each update() is called once per byte after the
    symbol is committed.

Implementations live in predictors/:
    markov.py     — order-3 Markov (wraps existing CMarkovCounts)
    match.py      — K-byte exact context match (wraps existing CMatchModel)
    sparse.py     — skip-n-gram patterns (NEW)
    rle.py        — run-length-aware match (NEW)
    indirect.py   — context-of-context predictor (NEW)
    apm.py        — APM layer applied after mix (Predictor that consumes a
                    pre-mixed distribution and remaps it; not a primary
                    predictor — wraps the mixer output)
    ssm.py        — Bellard's path: micro-RWKV / Mamba-tiny (NEW)

Performance note:
    Cython implementations of the same protocol expose `cpdef predict()` and
    `cpdef update()` at the cdef-class level. Python wrappers delegate. The
    mixer accepts both Python-shaped and Cython-shaped predictors via duck
    typing — both expose .predict() and .update().
"""

from __future__ import annotations

import abc
from typing import Tuple

import numpy as np


ALPHA = 256


class Predictor(abc.ABC):
    """Abstract base for any sub-model that contributes a byte distribution.

    Subclasses MUST implement predict() and update(). Subclasses SHOULD
    override name() for logging. The mixer treats all subclasses identically.
    """

    @abc.abstractmethod
    def predict(self) -> Tuple[np.ndarray, int]:
        """Return (counts[256] uint32, total uint32) Laplace-smoothed.

        - counts.dtype must be np.uint32
        - counts.shape must be (256,)
        - total must equal counts.sum() and be >= ALPHA
        - This method is called once per byte in encode and decode
        """

    @abc.abstractmethod
    def update(self, byte: int) -> None:
        """Observe the committed byte. Update internal state for next predict().

        - byte is 0..255 inclusive
        - Called after the arithmetic coder commits the symbol
        - Must be deterministic in its effect on internal state
        """

    def name(self) -> str:
        """Short identifier for logs / bench reports. Default: class name."""
        return type(self).__name__

    def reset(self) -> None:
        """Optional: reset internal state to fresh-instance state.

        Default implementation raises NotImplementedError. Subclasses MAY
        override to support reuse across bench runs without reallocating.
        """
        raise NotImplementedError(
            f"{self.name()} does not support reset; "
            "construct a fresh instance per bench run"
        )


def validate_predictor_output(counts: np.ndarray, total: int) -> None:
    """Sanity-check a predictor's predict() output. Used in tests + dev harness.

    Raises ValueError if any contract is violated. Cheap; ~3 numpy ops.
    Disable in hot bench loops via the validate=False mixer flag.
    """
    if not isinstance(counts, np.ndarray):
        raise ValueError(f"counts must be np.ndarray, got {type(counts).__name__}")
    if counts.dtype != np.uint32:
        raise ValueError(f"counts.dtype must be uint32, got {counts.dtype}")
    if counts.shape != (ALPHA,):
        raise ValueError(f"counts.shape must be ({ALPHA},), got {counts.shape}")
    if total < ALPHA:
        raise ValueError(
            f"total must be >= {ALPHA} (Laplace floor); got {total}. "
            "If your predictor has no signal, return all-1 counts (= ALPHA)."
        )
    actual = int(counts.sum())
    if actual != total:
        raise ValueError(
            f"total ({total}) must equal counts.sum() ({actual}). "
            "Caller computed total inconsistently."
        )


__all__ = ["Predictor", "ALPHA", "validate_predictor_output"]
