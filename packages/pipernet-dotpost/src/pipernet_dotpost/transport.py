"""
transport — Oracle MCP JSON-RPC transport layer.

Handles:
  - Token discovery (env vars → ~/.mcp.json → oracle_v3/.env)
  - MCP JSON-RPC POST with SSE-unwrapping
  - Cloudflare User-Agent workaround
  - oracle_ingest / oracle_query convenience wrappers

Pure transport: no business logic, no tag construction, no signing.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

ORACLE_BASE = os.getenv("ORACLE_BASE", "https://oracle.axxis.world")
ORACLE_MCP_PATH = os.getenv("ORACLE_MCP_PATH", "/oracle/mcp/")

# Exported so callers can reference it directly if needed.
BROADCAST_HANDLE = "all"


def load_token() -> str:
    """Return the Oracle bearer token, searching in priority order.

    Priority:
      1. ORACLE_TOKEN env var
      2. ORACLE_AUTH_TOKEN env var
      3. TREE_AUTH_TOKEN env var
      4. ~/.mcp.json mcpServers.oracle.headers.Authorization
      5. oracle_v3/.env ORACLE_AUTH_TOKEN line

    Raises RuntimeError if no token is found anywhere.
    """
    for env_var in ("ORACLE_TOKEN", "ORACLE_AUTH_TOKEN", "TREE_AUTH_TOKEN"):
        if t := os.getenv(env_var):
            return t

    mcp_path = Path.home() / ".mcp.json"
    if mcp_path.exists():
        try:
            cfg = json.loads(mcp_path.read_text())
            oracle_cfg = cfg.get("mcpServers", {}).get("oracle", {})
            auth = oracle_cfg.get("headers", {}).get("Authorization", "")
            if auth.startswith("Bearer "):
                return auth[len("Bearer "):]
        except (json.JSONDecodeError, KeyError):
            pass

    # Walk up from this file to find the repo root, then look for oracle_v3/.env.
    # Avoids hardcoded absolute user paths.
    _this = Path(__file__).resolve()
    candidates = [
        _this.parent.parent.parent.parent / "oracle_v3" / ".env",
        Path.home() / "Movies" / "Kin" / "oracle_v3" / ".env",
    ]
    for env_path in candidates:
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("ORACLE_AUTH_TOKEN="):
                    return line.split("=", 1)[1].strip()

    raise RuntimeError(
        "Oracle token not found. Set ORACLE_TOKEN env var or check ~/.mcp.json"
    )


def mcp_call(method: str, params: dict) -> dict:
    """Make a single MCP JSON-RPC 2.0 POST request and return the parsed data dict.

    MCP responses arrive as SSE-style lines: `data: <json>`.
    This function reads the first `data:` line and returns its parsed content.

    Raises RuntimeError on HTTP errors or unexpected response format.
    """
    payload = {
        "jsonrpc": "2.0",
        "id": int(time.time() * 1000),
        "method": method,
        "params": params,
    }
    req = Request(
        f"{ORACLE_BASE.rstrip('/')}{ORACLE_MCP_PATH}",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {load_token()}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            # Cloudflare blocks Python's default User-Agent — use a custom one.
            "User-Agent": "pipernet-dotpost/0.4 (+https://piedpiper.fun)",
        },
        method="POST",
    )
    with urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8")

    for line in body.splitlines():
        if line.startswith("data:"):
            return json.loads(line[5:].strip())
    raise RuntimeError(f"unexpected MCP response: {body[:300]}")


def dotpost_inbox(handle: str, *, include_broadcasts: bool = True,
                  include_mentions: bool = True, limit: int = 50,
                  since: str | None = None) -> dict:
    """Fetch dotposts addressed to <handle> via the tag-indexed endpoint.

    Replaces the text-CONTAINS oracle_query path that powered fetch_inbox()
    historically (state.md blocker #10). The /dotpost-inbox endpoint on
    tree_serve does a proper Cypher `WHERE 'dotpost' IN o.tags` query and
    returns structured rows with from/to/body/kind already split out.

    Returns the raw JSON: { ok, agent, count, messages: [...] }.
    Raises RuntimeError on HTTP errors or bad responses.
    """
    qs = [f"agent={handle}", f"limit={int(limit)}"]
    if include_broadcasts: qs.append("include_broadcasts=true")
    else:                  qs.append("include_broadcasts=false")
    if include_mentions:   qs.append("include_mentions=true")
    else:                  qs.append("include_mentions=false")
    if since:              qs.append(f"since={since}")
    url = f"{ORACLE_BASE.rstrip('/')}/dotpost-inbox?{'&'.join(qs)}"
    req = Request(
        url,
        headers={
            "Authorization": f"Bearer {load_token()}",
            "Accept":        "application/json",
            "User-Agent":    "pipernet-dotpost/0.5 (+https://piedpiper.fun)",
        },
        method="GET",
    )
    try:
        with urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8")
    except HTTPError as e:
        raise RuntimeError(f"dotpost-inbox HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")
    except URLError as e:
        raise RuntimeError(f"dotpost-inbox network error: {e.reason}")
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        raise RuntimeError(f"dotpost-inbox: not JSON: {body[:300]}")


# ─── signed-request (keyless) transport ─────────────────────────────────
#
# The public write/read surface. No bearer token; auth is the Ed25519
# signature on the request itself. Each function builds a SignedClient
# from the local keyring file for `handle`.
#
# These exist because the project's onboarding doctrine says "your
# keypair is your only credential" — but the original transport used
# tool_call("oracle_ingest", ...) which goes through MCP/bearer. These
# helpers move the package onto /p/* endpoints so onboarding requires
# zero platform-issued secrets.

def _make_signed_client(handle: str, timeout: int = 30):
    """Construct a SignedClient bound to `handle`'s local keyring file."""
    from .signed_request import SignedClient
    from .identity import _KEY_DIR
    base = os.getenv("ORACLE_BASE", "https://oracle.axxis.world")
    key_path = str(_KEY_DIR / f"{handle}.key")
    return SignedClient(
        handle=handle,
        privkey_path=key_path,
        base_url=base,
        timeout=timeout,
    )


def signed_ingest(handle: str, payload: dict, timeout: int = 30) -> dict:
    """POST to Oracle /p/ingest using the handle's keypair as the only auth.

    `payload` mirrors the oracle_ingest MCP tool shape:
        {"source": str, "extracted": {"items": [{"content","type","channel","tags":[...]}]}}

    Returns the parsed JSON response (typically {"status":"ok", "obs_id":..., "report":...}).
    Raises RuntimeError on HTTP errors.
    """
    client = _make_signed_client(handle, timeout=timeout)
    return client.post("/p/ingest", payload)


def signed_dotpost_inbox(handle: str, limit: int = 20,
                          include_broadcasts: bool = True,
                          since: str = None) -> dict:
    """GET /p/dotpost-inbox using the handle's keypair as auth (no bearer)."""
    client = _make_signed_client(handle, timeout=20)
    params = {
        "agent": handle,
        "limit": int(limit),
        "include_broadcasts": "true" if include_broadcasts else "false",
    }
    if since:
        params["since"] = since
    return client.get("/p/dotpost-inbox", params=params)


def tool_call(tool_name: str, args: dict) -> dict:
    """Call a named Oracle MCP tool with the given arguments dict.

    Returns the parsed result as a dict. If the tool returns a JSON-string
    text field, it is parsed automatically. Non-JSON text is wrapped as
    {"text": <str>}. Empty content returns {}.

    Raises RuntimeError if Oracle returns an error object.
    """
    resp = mcp_call("tools/call", {"name": tool_name, "arguments": args})
    if "error" in resp:
        raise RuntimeError(f"oracle error: {resp['error']}")
    content = resp.get("result", {}).get("content", [])
    if not content:
        return {}
    text = content[0].get("text", "")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"text": text}
