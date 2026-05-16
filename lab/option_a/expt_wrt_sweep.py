"""
Track-B Option A — EXPT-005: WRT selectivity sweep over min_word_len.

EXPT-004 showed WRT v0 with min_word_len=3 (replacing short common words like
"the", "and") was a wash on track-B because the substitute bytes are novel
to predictors that had compressed those words to <1 bit/char already.

Hypothesis: there's a sweet spot for min_word_len where the words being
replaced are long enough that track-B's existing per-byte cost exceeds the
substitute-byte cost. Sweep min_word_len ∈ {3, 4, 5, 6, 7, 8} to find it.

Quick scan: geometric mixer only (no tuner) for speed. The winning K then
gets the full tuned-logistic comparison in EXPT-006.

Usage:
    python3 expt_wrt_sweep.py [SLICE_BYTES]
"""

from __future__ import annotations

import gzip
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAB = HERE.parent
sys.path.insert(0, str(LAB))

from option_a.codec import encode, decode  # type: ignore
from option_a.mixer import multi_mix_geometric  # type: ignore
from option_a.tuner import make_factory  # type: ignore
from option_a.wrt import build_dictionary, encode_wrt, decode_wrt, measure  # type: ignore


def main(slice_bytes: int = 100_000) -> int:
    candidates = [Path("/tmp/enwik8_1mb"), Path("/tmp/enwik8")]
    src = next((p for p in candidates if p.exists()), None)
    if src is None:
        print("ERROR: enwik8 not found", file=sys.stderr)
        return 1
    raw = src.read_bytes()[:slice_bytes]
    n = len(raw)
    print(f"corpus: {src} [:{n:_}]\n")

    gz_raw = len(gzip.compress(raw, compresslevel=9))
    print(f"gzip-9 (raw):                   {gz_raw:_} bytes  bpb={gz_raw*8/n:.4f}")

    # Baseline: track-B on raw
    t0 = time.perf_counter()
    geom_raw = encode(raw, make_factory, mixer=multi_mix_geometric)
    print(f"track-B geometric (raw):        {len(geom_raw):_} bytes  bpb={len(geom_raw)*8/n:.4f}  enc={time.perf_counter()-t0:.2f}s")
    raw_bpb_baseline = len(geom_raw) * 8 / n

    print("\n" + "=" * 78)
    print(f"{'min_word_len':<14}{'dict':>6}{'match%':>8}{'wrt_size':>12}{'tb_size':>12}{'tb_bpb':>9}{'vs_raw':>10}")
    print("-" * 78)

    for K in [3, 4, 5, 6, 7, 8]:
        dictionary = build_dictionary(raw, max_entries=315, min_word_len=K)
        if not dictionary:
            continue
        stats = measure(raw, dictionary)
        wrt_data = encode_wrt(raw, dictionary)
        # Verify roundtrip
        rt = decode_wrt(wrt_data, dictionary)
        if rt != raw:
            print(f"K={K}: WRT ROUNDTRIP FAILED")
            continue
        # Compress with track-B geometric
        blob = encode(wrt_data, make_factory, mixer=multi_mix_geometric)
        # Verify full-pipeline roundtrip
        back = decode(blob, make_factory, mixer=multi_mix_geometric)
        raw_back = decode_wrt(back, dictionary)
        if raw_back != raw:
            print(f"K={K}: FULL PIPELINE ROUNDTRIP FAILED")
            continue
        bpb = len(blob) * 8 / n
        delta = (len(blob) - len(geom_raw)) * 100.0 / len(geom_raw)
        print(f"K={K:<12}{len(dictionary):>6}{stats['match_rate']*100:>7.1f}%"
              f"{len(wrt_data):>12_}{len(blob):>12_}{bpb:>9.4f}{delta:>+9.3f}%")

    print("\nLower 'vs_raw' = better. Negative means WRT helped.")
    return 0


if __name__ == "__main__":
    slice_size = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
    sys.exit(main(slice_size))
