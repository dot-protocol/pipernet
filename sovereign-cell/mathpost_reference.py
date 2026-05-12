"""
mathpost_reference.py — DOTpost without Oracle.

A sovereign message between two cells, verifiable by math alone.
Authored by the room during R79c follow-up, 11 May 2026.

No central server is required for sender, recipient, or any verifier.
The transport is interchangeable. The math is the channel.

Dependencies:
    pip install cryptography mnemonic bip32utils tiktoken zstandard

Commands:
    mathpost compose <cell_file> <recipient_dot1> <recipient_ed_pub> <recipient_x_pub> <body>
        → produce a signed encrypted envelope, write to <message_hash>.mpost
    mathpost open <cell_file> <envelope_file>
        → decrypt and verify; print plaintext + sender signature status
    mathpost verify <envelope_file>
        → signature-only verification (no decryption); anyone can do this
    mathpost selftest
        → run round-trip smoke test (v0.2 compression + v0.1 backwards compat)

Honest limits in v0.1 / v0.2:
    - Uses Ed25519 for signing and X25519 for ECDH, both derived from cell's leaf key via SHA-256.
      Production should derive separate keys for signing vs encryption with proper key separation.
    - No thread management beyond prev_hash chain; merging branches not handled.
    - Mailbox transport not included in this file; this file produces and
      consumes envelopes only. Transport is downstream of the math.
    - Replay protection via nonce + recipient's responsibility to track seen hashes.

v0.2 changes (Bellard's Amendment Q3 option a, room-resolved 2026-05-11):
    - zstd compression is MANDATORY (hard dep on zstandard package).
    - Encrypted plaintext = 1-byte compression header || body bytes.
    - Header 0x00 = raw UTF-8 (used when zstd does not shrink the body).
    - Header 0x01 = zstd-compressed body.
    - Envelope dict gains "version": "0.2" field.
    - v0.1 envelopes (no "version" field) continue to decrypt correctly.
"""

from __future__ import annotations
import argparse
import base64
import datetime
import getpass
import hashlib
import json
import os
import re
import secrets
import sys
from pathlib import Path

try:
    import zstandard as zstd
except ImportError:
    zstd = None

from mnemonic import Mnemonic
from bip32utils import BIP32Key

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes, serialization

import tiktoken

CANONICAL_BEGIN = "[CANONICAL_SECTION_BEGIN]"
CANONICAL_END   = "[CANONICAL_SECTION_END]"
HKDF_INFO = b"mathpost/v0.1/ecdh-derive"

MATHPOST_VERSION        = "0.2"   # legacy compose path — sender pubkeys plaintext
MATHPOST_VERSION_SEALED = "0.3"   # sealed-sender path — sender identity inside ciphertext

# HKDF info string is version-scoped so v0.2 and v0.3 derive distinct keys
# even from the same ECDH shared secret. Prevents cross-version replay.
HKDF_INFO_SEALED = b"mathpost/v0.3/ecdh-sealed"

# Compression header bytes (Bellard's Amendment Q3 option a)
_HDR_RAW  = b"\x00"  # 0x00 = raw UTF-8, no compression
_HDR_ZSTD = b"\x01"  # 0x01 = zstd-compressed body


# ============================================================================
# CELL KEY DERIVATION
# ============================================================================

def extract_canonical(cell_text: str) -> str:
    m = re.search(
        r"^" + re.escape(CANONICAL_BEGIN) + r"\s*\n(.*?)\n^" + re.escape(CANONICAL_END) + r"\s*$",
        cell_text, re.DOTALL | re.MULTILINE,
    )
    if not m:
        raise ValueError("canonical section markers not found")
    return m.group(1).strip()


def derive_cell_keypair(canonical_text: str, mnemonic: str, passphrase: str) -> dict:
    enc = tiktoken.get_encoding("cl100k_base")
    tokens = enc.encode(canonical_text)
    seed = Mnemonic("english").to_seed(mnemonic, passphrase=passphrase)
    node = BIP32Key.fromEntropy(seed)
    for t in tokens:
        node = node.ChildKey(t)

    leaf_priv_bytes = node.PrivateKey()
    leaf_pub_bytes  = node.PublicKey()

    ed25519_seed = hashlib.sha256(b"mathpost/ed25519/" + leaf_priv_bytes).digest()
    x25519_seed  = hashlib.sha256(b"mathpost/x25519/" + leaf_priv_bytes).digest()

    ed_priv = Ed25519PrivateKey.from_private_bytes(ed25519_seed)
    ed_pub  = ed_priv.public_key()
    x_priv  = X25519PrivateKey.from_private_bytes(x25519_seed)
    x_pub   = x_priv.public_key()

    addr = hashlib.sha256(leaf_pub_bytes).hexdigest()

    return {
        "dot1": "dot1:" + addr[:16],
        "secp256k1_pubkey_hex": leaf_pub_bytes.hex(),
        "ed25519_priv": ed_priv,
        "ed25519_pub":  ed_pub,
        "ed25519_pub_hex": ed_pub.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        ).hex(),
        "x25519_priv": x_priv,
        "x25519_pub":  x_pub,
        "x25519_pub_hex": x_pub.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        ).hex(),
    }


def load_cell_keys(cell_file: Path) -> dict:
    canonical = extract_canonical(cell_file.read_text(encoding="utf-8"))
    print("Enter the mnemonic and passphrase for this cell:\n")
    mnemonic   = input("mnemonic (12 words): ").strip()
    passphrase = getpass.getpass("passphrase:          ")
    return derive_cell_keypair(canonical, mnemonic, passphrase)


# ============================================================================
# MESSAGE FORMAT
# ============================================================================

def canonical_json(obj: dict) -> bytes:
    return json.dumps(obj, separators=(",", ":"), sort_keys=True).encode("utf-8")


# ============================================================================
# COMPOSE
# ============================================================================

