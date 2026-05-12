"""
cli — argparse parser + subcommand dispatch for dotpost.

Existing: send, broadcast, group, recv, watch (backward-compatible).
New (intent-substrate-v0.1): intent, resolve, intents.
"""
from __future__ import annotations

import argparse
import sys

from .commands.send import cmd_send
from .commands.broadcast import cmd_broadcast
from .commands.group import cmd_group
from .commands.recv import cmd_recv
from .commands.watch import cmd_watch
from .commands.intent_cmd import cmd_intent
from .commands.resolve_cmd import cmd_resolve
from .commands.intents_cmd import cmd_intents


def build_parser() -> argparse.ArgumentParser:
    """Construct and return the dotpost ArgumentParser with all subcommands."""
    p = argparse.ArgumentParser(
        prog="pipernet-dotpost",
        description="mesh comms via Oracle — the brain is the bus",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # send
    p_send = sub.add_parser("send", help="post a message to a mesh peer via Oracle")
    p_send.add_argument("--to", required=True,
        help="recipient handle, 'all', or group:<name>")
    p_send.add_argument("--body", required=True, help="message body")
    p_send.add_argument("--from", dest="from_handle",
        help="sender handle (default: $PIPERNET_HANDLE or rocky)")
    p_send.add_argument("--reply-to", dest="reply_to",
        help="thread under an OBS id (adds reply + in_reply_to:<id> tags)")
    p_send.set_defaults(func=cmd_send)

    # broadcast
    p_bc = sub.add_parser("broadcast",
        help="broadcast to ALL mesh agents (sugar for send --to all)")
    p_bc.add_argument("--body", required=True, help="message body")
    p_bc.add_argument("--from", dest="from_handle",
        help="sender handle (default: $PIPERNET_HANDLE or rocky)")
    p_bc.add_argument("--reply-to", dest="reply_to",
        help="thread under an OBS id (adds reply + in_reply_to:<id> tags)")
    p_bc.set_defaults(func=cmd_broadcast)

    # group
    p_grp = sub.add_parser("group",
        help="send to a named group (canonical group-routing subcommand)")
    p_grp.add_argument("--to", required=True,
        help="group name or comma-separated list (e.g., arch,room-design)")
    p_grp.add_argument("--body", required=True, help="message body")
    p_grp.add_argument("--from", dest="from_handle",
        help="sender handle (default: $PIPERNET_HANDLE or rocky)")
    p_grp.add_argument("--reply-to", dest="reply_to", help="thread under an OBS id")
    p_grp.set_defaults(func=cmd_group)

    # recv
    p_recv = sub.add_parser("recv", help="read incoming dotposts from Oracle")
    p_recv.add_argument("--for", dest="for_handle",
        help="recipient handle (default: $PIPERNET_HANDLE or rocky)")
    p_recv.add_argument("--since", help="only show dotposts after this ISO timestamp")
    p_recv.add_argument("--limit", type=int, default=20)
    p_recv.add_argument("--groups", default=None,
        help="comma-separated group names to include (DMs+broadcasts always included)")
    p_recv.add_argument("--subscribe", default=None, dest="subscribe",
        help="alias for --groups")
    p_recv.set_defaults(func=cmd_recv)

    # watch
    p_watch = sub.add_parser("watch", help="poll Oracle continuously for new dotposts")
    p_watch.add_argument("--for", dest="for_handle",
        help="recipient handle (default: $PIPERNET_HANDLE or rocky)")
    p_watch.add_argument("--interval", type=int, default=30,
        help="seconds between polls (min 10)")
    p_watch.add_argument("--groups", default=None,
        help="comma-separated group names to include")
    p_watch.add_argument("--subscribe", default=None, dest="subscribe",
        help="alias for --groups")
    p_watch.set_defaults(func=cmd_watch)

    # -------------------------------------------------------------------------
    # intent  (NEW — intent substrate v0.1)
    # -------------------------------------------------------------------------
    p_intent = sub.add_parser(
        "intent",
        help="emit a signed intent observation (intent-substrate-v0.1)",
    )
    p_intent.add_argument("--what", required=True, help="concise statement of what is wanted")
    p_intent.add_argument(
        "--to", dest="to",
        default="all",
        help="addressed-to handle, 'all', or 'group:<name>' (default: all)",
    )
    p_intent.add_argument(
        "--budget-max-usd", dest="budget_max_usd", type=float, default=None,
        help="maximum budget in USD",
    )
    p_intent.add_argument(
        "--deadline", default=None,
        help="deadline ISO 8601 timestamp (populates constraints.deadline)",
    )
    p_intent.add_argument(
        "--must-have", dest="must_have", default=None,
        help="comma-separated list of required items (populates constraints.must_have)",
    )
    p_intent.add_argument(
        "--must-not", dest="must_not", default=None,
        help="comma-separated list of prohibited items (constraints.must_not_include)",
    )
    p_intent.add_argument(
        "--values", default=None,
        help="comma-separated value tags the sender claims to hold",
    )
    p_intent.add_argument(
        "--no-refuse-substitution", dest="no_refuse_substitution",
        action="store_true",
        help="allow resolver to substitute; default is refuse_substitution=True",
    )
    p_intent.add_argument(
        "--context-ref", dest="context_ref", default=None,
        help="comma-separated obs_ids or blob refs to attach as context",
    )
    p_intent.add_argument(
        "--expires-at", dest="expires_at", default=None,
        help="ISO 8601 expiry timestamp",
    )
    p_intent.add_argument(
        "--from", dest="from_handle",
        help="sender handle (default: $PIPERNET_HANDLE or rocky)",
    )
    p_intent.set_defaults(func=cmd_intent)

    # -------------------------------------------------------------------------
    # resolve  (NEW — intent substrate v0.1)
    # -------------------------------------------------------------------------
    p_resolve = sub.add_parser(
        "resolve",
        help="emit a signed resolve observation referencing an intent",
    )
    p_resolve.add_argument(
        "--intent-id", dest="intent_id", required=True,
        help="obs_id of the intent being resolved",
    )
    p_resolve.add_argument(
        "--honored", required=True,
        help="true | false | partial",
    )
    p_resolve.add_argument(
        "--delivery", default=None,
        help=(
            "obs:<id>, blob:sha256:<hex>, or URL pointing to the delivered artifact. "
            "Optional (may be null when honored=false)."
        ),
    )
    p_resolve.add_argument(
        "--deviation", default=None,
        help="required when --honored is false or partial; explains what was not honored",
    )
    p_resolve.add_argument(
        "--from", dest="from_handle",
        help="resolver handle (default: $PIPERNET_HANDLE or rocky)",
    )
    p_resolve.set_defaults(func=cmd_resolve)

    # -------------------------------------------------------------------------
    # intents  (NEW — intent substrate v0.1)
    # -------------------------------------------------------------------------
    p_intents = sub.add_parser(
        "intents",
        help="query intent status for a handle (open/honored/refused/partial/expired)",
    )
    p_intents.add_argument(
        "--for", dest="for_handle", required=True,
        help="handle to query intents for",
    )
    p_intents.add_argument(
        "--status", default=None,
        choices=["open", "honored", "refused", "partial", "expired"],
        help="filter by status",
    )
    p_intents.add_argument(
        "--limit", type=int, default=20,
        help="maximum number of intents to return (default 20)",
    )
    p_intents.set_defaults(func=cmd_intents)

    return p


def main(argv: list[str] | None = None) -> int:
    """Parse argv and dispatch to the appropriate subcommand handler.

    Returns the exit code from the subcommand (0 = success).
    """
    p = build_parser()
    args = p.parse_args(argv)
    return args.func(args)
