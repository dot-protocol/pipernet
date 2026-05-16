"""
Track-B Option A — EXPT-010: bit-level logistic mix of Indirect + Phase 1.

Mixes BytewiseBitPredictor (byte-level Phase 1 logistic, 5 predictors) with
IndirectBitPredictor (1<<24 map, lr=0.05, hist=3 — EXPT-009 best). Combine
via logit sum + sigmoid (MultiBitPredictor).

The bet: bit-level state-machine signal (Indirect) and byte-level n-gram +
match signal (Phase 1) are orthogonal. Phase 1 sees byte-level co-occurrence;
Indirect sees bit-level coupling within and across bytes. Their mix should
beat either alone.

Reference numbers on 100KB enwik8 (EXPT-008 + EXPT-009):
  gzip-9:                36,239 bytes   2.8991 bpb
  bit-Phase1 alone:      36,511 bytes   2.9209 bpb   (+0.7% vs gzip)
  Indirect alone:        42,367 bytes   3.3894 bpb   (+16.9% vs gzip)
  Target for mix:        < 36,239 bytes (beat gzip — first decisive win)

Sweep weights: (1, 1), (1, 0.5), (1, 0.25), (0.5, 1), (1, 1.5), (0.75, 0.75),
                (2, 1), (1, 2).

Roundtrip verification: every variant must produce byte-exact data back.

Usage:
    python3 expt_bit_mix.py [SLICE_BYTES]
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


def make_bytewise_phase1():
    return BytewiseBitPredictor(make_byte_factory(), byte_mixer=byte_phase1_mixer)


def make_indirect():
    return IndirectBitPredictor(
        context_fn=None,
        map_size=1 << 24,
        lr=0.05,
        history_window=3,
    )


def make_mix_factory(weights: tuple[float, float]):
    def factory() -> MultiBitPredictor:
        return MultiBitPredictor(
            children=[make_bytewise_phase1(), make_indirect()],
            weights=list(weights),
        )
    return factory


def measure(label: str, data: bytes, factory, precision: int = DEFAULT_BIT_PRECISION):
    n = len(data)
    t0 = time.perf_counter()
    blob = bit_encode(data, factory, precision=precision)
    enc_t = time.perf_counter() - t0
    bpb = len(blob) * 8 / n

    t0 = time.perf_counter()
    back = bit_decode(blob, factory, precision=precision)
    dec_t = time.perf_counter() - t0
    rt = "✓" if back == data else "✗"
    return label, len(blob), bpb, enc_t, dec_t, rt


def main(slice_bytes: int = 100_000) -> int:
    candidates = [Path("/tmp/enwik8_1mb"), Path("/tmp/enwik8")]
    src = next((p for p in candidates if p.exists()), None)
    if src is None:
        print("ERROR: enwik8 not found", file=sys.stderr)
        return 1
    data = src.read_bytes()[:slice_bytes]
    n = len(data)
    print(f"corpus: {src} [:{n:_}]\n")

    gz = len(gzip.compress(data, compresslevel=9))
    print(f"reference baselines:")
    print(f"  gzip-9                              {gz:_} bytes  bpb={gz*8/n:.4f}")
    print()

    # Reference: each predictor alone
    print(f"{'variant':<48}{'bytes':>10}{'bpb':>8}{'vs gzip':>10}{'enc s':>7}{'rt':>4}")
    print("-" * 87)

    label, b, bpb, et, dt, rt = measure(
        "BIT Phase1 alone",
        data,
        make_bytewise_phase1,
    )
    delta_alone = (b - gz) * 100 / gz
    print(f"{label:<48}{b:>10_}{bpb:>8.4f}{delta_alone:>+9.3f}%{et:>7.1f}{rt:>4}")

    label, b, bpb, et, dt, rt = measure(
        "BIT Indirect alone (1<<24, lr=0.05, hist=3)",
        data,
        make_indirect,
    )
    delta_alone = (b - gz) * 100 / gz
    print(f"{label:<48}{b:>10_}{bpb:>8.4f}{delta_alone:>+9.3f}%{et:>7.1f}{rt:>4}")

    print()

    # Weight sweep
    sweep = [
        (1.0, 1.0),
        (1.0, 0.5),
        (1.0, 0.25),
        (0.5, 1.0),
        (1.0, 1.5),
        (0.75, 0.75),
        (2.0, 1.0),
        (1.0, 2.0),
    ]
    best = None
    for w_phase1, w_indirect in sweep:
        label = f"MIX  Phase1 w={w_phase1:.2f}  Indirect w={w_indirect:.2f}"
        _, b, bpb, et, dt, rt = measure(label, data, make_mix_factory((w_phase1, w_indirect)))
        delta = (b - gz) * 100 / gz
        marker = ""
        if best is None or b < best[1]:
            best = (label, b, bpb, et, rt, delta)
            marker = " ◆"
        print(f"{label:<48}{b:>10_}{bpb:>8.4f}{delta:>+9.3f}%{et:>7.1f}{rt:>4}{marker}")

    print()
    print("=" * 87)
    if best is not None:
        bl, bb, bbpb, bet, brt, bdelta = best
        verdict = "BEAT gzip" if bdelta < 0 else f"behind gzip by {bdelta:+.3f}%"
        print(f"BEST MIX: {bl}")
        print(f"  → {bb:_} bytes  {bbpb:.4f} bpb  vs gzip {bdelta:+.3f}%  ({verdict})  enc={bet:.1f}s  rt={brt}")

    return 0


if __name__ == "__main__":
    slice_size = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
    sys.exit(main(slice_size))
