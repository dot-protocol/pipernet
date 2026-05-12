"""
commands/intents_cmd — 'pipernet dotpost intents' subcommand.

Queries Oracle for intent and resolve observations for a given handle,
joins them, and prints a tabular status summary.

Status values:
  open      — intent exists, no resolve, not expired
  honored   — resolve exists with honored=true
  partial   — resolve exists with honored='partial'
  refused   — resolve exists with honored=false
  expired   — expires_at < now, no resolve found
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from datetime import datetime, timezone

from ..transport import tool_call

VALID_STATUSES = frozenset({"open", "honored", "refused", "partial", "expired"})


def _b64url_decode(s: str) -> bytes:
    """Decode a URL-safe base64 string (padding optional)."""
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)


def _extract_tag(tags: list[str], prefix: str) -> str | None:
    """Return the first tag value matching the given prefix, or None."""
    for t in tags:
        if t.startswith(prefix):
            return t[len(prefix):]
    return None


def _decode_intent_payload(intent_b64: str) -> dict:
    """Decode the base64url intent payload to a dict. Returns {} on failure."""
    try:
        raw = _b64url_decode(intent_b64)
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {}


def _decode_resolve_payload(resolve_b64: str) -> dict:
    """Decode the base64url resolve payload to a dict. Returns {} on failure."""
    try:
        raw = _b64url_decode(resolve_b64)
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {}


def _is_expired(expires_at: str | None) -> bool:
    """Return True if expires_at is in the past (UTC). False if None or future."""
    if not expires_at:
        return False
    try:
        exp = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        return exp < datetime.now(timezone.utc)
    except ValueError:
        return False


def _fetch_observations(query: str) -> list[dict]:
    """Query Oracle and return a flat list of observation dicts.

    Handles both {'items': [...]} and {'text': '...'} response shapes.
    Returns [] on any error.
    """
    try:
        result = tool_call("oracle_query", {"query": query, "type_filter": "dotpost"})
    except Exception as e:
        print(f"warn: oracle query failed: {e}", file=sys.stderr)
        return []

    # Try structured items format.
    if "items" in result:
        return result["items"]
    # Fall back to text — try JSON parsing.
    text = result.get("text", "")
    if text:
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict) and "items" in parsed:
                return parsed["items"]
        except json.JSONDecodeError:
            pass
    return []


def cmd_intents(args: argparse.Namespace) -> int:
    """Execute the 'intents' subcommand.

    Queries Oracle for intent + resolve observations for --for <handle>,
    joins them, filters by --status if given, and prints a status table.
    Returns exit code (0 = success, 1 = error).
    """
    handle = args.for_handle or os.getenv("PIPERNET_HANDLE", "rocky")
    status_filter = getattr(args, "status", None)
    limit = getattr(args, "limit", 20) or 20

    if status_filter and status_filter not in VALID_STATUSES:
        print(
            f"error: --status must be one of {sorted(VALID_STATUSES)}",
            file=sys.stderr,
        )
        return 1

    # Fetch intents addressed to or from the handle.
    intent_obs = _fetch_observations(f"dotpost intent from:{handle}")
    # Also fetch intents addressed to this handle.
    intent_obs_to = _fetch_observations(f"dotpost intent to:{handle}")
    # Merge, dedup by obs id.
    seen_ids: set[str] = set()
    all_intents: list[dict] = []
    for obs in intent_obs + intent_obs_to:
        obs_id = obs.get("id") or obs.get("obs_id") or ""
        if obs_id not in seen_ids:
            seen_ids.add(obs_id)
            all_intents.append(obs)

    # Fetch resolves referencing any of these intent IDs.
    # Query broadly then filter client-side.
    resolve_obs = _fetch_observations(f"dotpost resolve")
    # Build resolve index: intent_id -> resolve record.
    resolve_index: dict[str, dict] = {}
    for obs in resolve_obs:
        tags = obs.get("tags") or []
        intent_ref = _extract_tag(tags, "resolves_intent:")
        if intent_ref and intent_ref not in resolve_index:
            resolve_b64 = _extract_tag(tags, "resolve:")
            resolve_data = _decode_resolve_payload(resolve_b64) if resolve_b64 else {}
            resolve_index[intent_ref] = {
                "obs_id": obs.get("id") or obs.get("obs_id") or "",
                "honored": resolve_data.get("honored"),
                "deviation": resolve_data.get("deviation"),
                "resolved_at": resolve_data.get("resolved_at"),
                "resolver": resolve_data.get("resolver"),
            }

    # Build rows.
    rows: list[dict] = []
    for obs in all_intents:
        tags = obs.get("tags") or []
        obs_id = obs.get("id") or obs.get("obs_id") or "(no-id)"
        intent_b64 = _extract_tag(tags, "intent:")
        intent_data = _decode_intent_payload(intent_b64) if intent_b64 else {}
        what = intent_data.get("what") or obs.get("content") or ""
        expires_at = intent_data.get("expires_at")
        addressed_to = intent_data.get("addressed_to") or _extract_tag(tags, "to:") or "?"

        resolve = resolve_index.get(obs_id)
        if resolve:
            honored = resolve.get("honored")
            if honored is True:
                status = "honored"
            elif honored is False:
                status = "refused"
            else:
                status = "partial"
        elif _is_expired(expires_at):
            status = "expired"
        else:
            status = "open"

        rows.append({
            "id": obs_id,
            "what": what[:60] + ("..." if len(what) > 60 else ""),
            "status": status,
            "addressed_to": addressed_to,
            "expires_at": expires_at or "—",
            "resolve_id": resolve.get("obs_id") if resolve else "—",
            "deviation": resolve.get("deviation") if resolve else None,
        })

    # Apply status filter.
    if status_filter:
        rows = [r for r in rows if r["status"] == status_filter]

    # Apply limit.
    rows = rows[:limit]

    if not rows:
        print(f"(no intents found for '{handle}'" + (f" with status={status_filter}" if status_filter else "") + ")")
        return 0

    # Print table.
    print(f"\nIntents for '{handle}'" + (f" [status={status_filter}]" if status_filter else "") + f" — {len(rows)} result(s)\n")
    col_widths = {"id": 30, "what": 45, "status": 8, "addressed_to": 15, "expires_at": 22}
    header = (
        f"{'ID':<{col_widths['id']}}  "
        f"{'WHAT':<{col_widths['what']}}  "
        f"{'STATUS':<{col_widths['status']}}  "
        f"{'TO':<{col_widths['addressed_to']}}  "
        f"{'EXPIRES':<{col_widths['expires_at']}}"
    )
    print(header)
    print("-" * len(header))
    for r in rows:
        print(
            f"{r['id']:<{col_widths['id']}}  "
            f"{r['what']:<{col_widths['what']}}  "
            f"{r['status']:<{col_widths['status']}}  "
            f"{str(r['addressed_to']):<{col_widths['addressed_to']}}  "
            f"{str(r['expires_at']):<{col_widths['expires_at']}}"
        )
        if r.get("deviation"):
            print(f"  deviation: {r['deviation']}")
    print()
    return 0
