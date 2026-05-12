"""
compression — zstd transport compression for the icontact intent substrate.

All functions are pure (no I/O, no globals). They operate on bytes only.

Used by intent.py to implement the v0.5.0 wire format:
  intent_z:<b64url(zstd(canonical_json))>  +  intent_sig:<b64url(sig)>

The signature is always over the *canonical JSON bytes*, not the compressed bytes.
Compression is transport-only; the security domain is the canonical plaintext.
"""
from __future__ import annotations

import zstandard as zstd

# Compression level: 3 (balanced, deterministic).
_LEVEL: int = 3

# Hard cap on decompressed output to refuse maliciously crafted payloads.
# 10 MB is orders of magnitude above any realistic intent/resolve JSON payload.
_MAX_DECOMPRESSED_BYTES: int = 10 * 1024 * 1024


def compress(data: bytes) -> bytes:
    """Compress *data* with zstd at level 3.

    Args:
        data: Raw bytes to compress. May be empty.

    Returns:
        Compressed bytes. Same *data* always produces the same output
        (deterministic compressor context per call).

    Raises:
        TypeError: If *data* is not bytes.
    """
    if not isinstance(data, bytes):
        raise TypeError(f"compress() expects bytes, got {type(data).__name__}")
    cctx = zstd.ZstdCompressor(level=_LEVEL)
    return cctx.compress(data)


def decompress(data: bytes, *, max_bytes: int = _MAX_DECOMPRESSED_BYTES) -> bytes:
    """Decompress *data* produced by :func:`compress`.

    Args:
        data: zstd-compressed bytes.
        max_bytes: Upper bound on the size of the decompressed output.
            Defaults to 10 MB. Inputs that would decompress beyond this limit
            raise :exc:`ValueError` before any full decompression occurs,
            defending against decompression-bomb payloads.

    Returns:
        Decompressed bytes.

    Raises:
        TypeError: If *data* is not bytes.
        ValueError: If decompressed output would exceed *max_bytes*, or if
            *data* is not valid zstd-compressed bytes.
    """
    if not isinstance(data, bytes):
        raise TypeError(f"decompress() expects bytes, got {type(data).__name__}")
    dctx = zstd.ZstdDecompressor()
    try:
        result = dctx.decompress(data, max_bytes)
    except zstd.ZstdError as exc:
        raise ValueError(f"zstd decompression failed: {exc}") from exc
    if len(result) > max_bytes:
        raise ValueError(
            f"Decompressed payload ({len(result)} bytes) exceeds "
            f"max_bytes limit ({max_bytes} bytes)"
        )
    return result
