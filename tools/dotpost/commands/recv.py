"""
commands/recv — 'pipernet dotpost recv' subcommand.

Fetches DMs (to:<me>) + broadcasts (to:all) + optional group channels
from Oracle and prints them to stdout.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from ..tags import parse_groups_arg, BROADCAST_HANDLE
from ..transport import tool_call, dotpost_inbox


def _format_msg(m: dict) -> str:
    """Render one structured /dotpost-inbox message as a human line."""
    kind   = m.get("kind", "msg")
    sender = m.get("from", "?") or "?"
    obs_id = m.get("id", "")
    ts     = (m.get("created_at") or "")[:19]
    body   = (m.get("body") or m.get("subject") or "").strip()
    return f"  [{kind}] {sender}  {ts}  ({obs_id})\n  {body}"


def _fetch_groups(groups: list[str]) -> list[tuple[str, str]]:
    """Fetch group messages for the given group names.

    Group queries still use the MCP oracle_query path — /dotpost-inbox is
    handle-scoped, not group-scoped. (Adding group support to the endpoint
    is a follow-up; today groups are rare enough that the text query path
    is fine.)
    """
    chunks: list[tuple[str, str]] = []
    seen: set[str] = set()
    for group_name in groups:
        query = f"dotpost to:group:{group_name}"
        result = tool_call("oracle_query", {"query": query, "type_filter": "dotpost"})
        text = result.get("text") if "text" in result else json.dumps(result, indent=2)
        if text and text not in seen:
            seen.add(text)
            chunks.append((f"GROUP:{group_name}", text))
    return chunks


def fetch_inbox(me: str, groups: list[str] | None = None) -> str:
    """Fetch DMs + broadcasts + optional group channels as a formatted string.

    Uses the tag-indexed `/dotpost-inbox` HTTP endpoint on tree_serve
    (state.md blocker #10 — replaces the text-CONTAINS oracle_query path).
    Falls back to the MCP oracle_query path if the endpoint errors so that
    `recv` keeps working on a stale relay.

    Groups are declared per-call — no persistent subscription state.
    Returns '(no dotposts found)' if nothing is in the inbox.
    """
    chunks: list[str] = []
    try:
        data = dotpost_inbox(me, include_broadcasts=True, include_mentions=True, limit=50)
        messages = data.get("messages") or []
        if messages:
            # Split DM / broadcast / mention by `kind` for readability
            buckets: dict[str, list[dict]] = {}
            for m in messages:
                buckets.setdefault(m.get("kind", "msg"), []).append(m)
            for kind in ("dm", "mention", "broadcast"):
                bucket = buckets.get(kind) or []
                if not bucket: continue
                label = {"dm": "DMs", "mention": "MENTIONS", "broadcast": "BROADCASTS"}[kind]
                rendered = "\n".join(_format_msg(m) for m in bucket)
                chunks.append(f"=== {label} ({len(bucket)}) ===\n{rendered}")
    except RuntimeError as e:
        # Endpoint unreachable — fall back to the old text-CONTAINS MCP path
        chunks.append(f"# /dotpost-inbox unreachable ({e}); using MCP fallback")
        for query in (f"dotpost to:{me}", f"dotpost to:{BROADCAST_HANDLE}"):
            result = tool_call("oracle_query", {"query": query, "type_filter": "dotpost"})
            text = result.get("text") if "text" in result else json.dumps(result, indent=2)
            if text:
                label = "DM" if query.endswith(f":{me}") else "BROADCAST"
                chunks.append(f"=== {label} (fallback, {query}) ===\n{text}")

    if groups:
        seen_text: set[str] = set(chunks)
        for label, text in _fetch_groups(groups):
            if text not in seen_text:
                seen_text.add(text)
                chunks.append(f"=== {label} ===\n{text}")

    return "\n\n".join(chunks) if chunks else "(no dotposts found)"


def cmd_recv(args: argparse.Namespace) -> int:
    """Execute the 'recv' subcommand.

    Returns exit code (0 = success, 1 = error).
    """
    me = args.for_handle or os.getenv("PIPERNET_HANDLE", "rocky")
    groups_str = getattr(args, "groups", None) or getattr(args, "subscribe", None)
    try:
        groups = parse_groups_arg(groups_str)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    suffix = f" + groups [{groups_str}]" if groups else ""
    print(f"→ inbox for '{me}' (DMs + broadcasts{suffix})", file=sys.stderr)
    print(fetch_inbox(me, groups))
    return 0
