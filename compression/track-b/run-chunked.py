#!/usr/bin/env python3
"""Chunked enwik8 bench — subprocess-isolated per chunk for bounded peak RSS.

Linear-scale telemetry from profile-25mb (8.5 GB peak) and profile-50mb
(16.2 GB peak) implies full enwik8 (100 MB) needs ~32 GB peak in a single
process — which exceeds the 31 GB VPS. The fix: split corpus into N chunks,
encode each in a fresh Python process so the OS reclaims match-model memory
between chunks. Peak RSS = single chunk's peak, not the sum.

Encoder output format (TBCK1 chunk format, big-endian):
    4 bytes:   magic "TBCK"
    1 byte:    version (0x01)
    8 bytes:   total_n           — total INPUT bytes
    4 bytes:   chunk_count       — number of chunks
    4 bytes:   chunk_input_size  — canonical input bytes per chunk
                                   (last chunk may be smaller)
    for each chunk i in [0, chunk_count):
        4 bytes:  this chunk's INPUT byte count (chunk_in_i)
        8 bytes:  this chunk's BLOB byte count  (chunk_blob_i)
        N bytes:  the blob produced by cy_encode(input_chunk_i)

The decoder reads each chunk independently with cy_decode, concatenates,
and verifies total length. Roundtrip byte-exactness must hold.

Usage:
    # Encode-decode-verify cycle (default: full enwik8, 4 chunks of 25 MB)
    run-chunked.py [SLICE_BYTES] [CHUNK_BYTES]

    # Defaults: 100_000_000, 25_000_000   (4 chunks)
"""

from __future__ import annotations

import gzip
import hashlib
import os
import struct
import subprocess
import sys
import time
from pathlib import Path

MAGIC = b"TBCK"
VERSION = 0x01
HEADER_FMT = ">4sBQII"   # magic, version, total_n, chunk_count, chunk_input_size
CHUNK_HDR_FMT = ">IQ"    # chunk_in, chunk_blob

WORK = Path("/tmp/track-b-chunked")
ENWIK = Path("/tmp/enwik8")


# ----------------------------------------------------------------------------
# Worker entry points: invoked via subprocess to isolate memory between chunks.
# ----------------------------------------------------------------------------

def _worker_encode(in_path: str, out_path: str) -> int:
    sys.path.insert(0, "/opt/track-b")
    from mixer_multi_cy import encode as cy_encode  # type: ignore
    data = Path(in_path).read_bytes()
    blob = cy_encode(data)
    Path(out_path).write_bytes(blob)
    return 0


def _worker_decode(in_path: str, out_path: str) -> int:
    sys.path.insert(0, "/opt/track-b")
    from mixer_multi_cy import decode as cy_decode  # type: ignore
    blob = Path(in_path).read_bytes()
    data = cy_decode(blob)
    Path(out_path).write_bytes(data)
    return 0


# ----------------------------------------------------------------------------
# Driver
# ----------------------------------------------------------------------------

def _split_into_chunks(data: bytes, chunk_size: int) -> list[bytes]:
    chunks = []
    for offset in range(0, len(data), chunk_size):
        chunks.append(data[offset:offset + chunk_size])
    return chunks


def _run_worker(mode: str, in_path: Path, out_path: Path) -> tuple[int, float, int]:
    """Spawn a subprocess to encode or decode one chunk.

    Returns (exit_code, wall_seconds, peak_rss_kb).
    Uses /usr/bin/time -v on Linux for peak RSS extraction.
    """
    cmd = [
        "/usr/bin/time", "-v",
        sys.executable, __file__, f"--worker={mode}",
        str(in_path), str(out_path),
    ]
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True)
    wall = time.perf_counter() - t0
    # Peak RSS lives in /usr/bin/time -v stderr as "Maximum resident set size (kbytes): N"
    peak_kb = 0
    for line in proc.stderr.splitlines():
        if "Maximum resident set size" in line:
            try:
                peak_kb = int(line.rsplit(":", 1)[1].strip())
            except ValueError:
                pass
            break
    return proc.returncode, wall, peak_kb