def compose_message(
    sender_keys: dict,
    recipient_dot1: str,
    recipient_ed25519_pub_hex: str,
    recipient_x25519_pub_hex: str,
    body: str,
    thread: str | None = None,
    prev: str | None = None,
) -> dict:
    if zstd is None:
        raise RuntimeError(
            "mathpost v0.2 requires the 'zstandard' package. "
            "Install it with: pip install zstandard"
        )

    recipient_x_pub = X25519PublicKey.from_public_bytes(
        bytes.fromhex(recipient_x25519_pub_hex)
    )
    shared_secret = sender_keys["x25519_priv"].exchange(recipient_x_pub)

    derived_key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=HKDF_INFO,
    ).derive(shared_secret)

    # v0.2 compression layer (Bellard's Amendment Q3 option a)
    body_bytes = body.encode("utf-8")
    compressed = zstd.ZstdCompressor(level=3).compress(body_bytes)
    if len(compressed) < len(body_bytes):
        plaintext_with_header = _HDR_ZSTD + compressed
    else:
        plaintext_with_header = _HDR_RAW + body_bytes

    nonce = secrets.token_bytes(12)
    aesgcm = AESGCM(derived_key)
    ciphertext = aesgcm.encrypt(nonce, plaintext_with_header, associated_data=None)

    envelope = {
        "v":         "mathpost/0.2",
        "version":   MATHPOST_VERSION,
        "to":        recipient_dot1,
        "from":      sender_keys["dot1"],
        "from_ed25519_pub": sender_keys["ed25519_pub_hex"],
        "from_x25519_pub":  sender_keys["x25519_pub_hex"],
        "to_ed25519_pub":   recipient_ed25519_pub_hex,
        "thread":    thread,
        "prev":      prev,
        "ts":        datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "nonce":     base64.b64encode(nonce).decode("ascii"),
        "body":      base64.b64encode(ciphertext).decode("ascii"),
    }

    payload_to_sign = canonical_json(envelope)
    signature = sender_keys["ed25519_priv"].sign(payload_to_sign)
    envelope["sig"] = base64.b64encode(signature).decode("ascii")

    envelope["id"] = hashlib.sha256(canonical_json(envelope)).hexdigest()

    return envelope


# ============================================================================
# OPEN
# ============================================================================

def verify_signature(envelope: dict) -> bool:
    sig_b64 = envelope.pop("sig", None)
    msg_id  = envelope.pop("id", None)
    if not sig_b64:
        return False

    sender_ed_pub = Ed25519PublicKey.from_public_bytes(
        bytes.fromhex(envelope["from_ed25519_pub"])
    )
    payload = canonical_json(envelope)
    try:
        sender_ed_pub.verify(base64.b64decode(sig_b64), payload)
        envelope["sig"] = sig_b64
        if msg_id: envelope["id"] = msg_id
        return True
    except Exception:
        envelope["sig"] = sig_b64
        if msg_id: envelope["id"] = msg_id
        return False


def decrypt_body(envelope: dict, recipient_keys: dict) -> str:
    sender_x_pub = X25519PublicKey.from_public_bytes(
        bytes.fromhex(envelope["from_x25519_pub"])
    )
    shared_secret = recipient_keys["x25519_priv"].exchange(sender_x_pub)
    derived_key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=HKDF_INFO,
    ).derive(shared_secret)

    nonce      = base64.b64decode(envelope["nonce"])
    ciphertext = base64.b64decode(envelope["body"])
    aesgcm = AESGCM(derived_key)
    plaintext = aesgcm.decrypt(nonce, ciphertext, associated_data=None)

    # v0.2: read compression header byte; v0.1 (no "version" field): legacy path
    if envelope.get("version") == "0.2":
        if len(plaintext) < 1:
            raise ValueError("malformed mathpost v0.2: empty plaintext")
        header = plaintext[0:1]
        body_bytes = plaintext[1:]
        if header == _HDR_RAW:
            return body_bytes.decode("utf-8")
        elif header == _HDR_ZSTD:
            if zstd is None:
                raise RuntimeError(
                    "mathpost v0.2 zstd envelope requires the 'zstandard' package. "
                    "Install it with: pip install zstandard"
                )
            return zstd.ZstdDecompressor().decompress(body_bytes).decode("utf-8")
        else:
            raise ValueError(
                f"malformed mathpost v0.2: unknown compression header 0x{header.hex()}"
            )
    else:
        # v0.1 legacy: plaintext is raw UTF-8, no header byte
        return plaintext.decode("utf-8")


# ============================================================================
# SEALED-SENDER (mathpost v0.3)
# ============================================================================
#
# Audit-Carol finding (2026-05-11): in v0.2 the outer envelope plaintext leaked
# `from`, `from_ed25519_pub`, `from_x25519_pub`. Anyone with the envelope —
# the mailbox, the relay, a passive observer — learned sender identity even
# though body content was encrypted.
#
# v0.3 fix: sealed-sender via ephemeral X25519.
#   1. Sender generates a fresh X25519 keypair PER ENVELOPE.
#   2. ECDH(ephemeral_priv, recipient_long_term_x_pub) → shared secret → AES key.
#   3. INNER body (encrypted) carries:  from dot1, from ed25519 pub, from x25519 LT pub,
#      thread, prev, subject, message body, and a signature over the canonical inner.
#   4. OUTER envelope (plaintext) carries only:  v/version, to, to_ed25519_pub,
#      ephemeral_x25519_pub, ts, nonce, body (ciphertext), id (sha256 of canonical outer).
#
# What the mailbox / relay / passive observer can see:
#   - recipient dot1 (needed for routing)
#   - one-time ephemeral pubkey (anonymous, doesn't link to sender's identity)
#   - timestamp + envelope id
#   - ciphertext size (a metadata side-channel — unavoidable)
#
# What stays private:
#   - sender dot1, sender ed25519 pubkey, sender x25519 long-term pubkey, thread, prev, subject, body
#   - the sender signature itself (verified by recipient post-decrypt)


