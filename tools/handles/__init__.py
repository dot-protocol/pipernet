"""
handles — Pipernet handle substrate v0.1 reference implementation.

Public API for binding human-friendly handles to cryptographic identities
via signed observations stored in Oracle.

Example usage:
    from pipernet.tools.handles import claim_handle, resolve_handle, add_contact

    # Claim a handle
    result = claim_handle("shannon", note="primary builder session")
    print(result.pubkey)  # ed25519:...

    # Resolve a handle
    res = resolve_handle("jared")
    if res:
        print(f"jared → {res.pubkey}")

    # Add a contact
    contact_id = add_contact("jared", alias="Jared (iPhone)")

    # Parse mentions
    from pipernet.tools.handles import parse_mentions
    handles = parse_mentions("hey @shannon and @jared, discuss?")
"""

from .handles import (
    HandleClaim,
    HandleResolution,
    HandleRotation,
    Contact,
    claim_handle,
    rotate_handle,
    resolve_handle,
    add_contact,
    remove_contact,
    list_contacts,
    parse_mentions,
    mention_tags,
)

__all__ = [
    "HandleClaim",
    "HandleResolution",
    "HandleRotation",
    "Contact",
    "claim_handle",
    "rotate_handle",
    "resolve_handle",
    "add_contact",
    "remove_contact",
    "list_contacts",
    "parse_mentions",
    "mention_tags",
]
