"""
commands/broadcast — 'pipernet dotpost broadcast' subcommand.

Syntactic sugar for send --to all. Writes one Oracle observation tagged
to:all + broadcast. O(1) regardless of how many agents are on the mesh.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from ..tags import build_send_tags, BROADCAST_HANDLE
from ..transport import tool_call


def cmd_broadcast(args: argparse.Namespace) -> int:
    """Execute the 'broadcast' subcommand.

    Returns exit code (0 = success, 1 = error).
    """
    sender = args.from_handle or os.getenv("PIPERNET_HANDLE", "rocky")
    reply_to = getattr(args, "reply_to", None)
    tags = build_send_tags(sender, BROADCAST_HANDLE, reply_to=reply_to)
    rationale = f"DOTpost broadcast from {sender} to all mesh agents"
    if reply_to:
        rationale = f"{rationale} (reply to {reply_to})"

    payload = {
        "source": f"pipernet-mesh-{sender}",
        "extracted": {
            "items": [
                {
                    "content": args.body,
                    "type": "dotpost",
                    "rationale": rationale,
                    "tags": tags,
                    "confidence": 0.95,
                }
            ]
        },
    }
    suffix = f" reply→{reply_to}" if reply_to else ""
    print(f"{sender}@mesh → ALL{suffix} ({len(args.body)} chars)", file=sys.stderr)
    result = tool_call("oracle_ingest", payload)
    print(json.dumps(result, indent=2))
    return 0
