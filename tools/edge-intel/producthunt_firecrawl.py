"""
producthunt_firecrawl — scrape ProductHunt's daily leaderboard via Firecrawl.

ProductHunt blocks vanilla HTTP scrapers with 403 and their RSS feed
is dead (returns 0 items as of 2026-05-12; community mirror at
headllines/producthunt-daily-rss is stale since 2021). The only
free-tier-friendly path is a hosted headless-browser scraper.

This poller uses firecrawl.dev (v2 API) to fetch the leaderboard
as markdown, then parses out product entries.

Environment:
    FIRECRAWL_API_KEY   — required. Get one at https://firecrawl.dev
                          (free tier 500 scrapes/mo).
    PH_LEADERBOARD_URL  — optional. Defaults to
                          https://www.producthunt.com/leaderboard/daily/

If FIRECRAWL_API_KEY is unset the poller logs a one-line warning
and idles. No noisy retries.

Sidecar: /var/lib/edge-intel/producthunt.jsonl
Oracle source tag: edge-intel-producthunt
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from _common import (
    OracleClient,
    SidecarWriter,
    configure_logging,
)

PH_URL = os.getenv("PH_LEADERBOARD_URL", "https://www.producthunt.com/leaderboard/daily/")
FIRECRAWL_URL = "https://api.firecrawl.dev/v2/scrape"
SIDECAR_PATH = "/var/lib/edge-intel/producthunt.jsonl"


def firecrawl_scrape(target: str, api_key: str, timeout: int = 60) -> dict:
    """Call Firecrawl v2 /scrape, return parsed response."""
    payload = {
        "url": target,
        "formats": ["markdown"],
        "onlyMainContent": True,
        "waitFor": 2000,
    }
    req = Request(
        FIRECRAWL_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "pipernet-edge-intel-producthunt/0.1 (+https://piedpiper.fun)",
        },
        method="POST",
    )
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# Match a PH product entry in markdown. Patterns observed:
#   "1. **Product Name** — Tagline ([link](URL)) · 234 upvotes"
#   "## Product Name\nTagline (URL)\n234 upvotes"
# We capture liberally and let downstream cleanup happen.
PRODUCT_RE = re.compile(
    r"(?:^|\n)\s*(?:#{1,3}\s+|\d+\.\s+\**)([A-Z][^\n*•\[]{1,80}?)\s*"
    r"(?:[—–\-]\s*([^\n*•\[]{3,200}?))?"
    r"(?:[\s\S]{0,80}?(\d{1,5})\s*(?:upvotes?|points?|▲))?",
    re.MULTILINE,
)
URL_RE = re.compile(r"https?://(?:www\.)?producthunt\.com/posts/[a-z0-9-]+")


def parse_markdown(markdown: str) -> list[dict]:
    """Extract product candidates from firecrawl's markdown blob.

    Conservative: only emit entries that look like real products
    (title-cased name, plausible upvote count, or a producthunt.com/posts/
    URL nearby).
    """
    products: list[dict] = []
    seen_names: set[str] = set()
    # Collect post URLs in scan order so we can pair them with nearby names
    post_urls = URL_RE.findall(markdown)
    url_iter = iter(post_urls)

    for m in PRODUCT_RE.finditer(markdown):
        name = (m.group(1) or "").strip().rstrip(":–—-")
        tagline = (m.group(2) or "").strip() if m.group(2) else ""
        votes_str = m.group(3) or "0"
        # Skip navigation chrome and footer headings
        if not name or len(name) < 2 or name.lower() in (
            "today", "yesterday", "this week", "this month", "subscribe",
            "newsletter", "log in", "sign in", "product hunt", "leaderboard",
            "categories", "topics", "about", "advertise", "help",
        ):
            continue
        if name in seen_names:
            continue
        seen_names.add(name)
        try:
            votes = int(votes_str)
        except ValueError:
            votes = 0
        url = next(url_iter, "")
        products.append({
            "name": name,
            "tagline": tagline,
            "upvotes": votes,
            "url": url,
        })
        if len(products) >= 20:
            break
    return products


def to_observation(p: dict) -> dict:
    name = p["name"]
    tagline = p["tagline"]
    votes = p["upvotes"]
    url = p["url"]
    text = f"[producthunt] {name}"
    if tagline:
        text += f" — {tagline}"
    if votes:
        text += f" (▲ {votes})"
    tags = ["edge-intel", "source:producthunt", f"product:{name[:40]}"]
    if votes:
        tags.append(f"upvotes:{votes}")
    return {
        "content": text,
        "type": "edge-signal",
        "rationale": (
            f"ProductHunt daily leaderboard entry: {name}"
            f"{' (' + str(votes) + ' upvotes)' if votes else ''}."
            f"{' ' + url if url else ''}"
        ),
        "tags": tags,
        "confidence": 0.85,
    }


def to_sidecar(p: dict, raw_excerpt: str = "") -> dict:
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "source": "producthunt",
        "name": p["name"],
        "tagline": p["tagline"],
        "upvotes": p["upvotes"],
        "url": p["url"],
        **({"raw": raw_excerpt[:200]} if raw_excerpt else {}),
    }


def main() -> int:
    p = argparse.ArgumentParser(description="ProductHunt → Oracle edge-intel (firecrawl-backed)")
    p.add_argument("--interval", type=int, default=3600, help="poll seconds (default 3600 = 1 hour; firecrawl free tier is 500/mo)")
    p.add_argument("--batch", type=int, default=10)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args()

    log = configure_logging("edge-producthunt", args.log_level)
    api_key = os.getenv("FIRECRAWL_API_KEY", "").strip()
    if not api_key:
        log.warning(
            "FIRECRAWL_API_KEY not set — poller is idling. "
            "Get a key at firecrawl.dev (free tier 500 scrapes/mo), then "
            "set the env var on this pm2 service and restart."
        )

    sidecar = SidecarWriter(SIDECAR_PATH)
    oracle = OracleClient("edge-intel-producthunt", "pipernet-edge-intel-producthunt/0.2")
    seen: set[str] = set()

    log.info("starting producthunt poller; url=%s interval=%ds api_key=%s",
             PH_URL, args.interval, "set" if api_key else "MISSING")
    while True:
        if not api_key:
            # Idle politely; user can supply key + restart later.
            try:
                time.sleep(max(args.interval, 600))
            except KeyboardInterrupt:
                return 0
            api_key = os.getenv("FIRECRAWL_API_KEY", "").strip()
            continue
        try:
            resp = firecrawl_scrape(PH_URL, api_key)
            if not resp.get("success"):
                log.warning("firecrawl returned non-success: %s", str(resp)[:300])
            md = (resp.get("data") or {}).get("markdown") or ""
            if not md:
                log.warning("firecrawl returned empty markdown (response keys: %s)", list(resp.keys()))
                continue
            products = parse_markdown(md)
            new = []
            for prod in products:
                key = prod.get("url") or prod["name"]
                if key in seen:
                    continue
                seen.add(key)
                sidecar.write(to_sidecar(prod), log)
                new.append(to_observation(prod))
            if new:
                log.info("found %d new products", len(new))
                if not args.dry_run:
                    for i in range(0, len(new), args.batch):
                        try:
                            r = oracle.ingest(new[i:i + args.batch], log)
                            log.info("ingested batch %d → %s", i // args.batch, str(r)[:140])
                        except (URLError, HTTPError, RuntimeError) as e:
                            log.warning("ingest batch failed (%s)", e)
            else:
                log.info("no new products this poll (parsed %d total)", len(products))
            if len(seen) > 500:
                seen = set(list(seen)[-200:])
        except HTTPError as e:
            try:
                err_body = e.read().decode("utf-8")[:400]
            except Exception:  # noqa: BLE001
                err_body = ""
            log.warning("firecrawl HTTP error (%s): %s", e.code, err_body)
        except (URLError, json.JSONDecodeError) as e:
            log.warning("firecrawl request/parse failed (%s)", e)
        except Exception:  # noqa: BLE001
            log.exception("unexpected error")
        try:
            time.sleep(args.interval)
        except KeyboardInterrupt:
            log.info("stopped")
            return 0


if __name__ == "__main__":
    sys.exit(main())
