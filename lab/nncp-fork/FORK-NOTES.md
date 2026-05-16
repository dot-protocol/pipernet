# NNCP fork — Phase 2 target

**Upstream:** https://bellard.org/nncp/ (Fabrice Bellard, MIT licence)
**Imported version:** 2024-06-05
**Date imported:** 2026-05-16

## Why we forked

Track-B (Python bit-mixer, PAQ-lineage) plateaued at ~31 MB on enwik8.
The 2024 NNCP scoreboard on enwik8 is ~16 MB; the current Hutter Prize record
(STARLIT) is ~14.92 MB. To cross from Phase 1 (beat gzip, done) into Phase 2
(approach the record), we need a neural compressor. NNCP is the simplest
modern neural compressor in the lineage that still runs on CPU.

## What's inside

- `nncp.c` (3,906 LOC) — main compressor, profile selection, training loop
- `preprocess.c` (1,401 LOC) — text preprocessor + tokenizer
- `cp_utils.c` (754 LOC) — coding helpers
- `arith.c` (310 LOC) — range coder (`put_bit(state, prob0, bit)` interface
  — identical in shape to our bit-mixer harness)
- `libnc.h` (638 LOC) — tensor API surface for the fork
- `libnc.so` / `libnc_cuda.so` — Bellard's tensor library, binary-only
  (we cannot modify; we work above the API)

## Improvement vectors visible from a read

1. `rot_pos=0` in the enwik8 profile — could enable rotary position embeddings.
2. `attn_len=64,64,64,64,...` uniform 64 across all 20 layers — could vary by layer.
3. `mem_len=32` — could tune for more Transformer-XL context per step.
4. The LSTM `lstm_fast` profile (13.1M params, 4×512) is the only one that
   fits on VPS CPU; the `enwik8` profile (Transformer, ~160M params) needs GPU.

## Baseline runs

- `lstm_fast` on enwik8[:1MB] (VPS, 4 threads): 324,821 bytes / 2.598 BPS,
  6:51 wall. Worse than gzip-9 at 1MB (LSTM cold-starts on small data).
- `lstm_fast` on enwik8 (full 100MB, VPS, 4 threads): dispatched 2026-05-16,
  ETA ~12h.

## Phase 2 plan

1. Establish baseline NNCP `lstm_fast` number on full enwik8 (in flight).
2. Read the training loop (`trf_eval_gradient`, `trf_update`) end-to-end.
3. Identify one architectural change to attempt (likely: enable rot_pos,
   or raise mem_len). Variable attn_len needs LibNC support.
4. Run modified `lstm_fast` on enwik8, compare.
5. Decide GPU rental if and only if CPU LSTM approaches but doesn't cross
   the record (then a full Transformer enwik8 profile run becomes worth it).