def _seal_inner_body(
    sender_keys: dict,
    recipient_dot1: str,
    body: str,
    thread: str | None,
    prev: str | None,
    subject: str | None,
    outer_id_placeholder: str,
) -> bytes:
    """Build + sign the inner JSON, return UTF-8 bytes (NOT yet encrypted)."""
    inner = {
        "from":             sender_keys["dot1"],
        "from_ed25519_pub": sender_keys["ed25519_pub_hex"],
        "from_x25519_pub":  sender_keys["x25519_pub_hex"],
        "to":               recipient_dot1,
        "thread":           thread,
        "prev":             prev,
        "subject":          subject,
        "body":             body,
        "outer_id_binding": outer_id_placeholder,
    }
    payload_to_sign = canonical_json(inner)
    signature       = sender_keys["ed25519_priv"].sign(payload_to_sign)
    inner["sig"]    = base64.b64encode(signature).decode("ascii")
    return canonical_json(inner)


def seal_envelope(
    sender_keys: dict,
    recipient_dot1: str,
    recipient_ed25519_pub_hex: str,
    recipient_x25519_pub_hex: str,
    body: str,
    thread: str | None = None,
    prev: str | None = None,
    subject: str | None = None,
) -> dict:
    """Build a mathpost v0.3 sealed-sender envelope.

    The signature over the inner body is bound to the outer envelope id so a
    malicious mailbox cannot reuse a decrypted-and-re-encrypted body inside a
    different outer envelope.
    """
    if zstd is None:
        raise RuntimeError(
            "mathpost v0.3 requires the 'zstandard' package. "
            "Install it with: pip install zstandard"
        )

    # 1. Ephemeral X25519 keypair, used once.
    ephemeral_priv = X25519PrivateKey.generate()
    ephemeral_pub  = ephemeral_priv.public_key()
    ephemeral_pub_hex = ephemeral_pub.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex()

    # 2. ECDH with recipient's long-term x25519 pubkey.
    recipient_x_pub = X25519PublicKey.from_public_bytes(
        bytes.fromhex(recipient_x25519_pub_hex)
    )
    shared_secret = ephemeral_priv.exchange(recipient_x_pub)
    derived_key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=HKDF_INFO_SEALED,
    ).derive(shared_secret)

    # 3. Pre-compute outer skeleton so the inner can bind to outer_id.
    ts    = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    nonce = secrets.token_bytes(12)

    outer_skeleton = {
        "v":                    "mathpost/0.3",
        "version":              MATHPOST_VERSION_SEALED,
        "to":                   recipient_dot1,
        "to_ed25519_pub":       recipient_ed25519_pub_hex,
        "ephemeral_x25519_pub": ephemeral_pub_hex,
        "ts":                   ts,
        "nonce":                base64.b64encode(nonce).decode("ascii"),
    }
    # outer_id is derived from canonical(outer_skeleton) — i.e. the routing
    # header. The inner body binds to this id; the final outer with body+id
    # is computed below.
    outer_id_binding = hashlib.sha256(canonical_json(outer_skeleton)).hexdigest()

    # 4. Build + sign inner body.
    inner_bytes = _seal_inner_body(
        sender_keys,
        recipient_dot1,
        body,
        thread,
        prev,
        subject,
        outer_id_binding,
    )

    # 5. Compress + AES-GCM encrypt.
    compressed = zstd.ZstdCompressor(level=3).compress(inner_bytes)
    if len(compressed) < len(inner_bytes):
        plaintext_with_header = _HDR_ZSTD + compressed
    else:
        plaintext_with_header = _HDR_RAW + inner_bytes

    aesgcm = AESGCM(derived_key)
    ciphertext = aesgcm.encrypt(nonce, plaintext_with_header, associated_data=None)

    # 6. Assemble the final outer envelope.
    envelope = dict(outer_skeleton)
    envelope["body"] = base64.b64encode(ciphertext).decode("ascii")
    envelope["id"]   = hashlib.sha256(canonical_json(envelope)).hexdigest()

    return envelope


def open_sealed_envelope(envelope: dict, recipient_keys: dict) -> dict:
    """Decrypt + verify a mathpost v0.3 sealed-sender envelope.

    Returns a dict with the revealed inner body fields. Raises ValueError on
    signature failure or version mismatch.
    """
    if envelope.get("version") != MATHPOST_VERSION_SEALED:
        raise ValueError(
            f"open_sealed_envelope: expected version {MATHPOST_VERSION_SEALED!r}, "
            f"got {envelope.get('version')!r}"
        )

    # 1. ECDH with the ephemeral key.
    ephemeral_pub = X25519PublicKey.from_public_bytes(
        bytes.fromhex(envelope["ephemeral_x25519_pub"])
    )
    shared_secret = recipient_keys["x25519_priv"].exchange(ephemeral_pub)
    derived_key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=HKDF_INFO_SEALED,
    ).derive(shared_secret)

    # 2. AES-GCM decrypt.
    nonce      = base64.b64decode(envelope["nonce"])
    ciphertext = base64.b64decode(envelope["body"])
    aesgcm     = AESGCM(derived_key)
    plaintext  = aesgcm.decrypt(nonce, ciphertext, associated_data=None)

    # 3. Strip compression header, decompress if needed.
    if len(plaintext) < 1:
        raise ValueError("malformed mathpost v0.3: empty plaintext")
    header     = plaintext[0:1]
    body_bytes = plaintext[1:]
    if header == _HDR_RAW:
        inner_bytes = body_bytes
    elif header == _HDR_ZSTD:
        if zstd is None:
            raise RuntimeError(
                "mathpost v0.3 zstd envelope requires the 'zstandard' package. "
                "Install it with: pip install zstandard"
            )
        inner_bytes = zstd.ZstdDecompressor().decompress(body_bytes)
    else:
        raise ValueError(
            f"malformed mathpost v0.3: unknown compression header 0x{header.hex()}"
        )

    inner = json.loads(inner_bytes.decode("utf-8"))

    # 4. Verify the inner signature using the now-revealed sender ed25519 pubkey.
    sig_b64 = inner.pop("sig", None)
    if not sig_b64:
        raise ValueError("missing sig in sealed inner body")
    sender_ed_pub = Ed25519PublicKey.from_public_bytes(
        bytes.fromhex(inner["from_ed25519_pub"])
    )
    payload = canonical_json(inner)
    try:
        sender_ed_pub.verify(base64.b64decode(sig_b64), payload)
    except Exception as e:
        raise ValueError(f"sealed inner signature verification failed: {e}")

    # 5. Verify the outer_id_binding — sender committed to a specific outer
    #    routing header; any tamper of outer envelope shape breaks this.
    binding_claim = inner.get("outer_id_binding")
    outer_skeleton = {
        k: envelope[k]
        for k in ("v", "version", "to", "to_ed25519_pub",
                  "ephemeral_x25519_pub", "ts", "nonce")
    }
    computed_binding = hashlib.sha256(canonical_json(outer_skeleton)).hexdigest()
    if binding_claim != computed_binding:
        raise ValueError(
            "outer_id_binding mismatch — envelope routing header was tampered "
            "with after the inner was sealed"
        )

    inner["sig"] = sig_b64   # restore for caller inspection
    return inner