def encode_chunked(data: bytes, chunk_size: int, out_path: Path) -> dict:
    n = len(data)
    chunks = _split_into_chunks(data, chunk_size)
    chunk_count = len(chunks)

    WORK.mkdir(parents=True, exist_ok=True)

    header = struct.pack(HEADER_FMT, MAGIC, VERSION, n, chunk_count, chunk_size)

    chunk_meta = []
    blob_total = 0
    peak_max_kb = 0
    enc_total_s = 0.0
    enc_log = []

    # Write header placeholder first; rewind & overwrite chunk records as we go.
    with open(out_path, "wb") as out:
        out.write(header)
        for i, chunk in enumerate(chunks):
            in_path = WORK / f"chunk-{i}.in"
            blob_path = WORK / f"chunk-{i}.blob"
            in_path.write_bytes(chunk)
            rc, wall, peak_kb = _run_worker("encode", in_path, blob_path)
            if rc != 0:
                raise RuntimeError(f"encode worker {i} failed (rc={rc})")
            blob = blob_path.read_bytes()
            out.write(struct.pack(CHUNK_HDR_FMT, len(chunk), len(blob)))
            out.write(blob)
            chunk_meta.append((len(chunk), len(blob), wall, peak_kb))
            blob_total += len(blob)
            peak_max_kb = max(peak_max_kb, peak_kb)
            enc_total_s += wall
            line = (
                f"  chunk {i+1}/{chunk_count}: in={len(chunk):,} → blob={len(blob):,} "
                f"({len(blob)*8/len(chunk):.3f} bpb)  wall={wall:.1f}s  "
                f"peak_rss={peak_kb/1024:.1f} MB"
            )
            enc_log.append(line)
            print(line, flush=True)
            # Best-effort cleanup; keep going if it fails
            try:
                in_path.unlink()
                blob_path.unlink()
            except OSError:
                pass

    return {
        "chunk_count": chunk_count,
        "blob_total": blob_total,
        "peak_max_kb": peak_max_kb,
        "enc_total_s": enc_total_s,
        "chunks": chunk_meta,
    }


def decode_chunked(in_path: Path) -> tuple[bytes, dict]:
    """Decode a TBCK1 file. Returns (data, stats).

    Each chunk decoded in a fresh subprocess to bound memory the same way the
    encoder did. Slow but safe.
    """
    WORK.mkdir(parents=True, exist_ok=True)

    with open(in_path, "rb") as f:
        header = f.read(struct.calcsize(HEADER_FMT))
        magic, version, total_n, chunk_count, chunk_size = struct.unpack(HEADER_FMT, header)
        if magic != MAGIC:
            raise ValueError(f"bad magic: {magic!r}")
        if version != VERSION:
            raise ValueError(f"unsupported version: {version}")

        out_parts: list[bytes] = []
        peak_max_kb = 0
        dec_total_s = 0.0

        for i in range(chunk_count):
            ch_in, ch_blob = struct.unpack(CHUNK_HDR_FMT, f.read(struct.calcsize(CHUNK_HDR_FMT)))
            blob = f.read(ch_blob)
            blob_path = WORK / f"dec-blob-{i}.bin"
            data_path = WORK / f"dec-data-{i}.bin"
            blob_path.write_bytes(blob)
            rc, wall, peak_kb = _run_worker("decode", blob_path, data_path)
            if rc != 0:
                raise RuntimeError(f"decode worker {i} failed (rc={rc})")
            data = data_path.read_bytes()
            if len(data) != ch_in:
                raise RuntimeError(
                    f"chunk {i}: expected {ch_in} bytes, got {len(data)}"
                )
            out_parts.append(data)
            peak_max_kb = max(peak_max_kb, peak_kb)
            dec_total_s += wall
            print(
                f"  chunk {i+1}/{chunk_count}: blob={ch_blob:,} → data={ch_in:,}  "
                f"wall={wall:.1f}s  peak_rss={peak_kb/1024:.1f} MB",
                flush=True,
            )
            try:
                blob_path.unlink()
                data_path.unlink()
            except OSError:
                pass

    data = b"".join(out_parts)
    if len(data) != total_n:
        raise RuntimeError(f"decoded length {len(data)} != total_n {total_n}")
    return data, {
        "chunk_count": chunk_count,
        "peak_max_kb": peak_max_kb,
        "dec_total_s": dec_total_s,
    }


