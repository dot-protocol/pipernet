"""
Track-B Option A — EXPT-008: bit-level codec baseline.

Hypothesis: wrapping the byte-level Phase 1 logistic mixer inside a bit-level
codec (BytewiseBitPredictor) produces:
  (a) byte-exact roundtrip on real data
  (b) compressed size within ~1% of the byte-level Phase 1 codec
      (small delta = integer truncation in encode_symbol; 8 truncations per byte
       in bit-level vs 1 in byte-level)

If (a) fails, there is a bug. If (b) shows > ~1% gap, our bit-level precision
is too low or the truncation pattern is worse than expected.

This is the equivalence gate before adding any bit-native predictors. Once it
passes, the architecture is unlocked for:
  - Indirect context model (state byte + 256-entry prob table)
  - APM/SSE final stage (per-context 7-bin quantization)
  - High-cardinality per-context mixer dispatch

Usage:
    python3 expt_bit_baseline.py [SLICE_BYTES]
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

from option_a.codec import encode as byte_encode  # type: ignore
from option_a.mixer import multi_mix_geometric, multi_mix_logistic  # type: ignore
from option_a.predictor import ALPHA  # type: ignore
from option_a.predictors import MarkovPredictor, MatchPredictor  # type: ignore
from option_a.bit_codec import bit_encode, bit_decode, DEFAULT_BIT_PRECISION  # type: ignore
from option_a.bit_mixer import make_bytewise_bit_factory  # type: ignore


# Phase 1 global tuned weights (locked, EXPT-001, validated at 100KB and 1MB)
PHASE1_WEIGHTS = np.array([0.630, 1.401, 0.995, 0.550, 2.035], dtype=np.float64)


def make_byte_factory():
    return [
        MarkovPredictor(),
        MatchPredictor(window=3),
        MatchPredictor(window=5),
        MatchPredictor(window=8),
        MatchPredictor(window=12),
    ]


def phase1_mixer(predictors):
    return multi_mix_logistic(predictors, weights=PHASE1_WEIGHTS.tolist())


def main(slice_bytes: int = 100_000) -> int:
    candidates = [Path("/tmp/enwik8_1mb"), Path("/tmp/enwik8")]
    src = next((p for p in candidates if p.exists()), None)
    if src is None:
        print("ERROR: enwik8 not found at /tmp/enwik8 or /tmp/enwik8_1mb", file=sys.stderr)
        return 1
    data = src.read_bytes()[:slice_bytes]
    n = len(data)
    print(f"corpus: {src} [:{n:_}]\n")

    # --- Baselines ---
    gz = len(gzip.compress(data, compresslevel=9))
    print(f"gzip-9                            {gz:_} bytes  bpb={gz*8/n:.4f}")

    t0 = time.perf_counter()
    geom_blob = byte_encode(data, make_byte_factory, mixer=multi_mix_geometric)
    print(f"byte-level geometric              {len(geom_blob):_} bytes  "
          f"bpb={len(geom_blob)*8/n:.4f}  enc={time.perf_counter()-t0:.1f}s")

    t0 = time.perf_counter()
    phase1_blob = byte_encode(data, make_byte_factory, mixer=phase1_mixer)
    phase1_n = len(phase1_blob)
    print(f"byte-level Phase 1 logistic       {phase1_n:_} bytes  "
          f"bpb={phase1_n*8/n:.4f}  enc={time.perf_counter()-t0:.1f}s")

    # --- Bit-level wrapping byte-level mixers ---
    print()
    print(f"{'bit-level variant':<48}{'bytes':>10}{'bpb':>8}{'vs byte':>10}{'enc s':>7}")
    print("-" * 83)

    # Bit wrapping byte-geometric
    bit_factory_geom = make_bytewise_bit_factory(make_byte_factory, byte_mixer=multi_mix_geometric)
    t0 = time.perf_counter()
    bit_blob_geom = bit_encode(data, bit_factory_geom, precision=DEFAULT_BIT_PRECISION)
    enc_t = time.perf_counter() - t0
    delta_geom = (len(bit_blob_geom) - len(geom_blob)) * 100.0 / len(geom_blob)
    print(f"{'bit wrapping byte-geometric (2^24)':<48}"
          f"{len(bit_blob_geom):>10_}{len(bit_blob_geom)*8/n:>8.4f}"
          f"{delta_geom:>+9.3f}%{enc_t:>7.1f}")

    # Bit wrapping byte-Phase1
    bit_factory_p1 = make_bytewise_bit_factory(make_byte_factory, byte_mixer=phase1_mixer)
    t0 = time.perf_counter()
    bit_blob_p1 = bit_encode(data, bit_factory_p1, precision=DEFAULT_BIT_PRECISION)
    enc_t = time.perf_counter() - t0
    delta_p1 = (len(bit_blob_p1) - phase1_n) * 100.0 / phase1_n
    print(f"{'bit wrapping byte-Phase1 (2^24)':<48}"
          f"{len(bit_blob_p1):>10_}{len(bit_blob_p1)*8/n:>8.4f}"
          f"{delta_p1:>+9.3f}%{enc_t:>7.1f}")

    # Sanity sweep: lower bit-level precision
    for prec in (1 << 20, 1 << 16, 1 << 12):
        bf = make_bytewise_bit_factory(make_byte_factory, byte_mixer=phase1_mixer)
        t0 = time.perf_counter()
        blob = bit_encode(data, bf, precision=prec)
        enc_t = time.perf_counter() - t0
        delta = (len(blob) - phase1_n) * 100.0 / phase1_n
        bits_per_prec = (prec.bit_length() - 1)
        print(f"{f'bit wrapping byte-Phase1 (2^{bits_per_prec})':<48}"
              f"{len(blob):>10_}{len(blob)*8/n:>8.4f}"
              f"{delta:>+9.3f}%{enc_t:>7.1f}")

    # --- Roundtrip verification on the canonical Phase1 bit blob ---
    print()
    t0 = time.perf_counter()
    bit_factory_p1_dec = make_bytewise_bit_factory(make_byte_factory, byte_mixer=phase1_mixer)
    back = bit_decode(bit_blob_p1, bit_factory_p1_dec, precision=DEFAULT_BIT_PRECISION)
    dec_t = time.perf_counter() - t0
    if back != data:
        diff_idx = next((i for i, (a, b) in enumerate(zip(back, data)) if a != b), len(back))
        print(f"  ✗ ROUNDTRIP FAILED at byte {diff_idx} (decoded {len(back)} bytes)")
        return 2
    print(f"  ✓ Roundtrip verified byte-exact on bit-Phase1 blob (dec={dec_t:.1f}s)")

    # Verdict
    print()
    print(f"{'='*83}")
    print(f"VERDICT:")
    gate = 1.0  # within 1% of byte-level is the equivalence target
    if abs(delta_p1) <= gate:
        print(f"  ✓ bit-Phase1 within {gate}% of byte-Phase1 ({delta_p1:+.3f}%). "
              f"Equivalence holds — ready to add bit-native predictors.")
    else:
        print(f"  ⚠ bit-Phase1 vs byte-Phase1 delta is {delta_p1:+.3f}% (gate: ±{gate}%). "
              f"Investigate precision or truncation pattern before adding bit-native models.")

    return 0


if __name__ == "__main__":
    slice_size = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
    sys.exit(main(slice_size))
