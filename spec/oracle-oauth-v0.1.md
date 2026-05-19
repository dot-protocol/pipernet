# Oracle OAuth v0.1 — Per-Handle Identity for the Consumer Side

**Status:** DESIGN — awaiting Blaze approval
**Author:** Rocky (Claude Code) for Blaze
**Date:** 2026-05-19
**Companion specs:** handle-substrate-v0.1.md, coordination-substrate-v0.1.md, oracle-scale-plan-v0.1.md
**Supersedes (in part):** the shared-bearer auth pattern in tree_serve.py:65–73

---

## 1. ABSTRACT

Oracle currently authenticates external callers with a single shared bearer token. That token can't scale: it has one rate-limit bucket for everyone, can't be revoked per-user, and Claude.ai's connector UI drops the Authorization header on session refresh. This spec defines a per-handle identity layer that closes the consumer-side gap (`millions of Claude.ai users` and other browser-based clients that can't sign requests natively), while preserving the existing signed-request `/p/*` surface for keypair-equipped agents (Loom, Pipernet-native bots, autonomous runtimes).

End state: every Claude.ai user adding the Oracle connector gets a unique JWT bound to their own Pipernet handle, with per-handle write-scopes and revocation. UX matches moltbook's 30-second onboarding. Substrate (cryptographic identity, signed claims) matches Pipernet's handle substrate v0.1, avoiding the SOUL.md catastrophe (1.5M leaked API keys, 36% flawed agent code, prompt-injection-at-scale) that moltbook hit.

---

## 2. GOALS / NON-GOALS

### Goals (v0.1)
1. **Per-user JWT issuance**, bound to a Pipernet handle.
2. **Three identity providers** day one: email magic-link, GitHub OAuth, Pipernet-handle challenge-sign-in.
3. **Stateless verification** — Oracle verifies JWT signatures locally; zero DB round-trip on the read hot path.
4. **Scoped writes** — by default, a handle can only `oracle_ingest` to its own channel (`user/<handle>`) plus any community channel it has been explicitly granted.
5. **Claude.ai-native** — works with the connector wizard's OAuth flow without manual config.
6. **Agent compatibility** — delegated agents (Claude Code, Cursor, MCP clients) reuse a user's JWT; standalone agents (Loom, bots) continue to use signed-request `/p/*` unchanged.
7. **Migration path** — the existing shared bearer remains valid for the trusted-insider set during transition; new accounts go through the new flow.

### Non-goals (v0.1)
- Sign-in-with-Claude / Sign-in-with-Vercel (Anthropic-OAuth source) — deferred; not blocking.
- Full RBAC (channel ACL DSL, role assignments). v0.1 ships with three flat scope tiers; richer RBAC if/when v0.2 needs it.
- Stake / payment integration ($PIPER bonding) — deferred to coordination-substrate v0.2.
- Stateful access-token revocation (Redis blacklist). v0.1 relies on refresh-token revocation + 30d access-token TTL; add Redis behind a feature flag if token-theft incidents appear.
- Mobile-native SDKs. v0.1 surface is HTTP only; SDKs follow.

---

## 3. ARCHITECTURE OVERVIEW

```
                       ┌─────────────────────────────┐
                       │   axxis.world/connect       │
                       │   (Next.js page, public)    │
                       │                             │
                       │   [ Sign in with email ]    │
                       │   [ Sign in with GitHub ]   │
                       │   [ Sign in with handle ]   │
                       └────────────┬────────────────┘
                                    │
                ┌───────────────────┼───────────────────┐
                ▼                   ▼                   ▼
         ┌────────────┐      ┌────────────┐      ┌────────────┐
         │  /oauth/   │      │  /oauth/   │      │  /oauth/   │
         │  email     │      │  github    │      │  handle    │
         │  /init     │      │  /init     │      │  /init     │
         └─────┬──────┘      └─────┬──────┘      └─────┬──────┘
               │                    │                    │
        magic-link email     GitHub OAuth dance    challenge → sign
               │                    │                    │
               ▼                    ▼                    ▼
        ┌─────────────────────────────────────────────────────┐
        │           Oracle /oauth/callback                     │
        │  1. Verify proof (magic token / GH access / sig)    │
        │  2. Resolve-or-create Pipernet handle               │
        │  3. Mint JWT (RS256, 30d) + refresh (365d)          │
        │  4. Persist refresh in Neo4j                        │
        └─────────────────────────────┬───────────────────────┘
                                      │
                                      ▼
              ┌───────────────────────────────────────────┐
              │  Claude.ai connector wizard receives      │
              │  the JWT via /oauth/token exchange.       │
              │  Every subsequent MCP call carries it.    │
              └───────────────────────────────────────────┘

        Every request to /mcp/ or /search etc:
        ┌───────────────────────────────────────────┐
        │  1. Read Authorization: Bearer <JWT>      │
        │  2. RS256 verify against public key       │
        │  3. Extract { handle, pubkey, scopes }    │
        │  4. Pass to tool dispatcher as caller_id  │
        │  5. Tool checks scopes before writing     │
        └───────────────────────────────────────────┘

        Agent paths in parallel:
        - Standalone agent (Loom)     →  /p/*  signed-request  →  same caller_id resolution
        - Delegated agent (Claude Code) →  Bearer JWT issued to user  →  acts as user
```

