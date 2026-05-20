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
import email.utils
import hashlib
import logging
import os
import secrets
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlencode

import requests

_log = logging.getLogger(__name__)
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

    def __init__(self, handle: str, privkey_path: str, base_url: str, timeout: int = 120):
        self.handle = handle
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._priv, pub_bytes, self.generated = _load_or_generate(Path(privkey_path))
        self.pubkey_b64 = base64.b64encode(pub_bytes).decode("ascii")

    @classmethod
    def from_seed_hex(cls, handle: str, seed_hex: str, base_url: str, timeout: int = 120) -> "SignedClient":
        """Build a SignedClient from a 64-char hex seed without touching disk.

        Useful for rotation: the NEW keypair must sign the /p/ingest request
        proving control, but isn't on disk until the rotation succeeds.
        """
        self = cls.__new__(cls)
        self.handle = handle
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._priv = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(seed_hex))
        pub_bytes = self._priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        self.pubkey_b64 = base64.b64encode(pub_bytes).decode("ascii")
        self.generated = False
        return self

    # Process-wide cache: offset (server_time - local_time) in seconds.
    # Set on first sign attempt when PIPERNET_TIME_SYNC_URL is configured.
    _time_offset: "timedelta | None" = None

    @classmethod
    def _resolve_time_offset(cls) -> timedelta:
        """Return the local-clock offset to use when stamping signed requests.

        If PIPERNET_TIME_SYNC_URL env var is set, fetch that URL once
        per process and use its HTTP `Date:` header (RFC 7231 mandates
        every response carries one). This lets clients on machines with
        broken/disabled NTP still sign within the server's 300s window
        without touching the system clock.

        If the env var is unset or the fetch fails, returns zero offset
        and the client falls back to the local clock — same as before.
        """
        if cls._time_offset is not None:
            return cls._time_offset

        sync_url = os.environ.get("PIPERNET_TIME_SYNC_URL", "").strip()
        if not sync_url:
            cls._time_offset = timedelta(0)
            return cls._time_offset

        try:
            req = urllib.request.Request(
                sync_url,
                headers={"User-Agent": "pipernet-dotpost-clock-sync/0.2"},
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                date_hdr = r.headers.get("Date")
            if not date_hdr:
                raise RuntimeError(f"no Date header from {sync_url}")
            server_dt = email.utils.parsedate_to_datetime(date_hdr)
            local_dt = datetime.now(timezone.utc)
            offset = server_dt - local_dt
            cls._time_offset = offset
            if abs(offset.total_seconds()) > 60:
                _log.info(
                    "PIPERNET_TIME_SYNC: applying %+.0fs offset (local clock drift)",
                    offset.total_seconds(),
                )
            return offset
        except Exception as e:
            _log.warning("PIPERNET_TIME_SYNC fetch failed (%s); using local clock", e)
            cls._time_offset = timedelta(0)
            return cls._time_offset

    def _sign_headers(self, method: str, path: str, qs: str, body_bytes: bytes) -> dict:
        body_hash = hashlib.sha256(body_bytes).hexdigest()
        # Use server-synced time if PIPERNET_TIME_SYNC_URL is set (cached
        # offset). Falls back to local clock if not configured or fetch
        # failed. Replay window on the server is 300s.
        offset = self._resolve_time_offset()
        ts = (datetime.now(timezone.utc) + offset).strftime("%Y-%m-%dT%H:%M:%SZ")
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

    def post_stream(self, path: str, body: dict | None = None):
        """POST with streaming SSE response.

        Yields parsed SSE events as dicts: {"event": "context"|"token"|"done"|"error",
        "data": <parsed-json or raw string>}.

        Usage:
            for ev in client.post_stream("/p/ask", {"question": "...", "stream": True}):
                if ev["event"] == "token":
                    print(ev["data"]["text"], end="", flush=True)
                elif ev["event"] == "done":
                    citations = ev["data"]["citations"]

        The signature covers the body exactly as if it were a non-streaming POST;
        the only difference is response handling.
        """
        import json as _json
        body_bytes = _json.dumps(body or {}, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        headers = self._sign_headers("POST", path, "", body_bytes)
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "text/event-stream"
        url = f"{self.base_url}{path}"
        with requests.post(url, data=body_bytes, headers=headers,
                           timeout=self.timeout, stream=True) as r:
            event = None
            data_buf = []
            for raw_line in r.iter_lines(decode_unicode=True):
                if raw_line is None:
                    continue
                # Blank line = event boundary
                if raw_line == "":
                    if event is not None:
                        data_str = "\n".join(data_buf)
                        try: data = _json.loads(data_str)
                        except Exception: data = {"raw": data_str}
                        yield {"event": event, "data": data}
                    event = None
                    data_buf = []
                    continue
                if raw_line.startswith("event:"):
                    event = raw_line[6:].strip()
                elif raw_line.startswith("data:"):
                    data_buf.append(raw_line[5:].strip())

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
