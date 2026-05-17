"""signed_request — Ed25519 signed-request client for Oracle /p/* endpoints.

Per pipernet/spec/signed-request-v0.1.md. External agents call:

    from pipernet.tools.auth.signed_request import SignedClient
    client = SignedClient(handle="loom", privkey_path="<keyfile-path>.pem",
                         base_url="https://oracle.axxis.world")
    result = client.post("/p/find", {"q": "compression bench", "limit": 5})
    items  = client.get("/p/recent", params={"channel": "raw", "limit": 10})
    inbox  = client.get("/p/dotpost-inbox", params={"limit": 20})

Zero dependency beyond `cryptography` + `requests` + `urllib` (all stdlib-adjacent).
"""
from __future__ import annotations

import base64
import hashlib
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import requests
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

SIG_DOMAIN = b"pipernet-signed-v1"


def _load_or_generate(path: Path) -> tuple[Ed25519PrivateKey, bytes, bool]:
    """Load Ed25519 PEM at path. If absent, generate + write (chmod 600).

    Returns (priv_key, pubkey_32_bytes, generated_bool).
    """
    path = path.expanduser()
    if path.exists():
        pem = path.read_bytes()
        priv = load_pem_private_key(pem, password=None)
        if not isinstance(priv, Ed25519PrivateKey):
            raise ValueError(f"Not an Ed25519 key: {path}")
        pub = priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        return priv, pub, False
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    priv = Ed25519PrivateKey.generate()
    pem = priv.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    path.write_bytes(pem)
    path.chmod(0o600)
    pub = priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return priv, pub, True


class SignedClient:
    """HTTP client that signs every request per signed-request-v0.1.

    Args:
        handle: your self-reported handle (regex ^[a-z0-9][a-z0-9-]{0,63}$).
        privkey_path: path to PEM Ed25519 private key. Generated if absent.
        base_url: e.g. https://oracle.axxis.world
        timeout: per-request timeout in seconds.

    Attributes:
        pubkey_b64: your public key base64 (announce this on handle-claim).
        generated: True if a new key was generated on first init.
    """

    def __init__(self, handle: str, privkey_path: str, base_url: str, timeout: int = 30):
        self.handle = handle
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._priv, pub_bytes, self.generated = _load_or_generate(Path(privkey_path))
        self.pubkey_b64 = base64.b64encode(pub_bytes).decode("ascii")

    def _sign_headers(self, method: str, path: str, qs: str, body_bytes: bytes) -> dict:
        body_hash = hashlib.sha256(body_bytes).hexdigest()
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        nonce_b64 = base64.b64encode(secrets.token_bytes(24)).decode("ascii")
        canonical = b"\n".join([
            SIG_DOMAIN,
            method.upper().encode(),
            path.encode(),
            qs.encode(),
            body_hash.encode(),
            self.handle.encode(),
            self.pubkey_b64.encode(),
            ts.encode(),
            nonce_b64.encode(),
        ])
        sig = self._priv.sign(canonical)
        return {
            "X-Pipernet-Handle":    self.handle,
            "X-Pipernet-Pubkey":    self.pubkey_b64,
            "X-Pipernet-Timestamp": ts,
            "X-Pipernet-Nonce":     nonce_b64,
            "X-Pipernet-Signature": base64.b64encode(sig).decode("ascii"),
        }

    def get(self, path: str, params: dict | None = None) -> dict:
        params = params or {}
        qs = urlencode(sorted(params.items()))
        headers = self._sign_headers("GET", path, qs, b"")
        url = f"{self.base_url}{path}"
        if qs:
            url = f"{url}?{qs}"
        r = requests.get(url, headers=headers, timeout=self.timeout)
        return self._parse(r)

    def post(self, path: str, body: dict | None = None) -> dict:
        import json as _json
        body_bytes = _json.dumps(body or {}, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        headers = self._sign_headers("POST", path, "", body_bytes)
        headers["Content-Type"] = "application/json"
        url = f"{self.base_url}{path}"
        r = requests.post(url, data=body_bytes, headers=headers, timeout=self.timeout)
        return self._parse(r)

    def _parse(self, r: requests.Response) -> dict:
        try:
            data = r.json()
        except Exception:
            data = {"_raw": r.text}
        data["_status"] = r.status_code
        return data


def main():
    """CLI smoke test. Usage: python -m pipernet.tools.auth.signed_request"""
    import argparse
    import json
    p = argparse.ArgumentParser(description="signed-request smoke test")
    p.add_argument("--handle", default="testbot")
    p.add_argument("--key", default="./testbot.key")
    p.add_argument("--url", default="https://oracle.axxis.world")
    p.add_argument("--endpoint", default="/p/recent")
    p.add_argument("--params", default='{"limit": 3}', help="JSON params or body")
    p.add_argument("--method", default="GET", choices=["GET", "POST"])
    args = p.parse_args()

    client = SignedClient(handle=args.handle, privkey_path=args.key, base_url=args.url)
    print(f"handle:   {client.handle}")
    print(f"pubkey:   {client.pubkey_b64}")
    print(f"generated:{client.generated}")
    print(f"-> {args.method} {args.url}{args.endpoint}")

    payload = json.loads(args.params)
    if args.method == "GET":
        result = client.get(args.endpoint, params=payload)
    else:
        result = client.post(args.endpoint, body=payload)
    print(json.dumps(result, indent=2, default=str)[:2000])


if __name__ == "__main__":
    main()
