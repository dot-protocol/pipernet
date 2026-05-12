"""
test_compression — roundtrip, determinism, size guard, and bad-input tests
for the zstd compression module.
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from dotpost.compression import compress, decompress, _MAX_DECOMPRESSED_BYTES


class TestCompressDecompress(unittest.TestCase):

    def test_roundtrip_simple(self):
        """compress → decompress returns the original bytes."""
        data = b'{"v":"1","what":"Translate to French","refuse_substitution":true}'
        self.assertEqual(decompress(compress(data)), data)

    def test_roundtrip_empty(self):
        """Empty bytes survive the roundtrip."""
        self.assertEqual(decompress(compress(b"")), b"")

    def test_roundtrip_unicode(self):
        """UTF-8 multi-byte characters survive the roundtrip unchanged."""
        data = '{"what":"Übersetz auf Français – 日本語対応"}'.encode("utf-8")
        self.assertEqual(decompress(compress(data)), data)

    def test_roundtrip_large(self):
        """Repeated-string payload (compresses well) roundtrips correctly."""
        data = (b"x" * 1000 + b'{"k":"v"}') * 50
        self.assertEqual(decompress(compress(data)), data)

    def test_determinism(self):
        """Same input always produces identical compressed bytes."""
        data = b'{"intent":"stable","v":"1"}'
        c1 = compress(data)
        c2 = compress(data)
        self.assertEqual(c1, c2)

    def test_compression_reduces_size(self):
        """Compressing a repetitive payload produces fewer bytes."""
        data = b"hello world " * 100
        self.assertLess(len(compress(data)), len(data))

    def test_decompress_rejects_non_zstd(self):
        """Decompressing arbitrary bytes raises ValueError."""
        with self.assertRaises(ValueError):
            decompress(b"not-zstd-bytes-at-all-xyz")

    def test_decompress_size_guard(self):
        """Decompressing past max_bytes raises ValueError (size guard)."""
        # Compress 100 bytes, then ask for max_bytes=50 — forces the guard.
        payload = b"A" * 100
        compressed = compress(payload)
        with self.assertRaises(ValueError):
            decompress(compressed, max_bytes=50)

    def test_compress_rejects_non_bytes(self):
        """compress() raises TypeError for non-bytes input."""
        with self.assertRaises(TypeError):
            compress("not bytes")  # type: ignore[arg-type]

    def test_decompress_rejects_non_bytes(self):
        """decompress() raises TypeError for non-bytes input."""
        with self.assertRaises(TypeError):
            decompress("not bytes")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
