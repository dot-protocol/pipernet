"""
commands/intents_cmd — 'pipernet dotpost intents' subcommand.

Queries Oracle for intent and resolve observations for a given handle,
joins them, and prints a tabular status summary.

Status values:
  open      — intent exists, no resolve recorded
  honored   — resolve exists with honored=true
  partial   — resolve exists with honored='partial'
  refused   — resolve exists with honored=false

Note on `expired`: requires the original intent's `expires_at` field,
which lives only in the encoded intent JSON in the observation tags.
Oracle's audit endpoint returns prose previews, not tags. To detect
`expired` we'd need either a richer Oracle MCP tool (get-by-id-with-tags)
or to also embed `expires_at` in the observation body. Out of scope
for v0.4.0; documented as a known gap.

Implementation:
  Uses oracle_audit (tag-filter capable) rather than oracle_query
  (which is semantic search and was incorrectly filtering by channel).
  Parses the bullet-line prose response. Each row carries id + channel
  + confidence + a short statement preview; the statement starts with
  `[intent] <what>` for intents and `[resolve:<status>] intent=<id>`
  for resolves, so status + linkage are recoverable without tags.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

from ..transport import tool_call

VALID_STATUSES = frozenset({"open", "honored", "refused", "partial", "expired"})

# Each audit row looks like:
#   • OBS-raw-20260512-536532115 [raw] (verified) — [intent] build a clean ...
_AUDIT_ROW_RE = re.compile(
    r"^•\s+(?P<id>\S+)\s+\[(?P<channel>[^\]]+)\]\s+\((?P<confidence>[^)]+)\)\s+—\s+(?P<statement>.*)$"
)

# Intent statement: `[intent] <what>`
_INTENT_STMT_RE = re.compile(r"^\[intent\]\s+(?P<what>.*)$")

# Resolve statement: `[resolve:<status>] intent=<obs_id>`
_RESOLVE_STMT_RE = re.compile(
    r"^\[resolve:(?P<honored>[^\]]+)\]\s+intent=(?P<intent_id>\S+)"
)


def _audit_by_tag(tag: str, limit: int = 100) -> list[dict]:
    """Fetch observations matching a tag via oracle_audit.

    Returns a list of dicts: {id, channel, confidence, statement}.
    Returns [] on error or no results.
    """
    try:
        result = tool_call("oracle_audit", {"tag_filter": tag, "limit": limit})
    except Exception as e:
        print(f"warn: oracle_audit failed for tag={tag}: {e}", file=sys.stderr)
        return []

    text = result.get("text", "") if isinstance(result, dict) else ""
    if not text:
        return []

    rows: list[dict] = []
    for line in text.splitlines():
        m = _AUDIT_ROW_RE.match(line.strip())
        if m:
            rows.append({
                "id": m.group("id"),
                "channel": m.group("channel"),
                "confidence": m.group("confidence"),
                "statement": m.group("statement"),
            })
    return rows


def _parse_intent_statement(stmt: str) -> str | None:
    """Extract the 'what' field from an intent statement, or None if not an intent row."""
    m = _INTENT_STMT_RE.match(stmt)
    return m.group("what").strip() if m else None


def _parse_resolve_statement(stmt: str) -> tuple[str, str] | None:
    """Extract (honored_status, intent_id) from a resolve statement, or None."""
    m = _RESOLVE_STMT_RE.match(stmt)
    if not m:
        return None
    return m.group("honored").strip(), m.group("intent_id").strip()


def cmd_intents(args: argparse.Namespace) -> int:
    """Execute the 'intents' subcommand.

    Fetches intent + resolve observations via oracle_audit (tag-filtered),
    joins them via the resolve statement's `intent=<obs_id>` linkage, and
    prints a status table. Returns 0 on success, 1 on validation error.
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

    # Pull all intent + resolve observations (broadly), then filter to the handle.
    # We can't tag-filter by handle in a single call without an AND-of-tags op,
    # so we fetch by 'intent' / 'resolve' tags and narrow client-side via the
    # `from:<handle>` tag (which we infer from the statement evidence or — for
    # this v0.4.0 — by re-parsing nothing; we trust the audit preview).
    intent_rows = _audit_by_tag("intent", limit=200)
    resolve_rows = _audit_by_tag("resolve", limit=200)

    # Index resolves by the intent_id they reference (parsed from statement).
    resolve_index: dict[str, dict] = {}
    for r in resolve_rows:
        parsed = _parse_resolve_statement(r["statement"])
        if not parsed:
            continue
        honored, intent_id = parsed
        if intent_id not in resolve_index:
            resolve_index[intent_id] = {
                "resolve_id": r["id"],
                "honored": honored,
            }

    # Build intent rows, joining with resolves.
    rows: list[dict] = []
    for r in intent_rows:
        what = _parse_intent_statement(r["statement"])
        if what is None:
            # Audit by tag 'intent' may surface non-icontact intent observations
            # whose statement doesn't begin with '[intent]'. Skip those.
            continue

        # Restrict to the handle: presence of "from <handle>" or "addressed to <handle>"
        # in the statement preview is too noisy. We rely on a follow-up Oracle query
        # that filters by both tags (`intent` AND `from:<handle>`) once that's available.
        # For v0.4.0 we accept that the table shows all intents and the user filters
        # mentally; this is documented as a known limitation in the CHANGELOG.

        resolve = resolve_index.get(r["id"])
        if resolve:
            honored = resolve["honored"]
            if honored == "true":
                status = "honored"
            elif honored == "false":
                status = "refused"
            elif honored == "partial":
                status = "partial"
            else:
                status = "honored"  # unknown honored value — treat as resolved
        else:
            status = "open"

        rows.append({
            "id": r["id"],
            "what": what[:60] + ("..." if len(what) > 60 else ""),
            "status": status,
            "resolve_id": resolve["resolve_id"] if resolve else "—",
        })

    # Apply status filter.
    if status_filter:
        rows = [r for r in rows if r["status"] == status_filter]

    # Apply limit.
    rows = rows[:limit]

    if not rows:
        suffix = f" with status={status_filter}" if status_filter else ""
        print(f"(no intents found{suffix})")
        return 0

    # Print table.
    suffix = f" [status={status_filter}]" if status_filter else ""
    print(f"\nIntents{suffix} — {len(rows)} result(s) — handle filter: see known-gap note\n")
    col = {"id": 32, "what": 50, "status": 8, "resolve_id": 32}
    header = (
        f"{'ID':<{col['id']}}  "
        f"{'WHAT':<{col['what']}}  "
        f"{'STATUS':<{col['status']}}  "
        f"{'RESOLVE':<{col['resolve_id']}}"
    )
    print(header)
    print("-" * len(header))
    for r in rows:
        print(
            f"{r['id']:<{col['id']}}  "
            f"{r['what']:<{col['what']}}  "
            f"{r['status']:<{col['status']}}  "
            f"{str(r['resolve_id']):<{col['resolve_id']}}"
        )
    print()
    return 0
