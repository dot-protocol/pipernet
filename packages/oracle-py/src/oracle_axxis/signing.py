# SPDX-License-Identifier: Apache-2.0
# Part of oracle-axxis — https://github.com/dot-protocol/oracle-sdk-py

"""oracle_axxis.signing — ed25519 signing per signed-request-v0.1.

Implements the canonical-bytes assembly and Ed25519 signature scheme from
pipernet/spec/signed-request-v0.1.md. Header construction is here so client.py
can stay HTTP-shaped.

Canonical bytes layout (joined by b"\\n"):
    domain="pipernet-signed-v1"
    METHOD (uppercase)
    path (e.g. "/p/search")
    query_string (raw; empty string if none)
    sha256(body).hex()
    handle
    pubkey_b64
    timestamp (ISO-8601 UTC)
    nonce_b64
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import AuthError

# Constants from signed-request-v0.1.md
SIGNED_REQUEST_DOMAIN = b"pipernet-signed-v1"
HANDLE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
EMPTY_BODY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


class Keypair:
    """Ed25519 keypair holder.

    Loads from a JSON file or dict shaped as ``{"pubkey_hex": "...",
    "privkey_hex": "..."}``. Hex strings are 64 chars each (32 bytes).
    Handle is optional and used in the ``X-Pipernet-Handle`` header — if not
    provided, falls back to ``pk<first 16 hex chars of pubkey>``. Default
    handles conform to the ``^[a-z0-9][a-z0-9-]{0,63}$`` regex from
    signed-request-v0.1 §3.1.
    """

    def __init__(
        self,
        *,
        pubkey_hex: str,
        privkey_hex: str,
        handle: str | None = None,
    ) -> None:
        if len(pubkey_hex) != 64:
            raise AuthError(f"pubkey_hex must be 64 hex chars, got {len(pubkey_hex)}")
        if len(privkey_hex) != 64:
            raise AuthError(f"privkey_hex must be 64 hex chars, got {len(privkey_hex)}")
        self.pubkey_bytes = bytes.fromhex(pubkey_hex)
        self.privkey_seed = bytes.fromhex(privkey_hex)
        self.handle = handle or self._default_handle(pubkey_hex)
        if not HANDLE_RE.match(self.handle):
            raise AuthError(
                f"handle {self.handle!r} fails regex ^[a-z0-9][a-z0-9-]{{0,63}}$"
            )

    @staticmethod
    def _default_handle(pubkey_hex: str) -> str:
        # Per brief: "pk" + first 16 hex chars, lowercased. Conforms to
        # ^[a-z0-9][a-z0-9-]{0,63}$. No colon — colon violates the regex.
        return f"pk{pubkey_hex[:16].lower()}"

    @classmethod
    def load(cls, source: str | Path | dict[str, Any]) -> Keypair:
        """Load a keypair from a JSON file path or a dict."""
        if isinstance(source, (str, Path)):
            path = Path(source).expanduser()
            data = json.loads(path.read_text())
        elif isinstance(source, dict):
            data = source
        else:
            raise AuthError(
                f"keypair must be a path or dict, got {type(source).__name__}"
            )

        try:
            return cls(
                pubkey_hex=data["pubkey_hex"],
                privkey_hex=data["privkey_hex"],
                handle=data.get("handle"),
            )
        except KeyError as e:
            raise AuthError(f"keypair JSON missing field: {e}") from e

    @property
    def pubkey_b64(self) -> str:
        return base64.b64encode(self.pubkey_bytes).decode("ascii")

    def sign(self, message: bytes) -> bytes:
        """Sign ``message`` with the Ed25519 private key.

        Returns the 64-byte raw signature. Uses PyNaCl. We re-import inside
        the method so test environments can monkeypatch.
        """
        try:
            from nacl.signing import SigningKey  # type: ignore[import-untyped]
        except ImportError as e:  # pragma: no cover - dep is declared
            raise AuthError(
                "pynacl is required for signed-request auth; "
                "install oracle-axxis[signing] or `pip install pynacl`."
            ) from e

        signing_key = SigningKey(self.privkey_seed)
        signed = signing_key.sign(message)
        return signed.signature


def canonical_bytes(
    *,
    method: str,
    path: str,
    query_string: str,
    body: bytes,
    handle: str,
    pubkey_b64: str,
    timestamp: str,
    nonce_b64: str,
) -> bytes:
    """Build the canonical byte string for signing per signed-request-v0.1 §3.2.

    Lines are joined with single ``\\n``. An empty body still contributes its
    sha256 (e3b0c4...); an empty query string contributes an empty line.
    """
    body_hash = hashlib.sha256(body).hexdigest()
    lines = [
        SIGNED_REQUEST_DOMAIN.decode("ascii"),
        method.upper(),
        path,
        query_string,
        body_hash,
        handle,
        pubkey_b64,
        timestamp,
        nonce_b64,
    ]
    return "\n".join(lines).encode("utf-8")


def _now_iso_utc() -> str:
    """ISO-8601 UTC timestamp with second precision and trailing ``Z``."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _gen_nonce(num_bytes: int = 16) -> str:
    return base64.b64encode(os.urandom(num_bytes)).decode("ascii")


def sign_request(
    keypair: Keypair,
    *,
    method: str,
    path: str,
    query_string: str = "",
    body: bytes = b"",
    timestamp: str | None = None,
    nonce_b64: str | None = None,
) -> dict[str, str]:
    """Sign a request and return the five ``X-Pipernet-*`` headers.

    All header values are strings; the caller stuffs them into ``httpx.Request``
    headers. ``timestamp`` and ``nonce_b64`` are exposed for deterministic
    tests; in production both are generated fresh per call.
    """
    ts = timestamp or _now_iso_utc()
    nonce = nonce_b64 or _gen_nonce()

    cb = canonical_bytes(
        method=method,
        path=path,
        query_string=query_string,
        body=body,
        handle=keypair.handle,
        pubkey_b64=keypair.pubkey_b64,
        timestamp=ts,
        nonce_b64=nonce,
    )
    signature = keypair.sign(cb)
    sig_b64 = base64.b64encode(signature).decode("ascii")

    return {
        "X-Pipernet-Handle": keypair.handle,
        "X-Pipernet-Pubkey": keypair.pubkey_b64,
        "X-Pipernet-Timestamp": ts,
        "X-Pipernet-Nonce": nonce,
        "X-Pipernet-Signature": sig_b64,
    }
