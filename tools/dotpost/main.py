"""
pipernet dotpost — mesh communication via Oracle.

Entry point. Supports two invocation modes:
  python3 main.py <subcommand> ...        (direct script, VPS cron)
  python3 -m dotpost <subcommand> ...     (module mode)

All logic lives in the package modules:
  cli.py        — argparse + dispatch
  transport.py  — Oracle MCP transport
  tags.py       — tag construction + validation
  canonical.py  — RFC 8785 JSON canonicalization
  identity.py   — Ed25519 keypair load/generate/sign/verify
  intent.py     — Intent + Resolve dataclasses (v0.1 spec)
  commands/     — one file per subcommand

Usage:
    python3 main.py send --to <handle> --body "<text>"
    python3 main.py broadcast --body "<text>"
    python3 main.py group --to <group> --body "<text>"
    python3 main.py recv [--for <handle>]
    python3 main.py watch [--for <handle>]
    python3 main.py intent --what "<text>" [--to <handle>]
    python3 main.py resolve --intent-id <obs_id> --honored true|false|partial
    python3 main.py intents --for <handle> [--status open|honored|refused|expired]
"""
from __future__ import annotations

import sys
import os

# Support both `python3 main.py` (script mode) and `python3 -m dotpost` (package mode).
# When run as a script, __package__ is None and relative imports fail.
# Fix: insert the parent dir so absolute-style imports resolve.
if __name__ == "__main__" and __package__ in (None, ""):
    _pkg_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _pkg_parent not in sys.path:
        sys.path.insert(0, _pkg_parent)
    from dotpost.cli import main
else:
    from .cli import main

if __name__ == "__main__":
    sys.exit(main())
