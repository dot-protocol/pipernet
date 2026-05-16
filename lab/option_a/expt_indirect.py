"""
Track-B Option A — EXPT-009: Indirect context model (standalone, bit-native).

The first bit-native predictor in track-b. Ports fx2-cmix's `indirect.h`
pattern: shared state-byte map keyed on (byte_context, bit_context), local
prediction table indexed by state byte, EMA update on bit observation, state
machine advance via precomputed transition table.

Standalone test: drive the bit_codec with ONLY IndirectBitPredictor (no
byte-level mixer wrapping). This measures what the indirect context model
buys ALONE, without help from Markov or match models. We expect it to be
worse than Phase 1 (which has 5 specialized predictors), but it should beat
the trivial uniform predictor by a wide margin — order-of-magnitude better
than 8.0 bpb baseline.

If standalone Indirect lands in the 3.5–5.0 bpb range on enwik8 100KB, the
implementation is structurally correct and ready to mix with the byte-level
stack (EXPT-010).

Sweep:
  - map_size: 1<<20, 1<<22, 1<<24   (1 MB, 4 MB, 16 MB)
  - lr:       0.05, 0.1, 0.2
  - history:  1, 2, 3 bytes

Usage:
    python3 expt_indirect.py [SLICE_BYTES]
"""

from __future__ import annotations

import gzip
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAB = HERE.parent
sys.path.insert(0, str(LAB))

from option_a.bit_codec import bit_encode, bit_decode, DEFAULT_BIT_PRECISION  # type: ignore
from option_a.bit_mixer import make_indirect_factory  # type: ignore


def measure(label: str, data: bytes, factory, precision: int = DEFAULT_BIT_PRECISION):
    n = len(data)
    t0 = time.perf_counter()
    blob = bit_encode(data, factory, precision=precision)
    enc_t = time.perf_counter() - t0
    bpb = len(blob) * 8 / n

    # Roundtrip check
    t0 = time.perf_counter()
    back = bit_decode(blob, factory, precision=precision)
    dec_t = time.perf_counter() - t0
    rt = "✓" if back == data else "✗"
    return label, len(blob), bpb, enc_t, dec_t, rt


def main(slice_bytes: int = 100_000) -> int:
    candidates = [Path("/tmp/enwik8_1mb"), Path("/tmp/enwik8")]
    src = next((p for p in candidates if p.exists()), None)
    if src is None:
        print("ERROR: enwik8 not found at /tmp/enwik8 or /tmp/enwik8_1mb", file=sys.stderr)
        return 1
    data = src.read_bytes()[:slice_bytes]
    n = len(data)
    print(f"corpus: {src} [:{n:_}]\n")

    gz = len(gzip.compress(data, compresslevel=9))
    uniform_bytes = n  # uniform predictor encodes each byte in exactly 8 bits = n bytes
    print(f"reference baselines:")
    print(f"  uniform   {uniform_bytes:_} bytes  bpb=8.0000")
    print(f"  gzip-9    {gz:_} bytes  bpb={gz*8/n:.4f}")
    print()

    print(f"{'variant':<48}{'bytes':>10}{'bpb':>8}{'enc s':>7}{'dec s':>7}{'rt':>4}")
    print("-" * 84)

    # Default: 4 MB map, lr=0.1, history=2
    label, b, bpb, et, dt, rt = measure(
        "Indirect (1<<22 map, lr=0.1, hist=2)",
        data,
        make_indirect_factory(map_size=1 << 22, lr=0.1, history_window=2),
    )
    print(f"{label:<48}{b:>10_}{bpb:>8.4f}{et:>7.1f}{dt:>7.1f}{rt:>4}")

    # Sweep — only on small slice to keep wall time sane
    if n <= 200_000:
        for ms_bits in (20, 24):
            for lr in (0.05, 0.1, 0.2):
                for hist in (1, 2, 3):
                    if ms_bits == 22 and lr == 0.1 and hist == 2:
                        continue  # already measured above
                    label, b, bpb, et, dt, rt = measure(
                        f"Indirect (1<<{ms_bits} map, lr={lr}, hist={hist})",
                        data,
                        make_indirect_factory(map_size=1 << ms_bits, lr=lr, history_window=hist),
                    )
                    print(f"{label:<48}{b:>10_}{bpb:>8.4f}{et:>7.1f}{dt:>7.1f}{rt:>4}")

    return 0


if __name__ == "__main__":
    slice_size = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
    sys.exit(main(slice_size))