---

## 4. IDENTITY PROVIDERS

### 4.1 Email magic-link

**Endpoint:** `POST /oauth/email/init`
**Request:** `{ "email": "user@example.com", "redirect_uri": "..." }`
**Effect:** Mints a short-lived (10-min TTL) `:MagicLink` node in Neo4j with `{ token, email, redirect_uri, expires_at }`. Sends email via Stalwart (or stopgap: SendGrid/Postmark — see §10) containing a link to `https://oracle.axxis.world/oauth/email/verify?token=<magic_token>`.
**On click:** `/oauth/email/verify` validates the token, resolves-or-creates a handle (derived deterministically from `email` hash + collision suffix), mints JWT, hands off to OAuth callback.

**Why email first**: lowest friction for non-technical users; broadest reach. Maps to Claude.ai's typical user identity (they're already logged in with an email).

**Dependency:** Stalwart Mail (planned, blocked on DNS+PTR per agent-email-decision.md) OR third-party (SendGrid / Postmark / AWS SES) as v0.1 stopgap. Recommend Postmark for transactional reliability ($10/mo for 10K emails; covers our needs through ~10K signups).

### 4.2 GitHub OAuth

**Endpoint:** `GET /oauth/github/init` → redirects to GitHub OAuth.
**Callback:** `GET /oauth/github/callback?code=...` → exchanges code for access token, fetches user's GitHub `login` + `email` + `id`, resolves-or-creates handle (`gh-<github_login>` if available, else collision suffix), mints JWT.
**Scope requested:** `read:user` only — no repo / write access.

**Why GitHub second**: devs already have GH identities, lowest-friction for the technical audience, gives us a public attestation we can use for sybil resistance later (GH account age + star count = reputation prior).

**Setup:** Register `oracle.axxis.world` as a GitHub OAuth app. Callback URL = `https://oracle.axxis.world/oauth/github/callback`. Client ID + secret stored in `/opt/tree/.env`.

### 4.3 Pipernet handle (sovereign)

**Endpoint:** `POST /oauth/handle/challenge` → returns a 16-byte random challenge.
**Endpoint:** `POST /oauth/handle/verify`
**Request:**
```json
{
  "handle": "blaze",
  "pubkey": "ed25519:0xabc...",
  "challenge": "...",
  "signature": "...",
  "timestamp": "..."
}
```
**Effect:** Oracle verifies the signature against the pubkey, confirms the handle's claim observation exists with that pubkey, mints JWT bound to the handle.

**Why handle path third**: for users already in the ecosystem (Pipernet CLI installed, keypair generated). Skips email entirely. Sovereign — no third-party identity provider.

**Reuses:** the existing handle substrate v0.1 (`pipernet/spec/handle-substrate-v0.1.md`) and the `pipernet handle claim` CLI command.

---

## 5. JWT SHAPE

### 5.1 Access token (30d TTL)

**Header:**
```json
{
  "alg": "RS256",
  "typ": "JWT",
  "kid": "oracle-2026-05"
}
```

**Payload:**
```json
{
  "iss": "https://oracle.axxis.world",
  "sub": "blaze-3f8c",
  "aud": "oracle-mcp",
  "iat": 1758000000,
  "exp": 1760592000,
  "pubkey": "ed25519:0x...",
  "scopes": [
    "read:public",
    "write:user/blaze-3f8c",
    "write:community/illuminati"
  ],
  "via": "email"
}
```

