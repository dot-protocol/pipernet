# Cloudflare Proxy Removal Plan v0.1 — Keep DNS, Drop Proxy

**Date:** 2026-05-18
**Status:** PLANNING — not executed tonight
**Author:** Piper / Shannon (Claude Code, kin-1)
**Motivation:** Blaze: *"can we remove our dependency on cloudflare for the tunnel?"* — Tunnel is gone (Anti-Rot Rule 7). This document plans the next step: remove the Cloudflare proxy too. Keep DNS only.

This is path C from the 2026-05-17 decision triplet (A: HTTPS origin, B: purge cloudflared, C: drop proxy).

---

## 1. What we are and aren't dropping

| Dependency | Today | Target |
|---|---|---|
| Cloudflare DNS (zone authority) | Yes | **Keep** — DNS is cheap, fast, free, no lock-in |
| Cloudflare Tunnel (cloudflared) | Removed 2026-05-17 | Gone, never again (Rule 7) |
| Cloudflare Proxy (orange-cloud) | Yes (most subdomains) | **Drop** — go DNS-only (gray-cloud) |
| Cloudflare SSL/TLS termination | Yes (Full strict) | **Replace** with VPS-side LE certs |
| Cloudflare CDN / DDoS / WAF | Yes (free tier) | **Lose** (acceptable for now; revisit at Tier 4) |
| Cloudflare R2 / Workers (if used) | No active use | n/a |

DNS-only means Cloudflare resolves `*.axxis.world → 69.62.114.97` but does not proxy traffic. Browser talks to VPS directly. VPS serves LE certs. CF can't see plaintext, can't cache, can't DDoS-shield.

---

## 2. Why this matters

1. **Origin transparency.** Today: when something breaks, we have to debug CF + nginx together (526 errors, SSL mode mismatches, the Vercel-308-loop incident). DNS-only collapses it to one layer.
2. **No vendor lock.** If CF disables the account or changes pricing, DNS-only is a 30-min migration to any DNS host. Proxied means re-architecting around what CF was doing for us.
3. **Self-hosted ethos.** Pipernet is the alternative to corporate-mediated internet. Keeping the production stack proxy-free walks the talk.
4. **Public agent fairness.** With proxy on, every agent IP appears to be a CF IP. Per-IP rate limiting is impossible. DNS-only restores the real client IP at nginx.
5. **Latency.** CF adds 10-30ms per request. For agent traffic (high call rate, low individual value) this matters.

---

## 3. What we lose

Be honest about the trade:

- **DDoS protection.** CF absorbs L3/L4 floods today. DNS-only puts VPS on the open internet. Mitigations: VPS firewall (ufw), fail2ban, rate-limit at nginx, cloud provider's own DDoS guard (Hostinger has some basic protection).
- **CDN caching.** Static assets cached at CF edge today. With DNS-only, every request hits VPS. Mitigations: nginx-level caching, longer max-age headers, or move static assets to R2/B2 with their own CDN.
- **WAF rules.** CF blocks known bad signatures (SQL injection, etc.). Mitigations: ModSecurity on nginx, or accept the trade since our endpoints are mostly auth-gated.
- **Bot management.** CF identifies bot traffic. Mitigations: per-pubkey rate limits (we want this anyway).
- **Argo / smart routing.** Not using.
- **TLS termination.** CF terminates TLS at the edge. Mitigations: VPS serves LE certs directly. Slightly more CPU on VPS but trivial at our scale.

For agent-heavy traffic, **most of what CF gives us we don't want** (CDN caching of MCP calls is wrong; WAF would false-positive on legitimate agent payloads; bot management would block our own agents).

---

## 4. Migration sequence

### Step 1 — VPS hardening (before going DNS-only)

```bash
# Firewall: allow only 80, 443, 22 publicly
sudo ufw default deny incoming
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable

# fail2ban for SSH + nginx
sudo apt install fail2ban
# Pre-configured for sshd; add nginx-http-auth jail

# nginx-level rate-limit (global zones)
# Add to /etc/nginx/nginx.conf http block:
# limit_req_zone $binary_remote_addr zone=public:10m rate=10r/s;
# limit_req_zone $http_authorization zone=token:10m rate=60r/m;
```

### Step 2 — LE certs for every public subdomain

Today's multi-SAN cert at `/etc/letsencrypt/live/drop.axxis.world/` covers: drop, mcp, post, room. Need to expand to oracle + any other subdomain.

```bash
# Expand existing cert
certbot --nginx --expand \
  -d drop.axxis.world \
  -d mcp.axxis.world \
  -d post.axxis.world \
  -d room.axxis.world \
  -d oracle.axxis.world \
  -d studio.piedpiper.fun \
  -d agenthub.mevici.com \
  -d kin.mevici.com \
  -d <every other public subdomain>
```

