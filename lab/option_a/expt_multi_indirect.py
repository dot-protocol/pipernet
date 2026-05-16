"""
Track-B Option A — EXPT-011: multi-Indirect mix (cmix-style predictor stack).

EXPT-010 showed Phase 1 + Indirect (1<<24, lr=0.05, hist=3) beats gzip by 4%
on 100KB. cmix/fx2-cmix uses MULTIPLE indirect models with different context
hashes — each capturing different statistical regularities (last byte, last
2 bytes, last 3 bytes, sparse patterns, line-break contexts, etc).

This experiment stacks 2-4 Indirect predictors with different (hist, lr)
settings into the bit-level mix alongside Phase 1, and sweeps weights.

Hypothesis: adding a second Indirect with different context (hist=2) provides
signal that hist=3 misses (last 2 bytes are denser/more reliable than 3),
and the mix captures both. Expected: 1-3% improvement over EXPT-010 best.

Usage:
    python3 expt_multi_indirect.py [SLICE_BYTES]
"""

from __future__ import annotations

import gzip
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
LAB = HERE.parent
sys.path.insert(0, str(LAB))

from option_a.bit_codec import bit_encode, bit_decode, DEFAULT_BIT_PRECISION  # type: ignore
from option_a.bit_mixer import (  # type: ignore
    BytewiseBitPredictor,
    IndirectBitPredictor,
    MultiBitPredictor,
)
from option_a.mixer import multi_mix_logistic  # type: ignore
from option_a.predictors import MarkovPredictor, MatchPredictor  # type: ignore


PHASE1_WEIGHTS = np.array([0.630, 1.401, 0.995, 0.550, 2.035], dtype=np.float64)


def byte_phase1_mixer(predictors):
    return multi_mix_logistic(predictors, weights=PHASE1_WEIGHTS.tolist())


def make_byte_factory():
    return [
        MarkovPredictor(),
        MatchPredictor(window=3),
        MatchPredictor(window=5),
        MatchPredictor(window=8),
        MatchPredictor(window=12),
    ]


def build_mix(config: dict):
    """Construct a MultiBitPredictor from a config dict.

    Example config:
      {
        "phase1_w": 1.0,
        "indirects": [
          {"map_size": 1<<24, "lr": 0.05, "hist": 3, "w": 0.2},
          {"map_size": 1<<22, "lr": 0.05, "hist": 2, "w": 0.15},
        ],
      }
    """
    children = [BytewiseBitPredictor(make_byte_factory(), byte_mixer=byte_phase1_mixer)]
    weights = [config["phase1_w"]]
    for ind in config["indirects"]:
        children.append(IndirectBitPredictor(
            context_fn=None,
            map_size=ind["map_size"],
            lr=ind["lr"],
            history_window=ind["hist"],
        ))
        weights.append(ind["w"])
    return MultiBitPredictor(children, weights=weights)


def measure(label: str, data: bytes, config: dict, precision: int = DEFAULT_BIT_PRECISION):
    n = len(data)
    factory = lambda: build_mix(config)
    t0 = time.perf_counter()
    blob = bit_encode(data, factory, precision=precision)
    enc_t = time.perf_counter() - t0
    bpb = len(blob) * 8 / n
    back = bit_decode(blob, factory, precision=precision)
    rt = "✓" if back == data else "✗"
    return label, len(blob), bpb, enc_t, rt


def main(slice_bytes: int = 100_000) -> int:
    candidates = [Path("/tmp/enwik8_1mb"), Path("/tmp/enwik8")]
    src = next((p for p in candidates if p.exists()), None)
    if src is None:
        print("ERROR: enwik8 not found", file=sys.stderr)
        return 1
    data = src.read_bytes()[:slice_bytes]
    n = len(data)
    gz = len(gzip.compress(data, compresslevel=9))
    print(f"corpus: {src} [:{n:_}]   gzip-9: {gz:_} bytes ({gz*8/n:.4f} bpb)\n")

    print(f"{'config':<58}{'bytes':>10}{'bpb':>8}{'vs gzip':>10}{'enc s':>7}{'rt':>4}")
    print("-" * 97)

    configs = [
        # EXPT-010 best baseline (1 Indirect)
        {
            "label": "P1×0.9 + Ind(hist=3)×0.25  [EXPT-010 best]",
            "phase1_w": 0.9,
            "indirects": [
                {"map_size": 1 << 24, "lr": 0.05, "hist": 3, "w": 0.25},
            ],
        },
        # Add a second Indirect with hist=2
        {
            "label": "P1×0.9 + Ind(hist=3)×0.2 + Ind(hist=2)×0.15",
            "phase1_w": 0.9,
            "indirects": [
                {"map_size": 1 << 24, "lr": 0.05, "hist": 3, "w": 0.20},
                {"map_size": 1 << 22, "lr": 0.05, "hist": 2, "w": 0.15},
            ],
        },
        # Three Indirects covering hist 1/2/3
        {
            "label": "P1×0.9 + Ind3×0.2 + Ind2×0.12 + Ind1×0.08",
            "phase1_w": 0.9,
            "indirects": [
                {"map_size": 1 << 24, "lr": 0.05, "hist": 3, "w": 0.20},
                {"map_size": 1 << 22, "lr": 0.05, "hist": 2, "w": 0.12},
                {"map_size": 1 << 20, "lr": 0.05, "hist": 1, "w": 0.08},
            ],
        },
        # Tighter Indirect ensemble (matched LRs)
        {
            "label": "P1×0.9 + Ind3(lr=0.03)×0.18 + Ind2(lr=0.05)×0.12",
            "phase1_w": 0.9,
            "indirects": [
                {"map_size": 1 << 24, "lr": 0.03, "hist": 3, "w": 0.18},
                {"map_size": 1 << 22, "lr": 0.05, "hist": 2, "w": 0.12},
            ],
        },
        # Higher map size for hist=2 (try to push it)
        {
            "label": "P1×0.9 + Ind(hist=3)×0.2 + Ind(hist=2, big map)×0.15",
            "phase1_w": 0.9,
            "indirects": [
                {"map_size": 1 << 24, "lr": 0.05, "hist": 3, "w": 0.20},
                {"map_size": 1 << 24, "lr": 0.05, "hist": 2, "w": 0.15},
            ],
        },
    ]

    best = None
    for cfg in configs:
        label = cfg["label"]
        _, b, bpb, et, rt = measure(label, data, cfg)
        delta = (b - gz) * 100 / gz
        marker = ""
        if best is None or b < best[1]:
            best = (label, b, bpb, et, rt, delta)
            marker = " ◆"
        print(f"{label:<58}{b:>10_}{bpb:>8.4f}{delta:>+9.3f}%{et:>7.1f}{rt:>4}{marker}")

    print()
    if best:
        bl, bb, bbpb, bet, brt, bdelta = best
        verdict = "BEAT gzip" if bdelta < 0 else f"behind gzip by {bdelta:+.3f}%"
        print(f"BEST: {bl}")
        print(f"  → {bb:_} bytes  {bbpb:.4f} bpb  vs gzip {bdelta:+.3f}%  ({verdict})  enc={bet:.1f}s")

    return 0


if __name__ == "__main__":
    slice_size = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
    sys.exit(main(slice_size))
