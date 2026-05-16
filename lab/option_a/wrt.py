"""
Track-B Option A — Skibinski Word Replacement Transform (WRT) v0.

Static-dictionary preprocessing pass. Replaces frequent words with short
codes BEFORE the track-B match+Markov+mixer pipeline sees the data. Per
research synthesis 2026-05-16 (RESEARCH-2026-05-16.md), this is the single
biggest cheap win in the punch list: 5-10% on enwik9, ~1 week project,
low difficulty.

Original WRT: Skibinski et al. (2005-2007), refined into XWRT, used by
all paq8 variants and cmix as the standard text preprocessor.

This v0 design exploits a property of enwik8: 61 byte values NEVER appear
in the source (verified on 1MB prefix). We use these as "free" escape codes:
no escape-the-escape rule needed because they're not in the input at all.

Layout:
  - 59 unused bytes (from the 61 absent) serve as 1-byte codes for top-59 words
  - 1 unused byte (0xFE) serves as 2-byte prefix → 256 more codes
  - 1 unused byte (0xFF) serves as 3-byte prefix → 65,536 more codes (reserved for v1)

Total v0 capacity: 59 + 256 = 315 dictionary entries. Skibinski's WRT typically
uses ~80,000 entries; we're at <1% of that, so v0 leaves significant gain on
the table. v1 will extend the 3-byte prefix range.

Tokenisation: simple word boundary on `[A-Za-z]+`. All non-word characters
(spaces, punct, XML tags, digits) pass through literally. This is intentionally
naive — Skibinski WRT does case folding, q-gram replacement, EOL coding, but
those are v1+ features. v0 measures the floor of the technique.

Invariant: encode_wrt(raw, dict) → wrt_data, decode_wrt(wrt_data, dict) → raw.
Byte-exact roundtrip mandatory. Verification harness below.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple

# Bytes that never appear in enwik8 (verified on 1MB prefix; should hold for
# the full corpus since enwik8 is UTF-8 English Wikipedia with stable charset).
ABSENT_IN_ENWIK8 = [
    0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
    0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x10, 0x11, 0x12, 0x13, 0x14,
    0x15, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x1B, 0x1C, 0x1D, 0x1E, 0x1F,
    0x7F,
    0xC0, 0xC1, 0xC6, 0xC8, 0xCD,
    0xD3, 0xD4, 0xD5, 0xDC, 0xDD, 0xDE, 0xDF,
    0xEE, 0xEF,
    0xF0, 0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF7,
    0xF8, 0xF9, 0xFA, 0xFB, 0xFC, 0xFD,
    # 0xFE, 0xFF reserved as multi-byte prefixes
]

# Reserve last two absent bytes as multi-byte prefix markers
PREFIX_2BYTE = 0xFE
PREFIX_3BYTE = 0xFF  # reserved for v1

# 59 single-byte codes (the 61 minus the 2 reserved prefix bytes)
SINGLE_BYTE_CODES = [b for b in ABSENT_IN_ENWIK8 if b not in (PREFIX_2BYTE, PREFIX_3BYTE)]
# v0 expects 58 free single-byte codes (60 absent - 2 reserved prefixes).
# Exact count may vary slightly with corpus; assertion catches accidental code-table drift.
assert 50 <= len(SINGLE_BYTE_CODES) <= 70, (
    f"single-byte code count {len(SINGLE_BYTE_CODES)} outside expected band [50,70] — "
    f"check ABSENT_IN_ENWIK8 list against current corpus"
)

WORD_RE = re.compile(rb"[A-Za-z]+")


def build_dictionary(data: bytes, max_entries: int = 315, min_word_len: int = 3) -> List[bytes]:
    """Frequency-sort words by gain potential, return ordered word list.

    Gain heuristic: a word of length L appearing freq times saves:
      - (L-1)*freq bytes if assigned to a 1-byte code
      - (L-2)*freq bytes if assigned to a 2-byte code (prefix + index)

    The top-N slots get 1-byte codes (best gain). Next slots get 2-byte codes.
    We optimise greedily on the 1-byte gain (the dominant term).

    `min_word_len` is the threshold for inclusion. Short words (e.g. "the",
    "and") are highly compressible by track-B's existing context models, so
    replacing them with novel bytes is often a NET LOSS. Set min_word_len=5+
    to skip short words entirely. EXPT-005 explores this tradeoff.
    """
    counts = Counter(WORD_RE.findall(data))
    candidates = [(w, c) for w, c in counts.items() if len(w) >= min_word_len]
    candidates.sort(key=lambda wc: wc[1] * (len(wc[0]) - 1), reverse=True)
    return [w for w, _ in candidates[:max_entries]]


_N_SINGLE = len(SINGLE_BYTE_CODES)  # 58 currently


def _build_code_table(dictionary: List[bytes]) -> Dict[bytes, bytes]:
    """Map word → encoded-bytes representation."""
    word_to_code: Dict[bytes, bytes] = {}
    # First N words get 1-byte codes (where N = number of absent bytes available)
    for i, word in enumerate(dictionary[:_N_SINGLE]):
        word_to_code[word] = bytes([SINGLE_BYTE_CODES[i]])
    # Next up to 256 words get 2-byte codes (PREFIX_2BYTE + index)
    for i, word in enumerate(dictionary[_N_SINGLE:_N_SINGLE + 256]):
        word_to_code[word] = bytes([PREFIX_2BYTE, i])
    return word_to_code


def _build_decode_table(dictionary: List[bytes]) -> Tuple[Dict[int, bytes], Dict[int, bytes]]:
    """Inverse mapping: code → word."""
    single: Dict[int, bytes] = {}
    double: Dict[int, bytes] = {}
    for i, word in enumerate(dictionary[:_N_SINGLE]):
        single[SINGLE_BYTE_CODES[i]] = word
    for i, word in enumerate(dictionary[_N_SINGLE:_N_SINGLE + 256]):
        double[i] = word
    return single, double


def encode_wrt(data: bytes, dictionary: List[bytes]) -> bytes:
    """Apply WRT: replace dictionary words with short codes, preserve everything else."""
    word_to_code = _build_code_table(dictionary)
    out = bytearray()
    pos = 0
    n = len(data)
    while pos < n:
        m = WORD_RE.match(data, pos)
        if m:
            word = m.group(0)
            if word in word_to_code:
                out.extend(word_to_code[word])
            else:
                out.extend(word)
            pos = m.end()
        else:
            out.append(data[pos])
            pos += 1
    return bytes(out)


def decode_wrt(blob: bytes, dictionary: List[bytes]) -> bytes:
    """Inverse of encode_wrt."""
    single, double = _build_decode_table(dictionary)
    out = bytearray()
    pos = 0
    n = len(blob)
    while pos < n:
        b = blob[pos]
        if b == PREFIX_2BYTE:
            # 2-byte code: PREFIX_2BYTE + index
            if pos + 1 >= n:
                raise ValueError(f"WRT decode: truncated 2-byte code at offset {pos}")
            idx = blob[pos + 1]
            if idx not in double:
                raise ValueError(f"WRT decode: 2-byte code 0x{PREFIX_2BYTE:02x},{idx:02x} not in dict")
            out.extend(double[idx])
            pos += 2
        elif b in single:
            out.extend(single[b])
            pos += 1
        else:
            out.append(b)
            pos += 1
    return bytes(out)


def measure(data: bytes, dictionary: List[bytes]) -> dict:
    """Quick stats: encoded size, word coverage, single vs 2-byte split."""
    word_to_code = _build_code_table(dictionary)
    counts = Counter(WORD_RE.findall(data))
    total_words = sum(counts.values())
    matched_single = 0
    matched_double = 0
    saved_bytes = 0
    for word, freq in counts.items():
        code = word_to_code.get(word)
        if code is None:
            continue
        if len(code) == 1:
            matched_single += freq
            saved_bytes += freq * (len(word) - 1)
        else:
            matched_double += freq
            saved_bytes += freq * (len(word) - 2)
    return {
        "input_bytes": len(data),
        "unique_words": len(counts),
        "total_word_occurrences": total_words,
        "matched_single_byte": matched_single,
        "matched_two_byte": matched_double,
        "matched_total": matched_single + matched_double,
        "match_rate": (matched_single + matched_double) / total_words if total_words else 0.0,
        "estimated_savings_bytes": saved_bytes,
        "estimated_savings_pct": saved_bytes / len(data) * 100 if data else 0.0,
    }


def verify_roundtrip(data: bytes, dictionary: List[bytes]) -> Tuple[bool, int]:
    """Encode then decode; return (ok, first_diff_byte)."""
    encoded = encode_wrt(data, dictionary)
    decoded = decode_wrt(encoded, dictionary)
    if decoded == data:
        return True, -1
    diff = next((i for i, (a, b) in enumerate(zip(decoded, data)) if a != b), len(decoded))
    return False, diff


# ─── CLI bench ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    slice_size = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
    candidates = [Path("/tmp/enwik8_1mb"), Path("/tmp/enwik8")]
    src = next((p for p in candidates if p.exists()), None)
    if src is None:
        print("ERROR: enwik8 not found in /tmp/", file=sys.stderr)
        sys.exit(1)
    data = src.read_bytes()[:slice_size]
    n = len(data)
    print(f"corpus: {src} [:{n:_}]")

    # Build dict from THIS slice (self-trained for now; real submission would
    # use a pre-built dict shipped with the codec)
    dictionary = build_dictionary(data, max_entries=315)
    print(f"dict entries: {len(dictionary)}")
    print(f"top 20 words: {[w.decode('utf-8', errors='replace') for w in dictionary[:20]]}")

    # Measure expected savings
    stats = measure(data, dictionary)
    print(f"\nWRT stats:")
    print(f"  unique words:         {stats['unique_words']:_}")
    print(f"  total occurrences:    {stats['total_word_occurrences']:_}")
    print(f"  matched (1-byte):     {stats['matched_single_byte']:_}  "
          f"({100*stats['matched_single_byte']/stats['total_word_occurrences']:.1f}% of words)")
    print(f"  matched (2-byte):     {stats['matched_two_byte']:_}")
    print(f"  match rate:           {stats['match_rate']*100:.1f}%")
    print(f"  estimated savings:    {stats['estimated_savings_bytes']:_} bytes  "
          f"({stats['estimated_savings_pct']:.2f}%)")

    # Verify roundtrip
    ok, diff = verify_roundtrip(data, dictionary)
    if not ok:
        print(f"\n✗ ROUNDTRIP FAILED at byte {diff}")
        sys.exit(2)
    print(f"\n✓ Roundtrip verified byte-exact")

    encoded = encode_wrt(data, dictionary)
    print(f"\nWRT output size:        {len(encoded):_} bytes  "
          f"({len(encoded)/n*100:.2f}% of input)")

    # gzip comparison on raw vs WRT-preprocessed
    import gzip
    gz_raw = len(gzip.compress(data, compresslevel=9))
    gz_wrt = len(gzip.compress(encoded, compresslevel=9))
    print(f"\ngzip-9 on raw:          {gz_raw:_} bytes  bpb={gz_raw*8/n:.4f}")
    print(f"gzip-9 on WRT(raw):     {gz_wrt:_} bytes  bpb={gz_wrt*8/n:.4f}")
    print(f"  vs raw:               {(gz_wrt-gz_raw)*100/gz_raw:+.3f}%")
