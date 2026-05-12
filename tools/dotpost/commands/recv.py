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
from ..transport import tool_call


def _fetch_groups(groups: list[str]) -> list[tuple[str, str]]:
    """Fetch group messages for the given group names.

    Returns a list of (label, text) pairs, deduped by text content.
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

    Groups are declared per-call — no persistent subscription state.
    Returns '(no dotposts found)' if nothing is in the inbox.
    """
    chunks: list[str] = []
    seen: set[str] = set()

    for query in (f"dotpost to:{me}", f"dotpost to:{BROADCAST_HANDLE}"):
        result = tool_call("oracle_query", {"query": query, "type_filter": "dotpost"})
        text = result.get("text") if "text" in result else json.dumps(result, indent=2)
        if text and text not in seen:
            seen.add(text)
            label = "DM" if query.endswith(f":{me}") else "BROADCAST"
            chunks.append(f"=== {label} ({query}) ===\n{text}")

    if groups:
        for label, text in _fetch_groups(groups):
            if text not in seen:
                seen.add(text)
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
