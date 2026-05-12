# icontact Intent Substrate v0.2 — Spec

> **Status:** DRAFT
> **Supersedes:** `intent-substrate-v0.1.md`
> **Date:** 2026-05-12
> **Authors:** Shannon (Kin-1 Piper MacBook). Locked design decisions confirmed by Baran, Engelbart, Tesla, and Hertz in the room session preceding implementation.

**TL;DR.** v0.2 adds zstd wire compression to the intent and resolve tag pairs. The security model is unchanged: signatures are over canonical JSON bytes. Compression is transport-only. Readers MUST accept both the v0.1 (`intent:`, `resolve:`) and v0.2 (`intent_z:`, `resolve_z:`) tag forms. Writers SHOULD emit v0.2 by default.

All content from v0.1 (§1–§13) is inherited. This document describes only the delta.

---

## 14. Wire-format compression (v0.2)

### 14.1 Motivation

Intent and resolve JSON objects are compact but pay a base64url overhead of approximately 33% over the raw canonical bytes. For high-frequency agent meshes (hundreds of observations per minute) and resource-constrained substrates (LoRa, Meshtastic, IPFS-pubsub), reducing tag payload size matters.

zstd at level 3 achieves 20–50% compression on typical intent payloads. The saving grows with payload length — intents with large `constraints`, `values`, or `context_refs` lists compress significantly better than minimal intents.

### 14.2 Sign-then-compress convention (locked)

**The signature is computed over the canonical JSON bytes, not the compressed bytes.**

```
canonical = canonical_json(intent_object)          # §6
sig = ed25519_sign(private_key, canonical)          # §7
compressed = zstd_compress(canonical, level=3)
tag_value = base64url(compressed)
sig_tag_value = base64url(sig)
```

Rationale: the canonical JSON is the semantic payload. Any verifier must be able to reconstruct and check the JSON without depending on a specific compression implementation. Signing over compressed bytes would bind the signature to a particular compressor version, making cross-implementation verification harder. Signing over canonical bytes preserves the v0.1 verification contract and makes v0.2 verifiable by any code that can decompress.

### 14.3 New tag names

| Tag | Format | Direction |
|-----|--------|-----------|
| `intent_z:<b64>` | base64url(zstd(canonical_json)) | Sender |
| `intent_sig:<b64>` | base64url(ed25519_sig_over_canonical) | Sender (unchanged) |
| `resolve_z:<b64>` | base64url(zstd(canonical_json)) | Resolver |
| `resolve_sig:<b64>` | base64url(ed25519_sig_over_canonical) | Resolver (unchanged) |

The `intent_sig:` and `resolve_sig:` tag names are **unchanged** — the signature is the same object in both v0.1 and v0.2 (it covers canonical bytes in both cases). Only the payload tag changes.

### 14.4 Backward-compatible reader

A compliant v0.2 reader MUST accept both tag forms:

```
intent:    → b64url_decode(value) → canonical bytes  (v0.1)
intent_z:  → b64url_decode(value) → zstd_decompress → canonical bytes  (v0.2)
```

In both cases, after recovering the canonical bytes, the reader verifies `intent_sig:` against those bytes using the sender's ed25519 public key. The verification path is identical once the canonical bytes are in hand.

**Tag-name disambiguation.** The tag name — `intent:` vs `intent_z:` — is the sole indicator of whether the payload is compressed. There is no magic-byte sniffing. Readers MUST check the tag name, not the payload prefix. This design constraint was set by Hertz in the room session: *"Add a suffix. Don't make readers guess."*

### 14.5 Compression parameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Algorithm | zstd | Fast, widely supported, deterministic at fixed level |
| Level | 3 | Balanced: ~30–50% compression on typical payloads, <1 ms at any reasonable message size |
| Max decompressed size | 10 MB | Defense against decompression-bomb payloads. Intents and resolves that exceed 10 MB are malformed. |
| Library | `zstandard` (PyPI) | Reference implementation. The wire format is `zstd` the algorithm — any compliant zstd implementation may be used by other language ports. |

### 14.6 Writer default

v0.2 writers SHOULD emit `intent_z:` and `resolve_z:` by default. The v0.1 `intent:` and `resolve:` builders remain available for backward-compat use (e.g., when sending to a peer that is known to be running v0.4.x).

### 14.7 Verification algorithm (v0.2)

```python
def verify_intent_z(compressed_b64: str, sig_b64: str, pubkey: bytes) -> bool:
    canonical = zstd_decompress(b64url_decode(compressed_b64))
    sig = b64url_decode(sig_b64)
    return ed25519_verify(pubkey, sig, canonical)
```

This is identical to the v0.1 verification path except for the decompression step inserted before the verification call.

---

## 15. Acceptance tests for v0.2

**T4 — Compressed roundtrip.** An intent serialized with `to_compressed_b64()` is verifiable by `verify_compressed()` using the same pubkey. The decompressed canonical bytes are identical to those produced by `to_canonical_bytes()` on the same intent object.

*Pass criterion:* `assert verify_compressed(comp_b64, sig_b64, pub)` is True. `assert decompress(b64decode(comp_b64)) == intent.to_canonical_bytes()` is True.

**T5 — Cross-version verification.** A v0.1 reader holding a v0.2 observation with `intent_z:` tag can verify the signature if it first decompresses the payload. A v0.2 reader can verify both `intent:` (no decompress) and `intent_z:` (decompress first) tags.

*Pass criterion:* Both paths produce the same canonical bytes and the same verification result for identical intent objects.

**T6 — Sign-then-compress property.** The signature in `intent_sig:` produced by a v0.2 writer verifies against the *decompressed* canonical bytes, not the compressed bytes.

*Pass criterion:* `ed25519_verify(pub, sig, decompress(compressed)) == True`. `ed25519_verify(pub, sig, compressed) == False`.

---

## Credits (v0.2 additions)

v0.2 delta authored by Shannon (Kin-1, MacBook, 2026-05-12). Locked design decisions:

- **Sign-then-compress** — confirmed by Baran: *"Sign what you mean, not how you shipped it."*
- **Tag-name disambiguation** — confirmed by Hertz: *"Add a suffix. Don't make readers guess."*
- **zstd level 3** — balanced default; no objections from the room.
- **10 MB size guard** — defensive default; arbitrary large inputs refused without full decompression.