### 5.2 Refresh token (365d TTL)

Opaque random string, 32 bytes hex. Stored in Neo4j as `:RefreshToken` node:

```cypher
CREATE (rt:RefreshToken {
  token_hash: <sha256(token)>,
  handle: "blaze-3f8c",
  issued_at: datetime(),
  expires_at: datetime() + duration({days: 365}),
  client_id: "claude-ai-connector",
  via: "email"
})
CREATE (rt)-[:BELONGS_TO]->(h:Handle {name: "blaze-3f8c"})
```

### 5.3 Signing key

RS256 key pair generated once, stored at `/opt/tree/.keys/oracle-jwt-2026-05.{key,pub}`. Public key served at:

```
GET https://oracle.axxis.world/.well-known/jwks.json
```

So any service (Mission Control, Postiz, piperchat) can verify Oracle-issued JWTs without sharing the private key.

Key rotation: every 365 days, generate new keypair with bumped `kid`, keep old public key in JWKS for the rotation period to support in-flight tokens.

---

## 6. SCOPES MODEL

Three scope tiers, all flat strings in the JWT `scopes` claim:

| Scope | Granted | Description |
|---|---|---|
| `read:public` | Every authed user | `/search`, `/recent`, `/connections`, `/ask` against `channel ∉ {raw, private}` |
| `read:private` | Opt-in (CLI flag during sign-up) | Adds `raw` + `private` channels to read scope |
| `write:user/<handle>` | Auto-granted to user's own handle | `oracle_ingest`, `dotpost_send`, `task_*` writes to `channel = user/<handle>` |
| `write:community/<name>` | Granted explicitly (community admin invitation) | Same writes to specified community channel |
| `admin:*` | Internal-only (Rocky, Erlich, Jared, Loom in-cluster) | Bypass all checks. Never externally requestable. |

**Enforcement point:** every tool handler in `tree.py` / `oracle_mcp_server.py` checks `caller_scopes` before performing the action. Read tools check `channel ∈ caller.read_scopes`. Write tools check `channel ∈ caller.write_scopes`.

**Forward compat:** scope strings are dot-path-shaped (`write:community/<name>`) so a future RBAC system can introduce wildcards (`write:community/*`) without breaking v0.1 tokens.

---

## 7. ENDPOINTS (full surface)

### 7.1 OAuth 2.1 standard (Claude.ai connector compatibility)

```
GET  /.well-known/oauth-authorization-server
GET  /.well-known/jwks.json
POST /oauth/register              (DCR — dynamic client registration)
GET  /oauth/authorize             (OAuth dance entry — redirects to /connect)
POST /oauth/token                 (exchange code for JWT)
POST /oauth/refresh               (exchange refresh for new access)
POST /oauth/revoke                (revoke refresh token)
GET  /oauth/userinfo              (current handle + scopes; for client UIs)
```

### 7.2 Provider-specific (internal flow)

```
POST /oauth/email/init            (mint magic-link, send email)
GET  /oauth/email/verify          (consume magic-link, finalize)
GET  /oauth/github/init           (redirect to GitHub)
GET  /oauth/github/callback       (exchange GH code, finalize)
POST /oauth/handle/challenge      (mint random challenge)
POST /oauth/handle/verify         (verify signature, finalize)
```

### 7.3 New endpoints on existing tree_serve.py

The existing `_oauth_codes` / `_oauth_clients` shim (tree_serve.py:65–73, line 322) gets rewritten to back onto Neo4j instead of in-memory dicts. The endpoints stay the same paths Claude.ai already discovers; only the implementation changes.

---

## 8. NEO4J STORAGE MODEL

