"""
canonical — RFC 8785 subset JSON canonicalization.

Produces deterministic bytes suitable for ed25519 signing.

Canonical form rules (subset of RFC 8785):
  1. Keys sorted lexicographically (Unicode code-point order, byte by byte).
  2. No whitespace (no spaces, no newlines between tokens).
  3. UTF-8 encoding throughout.
  4. No trailing commas (standard JSON).
  5. Double-quote delimiters for strings.
  6. Numbers use standard Python JSON representation (no trailing zeros).

This module is intentionally dependency-free (stdlib json only).
"""
from __future__ import annotations

import json
from typing import Any


def canonicalize(obj: Any) -> bytes:
    """Return the canonical JSON encoding of obj as UTF-8 bytes.

    Keys in dicts are sorted lexicographically. No whitespace is emitted.
    Nested dicts/lists are recursively sorted.

    This is the payload that must be signed / verified. Two callers
    passing the same logical object will always produce identical bytes.
    """
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
