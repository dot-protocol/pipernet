"""
bluesky_jetstream — first edge-intel signal source.

Streams the Bluesky AT Protocol Jetstream firehose (no auth, no key,
public service), filters posts by a configurable keyword list, and
ingests matches into Oracle as observations on the `edge-intel` channel.

Why this exists
---------------
The next internet needs awareness. We are the agent OS for the people
building it — so we have to see what they are saying before the rest
of the timeline does. Jetstream is a free, low-latency window onto
public conversation. Filter once, store the signal, feed Oracle.

Wire
----
    wss://jetstream2.us-east.bsky.network/subscribe
        ?wantedCollections=app.bsky.feed.post

Each frame is JSON:
    {
      "did": "did:plc:...",
      "time_us": 1715537261000,
      "commit": {
        "operation": "create",
        "collection": "app.bsky.feed.post",
        "record": { "text": "...", "createdAt": "...", "langs": ["en"] }
      }
    }

We care about: commit.operation == "create" and matching keyword.

Run
---
    python3 bluesky_jetstream.py                 # default keywords
    python3 bluesky_jetstream.py --keywords-file kw.txt
    python3 bluesky_jetstream.py --dry-run       # log matches, no ingest

Deploy
------
    pm2 start bluesky_jetstream.py \
        --name edge-bluesky \
        --interpreter python3 \
        --time

Dependencies
------------
    pip install websockets   # only one extra dep

License: Apache-2.0
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    import websockets
except ImportError:
    print("ERROR: websockets not installed. Run: pip install websockets", file=sys.stderr)
    sys.exit(2)


# --- Oracle plumbing (mirrors pipernet/tools/dotpost/main.py) ---

ORACLE_BASE = os.getenv("ORACLE_BASE", "https://oracle.axxis.world")
ORACLE_MCP_PATH = os.getenv("ORACLE_MCP_PATH", "/oracle/mcp/")
JETSTREAM_URL = os.getenv(
    "BLUESKY_JETSTREAM_URL",
    "wss://jetstream2.us-east.bsky.network/subscribe?wantedCollections=app.bsky.feed.post",
)
# Sidecar feed file for Mission Control UI (decouples /edge view from Oracle MCP).
# JSONL append-only, one match per line. Mission Control tails the last N lines.
SIDECAR_PATH = os.getenv("EDGE_INTEL_SIDECAR", "/var/lib/edge-intel/bluesky.jsonl")
SIDECAR_MAX_BYTES = int(os.getenv("EDGE_INTEL_SIDECAR_MAX_BYTES", str(50 * 1024 * 1024)))  # 50 MB

DEFAULT_KEYWORDS = [
    # Pied Piper / Pipernet / DOT
    "pied piper", "piedpiper", "$piper", "pipernet", "dot protocol",
    # AXXIS / Access OS
    "axxis.world", "access os",
    # Decentralized web themes we want to surface
    "decentralized ai", "decentralized agents", "agentic web",
    "agent mesh", "ai mesh", "swarm agents",
    "at protocol", "atproto", "open social",
    # Compression (canonical Pied Piper meme)
    "compression algorithm", "weissman score",
    # Memetic competitors / fellow travelers
    "polymarket", "kalshi", "metaculus",
    # Voices we want to hear
    "vitalik", "balajis", "naval ravikant",
]


def _oracle_token() -> str:
    """Resolve the Oracle bearer token in priority order."""
    for var in ("ORACLE_TOKEN", "ORACLE_AUTH_TOKEN", "TREE_AUTH_TOKEN"):
        if t := os.getenv(var):
            return t
    mcp_path = Path.home() / ".mcp.json"
    if mcp_path.exists():
        try:
            cfg = json.loads(mcp_path.read_text())
            auth = cfg.get("mcpServers", {}).get("oracle", {}).get("headers", {}).get("Authorization", "")
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


def _oracle_ingest(items: list[dict]) -> dict:
    payload = {
        "jsonrpc": "2.0",
        "id": int(time.time() * 1000),
        "method": "tools/call",
        "params": {
            "name": "oracle_ingest",
            "arguments": {
                "source": f"edge-intel-bluesky-{datetime.now(timezone.utc).strftime('%Y%m%d')}",
                "extracted": {"items": items},
            },
        },
    }
    req = Request(
        f"{ORACLE_BASE.rstrip('/')}{ORACLE_MCP_PATH}",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {_oracle_token()}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": "pipernet-edge-intel-bluesky/0.1 (+https://piedpiper.fun)",
        },
        method="POST",
    )
    with urlopen(req, timeout=20) as resp:
        body = resp.read().decode("utf-8")
    for line in body.splitlines():
        if line.startswith("data:"):
            return json.loads(line[5:].strip())
    return {"raw": body[:500]}


def _sidecar_write(record: dict, log: logging.Logger) -> None:
    """Append one match to the JSONL sidecar for the Mission Control UI."""
    try:
        path = Path(SIDECAR_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Rotate if file exceeds cap — simple keep-last-half truncation.
        if path.exists() and path.stat().st_size > SIDECAR_MAX_BYTES:
            data = path.read_bytes()
            mid = len(data) // 2
            # Slice from next newline so we keep whole records
            cut = data.find(b"\n", mid)
            if cut > 0:
                path.write_bytes(data[cut + 1:])
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as e:
        log.warning("sidecar write failed (%s)", e)


# --- Filter ---

def load_keywords(path: str | None) -> list[str]:
    if not path:
        return DEFAULT_KEYWORDS
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(path)
    return [
        line.strip().lower()
        for line in p.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]


def match_keywords(text: str, keywords: Iterable[str]) -> list[str]:
    t = text.lower()
    return [kw for kw in keywords if kw in t]


# --- Main loop ---

async def stream(args, log: logging.Logger) -> None:
    keywords = load_keywords(args.keywords_file)
    log.info("loaded %d keywords; dry_run=%s", len(keywords), args.dry_run)
    batch: list[dict] = []
    last_flush = time.monotonic()
    seen_uris: set[str] = set()

    while True:
        try:
            async with websockets.connect(JETSTREAM_URL, max_size=2 ** 22) as ws:
                log.info("connected to Jetstream: %s", JETSTREAM_URL)
                async for raw in ws:
                    try:
                        ev = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    commit = ev.get("commit") or {}
                    if commit.get("operation") != "create":
                        continue
                    record = commit.get("record") or {}
                    if record.get("$type") != "app.bsky.feed.post":
                        # Some Jetstream variants include $type, some not — be lenient
                        if commit.get("collection") != "app.bsky.feed.post":
                            continue
                    text = (record.get("text") or "").strip()
                    if not text:
                        continue
                    hits = match_keywords(text, keywords)
                    if not hits:
                        continue
                    did = ev.get("did") or "did:unknown"
                    rkey = commit.get("rkey") or ""
                    uri = f"at://{did}/app.bsky.feed.post/{rkey}"
                    if uri in seen_uris:
                        continue
                    seen_uris.add(uri)
                    if len(seen_uris) > 50_000:
                        # Keep memory bounded — drop oldest half (cheap, not LRU)
                        seen_uris = set(list(seen_uris)[-25_000:])

                    when = record.get("createdAt") or datetime.now(timezone.utc).isoformat()
                    langs = record.get("langs") or []
                    item = {
                        "content": f"[bluesky] {text}",
                        "type": "edge-signal",
                        "rationale": (
                            f"Bluesky post matching {', '.join(hits)} "
                            f"by {did[:24]} at {when}"
                        ),
                        "tags": [
                            "edge-intel",
                            "source:bluesky",
                            f"author:{did[:24]}",
                            f"uri:{uri}",
                            *[f"kw:{k}" for k in hits],
                            *[f"lang:{l}" for l in langs[:3]],
                        ],
                        "confidence": 0.7,
                    }
                    batch.append(item)
                    log.info("match: %s | %s", ",".join(hits), text[:120].replace("\n", " "))
                    # Sidecar — written immediately for the live UI feed
                    _sidecar_write(
                        {
                            "ts": datetime.now(timezone.utc).isoformat(),
                            "source": "bluesky",
                            "did": did,
                            "uri": uri,
                            "text": text,
                            "keywords": hits,
                            "langs": langs[:3],
                            "created_at": when,
                        },
                        log,
                    )

                    now = time.monotonic()
                    if len(batch) >= args.batch or (now - last_flush) >= args.flush_seconds:
                        if not args.dry_run:
                            try:
                                result = _oracle_ingest(batch)
                                log.info("ingested %d items → %s", len(batch), str(result)[:160])
                            except (URLError, HTTPError, RuntimeError) as e:
                                log.warning("ingest failed (%s); keeping batch for retry", e)
                                # Don't clear batch — try again on next flush
                                last_flush = now
                                continue
                        batch.clear()
                        last_flush = now
        except (websockets.ConnectionClosed, OSError) as e:
            log.warning("connection dropped (%s); reconnecting in 5s", e)
            await asyncio.sleep(5)
        except Exception:  # noqa: BLE001
            log.exception("unexpected error; reconnecting in 15s")
            await asyncio.sleep(15)


def main() -> int:
    p = argparse.ArgumentParser(description="Bluesky Jetstream → Oracle edge-intel feeder")
    p.add_argument("--keywords-file", help="path to one-keyword-per-line file (default: built-in list)")
    p.add_argument("--batch", type=int, default=10, help="flush after this many matches (default 10)")
    p.add_argument("--flush-seconds", type=int, default=60, help="flush after this many seconds even if batch not full (default 60)")
    p.add_argument("--dry-run", action="store_true", help="log matches but do not ingest to Oracle")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )
    log = logging.getLogger("bluesky-jetstream")
    try:
        asyncio.run(stream(args, log))
    except KeyboardInterrupt:
        log.info("stopped")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