```cypher
// Identity primitives (extends handle-substrate-v0.1)
CREATE CONSTRAINT handle_name IF NOT EXISTS FOR (h:Handle) REQUIRE h.name IS UNIQUE;
CREATE CONSTRAINT handle_pubkey IF NOT EXISTS FOR (h:Handle) REQUIRE h.pubkey IS UNIQUE;
CREATE INDEX handle_email IF NOT EXISTS FOR (h:Handle) ON (h.email);

// OAuth artifacts
CREATE CONSTRAINT refresh_token_hash IF NOT EXISTS FOR (rt:RefreshToken) REQUIRE rt.token_hash IS UNIQUE;
CREATE INDEX refresh_token_handle IF NOT EXISTS FOR (rt:RefreshToken) ON (rt.handle);
CREATE CONSTRAINT magic_link_token IF NOT EXISTS FOR (ml:MagicLink) REQUIRE ml.token IS UNIQUE;
CREATE INDEX magic_link_expires IF NOT EXISTS FOR (ml:MagicLink) ON (ml.expires_at);
CREATE CONSTRAINT oauth_state IF NOT EXISTS FOR (s:OAuthState) REQUIRE s.state IS UNIQUE;

// Provider bindings (so re-sign-in with same email/github finds the same handle)
// (b:ProviderBinding) - email_hash | github_id - linked to (h:Handle)
CREATE CONSTRAINT provider_binding_id IF NOT EXISTS FOR (b:ProviderBinding) REQUIRE (b.provider, b.external_id) IS UNIQUE;
```

---

## 9. ONBOARDING UX (steal moltbook shape)

### 9.1 Human path (Claude.ai user)

```
[t=0s]   Open axxis.world/connect
[t=2s]   Click "Sign in with email"
[t=3s]   Type email, click "Send link"
[t=5s]   Switch to email tab
[t=10s]  Click magic link
[t=12s]  Back at axxis.world/connect/success
[t=15s]  "Your handle is blaze-3f8c. Copy connector URL?" → click
[t=20s]  Open Claude.ai → Settings → Connectors → Add custom → paste
[t=30s]  Done. JWT lives in Claude.ai's connector config.
```

Matches moltbook's ~30s onboarding. Same "system provisions identity behind the scenes, user never sees a keypair" philosophy — but the underlying identity is cryptographic (Ed25519 keypair generated server-side, private key sealed in Neo4j, never exposed to user unless they explicitly request export).

### 9.2 Agent path (Loom, Cursor, autonomous bot)

```
$ pipernet handle claim --name=loom-a7f3 --pubkey=ed25519:0x...
✓ Claim posted (OBS-handle-20260519-...). Signed challenge accepted.
✓ Handle 'loom-a7f3' resolves to your pubkey.
$ pipernet oracle test --signed
✓ /p/search round-trip: 73ms, 5 hits.
$ # Agent now signs every request. Zero tokens.
```

### 9.3 Claude-Code-on-laptop path (Rocky, Jared, Erlich, Stewart, you)

```
1. Visit axxis.world/connect
2. Sign in (any provider)
3. axxis.world/connect/success displays:
   - Handle: blaze-3f8c
   - MCP URL: https://oracle.axxis.world/oauth/mcp/
   - Access token: eyJ... (one-time-shown; user copies)
4. Update ~/.mcp.json with the new URL + token.
5. Restart Claude Code.
6. Old shared bearer continues to work in parallel during transition.
```

### 9.4 Export your keypair (sovereignty escape hatch)

```
GET /oauth/handle/export
Authorization: Bearer <JWT>

Response:
{
  "handle": "blaze-3f8c",
  "pubkey": "ed25519:0x...",
  "secret": "ed25519:0x...",
  "encrypted_with": "user_passphrase",
  "note": "This is your private key. Oracle has wiped it server-side. From now on, sign requests directly via /p/* and stop using OAuth tokens."
}
```

Optional. Default users never see it. Power users opt in. The point: identity remains sovereign — Oracle holds the keypair only as a convenience, never as a lock-in.

---

## 10. SECURITY MODEL (moltbook lessons applied)

### 10.1 Defenses against the failure modes that broke moltbook

| Moltbook failure | Cause | Oracle OAuth defense |
|---|---|---|
| 1.5M API keys leaked | Misconfigured DB with raw keys | No raw tokens in DB. Refresh tokens stored as SHA-256 hashes. Access tokens never stored at all (stateless JWT). |
| 36% of agent code flawed | Anyone could publish | Channel-scoped writes; user can only write to own channel by default. Mass-write requires explicit community-scope grant. |
| Prompt injection via posts | No content validation | Adopt axxis-mcp's 16-pattern regex at `/ingest` gate. Already exists at axxis-mcp/server.py — promote to tree_serve.py middleware. |
| Identity mutable (SOUL.md) | Plain-text identity | Ed25519 keypair claims, signature-verified, append-only. (Already enforced by handle substrate v0.1.) |
| Identity tied to model | Different model = different agent | Handle = pubkey, not model. Survives model swap because keypair survives. |
| Sybil farming | Zero cost to create accounts | v0.1: rate-limit handle-claim by email/GH-id. v0.2: reputation-prior from external provider (GH account age, email domain). |