# ============================================================================
# SELF-TEST
# ============================================================================

def _round_trip_smoke_test():
    """v0.2 round-trip smoke test + v0.1 backwards-compat check.

    Invoke with:  python mathpost_reference.py selftest
    """
    import os

    print("=== mathpost selftest ===\n")

    # --- build two cells using simple canonical-section strings ---
    MNEMONIC   = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
    PASSPHRASE = "mathpost-selftest"

    canonical_alice = "alice-test-cell-canonical-section"
    canonical_bob   = "bob-test-cell-canonical-section"

    print("Deriving keypairs (Alice + Bob)...")
    alice = derive_cell_keypair(canonical_alice, MNEMONIC, PASSPHRASE)
    bob   = derive_cell_keypair(canonical_bob,   MNEMONIC, PASSPHRASE)
    print(f"  Alice dot1: {alice['dot1']}")
    print(f"  Bob   dot1: {bob['dot1']}\n")

    # --- compose a 5 KB message (compressible) ---
    sample_body = "The quick brown fox " * 250          # 5 000 chars
    raw_bytes   = sample_body.encode("utf-8")
    print(f"Sample body: {len(raw_bytes)} bytes raw")

    print("Composing v0.2 envelope...")
    envelope = compose_message(
        sender_keys              = alice,
        recipient_dot1           = bob["dot1"],
        recipient_ed25519_pub_hex = bob["ed25519_pub_hex"],
        recipient_x25519_pub_hex  = bob["x25519_pub_hex"],
        body                     = sample_body,
    )

    assert envelope.get("version") == "0.2", \
        f"Expected version '0.2', got {envelope.get('version')!r}"
    print(f"  envelope version: {envelope['version']}  ✓")
    print(f"  envelope id:      {envelope['id']}")

    # peek at the compression by inspecting the ciphertext size vs raw
    ciphertext_bytes = base64.b64decode(envelope["body"])
    # subtract AES-GCM tag (16 bytes) and header byte (1 byte) to approximate
    compressed_payload_size = len(ciphertext_bytes) - 16 - 1
    print(f"\nSize report:")
    print(f"  raw body:           {len(raw_bytes):>7} bytes")
    print(f"  AES-GCM ciphertext: {len(ciphertext_bytes):>7} bytes  (includes 1-byte header + 16-byte GCM tag)")
    print(f"  approx payload:     {compressed_payload_size:>7} bytes  (ciphertext - GCM tag - header)")
    ratio = compressed_payload_size / len(raw_bytes) * 100
    print(f"  compression ratio:  {ratio:.1f}% of raw")

    # --- decrypt on Bob's side ---
    print("\nDecrypting on Bob's side...")
    plaintext = decrypt_body(envelope, bob)
    assert plaintext == sample_body, "FAIL: decrypted body does not match input"
    print("  plaintext matches input  ✓")

    # verify signature
    sig_ok = verify_signature(envelope)
    assert sig_ok, "FAIL: signature verification failed"
    print("  signature valid          ✓")

    # -----------------------------------------------------------------------
    # Backwards-compat: synthesize a v0.1-style envelope (no "version" field,
    # plaintext is raw UTF-8 with NO compression header byte).
    # -----------------------------------------------------------------------
    print("\n--- Backwards-compat: v0.1 envelope ---")
    v01_body = "Hello from v0.1"

    # Build a real v0.2 envelope then manually patch it to look like v0.1:
    # re-encrypt the body WITHOUT the header byte and strip the "version" field.
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF as _HKDF

    sender_x_pub_for_bob = X25519PublicKey.from_public_bytes(
        bytes.fromhex(alice["x25519_pub_hex"])
    )
    shared = bob["x25519_priv"].exchange(sender_x_pub_for_bob)
    # We need the SAME derived key that compose used — derive from Alice's perspective
    alice_shared = alice["x25519_priv"].exchange(
        X25519PublicKey.from_public_bytes(bytes.fromhex(bob["x25519_pub_hex"]))
    )
    derived_key_v01 = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=HKDF_INFO,
    ).derive(alice_shared)

    nonce_v01 = secrets.token_bytes(12)
    aesgcm_v01 = AESGCM(derived_key_v01)
    # v0.1: encrypt raw UTF-8, no header byte
    ct_v01 = aesgcm_v01.encrypt(nonce_v01, v01_body.encode("utf-8"), associated_data=None)

    envelope_v01 = {
        "v":                  "mathpost/0.1",
        # "version" field deliberately absent — that's what marks it as v0.1
        "to":                 bob["dot1"],
        "from":               alice["dot1"],
        "from_ed25519_pub":   alice["ed25519_pub_hex"],
        "from_x25519_pub":    alice["x25519_pub_hex"],
        "to_ed25519_pub":     bob["ed25519_pub_hex"],
        "thread":             None,
        "prev":               None,
        "ts":                 datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "nonce":              base64.b64encode(nonce_v01).decode("ascii"),
        "body":               base64.b64encode(ct_v01).decode("ascii"),
    }

    decrypted_v01 = decrypt_body(envelope_v01, bob)
    assert decrypted_v01 == v01_body, \
        f"FAIL: v0.1 backwards-compat broken — got {decrypted_v01!r}"
    print(f"  v0.1 envelope decrypted correctly: {decrypted_v01!r}  ✓")

    # -----------------------------------------------------------------------
    # v0.3 sealed-sender round trip (Audit-Carol fix).
    # -----------------------------------------------------------------------
    print("\n--- Sealed-sender v0.3 round trip ---")
    v03_body = "The mailbox cannot read who I am. " * 10  # ~340 bytes
    sealed = seal_envelope(
        sender_keys              = alice,
        recipient_dot1           = bob["dot1"],
        recipient_ed25519_pub_hex = bob["ed25519_pub_hex"],
        recipient_x25519_pub_hex  = bob["x25519_pub_hex"],
        body                     = v03_body,
        subject                  = "sealed-sender smoke",
        thread                   = "test-thread",
        prev                     = None,
    )

    # Confirm outer envelope leaks NO sender identity.
    for forbidden_key in ("from", "from_ed25519_pub", "from_x25519_pub"):
        assert forbidden_key not in sealed, (
            f"FAIL: outer envelope still leaks {forbidden_key!r} — "
            "Audit-Carol issue NOT fixed"
        )
    print("  outer envelope contains no from/sender pubkeys  ✓")

    # Required outer fields.
    for required in ("v", "version", "to", "to_ed25519_pub",
                     "ephemeral_x25519_pub", "ts", "nonce", "body", "id"):
        assert required in sealed, f"FAIL: outer missing {required!r}"
    assert sealed["version"] == "0.3"
    assert sealed["v"] == "mathpost/0.3"
    print(f"  outer schema valid (v={sealed['v']!r}, version={sealed['version']!r})  ✓")
    print(f"  outer envelope id: {sealed['id']}")

    # Open on Bob's side, confirm inner reveals sender + body.
    inner = open_sealed_envelope(sealed, bob)
    assert inner["from"]              == alice["dot1"]
    assert inner["from_ed25519_pub"]  == alice["ed25519_pub_hex"]
    assert inner["from_x25519_pub"]   == alice["x25519_pub_hex"]
    assert inner["body"]              == v03_body
    assert inner["subject"]           == "sealed-sender smoke"
    assert inner["thread"]            == "test-thread"
    assert inner["prev"] is None
    print(f"  sender revealed: {inner['from']}  ✓")
    print(f"  body matches input  ✓")
    print(f"  signature verified by sender ed25519 pub  ✓")

    # Tamper test: flip a byte in the outer routing header, confirm rejection.
    tampered = dict(sealed)
    tampered["to"] = "dot1:0000000000000000"
    try:
        open_sealed_envelope(tampered, bob)
    except Exception as e:
        msg = str(e)
        # Either AES-GCM tag fails OR binding mismatch — both are correct rejections.
        assert ("InvalidTag" in msg
                or "outer_id_binding" in msg
                or "decryption" in msg.lower()
                or "verification failed" in msg.lower()), (
            f"expected tamper rejection, got: {msg}"
        )
        print(f"  tamper of outer.to → rejected ({type(e).__name__})  ✓")
    else:
        raise AssertionError("FAIL: tampered envelope was NOT rejected")

    print("\n=== ALL TESTS PASSED ===\n")




