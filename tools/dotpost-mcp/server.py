#!/usr/bin/env python3
"""
DOTpost MCP Server — agent-to-agent async messaging via SSH proxy to VPS.

Exposes 4 tools:
  dotpost_inbox         — list incoming messages
  dotpost_send          — send a message
  dotpost_read          — read a thread (+ marks as read)
  dotpost_known_agents  — list mesh agent handles
"""

import json
import os
import subprocess
from typing import Any

from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Config (env overrides)
# ---------------------------------------------------------------------------

AGENT_HANDLE = os.environ.get("DOTPOST_AGENT_HANDLE", "rocky-claude-code")
TRANSPORT = os.environ.get("DOTPOST_TRANSPORT", "ssh")        # "ssh" | "https"
SSH_HOST = os.environ.get("DOTPOST_SSH_HOST", "adrian")
HTTPS_URL = os.environ.get("DOTPOST_HTTPS_URL", "")
AUTH_TOKEN = os.environ.get("DOTPOST_AUTH_TOKEN", "")
DOTPOST_BASE = "http://localhost:4060"  # VPS-local address

KNOWN_AGENTS = [
    {"handle": "rocky-claude-code", "device": "MacBook Pro (Kin-1)", "role": "Builder / orchestrator"},
    {"handle": "jared-claude-ai",   "device": "iPhone Claude AI (Kin-2)", "role": "Strategist / scrum master"},
    {"handle": "loom",              "device": "Lenovo RTX3050 (Kin-3)", "role": "Weaver / engineer"},
]

# ---------------------------------------------------------------------------
# Transport helpers
# ---------------------------------------------------------------------------

def _ssh_curl(method: str, path: str, body: dict | None = None) -> Any:
    """Run a curl command on the VPS via SSH and return parsed JSON."""
    url = f"{DOTPOST_BASE}{path}"
    cmd_parts = ["ssh", "-o", "ConnectTimeout=10", SSH_HOST,
                 "curl", "-sS", "--max-time", "15"]
    if method.upper() == "POST":
        cmd_parts += ["-X", "POST", "-H", "Content-Type: application/json"]
        if body is not None:
            cmd_parts += ["-d", json.dumps(body)]
    cmd_parts.append(url)

    result = subprocess.run(cmd_parts, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"SSH/curl failed: {result.stderr.strip()}")
    raw = result.stdout.strip()
    if not raw:
        return {}
    return json.loads(raw)


def _https_curl(method: str, path: str, body: dict | None = None) -> Any:
    """Hit the public HTTPS relay directly."""
    import urllib.request
    url = f"{HTTPS_URL.rstrip('/')}{path}"
    headers = {"Content-Type": "application/json"}
    if AUTH_TOKEN:
        headers["Authorization"] = f"Bearer {AUTH_TOKEN}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def _call(method: str, path: str, body: dict | None = None) -> Any:
    if TRANSPORT == "https":
        return _https_curl(method, path, body)
    return _ssh_curl(method, path, body)


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

mcp = FastMCP("dotpost")


@mcp.tool()
def dotpost_inbox(unread_only: bool = False, limit: int = 20) -> list[dict]:
    """
    List incoming DOTpost messages for the configured agent.

    Returns an array of message summaries sorted newest-first.
    """
    path = f"/dotpost/inbox?agent={AGENT_HANDLE}&limit={limit}"
    if unread_only:
        path += "&unread_only=true"

    data = _call("GET", path)
    messages = data.get("messages", data) if isinstance(data, dict) else data

    # Normalise to a compact summary list
    result = []
    for m in messages[:limit]:
        result.append({
            "id": m.get("id"),
            "from_agent": m.get("from_agent"),
            "subject": m.get("subject"),
            "timestamp": m.get("timestamp"),
            "read": m.get("read", False),
            "thread_size": m.get("thread_size", 1),
        })
    return result


@mcp.tool()
def dotpost_send(
    to_agent: str,
    subject: str,
    body: str,
    priority: str = "normal",
) -> dict:
    """
    Send a DOTpost message to another mesh agent.

    priority: "low" | "normal" | "high"
    Known agent handles: rocky-claude-code, jared-claude-ai, loom
    """
    payload = {
        "from_agent": AGENT_HANDLE,
        "to_agent": to_agent,
        "subject": subject,
        "body": body,
        "priority": priority,
    }
    result = _call("POST", "/dotpost/send", payload)
    return result


@mcp.tool()
def dotpost_read(message_id: str) -> dict:
    """
    Read a full message thread by ID and mark it as read.

    Returns the thread content including all messages in the thread.
    """
    # Fetch thread content
    thread = _call("GET", f"/dotpost/thread/{message_id}")

    # Mark as read (best-effort — ignore errors)
    try:
        _call("POST", f"/dotpost/read/{message_id}")
    except Exception:
        pass

    return thread


@mcp.tool()
def dotpost_known_agents() -> list[dict]:
    """
    List known mesh agent handles and their device/role.

    Returns a static registry (v0). Each entry: handle, device, role.
    """
    return KNOWN_AGENTS


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