This requires HTTP-01 challenge to succeed, which requires the subdomain to be DNS-only at the moment of certbot (otherwise CF intercepts and we hit the same chicken-and-egg).

### Step 3 — Per-subdomain proxy flip (one at a time, never all at once)

For each subdomain:

1. In Cloudflare DNS panel, flip orange-cloud → gray-cloud (DNS-only).
2. Wait 60s for propagation.
3. Run `certbot --nginx --expand -d <subdomain>` to mint/refresh LE cert.
4. Verify `curl https://<subdomain>/health` works direct-to-VPS.
5. Watch nginx access log for the real client IP (no longer a CF IP).

Do one subdomain per day. Watch for fallout. If anything breaks, flip back to orange-cloud and investigate before continuing.

### Step 4 — Remove CF-specific nginx config

After all subdomains are DNS-only:

- Remove `set_real_ip_from` blocks (no longer needed; client IP is real).
- Remove CF-IP allowlisting if any.
- Remove `CF-Connecting-IP` header forwarding.

### Step 5 — Verify SSL/TLS mode no longer matters

Once everything is DNS-only, the CF SSL/TLS mode setting becomes irrelevant (CF doesn't proxy). Set it to "Off" or leave at "Full (strict)" — doesn't matter.

### Step 6 — Tighten firewall

After DNS-only, the previous CF-IP-only firewall rule is wrong (clients are not CF IPs anymore). Open 443 to 0.0.0.0/0. Already done in Step 1, but verify.

---

## 5. Subdomain inventory

Today's known subdomains and their current state:

| Subdomain | Proxy state | Backend | LE cert |
|---|---|---|---|
| drop.axxis.world | proxied | VPS pied-piper-send | ✅ multi-SAN |
| mcp.axxis.world | proxied | VPS axxis-mcp | ✅ multi-SAN |
| post.axxis.world | proxied | VPS postiz | ✅ multi-SAN |
| room.axxis.world | proxied | VPS room-server | ✅ multi-SAN |
| oracle.axxis.world | proxied | VPS tree_serve.py | ❌ MISSING (today's blocker) |
| relay.piedpiper.fun | proxied | VPS pipernet | ✅ own cert |
| studio.piedpiper.fun | proxied | VPS postiz | ❌ MISSING |
| piedpiper.fun | proxied | Vercel | n/a |
| axxis.world (root) | proxied | Vercel | n/a |
| kin.mevici.com | proxied | DEAD Vercel | ❌ MISSING |
| agenthub.mevici.com | proxied | DEAD Vercel | ❌ MISSING |
| api.mevici.com | proxied | VPS | ✅ own cert |
| mevici.com | proxied | Vercel | n/a |

**Vercel-backed subdomains stay proxied for now.** CF in front of Vercel is fine (Vercel handles its own TLS). DNS-only migration applies to VPS-backed subdomains only.

---

## 6. Rollback plan

If anything breaks during migration:

1. **Per-subdomain rollback:** flip gray-cloud → orange-cloud in CF panel. CF resumes proxying. 60s propagation.
2. **Total rollback:** revert all DNS records to orange-cloud, set CF SSL/TLS mode back to Full (strict). Everything is back to today's state.

No code changes are destructive. The CF panel is the rollback surface.

---

## 7. Timeline

Not tonight. Not this week. Suggested order:

1. **First:** Phase 0-1 of Oracle scale plan (HTTPS origin, externalize embeddings). Don't change two layers at once.
2. **Then:** Step 1 (VPS hardening) — week +2.
3. **Then:** Step 3 (per-subdomain flip) — one subdomain per day starting week +3.
4. **Done:** all VPS subdomains DNS-only by week +5.

Vercel-backed roots (piedpiper.fun, axxis.world, mevici.com) keep CF proxy indefinitely — no benefit to changing.

---

## 8. The doctrine line

After this migration, add to state.md / CLAUDE.md:

> **Anti-Rot Rule 8 — CF proxy is for static / Vercel only.** VPS-backed subdomains run DNS-only with VPS-side LE certs. CF proxy is acceptable in front of Vercel (Vercel handles its own TLS). CF proxy is never in front of VPS endpoints because it adds debugging layers, masks client IPs, and creates SSL-mode lock-in.

---

## 9. What this is NOT

- Not anti-Cloudflare. CF DNS is excellent and stays.
- Not anti-CDN. We may put R2 in front of static asset traffic later.
- Not a vanity exercise. The real motivation is debugging simplicity + per-IP rate limiting + sovereignty.

---

*Plan, not implementation. Comments via dotpost to `piper` with tag `cf-proxy-drop`.*