# ============================================================================
# MAILBOX TRANSPORT HELPERS  (Phase 2 — closes the transport loop)
# ============================================================================

DEFAULT_MAILBOX_URL = os.environ.get("MATHPOST_MAILBOX_URL", "https://relay.piedpiper.fun")
_CURSOR_DIR = os.path.expanduser("~/.mathpost/cursors")

# Pubkey line patterns embedded in cell files (optional, below CANONICAL_SECTION_END)
_ED25519_PUB_RE  = re.compile(r"^\s*ed25519_pub:\s*([0-9a-f]{64})\s*$",  re.IGNORECASE)
_X25519_PUB_RE   = re.compile(r"^\s*x25519_pub:\s*([0-9a-f]{64})\s*$",   re.IGNORECASE)
# dot1 line in section 1 header: - **Personal `dot1:`:** dot1:... (any variant)
_DOT1_ANYWHERE_RE = re.compile(r"\b(dot1:[0-9a-f]{16})\b")


def _http_get(url: str, timeout: int = 15) -> "requests.Response":
    """GET with clear error on connection failure."""
    try:
        import requests as _req
        resp = _req.get(url, timeout=timeout)
        return resp
    except Exception as exc:
        print(f"[mailbox] connection error: {exc}", file=sys.stderr)
        sys.exit(2)


def _http_post(url: str, payload: dict, timeout: int = 15) -> "requests.Response":
    """POST JSON with clear error on connection failure."""
    try:
        import requests as _req
        resp = _req.post(url, json=payload, timeout=timeout)
        return resp
    except Exception as exc:
        print(f"[mailbox] connection error: {exc}", file=sys.stderr)
        sys.exit(2)


