"""
Track-B Option A — fast dev bench harness.

Iterates predictor configurations on a small corpus (default 100KB enwik8)
with byte-exact round-trip verification. Sub-10s per config for tight
inner-loop development. Run before any larger bench to catch regressions.

Usage:
    python3 bench_dev.py                 # default: 100KB, all baseline configs
    python3 bench_dev.py 10000           # 10KB slice (faster)
    python3 bench_dev.py 1000000         # 1MB slice (overnight ratification)

Reports per-config table:
    config          bytes      bpb     vs gzip    enc_t   dec_t   roundtrip
    geometric       37,502     3.000   -...%      ...s    ...s    ✓
    logistic-w1     37,...     ...     ...%       ...s    ...s    ✓
    + sparse(2)     ...        ...     ...%       ...s    ...s    ✓

The gzip-9 baseline is always reported as the comparison anchor.
Round-trip verification is mandatory — if any config fails, the row is
marked ✗ and a diagnostic snippet is printed.
"""

from __future__ import annotations

import gzip
import hashlib
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List

# package imports
HERE = Path(__file__).resolve().parent
LAB = HERE.parent
sys.path.insert(0, str(LAB))

from option_a.codec import encode, decode, default_v03cy_factory  # type: ignore
from option_a.mixer import multi_mix_geometric, multi_mix_logistic  # type: ignore
from option_a.predictors import MarkovPredictor, MatchPredictor  # type: ignore
from option_a.predictor import Predictor  # type: ignore


@dataclass
class BenchResult:
    name: str
    blob_bytes: int
    bpb: float
    vs_gzip_pct: float
    enc_t: float
    dec_t: float
    roundtrip_ok: bool
    blob_sha: str
    diff_byte: int = -1  # first differing byte if roundtrip failed; -1 if ok


def run_one(data: bytes, name: str, factory: Callable[[], List[Predictor]],
            mixer=multi_mix_geometric) -> BenchResult:
    """Run one encode/decode round, report result."""
    n = len(data)
    t0 = time.perf_counter()
    try:
        blob = encode(data, factory, mixer=mixer)
        enc_t = time.perf_counter() - t0
    except Exception as e:
        print(f"  {name}: ENCODE FAILED — {e}")
        raise

    t0 = time.perf_counter()
    try:
        back = decode(blob, factory, mixer=mixer)
        dec_t = time.perf_counter() - t0
    except Exception as e:
        print(f"  {name}: DECODE FAILED — {e}")
        return BenchResult(
            name=name, blob_bytes=len(blob), bpb=len(blob) * 8 / n,
            vs_gzip_pct=0.0, enc_t=enc_t, dec_t=-1.0,
            roundtrip_ok=False, blob_sha=hashlib.sha256(blob).hexdigest(),
        )

    if back != data:
        diff = next((i for i, (a, b) in enumerate(zip(back, data)) if a != b), len(back))
        return BenchResult(
            name=name, blob_bytes=len(blob), bpb=len(blob) * 8 / n,
            vs_gzip_pct=0.0, enc_t=enc_t, dec_t=dec_t,
            roundtrip_ok=False, blob_sha=hashlib.sha256(blob).hexdigest(),
            diff_byte=diff,
        )

    return BenchResult(
        name=name, blob_bytes=len(blob), bpb=len(blob) * 8 / n,
        vs_gzip_pct=0.0,  # filled after gzip baseline
        enc_t=enc_t, dec_t=dec_t,
        roundtrip_ok=True, blob_sha=hashlib.sha256(blob).hexdigest(),
    )


