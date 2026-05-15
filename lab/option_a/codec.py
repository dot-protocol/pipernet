"""
Track-B Option A — pure-Python encode/decode using pluggable Predictor list.

The encode/decode pair below is the architectural reference. It is slower
than mixer_multi_cy.encode (no Cython hot path) but is the cleanest place
to develop new predictor types and verify byte-exact equivalence before
porting changes back to the .pyx.

Usage:
    from option-a.predictors import MarkovPredictor, MatchPredictor
    from option-a.codec import encode, decode

    predictors_factory = lambda: [
        MarkovPredictor(),
        MatchPredictor(window=3),
        MatchPredictor(window=5),
        MatchPredictor(window=8),
        MatchPredictor(window=12),
    ]
    blob = encode(data, predictors_factory)
    back = decode(blob, predictors_factory)
    assert back == data
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, List

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

from .predictor import Predictor
from .mixer import multi_mix_geometric


PredictorFactory = Callable[[], List[Predictor]]


def encode(data: bytes, predictors_factory: PredictorFactory, mixer=multi_mix_geometric) -> bytes:
    """Encode `data` using the predictors returned by `predictors_factory()`.

    The factory is called once at the start. Each predictor must start with
    fresh state — encode() does NOT reset them, so don't reuse predictor
    instances across encode/decode calls.
    """
    predictors = predictors_factory()
    encoder = ArithmeticEncoder()

    for byte in data:
        cum, total = mixer(predictors)
        encoder.encode_symbol(cum[byte], cum[byte + 1], total)
        for p in predictors:
            p.update(byte)

    return _header(len(data)) + encoder.finish()


def decode(blob: bytes, predictors_factory: PredictorFactory, mixer=multi_mix_geometric) -> bytes:
    """Decode `blob` using the predictors returned by `predictors_factory()`.

    Predictors must be configured identically to those used at encode time —
    same classes, same constructor args, same order. The mixer determinism
    contract guarantees byte-exact round-trip iff both sides match.
    """
    n, payload = _unheader(blob)
    predictors = predictors_factory()
    decoder = ArithmeticDecoder(payload)
    out = bytearray()

    for _ in range(n):
        cum, total = mixer(predictors)
        byte = decoder.decode_symbol(cum, total)
        out.append(byte)
        for p in predictors:
            p.update(byte)

    return bytes(out)


def default_v03cy_factory() -> List[Predictor]:
    """Return a fresh predictor list matching the v0.3cy baseline.

    Markov base + 4 match models at windows (3, 5, 8, 12).
    """
    from .predictors import MarkovPredictor, MatchPredictor
    return [
        MarkovPredictor(),
        MatchPredictor(window=3),
        MatchPredictor(window=5),
        MatchPredictor(window=8),
        MatchPredictor(window=12),
    ]


__all__ = ["encode", "decode", "default_v03cy_factory", "PredictorFactory"]
