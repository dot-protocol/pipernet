# icontact Blob Substrate v0.1 — Spec

> **Status:** DRAFT
> **Date:** 2026-05-12
> **Authors:** Shannon (Kin-1 Piper MacBook). Built parallel to intent substrate, completing Baran's fifth substrate (content) of the five kill-survivable layers.
> **Companion specs:** `intent-substrate-v0.2.md`, `05-identity.md`, `06-compression.md`.

**TL;DR.** Content-addressed retrieval over the icontact mesh. A blob is bytes plus a mime type. Its address is the BLAKE3 hash of the bytes (the CID). A blob lives in Oracle as a signed **manifest** observation plus one or more **chunk** observations. Tag-routing makes retrieval indistinguishable from any other dotpost query. Sign-then-compress reuses the intent substrate's wire convention. No partial reconstructions unless the manifest expressly allows them. This substrate is what carries files, audio, video, and gaussian splats across the mesh.

---

## 1. Why a separate substrate

The four substrates already in the icontact stack each do one thing:

| Substrate | Role |
|---|---|
| **Identity** (`05-identity.md`) | Who said what (ed25519 keys, signed observations). |
| **Routing** (dotpost tags) | Where it goes (`to:<handle>`, `to:all`, `to:group:<name>`). |
| **Capability/intent** (`intent-substrate-v0.2.md`) | What an agent commits to / refuses (signed declarations). |
| **Value** (TODO) | Economic accounting (out of scope here). |

What is missing is **content**: a way to put arbitrary bytes on the mesh, addressed by hash, retrievable by anyone, verifiable without trust. Text observations already cover small payloads, but they are not designed for files. Embedding a 50 MB video in a single observation:

- breaks Oracle's per-observation size budget,
- inflates indexed text storage with binary noise,
- prevents range fetch, retry, or partial caching,
- makes deduplication impossible (the same video re-uploaded by a second sender is stored twice).

The blob substrate solves these by **chunking**, **content-addressing**, and **manifest-as-observation**.

This is the layer that lets a human send a song to another human through the mesh, a researcher post a dataset alongside an intent, or an agent attach a screenshot to a resolve. It is also the substrate over which dotjpg / microdot encodings (spec 10) can travel.

---

## 2. Locked design decisions

These were settled before implementation; any future revision must explicitly supersede them.

1. **BLAKE3 for CIDs.** Cryptographic hash, 256-bit output, faster than SHA-256, tree-mode native (relevant for chunk verification). CID format: `b3:<32-byte-hex>` (66 chars total) or `b3z:<base32>` (compact form, 52 chars). Canonical wire form is the hex variant.
2. **Chunk size: 256 KiB.** Fits well under any reasonable observation budget, gives a 50 MB file 200 chunks, gives a 5 GB file 20 000 chunks. Tunable per manifest (see §5.3) but **MUST** default to 262 144 bytes.
3. **Manifest is a signed observation.** Same signing path as intent: canonical JSON → ed25519 sig over canonical bytes → zstd compress the JSON → base64url. Sign-then-compress, locked (see intent v0.2 §14.2).
4. **Chunks are unsigned observations.** Integrity is enforced by the manifest's per-chunk BLAKE3 hashes; the chunk observation itself does not carry a signature. A chunk whose bytes do not hash to the manifest's claim is treated as if it does not exist (gate-2 verification, see §6.2).
5. **No partial reconstruction by default.** A reader MUST refuse to reconstruct a blob if any chunk is missing or fails verification — the substrate returns `null`, not "best effort." Manifests MAY set `partial_ok: true` for streaming/best-effort use cases (audio preview, progressive image), but the default is refusal. This is Tesla's law as applied to bytes: never approximate without express permission.
6. **Mime type is mandatory.** Every manifest declares its mime. A blob without a declared content type is not a blob, it is a hash with no semantics. Mime strings follow IANA registry conventions; unknown types use `application/octet-stream`.
7. **One manifest per CID.** If two senders post the same bytes, they produce the **same** CID and the substrate stores only one canonical manifest (the first one ingested). Subsequent senders create a `reseed:<cid>` observation that points at the existing manifest. The chunks are deduplicated structurally.
8. **No assumed transport.** This spec describes the **on-Oracle wire format**. A blob carried over LoRa, Meshtastic, or a peer-to-peer file transfer uses the same manifest schema but may chunk differently or sign chunks individually. The base manifest format MUST round-trip across transports.

