"""
identity — Ed25519 keypair load/generate, sign, verify.

Uses the `cryptography` library (ships with pipernet's declared deps).
Keys are stored as raw 32-byte seeds (private) and 32-byte pubkeys (public),
written to disk in PEM format for human-readability and tool compatibility.

Key discovery priority for a given handle:
  1. PIPERNET_PRIVKEY env var (raw hex or PEM content)
  2. ~/KEY_DIR/<handle>.key  (PEM private key file, KEY_DIR = .pipernet)
  3. Generate a new keypair, write to ~/KEY_DIR/<handle>.key (chmod 600),
     and return the new key. Caller is responsible for announcing the pubkey.

Signing and verification operate over arbitrary bytes (typically the output
of canonical.canonicalize()).
"""
from __future__ import annotations

import os
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PrivateFormat,
    PublicFormat,
    NoEncryption,
    load_pem_private_key,
)

_KEY_DIR = Path.home() / ".pipernet"


def _key_path(handle: str) -> Path:
    """Return the canonical path for a handle's private key file."""
    return _KEY_DIR / f"{handle}.key"


def load_or_generate(handle: str) -> tuple[Ed25519PrivateKey, bytes, bool]:
    """Load an Ed25519 private key for handle, generating one if absent.

    Returns (private_key, pubkey_bytes, generated) where:
      - private_key: Ed25519PrivateKey usable for signing.
      - pubkey_bytes: raw 32-byte public key bytes.
      - generated: True if a new key was created (caller should announce pubkey).

    Key discovery order:
      1. PIPERNET_PRIVKEY env var (PEM or raw hex 64-char seed).
      2. ~/KEY_DIR/<handle>.key (PEM file).
      3. Generate, write to ~/KEY_DIR/<handle>.key (chmod 600).
    """
    env_val = os.getenv("PIPERNET_PRIVKEY")
    if env_val:
        priv = _parse_privkey_str(env_val)
        pub_bytes = _pubkey_bytes(priv)
        return priv, pub_bytes, False

    key_file = _key_path(handle)
    if key_file.exists():
        pem_data = key_file.read_bytes()
        priv = load_pem_private_key(pem_data, password=None)
        if not isinstance(priv, Ed25519PrivateKey):
            raise ValueError(f"Key at {key_file} is not an Ed25519 key")
        pub_bytes = _pubkey_bytes(priv)
        return priv, pub_bytes, False

    # Generate new keypair.
    priv = Ed25519PrivateKey.generate()
    _KEY_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    pem = priv.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    key_file.write_bytes(pem)
    key_file.chmod(0o600)
    pub_bytes = _pubkey_bytes(priv)
    return priv, pub_bytes, True


def load_pubkey(handle: str) -> bytes | None:
    """Return the raw 32-byte pubkey for handle, or None if no key exists.

    Only reads the public key — does not generate anything.
    """
    key_file = _key_path(handle)
    if not key_file.exists():
        return None
    pem_data = key_file.read_bytes()
    priv = load_pem_private_key(pem_data, password=None)
    if not isinstance(priv, Ed25519PrivateKey):
        return None
    return _pubkey_bytes(priv)


def sign(private_key: Ed25519PrivateKey, data: bytes) -> bytes:
    """Sign data with private_key. Returns 64-byte ed25519 signature bytes."""
    return private_key.sign(data)


def verify(pubkey_bytes: bytes, signature: bytes, data: bytes) -> bool:
    """Verify an ed25519 signature. Returns True on success, False on failure.

    pubkey_bytes: raw 32-byte public key.
    signature: 64-byte signature from sign().
    data: the bytes that were signed.
    """
    try:
        pub = Ed25519PublicKey.from_public_bytes(pubkey_bytes)
        pub.verify(signature, data)
        return True
    except Exception:
        return False


def pubkey_hex(pubkey_bytes: bytes) -> str:
    """Return the hex-encoded public key for display / announcement purposes."""
    return pubkey_bytes.hex()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _pubkey_bytes(priv: Ed25519PrivateKey) -> bytes:
    """Extract raw 32-byte public key from a private key object."""
    return priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def _parse_privkey_str(value: str) -> Ed25519PrivateKey:
    """Parse a private key from a PEM string or 64-char hex seed string."""
    value = value.strip()
    if value.startswith("-----BEGIN"):
        return load_pem_private_key(value.encode("utf-8"), password=None)
    # Treat as 64-char hex seed (raw 32 bytes).
    if len(value) == 64:
        try:
            raw = bytes.fromhex(value)
            return Ed25519PrivateKey.from_private_bytes(raw)
        except ValueError:
            pass
    raise ValueError(
        "PIPERNET_PRIVKEY must be a PEM private key or a 64-char hex seed string"
    )
