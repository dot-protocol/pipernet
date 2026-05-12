# edge-intel — Free Signal Sources for the Mesh

The next internet needs awareness. These feeders watch public firehoses,
filter for what matters to Pied Piper / DOT / agentic-web work, and
ingest matches into Oracle as `edge-intel` observations. Free as in
beer (no API keys), free as in speech (Apache-2.0).

## Sources

| Source | Status | Script | Tags |
|---|---|---|---|
| Bluesky Jetstream | ✅ live | `bluesky_jetstream.py` | `source:bluesky` |
| Hacker News | ⏳ next | — | `source:hn` |
| Reddit (no auth) | ⏳ next | — | `source:reddit` |
| Telegram public | ⏳ next | — | `source:telegram` |
| DexScreener | ⏳ next | — | `source:dexscreener` |

## bluesky_jetstream.py

Streams the AT Protocol Jetstream firehose (no auth needed) and ingests
posts matching a keyword list into Oracle.

### Local test

```bash
cd pipernet/tools/edge-intel          # from your Kin checkout root
python3 -m pip install -r requirements.txt
ORACLE_TOKEN=$(grep ORACLE_AUTH_TOKEN ../../../oracle_v3/.env | cut -d= -f2) \
  python3 bluesky_jetstream.py --dry-run --batch 5 --flush-seconds 30
```

Dry-run logs matches without writing to Oracle — use this to tune the
keyword list before going live.

### Deploy on VPS

```bash
ssh adrian
mkdir -p /opt/edge-intel
scp pipernet/tools/edge-intel/{bluesky_jetstream.py,requirements.txt} \
    adrian:/opt/edge-intel/
ssh adrian 'cd /opt/edge-intel && python3 -m pip install --break-system-packages -r requirements.txt'
ssh adrian 'pm2 start /opt/edge-intel/bluesky_jetstream.py \
    --name edge-bluesky --interpreter python3 --time \
    -- --batch 20 --flush-seconds 120'
ssh adrian 'pm2 save'
```

The Oracle token is read from `/opt/tree/.env` automatically if env
vars aren't set — same plumbing as dotpost.

### Keyword file format

One keyword (or short phrase) per line. Lines starting with `#` are
comments. Matching is case-insensitive substring.

```text
# Pied Piper canon
pied piper
$piper
weissman score

# Decentralization themes
agentic web
at protocol
```

Pass it via `--keywords-file kw.txt`.

### What lands in Oracle

Each match becomes an `edge-signal` observation:

```
content    [bluesky] <post body>
type       edge-signal
tags       edge-intel, source:bluesky, author:<did-prefix>,
           uri:at://..., kw:<each-hit>, lang:<each-lang>
rationale  Bluesky post matching <hits> by <did> at <when>
confidence 0.7
```

Query later via:

```python
oracle_query("edge-intel agentic web")
oracle_query("source:bluesky kw:pied piper")
```

### Gotchas

- Jetstream URL changes occasionally — set `BLUESKY_JETSTREAM_URL` env if
  the default goes down. Mirrors: jetstream1.us-east, jetstream2.us-east,
  jetstream1.us-west.
- Volume is high (~500 posts/sec). Keep keyword list tight — broad words
  like "ai" or "web" will flood Oracle.
- Oracle's content-hash dedup catches retweets/copy-paste, so duplicates
  don't bloat the graph. Vector dedup is bypassed (gate-2 patch
  2026-05-12 — see `OBS-axxis-20260512-2086`).

### Tuning

If volume is too high: shorten keyword list, raise `--flush-seconds`.
If volume is too low: add broader themes, drop low-confidence keywords.
Audit weekly via `oracle_audit(tags=["edge-intel"])`.