---

## 3. Tag shape

Blob-substrate observations carry these tags. Existing dotpost tags (`from:<sender>`, `to:<handle>`, `to:all`, `to:group:<name>`) compose normally.

| Tag | Meaning | Direction |
|---|---|---|
| `blob` | This observation is part of the blob substrate. Always present. | Both |
| `manifest:<cid>` | This observation is the manifest for `<cid>`. | Manifest only |
| `chunk:<cid>:<n>` | This observation is chunk `n` (0-indexed) of `<cid>`. | Chunk only |
| `mime:<type>` | The mime type of the full blob. Always on the manifest. | Manifest |
| `size:<bytes>` | The decompressed total byte length. Always on the manifest. | Manifest |
| `nchunks:<count>` | Number of chunks. Always on the manifest. | Manifest |
| `manifest_z:<b64>` | base64url(zstd(canonical_json_of_manifest)). Always on the manifest. | Manifest |
| `manifest_sig:<b64>` | base64url(ed25519_sig_over_canonical_manifest). Always on the manifest. | Manifest |
| `chunk_data:<b64>` | base64url(raw chunk bytes). Always on a chunk. | Chunk |
| `reseed:<cid>` | This observation announces a re-post of an existing CID by a new sender. | Reseed |

Lookup by CID is a single Oracle query:

```
oracle_audit(tag_filter="manifest:<cid>", limit=1)
```

Chunk fetch is parallel by index:

```
oracle_audit(tag_filter="chunk:<cid>:<n>", limit=1)   # for each n in 0..nchunks-1
```

Reseed lookup ("who else has posted this?"):

```
oracle_audit(tag_filter="reseed:<cid>", limit=100)
```

All routing tags (`to:<handle>`, etc.) apply normally — a blob can be DM'd, broadcast, or group-routed. The manifest carries the routing; the chunks do not need it (they are fetched by CID once the manifest is known).

---

## 4. CID derivation

Given raw bytes `B` of length `L`:

```
cid_bytes = BLAKE3(B)                    # 32 bytes
cid       = "b3:" + hex(cid_bytes)       # 66 chars total
```

Implementations MUST use the standard BLAKE3 keyed-hash-disabled mode. The hash is over the **uncompressed** bytes — the bytes the recipient will ultimately receive, not the compressed wire payload. This makes the CID stable across compression levels, and lets a chunk be re-compressed or transported uncompressed without changing the manifest.

A manifest's `cid` field MUST equal the BLAKE3 hash of the concatenation of all chunk plaintexts in order. Readers verify this at gate-2 reconstruction (see §6).

---

## 5. Manifest schema

A manifest is a JSON object with the following canonical fields. Optional fields are marked.

```json
{
  "v": 1,
  "cid": "b3:f3a1...",
  "mime": "image/png",
  "size": 1048576,
  "nchunks": 4,
  "chunk_size": 262144,
  "chunks": [
    {"i": 0, "h": "b3:aa11...", "n": 262144},
    {"i": 1, "h": "b3:bb22...", "n": 262144},
    {"i": 2, "h": "b3:cc33...", "n": 262144},
    {"i": 3, "h": "b3:dd44...", "n": 262144}
  ],
  "created_at": "2026-05-12T15:00:00Z",
  "sender": "shannon",
  "sender_pubkey": "ed25519:base64...",
  "filename": "diagram.png",
  "partial_ok": false,
  "refuse_substitution": true,
  "metadata": {}
}
```

### 5.1 Required fields

| Field | Type | Notes |
|---|---|---|
| `v` | integer | Schema version. MUST be 1 for this spec. |
| `cid` | string | BLAKE3 over concatenated plaintext chunks. |
| `mime` | string | IANA mime type. Defaults `application/octet-stream` if unknown. |
| `size` | integer | Total byte length of the reconstructed blob. |
| `nchunks` | integer | Number of chunks. Equal to `len(chunks)`. |
| `chunk_size` | integer | Chunk size in bytes. Defaults to 262144. Last chunk may be smaller. |
| `chunks` | array | Per-chunk descriptors. See §5.2. |
| `created_at` | string | ISO-8601 UTC timestamp. |
| `sender` | string | Handle that produced the manifest. |
| `sender_pubkey` | string | `ed25519:<base64-32-bytes>`. Same format as intent spec §7. |

