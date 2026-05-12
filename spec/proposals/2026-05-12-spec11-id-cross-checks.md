# Proposal — spec/11 §8 cross-checks (SPHINCS+, X25519, BLAKE3)

Date: 2026-05-12
Author: Shannon (Kin-1 Piper MacBook surface, taking Rocky's queue)
Status: DRAFT for Council review. Not yet merged into spec/11-packet.md §8.

## Context

spec/14-rooms.md line 7 declares:

> Depends on: spec/11-packet.md §8 (identity layer — Ed25519, X25519, SPHINCS+)

But spec/11 §8 today only covers Ed25519 (8.1) and onion-encrypted privacy
tiers (8.2). SPHINCS+ is unmentioned. X25519 is unmentioned. The hash
primitive used by `PACKET_ID` is SHA-256 (per §5), while spec/14 §6
specifies BLAKE3 for `message_id`. These three cross-checks were called
out in Jared's 2026-05-11 queue (msg-c8ffd78e item Q1) and have been
pending Rocky since.

This proposal adds three sub-sections — 8.3, 8.4, 8.5 — answering each.
It is intentionally conservative: it commits to the cheapest version
of each primitive that closes the gap, leaving more aggressive
hardening for later spec revisions.

---

## 8.3 — Post-quantum signature hybrid (SPHINCS+ adjunct)

### Why

Ed25519 is broken by a sufficiently large quantum computer (Shor's
algorithm on the discrete-log problem). The packet network is
expected to outlive that horizon. We need a transition path that
does not break existing identities the day after a quantum break.

### Proposal

The packet supports a HYBRID signature scheme. A packet may carry:

- An Ed25519 signature (`SIG_CLASSICAL`, 64 bytes, required in v1)
- An optional SPHINCS+ signature (`SIG_PQ`, ~7,856 bytes for
  SPHINCS+-SHAKE-128s, optional in v1, MANDATORY by v2)

Both signatures cover the same canonical bytes (the SHA-256
PACKET_ID per §5). A relay considers a packet valid if EITHER
signature verifies in v1. In v2, BOTH must verify.

### Why SPHINCS+-SHAKE-128s

- **Stateless.** No per-key counter to track; key compromise on
  signing recovery is bounded the same way as Ed25519.
- **Hash-based.** Security reduces to the underlying hash, not
  to a lattice or code-based assumption.
- **NIST standardized** (FIPS 205, 2024). Already in OpenSSL 3.5.
- **Cost: signature size.** 7,856 bytes per signature. Acceptable
  for Tier 0 + Tier 1 packets which already carry ≥4 KB of payload;
  prohibitive for the compressed Tier 2 sub-30-byte packet form.
  Therefore SPHINCS+ is optional below a configurable threshold
  (default: include SPHINCS+ only if payload ≥ 1024 bytes).

### Cross-check resolution

`AXXIS_PUBKEY` (§8.1) gains a sibling field `AXXIS_PQ_PUBKEY` (32
bytes for SPHINCS+ root). Identities published before this field
existed are treated as `SIG_PQ_OPTIONAL` until they re-announce
with a PQ pubkey. The behavioral signature mechanism (§8.1,
"Key rotation") covers the transition: announcing a new PQ pubkey
under an existing Ed25519 identity is one valid form of rotation.

---

## 8.4 — X25519 ECDH for Tier 1+ key agreement

### Why

Tier 0 (signed + TLS) needs no key agreement — the TLS handshake
provides it. Tier 1 (opt-in E2E) and Tier 2 (onion) DO need a way
for two pubkeys to derive a shared symmetric key without a third
party seeing it. spec/14 already assumes X25519 is available.

### Proposal

Every AXXIS ID gains a parallel X25519 keypair, derived
deterministically from the Ed25519 private key via the BIP-32-style
scheme: `x25519_priv = SHA-512(ed25519_priv || "X25519-derivation-v1")[:32]`,
clamped per RFC 7748. The X25519 pubkey is published in the same
handshake packet as the Ed25519 pubkey.

E2E layer (Tier 1):
- Sender derives `K_shared = X25519(sender_priv, receiver_pub)`
- HKDF over `K_shared` with per-message salt → per-message symmetric key
- Payload encrypted with ChaCha20-Poly1305 (already in scope for
  TLS) under the derived key
- The Ed25519 signature still covers the canonical bytes for
  authenticity; X25519 only provides confidentiality

This separates "who signed" (Ed25519) from "who can read" (X25519),
matching the Noise Protocol Framework split. No new primitives —
both algorithms are in TLS 1.3 already.

### Cross-check resolution

§8.1 "Every participant has an AXXIS ID" remains true. An AXXIS ID
is now formally a TUPLE of (Ed25519 pubkey, X25519 pubkey, optional
SPHINCS+ pubkey). The 32-byte short form (Ed25519 pubkey only) is
preserved for §5 bootstrap-header compatibility; the long form
(96 bytes — 32+32+32 — or 128 if SPHINCS+ root included) is used in
discovery and channel-join messages where size matters less.

---

## 8.5 — Hash primitive: single answer (BLAKE3)

### Why

spec/11 uses SHA-256 for `PACKET_ID`, `SCHEMA_HASH`, `RUNTIME_HASH`,
`POLICY_HASH`, `STATE_HASH` (§5). spec/14 uses BLAKE3 for
`message_id` (§6). Two specs, two hash primitives — drift waiting
to become a bug.

### Proposal

**Migrate spec/11 from SHA-256 to BLAKE3, NOT the other way.**

Why BLAKE3, not SHA-256:

- **Speed.** BLAKE3 hashes ~6 GB/s on a single modern core via SIMD;
  SHA-256 hashes ~600 MB/s on the same core. The packet network
  hashes every payload twice (PACKET_ID + body integrity). At
  10⁵ packets/sec a node would burn 17% of one core on SHA-256 vs
  1.7% on BLAKE3.
- **Tree-friendly.** BLAKE3 is a Merkle tree natively. The packet
  is already fractal (§9). Substrate matches substance.
- **Output flexibility.** BLAKE3 emits any output length up to
  2⁶⁴ bytes from a single hash call. spec/11's 32-byte PACKET_ID
  and spec/06's compression-profile hash can both be derived from
  one BLAKE3 call instead of two hash invocations.
- **Identical 32-byte truncation.** A 32-byte BLAKE3 output occupies
  the same wire slot as a SHA-256 output. No bootstrap-header field
  resize.

### Migration

`PACKET_ID` v1 packets are SHA-256 (existing). v2 packets are
BLAKE3 with a 1-bit version flag in the bootstrap header
(§5.2 reserves a `HASH_VERSION` bit). Relays accept both during
the transition window (default 90 days from v2 announcement).
After the window, v1 packets are flagged stale and rebroadcast
under v2 hashing by any willing relay.

### Cross-check resolution

After migration, spec/11 §5 and spec/14 §6 both compute hashes
using BLAKE3. `PACKET_ID = BLAKE3(canonical_bytes)[:32]`;
`message_id = BLAKE3(canonical_bytes)[:32]`. One primitive, two
specs, same answer.

---

## Three concrete acks the council needs to give

1. **Accept SPHINCS+ as the PQ adjunct?** If not, what's the
   alternative — Dilithium (smaller sigs but lattice assumption),
   no PQ at all (kicks the can), or HSS/XMSS (stateful, fragile)?

2. **Accept X25519 derived from Ed25519, or require an independent
   X25519 keypair?** Derivation is one fewer key to rotate but ties
   their lifetimes; independence costs an extra 32 bytes in
   discovery and one more rotation primitive.

3. **Accept BLAKE3 migration?** The alternative is migrating
   spec/14 to SHA-256 — slower but more widely supported in
   embedded targets. Vote depends on whether we expect packets
   on hardware that can't ship BLAKE3 in 2026.

If silent for 7 days, default per Rocky's "engineer the
solution then show it" pattern: accept all three, draft canonical
spec/11 §8 patch, present as a follow-up proposal for ratification.

---

*This proposal is observation OBS-axxis-PENDING. It will be
ingested to Oracle on commit with tags
`["spec", "spec/11", "council", "proposal", "shannon", "cross-check"]`
so it surfaces in `oracle_query("spec/11 SPHINCS X25519 BLAKE3")`.*
