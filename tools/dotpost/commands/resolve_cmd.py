"""
commands/resolve_cmd — 'pipernet dotpost resolve' subcommand.

Constructs, signs, and posts a v0.1 Resolve observation to Oracle,
referencing a prior intent by its obs_id.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from pathlib import Path
from ..intent import Resolve, _utcnow_iso
from ..identity import load_or_generate, pubkey_hex
from ..tags import build_resolve_z_tags
from ..transport import tool_call


def cmd_resolve(args: argparse.Namespace) -> int:
    """Execute the 'resolve' subcommand.

    Builds a Resolve object, signs it, and posts to Oracle with
    resolves_intent:<obs_id> back-reference.
    Returns exit code (0 = success, 1 = error).
    """
    resolver = args.from_handle or os.getenv("PIPERNET_HANDLE", "rocky")

    # Parse --honored: accept 'true', 'false', 'partial' (case-insensitive).
    honored_raw = args.honored.lower().strip()
    if honored_raw == "true":
        honored: bool | str = True
    elif honored_raw == "false":
        honored = False
    elif honored_raw == "partial":
        honored = "partial"
    else:
        print(
            f"error: --honored must be 'true', 'false', or 'partial'; got {args.honored!r}",
            file=sys.stderr,
        )
        return 1

    # Build delivery dict — at most one of observation/blob/url is non-null.
    delivery_raw = getattr(args, "delivery", None)
    delivery: dict = {"observation": None, "blob": None, "url": None}
    if delivery_raw:
        if delivery_raw.startswith("obs:"):
            delivery["observation"] = delivery_raw
        elif delivery_raw.startswith("blob:"):
            delivery["blob"] = delivery_raw
        else:
            delivery["url"] = delivery_raw

    deviation = getattr(args, "deviation", None)

    try:
        resolve = Resolve(
            intent_id=args.intent_id,
            honored=honored,
            resolver=resolver,
            resolved_at=_utcnow_iso(),
            delivery=delivery,
            deviation=deviation,
        )
    except ValueError as e:
        print(f"error: invalid resolve: {e}", file=sys.stderr)
        return 1

    # Load keypair.
    try:
        priv_key, pub_bytes, generated = load_or_generate(resolver)
    except Exception as e:
        print(f"error: key load failed: {e}", file=sys.stderr)
        return 1

    if generated:
        pub_hex = pubkey_hex(pub_bytes)
        print(
            f"info: generated new keypair for '{resolver}' at {Path.home() / '.pipernet' / f'{resolver}.key'}",
            file=sys.stderr,
        )
        print(f"info: pubkey = {pub_hex}", file=sys.stderr)

    # Sign and compress the resolve (v0.5.0 wire format).
    compressed_b64, sig_b64 = resolve.to_compressed_b64(priv_key)

    # The resolve is addressed back to the intent's channel ("all" by default).
    tags = build_resolve_z_tags(
        resolver, compressed_b64, sig_b64, args.intent_id, addressed_to="all"
    )

    honored_label = {True: "honored", False: "refused", "partial": "partial"}.get(
        honored, str(honored)
    )
    body = (
        f"[resolve:{honored_label}] intent={args.intent_id}"
        + (f" deviation={deviation}" if deviation else "")
    )
    payload = {
        "source": f"pipernet-mesh-{resolver}",
        "extracted": {
            "items": [
                {
                    "content": body,
                    "type": "dotpost",
                    "rationale": (
                        f"Resolve from {resolver}: intent {args.intent_id} "
                        f"→ honored={honored_label}"
                    ),
                    "tags": tags,
                    "confidence": 0.95,
                }
            ]
        },
    }
    print(
        f"{resolver}@mesh resolve → {args.intent_id} [{honored_label}]",
        file=sys.stderr,
    )
    result = tool_call("oracle_ingest", payload)
    print(json.dumps(result, indent=2))
    return 0