### 10.2 Rate limits (per handle)

| Endpoint | Limit | Reset |
|---|---|---|
| `/oauth/email/init` | 5/hour per email | rolling 1h |
| `/oauth/github/callback` | 20/hour per github_id | rolling 1h |
| `/oauth/handle/verify` | 20/hour per pubkey | rolling 1h |
| `/oauth/token` (code exchange) | 30/hour per client_id | rolling 1h |
| `/oauth/refresh` | 60/day per refresh_token | rolling 24h |
| Trusted-mesh handles | Bypass all of the above | Hardcoded handle list in `/opt/tree/.env`: `TRUSTED_MESH_HANDLES=rocky,erlich,jared,stewart,loom`. Same pattern as axxis-mcp's existing `TRUSTED_MESH_AGENTS` set. Adding/removing requires Oracle env edit + restart. |

Stored in-memory (same pattern as axxis-mcp `_rate_buckets`). Resets on Oracle restart — acceptable for v0.1.

### 10.3 Replay protection

OAuth state parameter (16 bytes random) on every authorize → callback round-trip, single-use. Magic-link tokens single-use, expire after 10 min. Handle-challenge signatures bound to `timestamp` claim, ±5 min skew tolerated.

### 10.4 Revocation

- `POST /oauth/revoke` with refresh token → marks refresh token as revoked in Neo4j.
- Access tokens age out naturally within 30 days; no immediate revocation in v0.1.
- For emergency revocation of a specific access token, add a Redis blacklist behind a feature flag (low priority).

---

## 11. MIGRATION PLAN (shared bearer → per-handle)

### 11.1 Phase A: dual-auth (week 1)

Oracle accepts both the shared bearer AND new per-handle JWTs. New accounts go through OAuth; existing trusted insiders keep using the shared bearer. Zero breakage.

### 11.2 Phase B: insider migration (weeks 2–3)

Rocky, Erlich, Jared, Stewart, Loom run through the OAuth flow once, switch ~/.mcp.json to JWT, verify everything works. Shared bearer kept as fallback.

### 11.3 Phase C: shared-bearer deprecation (week 4+)

Once all insiders are on JWTs, the shared bearer's scope is narrowed to `admin:*` only (no read/write to user channels). Eventually the shared bearer becomes an admin override only, not a normal-use credential.

### 11.4 Phase D: public launch

axxis.world/connect ships to the public homepage. Onboarding flow visible. Claude.ai users can self-serve.

---

## 12. BUILD PHASES

Three sessions estimated, each shippable independently. Each phase ends with a working production deploy.

### Phase 1 (Session 1): scaffolding + email magic-link (~600 LOC)

- Generate RS256 keypair, serve at `/.well-known/jwks.json`
- Rewrite `_oauth_codes` / `_oauth_clients` shim onto Neo4j
- Implement `/oauth/email/{init,verify}` end-to-end
- Implement `/oauth/{token,refresh,revoke,userinfo}` standard endpoints
- Implement axxis.world/connect Next.js page (in projects/axxis-world)
- Build `caller_id` middleware in tree_serve.py (parse JWT, populate request context)
- One end-to-end test: email magic-link → JWT → call /search → verify caller_id is set

**Deliverable:** trusted-insider can run through the full OAuth dance and get a JWT. Existing shared-bearer auth continues to work.

**Email provider for Phase 1:** Postmark transactional, $10/mo, 10K emails. API key in `/opt/tree/.env::POSTMARK_TOKEN`. Pre-commit: when Stalwart Mail's DNS+PTR blockers (per `agent-email-decision.md`) resolve, swap the email-send function in `/oauth/email/init` to use local SMTP via Stalwart. Single-file change. No spec amendment needed.

### Phase 2 (Session 2): GitHub + handle providers (~400 LOC)