### 5.2 Chunk descriptors

Each entry in `chunks` is `{"i": <int>, "h": "b3:<hex>", "n": <int>}`:

- `i` — chunk index, 0-based. MUST be strictly increasing.
- `h` — BLAKE3 of this chunk's plaintext bytes.
- `n` — byte length of this chunk's plaintext.

The sum of all `n` MUST equal the manifest's `size`. The hash of the concatenation in order MUST equal the manifest's `cid`.

### 5.3 Optional fields

| Field | Type | Default | Notes |
|---|---|---|---|
| `filename` | string | `null` | Display name. No semantic meaning to the substrate. |
| `partial_ok` | bool | `false` | If true, readers MAY surface partial reconstructions when chunks are missing. Default is refusal. |
| `refuse_substitution` | bool | `true` | Tesla's law: never substitute a "similar" blob. Locked default true. Setting to false is a deliberate looseness for caches or proxies; not recommended. |
| `metadata` | object | `{}` | Free-form per-application metadata (camera EXIF, video duration, splat density, etc.). Not signed separately — it is part of the canonical JSON and so is covered by the manifest signature. |

### 5.4 Canonicalization

The manifest is canonicalized using the same RFC 8785-subset routine as intent (see `intent-substrate-v0.1.md` §6): sorted keys at every level, UTF-8 strings, no extraneous whitespace, JSON-RFC numeric form. The canonical bytes are the bytes that get signed.

### 5.5 Signing

```
canonical   = canonical_json(manifest_without_signature)
sig         = ed25519_sign(sender_private_key, canonical)
manifest_z  = base64url(zstd(canonical, level=3))
manifest_sig = base64url(sig)
```

The signature is over the canonical JSON of the manifest **without** the signature itself — the manifest carries no `sig` field inside the JSON object. The signature lives only in the `manifest_sig:` tag. This keeps canonicalization and signing decoupled and matches the intent substrate's pattern.

---

## 6. Reader contract

A compliant reader takes a CID and a public-key resolver, and returns either:

- the reconstructed bytes plus the verified manifest, or
- `null` (with a structured reason).

### 6.1 Gate 1 — manifest fetch & verify

```
manifest_obs = oracle_audit(tag_filter="manifest:<cid>", limit=1)
if not manifest_obs: return null, "manifest-missing"

manifest_z = extract_tag("manifest_z:", manifest_obs.tags)
sig_b64    = extract_tag("manifest_sig:", manifest_obs.tags)
canonical  = zstd_decompress(base64url_decode(manifest_z))
manifest   = json.loads(canonical)
pubkey     = resolve_pubkey(manifest["sender"])     # mesh registry
if not ed25519_verify(pubkey, base64url_decode(sig_b64), canonical):
    return null, "manifest-signature-invalid"
if manifest["cid"] != cid:
    return null, "manifest-cid-mismatch"
```

### 6.2 Gate 2 — chunk fetch & verify

```
plaintexts = [None] * manifest["nchunks"]
for i in 0..manifest["nchunks"]-1:
    chunk_obs = oracle_audit(tag_filter="chunk:<cid>:<i>", limit=1)
    if not chunk_obs:
        if manifest["partial_ok"]: plaintexts[i] = None; continue
        return null, f"chunk-missing:{i}"
    chunk_data = base64url_decode(extract_tag("chunk_data:", chunk_obs.tags))
    if blake3(chunk_data) != manifest["chunks"][i]["h"]:
        return null, f"chunk-hash-mismatch:{i}"
    if len(chunk_data) != manifest["chunks"][i]["n"]:
        return null, f"chunk-length-mismatch:{i}"
    plaintexts[i] = chunk_data
```

### 6.3 Gate 3 — assembly & whole-CID verification

```
if None in plaintexts and not manifest["partial_ok"]:
    return null, "incomplete-and-strict"
full = b"".join(p for p in plaintexts if p is not None)
if not manifest["partial_ok"] and blake3(full) != cid_bytes:
    return null, "cid-mismatch-after-assembly"
return full, manifest
```

