"""
tags — tag construction, validation, and parsing helpers.

All functions are pure (no I/O). They operate on strings and lists only.

Tag grammar used by icontact / dotpost:
  from:<handle>         sender identity
  to:<handle>           DM recipient
  to:all                broadcast
  to:group:<name>       group message
  group:<name>          secondary group index
  mesh                  marks the observation as a mesh message
  broadcast             marks to:all observations explicitly
  reply                 marks a reply message
  in_reply_to:<obs_id>  thread parent reference
  intent:<b64>          signed intent payload (intent substrate v0.1, uncompressed)
  intent_sig:<b64>      ed25519 signature over canonical intent bytes
  intent_z:<b64>        signed + zstd-compressed intent payload (intent substrate v0.2)
  resolve:<b64>         signed resolve payload (v0.1, uncompressed)
  resolve_sig:<b64>     ed25519 signature over canonical resolve bytes
  resolve_z:<b64>       signed + zstd-compressed resolve payload (v0.2)
  resolves_intent:<id>  back-reference from resolve to intent obs_id
"""
from __future__ import annotations

import re

# Group names: lowercase alphanumeric + dashes, must start with alphanumeric.
_GROUP_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

BROADCAST_HANDLE = "all"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_group_name(name: str) -> str:
    """Return name if it matches ^[a-z0-9][a-z0-9-]*$, else raise ValueError."""
    if not _GROUP_NAME_RE.match(name):
        raise ValueError(
            f"Invalid group name {name!r}. "
            "Group names must match ^[a-z0-9][a-z0-9-]*$ "
            "(lowercase alphanumeric + dashes, starting with alphanumeric)."
        )
    return name


def parse_to_arg(to_value: str) -> tuple[str, str | None]:
    """Parse a --to argument into (routing_mode, value).

    routing_mode is one of 'handle', 'group', 'broadcast'.
    value is the group name or handle string; None for broadcast.

    Raises ValueError for invalid group names.
    """
    if to_value == BROADCAST_HANDLE:
        return ("broadcast", None)
    if to_value.startswith("group:"):
        group_name = to_value[len("group:"):]
        validate_group_name(group_name)
        return ("group", group_name)
    return ("handle", to_value)


def parse_groups_arg(groups_str: str | None) -> list[str]:
    """Parse a comma-separated groups string into a validated name list.

    Returns [] if groups_str is None or empty.
    Raises ValueError for any invalid group name.
    """
    if not groups_str:
        return []
    names = [g.strip() for g in groups_str.split(",") if g.strip()]
    return [validate_group_name(g) for g in names]


def parse_comma_list(value: str | None) -> list[str]:
    """Split a comma-separated string into a stripped, non-empty item list.

    Returns [] for None or empty input.
    """
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


# ---------------------------------------------------------------------------
# Tag construction
# ---------------------------------------------------------------------------

def build_send_tags(
    sender: str,
    recipient: str,
    *,
    reply_to: str | None = None,
    extra: list[str] | None = None,
) -> list[str]:
    """Build tag list for a DM or broadcast dotpost observation.

    sender: the from-handle.
    recipient: the to-handle (use BROADCAST_HANDLE for broadcasts).
    reply_to: optional parent obs_id (adds 'reply' + 'in_reply_to:<id>').
    extra: optional additional tags appended at the end.
    """
    is_broadcast = recipient == BROADCAST_HANDLE
    tags: list[str] = ["dotpost", f"from:{sender}", f"to:{recipient}", "mesh"]
    if is_broadcast:
        tags.append("broadcast")
    if reply_to:
        tags.append("reply")
        tags.append(f"in_reply_to:{reply_to}")
    if extra:
        tags.extend(extra)
    return tags