- Register GitHub OAuth app, store credentials
- Implement `/oauth/github/{init,callback}`
- Implement `/oauth/handle/{challenge,verify}` reusing handle-substrate-v0.1 verification
- axxis.world/connect adds the two extra buttons
- End-to-end tests for all three providers
- Documentation in axxis.world/docs/connect

**Deliverable:** all three providers live. axxis.world/connect feature-complete.

### Phase 3 (Session 3): scope enforcement + Claude.ai wizard polish (~300 LOC)

- Implement scope check at every tool handler (`tree.py` + `oracle_mcp_server.py`)
- Channel-scoped write enforcement (user can only write to own channel + granted communities)
- `/oauth/handle/export` endpoint for keypair extraction
- Claude.ai connector wizard polish — verify the OAuth metadata works in the actual Claude.ai add-connector UI
- Migration helper script for trusted insiders (`tools/oauth/migrate-insider.sh`)

**Deliverable:** scopes enforced. Migration runbook ready. Ready for public launch (axxis.world/connect goes on the homepage).

### Total estimate

~1,300 LOC across three sessions. About 1.5–2 days of focused work each. No dependencies between phases beyond the sequence.

---

## 13. OPEN QUESTIONS

1. **Email provider for Phase 1:** Stalwart is planned but blocked on DNS+PTR (Blaze action items per agent-email-decision.md). Stopgap recommendation: Postmark ($10/mo, transactional reliability) until Stalwart ships. Decision pending.

2. **Handle naming:** auto-derive from email/github (`blaze-3f8c`) or let users pick (`@blaze`)? Moltbook used Reddit-style usernames which were user-picked. Recommended: allow user-pick on the connect page with collision-suffix fallback. Decision pending.

3. **Public-channel-write scope:** should regular users be able to `oracle_ingest` to community channels like `illuminati` (current room)? Current room work has all gone through trusted insiders. Recommendation: invitation-only for v0.1; community-admin-grants-write-scope flow in v0.2.

4. **MCP-OAuth Claude.ai compatibility:** the existing tree_serve.py shim claims it's Claude.ai-wizard-compatible, but it was tested against the wizard before "Sign in with Claude" launched. Re-test with current claude.ai to confirm the DCR endpoints still match the wizard's expectations.

5. **Cloudflare in the path:** prior `is_query` regression was traced to CF WAF blocking Python-urllib UAs. The OAuth callback endpoints will be hit by GitHub's bot (not a browser); confirm CF doesn't block GH OAuth callbacks. Pre-test with a probe.

6. **Stake mechanism:** out of scope for v0.1 per goals, but the spec should leave room for `$PIPER` bonding to expand handle scopes (e.g., bond 10 $PIPER → unlock `write:community/*`). Reserve a JWT claim `stake_bonded` for forward-compat.

---

## 14. REFERENCES

- handle-substrate-v0.1.md — identity primitive this spec extends.
- coordination-substrate-v0.1.md — work-allocation state machine; uses `write:user/<handle>` scope.
- oracle-scale-plan-v0.1.md — 440-line phased plan for Oracle scale; references moltbook saga.
- agent-email-decision.md (.claude/rules/) — Stalwart mail server plan, blocked on DNS+PTR.
- research/2026-04-30-protocol-landscape-and-trademark.md — moltbook deep dive; identifies the SOUL.md security gap and the prompt-injection vector.
- conversations/2026-02-04-rent-a-human-research.md — three-component MVP shape (identity + reputation + stake) that this spec operationalizes for #1.
- tree_serve.py:65–73 + :322 — existing OAuth 2.1 shim to be rewritten.
- oracle_v3/serve.py — fuller OAuth 2.1 reference implementation (381 lines, refresh-token aware).
- IETF RFC 6749 (OAuth 2.0), RFC 8414 (Discovery), RFC 7591 (DCR), RFC 7519 (JWT), RFC 7518 (JWS).

---

## 15. APPROVAL

This spec is locked when Blaze acknowledges with `lock spec` or equivalent. After lock, an implementation plan is drafted (writing-plans skill or equivalent) breaking Phase 1 into atomic commits, and execution begins.

Open changes welcome before lock. Specifically calling out: §10.2 rate limits, §13.2 handle-naming UX, §13.3 community-write-scope policy.
