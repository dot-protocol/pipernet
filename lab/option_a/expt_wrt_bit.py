"""
Track-B Option A — EXPT-019: WRT preprocessing → bit-level mix.

EXPT-004/005 (earlier today) showed WRT preprocessing was a NULL on the
byte-level Phase 1 codec. The hypothesis there: byte-level predictors
trained on natural English text can't decode WRT-encoded tokens (escape
codes look like noise to a Markov/match model that doesn't know about them).

Now we have a bit-level mix with multi-Indirect + tuner. The Indirect maps
re-learn distributions from scratch — they don't carry assumptions about
"natural English byte frequency". They MAY be able to handle WRT bytes.

Test: encode WRT(data) with the EXPT-014 best stack (4 children + tuner),
compare against raw bit_encode(data).

Output size accounting:
  raw:     bit_encode(data).length
  WRT:     wrt(data) → bit_encode(...).length

Total cost for WRT path = compressed_wrt + dictionary_overhead.
For 100KB enwik8 the WRT dictionary is small (~few KB). For honest
comparison we include the dictionary in the WRT total.

Usage:
    python3 expt_wrt_bit.py [SLICE_BYTES]
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
from option_a.bit_tuner import tune_bit_weights  # type: ignore
from option_a.mixer import multi_mix_logistic  # type: ignore
from option_a.predictors import MarkovPredictor, MatchPredictor  # type: ignore
from option_a.wrt import build_dictionary, encode_wrt, decode_wrt  # type: ignore


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


def baseline_children():
    return [
        BytewiseBitPredictor(make_byte_factory(), byte_mixer=byte_phase1_mixer),
        IndirectBitPredictor(context_fn=None, map_size=1 << 24, lr=0.05, history_window=3),
        IndirectBitPredictor(context_fn=None, map_size=1 << 22, lr=0.05, history_window=2),
        IndirectBitPredictor(context_fn=None, map_size=1 << 20, lr=0.05, history_window=1),
    ]


def make_factory(weights):
    def factory():
        return MultiBitPredictor(children=baseline_children(), weights=list(weights))
    return factory


def measure(label, data, initial):
    n = len(data)
    t0 = time.perf_counter()
    weights, _ = tune_bit_weights(
        data, baseline_children, num_passes=1, lr_init=0.01,
        initial_weights=initial, verbose=False,
    )
    tt = time.perf_counter() - t0
    t0 = time.perf_counter()
    blob = bit_encode(data, make_factory(weights.tolist()), precision=DEFAULT_BIT_PRECISION)
    et = time.perf_counter() - t0
    back = bit_decode(blob, make_factory(weights.tolist()), precision=DEFAULT_BIT_PRECISION)
    rt = "✓" if back == data else "✗"
    return label, len(blob), len(blob) * 8 / n, tt, et, rt, weights.tolist()


def main(slice_bytes: int = 100_000) -> int:
    candidates = [Path("/tmp/enwik8"), Path("/tmp/enwik8_1mb")]
    src = next((p for p in candidates if p.exists()), None)
    if src is None:
        print("ERROR: enwik8 not found", file=sys.stderr)
        return 1
    data = src.read_bytes()[:slice_bytes]
    n = len(data)
    gz = len(gzip.compress(data, compresslevel=9))
    print(f"corpus: {src} [:{n:_}]   gzip-9: {gz:_} bytes ({gz*8/n:.4f} bpb)\n")

    # WRT preprocess on FULL data (dictionary built from corpus, transparent)
    print(f"[WRT preprocess]")
    t0 = time.perf_counter()
    dictionary = build_dictionary(data, max_entries=315, min_word_len=3)
    dict_t = time.perf_counter() - t0

    t0 = time.perf_counter()
    wrt_data = encode_wrt(data, dictionary)
    wrt_enc_t = time.perf_counter() - t0
    print(f"  dictionary entries: {len(dictionary)}  (build {dict_t:.2f}s)")
    print(f"  wrt(data) length: {len(wrt_data):_} bytes  ({len(wrt_data)*100.0/n:.2f}% of raw)")
    print(f"  wrt encode time:  {wrt_enc_t:.2f}s")

    # Dictionary overhead estimate: serialize dict as bytes (sum of word lengths)
    dict_overhead = sum(len(w) + 1 for w in dictionary)  # +1 byte separator
    print(f"  dict serialized:  ~{dict_overhead:_} bytes overhead")
    print()

    # Verify WRT roundtrip
    decoded_test = decode_wrt(wrt_data, dictionary)
    if decoded_test != data:
        print(f"WRT roundtrip BROKEN — abort")
        return 2

    print(f"{'variant':<48}{'bytes':>10}{'bpb':>8}{'vs gzip':>10}{'tune s':>8}{'enc s':>7}{'rt':>4}")
    print("-" * 95)

    # Raw bit-mix encode
    init = [0.9, 0.20, 0.12, 0.08]
    lab, b_raw, bpb, tt, et, rt, w = measure("raw (no WRT)", data, init)
    delta = (b_raw - gz) * 100 / gz
    print(f"{lab:<48}{b_raw:>10_}{bpb:>8.4f}{delta:>+9.3f}%{tt:>8.1f}{et:>7.1f}{rt:>4}")

    # WRT-encoded bit-mix encode
    lab, b_wrt, bpb, tt, et, rt, w = measure("WRT(data) → bit-mix encode", wrt_data, init)
    # Add dictionary overhead for honest accounting
    total_wrt = b_wrt + dict_overhead
    delta_total = (total_wrt - gz) * 100 / gz
    delta_no_dict = (b_wrt - gz) * 100 / gz
    print(f"{lab:<48}{b_wrt:>10_}{bpb:>8.4f}{delta_no_dict:>+9.3f}%{tt:>8.1f}{et:>7.1f}{rt:>4}")
    print(f"  + dict overhead ({dict_overhead:_} bytes) → total {total_wrt:_} bytes, vs gzip {delta_total:+.3f}%")

    print()
    if total_wrt < b_raw:
        print(f"VERDICT: WRT helps ({b_raw - total_wrt:_} bytes saved, {(b_raw - total_wrt)*100/b_raw:.3f}% improvement)")
    else:
        print(f"VERDICT: WRT NULL or hurts ({total_wrt - b_raw:_} bytes worse, {(total_wrt - b_raw)*100/b_raw:.3f}%)")

    return 0


if __name__ == "__main__":
    slice_size = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
    sys.exit(main(slice_size))
