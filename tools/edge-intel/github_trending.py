"""
github_trending — pollers OSS Insight for trending GitHub repos.

OSS Insight (https://ossinsight.io, by PingCAP) maintains a free
public API backed by ~10B rows of GH event data. We poll every
5 minutes and ingest each newly-seen trending repo into Oracle.

Endpoint:
    GET https://api.ossinsight.io/v1/trends/repos/?period=past_24_hours&language=All

Returns a JSON `data.rows` with: repo_name, description, primary_language,
stars, forks, total_score, etc.

Sidecar: /var/lib/edge-intel/github.jsonl
Oracle source tag: edge-intel-github
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError

from _common import (
    OracleClient,
    SidecarWriter,
    configure_logging,
    http_get_json,
)

ENDPOINT = (
    "https://api.ossinsight.io/v1/trends/repos/?period=past_24_hours&language=All"
)
SIDECAR_PATH = "/var/lib/edge-intel/github.jsonl"


def parse_rows(body: dict) -> list[dict]:
    """OSS Insight returns {data: {rows: [{...}]}} with snake_case keys."""
    return list(body.get("data", {}).get("rows", []))


def to_item(row: dict) -> dict:
    """Shape a row into the canonical edge-signal observation."""
    repo = row.get("repo_name", "")
    desc = (row.get("description") or "").strip()
    lang = row.get("primary_language", "")
    stars = int(row.get("stars", 0) or 0)
    forks = int(row.get("forks", 0) or 0)
    score = row.get("total_score", "")
    text = f"[github] {repo} — {desc or '(no description)'} (★ {stars}, lang: {lang or 'n/a'})"
    tags = [
        "edge-intel",
        "source:github",
        f"repo:{repo}",
        f"lang:{lang or 'n/a'}",
        f"stars:{stars}",
    ]
    return {
        "content": text,
        "type": "edge-signal",
        "rationale": (
            f"GitHub trending repo {repo} (OSS Insight 24h). "
            f"{stars} stars, {forks} forks, score {score}."
        ),
        "tags": tags,
        "confidence": 0.85,
    }


def to_sidecar(row: dict) -> dict:
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "source": "github",
        "repo": row.get("repo_name", ""),
        "uri": f"https://github.com/{row.get('repo_name', '')}",
        "description": (row.get("description") or "").strip(),
        "language": row.get("primary_language", ""),
        "stars": int(row.get("stars", 0) or 0),
        "forks": int(row.get("forks", 0) or 0),
        "score": row.get("total_score", ""),
    }


def main() -> int:
    p = argparse.ArgumentParser(description="GitHub trending → Oracle edge-intel feeder")
    p.add_argument("--interval", type=int, default=300, help="poll seconds (default 300 = 5 min)")
    p.add_argument("--batch", type=int, default=15, help="max items per Oracle ingest call")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args()

    log = configure_logging("edge-github", args.log_level)
    sidecar = SidecarWriter(SIDECAR_PATH)
    oracle = OracleClient("edge-intel-github", "pipernet-edge-intel-github/0.1")
    seen: set[str] = set()

    log.info("starting github trending poller; endpoint=%s interval=%ds", ENDPOINT, args.interval)
    while True:
        try:
            body = http_get_json(ENDPOINT)
            rows = parse_rows(body)
            new = []
            for row in rows:
                repo = row.get("repo_name") or ""
                if not repo or repo in seen:
                    continue
                seen.add(repo)
                sidecar.write(to_sidecar(row), log)
                new.append(to_item(row))
            if new:
                log.info("found %d new trending repos", len(new))
                if not args.dry_run:
                    for i in range(0, len(new), args.batch):
                        try:
                            r = oracle.ingest(new[i:i + args.batch], log)
                            log.info("ingested batch of %d → %s", min(args.batch, len(new) - i), str(r)[:140])
                        except (URLError, HTTPError, RuntimeError) as e:
                            log.warning("ingest batch failed (%s)", e)
            else:
                log.info("no new trending repos this poll")
            # Bound memory: keep last 500 seen
            if len(seen) > 500:
                seen = set(list(seen)[-300:])
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