Three gates: manifest validity, per-chunk validity, whole-CID validity. A blob that passes all three is the bytes the sender intended.

---

## 7. Writer contract

```
def post_blob(blob_bytes, mime, sender_keypair, to=None, group=None, filename=None, metadata=None):
    cid_bytes = blake3(blob_bytes)
    cid       = "b3:" + cid_bytes.hex()

    # Skip if manifest already exists
    if oracle_audit(tag_filter=f"manifest:{cid}", limit=1):
        post_reseed(cid, sender_keypair.handle, to=to, group=group)
        return cid

    chunks = split(blob_bytes, chunk_size=262144)
    manifest = build_manifest(cid, mime, blob_bytes, chunks, sender_keypair, filename, metadata)

    # Post manifest with routing tags
    canonical = canonical_json(manifest)
    sig       = ed25519_sign(sender_keypair.private, canonical)
    tags = [
        "blob",
        f"manifest:{cid}",
        f"mime:{mime}",
        f"size:{len(blob_bytes)}",
        f"nchunks:{len(chunks)}",
        f"manifest_z:{base64url(zstd(canonical))}",
        f"manifest_sig:{base64url(sig)}",
        f"from:{sender_keypair.handle}",
    ]
    if to:    tags.append(f"to:{to}")
    if group: tags.append(f"to:group:{group}")
    oracle_ingest(channel="raw", tags=tags, statement=f"[blob] {mime} {len(blob_bytes)}B {cid[:12]}")

    # Post chunks
    for i, chunk in enumerate(chunks):
        oracle_ingest(
            channel="raw",
            tags=["blob", f"chunk:{cid}:{i}", f"chunk_data:{base64url(chunk)}"],
            statement=f"[chunk] {cid[:12]} {i}/{len(chunks)}",
        )

    return cid
```

### 7.1 Sender's responsibilities

- Compute CID **before** uploading. Skip the manifest write if a manifest already exists (post a `reseed:` instead).
- Refuse to post a blob whose mime type contains characters outside the IANA range.
- Refuse to post a blob larger than `MAX_BLOB_BYTES` (default 100 MiB for v0.1; transports may negotiate higher).
- Post the manifest **before** any chunks. Readers MAY abort early if the manifest is malformed; chunks orphaned by a missing manifest are dead storage.
- A failed chunk write is fatal: the manifest is then inconsistent and the sender SHOULD post a `void:<cid>` retraction (see §9) or retry.

### 7.2 Routing semantics

The manifest carries `to:<handle>` / `to:all` / `to:group:<name>` tags. The chunks do not. This means:

- The recipient is notified about the **availability** of the blob (the manifest).
- Anyone with the CID can fetch the chunks — chunks are public by their nature on Oracle.
- For private blobs (TODO, see §10): encrypt the bytes **before** chunking. The substrate is content-addressed, not access-controlled.

---

## 8. Reseed observations

When a sender wants to declare "I also have this blob, you can ask me for it offline" without re-uploading, they post a reseed:

```
oracle_ingest(
  channel="raw",
  tags=["blob", f"reseed:{cid}", f"from:{handle}", "blob_reseed"],
  statement=f"[reseed] {cid[:12]} held by {handle}",
)
```

Reseeds are unsigned and informational. They support out-of-band transports (LoRa, USB stick, direct WebRTC) where the receiver can verify the blob via the canonical manifest even though Oracle was not the carrier.

A reader fetching a blob and finding chunks missing on Oracle MAY query reseeds and attempt out-of-band retrieval; the manifest's hashes still validate whatever bytes arrive.

---

## 9. Voids and retractions

A sender who posts a manifest and later wants to retract it (corrupted bytes, leaked key, accidental upload) posts:

```
oracle_ingest(
  channel="raw",
  tags=["blob", f"void:{cid}", f"from:{handle}", "blob_void"],
  statement=f"[void] {cid[:12]} retracted by {handle}",
)
```

A void observation does not delete the manifest or chunks from Oracle (the substrate is append-only). It is an advisory signal: readers SHOULD NOT serve this blob as live content and SHOULD warn callers. The substrate's record of "this CID once existed and was retracted" is itself part of the audit history.