def extract_recipient_pubkeys(cell_path: Path) -> dict:
    """Read dot1 + ed25519_pub + x25519_pub from a cell file.

    Looks for optional pubkey lines below [CANONICAL_SECTION_END]:
        ed25519_pub: <64 hex chars>
        x25519_pub:  <64 hex chars>

    Also reads the dot1 from the '**Personal `dot1:`**' header line.

    Raises ValueError with a clear message if any field is missing.
    Returns dict with keys: dot1, ed25519_pub_hex, x25519_pub_hex
    """
    text = cell_path.read_text(encoding="utf-8")
    dot1 = ed25519_pub = x25519_pub = None

    for line in text.splitlines():
        # dot1: look only in lines that contain "Personal" and "dot1:" (the header line)
        if dot1 is None and "Personal" in line and "dot1:" in line:
            m = _DOT1_ANYWHERE_RE.search(line)
            if m:
                dot1 = m.group(1)
        if ed25519_pub is None:
            m = _ED25519_PUB_RE.match(line)
            if m:
                ed25519_pub = m.group(1)
        if x25519_pub is None:
            m = _X25519_PUB_RE.match(line)
            if m:
                x25519_pub = m.group(1)

    missing = []
    if not dot1:
        missing.append("dot1 (expected '- **Personal `dot1:`**: dot1:...' line)")
    if not ed25519_pub:
        missing.append("ed25519_pub (expected 'ed25519_pub: <64 hex>' line in cell file)")
    if not x25519_pub:
        missing.append("x25519_pub (expected 'x25519_pub: <64 hex>' line in cell file)")
    if missing:
        raise ValueError(
            f"Cannot read recipient pubkeys from {cell_path}.\n"
            "Missing fields:\n" + "\n".join(f"  - {m}" for m in missing) + "\n\n"
            "Either add these lines to the cell file (below [CANONICAL_SECTION_END]) "
            "or supply --recipient-dot1, --recipient-ed25519-pub, --recipient-x25519-pub flags."
        )

    return {
        "dot1": dot1,
        "ed25519_pub_hex": ed25519_pub,
        "x25519_pub_hex": x25519_pub,
    }


def _load_cursor(dot1: str) -> int:
    """Load seq cursor for dot1 from ~/.mathpost/cursors/{dot1}.json. Default 0."""
    path = os.path.join(_CURSOR_DIR, f"{dot1}.json")
    if os.path.exists(path):
        try:
            data = json.loads(open(path).read())
            return int(data.get("cursor", 0))
        except Exception:
            return 0
    return 0


