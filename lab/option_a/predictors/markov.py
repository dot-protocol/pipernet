"""
MarkovPredictor — order-3 Markov context model.

Wraps the existing Cython CMarkovCounts from middle-out/track-b/mixer_multi_cy.
CMarkovCounts has a slightly different signature than Predictor expects — it
takes a position parameter on every call so it can compute the absolute-position
ring-buffer context (start = max(0, pos - 3)). The adapter tracks position
internally and exposes the standard Predictor.predict()/update(byte) interface.

Algorithm (reference, see mixer_multi_cy.pyx for hot-path implementation):
  Maintain a dict mapping 0-3 byte contexts to Laplace-smoothed uint32[256]
  count arrays (init = 1 per byte). predict() looks up the current context's
  array. update(byte) increments arr[byte] in the current context's array.
  Position-aware context computation matches baseline.MarkovModel.context_of().

Important: this Predictor is the BASE distribution in the geometric-mean mix.
It is always used; match predictors are multiplied IN ON TOP if they have
signal beyond their Laplace floor. The no-signal fallback in the mixer reverts
to this base if any match would collapse the distribution to zero.
"""

import sys
from pathlib import Path

_TRACKB = Path(__file__).resolve().parents[4] / "middle-out" / "track-b"
if str(_TRACKB) not in sys.path:
    sys.path.insert(0, str(_TRACKB))

from mixer_multi_cy import CMarkovCounts  # type: ignore

from ..predictor import Predictor


class MarkovPredictor(Predictor):
    """Adapter: CMarkovCounts as Predictor.

    Position-tracking adapter for the order-3 Markov base distribution.
    """

    def __init__(self):
        self._inner = CMarkovCounts()
        self._pos = 0

    def predict(self):
        arr, _view, total = self._inner.get_counts_total(self._pos)
        return arr, int(total)

    def update(self, byte: int) -> None:
        self._inner.update(self._pos, byte)
        self._pos += 1

    def name(self) -> str:
        return "Markov(order=3)"

    @property
    def position(self) -> int:
        return self._pos

    @property
    def inner(self):
        return self._inner
