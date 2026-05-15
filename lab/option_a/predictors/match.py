"""
MatchPredictor — K-byte exact context match.

Wraps the existing Cython CMatchModel from middle-out/track-b/mixer_multi_cy
without modification. CMatchModel already exposes cpdef predict() and update()
which conform to the Predictor protocol; the wrapper exists only so the mixer
can hold a uniform Predictor reference and so the predictor's name/state can
be introspected for logging.

Algorithm (reference, see mixer_multi_cy.pyx for hot-path implementation):
  Maintain an index mapping K-byte contexts to a list of byte positions where
  that context appeared. For a new byte at position p, look up the last
  max_matches positions with the same K-byte context, count what byte followed
  each match, return Laplace-smoothed distribution (init counts = 1 each).

The match-model index is rebuilt from already-decoded data — never shipped in
the archive. Decoder determinism: both encoder and decoder run identical code
paths over the same byte stream, producing identical predictions.
"""

import sys
from pathlib import Path

# Make compiled mixer_multi_cy importable
_TRACKB = Path(__file__).resolve().parents[4] / "middle-out" / "track-b"
if str(_TRACKB) not in sys.path:
    sys.path.insert(0, str(_TRACKB))

from mixer_multi_cy import CMatchModel  # type: ignore

from ..predictor import Predictor


class MatchPredictor(Predictor):
    """Adapter: CMatchModel as Predictor.

    Args:
        window: K, the context length in bytes (3, 5, 8, 12 are v0.3cy defaults)
        max_matches: cap on retrieved historical matches per predict() call (default 32)
    """

    def __init__(self, window: int = 8, max_matches: int = 32):
        self._inner = CMatchModel(window=window, max_matches=max_matches)
        self.window = window
        self.max_matches = max_matches

    def predict(self):
        return self._inner.predict()

    def update(self, byte: int) -> None:
        self._inner.update(byte)

    def name(self) -> str:
        return f"Match(K={self.window})"

    @property
    def inner(self):
        """Direct access to the underlying CMatchModel for hot-path mixers."""
        return self._inner