Voids are unsigned for v0.1. A future signed-void variant is reserved for spec v0.2.

---

## 10. Out of scope for v0.1

These are explicitly deferred:

- **End-to-end encryption.** A blob is public to anyone who can read its manifest. Private blobs require encryption above this substrate (sender encrypts bytes with recipient's pubkey, posts ciphertext with `mime: application/x-encrypted-blob`).
- **Streaming reconstruction.** v0.1 reconstructs sequentially. Real-time streaming (live audio/video) is a different shape; this substrate is for at-rest content.
- **Garbage collection.** Oracle is append-only; chunks orphaned by voided manifests stay on disk. A future janitor pass MAY reclaim space.
- **Erasure coding.** Reed-Solomon or fountain codes for high-redundancy storage. Future work.
- **Provable retrievability.** A sender claiming `reseed:` without actually being reachable is a soft attack. v0.1 has no challenge-response mechanism; this can be added later as a separate substrate (signed availability proofs).
- **Cross-shard CIDs.** When Oracle scales beyond a single Neo4j, manifests will need shard hints. Out of scope.

---

## 11. Failure modes (catalog)

| Code | Cause | Reader behaviour |
|---|---|---|
| `manifest-missing` | No observation with `manifest:<cid>`. | Return `null`. |
| `manifest-signature-invalid` | Signature does not verify. | Return `null`, log. |
| `manifest-cid-mismatch` | Manifest claims a CID that does not match its own tag. | Return `null`, log. |
| `chunk-missing:N` | No observation with `chunk:<cid>:N`. | Return `null` unless `partial_ok`. |
| `chunk-hash-mismatch:N` | Chunk N's bytes hash to something other than the manifest's claim. | Return `null`, log. |
| `chunk-length-mismatch:N` | Chunk N's byte length differs from manifest's claim. | Return `null`, log. |
| `incomplete-and-strict` | Chunks missing and `partial_ok=false`. | Return `null`. |
| `cid-mismatch-after-assembly` | Concatenation does not hash to the claimed CID. | Return `null`, log loudly — this is a manifest forgery attempt. |
| `void-observed` | A `void:<cid>` exists. | Return `null` with `voided=true`. |

Loud-log codes (`manifest-signature-invalid`, `chunk-hash-mismatch`, `cid-mismatch-after-assembly`) indicate adversarial activity and SHOULD be surfaced to operators.

---

## 12. Worked example — a 600 KiB PNG

A sender on handle `shannon` posts `diagram.png` (614 400 bytes, mime `image/png`):

1. `cid_bytes = BLAKE3(bytes)`, `cid = "b3:7f3e..."` (full 64 hex chars).
2. `chunks = [bytes[0:262144], bytes[262144:524288], bytes[524288:614400]]` (sizes 262144, 262144, 90112).
3. `chunk_hashes = [BLAKE3(chunks[0]), BLAKE3(chunks[1]), BLAKE3(chunks[2])]`.
4. Build manifest JSON with `cid`, `mime: "image/png"`, `size: 614400`, `nchunks: 3`, `chunk_size: 262144`, `chunks: [{i:0, h:..., n:262144}, {i:1, h:..., n:262144}, {i:2, h:..., n:90112}]`, sender, sender_pubkey, created_at, `partial_ok: false`, `refuse_substitution: true`, `filename: "diagram.png"`.
5. Canonicalize. Sign. zstd-compress canonical bytes.
6. Post manifest observation with tags: `[blob, manifest:b3:7f3e..., mime:image/png, size:614400, nchunks:3, manifest_z:..., manifest_sig:..., from:shannon, to:jared]`. Statement: `[blob] image/png 614400B b3:7f3e...`.
7. Post three chunk observations with tags `[blob, chunk:b3:7f3e...:0, chunk_data:...]`, etc.
8. Recipient `jared` sees `dotpost to:jared` traffic, notices the `blob` tag, follows the manifest, fetches 3 chunks in parallel, verifies, reconstructs, opens the PNG.

Wall-clock cost at typical Oracle ingest latency (~150 ms per write): 4 ingests sequentially is ~600 ms. Parallelized: ~200 ms total. Network cost: 614 400 bytes plaintext + ~33% base64url overhead per chunk + small manifest.

---

## 13. Test vectors (v0.1)

The reference implementation MUST pass these vectors:

| Input | Expected `cid` |
|---|---|
| `b""` (empty) | `b3:af1349b9f5f9a1a6a0404dea36dcc9499bcb25c9adc112b7cc9a93cae41f3262` |
| `b"hello"` | `b3:ea8f163db38682925e4491c5e58d4bb3506ef8c14eb78a86e908c5624a67200f` |
| `b"a" * 262145` (one chunk + 1 byte, splits into 2 chunks) | `b3:` of concat-hash; sizes `[262144, 1]` |
| `b"a" * (10*1024*1024)` (10 MiB) | exactly 40 chunks of 262144 bytes; the cid is the BLAKE3 of the full 10 MiB |

Boundary cases the reference suite MUST cover:

- Exactly chunk-size blob (1 chunk, no remainder).
- 1-byte blob (1 chunk of size 1).
- Empty blob (0 chunks, manifest still required; CID is the BLAKE3 of empty input).
- Chunk-size + 1 byte (2 chunks, last of size 1).
- Mime with parameters (`text/plain; charset=utf-8`).
- Filename with unicode characters.
- Manifest with `partial_ok: true` and one chunk missing — reader returns the available bytes with a non-null but flagged result.

---

## 14. Relationship to other specs

- **`05-identity.md`** — supplies the ed25519 keys and `<handle>:<pubkey>` registry the manifest signing relies on.
- **`06-compression.md`** — zstd at level 3, identical to intent v0.2's wire compression.
- **`intent-substrate-v0.2.md`** — same sign-then-compress, same canonical JSON convention, same Tesla refusal default. Intent and blob are companion substrates: an intent can reference a blob CID in its `context_refs` (e.g. "I intend to ship the document at `b3:7f3e...`"), and a resolve can attach a CID as evidence ("I delivered, here is the artifact at `b3:abc...`").
- **`10-microdot.md` / `10-dotjpg.md`** — content-encoding specs. A microdot PNG is *itself* a blob; its CID can be the address used to reference it. Encoding and substrate are independent layers.
- **`14-rooms.md`** — rooms are tag-namespaces. A blob posted with `to:group:<room>` becomes visible to that room's members. Files in a room are blob substrate observations.

---

## 15. Open questions for the next room

These are explicitly **not** resolved by v0.1 and will be revisited:

1. **Per-recipient encryption envelope.** Should encryption be a layer above the substrate (sender chooses) or a default behaviour for `to:<single-handle>` (substrate-level)? Lean: above-substrate, but worth a room.
2. **Reseed economics.** When the value substrate (Baran's 5th) lands, reseeds become a candidate for micropayment (you seed my blob, I pay a sliver of $PIPER). Out of scope for v0.1 but the tag shape is forward-compatible.
3. **Chunk-size discovery for low-bandwidth transports.** LoRa and Meshtastic have packet budgets below 256 KiB. Two options: (a) chunk small enough by default (16 KiB, 100x more observations); (b) accept that some transports re-chunk and the on-Oracle canonical form is one shape while the on-radio form is another, bound by a transport-specific manifest. Lean: (b), but it needs a spec of its own.
4. **Mime-driven validators.** Should the substrate run mime-aware validators (PNG header check, MP3 frame sync) before accepting an upload? Adds complexity; default for v0.1 is no — the substrate is mime-agnostic. Applications layer their own checks.
5. **Manifest-of-manifests.** Datasets, gaussian-splat scenes, multi-file archives. Two paths: (a) a manifest can be of mime `application/x-icontact-bundle` and its bytes are themselves a JSON listing child CIDs; (b) introduce a new `bundle` substrate. Lean: (a) — bundles are blobs whose bytes describe other blobs.

---

## 16. Version semantics

Specs are versioned. A v0.1 reader MUST refuse manifests with `v > 1`. A v0.2 reader MUST accept v0.1 manifests but MAY emit v0.2-only fields when writing. Forward-compatible field additions are allowed; semantic changes require a major bump.

---

**Locked.** Implementation can begin against this document. Subsequent revisions land as `blob-substrate-v0.2.md` etc.; this file is canon for v0.1.
