"""
Track-B Option A — Phase 2C bit-level codec.

Encode/decode at the bit granularity. Per byte we make 8 calls into the
arithmetic coder, each narrowing the interval by one bit of the byte.
Bit ordering: MSB first. bit_context starts at 1 (sentinel); after each bit
bit_context = (bit_context << 1) | bit. This is PAQ / cmix convention.

Why bit-level: it is the architectural prerequisite for the next moves
toward Hutter-prize structure:
  - Indirect context models keyed on (context_hash, bit_context, byte_partial)
  - APM/SSE chains that quantize probability per bit decision
  - High-cardinality per-context mixer weights (>>256 slots)

For v0 we wrap the byte-level mixer (BytewiseBitPredictor), which makes the
bit walk mathematically equivalent to the byte-level codec up to integer
truncation in encode_symbol. The expt_bit_baseline.py harness verifies
both byte-exact roundtrip and compressed-size parity vs byte-level encode().

Precision: bit-level AC operates over the [0, precision) interval per bit.
Default 2^24 (Nacrith-style high precision). At 8 bits per byte we accumulate
8x more quantization-step opportunities than the byte-level codec, so the
high precision matters here more than in the byte-level codec.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

# baseline ArithmeticEncoder / Decoder live in middle-out/src/baseline.py
_MIDDLEOUT = Path(__file__).resolve().parents[3] / "middle-out"
if str(_MIDDLEOUT) not in sys.path:
    sys.path.insert(0, str(_MIDDLEOUT))

from src.baseline import (  # type: ignore
    ArithmeticEncoder,
    ArithmeticDecoder,
    _header,
    _unheader,
)

from .bit_mixer import BitPredictor


BitPredictorFactory = Callable[[], BitPredictor]

DEFAULT_BIT_PRECISION = 1 << 24  # 2^24


def _quantize_p_one(p_one: float, precision: int) -> int:
    """Quantize p_one ∈ (0, 1) to integer in [1, precision-1].

    Floor at 1 and ceil at precision-1 to keep both bit outcomes encodable.
    This matches the cum-freq Laplace-floor pattern from the byte-level mixer.
    """
    if p_one != p_one:  # NaN guard
        p_one = 0.5
    q = int(round(p_one * precision))
    if q < 1:
        return 1
    if q > precision - 1:
        return precision - 1
    return q


def bit_encode(
    data: bytes,
    bit_predictor_factory: BitPredictorFactory,
    precision: int = DEFAULT_BIT_PRECISION,
) -> bytes:
    """Encode `data` bit-by-bit via a BitPredictor.

    Bit-tree walk: per byte, 8 calls to encode_symbol on a 2-symbol interval
    (bit=0 or bit=1) of size `precision`. p_one is the bit_predictor's
    estimate of P(bit_k = 1) given the prefix encoded so far.
    """
    bit_predictor = bit_predictor_factory()
    encoder = ArithmeticEncoder()

    for byte in data:
        bit_predictor.start_byte()
        bit_context = 1
        for k in range(8):
            bit = (byte >> (7 - k)) & 1
            p_one = bit_predictor.predict_bit(bit_context, k)
            p_one_int = _quantize_p_one(p_one, precision)
            # cum_freq layout: [bit=0 region][bit=1 region] sums to precision.
            #   bit=0 occupies [0, precision - p_one_int)
            #   bit=1 occupies [precision - p_one_int, precision)
            split = precision - p_one_int
            if bit == 0:
                encoder.encode_symbol(0, split, precision)
            else:
                encoder.encode_symbol(split, precision, precision)
            bit_context = (bit_context << 1) | bit
        bit_predictor.commit_byte(byte)

    return _header(len(data)) + encoder.finish()


def bit_decode(
    blob: bytes,
    bit_predictor_factory: BitPredictorFactory,
    precision: int = DEFAULT_BIT_PRECISION,
) -> bytes:
    """Decode `blob` produced by bit_encode using a matching BitPredictor."""
    n, payload = _unheader(blob)
    bit_predictor = bit_predictor_factory()
    decoder = ArithmeticDecoder(payload)
    out = bytearray()

    for _ in range(n):
        bit_predictor.start_byte()
        bit_context = 1
        byte = 0
        for k in range(8):
            p_one = bit_predictor.predict_bit(bit_context, k)
            p_one_int = _quantize_p_one(p_one, precision)
            split = precision - p_one_int
            cum_freqs = [0, split, precision]
            bit = decoder.decode_symbol(cum_freqs, precision)
            byte = (byte << 1) | bit
            bit_context = (bit_context << 1) | bit
        out.append(byte)
        bit_predictor.commit_byte(byte)

    return bytes(out)


__all__ = [
    "bit_encode",
    "bit_decode",
    "DEFAULT_BIT_PRECISION",
    "BitPredictorFactory",
]
