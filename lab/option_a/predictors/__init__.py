"""
Track-B Option A — predictor implementations.

Each module provides a Predictor subclass wrapping or implementing a sub-model:
  markov.MarkovPredictor   — order-3 Markov (wraps CMarkovCounts)
  match.MatchPredictor     — K-byte exact context match (wraps CMatchModel)

New predictors plug in here as Phase 1-4 ships them:
  sparse_match.SparseMatchPredictor  (Phase 2)
  rle_match.RLEMatchPredictor        (Phase 2)
  indirect.IndirectContextPredictor  (Phase 3)
  apm.APMLayer                       (Phase 3, post-mix)
  ssm.MicroSSMPredictor              (Phase 4)
"""

from .markov import MarkovPredictor
from .match import MatchPredictor

__all__ = ["MarkovPredictor", "MatchPredictor"]
