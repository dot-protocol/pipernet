"""
Shared plumbing for edge-intel pollers.

Each source script (bluesky_jetstream.py, github_trending.py,
producthunt_trending.py, gtrends.py) builds on this module:

    from _common import (
        OracleClient,
        SidecarWriter,
        oracle_token,
        configure_logging,
    )

OracleClient wraps the MCP JSON-RPC `oracle_ingest` call.
SidecarWriter is an append-only JSONL writer with size rotation.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ORACLE_BASE = os.getenv("ORACLE_BASE", "https://oracle.axxis.world")
ORACLE_MCP_PATH = os.getenv("ORACLE_MCP_PATH", "/oracle/mcp/")


def oracle_token() -> str:
    """Resolve the Oracle bearer token in priority order."""
    for var in ("ORACLE_TOKEN", "ORACLE_AUTH_TOKEN", "TREE_AUTH_TOKEN"):
        if t := os.getenv(var):
            return t
    mcp_path = Path.home() / ".mcp.json"
    if mcp_path.exists():
        try:
            cfg = json.loads(mcp_path.read_text())
            auth = (
                cfg.get("mcpServers", {})
                .get("oracle", {})
                .get("headers", {})
                .get("Authorization", "")
            )
            if auth.startswith("Bearer "):
                return auth[len("Bearer "):]
        except (json.JSONDecodeError, KeyError):
            pass
    for env_path in (
        Path.home() / "Movies" / "Kin" / "oracle_v3" / ".env",
        Path("/opt/tree/.env"),
    ):
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("ORACLE_AUTH_TOKEN="):
                    return line.split("=", 1)[1].strip()
    raise RuntimeError("Oracle token not found. Set ORACLE_TOKEN env var.")


def configure_logging(name: str, level: str = "INFO") -> logging.Logger:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )
    return logging.getLogger(name)


class OracleClient:
    """Thin wrapper over the Oracle MCP `oracle_ingest` tool call."""

    def __init__(self, source: str, user_agent: str = "pipernet-edge-intel/0.1") -> None:
        self.source = source
        self.ua = user_agent
        self._token = oracle_token()

    def ingest(self, items: list[dict[str, Any]], log: logging.Logger | None = None) -> dict[str, Any]:
        if not items:
            return {"skipped": "empty"}
        payload = {
            "jsonrpc": "2.0",
            "id": int(time.time() * 1000),
            "method": "tools/call",
            "params": {
                "name": "oracle_ingest",
                "arguments": {
                    "source": f"{self.source}-{datetime.now(timezone.utc).strftime('%Y%m%d')}",
                    "extracted": {"items": items},
                },
            },
        }
        req = Request(
            f"{ORACLE_BASE.rstrip('/')}{ORACLE_MCP_PATH}",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "User-Agent": f"{self.ua} (+https://piedpiper.fun)",
            },
            method="POST",
        )
        try:
            with urlopen(req, timeout=20) as resp:
                body = resp.read().decode("utf-8")
        except (URLError, HTTPError) as e:
            if log:
                log.warning("oracle ingest failed (%s)", e)
            raise
        for line in body.splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:].strip())
        return {"raw": body[:500]}


class SidecarWriter:
    """Append-only JSONL writer with size cap (oldest half is dropped on overflow)."""

    def __init__(self, path: str, max_bytes: int = 50 * 1024 * 1024) -> None:
        self.path = Path(path)
        self.max_bytes = max_bytes

    def write(self, record: dict[str, Any], log: logging.Logger | None = None) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists() and self.path.stat().st_size > self.max_bytes:
                data = self.path.read_bytes()
                mid = len(data) // 2
                cut = data.find(b"\n", mid)
                if cut > 0:
                    self.path.write_bytes(data[cut + 1:])
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as e:
            if log:
                log.warning("sidecar write failed (%s)", e)


def http_get_json(url: str, timeout: int = 20, user_agent: str = "pipernet-edge-intel/0.1") -> Any:
    req = Request(url, headers={"User-Agent": user_agent, "Accept": "application/json"})
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_get_text(url: str, timeout: int = 20, user_agent: str = "pipernet-edge-intel/0.1") -> str:
    req = Request(url, headers={"User-Agent": user_agent})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")
