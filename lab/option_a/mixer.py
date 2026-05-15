"""
Track-B Option A — pure-Python mixers.

Two implementations:
  multi_mix_geometric(predictors)
      The current v0.3cy mixer in pure Python. Must match _multi_mix_cy
      byte-exact when the predictor list is [Markov, Match(3), Match(5),
      Match(8), Match(12)] — the baseline configuration.

  multi_mix_logistic(predictors, weights)
      Logistic-style weighted mix (Phase 1 deliverable). Adaptive per-context
      weights are learned online; the unweighted geometric mean is the special
      case where all weights equal 1.

Numerical determinism:
  All renormalisation uses numpy.add.reduce (pairwise summation) to match
  the Cython implementation bit-for-bit. Element-wise true division (not
  multiply-by-reciprocal). np.round with banker's rounding for final integer
  cum-freqs scaling. These choices were locked when v0.3cy shipped byte-exact
  between Python and Cython; do NOT change them without re-verifying the
  full byte-exact harness.

  See predictor.py for the contract every input must satisfy.
"""

from __future__ import annotations

from typing import Any, List, Optional, Sequence, Tuple

import numpy as np

from .predictor import ALPHA, Predictor

LAPLACE_FLOOR = 256


def multi_mix_geometric(predictors: Sequence[Predictor]) -> Tuple[List[int], int]:
    """Geometric-mean mix matching _multi_mix_cy byte-exact.

    First predictor is the base (always used).
    Remaining predictors are multiplied IN if their total > LAPLACE_FLOOR.
    No-signal fallback: if any multiply-in step zeros out the distribution,
    revert to the initial base-only distribution and stop the loop.

    Returns:
        (cum_freqs: list[int] of length 257, total_cum: int)
        cum_freqs[byte] / cum_freqs[byte+1] are the symbol's interval bounds
        for arithmetic coding.
    """
    assert len(predictors) >= 1, "need at least one predictor (base)"

    # Snapshot all predictions BEFORE any state mutation (no .update() here)
    preds: List[Tuple[np.ndarray, int]] = [p.predict() for p in predictors]
    base_counts, base_total = preds[0]
    extras = preds[1:]

    # Initial: base distribution normalised. Backup = same; if any later
    # multiplication zeros the distribution we revert to base-only.
    p_mixed = base_counts.astype(np.float64) / float(base_total)
    p_backup = p_mixed.copy()

    for counts, total in extras:
        if total <= LAPLACE_FLOOR:
            continue  # no signal — skip
        p_mixed = p_mixed * (counts.astype(np.float64) / float(total))
        s = np.add.reduce(p_mixed)
        if s > 0.0:
            p_mixed = p_mixed / s
        else:
            p_mixed = p_backup.copy()
            break

    # Final renorm
    s = np.add.reduce(p_mixed)
    p_mixed = p_mixed / s

    # Build cum_freqs: scale by 1e6, round-half-to-even, clamp ≥1, prefix-sum
    counts_int = np.maximum(1, np.round(p_mixed * 1_000_000.0)).astype(np.uint64)
    cum = [0] * (ALPHA + 1)
    total_cum = 0
    for i in range(ALPHA):
        cum[i] = total_cum
        total_cum += int(counts_int[i])
    cum[ALPHA] = total_cum
    return cum, total_cum


def multi_mix_logistic(
    predictors: Sequence[Predictor],
    weights: Optional[Sequence[float]] = None,
) -> Tuple[List[int], int]:
    """Logistic mix: weighted sum of log-probabilities, then exponentiate.

    Mathematically: P(x) ∝ exp(Σ w_i · log p_i(x))

    When all weights equal 1 and predictors share a uniform Laplace floor,
    this collapses to the geometric mean (same as multi_mix_geometric).
    With per-predictor weights, predictors can be given more or less voice
    in the joint distribution — the basis for adaptive mixing in Phase 1.

    Args:
        predictors: list of Predictor instances (first is treated identically
                    to the rest in logistic mix; no special "base" role)
        weights: optional sequence of float weights, one per predictor. If
                 None, all weights default to 1.0 (= geometric mean).

    Returns:
        Same shape as multi_mix_geometric.

    Note: this is NOT byte-exact with multi_mix_geometric even at uniform
    weights because the math path is different (log-domain vs multiply-renorm).
    Use multi_mix_geometric for v0.3cy parity verification.
    """
    n = len(predictors)
    assert n >= 1, "need at least one predictor"

    if weights is None:
        weights = [1.0] * n
    assert len(weights) == n, f"weights ({len(weights)}) must match predictors ({n})"

    preds = [p.predict() for p in predictors]

    # Log-domain accumulation with weight
    log_p = np.zeros(ALPHA, dtype=np.float64)
    for (counts, total), w in zip(preds, weights):
        # log p_i(x) = log(count_i(x) / total_i)  [with Laplace floor ensuring no zeros]
        log_p += w * (np.log(counts.astype(np.float64)) - np.log(float(total)))

    # Exponentiate + normalise. Subtract max for numerical stability.
    log_p -= log_p.max()
    p_mixed = np.exp(log_p)
    p_mixed /= np.add.reduce(p_mixed)

    counts_int = np.maximum(1, np.round(p_mixed * 1_000_000.0)).astype(np.uint64)
    cum = [0] * (ALPHA + 1)
    total_cum = 0
    for i in range(ALPHA):
        cum[i] = total_cum
        total_cum += int(counts_int[i])
    cum[ALPHA] = total_cum
    return cum, total_cum


# Re-export for convenience
__all__ = ["multi_mix_geometric", "multi_mix_logistic", "LAPLACE_FLOOR"]
