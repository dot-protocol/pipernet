"""
commands/intent_cmd — 'pipernet dotpost intent' subcommand.

Constructs, signs, and posts a v0.1 Intent observation to Oracle.
The observation carries intent:<b64> + intent_sig:<b64> tags per the spec.

Key discovery order:
  1. PIPERNET_PRIVKEY env var
  2. ~/KEY_DIR/<handle>.key  (KEY_DIR = .pipernet)
  3. Generate new keypair, write to disk, announce pubkey via broadcast.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from ..intent import Intent
from ..identity import load_or_generate, pubkey_hex, _key_path
from ..tags import build_intent_z_tags, parse_comma_list
from ..transport import tool_call


def cmd_intent(args: argparse.Namespace) -> int:
    """Execute the 'intent' subcommand.

    Builds an Intent object from CLI args, signs it, and posts to Oracle.
    Returns exit code (0 = success, 1 = error).
    """
    sender = args.from_handle or os.getenv("PIPERNET_HANDLE", "rocky")
    addressed_to = getattr(args, "to", None) or "all"
    must_have = parse_comma_list(getattr(args, "must_have", None))
    must_not = parse_comma_list(getattr(args, "must_not", None))
    values = parse_comma_list(getattr(args, "values", None))
    context_refs = parse_comma_list(getattr(args, "context_ref", None))
    refuse_sub = not getattr(args, "no_refuse_substitution", False)

    # Build constraints dict from individual flags.
    constraints: dict = {}
    if getattr(args, "budget_max_usd", None) is not None:
        constraints["budget_max_usd"] = args.budget_max_usd
    if getattr(args, "deadline", None):
        constraints["deadline"] = args.deadline
    if must_have:
        constraints["must_have"] = must_have
    if must_not:
        constraints["must_not_include"] = must_not

    try:
        intent = Intent(
            what=args.what,
            constraints=constraints,
            values=values,
            refuse_substitution=refuse_sub,
            addressed_to=addressed_to,
            expires_at=getattr(args, "expires_at", None),
            context_refs=context_refs,
        )
    except ValueError as e:
        print(f"error: invalid intent: {e}", file=sys.stderr)
        return 1

    # Load or generate keypair.
    try:
        priv_key, pub_bytes, generated = load_or_generate(sender)
    except Exception as e:
        print(f"error: key load failed: {e}", file=sys.stderr)
        return 1

    if generated:
        pub_hex = pubkey_hex(pub_bytes)
        print(
            f"info: generated new keypair for '{sender}' at {_key_path(sender)}",
            file=sys.stderr,
        )
        print(f"info: pubkey = {pub_hex}", file=sys.stderr)
        # Announce the new pubkey via broadcast so other agents can verify future sigs.
        _announce_pubkey(sender, pub_hex)

    # Sign and compress the intent (v0.5.0 wire format).
    compressed_b64, sig_b64 = intent.to_compressed_b64(priv_key)

    # Build oracle observation using compressed _z tags.
    tags = build_intent_z_tags(
        sender, compressed_b64, sig_b64,
        addressed_to=addressed_to,
        context_refs=context_refs if context_refs else None,
    )
    body = f"[intent] {intent.what}"
    payload = {
        "source": f"pipernet-mesh-{sender}",
        "extracted": {
            "items": [
                {
                    "content": body,
                    "type": "dotpost",
                    "rationale": f"Intent from {sender} addressed to {addressed_to}: {intent.what}",
                    "tags": tags,
                    "confidence": 0.95,
                }
            ]
        },
    }
    print(f"{sender}@mesh intent → {addressed_to}: {intent.what[:60]}", file=sys.stderr)
    result = tool_call("oracle_ingest", payload)
    print(json.dumps(result, indent=2))
    return 0


def _announce_pubkey(sender: str, pub_hex: str) -> None:
    """Broadcast the new public key once so other agents can record it."""
    from ..tags import build_send_tags, BROADCAST_HANDLE
    tags = build_send_tags(sender, BROADCAST_HANDLE, extra=[f"pubkey:{pub_hex}", "identity"])
    payload = {
        "source": f"pipernet-mesh-{sender}",
        "extracted": {
            "items": [
                {
                    "content": (
                        f"[identity] {sender} new ed25519 pubkey: {pub_hex}"
                    ),
                    "type": "dotpost",
                    "rationale": f"New keypair generated for {sender}",
                    "tags": tags,
                    "confidence": 1.0,
                }
            ]
        },
    }
    try:
        tool_call("oracle_ingest", payload)
        print(f"info: pubkey broadcast sent", file=sys.stderr)
    except Exception as e:
        print(f"warn: pubkey broadcast failed: {e}", file=sys.stderr)
