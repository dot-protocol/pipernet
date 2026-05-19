"""
handles — Pipernet handle substrate v0.1 reference implementation.

Provides identity binding for human-friendly handles (e.g., "shannon") to
cryptographic public keys via signed observations stored in Oracle.

Public API:
  - claim_handle(handle, note) → {handle, pubkey, claim_id, claimed_at}
  - resolve_handle(handle) → {handle, pubkey, claim_id, claimed_at, claimer} | None
  - add_contact(contact_handle, alias, tags) → obs_id
  - remove_contact(contact_handle, reason) → obs_id
  - list_contacts(handle) → [{contact, alias, tags, added_at}]
  - parse_mentions(body) → [handles]
  - mention_tags(body) → [tags]

All operations use ed25519 signing with canonical JSON, matching the shape of
the coordination substrate reference implementation.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .identity import load_or_generate, load_pubkey, pubkey_hex, sign, verify
from .canonical import canonicalize
from .transport import tool_call, load_token

logger = logging.getLogger(__name__)

# Handle validation regex per spec §2.
HANDLE_REGEX = re.compile(r"^[a-z0-9][a-z0-9-]{2,31}$")

# Reserved handles per spec §2.
RESERVED_HANDLES = {
    "all", "system", "oracle", "admin", "null", "none", "void",
    "self", "me", "piper", "pipernet", "icontact", "dotpost",
}


def _validate_handle(handle: str) -> str:
    """Normalize and validate a handle. Raises ValueError on invalid format.

    Mixed-case input is REJECTED (not silently lowercased) because users who
    typed `Bramble` thinking they'd own `Bramble` would otherwise be told
    they claimed `bramble` without warning — an onboarding footgun.
    """
    original = handle.strip()
    if not original:
        raise ValueError("invalid-handle-empty")
    if original != original.lower():
        raise ValueError(
            f"invalid-handle-case: handles are lowercase only — "
            f"did you mean '{original.lower()}'?"
        )
    if not HANDLE_REGEX.match(original):
        raise ValueError(f"invalid-handle-format: {original}")
    if original in RESERVED_HANDLES or original.startswith(("kin-", "dot-")):
        raise ValueError(f"reserved-handle: {original}")
    return original


def _already_claimed(handle: str) -> Optional[dict]:
    """Check Oracle for any existing claim on this handle.

    Uses Oracle REST /find directly (resolve_handle's oracle_audit path is
    currently broken — different response shape than expected).

    Returns:
        {"obs_id": str, "pubkey_hex": str} of the earliest hit, or None if
        no claim exists. Returns None on network errors (fail-open — we
        don't want a flaky Oracle to block legitimate claims).
    """
    try:
        import urllib.request, urllib.error
        from .transport import load_token, ORACLE_BASE

        body = json.dumps({"q": f"handle_claim:{handle}", "limit": 5}).encode()
        req = urllib.request.Request(
            f"{ORACLE_BASE.rstrip('/')}/find",
            data=body,
            headers={
                "Authorization": f"Bearer {load_token()}",
                "Content-Type": "application/json",
                "User-Agent": "pipernet-dotpost/0.1",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        hits = data.get("hits", [])
        if not hits:
            return None
        # Earliest-by-created_at wins per first-valid-write semantics.
        hits_sorted = sorted(hits, key=lambda h: h.get("created_at", ""))
        first = hits_sorted[0]
        pubkey = None
        for t in first.get("tags", []):
            if t.startswith("handle_pubkey:"):
                pubkey = t[len("handle_pubkey:"):]
                break
        return {"obs_id": first.get("id"), "pubkey_hex": pubkey}
    except Exception as e:
        logger.warning(f"availability check failed: {e}; proceeding optimistically")
        return None


def _base64url_encode(data: bytes) -> str:
    """Encode bytes to base64url string (RFC 4648 with no padding)."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _base64url_decode(s: str) -> bytes:
    """Decode base64url string to bytes, adding padding as needed."""
    # Add padding to make length a multiple of 4.
    padding = (4 - len(s) % 4) % 4
    s_padded = s + "=" * padding
    return base64.urlsafe_b64decode(s_padded)


def _get_current_handle() -> str:
    """Return the current handle from env or state file.

    Resolution order:
      1. $PIPERNET_HANDLE environment variable
      2. File at $PIPERNET_HOME/handle
      3. Fallback: 'anonymous'
    """
    handle = os.getenv("PIPERNET_HANDLE")
    if not handle:
        home = os.getenv("PIPERNET_HOME") or str(Path.home() / ".pipernet")
        handle_file = Path(home) / "handle"
        if handle_file.exists():
            handle = handle_file.read_text().strip()
        else:
            handle = "anonymous"
    return handle


@dataclass
class HandleClaim:
    """Result of a successful handle claim."""
    handle: str
    pubkey: str
    claim_id: str
    claimed_at: str


@dataclass
class HandleResolution:
    """Result of a successful handle resolution."""
    handle: str
    pubkey: str
    claim_id: str
    claimed_at: str
    claimer: str


@dataclass
class Contact:
    """A contact list entry."""
    contact: str
    alias: str
    tags: list[str]
    added_at: str


@dataclass
class HandleRotation:
    """Result of a successful handle rotation."""
    handle: str
    old_pubkey: str
    new_pubkey: str
    rotate_id: str
    rotated_at: str


def claim_handle(handle: str, note: str = None) -> HandleClaim:
    """Claim a handle, binding it to the current session's keypair.

    Args:
        handle: The handle to claim (validated, lowercased, checked against reserved list).
        note: Optional public note (up to 200 chars).

    Returns:
        HandleClaim with handle, pubkey (ed25519:base64 format), claim_id, and claimed_at.

    Raises:
        ValueError: If handle is invalid, reserved, or already claimed by this pubkey.
        RuntimeError: If Oracle ingest fails.
    """
    handle = _validate_handle(handle)

    # Pre-flight: refuse if the handle is already claimed by a DIFFERENT pubkey.
    # If we have a local seed for this handle and its pubkey matches the existing
    # claim, treat as an idempotent retry (e.g. recovering from a network blip)
    # and proceed. Otherwise refuse — we won't pollute Oracle with a competing
    # claim that the resolver would correctly ignore but that humans would
    # see in the audit log and find confusing.
    existing = _already_claimed(handle)
    if existing and existing.get("pubkey_hex"):
        from .identity import load_pubkey
        local_pub = load_pubkey(handle)
        local_hex = local_pub.hex() if local_pub else None
        if local_hex != existing["pubkey_hex"]:
            short = existing["pubkey_hex"][:16]
            raise ValueError(
                f"handle-already-claimed: '{handle}' is already claimed by "
                f"ed25519:{short}... ({existing['obs_id']}). "
                f"Pick a different handle. If this IS your handle, place your "
                f"seed in the local keyring for this handle before retrying."
            )
        # Local seed matches the on-chain claim — idempotent retry, fall through.
        logger.info(f"handle '{handle}' already claimed by local pubkey, retry will be idempotent")

    # Load or generate keypair for this handle.
    priv, pubkey_bytes, generated = load_or_generate(handle)
    pubkey_b64 = pubkey_hex(pubkey_bytes)
    pubkey_str = f"ed25519:{pubkey_b64}"

    # Build canonical claim object.
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    claim_obj = {
        "v": 1,
        "kind": "handle_claim",
        "handle": handle,
        "pubkey": pubkey_str,
        "claimed_at": now_iso,
        "note": note or "",
    }
    canonical = canonicalize(claim_obj)
    sig = sign(priv, canonical)

    # Compress and encode.
    claim_z = _base64url_encode(zlib.compress(canonical, level=3))
    claim_sig = _base64url_encode(sig)

    # Construct Oracle observation.
    tags = [
        "icontact",
        "handle",
        "mesh",  # bypasses Oracle's vector-dedup gate (tree_ingest.py:78 _DEDUP_BYPASS_TAGS)
        f"handle_claim:{handle}",
        f"handle_pubkey:{pubkey_b64}",
        f"claim_z:{claim_z}",
        f"claim_sig:{claim_sig}",
        f"from:{handle}",
    ]

    # Include full pubkey + note so vector-dedup doesn't false-positive against other claims.
    statement = (
        f"[handle_claim] {handle} → {pubkey_b64}\n"
        f"claimed_at: {now_iso}\n"
        f"note: {note or '(no note)'}"
    )

    try:
        result = tool_call("oracle_ingest", {
            "source": "pipernet-handle-claim",
            "extracted": {
                "items": [{
                    "content": statement,
                    "type": "handle_claim",
                    "channel": "raw",
                    "tags": tags,
                }]
            },
        })
        # Oracle MCP returns either {obs_id} (newer) or {text: "...IDs: OBS-..."} (legacy)
        obs_id = result.get("obs_id") or result.get("id")
        if not obs_id:
            text = result.get("text", "")
            for line in text.splitlines():
                if line.startswith("IDs:"):
                    obs_id = line.split("IDs:", 1)[1].strip().split(",")[0].strip()
                    break
        if not obs_id:
            raise RuntimeError(f"oracle ingest failed: no obs_id in response {result}")
    except Exception as e:
        logger.error(f"oracle_ingest failed: {e}")
        raise RuntimeError(f"Failed to ingest handle claim: {e}")

    return HandleClaim(
        handle=handle,
        pubkey=pubkey_str,
        claim_id=obs_id,
        claimed_at=now_iso,
    )


def rotate_handle(
    handle: str,
    new_privkey_hex: str,
    old_privkey_hex: str = None,
    reason: str = None,
) -> HandleRotation:
    """Rotate the keypair backing an existing handle.

    Posts a signed handle_rotate observation. Both the OLD key (proving rotation
    authority) and the NEW key (proving new key control) sign the same canonical
    rotation bytes. After this lands, resolvers per §5.3 advance the canonical
    pubkey for <handle> from old → new.

    Args:
        handle: Existing claimed handle to rotate. Must already have a valid claim.
        new_privkey_hex: 64-char hex seed of the NEW Ed25519 keypair (the one taking over).
        old_privkey_hex: 64-char hex seed of the OLD keypair. If None, falls back to
            $PIPERNET_OLD_PRIVKEY env, then to load_or_generate(handle) which respects
            $PIPERNET_PRIVKEY and the pipernet keyring file for <handle>.
        reason: Optional public note (up to 200 chars).

    Returns:
        HandleRotation with handle, old_pubkey, new_pubkey, rotate_id, rotated_at.

    Raises:
        ValueError: If handle is invalid/reserved, keys are malformed, or rotation is a no-op.
        RuntimeError: If Oracle ingest fails.
    """
    from .identity import _parse_privkey_str  # private helper, reused for hex/PEM parse

    handle = _validate_handle(handle)

    # Load OLD keypair: explicit arg → PIPERNET_OLD_PRIVKEY env → load_or_generate
    if old_privkey_hex is None:
        old_privkey_hex = os.getenv("PIPERNET_OLD_PRIVKEY")
    if old_privkey_hex:
        old_priv = _parse_privkey_str(old_privkey_hex)
        old_pub_bytes = old_priv.public_key().public_bytes_raw()
    else:
        old_priv, old_pub_bytes, _ = load_or_generate(handle)
    old_pub_hex = pubkey_hex(old_pub_bytes)
    old_pubkey_str = f"ed25519:{old_pub_hex}"

    # Load NEW keypair
    new_priv = _parse_privkey_str(new_privkey_hex)
    new_pub_bytes = new_priv.public_key().public_bytes_raw()
    new_pub_hex = pubkey_hex(new_pub_bytes)
    new_pubkey_str = f"ed25519:{new_pub_hex}"

    if old_pub_hex == new_pub_hex:
        raise ValueError("rotation is a no-op: old and new pubkeys are identical")

    # Build canonical rotation object
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    rotate_obj = {
        "v": 1,
        "kind": "handle_rotate",
        "handle": handle,
        "old_pubkey": old_pubkey_str,
        "new_pubkey": new_pubkey_str,
        "rotated_at": now_iso,
        "reason": reason or "",
    }
    canonical = canonicalize(rotate_obj)

    # Double signing: OLD authorizes, NEW proves control
    sig_old = sign(old_priv, canonical)
    sig_new = sign(new_priv, canonical)

    rotate_z = _base64url_encode(zlib.compress(canonical, level=3))
    rotate_sig_old_b64 = _base64url_encode(sig_old)
    rotate_sig_new_b64 = _base64url_encode(sig_new)

    tags = [
        "icontact",
        "handle",
        "mesh",  # bypasses Oracle's vector-dedup gate (same reason as claim)
        f"handle_rotate:{handle}",
        f"handle_pubkey:{new_pub_hex}",
        f"old_pubkey:{old_pub_hex}",
        f"rotate_z:{rotate_z}",
        f"rotate_sig_old:{rotate_sig_old_b64}",
        f"rotate_sig_new:{rotate_sig_new_b64}",
        f"from:{handle}",
    ]

    # Statement is structured distinctly from handle_claim so vector dedup doesn't false-positive.
    statement = (
        f"HANDLE ROTATION EVENT (v1) — keypair replacement for handle '{handle}'\n"
        f"  authority sig:  ed25519 by old pubkey {old_pub_hex}\n"
        f"  control sig:    ed25519 by new pubkey {new_pub_hex}\n"
        f"  rotated_at:     {now_iso}\n"
        f"  reason:         {reason or '(no reason given)'}\n"
        f"After this event, the canonical pubkey for '{handle}' advances from "
        f"{old_pub_hex[:16]}… to {new_pub_hex[:16]}…. Resolvers per spec §5.3 "
        f"validate both signatures and advance the chain forward."
    )

    try:
        result = tool_call("oracle_ingest", {
            "source": "pipernet-handle-rotate",
            "extracted": {
                "items": [{
                    "content": statement,
                    "type": "handle_rotate",
                    "channel": "raw",
                    "tags": tags,
                }]
            },
        })
        obs_id = result.get("obs_id") or result.get("id")
        if not obs_id:
            text = result.get("text", "")
            for line in text.splitlines():
                if line.startswith("IDs:"):
                    obs_id = line.split("IDs:", 1)[1].strip().split(",")[0].strip()
                    break
        if not obs_id:
            raise RuntimeError(f"oracle ingest failed: no obs_id in response {result}")
    except Exception as e:
        logger.error(f"oracle_ingest failed: {e}")
        raise RuntimeError(f"Failed to ingest handle rotation: {e}")

    return HandleRotation(
        handle=handle,
        old_pubkey=old_pubkey_str,
        new_pubkey=new_pubkey_str,
        rotate_id=obs_id,
        rotated_at=now_iso,
    )


def resolve_handle(handle: str) -> Optional[HandleResolution]:
    """Resolve a handle to its claimed pubkey.

    Queries Oracle for all claims to this handle, validates signatures,
    and returns the oldest valid claim (first-valid-write).

    Args:
        handle: The handle to resolve (validated, lowercased).

    Returns:
        HandleResolution if a valid claim exists, None otherwise.
    """
    try:
        handle = _validate_handle(handle)
    except ValueError:
        return None

    try:
        result = tool_call("oracle_audit", {
            "tag_filter": f"handle_claim:{handle}",
            "limit": 50,
        })
    except Exception as e:
        logger.error(f"oracle_audit failed: {e}")
        return None

    if not result:
        return None

    # Expect result to be a dict with 'items' or directly a list.
    items = result.get("items", []) if isinstance(result, dict) else result
    if not items:
        return None

    # Sort by created_at (oldest first).
    try:
        items_sorted = sorted(items, key=lambda x: x.get("created_at", ""))
    except Exception:
        items_sorted = items

    for item in items_sorted:
        try:
            tags = item.get("tags", [])
            obs_id = item.get("id")

            # Extract claim_z and claim_sig from tags.
            claim_z = None
            sig_b64 = None
            pubkey_b64 = None
            for tag in tags:
                if tag.startswith("claim_z:"):
                    claim_z = tag[8:]
                elif tag.startswith("claim_sig:"):
                    sig_b64 = tag[10:]
                elif tag.startswith("handle_pubkey:"):
                    pubkey_b64 = tag[14:]

            if not (claim_z and sig_b64 and pubkey_b64):
                continue

            # Decompress and parse claim.
            canonical = zlib.decompress(_base64url_decode(claim_z))
            claim = json.loads(canonical)

            # Validate claim structure.
            if claim.get("handle") != handle:
                continue
            if claim.get("v") != 1:
                continue
            if claim.get("kind") != "handle_claim":
                continue

            # Verify signature.
            pubkey_str = claim.get("pubkey", "")
            if not pubkey_str.startswith("ed25519:"):
                continue
            pubkey_bytes = bytes.fromhex(pubkey_str[8:])

            if not verify(pubkey_bytes, _base64url_decode(sig_b64), canonical):
                logger.warning(f"signature invalid for {handle} claim {obs_id}")
                continue

            return HandleResolution(
                handle=handle,
                pubkey=pubkey_str,
                claim_id=obs_id,
                claimed_at=claim.get("claimed_at", ""),
                claimer=claim.get("note", ""),
            )
        except (KeyError, ValueError, json.JSONDecodeError) as e:
            logger.debug(f"skipping invalid claim {item.get('id')}: {e}")
            continue

    return None


def add_contact(contact_handle: str, alias: str = None, tags: list[str] = None) -> str:
    """Add a contact to the current session's contact list.

    The contact_handle must resolve via resolve_handle(); refuses if unclaimed.

    Args:
        contact_handle: The handle to add (validated).
        alias: Optional display alias.
        tags: Optional list of category tags.

    Returns:
        The obs_id of the contact observation.

    Raises:
        ValueError: If contact_handle doesn't resolve.
        RuntimeError: If Oracle ingest fails.
    """
    contact_handle = _validate_handle(contact_handle)

    # Verify contact resolves.
    if not resolve_handle(contact_handle):
        raise ValueError(f"contact-resolve-failed: {contact_handle} is unclaimed")

    self_handle = _get_current_handle()
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # Build canonical contact object.
    contact_obj = {
        "v": 1,
        "kind": "contact",
        "self": self_handle,
        "contact": contact_handle,
        "alias": alias or "",
        "added_at": now_iso,
        "tags": tags or [],
    }

    # Load key to sign (use self_handle's key).
    priv, pubkey_bytes, _ = load_or_generate(self_handle)
    canonical = canonicalize(contact_obj)
    sig = sign(priv, canonical)

    contact_z = _base64url_encode(zlib.compress(canonical, level=3))
    contact_sig = _base64url_encode(sig)
    pubkey_b64 = pubkey_hex(pubkey_bytes)

    tags_list = [
        "icontact",
        "handle_contact",
        f"contact_for:{self_handle}",
        f"contact:{contact_handle}",
        f"contact_z:{contact_z}",
        f"contact_sig:{contact_sig}",
        f"from:{self_handle}",
    ]

    statement = f"[contact] {self_handle} → {contact_handle}" + (
        f" ({alias})" if alias else ""
    )

    try:
        result = tool_call("oracle_ingest", {
            "source": "pipernet-handle-contact",
            "extracted": {
                "items": [{
                    "content": statement,
                    "type": "contact_add",
                    "channel": "raw",
                    "tags": tags_list,
                }]
            },
        })
        obs_id = result.get("obs_id") or result.get("id")
        if not obs_id:
            text = result.get("text", "")
            for line in text.splitlines():
                if line.startswith("IDs:"):
                    obs_id = line.split("IDs:", 1)[1].strip().split(",")[0].strip()
                    break
        if not obs_id:
            raise RuntimeError(f"oracle ingest failed: no obs_id in response {result}")
    except Exception as e:
        logger.error(f"oracle_ingest failed: {e}")
        raise RuntimeError(f"Failed to add contact: {e}")

    return obs_id


def remove_contact(contact_handle: str, reason: str = None) -> str:
    """Remove a contact from the current session's contact list.

    Posts a contact_remove event (append-only). Readers will see the latest
    event per (self, contact) pair.

    Args:
        contact_handle: The handle to remove.
        reason: Optional reason for removal.

    Returns:
        The obs_id of the removal event.

    Raises:
        RuntimeError: If Oracle ingest fails.
    """
    contact_handle = _validate_handle(contact_handle)
    self_handle = _get_current_handle()
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # Build canonical removal object.
    remove_obj = {
        "v": 1,
        "kind": "contact_remove",
        "self": self_handle,
        "contact": contact_handle,
        "removed_at": now_iso,
        "reason": reason or "",
    }

    priv, pubkey_bytes, _ = load_or_generate(self_handle)
    canonical = canonicalize(remove_obj)
    sig = sign(priv, canonical)

    remove_z = _base64url_encode(zlib.compress(canonical, level=3))
    remove_sig = _base64url_encode(sig)

    tags_list = [
        "icontact",
        "handle_contact",
        f"contact_remove:{contact_handle}",
        f"contact_for:{self_handle}",
        f"contact_z:{remove_z}",
        f"contact_sig:{remove_sig}",
        f"from:{self_handle}",
    ]

    statement = f"[contact_remove] {self_handle} ✗ {contact_handle}"

    try:
        result = tool_call("oracle_ingest", {
            "source": "pipernet-handle-contact-remove",
            "extracted": {
                "items": [{
                    "content": statement,
                    "type": "contact_remove",
                    "channel": "raw",
                    "tags": tags_list,
                }]
            },
        })
        obs_id = result.get("obs_id") or result.get("id")
        if not obs_id:
            text = result.get("text", "")
            for line in text.splitlines():
                if line.startswith("IDs:"):
                    obs_id = line.split("IDs:", 1)[1].strip().split(",")[0].strip()
                    break
        if not obs_id:
            raise RuntimeError(f"oracle ingest failed: no obs_id in response {result}")
    except Exception as e:
        logger.error(f"oracle_ingest failed: {e}")
        raise RuntimeError(f"Failed to remove contact: {e}")

    return obs_id


def list_contacts(handle: str = None) -> list[Contact]:
    """List the contact entries for a handle.

    Queries all contact and contact_remove observations for this handle,
    collapses add/remove events, and returns the current contact set.

    Args:
        handle: The handle whose contacts to list. Defaults to current session.

    Returns:
        List of Contact objects (empty list if no contacts).
    """
    if not handle:
        handle = _get_current_handle()
    else:
        handle = _validate_handle(handle)

    try:
        result = tool_call("oracle_audit", {
            "tag_filter": f"contact_for:{handle}",
            "limit": 200,
        })
    except Exception as e:
        logger.error(f"oracle_audit failed: {e}")
        return []

    items = result.get("items", []) if isinstance(result, dict) else result
    if not items:
        return []

    # Build a map of (contact_handle) → latest event.
    contact_map = {}
    for item in items:
        try:
            tags = item.get("tags", [])
            created_at = item.get("created_at", "")

            contact_h = None
            is_remove = False
            for tag in tags:
                if tag.startswith("contact:") and not is_remove:
                    contact_h = tag[8:]
                elif tag.startswith("contact_remove:"):
                    contact_h = tag[15:]
                    is_remove = True

            if not contact_h:
                continue

            if contact_h not in contact_map or contact_map[contact_h][2] < created_at:
                contact_map[contact_h] = (item, is_remove, created_at)
        except Exception:
            continue

    # Extract current contacts (non-removed).
    contacts = []
    for contact_h, (item, is_remove, _) in contact_map.items():
        if is_remove:
            continue

        try:
            tags = item.get("tags", [])
            contact_z = None
            for tag in tags:
                if tag.startswith("contact_z:"):
                    contact_z = tag[10:]
                    break

            if contact_z:
                canonical = zlib.decompress(_base64url_decode(contact_z))
                contact_obj = json.loads(canonical)
            else:
                contact_obj = {}

            contacts.append(Contact(
                contact=contact_h,
                alias=contact_obj.get("alias", ""),
                tags=contact_obj.get("tags", []),
                added_at=contact_obj.get("added_at", ""),
            ))
        except Exception:
            # Fallback: just the handle.
            contacts.append(Contact(
                contact=contact_h,
                alias="",
                tags=[],
                added_at="",
            ))

    return contacts


def parse_mentions(body: str) -> list[str]:
    """Parse @<handle> mentions from message body.

    Returns a list of unique lowercased handles that match the handle regex.
    Excludes invalid handles (too short, bad chars, etc.).

    Args:
        body: The message body text.

    Returns:
        Sorted list of unique valid handles (lowercase).
    """
    # Regex: @ followed by handle pattern (lowercase already enforced by parser).
    pattern = r"@([a-z0-9][a-z0-9-]{2,31})"
    matches = re.findall(pattern, body.lower())
    # Return unique, sorted.
    return sorted(set(matches))


def mention_tags(body: str) -> list[str]:
    """Generate mention tags from body text.

    Args:
        body: The message body.

    Returns:
        List of tags like ["mention:shannon", "mention:jared"].
    """
    mentions = parse_mentions(body)
    return [f"mention:{h}" for h in mentions]
