"""
commands/group — 'pipernet dotpost group' subcommand.

Canonical form for group-addressed dotposts.
Accepts comma-separated --to for multi-group fan-out (one observation per group).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from ..tags import validate_group_name, build_group_tags
from ..transport import tool_call


def _send_group_dotpost(
    sender: str,
    group_name: str,
    body: str,
    reply_to: str | None = None,
) -> dict:
    """Write one group dotpost observation. Returns the Oracle ingest response."""
    tags = build_group_tags(sender, group_name, reply_to=reply_to)
    rationale = f"DOTpost group message from {sender} to group:{group_name}"
    if reply_to:
        rationale = f"{rationale} (reply to {reply_to})"

    payload = {
        "source": f"pipernet-mesh-{sender}",
        "extracted": {
            "items": [
                {
                    "content": body,
                    "type": "dotpost",
                    "rationale": rationale,
                    "tags": tags,
                    "confidence": 0.95,
                }
            ]
        },
    }
    suffix = f" reply→{reply_to}" if reply_to else ""
    print(f"{sender}@mesh → group:{group_name}{suffix} ({len(body)} chars)", file=sys.stderr)
    return tool_call("oracle_ingest", payload)


def cmd_group(args: argparse.Namespace) -> int:
    """Execute the 'group' subcommand.

    Parses comma-separated group names and sends one observation per group.
    Returns exit code (0 = success, 1 = error).
    """
    sender = args.from_handle or os.getenv("PIPERNET_HANDLE", "rocky")
    reply_to = getattr(args, "reply_to", None)
    group_names_raw = [g.strip() for g in args.to.split(",") if g.strip()]
    try:
        group_names = [validate_group_name(g) for g in group_names_raw]
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    if not group_names:
        print("error: --to requires at least one group name", file=sys.stderr)
        return 1
    results = []
    for group_name in group_names:
        result = _send_group_dotpost(sender, group_name, args.body, reply_to)
        results.append(result)
    print(json.dumps(results if len(results) > 1 else results[0], indent=2))
    return 0
