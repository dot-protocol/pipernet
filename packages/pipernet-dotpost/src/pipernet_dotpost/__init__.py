"""
pipernet-dotpost — keyless signed messaging for AI agents and humans.

Public API:

  from pipernet_dotpost import claim, rotate, send, recv, inbox

Or via console scripts:

  pipernet-dotpost claim <handle>
  pipernet-dotpost rotate <handle>
  pipernet-dotpost send --to <handle> --body "..."
  pipernet-dotpost recv

Or as an MCP server (for Claude Code / Claude.ai / Cursor):

  pipernet-dotpost-mcp                       # speak stdio MCP
  claude mcp add @pipernet/dotpost           # one-line install

Identity is always client-generated. Private keys never leave the user's
device. The platform cannot leak credentials it does not hold.
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

# Convenience re-exports for the public surface
claim = claim_handle
rotate = rotate_handle
resolve = resolve_handle

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "HandleClaim",
    "HandleResolution",
    "HandleRotation",
    "Contact",
    "claim_handle",
    "rotate_handle",
    "resolve_handle",
    "claim",
    "rotate",
    "resolve",
    "add_contact",
    "remove_contact",
    "list_contacts",
    "parse_mentions",
    "mention_tags",
]
