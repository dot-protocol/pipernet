"""
Byte-exact verification harness.

Compares our pure-Python pluggable-predictor pipeline against the existing
Cython mixer_multi_cy.encode/decode on the v0.3cy baseline config
(Markov + 4 Match at windows 3,5,8,12). If our pipeline produces the
same blob byte-for-byte, the predictor interface refactor is correct.

Usage:
    python3 verify_byte_exact.py [SLICE_BYTES]

Default slice: enwik8[:10000] (fast iteration). Bump to 1_000_000 for
the 1MB confidence check before broadcasting Phase 1 success.
"""

import hashlib
import sys
import time
from pathlib import Path


def main(slice_bytes: int = 10_000) -> int:
    # Locate enwik8
    candidates = [
        Path("/tmp/enwik8_1mb"),
        Path("/tmp/enwik8"),
        Path.home() / "Downloads/enwik8",
    ]
    src = next((p for p in candidates if p.exists()), None)
    if src is None:
        print("ERROR: enwik8 not found. Tried:", file=sys.stderr)
        for p in candidates:
            print(f"  {p}", file=sys.stderr)
        return 1

    data = src.read_bytes()[:slice_bytes]
    n = len(data)
    print(f"corpus: {src} [:{n:_}]")
    print(f"sha256: {hashlib.sha256(data).hexdigest()}")
    print("-" * 70)

    # Reference: existing Cython implementation
    HERE = Path(__file__).resolve().parent
    TRACKB = HERE.parents[2] / "middle-out" / "track-b"
    sys.path.insert(0, str(TRACKB))
    import mixer_multi_cy as cy_module  # noqa: E402

    t0 = time.perf_counter()
    ref_blob = cy_module.encode(data)
    ref_enc_t = time.perf_counter() - t0
    ref_sha = hashlib.sha256(ref_blob).hexdigest()
    print(f"ref (mixer_multi_cy):   {len(ref_blob):>10_} bytes  enc={ref_enc_t:6.2f}s")
    print(f"  sha256:                {ref_sha}")

    # Pure-Python pluggable pipeline
    sys.path.insert(0, str(HERE.parent))  # lab/ on path
    # (lab/ already on path)
    from option_a.codec import encode as plug_encode, decode as plug_decode, default_v03cy_factory  # type: ignore

    t0 = time.perf_counter()
    plug_blob = plug_encode(data, default_v03cy_factory)
    plug_enc_t = time.perf_counter() - t0
    plug_sha = hashlib.sha256(plug_blob).hexdigest()
    print(f"plug (option-a, pure):  {len(plug_blob):>10_} bytes  enc={plug_enc_t:6.2f}s")
    print(f"  sha256:                {plug_sha}")
    print()

    # Compare
    if ref_blob == plug_blob:
        print("✓ BYTE-EXACT MATCH — pluggable pipeline produces identical blob")
        match_ok = True
    else:
        # Find first differing byte
        for i, (a, b) in enumerate(zip(ref_blob, plug_blob)):
            if a != b:
                print(f"✗ FIRST DIFF at byte {i}: ref={a:#04x} plug={b:#04x}")
                break
        else:
            if len(ref_blob) != len(plug_blob):
                print(f"✗ LENGTH DIFF: ref={len(ref_blob)} plug={len(plug_blob)}")
        match_ok = False

    # Round-trip the plug blob
    t0 = time.perf_counter()
    plug_back = plug_decode(plug_blob, default_v03cy_factory)
    plug_dec_t = time.perf_counter() - t0
    plug_back_ok = plug_back == data
    print(f"plug round-trip:        dec={plug_dec_t:6.2f}s  byte-exact={plug_back_ok}")

    print()
    print(f"Speed ratio plug/ref:   {plug_enc_t / ref_enc_t:.1f}x slower " +
          f"({plug_enc_t:.2f}s vs {ref_enc_t:.2f}s)")
    print(f"  Expected — pure Python mixer is the dev/spec version; the .pyx is the hot path.")
    print(f"  Once Phase 1 ships predictors, port the hot path to Cython for parity.")

    return 0 if (match_ok and plug_back_ok) else 2


if __name__ == "__main__":
    slice_size = int(sys.argv[1]) if len(sys.argv) > 1 else 10_000
    sys.exit(main(slice_size))