def main(slice_bytes: int = 100_000) -> int:
    # Locate corpus
    candidates = [
        Path("/tmp/enwik8_1mb"),
        Path("/tmp/enwik8"),
        Path.home() / "Downloads" / "enwik8",
    ]
    src = next((p for p in candidates if p.exists()), None)
    if src is None:
        print("ERROR: enwik8 not found in /tmp/enwik8 or /tmp/enwik8_1mb or ~/Downloads/enwik8", file=sys.stderr)
        return 1

    data = src.read_bytes()[:slice_bytes]
    n = len(data)
    raw_sha = hashlib.sha256(data).hexdigest()
    print(f"corpus:  {src} [:{n:_}]")
    print(f"sha256:  {raw_sha}")
    print("-" * 78)

    # gzip-9 baseline anchor
    t0 = time.perf_counter()
    gz_blob = gzip.compress(data, compresslevel=9)
    gz_t = time.perf_counter() - t0
    gz_size = len(gz_blob)
    print(f"gzip -9      bytes={gz_size:>10_}  bpb={gz_size*8/n:6.3f}  enc={gz_t:5.2f}s  (baseline)")

    # Configs to bench
    configs = [
        ("geometric (v0.3cy parity)", default_v03cy_factory, multi_mix_geometric),
        ("logistic w=1 (uniform)", default_v03cy_factory, multi_mix_logistic),
        # Future configs land here as new predictors come online:
        # ("+ match K=2", lambda: default_v03cy_factory() + [MatchPredictor(window=2)], multi_mix_geometric),
        # ("+ sparse skip=2", ..., multi_mix_geometric),
    ]

    results: List[BenchResult] = []
    for name, factory, mixer in configs:
        print(f"\n[{name}]")
        res = run_one(data, name, factory, mixer)
        res.vs_gzip_pct = (res.blob_bytes - gz_size) * 100.0 / gz_size
        ok = "✓" if res.roundtrip_ok else f"✗ diff@{res.diff_byte}"
        print(f"  bytes={res.blob_bytes:>10_}  bpb={res.bpb:6.3f}  vs gzip={res.vs_gzip_pct:+6.2f}%  enc={res.enc_t:5.2f}s  dec={res.dec_t:5.2f}s  {ok}")
        print(f"  sha256={res.blob_sha}")
        results.append(res)

    # Summary
    print()
    print("=" * 78)
    print(f"{'config':<32} {'bytes':>12} {'bpb':>7} {'vs gzip':>9} {'enc':>7} {'dec':>7} {'rt':>3}")
    print("-" * 78)
    print(f"{'gzip-9 (anchor)':<32} {gz_size:>12_} {gz_size*8/n:>7.3f} {'0.00%':>9} {gz_t:>6.2f}s {'-':>7} {'✓':>3}")
    for r in results:
        ok = "✓" if r.roundtrip_ok else "✗"
        vs = f"{r.vs_gzip_pct:+.2f}%"
        print(f"{r.name:<32} {r.blob_bytes:>12_} {r.bpb:>7.3f} {vs:>9} {r.enc_t:>6.2f}s {r.dec_t:>6.2f}s {ok:>3}")

    # Decision gates
    print()
    geom = next((r for r in results if "geometric" in r.name and r.roundtrip_ok), None)
    logi = next((r for r in results if "logistic" in r.name and r.roundtrip_ok), None)
    if geom and logi:
        delta = (geom.blob_bytes - logi.blob_bytes) * 100.0 / geom.blob_bytes
        gate_target = 0.5
        verdict = "PASS" if delta >= gate_target else "FAIL"
        sign = "logistic better" if delta > 0 else "geometric better"
        print(f"Phase 1 decision gate: logistic vs geometric = {delta:+.3f}% ({sign})")
        print(f"  Target: ≥{gate_target}% logistic improvement → {verdict}")
        if delta >= gate_target:
            print(f"  → switch default mixer to logistic for Phase 2+")
        else:
            print(f"  → stay with geometric; logistic remains as opt-in for future tuning")

    any_fail = any(not r.roundtrip_ok for r in results)
    if any_fail:
        print("\n✗ ONE OR MORE CONFIGS FAILED ROUND-TRIP — investigate before proceeding")
        return 2

    return 0


if __name__ == "__main__":
    slice_size = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
    sys.exit(main(slice_size))
