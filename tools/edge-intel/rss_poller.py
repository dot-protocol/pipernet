"""
rss_poller — generic RSS poller for ProductHunt + Google Trends.

Same shape as github_trending.py and bluesky_jetstream.py: poll on
an interval, dedupe by item GUID/link, write to sidecar JSONL,
ingest to Oracle.

Used as the implementation for two pm2 services:
    pm2 start rss_poller.py --name edge-producthunt -- \\
        --source producthunt \\
        --url https://www.producthunt.com/feed \\
        --sidecar /var/lib/edge-intel/producthunt.jsonl

    pm2 start rss_poller.py --name edge-gtrends -- \\
        --source gtrends \\
        --url https://trends.google.com/trending/rss?geo=US \\
        --sidecar /var/lib/edge-intel/gtrends.jsonl
"""
from __future__ import annotations

import argparse
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError

from _common import (
    OracleClient,
    SidecarWriter,
    configure_logging,
    http_get_text,
)


def _strip_ns(tag: str) -> str:
    """ElementTree gives '{namespace}tag'; we want just 'tag'."""
    return tag.split("}", 1)[-1] if "}" in tag else tag


def parse_rss(xml_text: str) -> list[dict]:
    """Parse RSS 2.0 + RSS-namespace items into plain dicts.

    Captures: title, link, description, pubDate, guid, category, traffic
    (Google Trends uses ht:approx_traffic + ht:news_item* — also captured).
    """
    items: list[dict] = []
    root = ET.fromstring(xml_text)
    for chan in root.iter("channel"):
        for item in chan.findall("item"):
            d: dict[str, str | list] = {}
            news_items: list[dict[str, str]] = []
            for child in item:
                tag = _strip_ns(child.tag)
                text = (child.text or "").strip()
                if tag == "news_item":
                    ni: dict[str, str] = {}
                    for sub in child:
                        ni[_strip_ns(sub.tag)] = (sub.text or "").strip()
                    news_items.append(ni)
                elif tag in d and isinstance(d[tag], str):
                    d[tag] = [d[tag], text]
                elif tag in d and isinstance(d[tag], list):
                    d[tag].append(text)
                else:
                    d[tag] = text
            if news_items:
                d["news_items"] = news_items
            items.append(d)
    return items


def item_id(item: dict) -> str:
    """Stable dedup key. Prefer guid → link → title."""
    return str(item.get("guid") or item.get("link") or item.get("title") or "")


def to_observation(item: dict, source: str) -> dict:
    title = (item.get("title") or "").strip()
    desc = (item.get("description") or "").strip()
    link = (item.get("link") or "").strip()
    # Strip HTML tags for cleaner display (rough)
    if "<" in desc:
        import re
        desc = re.sub(r"<[^>]+>", "", desc).strip()
    text = f"[{source}] {title}"
    if desc:
        text += f" — {desc[:300]}"
    tags = [
        "edge-intel",
        f"source:{source}",
    ]
    if cat := item.get("category"):
        tags.append(f"category:{cat if isinstance(cat, str) else cat[0]}"[:80])
    if traffic := item.get("approx_traffic"):
        tags.append(f"traffic:{traffic}")
    return {
        "content": text,
        "type": "edge-signal",
        "rationale": f"RSS item from {source}: {title[:120]} ({link})",
        "tags": tags,
        "confidence": 0.85,
    }


def to_sidecar(item: dict, source: str) -> dict:
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "title": item.get("title", ""),
        "link": item.get("link", ""),
        "description": item.get("description", ""),
        "pubDate": item.get("pubDate", ""),
        "guid": item.get("guid", ""),
    }
    if "approx_traffic" in item:
        rec["traffic"] = item["approx_traffic"]
    if "news_items" in item:
        rec["news_items"] = item["news_items"]
    if "category" in item:
        rec["category"] = item["category"]
    return rec


def main() -> int:
    p = argparse.ArgumentParser(description="RSS → Oracle edge-intel feeder")
    p.add_argument("--source", required=True, help="source tag (producthunt, gtrends, etc.)")
    p.add_argument("--url", required=True, help="RSS feed URL")
    p.add_argument("--sidecar", required=True, help="JSONL sidecar path")
    p.add_argument("--interval", type=int, default=900, help="poll seconds (default 900 = 15 min)")
    p.add_argument("--batch", type=int, default=15, help="max items per Oracle ingest call")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args()

    log = configure_logging(f"edge-{args.source}", args.log_level)
    sidecar = SidecarWriter(args.sidecar)
    oracle = OracleClient(f"edge-intel-{args.source}", f"pipernet-edge-intel-{args.source}/0.1")
    seen: set[str] = set()

    log.info("starting rss poller; source=%s url=%s interval=%ds", args.source, args.url, args.interval)
    while True:
        try:
            xml_text = http_get_text(args.url)
            items = parse_rss(xml_text)
            new = []
            for it in items:
                key = item_id(it)
                if not key or key in seen:
                    continue
                seen.add(key)
                sidecar.write(to_sidecar(it, args.source), log)
                new.append(to_observation(it, args.source))
            if new:
                log.info("found %d new items", len(new))
                if not args.dry_run:
                    for i in range(0, len(new), args.batch):
                        try:
                            r = oracle.ingest(new[i:i + args.batch], log)
                            log.info("ingested batch %d → %s", i // args.batch, str(r)[:140])
                        except (URLError, HTTPError, RuntimeError) as e:
                            log.warning("ingest batch failed (%s)", e)
            else:
                log.info("no new items this poll")
            if len(seen) > 800:
                seen = set(list(seen)[-400:])
        except (URLError, HTTPError) as e:
            log.warning("fetch failed (%s)", e)
        except ET.ParseError as e:
            log.warning("RSS parse failed (%s)", e)
        except Exception:  # noqa: BLE001
            log.exception("unexpected error")
        try:
            time.sleep(args.interval)
        except KeyboardInterrupt:
            log.info("stopped")
            return 0


if __name__ == "__main__":
    sys.exit(main())
