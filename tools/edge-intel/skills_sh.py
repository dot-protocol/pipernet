"""
skills_sh — poll skills.sh sitemap for newly-published agent skills.

skills.sh (github.com/vercel-labs/skills, 18k★) is the open agent-
skills marketplace. Anyone can publish a skill at
    <org>/<repo>/<skill-name>
Skills work across Claude Code, Cursor, Codex, Copilot, Windsurf,
Gemini, Cline, AMP, Antigravity, ClawdBot, Droid, Goose, Kilo,
Kiro CLI, Nous, OpenCode, Roo, Trae, VS Code.

We poll the sitemap, parse out the skill URLs, dedupe by full path,
and ingest each new skill into Oracle on the edge-intel channel.

Sidecar: /var/lib/edge-intel/skills_sh.jsonl
Oracle source tag: edge-intel-skills_sh
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError

from _common import (
    OracleClient,
    SidecarWriter,
    configure_logging,
    http_get_text,
)

# Two sitemap files; the second has the most recently-added skills at the tail
SITEMAPS = (
    "https://skills.sh/sitemap-skills-2.xml",
    "https://skills.sh/sitemap-skills-1.xml",
)
SIDECAR_PATH = "/var/lib/edge-intel/skills_sh.jsonl"
URL_RE = re.compile(r"<loc>https://skills\.sh/([^<]+)</loc>")


def parse_sitemap(xml_text: str) -> list[str]:
    """Return list of `org/repo/skill` paths (URL part after the host)."""
    return [m.group(1) for m in URL_RE.finditer(xml_text)]


def to_observation(path: str) -> dict:
    parts = path.split("/")
    if len(parts) != 3:
        return {}
    org, repo, skill = parts
    return {
        "content": (
            f"[skills.sh] new agent skill: {org}/{repo}/{skill}. "
            f"Install: `npx skills add {org}/{repo}/{skill}`. "
            f"Page: https://skills.sh/{path}"
        ),
        "type": "edge-signal",
        "rationale": (
            f"New agent skill on skills.sh marketplace: {skill} "
            f"(by {org}/{repo}). Works across Claude Code, Cursor, Codex, "
            f"and 15+ other agents via npx."
        ),
        "tags": [
            "edge-intel",
            "source:skills.sh",
            f"org:{org}",
            f"repo:{repo}",
            f"skill:{skill}",
        ],
        "confidence": 0.85,
    }


def to_sidecar(path: str) -> dict:
    parts = path.split("/")
    org, repo, skill = (parts + ["", "", ""])[:3]
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "source": "skills.sh",
        "org": org,
        "repo": repo,
        "skill": skill,
        "path": path,
        "url": f"https://skills.sh/{path}",
        "install": f"npx skills add {org}/{repo}/{skill}",
    }


def main() -> int:
    p = argparse.ArgumentParser(description="skills.sh → Oracle edge-intel feeder")
    p.add_argument("--interval", type=int, default=1800, help="poll seconds (default 1800 = 30 min)")
    p.add_argument("--batch", type=int, default=15)
    p.add_argument("--max-per-poll", type=int, default=40, help="cap new ingests per poll (skills.sh adds many at once)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args()

    log = configure_logging("edge-skills.sh", args.log_level)
    sidecar = SidecarWriter(SIDECAR_PATH)
    oracle = OracleClient("edge-intel-skills_sh", "pipernet-edge-intel-skills_sh/0.1")
    seen: set[str] = set()
    first_poll = True

    log.info("starting skills.sh poller; sitemaps=%s interval=%ds", SITEMAPS, args.interval)
    while True:
        try:
            new: list[str] = []
            for url in SITEMAPS:
                xml = http_get_text(url)
                for path in parse_sitemap(xml):
                    if path in seen:
                        continue
                    seen.add(path)
                    if len(path.split("/")) != 3:
                        continue
                    new.append(path)
            # On first poll: seed `seen` with everything but don't ingest (we'd
            # otherwise flood Oracle with thousands of historical skills).
            if first_poll:
                log.info("first poll: seeded %d existing skills (no ingest)", len(new))
                first_poll = False
                new = []
            if new:
                # Newest-last in the sitemap (typical); take the tail of what we
                # haven't seen, capped at max-per-poll.
                new = new[-args.max_per_poll:]
                log.info("found %d new skills (capped at %d)", len(new), args.max_per_poll)
                items = []
                for path in new:
                    sidecar.write(to_sidecar(path), log)
                    obs = to_observation(path)
                    if obs:
                        items.append(obs)
                if not args.dry_run:
                    for i in range(0, len(items), args.batch):
                        try:
                            r = oracle.ingest(items[i:i + args.batch], log)
                            log.info("ingested batch %d → %s", i // args.batch, str(r)[:140])
                        except (URLError, HTTPError, RuntimeError) as e:
                            log.warning("ingest batch failed (%s)", e)
            else:
                log.info("no new skills this poll")
            if len(seen) > 20000:
                seen = set(list(seen)[-10000:])
        except (URLError, HTTPError) as e:
            log.warning("fetch failed (%s)", e)
        except Exception:  # noqa: BLE001
            log.exception("unexpected error")
        try:
            time.sleep(args.interval)
        except KeyboardInterrupt:
            log.info("stopped")
            return 0


if __name__ == "__main__":
    sys.exit(main())
