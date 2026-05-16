"""
Track-B Option A — bit-level logistic mixer weight tuner (EXPT-012 prep).

Online SGD over per-predictor weights in the bit-level logistic mix.
Mirrors the byte-level `tuner.py` SGD pattern; the bit-level math is even
cleaner because each step has a single binary outcome (bit ∈ {0, 1}) rather
than a 256-way softmax.

Math:
  Forward:   logit_i = log(p_i / (1 - p_i))
             s       = Σ w_i · logit_i
             final_p = sigmoid(s)
  Loss (bit y ∈ {0,1}):
             L       = -y · log(final_p) - (1-y) · log(1 - final_p)
  Gradient:
             dL/dw_i = (final_p - y) · logit_i

Caveat: the children's INTERNAL state advances on `update_bit(bit, ...)`
exactly as in encode. Their state evolves the same way under tuning and
under actual encode, so the tuned weights are valid for encode.

For the BytewiseBitPredictor child, internal state per byte includes the
byte-level snapshot taken at start_byte — that snapshot stays correct because
update_bit is a no-op for that child.

For the IndirectBitPredictor child, internal state (predictions, map) DOES
mutate on update_bit, mirroring encode. So tuning IS the first pass; subsequent
encode passes start from fresh state. Calling the tuner is equivalent to a
"with-learning" encode pass.

Usage:
    from option_a.bit_tuner import tune_bit_weights
    weights, total_bits = tune_bit_weights(
        data, children_factory, num_passes=1, lr_init=0.01
    )

The returned weights are the FINAL learned values. Use them to construct a
MultiBitPredictor with fresh children for the actual encode.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Callable, List, Tuple

import numpy as np

HERE = Path(__file__).resolve().parent
LAB = HERE.parent
sys.path.insert(0, str(LAB))

from option_a.bit_mixer import BitPredictor  # type: ignore


EPS = 1e-6


def _safe_logit(p: float) -> float:
    if p < EPS:
        p = EPS
    elif p > 1.0 - EPS:
        p = 1.0 - EPS
    return math.log(p / (1.0 - p))


def _safe_sigmoid(s: float) -> float:
    if s >= 700:
        return 1.0 - EPS
    if s <= -700:
        return EPS
    return 1.0 / (1.0 + math.exp(-s))


def tune_bit_weights(
    data: bytes,
    children_factory: Callable[[], List[BitPredictor]],
    num_passes: int = 1,
    lr_init: float = 0.01,
    lr_decay: float = 0.99999,
    weight_clip: float = 5.0,
    initial_weights: List[float] | None = None,
    verbose: bool = True,
) -> Tuple[np.ndarray, float]:
    """Run online SGD over the bit-level logistic mix weights.

    Args:
        data: corpus bytes
        children_factory: zero-arg callable returning a list[BitPredictor].
            Called once per pass to get fresh predictor state.
        num_passes: passes over the corpus (default 1)
        lr_init: initial learning rate (default 0.01 — bit-level is less
            noisy than byte-level so smaller lr is fine)
        lr_decay: per-bit decay factor (default 0.99999)
        weight_clip: clamp |w_i| ≤ weight_clip after each step
        initial_weights: warm-start; defaults to ones
        verbose: print progress

    Returns:
        (weights: ndarray shape (n_children,), total_bits: float)
        total_bits is the cross-entropy cost of encoding `data` under the
        (online-learning) tuner pass. NOT the final blob bit count — that
        comes from a separate clean encode with the tuned weights.
    """
    n = len(data)
    bits_total = n * 8

    # Probe one factory call to find n_children
    _probe = children_factory()
    n_children = len(_probe)
    del _probe

    if initial_weights is None:
        weights = np.ones(n_children, dtype=np.float64)
    else:
        weights = np.asarray(initial_weights, dtype=np.float64).copy()
        assert weights.shape == (n_children,), (
            f"initial_weights shape {weights.shape} != ({n_children},)"
        )

    total_bits = 0.0
    snap = max(1, bits_total // 20)

    for pass_idx in range(num_passes):
        children = children_factory()
        lr = lr_init
        bits_seen = 0

        for byte_idx, byte in enumerate(data):
            for c in children:
                c.start_byte()

            bit_context = 1
            for k in range(8):
                bit = (byte >> (7 - k)) & 1

                # Collect each child's p_one + logit
                logits = np.empty(n_children, dtype=np.float64)
                for i, c in enumerate(children):
                    logits[i] = _safe_logit(c.predict_bit(bit_context, k))

                # Mix: weighted sum of logits → sigmoid
                s = float(np.dot(weights, logits))
                final_p_one = _safe_sigmoid(s)

                # Cross-entropy contribution (in bits)
                if bit == 1:
                    total_bits += -math.log2(max(EPS, final_p_one))
                else:
                    total_bits += -math.log2(max(EPS, 1.0 - final_p_one))

                # SGD: dL/dw_i = (final_p - bit) · logit_i
                grad_factor = final_p_one - bit
                weights -= lr * grad_factor * logits
                np.clip(weights, -weight_clip, weight_clip, out=weights)

                # Advance children's bit state (same as encode would)
                for c in children:
                    c.update_bit(bit, bit_context, k)

                bit_context = (bit_context << 1) | bit
                bits_seen += 1
                lr *= lr_decay

                if verbose and bits_seen % snap == 0:
                    avg = total_bits / bits_seen
                    print(
                        f"  pass {pass_idx+1}/{num_passes}  bit {bits_seen:>10_}/{bits_total:_}  "
                        f"avg_bpb={avg:.4f}  lr={lr:.5f}  weights={weights.tolist()}",
                        flush=True,
                    )

            for c in children:
                c.commit_byte(byte)

        if verbose:
            print(
                f"  pass {pass_idx+1}: total_bits={total_bits:_.1f} "
                f"bpb={total_bits/n:.4f}  final_weights={weights.tolist()}",
                flush=True,
            )

    return weights, total_bits


__all__ = ["tune_bit_weights"]
