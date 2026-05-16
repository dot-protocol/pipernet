"""
Track-B Option A — EXPT-004: WRT preprocessing impact on track-B pipeline.

Measures the actual gain from applying Skibinski-style word replacement
BEFORE the track-B encode pass. Per RESEARCH-2026-05-16.md the literature
suggests 5-10% on enwik9 with a full dictionary. v0 uses a self-trained
dict of 315 entries (vs Skibinski's ~80k), so this is the FLOOR of the
technique.

Method:
  1. Encode raw data with track-B (geometric AND tuned-logistic) → baseline
  2. Encode WRT(data) with track-B (same configs) → treatment
  3. Roundtrip verify on both pipelines
  4. Compare blob sizes

The dictionary cost is OUT OF SCOPE here — a real submission ships the
dict as part of the decoder. At 100KB scale the dict is ~2-3 KB which
would dominate the gain; at enwik9 scale it amortises to negligible.

Usage:
    python3 expt_wrt.py [SLICE_BYTES] [PASSES] [LR]
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

from option_a.codec import encode, decode  # type: ignore
from option_a.mixer import multi_mix_logistic, multi_mix_geometric  # type: ignore
from option_a.predictors import MarkovPredictor, MatchPredictor  # type: ignore
from option_a.tuner import tune_weights, make_factory  # type: ignore
from option_a.wrt import build_dictionary, encode_wrt, decode_wrt, measure  # type: ignore


def main(slice_bytes: int = 100_000, num_passes: int = 1, lr: float = 0.05) -> int:
    candidates = [Path("/tmp/enwik8_1mb"), Path("/tmp/enwik8")]
    src = next((p for p in candidates if p.exists()), None)
    if src is None:
        print("ERROR: enwik8 not found", file=sys.stderr)
        return 1
    raw = src.read_bytes()[:slice_bytes]
    n = len(raw)
    print(f"corpus: {src} [:{n:_}]")

    gz_raw = len(gzip.compress(raw, compresslevel=9))
    print(f"gzip-9 (raw):         {gz_raw:_} bytes  bpb={gz_raw*8/n:.4f}\n")

    # Build dictionary from the corpus itself (self-trained for measurement;
    # production codec would ship a pre-built dict in the decoder binary)
    dictionary = build_dictionary(raw, max_entries=315)
    stats = measure(raw, dictionary)
    print(f"WRT dict entries:     {len(dictionary)}")
    print(f"WRT match rate:       {stats['match_rate']*100:.1f}% of word occurrences")
    print(f"WRT raw savings:      {stats['estimated_savings_bytes']:_} bytes  "
          f"({stats['estimated_savings_pct']:.2f}%)")

    wrt_data = encode_wrt(raw, dictionary)
    # Roundtrip
    rt = decode_wrt(wrt_data, dictionary)
    assert rt == raw, "WRT roundtrip failed"
    print(f"WRT output:           {len(wrt_data):_} bytes  ({len(wrt_data)/n*100:.2f}% of input)\n")

    # ─── RAW pipeline ──────────────────────────────────────────────────
    print("=" * 78)
    print("[RAW + track-B geometric]")
    t0 = time.perf_counter()
    geom_raw = encode(raw, make_factory, mixer=multi_mix_geometric)
    print(f"  encode: {len(geom_raw):>10_} bytes  bpb={len(geom_raw)*8/n:.4f}  enc={time.perf_counter()-t0:.2f}s")
    # Verify roundtrip
    back = decode(geom_raw, make_factory, mixer=multi_mix_geometric)
    assert back == raw, "track-B raw geometric roundtrip FAILED"
    print(f"  roundtrip: ✓ byte-exact")

    # Tune weights for raw pipeline
    print("\n[RAW] tuning logistic weights via SGD...")
    t0 = time.perf_counter()
    raw_weights, _, _ = tune_weights(raw, num_passes=num_passes, lr_init=lr, verbose=False)
    print(f"  weights: {[f'{w:+.3f}' for w in raw_weights]}  ({time.perf_counter()-t0:.2f}s)")

    def raw_logistic_mixer(predictors):
        return multi_mix_logistic(predictors, weights=raw_weights.tolist())
    t0 = time.perf_counter()
    log_raw = encode(raw, make_factory, mixer=raw_logistic_mixer)
    print(f"  encode (tuned logistic): {len(log_raw):>10_} bytes  bpb={len(log_raw)*8/n:.4f}  "
          f"enc={time.perf_counter()-t0:.2f}s")
    back = decode(log_raw, make_factory, mixer=raw_logistic_mixer)
    assert back == raw, "track-B raw logistic roundtrip FAILED"
    print(f"  roundtrip: ✓ byte-exact")

    # ─── WRT pipeline ──────────────────────────────────────────────────
    print("\n" + "=" * 78)
    print("[WRT + track-B geometric]")
    nw = len(wrt_data)
    # bpb still computed on ORIGINAL size for fair comparison
    t0 = time.perf_counter()
    geom_wrt = encode(wrt_data, make_factory, mixer=multi_mix_geometric)
    print(f"  encode: {len(geom_wrt):>10_} bytes  bpb={len(geom_wrt)*8/n:.4f}  enc={time.perf_counter()-t0:.2f}s")
    back = decode(geom_wrt, make_factory, mixer=multi_mix_geometric)
    assert back == wrt_data, "track-B WRT geometric roundtrip FAILED"
    raw_back = decode_wrt(back, dictionary)
    assert raw_back == raw, "WRT decode after track-B decode FAILED"
    print(f"  roundtrip: ✓ byte-exact (full pipeline)")

    # Tune weights for WRT pipeline
    print("\n[WRT] tuning logistic weights via SGD on WRT data...")
    t0 = time.perf_counter()
    wrt_weights, _, _ = tune_weights(wrt_data, num_passes=num_passes, lr_init=lr, verbose=False)
    print(f"  weights: {[f'{w:+.3f}' for w in wrt_weights]}  ({time.perf_counter()-t0:.2f}s)")

    def wrt_logistic_mixer(predictors):
        return multi_mix_logistic(predictors, weights=wrt_weights.tolist())
    t0 = time.perf_counter()
    log_wrt = encode(wrt_data, make_factory, mixer=wrt_logistic_mixer)
    print(f"  encode (tuned logistic): {len(log_wrt):>10_} bytes  bpb={len(log_wrt)*8/n:.4f}  "
          f"enc={time.perf_counter()-t0:.2f}s")
    back = decode(log_wrt, make_factory, mixer=wrt_logistic_mixer)
    assert back == wrt_data, "track-B WRT logistic roundtrip FAILED"
    raw_back = decode_wrt(back, dictionary)
    assert raw_back == raw, "Full WRT pipeline failed"
    print(f"  roundtrip: ✓ byte-exact (full pipeline)")

    # ─── Comparison ────────────────────────────────────────────────────
    print("\n" + "=" * 78)
    print(f"{'PIPELINE':<32}{'BYTES':>12}{'bpb':>9}{'vs RAW':>12}")
    print("-" * 78)
    print(f"{'gzip-9 (raw)':<32}{gz_raw:>12_}{gz_raw*8/n:>9.4f}{'baseline':>12}")
    print(f"{'track-B geometric (raw)':<32}{len(geom_raw):>12_}{len(geom_raw)*8/n:>9.4f}{0:>+12.3f}")
    print(f"{'track-B tuned (raw)':<32}{len(log_raw):>12_}{len(log_raw)*8/n:>9.4f}"
          f"{(len(log_raw)-len(geom_raw))*100/len(geom_raw):>+12.3f}%")
    print(f"{'track-B geometric (WRT)':<32}{len(geom_wrt):>12_}{len(geom_wrt)*8/n:>9.4f}"
          f"{(len(geom_wrt)-len(geom_raw))*100/len(geom_raw):>+12.3f}%")
    print(f"{'track-B tuned (WRT)':<32}{len(log_wrt):>12_}{len(log_wrt)*8/n:>9.4f}"
          f"{(len(log_wrt)-len(geom_raw))*100/len(geom_raw):>+12.3f}%")

    # The headline number: best-WRT vs best-RAW
    best_raw = min(len(geom_raw), len(log_raw))
    best_wrt = min(len(geom_wrt), len(log_wrt))
    delta_pct = (best_raw - best_wrt) * 100.0 / best_raw
    print("\n" + "=" * 78)
    print(f"WRT preprocessing gain: {delta_pct:+.3f}% on track-B")
    gate = 3.0  # WRT v0 with 315-entry dict; literature says 5-10% with 80k dict
    verdict = "PASS" if delta_pct >= gate else "FAIL"
    print(f"  Target: ≥{gate}% (v0 floor; full dict expected 5-10%) → {verdict}")
    return 0 if delta_pct >= gate else 1


if __name__ == "__main__":
    slice_size = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
    n_passes = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    learning_rate = float(sys.argv[3]) if len(sys.argv) > 3 else 0.05
    sys.exit(main(slice_size, n_passes, learning_rate))
