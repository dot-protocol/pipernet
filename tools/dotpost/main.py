"""
pipernet dotpost — mesh communication via Oracle.

Posts a message to the Oracle knowledge graph as a DOT envelope,
tagged for routing. Any other mesh node can query Oracle and read
their incoming dotposts. No paste relay. No audio bridge. The brain
is the bus.

Usage:
    pipernet dotpost send --to <handle> --body "<text>"        [--from <handle>]
    pipernet dotpost send --to group:<name> --body "<text>"    [--from <handle>]
    pipernet dotpost broadcast --body "<text>"                 [--from <handle>]
    pipernet dotpost group --to <group> --body "<text>"        [--from <handle>]
    pipernet dotpost recv [--for <handle>] [--groups g1,g2] [--since <iso>] [--limit 20]
    pipernet dotpost watch [--for <handle>] [--groups g1,g2] [--interval 30]

A broadcast is just `--to all`. Receivers automatically pick up both
their own DMs (`to:<me>`) and any `to:all` broadcasts in `recv` / `watch`.

Group routing: tag pattern `to:group:<name>` + `group:<name>`. Send via
the `group` subcommand or `send --to group:<name>`. Receive by passing
`--groups <name>,<name>` to `recv` / `watch` — callers declare interest
per-call, no persistent subscription state needed.

Group names: lowercase alphanumeric + dashes only (^[a-z0-9][a-z0-9-]*$).

Each dotpost becomes a typed Oracle observation with:
    type    = "dotpost"
    tags    = ["dotpost", "from:<sender>", "to:<recipient>"]   # or to:all / to:group:<name>
    content = the message body
    source  = "pipernet-mesh-<sender>"

Other nodes — Loom, Janus, Jared, Shannon, Stewart, anyone — query
Oracle for their tag and find their messages. The mesh routes through
the brain.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError


# Regex for valid group names: lowercase alphanumeric + dashes, must start with alnum
_GROUP_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _validate_group_name(name: str) -> str:
    """Return the group name if valid, raise ValueError otherwise."""
    if not _GROUP_NAME_RE.match(name):
        raise ValueError(
            f"Invalid group name {name!r}. "
            "Group names must match ^[a-z0-9][a-z0-9-]*$ "
            "(lowercase alphanumeric + dashes, starting with alphanumeric)."
        )
    return name


def _parse_to_arg(to_value: str) -> tuple[str, str | None]:
    """Parse --to value. Returns (routing_mode, value) where routing_mode is
    'handle', 'group', or 'broadcast'. For groups, value is the group name.
    For handles, value is the handle. For broadcast ('all'), value is None.
    """
    if to_value == BROADCAST_HANDLE:
        return ("broadcast", None)
    if to_value.startswith("group:"):
        group_name = to_value[len("group:"):]
        _validate_group_name(group_name)
        return ("group", group_name)
    return ("handle", to_value)


ORACLE_BASE = os.getenv("ORACLE_BASE", "https://oracle.axxis.world")
ORACLE_MCP_PATH = os.getenv("ORACLE_MCP_PATH", "/oracle/mcp/")
BROADCAST_HANDLE = "all"


def _oracle_token() -> str:
    """Get the Oracle V4 bearer token, in priority order."""
    if t := os.getenv("ORACLE_TOKEN"):
        return t
    if t := os.getenv("ORACLE_AUTH_TOKEN"):
        return t
    if t := os.getenv("TREE_AUTH_TOKEN"):
        return t
    # Fall back to ~/.mcp.json (Claude Code MCP config — canonical source)
    mcp_path = Path.home() / ".mcp.json"
    if mcp_path.exists():
        try:
            cfg = json.loads(mcp_path.read_text())
            oracle = cfg.get("mcpServers", {}).get("oracle", {})
            auth = oracle.get("headers", {}).get("Authorization", "")
            if auth.startswith("Bearer "):
                return auth[len("Bearer "):]
        except (json.JSONDecodeError, KeyError):
            pass
    # Fall back to oracle_v3/.env
    candidates = [
        Path(__file__).resolve().parent.parent.parent.parent / "oracle_v3" / ".env",
        Path("/Users/blaze/Movies/Kin/oracle_v3/.env"),
        Path.home() / "Movies" / "Kin" / "oracle_v3" / ".env",
    ]
    for env_path in candidates:
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("ORACLE_AUTH_TOKEN="):
                    return line.split("=", 1)[1].strip()
    raise RuntimeError(
        "Oracle token not found. Set ORACLE_TOKEN env var or check ~/.mcp.json"
    )


def _mcp_call(method: str, params: dict) -> dict:
    """Make an MCP JSON-RPC call against Oracle V4."""
    payload = {"jsonrpc": "2.0", "id": int(time.time() * 1000), "method": method, "params": params}
    req = Request(
        f"{ORACLE_BASE.rstrip('/')}{ORACLE_MCP_PATH}",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {_oracle_token()}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": "pipernet-dotpost/0.2 (+https://piedpiper.fun)",
        },
        method="POST",
    )
    with urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8")
    # MCP responses are SSE-style: lines beginning "data: <json>"
    for line in body.splitlines():
        if line.startswith("data:"):
            return json.loads(line[5:].strip())
    raise RuntimeError(f"unexpected MCP response: {body[:300]}")


def _tool_call(tool_name: str, args: dict) -> dict:
    resp = _mcp_call("tools/call", {"name": tool_name, "arguments": args})
    if "error" in resp:
        raise RuntimeError(f"oracle error: {resp['error']}")
    content = resp.get("result", {}).get("content", [])
    if not content:
        return {}
    text = content[0].get("text", "")
    # Some tools return JSON-string text, some return prose. Try parsing.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"text": text}


def _send_dotpost(
    sender: str,
    recipient: str,
    body: str,
    reply_to: str | None = None,
) -> dict:
    is_broadcast = recipient == BROADCAST_HANDLE
    tags = ["dotpost", f"from:{sender}", f"to:{recipient}", "mesh"]
    if is_broadcast:
        tags.append("broadcast")
        rationale = f"DOTpost broadcast from {sender} to all mesh agents"
    else:
        rationale = f"DOTpost from {sender} to {recipient} via mesh"
    if reply_to:
        tags.append("reply")
        tags.append(f"in_reply_to:{reply_to}")
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
    return _tool_call("oracle_ingest", payload)


def _send_group_dotpost(
    sender: str,
    group_name: str,
    body: str,
    reply_to: str | None = None,
) -> dict:
    """Write one observation addressed to a group.

    Tags written:
        to:group:<group_name>   — primary routing tag (used by recv)
        group:<group_name>      — secondary index tag (queryable standalone)
        dotpost, from:<sender>, mesh
    """
    _validate_group_name(group_name)
    tags = [
        "dotpost",
        f"from:{sender}",
        f"to:group:{group_name}",
        f"group:{group_name}",
        "mesh",
        "group-post",
    ]
    rationale = f"DOTpost group message from {sender} to group:{group_name}"
    if reply_to:
        tags.append("reply")
        tags.append(f"in_reply_to:{reply_to}")
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
    return _tool_call("oracle_ingest", payload)


def cmd_send(args: argparse.Namespace) -> int:
    sender = args.from_handle or os.getenv("PIPERNET_HANDLE", "rocky")
    reply_to = getattr(args, "reply_to", None)
    # Detect group: prefix in --to and route accordingly
    try:
        mode, value = _parse_to_arg(args.to)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    if mode == "group":
        result = _send_group_dotpost(sender, value, args.body, reply_to)
    else:
        result = _send_dotpost(sender, args.to, args.body, reply_to)
    print(json.dumps(result, indent=2))
    return 0


def cmd_broadcast(args: argparse.Namespace) -> int:
    sender = args.from_handle or os.getenv("PIPERNET_HANDLE", "rocky")
    result = _send_dotpost(sender, BROADCAST_HANDLE, args.body, getattr(args, "reply_to", None))
    print(json.dumps(result, indent=2))
    return 0


def cmd_group(args: argparse.Namespace) -> int:
    """Send a message to one or more groups.

    Canonical form:
        pipernet dotpost group --to <group_name> --from <handle> --body "..."

    Multi-group (comma-separated):
        pipernet dotpost group --to architecture,room-design --from shannon --body "..."
    """
    sender = args.from_handle or os.getenv("PIPERNET_HANDLE", "rocky")
    reply_to = getattr(args, "reply_to", None)
    # Parse comma-separated group names
    group_names_raw = [g.strip() for g in args.to.split(",") if g.strip()]
    try:
        group_names = [_validate_group_name(g) for g in group_names_raw]
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


def _fetch_groups(groups: list[str]) -> list[tuple[str, str]]:
    """Fetch group messages for the given group names.

    Returns a list of (label, text) pairs, one per group, deduped by text.
    """
    chunks: list[tuple[str, str]] = []
    seen: set[str] = set()
    for group_name in groups:
        query = f"dotpost to:group:{group_name}"
        result = _tool_call("oracle_query", {"query": query, "type_filter": "dotpost"})
        text = result.get("text") if "text" in result else json.dumps(result, indent=2)
        if text and text not in seen:
            seen.add(text)
            chunks.append((f"GROUP:{group_name}", text))
    return chunks


def _parse_groups_arg(groups_str: str | None) -> list[str]:
    """Parse a comma-separated groups string into a validated list of names.

    Returns an empty list if groups_str is None or empty.
    Raises ValueError for invalid group names.
    """
    if not groups_str:
        return []
    names = [g.strip() for g in groups_str.split(",") if g.strip()]
    return [_validate_group_name(g) for g in names]


def _fetch_inbox(me: str, groups: list[str] | None = None) -> str:
    """Fetch DMs (to:me) + broadcasts (to:all) + optional group channels.

    Groups are passed in per-call — no persistent subscription state.
    Backward-compatible: if groups is None or empty, only DMs + broadcasts.
    """
    chunks: list[str] = []
    seen: set[str] = set()

    for query in (f"dotpost to:{me}", f"dotpost to:{BROADCAST_HANDLE}"):
        result = _tool_call("oracle_query", {"query": query, "type_filter": "dotpost"})
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
    me = args.for_handle or os.getenv("PIPERNET_HANDLE", "rocky")
    groups_str = getattr(args, "groups", None) or getattr(args, "subscribe", None)
    try:
        groups = _parse_groups_arg(groups_str)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    suffix = f" + groups [{groups_str}]" if groups else ""
    print(f"→ inbox for '{me}' (DMs + broadcasts{suffix})", file=sys.stderr)
    print(_fetch_inbox(me, groups))
    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    me = args.for_handle or os.getenv("PIPERNET_HANDLE", "rocky")
    interval = max(10, int(args.interval))
    groups_str = getattr(args, "groups", None) or getattr(args, "subscribe", None)
    try:
        groups = _parse_groups_arg(groups_str)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    suffix = f" + groups [{groups_str}]" if groups else ""
    print(
        f"→ watching inbox for '{me}' (DMs + broadcasts{suffix}) every {interval}s. Ctrl-C to stop.",
        file=sys.stderr,
    )
    seen: set[str] = set()
    while True:
        try:
            text = _fetch_inbox(me, groups)
            digest = str(hash(text))
            if digest not in seen:
                seen.add(digest)
                ts = datetime.now(timezone.utc).isoformat()
                print(f"\n[{ts}]")
                print(text)
            time.sleep(interval)
        except KeyboardInterrupt:
            print("\n→ stopped", file=sys.stderr)
            return 0
        except (URLError, HTTPError, RuntimeError) as e:
            print(f"! error: {e}; retrying in {interval}s", file=sys.stderr)
            time.sleep(interval)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="pipernet-dotpost",
        description="mesh comms via Oracle — the brain is the bus",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_send = sub.add_parser("send", help="post a message to a mesh peer via Oracle")
    p_send.add_argument(
        "--to", required=True,
        help="recipient handle (e.g., loam, janus, jared, all) OR group:<name> to send to a group",
    )
    p_send.add_argument("--body", required=True, help="message body")
    p_send.add_argument("--from", dest="from_handle", help="sender handle (default: $PIPERNET_HANDLE or rocky)")
    p_send.add_argument("--reply-to", dest="reply_to", help="thread this message under an OBS id (adds reply + in_reply_to:<id> tags; bypasses Oracle vector dedup)")
    p_send.set_defaults(func=cmd_send)

    p_bc = sub.add_parser("broadcast", help="broadcast a dotpost to ALL mesh agents (sugar for --to all)")
    p_bc.add_argument("--body", required=True, help="message body")
    p_bc.add_argument("--from", dest="from_handle", help="sender handle (default: $PIPERNET_HANDLE or rocky)")
    p_bc.add_argument("--reply-to", dest="reply_to", help="thread this broadcast under an OBS id (adds reply + in_reply_to:<id> tags; bypasses Oracle vector dedup)")
    p_bc.set_defaults(func=cmd_broadcast)

    p_grp = sub.add_parser(
        "group",
        help="send a dotpost to a named group (canonical group-routing subcommand)",
    )
    p_grp.add_argument(
        "--to", required=True,
        help="group name or comma-separated list of group names (e.g., architecture or architecture,room-design)",
    )
    p_grp.add_argument("--body", required=True, help="message body")
    p_grp.add_argument("--from", dest="from_handle", help="sender handle (default: $PIPERNET_HANDLE or rocky)")
    p_grp.add_argument("--reply-to", dest="reply_to", help="thread this under an OBS id")
    p_grp.set_defaults(func=cmd_group)

    p_recv = sub.add_parser("recv", help="read incoming dotposts from Oracle")
    p_recv.add_argument("--for", dest="for_handle", help="recipient handle to read for (default: $PIPERNET_HANDLE or rocky)")
    p_recv.add_argument("--since", help="only show dotposts after this ISO timestamp")
    p_recv.add_argument("--limit", type=int, default=20)
    p_recv.add_argument(
        "--groups", default=None,
        help="comma-separated group names to include (e.g., architecture,cmo). No groups = DMs + broadcasts only.",
    )
    p_recv.add_argument(
        "--subscribe", default=None, dest="subscribe",
        help="alias for --groups (synonym)",
    )
    p_recv.set_defaults(func=cmd_recv)

    p_watch = sub.add_parser("watch", help="poll Oracle continuously for new dotposts")
    p_watch.add_argument("--for", dest="for_handle", help="recipient handle (default: $PIPERNET_HANDLE or rocky)")
    p_watch.add_argument("--interval", type=int, default=30, help="seconds between polls (min 10)")
    p_watch.add_argument(
        "--groups", default=None,
        help="comma-separated group names to include (e.g., architecture,cmo). No groups = DMs + broadcasts only.",
    )
    p_watch.add_argument(
        "--subscribe", default=None, dest="subscribe",
        help="alias for --groups (synonym)",
    )
    p_watch.set_defaults(func=cmd_watch)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
