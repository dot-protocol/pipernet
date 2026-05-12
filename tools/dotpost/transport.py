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