def build_group_tags(
    sender: str,
    group_name: str,
    *,
    reply_to: str | None = None,
) -> list[str]:
    """Build tag list for a group dotpost observation.

    Validates group_name before use; raises ValueError on invalid input.
    """
    validate_group_name(group_name)
    tags: list[str] = [
        "dotpost",
        f"from:{sender}",
        f"to:group:{group_name}",
        f"group:{group_name}",
        "mesh",
        "group-post",
    ]
    if reply_to:
        tags.append("reply")
        tags.append(f"in_reply_to:{reply_to}")
    return tags


def build_intent_tags(
    sender: str,
    intent_b64: str,
    sig_b64: str,
    *,
    addressed_to: str = "all",
    context_refs: list[str] | None = None,
) -> list[str]:
    """Build tag list for an intent dotpost observation.

    intent_b64: base64url-encoded canonical JSON of the intent object.
    sig_b64: base64url-encoded ed25519 signature over those canonical bytes.
    addressed_to: routing target (handle, 'all', or 'group:<name>').
    context_refs: optional list of obs_ids / blob refs to tag as context.
    """
    tags: list[str] = [
        "dotpost",
        "intent",
        f"from:{sender}",
        f"to:{addressed_to}",
        f"intent:{intent_b64}",
        f"intent_sig:{sig_b64}",
        "mesh",
    ]
    for ref in (context_refs or []):
        tags.append(f"context_ref:{ref}")
    return tags


def build_resolve_tags(
    resolver: str,
    resolve_b64: str,
    sig_b64: str,
    intent_id: str,
    *,
    addressed_to: str = "all",
) -> list[str]:
    """Build tag list for a resolve dotpost observation.

    resolver: the from-handle of the resolver.
    resolve_b64: base64url-encoded canonical JSON of the resolve object.
    sig_b64: base64url-encoded ed25519 signature over those canonical bytes.
    intent_id: the obs_id of the intent being resolved.
    addressed_to: routing target (typically the original intent sender).
    """
    return [
        "dotpost",
        "resolve",
        f"from:{resolver}",
        f"to:{addressed_to}",
        f"resolve:{resolve_b64}",
        f"resolve_sig:{sig_b64}",
        f"resolves_intent:{intent_id}",
        "mesh",
    ]


def build_intent_z_tags(
    sender: str,
    compressed_b64: str,
    sig_b64: str,
    *,
    addressed_to: str = "all",
    context_refs: list[str] | None = None,
) -> list[str]:
    """Build tag list for a v0.5.0 compressed intent dotpost observation.

    Mirrors build_intent_tags() but uses the intent_z: tag prefix.
    The signature is over canonical JSON, not the compressed bytes.

    compressed_b64: base64url(zstd(canonical_json)) — from Intent.to_compressed_b64().
    sig_b64: base64url(ed25519_sig_over_canonical).
    addressed_to: routing target (handle, 'all', or 'group:<name>').
    context_refs: optional list of obs_ids / blob refs to tag as context.
    """
    tags: list[str] = [
        "dotpost",
        "intent",
        f"from:{sender}",
        f"to:{addressed_to}",
        f"intent_z:{compressed_b64}",
        f"intent_sig:{sig_b64}",
        "mesh",
    ]
    for ref in (context_refs or []):
        tags.append(f"context_ref:{ref}")
    return tags


def build_resolve_z_tags(
    resolver: str,
    compressed_b64: str,
    sig_b64: str,
    intent_id: str,
    *,
    addressed_to: str = "all",
) -> list[str]:
    """Build tag list for a v0.5.0 compressed resolve dotpost observation.

    Mirrors build_resolve_tags() but uses the resolve_z: tag prefix.

    resolver: the from-handle of the resolver.
    compressed_b64: base64url(zstd(canonical_json)) — from Resolve.to_compressed_b64().
    sig_b64: base64url(ed25519_sig_over_canonical).
    intent_id: the obs_id of the intent being resolved.
    addressed_to: routing target.
    """
    return [
        "dotpost",
        "resolve",
        f"from:{resolver}",
        f"to:{addressed_to}",
        f"resolve_z:{compressed_b64}",
        f"resolve_sig:{sig_b64}",
        f"resolves_intent:{intent_id}",
        "mesh",
    ]
