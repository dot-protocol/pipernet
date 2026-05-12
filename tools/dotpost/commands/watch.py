"""
commands/watch — 'pipernet dotpost watch' subcommand.

Polls Oracle continuously for new dotposts using hash-based change detection.
Calls recv.fetch_inbox() on each interval and prints only when content changes.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from urllib.error import URLError, HTTPError

from ..tags import parse_groups_arg
from .recv import fetch_inbox


def cmd_watch(args: argparse.Namespace) -> int:
    """Execute the 'watch' subcommand.

    Polls every --interval seconds (min 10). Prints inbox content only when
    the hash changes, suppressing duplicate output. Ctrl-C to stop.
    Returns exit code (0 = clean stop).
    """
    me = args.for_handle or os.getenv("PIPERNET_HANDLE", "rocky")
    interval = max(10, int(args.interval))
    groups_str = getattr(args, "groups", None) or getattr(args, "subscribe", None)
    try:
        groups = parse_groups_arg(groups_str)
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
            text = fetch_inbox(me, groups)
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