def main(slice_bytes: int, chunk_bytes: int) -> int:
    if not ENWIK.exists():
        print("ERROR: /tmp/enwik8 missing", file=sys.stderr)
        return 1

    raw = ENWIK.read_bytes()[:slice_bytes]
    n = len(raw)
    raw_sha = hashlib.sha256(raw).hexdigest()
    blob_path = WORK / f"enwik8-{n}-chunked.tbck"

    print(f"corpus:      enwik8[:{n:_}]  ({n:_} bytes)")
    print(f"chunk_size:  {chunk_bytes:_} bytes  → {(n + chunk_bytes - 1) // chunk_bytes} chunks")
    print(f"sha256:      {raw_sha}")
    print(f"started:     {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"output:      {blob_path}")
    print("-" * 80)

    # gzip baseline
    t0 = time.perf_counter()
    gz = gzip.compress(raw, compresslevel=9)
    gz_t = time.perf_counter() - t0
    print(f"gzip -9    {len(gz):>12_} bytes  {len(gz)*8/n:>6.3f} bpb  enc={gz_t:.1f}s")

    # chunked encode
    print(f"track-b chunked encode:")
    enc_stats = encode_chunked(raw, chunk_bytes, blob_path)
    blob_size = blob_path.stat().st_size
    print(
        f"  total: {blob_size:_} bytes  "
        f"{blob_size*8/n:.3f} bpb  enc={enc_stats['enc_total_s']:.1f}s  "
        f"peak_rss={enc_stats['peak_max_kb']/1024:.1f} MB"
    )
    print(
        f"  vs gzip: {(len(gz)-blob_size)/len(gz)*100:+.3f}% "
        f"({'AHEAD' if blob_size < len(gz) else 'behind'})"
    )

    # chunked decode + roundtrip
    print(f"track-b chunked decode:")
    back, dec_stats = decode_chunked(blob_path)
    print(
        f"  total dec_time: {dec_stats['dec_total_s']:.1f}s  "
        f"peak_rss={dec_stats['peak_max_kb']/1024:.1f} MB"
    )
    back_sha = hashlib.sha256(back).hexdigest()
    if back_sha != raw_sha:
        print(f"  ROUND-TRIP FAILED: {back_sha} != {raw_sha}")
        return 2
    print(f"  ROUND-TRIP: byte-exact ✓ (sha256 match)")

    print("-" * 80)
    print(
        f"DONE @ {time.strftime('%Y-%m-%d %H:%M:%S')}   "
        f"peak_rss_overall={enc_stats['peak_max_kb']/1024:.1f} MB  "
        f"(was 16162 MB at 50MB single-process — chunking reduces by "
        f"{(1 - enc_stats['peak_max_kb']/(16162*1024))*100:.1f}%)"
    )
    return 0


if __name__ == "__main__":
    # Worker entry path: --worker=encode|decode IN_PATH OUT_PATH
    if len(sys.argv) >= 4 and sys.argv[1].startswith("--worker="):
        mode = sys.argv[1].split("=", 1)[1]
        if mode == "encode":
            sys.exit(_worker_encode(sys.argv[2], sys.argv[3]))
        elif mode == "decode":
            sys.exit(_worker_decode(sys.argv[2], sys.argv[3]))
        else:
            print(f"unknown worker mode: {mode}", file=sys.stderr)
            sys.exit(1)

    slice_n = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000_000
    chunk_n = int(sys.argv[2]) if len(sys.argv) > 2 else 25_000_000
    sys.exit(main(slice_n, chunk_n))
