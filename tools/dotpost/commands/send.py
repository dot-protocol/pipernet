"""
commands/send — 'pipernet dotpost send' subcommand.

Sends a DM, broadcast, or group message depending on the --to value.
Routes to group posts if --to group:<name> is detected.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from ..tags import parse_to_arg, build_send_tags, build_group_tags, BROADCAST_HANDLE
from ..transport import tool_call


def _send_dotpost(
    sender: str,
    recipient: str,
    body: str,
    reply_to: str | None = None,
) -> dict:
    """Write a DM or broadcast dotpost observation to Oracle.

    Returns the raw Oracle ingest response dict.
    """
    is_broadcast = recipient == BROADCAST_HANDLE
    tags = build_send_tags(sender, recipient, reply_to=reply_to)
    if is_broadcast:
        rationale = f"DOTpost broadcast from {sender} to all mesh agents"
    else:
        rationale = f"DOTpost from {sender} to {recipient} via mesh"
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
    arrow = "→ ALL" if is_broadcast else f"→ {recipient}"
    suffix = f" reply→{reply_to}" if reply_to else ""
    print(f"{sender}@mesh {arrow}{suffix} ({len(body)} chars)", file=sys.stderr)
    return tool_call("oracle_ingest", payload)


def _send_group_dotpost(
    sender: str,
    group_name: str,
    body: str,
    reply_to: str | None = None,
) -> dict:
    """Write a group dotpost observation to Oracle.

    Tags written: to:group:<name>, group:<name>, dotpost, from:<sender>, mesh, group-post.
    Returns the raw Oracle ingest response dict.
    """
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


def cmd_send(args: argparse.Namespace) -> int:
    """Execute the 'send' subcommand.

    Routes to group send if --to group:<name> is detected.
    Returns exit code (0 = success, 1 = error).
    """
    sender = args.from_handle or os.getenv("PIPERNET_HANDLE", "rocky")
    reply_to = getattr(args, "reply_to", None)
    try:
        mode, value = parse_to_arg(args.to)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    if mode == "group":
        result = _send_group_dotpost(sender, value, args.body, reply_to)
    else:
        result = _send_dotpost(sender, args.to, args.body, reply_to)
    print(json.dumps(result, indent=2))
    return 0