def _save_cursor(dot1: str, cursor: int) -> None:
    """Save seq cursor for dot1 to ~/.mathpost/cursors/{dot1}.json."""
    os.makedirs(_CURSOR_DIR, exist_ok=True)
    path = os.path.join(_CURSOR_DIR, f"{dot1}.json")
    with open(path, "w") as f:
        json.dump({"cursor": cursor, "last_fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}, f)


# ============================================================================
# CMD: send
# ============================================================================

def cmd_send(args: "argparse.Namespace") -> None:
    mailbox_base = (args.mailbox or DEFAULT_MAILBOX_URL).rstrip("/")

    # Load sender
    sender_cell_path = Path(args.sender_cell)
    if not sender_cell_path.exists():
        print(f"error: sender cell file not found: {sender_cell_path}", file=sys.stderr)
        sys.exit(1)
    sender_canonical = extract_canonical(sender_cell_path.read_text(encoding="utf-8"))
    sender_keys = derive_cell_keypair(sender_canonical, args.sender_mnemonic, args.sender_passphrase)

    # Load recipient pubkeys
    recipient_cell_path = Path(args.recipient_cell)
    if not recipient_cell_path.exists():
        print(f"error: recipient cell file not found: {recipient_cell_path}", file=sys.stderr)
        sys.exit(1)

    try:
        rkeys = extract_recipient_pubkeys(recipient_cell_path)
        recipient_dot1        = rkeys["dot1"]
        recipient_ed25519_pub = rkeys["ed25519_pub_hex"]
        recipient_x25519_pub  = rkeys["x25519_pub_hex"]
    except ValueError as exc:
        # Fallback: explicit flags
        if args.recipient_dot1 and args.recipient_ed25519_pub and args.recipient_x25519_pub:
            recipient_dot1        = args.recipient_dot1
            recipient_ed25519_pub = args.recipient_ed25519_pub
            recipient_x25519_pub  = args.recipient_x25519_pub
        else:
            print(f"error: {exc}", file=sys.stderr)
            print("Tip: supply --recipient-dot1, --recipient-ed25519-pub, --recipient-x25519-pub", file=sys.stderr)
            sys.exit(1)

    # Read body
    if args.body_file:
        body = Path(args.body_file).read_text(encoding="utf-8")
    elif args.body_stdin:
        body = sys.stdin.read()
    else:
        print("error: provide --body-file <path> or --body-stdin", file=sys.stderr)
        sys.exit(1)

    # Compose — default to sealed (v0.3), `--legacy` falls back to v0.2.
    if getattr(args, "legacy", False):
        envelope = compose_message(
            sender_keys,
            recipient_dot1,
            recipient_ed25519_pub,
            recipient_x25519_pub,
            body,
            thread=args.thread,
            prev=args.prev,
        )
        envelope_kind = "v0.2 (legacy — sender pubkeys plaintext)"
    else:
        envelope = seal_envelope(
            sender_keys,
            recipient_dot1,
            recipient_ed25519_pub,
            recipient_x25519_pub,
            body,
            thread=args.thread,
            prev=args.prev,
            subject=getattr(args, "subject", None),
        )
        envelope_kind = "v0.3 (sealed sender)"

    envelope_id = envelope["id"]
    size_bytes  = len(json.dumps(envelope, separators=(",", ":")).encode())

    print(f"\nmathpost envelope composed ({envelope_kind}):")
    print(f"  envelope_id : {envelope_id}")
    # `from` only exists at the outer layer for v0.2; for v0.3 it's inside the
    # ciphertext (sealed sender). Show "sealed" to make the privacy posture obvious.
    print(f"  from        : {envelope.get('from', '<sealed>')}")
    print(f"  to          : {envelope['to']}")
    print(f"  thread      : {envelope.get('thread', '<sealed>')}")
    print(f"  ts          : {envelope['ts']}")
    print(f"  size_bytes  : {size_bytes}")
    if "sig" in envelope:
        print(f"  sig[:32]    : {envelope['sig'][:32]}")
    if "ephemeral_x25519_pub" in envelope:
        print(f"  ephemeral_x : {envelope['ephemeral_x25519_pub'][:32]}...")

    if args.no_push:
        out_path = f"/tmp/mathpost-{envelope_id[:16]}.mpost"
        Path(out_path).write_text(json.dumps(envelope, indent=2), encoding="utf-8")
        print(f"\n--no-push: envelope written to {out_path}")
        return

    # Push to mailbox
    url = f"{mailbox_base}/mailbox/{recipient_dot1}/push"
    resp = _http_post(url, envelope)

    if resp.status_code == 201:
        data = resp.json()
        print(f"\nmailbox=ok  seq={data.get('seq')}  pushed_at={data.get('pushed_at')}")
    elif resp.status_code == 409:
        data = resp.json()
        print(f"\nmailbox=duplicate  envelope_id={data.get('envelope_id', envelope_id)}")
    else:
        print(f"\nmailbox error  status={resp.status_code}", file=sys.stderr)
        print(resp.text, file=sys.stderr)
        sys.exit(1)


# ============================================================================
# CMD: pull
# ============================================================================

def cmd_pull(args: "argparse.Namespace") -> None:
    mailbox_base = (args.mailbox or DEFAULT_MAILBOX_URL).rstrip("/")

    # Load own keys
    cell_path = Path(args.cell)
    if not cell_path.exists():
        print(f"error: cell file not found: {cell_path}", file=sys.stderr)
        sys.exit(1)
    canonical  = extract_canonical(cell_path.read_text(encoding="utf-8"))
    own_keys   = derive_cell_keypair(canonical, args.mnemonic, args.passphrase)
    own_dot1   = own_keys["dot1"]

    # Cursor
    if args.since is not None:
        cursor = args.since
    else:
        cursor = _load_cursor(own_dot1)

    # Fetch
    url = f"{mailbox_base}/mailbox/{own_dot1}/pull?since={cursor}"
    resp = _http_get(url)
    if resp.status_code != 200:
        print(f"error: mailbox pull failed  status={resp.status_code}", file=sys.stderr)
        print(resp.text, file=sys.stderr)
        sys.exit(1)

    data      = resp.json()
    envelopes = data.get("envelopes", [])

    n_pulled    = 0
    n_verified  = 0
    n_decrypted = 0
    max_seq     = cursor

    for item in envelopes:
        seq  = item["seq"]
        env  = item["envelope"]
        pts  = item.get("pushed_at", "")
        n_pulled += 1
        if seq > max_seq:
            max_seq = seq

        env_id     = env.get("id", "?")
        env_ts     = env.get("ts", "?")
        env_version = env.get("version", "0.1")
        is_sealed   = env_version == MATHPOST_VERSION_SEALED

        # For sealed envelopes the sender + thread live INSIDE the ciphertext,
        # so we show "<sealed>" at the routing-layer summary and unseal below.
        env_from   = "<sealed>" if is_sealed else env.get("from", "?")
        env_thread = "<sealed>" if is_sealed else env.get("thread")
        print(
            f"\n--- envelope  seq={seq}  id={env_id[:16]}...  "
            f"ts={env_ts}  version={env_version}  from={env_from}  thread={env_thread} ---"
        )

        if is_sealed:
            # v0.3: open_sealed_envelope verifies the inner signature AND
            # the outer_id_binding in one shot. No separate verify pass.
            if args.verify_only:
                print("  (verify-only on sealed envelopes requires decrypt — skipping)")
                continue
            try:
                inner = open_sealed_envelope(env, own_keys)
                n_verified  += 1   # signature checked inside open_sealed_envelope
                n_decrypted += 1
                plaintext = inner["body"]
                print(f"  sig=OK  sender_revealed={inner['from']}")
                print(f"  decrypt=OK  plaintext_bytes={len(plaintext.encode())}")
                if args.show_body:
                    if len(plaintext) > 500:
                        print(f"\n  BODY (first 500 chars):\n{plaintext[:500]}\n  [... truncated, total {len(plaintext)} chars]")
                    else:
                        print(f"\n  BODY:\n{plaintext}")
            except Exception as exc:
                print(f"  unseal=FAIL  reason={exc}")
            continue

        # v0.1 / v0.2 legacy path — sender pubkeys plaintext at outer.
        sig_ok = verify_signature(env)
        print(f"  sig={'OK' if sig_ok else 'FAIL'}")
        if sig_ok:
            n_verified += 1

        if args.verify_only:
            continue

        try:
            plaintext = decrypt_body(env, own_keys)
            n_decrypted += 1
            print(f"  decrypt=OK  plaintext_bytes={len(plaintext.encode())}")
            if args.show_body:
                if len(plaintext) > 500:
                    print(f"\n  BODY (first 500 chars):\n{plaintext[:500]}\n  [... truncated, total {len(plaintext)} chars]")
                else:
                    print(f"\n  BODY:\n{plaintext}")
        except Exception as exc:
            print(f"  decrypt=FAIL  reason={exc}")

    # Save cursor
    _save_cursor(own_dot1, max_seq)

    print(f"\npulled={n_pulled}  verified={n_verified}  decrypted={n_decrypted}  cursor->{max_seq}")


# ============================================================================
# CMD: mailbox-stats
# ============================================================================

def cmd_mailbox_stats(args: "argparse.Namespace") -> None:
    mailbox_base = (args.mailbox or DEFAULT_MAILBOX_URL).rstrip("/")
    url = f"{mailbox_base}/mailbox/{args.dot1}/stats"
    resp = _http_get(url)
    print(json.dumps(resp.json(), indent=2))
    if resp.status_code != 200:
        sys.exit(1)


# ============================================================================
# CMD: mailbox-health
# ============================================================================

def cmd_mailbox_health(args: "argparse.Namespace") -> None:
    mailbox_base = (args.mailbox or DEFAULT_MAILBOX_URL).rstrip("/")
    url = f"{mailbox_base}/health"
    resp = _http_get(url)
    print(json.dumps(resp.json(), indent=2))
    if resp.status_code != 200:
        sys.exit(1)


def main():
    p = argparse.ArgumentParser(description="mathpost — DOTpost without Oracle")
    sub = p.add_subparsers(dest="cmd", required=True)

    pc = sub.add_parser("compose")
    pc.add_argument("cell_file", type=Path)
    pc.add_argument("recipient_dot1")
    pc.add_argument("recipient_ed_pub")
    pc.add_argument("recipient_x_pub")
    pc.add_argument("body")
    pc.add_argument("--thread", default=None)
    pc.add_argument("--prev",   default=None)
    pc.add_argument("--out", type=Path, default=None)

    po = sub.add_parser("open")
    po.add_argument("cell_file",      type=Path)
    po.add_argument("envelope_file",  type=Path)

    pv = sub.add_parser("verify")
    pv.add_argument("envelope_file", type=Path)

    sub.add_parser("selftest")

    # ---- send ----
    ps = sub.add_parser("send", help="Compose + push envelope to mailbox daemon")
    ps.add_argument("--sender-cell",       required=True,  help="Path to sender's cell file")
    ps.add_argument("--sender-mnemonic",   required=True,  help="Sender's BIP-39 mnemonic (12 words)")
    ps.add_argument("--sender-passphrase", required=True,  help="Sender's 25th-word passphrase")
    ps.add_argument("--recipient-cell",    required=True,  help="Path to recipient's cell file")
    # body source (exactly one required, checked at runtime)
    pg = ps.add_mutually_exclusive_group()
    pg.add_argument("--body-file",  default=None, help="Path to plaintext body file")
    pg.add_argument("--body-stdin", action="store_true",  help="Read body from stdin")
    # optional message fields
    ps.add_argument("--thread",  default=None, help="Thread ID")
    ps.add_argument("--prev",    default=None, help="Previous envelope ID (chain)")
    ps.add_argument("--subject", default=None, help="Subject line (sealed inside body for v0.3)")
    # version selection (sealed-sender by default)
    ps.add_argument(
        "--legacy",
        action="store_true",
        help="Use v0.2 envelope (sender pubkeys plaintext at outer). "
             "Default is v0.3 sealed-sender; --legacy is for senders that need "
             "compatibility with v0.2-only receivers.",
    )
    # transport
    ps.add_argument("--mailbox",  default=None, help="Mailbox base URL (overrides MATHPOST_MAILBOX_URL)")
    ps.add_argument("--no-push",  action="store_true", help="Write envelope to /tmp instead of pushing")
    # fallback pubkey flags (used when cell file lacks pubkey lines)
    ps.add_argument("--recipient-dot1",        default=None, help="Recipient dot1 (fallback)")
    ps.add_argument("--recipient-ed25519-pub", default=None, help="Recipient ed25519 pubkey hex (fallback)")
    ps.add_argument("--recipient-x25519-pub",  default=None, help="Recipient x25519 pubkey hex (fallback)")

    # ---- pull ----
    pp = sub.add_parser("pull", help="Fetch + decrypt envelopes from mailbox daemon")
    pp.add_argument("--cell",       required=True, help="Path to own cell file")
    pp.add_argument("--mnemonic",   required=True, help="Own BIP-39 mnemonic (12 words)")
    pp.add_argument("--passphrase", required=True, help="Own 25th-word passphrase")
    pp.add_argument("--mailbox",    default=None,  help="Mailbox base URL (overrides MATHPOST_MAILBOX_URL)")
    pp.add_argument("--since",      type=int, default=None, help="Fetch envelopes with seq > N (default: use saved cursor)")
    pp.add_argument("--verify-only", action="store_true", help="Verify signatures only, skip decrypt")
    pp.add_argument("--show-body",   action="store_true", help="Print decrypted body text")

    # ---- mailbox-stats ----
    pms = sub.add_parser("mailbox-stats", help="GET /mailbox/{dot1}/stats from mailbox daemon")
    pms.add_argument("--dot1",    required=True, help="dot1 address to query")
    pms.add_argument("--mailbox", default=None,  help="Mailbox base URL")

    # ---- mailbox-health ----
    pmh = sub.add_parser("mailbox-health", help="GET /health from mailbox daemon")
    pmh.add_argument("--mailbox", default=None, help="Mailbox base URL")

    args = p.parse_args()

    if args.cmd == "compose":
        sender_keys = load_cell_keys(args.cell_file)
        envelope = compose_message(
            sender_keys, args.recipient_dot1,
            args.recipient_ed_pub, args.recipient_x_pub,
            args.body, thread=args.thread, prev=args.prev,
        )
        out = args.out or Path(f"{envelope['id'][:16]}.mpost")
        out.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
        print(f"\nMessage composed:")
        print(f"  id:       {envelope['id']}")
        print(f"  from:     {envelope['from']}")
        print(f"  to:       {envelope['to']}")
        print(f"  written:  {out}")
        print("\nTransport this file by ANY substrate. No Oracle. No server.\n")

    elif args.cmd == "open":
        envelope = json.loads(args.envelope_file.read_text(encoding="utf-8"))
        recipient_keys = load_cell_keys(args.cell_file)
        if envelope["to"] != recipient_keys["dot1"]:
            sys.exit(f"address mismatch: envelope to {envelope['to']}, your cell is {recipient_keys['dot1']}")
        sig_ok = verify_signature(envelope)
        print(f"\nSignature: {'VALID' if sig_ok else 'INVALID'}")
        if not sig_ok:
            sys.exit("aborted")
        plaintext = decrypt_body(envelope, recipient_keys)
        print(f"\n  id:    {envelope['id']}")
        print(f"  from:  {envelope['from']}")
        print(f"  to:    {envelope['to']}")
        print(f"  ts:    {envelope['ts']}")
        print(f"\nBODY:\n{plaintext}\n")

    elif args.cmd == "verify":
        envelope = json.loads(args.envelope_file.read_text(encoding="utf-8"))
        sig_ok = verify_signature(envelope)
        print(f"\n  id:    {envelope.get('id')}")
        print(f"  from:  {envelope['from']}")
        print(f"  to:    {envelope['to']}")
        print(f"  sig:   {'VALID' if sig_ok else 'INVALID'}")

    elif args.cmd == "selftest":
        _round_trip_smoke_test()

    elif args.cmd == "send":
        cmd_send(args)

    elif args.cmd == "pull":
        cmd_pull(args)

    elif args.cmd == "mailbox-stats":
        cmd_mailbox_stats(args)

    elif args.cmd == "mailbox-health":
        cmd_mailbox_health(args)


if __name__ == "__main__":
    main()
