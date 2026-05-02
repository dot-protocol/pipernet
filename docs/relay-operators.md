# Running a public Pipernet relay

Anyone can run a relay. The relay is a single Python process with no database
requirement and no external service dependencies. This document covers
everything you need to run a production relay that other nodes can reach.

---

## Minimum requirements

| Requirement | Value |
|------------|-------|
| Python | 3.10+ |
| RAM | ~50 MB idle, ~5 MB per 1,000 connected SSE clients |
| Disk | Proportional to channel traffic; JSONL files grow with messages |
| Open port | One TCP port (default 8000) |
| Dependencies | `aiohttp>=3.9` (installed with `pip install pipernet`) |

A $6/month VPS handles a small community relay comfortably. The reference
relay at `api.mevici.com/pipernet` runs on a 4-core/16 GB machine alongside
other services.

---

## Quickstart

```bash
pip install pipernet

# Generate an identity for the relay node (gives the relay a named handle)
pipernet keygen --handle my-relay

# Start the relay (binds 0.0.0.0:8000 by default)
pipernet serve --port 8000 --host 0.0.0.0 --log-level info
```

Verify it's running:

```bash
curl http://localhost:8000/health
# → {"status":"ok","node":"my-relay","version":"0.2.0","uptime_seconds":5,...}
```

---

## Systemd service (production)

Save as `/etc/systemd/system/pipernet-relay.service`:

```ini
[Unit]
Description=Pipernet relay node
After=network.target

[Service]
Type=simple
User=pipernet
WorkingDirectory=/opt/pipernet
ExecStart=/opt/pipernet/venv/bin/pipernet serve \
    --host 127.0.0.1 \
    --port 8000 \
    --log-level info
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

# Rate limit override via environment (optional)
Environment=PIPERNET_HOME=/var/lib/pipernet
Environment=PIPERNET_OPEN_CHANNELS=

[Install]
WantedBy=multi-user.target
```

```bash
# Create a dedicated user
useradd -r -s /sbin/nologin pipernet
mkdir -p /var/lib/pipernet /opt/pipernet

# Install into a venv
python3 -m venv /opt/pipernet/venv
/opt/pipernet/venv/bin/pip install pipernet

# Enable and start
systemctl daemon-reload
systemctl enable pipernet-relay
systemctl start pipernet-relay
systemctl status pipernet-relay
```

---

## Nginx reverse proxy (HTTPS)

Run the relay on localhost only (`--host 127.0.0.1`) and put nginx in front.
This gives you TLS termination, access logging, and the ability to run other
services on the same machine.

`/etc/nginx/sites-available/relay.example.com`:

```nginx
server {
    listen 80;
    server_name relay.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name relay.example.com;

    ssl_certificate     /etc/letsencrypt/live/relay.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/relay.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;

        # Required for SSE
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 86400;

        # Standard proxy headers
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
certbot --nginx -d relay.example.com
nginx -t && systemctl reload nginx
```

**Important:** The `proxy_buffering off` and `proxy_read_timeout 86400` lines
are required for SSE. Without them, nginx will buffer the event stream and
subscribers will not receive live envelopes.

---

## Rate limits

The relay ships with sensible defaults. All limits are enforced in memory
using a sliding window — no Redis, no external state.

| Limit | Default | What it protects against |
|-------|---------|-------------------------|
| Per pubkey: 10 envelopes / 60s | `per_pubkey` | A single user flooding a channel |
| Per IP: 60 POSTs / 60s | `per_ip_post` | A single machine spamming |
| Per IP: 30 unique handles / 3600s | `per_ip_sybil` | Sybil registration attacks |
| Per IP: 5 concurrent SSE connections | `per_ip_sse` | Connection exhaustion |

Query the configured limits at any time:

```bash
curl http://relay.example.com/limits
```

These defaults are intentionally conservative. A relay serving a small team
or community (dozens of users) will not hit them under normal use. If you
need higher limits, the values are defined at the top of `cli/server.py` in
the `RATE_LIMITS` dict — edit and redeploy.

---

## Open channels

By default, every channel requires Ed25519 signature verification. The
`PIPERNET_OPEN_CHANNELS` environment variable lists channels that skip
signature verification — useful for demo deployments or applications where
a different auth mechanism (e.g., wallet gating) handles access control.

```bash
# Allow unsigned envelopes on the "lobby" and "public" channels
PIPERNET_OPEN_CHANNELS=lobby,public pipernet serve --port 8000
```

Open-channel envelopes are normalised into the standard schema and stored
identically to signed envelopes — the relay marks them with `"modes": ["open"]`
and sets `"signature": null`. History and SSE work identically.

**For production relays that require cryptographic authenticity throughout,
set `PIPERNET_OPEN_CHANNELS=` (empty) or do not set it.** The default is
`holders` for backward compatibility with the v0 holder chat demo; you should
override this unless you specifically need it.

---

## Federation: connecting relays

Two relays can synchronise their channel state via the gossip endpoint.

```bash
# Pull all envelopes from a peer relay's "news" channel and push to this relay
curl https://peer.example.com/channels/news?format=jsonl \
  | python3 -c "
import sys, json
envelopes = [json.loads(line) for line in sys.stdin if line.strip()]
print(json.dumps(envelopes))
" | curl -s -X POST http://localhost:8000/gossip \
         -H 'Content-Type: application/json' -d @-
```

The gossip endpoint deduplicates by signature — safe to push the same batch
twice. A future milestone is scheduled gossip (polling or WebSocket-based
peer sync); for now, gossip sync is manual or cron-driven.

---

## Abuse posture

A relay operator controls their trust surface by controlling whose pubkeys
they accept. The recommended posture for a public relay:

1. **Require identity assertions.** When accepting pubkey registrations,
   verify the `identity_assertion.self_signature_hex` field (the relay does
   this automatically if the client sends it). This confirms the registrant
   controls the corresponding private key.

2. **Monitor channel growth.** Channel JSONL files grow unbounded. Set up
   a cron job or logrotate equivalent to archive old entries if disk is
   a concern. The relay restarts cleanly with any valid JSONL history.

3. **Reject open channels in production.** Set `PIPERNET_OPEN_CHANNELS=` to
   require signatures on everything. Open channels are a convenience for
   demos, not a production posture.

4. **Log with structured output.** Every relay event is a JSON line on
   stdout. Pipe to a log aggregator (`journald`, `loki`, `cloudwatch`) for
   abuse investigation. IP addresses are truncated to `/24` in logs by
   default — high privacy while retaining enough signal for abuse patterns.

---

## Health monitoring

```bash
# Simple uptime check (add to your monitoring system)
curl -fs https://relay.example.com/health | python3 -c "
import sys, json
h = json.load(sys.stdin)
status = 'OK' if h['status'] == 'ok' else 'DEGRADED'
print(f\"{status} — uptime {h['uptime_seconds']}s, {h['channel_count']} channels, {h['peer_count']} peers, {h['sse_subscribers']} SSE clients\")
"
```

Expected output: `OK — uptime 86400s, 3 channels, 12 peers, 4 SSE clients`

If the relay is unreachable, `curl -fs` exits non-zero — suitable for use
in a cron health check or alerting pipeline.
