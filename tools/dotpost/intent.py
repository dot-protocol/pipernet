"""
intent — Intent and Resolve dataclasses matching the intent-substrate-v0.1 spec.

These are pure data + crypto structures. No I/O, no Oracle calls.

Intent: describes what a sender wants, under what constraints, with what values.
Resolve: records whether a resolver honored a stated intent, and what was delivered.

Both types produce canonical bytes (for signing/verification) via
to_canonical_bytes(), and support sign() / verify() methods for the
ed25519 substrate defined in identity.py.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .canonical import canonicalize
from .compression import compress, decompress
from .identity import sign, verify


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _b64url_encode(data: bytes) -> str:
    """Return URL-safe base64 encoding of data, without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    """Decode a URL-safe base64 string (padding optional)."""
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)


def _utcnow_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Intent
# ---------------------------------------------------------------------------

@dataclass
class Intent:
    """Represents a signed intent per the intent-substrate-v0.1 spec.

    Required fields:
      what: concise human-readable statement of the desired outcome.

    Optional fields follow the spec schema exactly. refuse_substitution
    defaults to True (Tesla's law).
    """

    what: str
    v: str = "1"
    constraints: dict[str, Any] = field(default_factory=dict)
    values: list[str] = field(default_factory=list)
    refuse_substitution: bool = True
    addressed_to: str = "all"
    expires_at: str | None = None
    context_refs: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate required fields on construction."""
        if not self.what or not self.what.strip():
            raise ValueError("Intent.what is required and must be non-empty")
        if self.v != "1":
            raise ValueError(f"Intent.v must be '1'; got {self.v!r}")
        if self.expires_at is not None:
            _validate_iso8601(self.expires_at)

    def to_dict(self) -> dict[str, Any]:
        """Return the full intent as a plain dict suitable for JSON serialization."""
        obj: dict[str, Any] = {
            "v": self.v,
            "what": self.what,
            "refuse_substitution": self.refuse_substitution,
            "addressed_to": self.addressed_to,
        }
        if self.constraints:
            obj["constraints"] = self.constraints
        if self.values:
            obj["values"] = self.values
        if self.expires_at:
            obj["expires_at"] = self.expires_at
        if self.context_refs:
            obj["context_refs"] = self.context_refs
        return obj

    def to_canonical_bytes(self) -> bytes:
        """Return the RFC 8785-subset canonical JSON encoding.

        This is the payload that ed25519 signs/verifies.
        Two Intent instances with identical fields produce identical bytes.
        """
        return canonicalize(self.to_dict())

    def sign(self, private_key: Ed25519PrivateKey) -> tuple[str, str]:
        """Sign this intent with private_key.

        Returns (intent_b64, sig_b64) where:
          - intent_b64: base64url-encoded canonical JSON bytes (the payload tag).
          - sig_b64: base64url-encoded 64-byte ed25519 signature.
        """
        canonical = self.to_canonical_bytes()
        sig_bytes = sign(private_key, canonical)
        return _b64url_encode(canonical), _b64url_encode(sig_bytes)

    def verify(self, pubkey_bytes: bytes, intent_b64: str, sig_b64: str) -> bool:
        """Verify a previously computed (intent_b64, sig_b64) pair.

        Returns True if the signature is valid for this intent and pubkey.
        """
        try:
            canonical = _b64url_decode(intent_b64)
            sig = _b64url_decode(sig_b64)
            # Canonical bytes must also match what this object produces.
            if canonical != self.to_canonical_bytes():
                return False
            return verify(pubkey_bytes, sig, canonical)
        except Exception:
            return False

    @classmethod
    def from_b64(cls, intent_b64: str) -> "Intent":
        """Reconstruct an Intent from its base64url-encoded canonical JSON form.

        Raises ValueError if the bytes cannot be decoded to a valid Intent.
        """
        import json
        try:
            raw = _b64url_decode(intent_b64)
            data = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise ValueError(f"Cannot decode intent_b64: {exc}") from exc
        return cls(
            v=data.get("v", "1"),
            what=data["what"],
            constraints=data.get("constraints", {}),
            values=data.get("values", []),
            refuse_substitution=data.get("refuse_substitution", True),
            addressed_to=data.get("addressed_to", "all"),
            expires_at=data.get("expires_at"),
            context_refs=data.get("context_refs", []),
        )

    # ------------------------------------------------------------------
    # v0.5.0 compressed wire format (sign-then-compress)
    # ------------------------------------------------------------------

    def to_compressed_b64(self, private_key: Ed25519PrivateKey) -> tuple[str, str]:
        """Sign and compress this intent for the v0.5.0 wire format.

        Signature is over the *canonical JSON bytes*, not the compressed bytes.
        Compression is transport-only.

        Returns:
            (compressed_b64, sig_b64) where:
              - compressed_b64: base64url(zstd(canonical_json)) — the intent_z: tag value.
              - sig_b64: base64url(ed25519_sig_over_canonical) — same sig as .sign().
        """
        canonical = self.to_canonical_bytes()
        sig_bytes = sign(private_key, canonical)
        return _b64url_encode(compress(canonical)), _b64url_encode(sig_bytes)

    @classmethod
    def from_compressed_b64(cls, compressed_b64: str) -> "Intent":
        """Reconstruct an Intent from its compressed base64url form (intent_z: tag).

        Raises ValueError if the bytes cannot be decoded or decompressed.
        """
        import json
        try:
            raw = decompress(_b64url_decode(compressed_b64))
            data = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise ValueError(f"Cannot decode compressed intent: {exc}") from exc
        return cls(
            v=data.get("v", "1"),
            what=data["what"],
            constraints=data.get("constraints", {}),
            values=data.get("values", []),
            refuse_substitution=data.get("refuse_substitution", True),
            addressed_to=data.get("addressed_to", "all"),
            expires_at=data.get("expires_at"),
            context_refs=data.get("context_refs", []),
        )

    @classmethod
    def verify_compressed(
        cls,
        compressed_b64: str,
        sig_b64: str,
        pubkey_bytes: bytes,
    ) -> bool:
        """Verify a v0.5.0 compressed intent tag pair.

        Decompresses the canonical JSON, then verifies the signature against
        those decompressed bytes.  The signature is over canonical JSON, not
        over the compressed form.

        Returns True if the signature is valid; False on any failure.
        """
        try:
            canonical = decompress(_b64url_decode(compressed_b64))
            sig = _b64url_decode(sig_b64)
            return verify(pubkey_bytes, sig, canonical)
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Resolve
# ---------------------------------------------------------------------------

HONORED_VALUES = frozenset({"true", "false", "partial"})


@dataclass
class Resolve:
    """Represents a signed resolve record per the intent-substrate-v0.1 spec.

    Required fields: intent_id, honored, resolver, resolved_at.
    honored must be one of True (bool), False (bool), or "partial" (str).
    deviation is required when honored is not True.
    """

    intent_id: str
    honored: bool | str               # True, False, or "partial"
    resolver: str
    resolved_at: str = field(default_factory=_utcnow_iso)
    v: str = "1"
    delivery: dict[str, Any] = field(
        default_factory=lambda: {"observation": None, "blob": None, "url": None}
    )
    deviation: str | None = None

    def __post_init__(self) -> None:
        """Validate required fields and cross-field constraints."""
        if not self.intent_id:
            raise ValueError("Resolve.intent_id is required")
        if not self.resolver:
            raise ValueError("Resolve.resolver is required")
        if self.v != "1":
            raise ValueError(f"Resolve.v must be '1'; got {self.v!r}")
        _validate_iso8601(self.resolved_at)

        honored_norm = str(self.honored).lower()
        if honored_norm not in HONORED_VALUES:
            raise ValueError(
                f"Resolve.honored must be True, False, or 'partial'; got {self.honored!r}"
            )
        if honored_norm in ("false", "partial") and not self.deviation:
            raise ValueError(
                "Resolve.deviation is required when honored is False or 'partial'"
            )

    def to_dict(self) -> dict[str, Any]:
        """Return the full resolve as a plain dict suitable for JSON serialization."""
        honored_val: Any = self.honored
        if isinstance(self.honored, bool):
            honored_val = self.honored
        else:
            honored_val = str(self.honored).lower()
            if honored_val == "true":
                honored_val = True
            elif honored_val == "false":
                honored_val = False
            # else keep as string "partial"

        return {
            "v": self.v,
            "intent_id": self.intent_id,
            "honored": honored_val,
            "delivery": self.delivery,
            "deviation": self.deviation,
            "resolved_at": self.resolved_at,
            "resolver": self.resolver,
        }

    def to_canonical_bytes(self) -> bytes:
        """Return the RFC 8785-subset canonical JSON encoding for signing."""
        return canonicalize(self.to_dict())

    def sign(self, private_key: Ed25519PrivateKey) -> tuple[str, str]:
        """Sign this resolve with private_key.

        Returns (resolve_b64, sig_b64) — the pair stored as tags on the
        dotpost observation.
        """
        canonical = self.to_canonical_bytes()
        sig_bytes = sign(private_key, canonical)
        return _b64url_encode(canonical), _b64url_encode(sig_bytes)

    def verify(self, pubkey_bytes: bytes, resolve_b64: str, sig_b64: str) -> bool:
        """Verify a previously computed (resolve_b64, sig_b64) pair.

        Returns True if the signature is valid.
        """
        try:
            canonical = _b64url_decode(resolve_b64)
            sig = _b64url_decode(sig_b64)
            if canonical != self.to_canonical_bytes():
                return False
            return verify(pubkey_bytes, sig, canonical)
        except Exception:
            return False

    # ------------------------------------------------------------------
    # v0.5.0 compressed wire format (sign-then-compress)
    # ------------------------------------------------------------------

    def to_compressed_b64(self, private_key: Ed25519PrivateKey) -> tuple[str, str]:
        """Sign and compress this resolve for the v0.5.0 wire format.

        Signature is over the *canonical JSON bytes*, not the compressed bytes.

        Returns:
            (compressed_b64, sig_b64) where:
              - compressed_b64: base64url(zstd(canonical_json)) — the resolve_z: tag value.
              - sig_b64: base64url(ed25519_sig_over_canonical).
        """
        canonical = self.to_canonical_bytes()
        sig_bytes = sign(private_key, canonical)
        return _b64url_encode(compress(canonical)), _b64url_encode(sig_bytes)

    @classmethod
    def from_compressed_b64(cls, compressed_b64: str) -> "Resolve":
        """Reconstruct a Resolve from its compressed base64url form (resolve_z: tag).

        Raises ValueError if the bytes cannot be decoded or decompressed.
        """
        import json
        try:
            raw = decompress(_b64url_decode(compressed_b64))
            data = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise ValueError(f"Cannot decode compressed resolve: {exc}") from exc
        return cls(
            v=data.get("v", "1"),
            intent_id=data["intent_id"],
            honored=data["honored"],
            resolver=data["resolver"],
            resolved_at=data.get("resolved_at", _utcnow_iso()),
            delivery=data.get("delivery", {"observation": None, "blob": None, "url": None}),
            deviation=data.get("deviation"),
        )

    @classmethod
    def verify_compressed(
        cls,
        compressed_b64: str,
        sig_b64: str,
        pubkey_bytes: bytes,
    ) -> bool:
        """Verify a v0.5.0 compressed resolve tag pair.

        Decompresses the canonical JSON, then verifies the signature against
        those decompressed bytes.

        Returns True if the signature is valid; False on any failure.
        """
        try:
            canonical = decompress(_b64url_decode(compressed_b64))
            sig = _b64url_decode(sig_b64)
            return verify(pubkey_bytes, sig, canonical)
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _validate_iso8601(value: str) -> None:
    """Raise ValueError if value is not a parseable ISO 8601 datetime string."""
    try:
        # Accept both Z suffix and +00:00 offset forms.
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(
            f"Expected ISO 8601 datetime string (e.g. 2026-05-19T00:00:00Z), got: {value!r}"
        )
