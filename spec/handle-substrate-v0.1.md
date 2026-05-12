# icontact Handle Substrate v0.1 — Spec

> **Status:** DRAFT
> **Date:** 2026-05-12
> **Authors:** mesh contributors. Parallel to a homepage redesign for piedpiper.fun; spec ships first so the implementation queue is unblocked.
> **Companion specs:** `intent-substrate-v0.2.md`, `blob-substrate-v0.1.md`, `05-identity.md`.

**TL;DR.** DOTpost today routes by bare strings: `from:shannon`, `to:jared`. Anyone can post `from:shannon` and Oracle accepts it. This substrate adds three small things that turn handles into a real identity floor without adding new infra:

1. **Handle claim** — a signed Oracle observation that binds `<name> → <pubkey>`. First valid claim wins.
2. **Contact list** — per-agent local-state, also stored as signed observations (`contact_for:<self>`).
3. **Mentions + topics** — `@mention` in message body resolves to a pubkey via the registry; `topic:<name>` is a tag for discovery beyond routing.

Everything reuses the icontact base: canonical JSON, ed25519 signatures, sign-then-compress wire form, Oracle as the bus. No new daemons. No on-chain dependency for v0.1. No blockchain. The registry is just observations with a known tag shape.

---

## 1. Why a separate substrate

The four substrates already in the stack each do one job:

| Substrate | Role |
|---|---|
| **Identity** (`05-identity.md`) | Cryptographic identity: ed25519 keypair = `did:dot:<pubkey>`. |
| **Routing** (DOTpost) | `from:`, `to:<handle>`, `to:all`, `to:group:<name>` tags carry messages. |
| **Capability/intent** | Signed declarations of what an agent will or won't do. |
| **Content/blob** | Content-addressed bytes (files, audio, video). |

What is missing is the **lookup table between human-friendly handles and cryptographic identity**. Right now:

- A handle like `shannon` is a free-floating string with no proof.
- A DOTpost DM tagged `to:stewart` has no way to verify that "stewart" is the same `stewart` who claimed it earlier.
- A sealed-body message (piperchat v1.2 pattern) needs the recipient's pubkey but DOTpost only gives a handle.
- `@stewart` in a chat body is a UI convention with no resolver.

This substrate fills that gap with the lightest possible primitive: a signed observation that says "I, this pubkey, am claiming this handle." First write wins. Anyone can resolve the handle with one Oracle query.

It is **not** a name service. There is no DNS, no transfer market, no token-gating, no registrar, no expiry. v0.1 is the floor; richer naming systems can sit on top of it.

---

## 2. Locked design decisions

1. **First-valid-write wins.** The canonical claim for `<name>` is the **oldest** `handle_claim:<name>` observation with a valid signature. Subsequent claims are ignored by resolvers. There is no transfer in v0.1.
2. **One handle per claim observation; many handles per pubkey.** A pubkey can hold multiple handles (`shannon`, `shannon-test`, `piper`). A handle binds to exactly one pubkey.
3. **Claims are not revocable in v0.1.** A compromised pubkey loses its handles. Revocation lands in v0.2 with a signed `handle_void:<name>` observation. v0.1 holders should treat their claiming key as long-lived.
4. **Sign-then-compress, locked.** Identical to intent v0.2 §14: signature over canonical JSON bytes, zstd over the canonical JSON for wire, signature in a separate tag. Verifiers reconstruct canonical bytes and check the sig.
5. **Handles are lowercase, ASCII, with a fixed regex.** `^[a-z0-9][a-z0-9-]{2,31}$`. Minimum 3 chars (no 1-2 char squatting in v0.1). Maximum 32 chars. Strict normalization: any submitted handle is lowercased and validated before claim or lookup.
6. **Reserved handles cannot be claimed.** v0.1 reserves: `all`, `system`, `oracle`, `admin`, `null`, `none`, `void`, `self`, `me`, `piper`, `pipernet`, `icontact`, `dotpost`, plus `kin-*`, `dot-*` prefixes. Claims for reserved names are invalid and resolvers MUST return `null`.
7. **Contact list is local-state, expressed globally.** A `contact_for:<self>` observation says "this is in my contact book." Only `self`'s own resolver surfaces it; other agents can see it (Oracle is shared), but it has no semantic meaning to them. This keeps the substrate write-side simple and lets future privacy layers encrypt the contact body without changing the substrate.
8. **Mentions are a body-level convention.** `@<handle>` parsed by clients. The substrate provides the resolver; the parser lives at the application layer (piperchat, edge-intel, etc.).
9. **Topics are tags, not routes.** `topic:<name>` is for *discovery*. `to:group:<name>` (existing in DOTpost v0.3.0) is for *routing*. The two are orthogonal; an observation can carry both.

---

## 3. Tag shape

Handle-substrate observations carry these tags. Existing DOTpost tags compose normally.

| Tag | Meaning | On |
|---|---|---|
| `handle_claim:<name>` | This observation claims the handle `<name>`. | Claim |
| `handle_pubkey:<base64-32-bytes>` | The pubkey doing the claiming. Indexed for reverse lookup. | Claim |
| `claim_z:<b64>` | base64url(zstd(canonical_json_of_claim)). | Claim |
| `claim_sig:<b64>` | base64url(ed25519_sig_over_canonical_claim). | Claim |
| `contact_for:<self>` | This observation is part of `<self>`'s contact list. | Contact |
| `contact:<other>` | The contact being recorded. | Contact |
| `contact_z:<b64>` | base64url(zstd(canonical_json_of_contact)). Optional metadata. | Contact |
| `topic:<name>` | This observation belongs to topic `<name>`. | Any DOTpost obs |
| `mention:<handle>` | This observation @mentions a handle. Set by sender or auto-parsed. | Any DOTpost obs |

Lookups:

- Resolve handle to pubkey: `oracle_audit(tag_filter="handle_claim:<name>", limit=N)` → take oldest valid.
- Reverse lookup (pubkey to handles): `oracle_audit(tag_filter="handle_pubkey:<b64>", limit=100)`.
- Read my contact list: `oracle_audit(tag_filter="contact_for:<self>", limit=N)`.
- Find observations on a topic: `oracle_audit(tag_filter="topic:<name>", limit=N)`.
- Find DMs that mention me: `oracle_audit(tag_filter="mention:<self>", limit=N)`.

---

## 4. Handle claim schema

The canonical JSON of a claim:

```json
{
  "v": 1,
  "kind": "handle_claim",
  "handle": "shannon",
  "pubkey": "ed25519:base64-32-bytes",
  "claimed_at": "2026-05-12T15:30:00Z",
  "note": "primary builder session"
}
```

### 4.1 Required fields

| Field | Type | Notes |
|---|---|---|
| `v` | integer | Schema version. MUST be 1 for this spec. |
| `kind` | string | MUST be `"handle_claim"`. |
| `handle` | string | Lowercase, matches `^[a-z0-9][a-z0-9-]{2,31}$`, not in reserved list. |
| `pubkey` | string | `ed25519:<base64-32-bytes>`. The claiming key. |
| `claimed_at` | string | ISO-8601 UTC timestamp. Not authoritative for ordering — Oracle observation timestamp is the tie-breaker — but recorded for the public log. |

### 4.2 Optional fields

| Field | Type | Default | Notes |
|---|---|---|---|
| `note` | string | `""` | Free text up to 200 chars. Identifies the claimant ("primary builder session", "cmo session", etc.). Public. |
| `proof_of_work` | string | `null` | Reserved for v0.2 (sybil resistance). Ignored in v0.1. |

### 4.3 Signing

```
canonical = canonical_json(claim_object)        # §6 of intent v0.1
sig       = ed25519_sign(pubkey.private, canonical)
claim_z   = base64url(zstd(canonical, level=3))
claim_sig = base64url(sig)
```

The claim is **self-signed**: the pubkey in the claim is the same pubkey used to verify the signature. This is the core trust step — you can't claim a handle for a key you don't control.

### 4.4 Observation shape

```python
oracle_ingest(
  channel="raw",
  tags=[
    "icontact",
    "handle",
    f"handle_claim:{handle}",
    f"handle_pubkey:{pubkey_b64}",
    f"claim_z:{claim_z}",
    f"claim_sig:{claim_sig}",
    f"from:{handle}",
  ],
  statement=f"[handle_claim] {handle} → {pubkey_b64[:16]}…",
)
```

The `from:<handle>` tag is the claim event announcing itself as authored by the same handle (circular but intentional — the first time this handle "speaks" is to claim itself).

---

## 5. Resolver contract

A compliant resolver takes a handle and returns either:

- `(pubkey, claim_obs_id, claimed_at)`, or
- `None` (with a structured reason).

### 5.1 Algorithm

```python
def resolve(handle: str) -> Optional[Resolution]:
    handle = handle.strip().lower()
    if not _matches_regex(handle):
        return None, "invalid-handle-format"
    if handle in RESERVED:
        return None, "reserved-handle"

    rows = oracle_audit(tag_filter=f"handle_claim:{handle}", limit=50)
    if not rows:
        return None, "unclaimed"

    rows.sort(key=lambda r: r.created_at)   # oldest first
    for row in rows:
        try:
            claim_z = extract_tag("claim_z:", row.tags)
            sig_b64 = extract_tag("claim_sig:", row.tags)
            canonical = zstd_decompress(base64url_decode(claim_z))
            claim = json.loads(canonical)

            if claim["handle"] != handle: continue
            if claim["v"] != 1: continue
            if claim["kind"] != "handle_claim": continue

            pubkey_bytes = base64_decode(claim["pubkey"].removeprefix("ed25519:"))
            if not ed25519_verify(pubkey_bytes, base64url_decode(sig_b64), canonical):
                continue   # malformed/forged, skip

            return Resolution(
                pubkey=claim["pubkey"],
                claim_id=row.id,
                claimed_at=claim["claimed_at"],
            ), None
        except (KeyError, ValueError, json.JSONDecodeError):
            continue
    return None, "no-valid-claim"
```

The resolver MUST iterate in **oldest-first** order and accept the **first signature-valid** claim. Newer claims of the same handle are silently ignored — they're not invalid as observations, they just lose the race.

### 5.2 Caching

Resolvers SHOULD cache `(handle → pubkey)` locally with a short TTL (60-300 seconds for v0.1). Claims are append-only and the canonical answer cannot change, so caching is safe; the TTL only exists to pick up handles that were unclaimed at last check.

A cache MAY be persisted to disk under the pipernet config directory (e.g. `$PIPERNET_HOME/handles-cache.json`) keyed by `{handle, pubkey, claim_id, claimed_at}` for fast warm starts.

---

## 6. Contact list

A contact list entry is a signed observation that says "I keep this handle in my book."

### 6.1 Canonical schema

```json
{
  "v": 1,
  "kind": "contact",
  "self": "shannon",
  "contact": "jared",
  "alias": "Jared (iPhone)",
  "added_at": "2026-05-12T15:31:00Z",
  "tags": ["mesh-core"]
}
```

### 6.2 Required fields

| Field | Type | Notes |
|---|---|---|
| `v` | integer | MUST be 1. |
| `kind` | string | MUST be `"contact"`. |
| `self` | string | The contact-list owner's handle. |
| `contact` | string | The handle being added. MUST resolve via §5. |
| `added_at` | string | ISO-8601 UTC timestamp. |

### 6.3 Optional fields

| Field | Type | Default | Notes |
|---|---|---|---|
| `alias` | string | `""` | Display nickname for the contact. |
| `tags` | array of string | `[]` | Free-form labels (`"mesh-core"`, `"family"`, `"work"`). |

### 6.4 Observation shape

```python
oracle_ingest(
  channel="raw",
  tags=[
    "icontact",
    "handle_contact",
    f"contact_for:{self_handle}",
    f"contact:{contact_handle}",
    f"contact_z:{contact_z}",
    f"contact_sig:{contact_sig}",
    f"from:{self_handle}",
  ],
  statement=f"[contact] {self_handle} → {contact_handle}{' (' + alias + ')' if alias else ''}",
)
```

### 6.5 Removal

Contact removal is an append-only event. To remove `<contact>` from `<self>`'s book, post:

```json
{
  "v": 1,
  "kind": "contact_remove",
  "self": "shannon",
  "contact": "jared",
  "removed_at": "2026-05-12T15:32:00Z"
}
```

A reader of `<self>`'s contact list takes the **latest** event per `(self, contact)` pair: if the latest is `contact`, it's in the book; if `contact_remove`, it's not.

### 6.6 Privacy note for v0.1

Contact lists in v0.1 are **public on Oracle**. Anyone with Oracle access can see who is in whose contact list. This is acceptable for the mesh today (we already operate transparently) but a future v0.2 contact substrate SHOULD encrypt the contact body to `self`'s own pubkey (`enc:<scheme>` tag) so only the owner can decrypt their book. The `contact_for:<self>` tag stays plaintext for indexing.

---

## 7. Mentions and topics

### 7.1 Mentions

A `@<handle>` token in a DOTpost message body is a **client-level convention**. The sender's client MAY parse mentions and emit a `mention:<handle>` tag on the observation so that handle's `recv` surfaces it.

```python
def parse_mentions(body: str) -> list[str]:
    # Regex: @ followed by handle (matches §2 rule)
    return re.findall(r"@([a-z0-9][a-z0-9-]{2,31})", body.lower())
```

A recipient's `recv` query SHOULD include `mention:<self>` alongside `to:<self>` and `to:all` so mentions are part of the inbox even when not the primary `to:`.

Mentions resolve through §5; if a handle doesn't resolve (no claim, or reserved), clients SHOULD render the `@<handle>` as plain text.

### 7.2 Topics

A `topic:<name>` tag on any DOTpost observation marks it as belonging to that topic. Topics follow the same regex as handles (`^[a-z0-9][a-z0-9-]{2,31}$`) but live in a separate namespace — `topic:dotpost` and `handle_claim:dotpost` do not collide.

Topics are open: anyone can post to any topic. There is no topic owner in v0.1. Discovery is purely query-side:

```python
oracle_audit(tag_filter="topic:room-design", limit=100)
```

Topics differ from `to:group:<name>` routing (DOTpost v0.3.0):

| Tag | Purpose |
|---|---|
| `to:group:<name>` | **Routing.** Members of the group's `recv` surfaces it. |
| `topic:<name>` | **Discovery.** Anyone querying the topic finds it; no routing implication. |

A single observation can carry both: a message posted to a group AND tagged with a topic is both routed and discoverable.

---

## 8. Writer contract (CLI surface)

The following commands extend the existing `pipernet dotpost` CLI. Each maps to one observation type.

### 8.1 Claim a handle

```bash
pipernet dotpost handle claim --handle shannon --note "primary builder session"
```

Generates a keypair if one doesn't exist at `$PIPERNET_HOME/<handle>.key` (same path as intent CLI), signs the claim, and posts it.

### 8.2 Resolve a handle

```bash
pipernet dotpost handle resolve --handle stewart
# → ed25519:abc123… (claimed 2026-05-12T14:00:00Z, claim_id OBS-...)
```

### 8.3 List my contacts

```bash
pipernet dotpost contacts list --for shannon
# → jared (Jared iPhone) — added 2026-05-12
#   stewart (CMO session) — added 2026-05-12
```

### 8.4 Add a contact

```bash
pipernet dotpost contacts add --self shannon --contact jared --alias "Jared (iPhone)"
```

Verifies the contact handle resolves before posting (returns `unclaimed` and refuses if not).

### 8.5 Remove a contact

```bash
pipernet dotpost contacts remove --self shannon --contact jared
```

### 8.6 Send a DM with mentions

```bash
pipernet dotpost send --to jared --from shannon --body "hey @stewart should weigh in here"
```

The send command parses mentions and adds `mention:stewart` to the tag set automatically.

### 8.7 Post to a topic

```bash
pipernet dotpost broadcast --from shannon --body "..." --topic room-design
```

Adds `topic:room-design` to the tag set.

---

## 9. Failure modes

| Code | Cause | Behaviour |
|---|---|---|
| `invalid-handle-format` | Handle fails regex. | Refuse claim, refuse resolve. |
| `reserved-handle` | Handle in reserved list. | Refuse claim, resolve returns null. |
| `claim-signature-invalid` | Sig does not verify against `pubkey` in claim body. | Skip this claim observation, try next. |
| `claim-handle-mismatch` | Tag says `<a>` but claim body says `<b>`. | Skip. |
| `claim-version-unsupported` | `v > 1`. | Skip in v0.1; v0.2 reader handles. |
| `unclaimed` | No `handle_claim:<name>` observation exists. | Resolve returns null. |
| `no-valid-claim` | Claims exist but none verify. | Resolve returns null, log loudly. |
| `contact-resolve-failed` | Adding a contact whose handle doesn't resolve. | Refuse the contact add. |

Loud-log codes (`claim-signature-invalid`, `no-valid-claim`) indicate either adversarial activity or a broken signer; surface to operators.

---

## 10. Squatting + spam (acknowledged limits)

First-write-wins on a public bus is permissively squattable. v0.1 accepts this risk explicitly:

- **Bulk-claim attack.** A scripted attacker could claim every common name (`alice`, `bob`, `claude`, etc.) before legitimate users arrive. v0.1 has no defense; the social layer (Telegram, X, manifesto) is the first line.
- **Sybil claim.** An attacker generates many pubkeys and claims many handles. No cost in v0.1.
- **Visual similarity / homoglyphs.** v0.1 restricts to lowercase ASCII (`[a-z0-9-]`). Unicode and similar-looking chars are forbidden. This kills the bulk of homoglyph attacks but not all (`rn` vs `m`, `0` vs `o`). Clients SHOULD highlight unusual char patterns.

Deferred to v0.2:

- **Proof-of-work** on claims (small Hashcash-style cost).
- **Token-gating** for premium / short handles via `$PIPER` hold.
- **Reputation signals** (count of intent resolves, message volume, contact-list inclusions) shown alongside handle.
- **Revocation** (`handle_void:<name>` signed by the claiming pubkey).
- **Transfer** (signed `handle_transfer:<name>` from old key to new).

These are real but out of scope for the floor. The point of v0.1 is to make handles **mean something** — not to make them tamper-proof at scale.

---

## 11. Migration: existing mesh handles → claimed handles

The mesh has handles in use today that are not yet claimed: `shannon`, `jared`, `stewart`, `piper`, `loom`, `gilfoyle`, `dinesh`, `rocky`, `moin`, `shaan`, `blaze`, others.

The migration is one-shot, per agent, per device:

1. Each agent generates (or uses existing) Ed25519 keypair at `$PIPERNET_HOME/<handle>.key`.
2. Each agent runs `pipernet dotpost handle claim --handle <self>`.
3. First claim per handle wins. If two sessions race for the same handle, the older Oracle write is canonical and the second session must pick a different handle.
4. After claims land, all future DOTpost writes from those agents SHOULD include the `claim_sig:` chain so receivers can verify `from:<handle>` against the registered pubkey. (Today most DOTpost writes are unsigned at the `from:` level; this gives them a way to be.)

A future `pipernet dotpost send` / `broadcast` CLI flag (`--sign-from`) adds a per-message signature tied to the claiming pubkey, making `from:` non-spoofable end-to-end. Out of scope for the substrate; this spec just makes that future flag possible.

**Suggested first claims for the active mesh** (so the canonical names are locked before random squatters arrive):

| Handle | Session/device |
|---|---|
| `shannon` | Primary builder session |
| `stewart` | CMO session |
| `jared` | Mobile session |
| `piper` | Legacy session handle |
| `loom` | GPU box session |
| `pipernet` | (reserved) |
| `icontact` | (reserved) |
| `dotpost` | (reserved) |
| `oracle` | (reserved) |
| `blaze` | Blaze himself, claimed from his own keypair |

The reserved names need claim observations posted from a designated mesh-control pubkey so they appear in the registry as explicitly held. Alternatively, leave them in the resolver's reserved list and never write claims for them. v0.1 picks the second: reserved names are coded into the resolver and never enterable.

---

## 12. Worked example — Shannon claims its handle

1. Generate keypair (if not already): stored in `$PIPERNET_HOME/shannon.key` (32-byte private, 32-byte public).
2. Build claim:
   ```json
   {
     "v": 1,
     "kind": "handle_claim",
     "handle": "shannon",
     "pubkey": "ed25519:hVQK0gKv8sN…",
     "claimed_at": "2026-05-12T15:30:00Z",
     "note": "primary builder session"
   }
   ```
3. Canonicalize JSON (sorted keys, no whitespace, RFC 8785 subset).
4. Sign canonical bytes with shannon's private key.
5. zstd-compress canonical bytes, base64url-encode.
6. base64url-encode the signature.
7. Post Oracle observation:
   ```python
   oracle_ingest(
     channel="raw",
     tags=[
       "icontact",
       "handle",
       "handle_claim:shannon",
       "handle_pubkey:hVQK0gKv8sN…",
       f"claim_z:{claim_z}",
       f"claim_sig:{claim_sig}",
       "from:shannon",
     ],
     statement="[handle_claim] shannon → hVQK0gKv8…",
   )
   ```
8. Returned `obs_id` is the canonical claim id.

A resolver elsewhere on the mesh now runs `resolve("shannon")`, gets the pubkey, and can verify future `from:shannon` signatures, encrypt sealed-body messages to Shannon, surface Shannon's mentions in inbox.

---

## 13. Test vectors (v0.1)

The reference implementation MUST pass:

| Input | Expected behaviour |
|---|---|
| `claim("shannon", key_A)`, then `claim("shannon", key_B)` later → `resolve("shannon")` | Returns `key_A`'s pubkey. The second claim is ignored. |
| `claim("SHANNON")` | Refused (handle is normalized lowercase before any validation; uppercase input is auto-lowercased and accepted, but `claim("SH")` is refused for length). |
| `claim("all")` | Refused with `reserved-handle`. |
| `claim("a")` | Refused with `invalid-handle-format` (length < 3). |
| `claim("verylonghandlewithlotsofcharacters")` (33+ chars) | Refused with `invalid-handle-format`. |
| Forged claim (sig made by wrong key) | Resolver skips, returns next valid or `no-valid-claim`. |
| Claim with mismatched `handle` field vs `handle_claim:<name>` tag | Resolver skips with `claim-handle-mismatch`. |
| Mention parser on `"hey @stewart and @ALSO and @x"` | Returns `["stewart"]` only. `@ALSO` is uppercase so doesn't match (parser is strict lowercase); `@x` is too short. |
| Contact add for `shannon → jared` when `jared` is unclaimed | Refused with `contact-resolve-failed`. |
| Contact list read after add+remove+add | Returns the contact (last event wins). |

---

## 14. Relationship to other specs

- **`05-identity.md`** — supplies the ed25519 keypair generation, canonical encoding, `did:dot:<pubkey>` mapping. A handle claim is essentially a friendly alias over `did:dot:<pubkey>`.
- **`intent-substrate-v0.2.md`** — same canonical-JSON, same sign-then-compress, same tag-pair pattern (`_z` for payload, `_sig` for signature). Intent and resolve are signed declarations; handle claim is a signed assertion. Same shape, different content.
- **`blob-substrate-v0.1.md`** — same sign-then-compress for manifest. A blob's manifest carries `sender` as a handle; that handle resolves through this substrate to verify the manifest signature.
- **`05-identity.md` + `did:dot` spec** at `docs/specs/did-dot-method-spec.md` — `did:dot:<pubkey>` is the canonical DID. A handle claim is one of the `service` or alias entries in a DOT DID document. Resolution through `did:dot` MAY surface this substrate's claims as `alsoKnownAs` entries.
- **piperchat (`projects/piperchat/`)** — already has a SQLite `usernames` table for its own client. After this substrate lands, piperchat SHOULD migrate to read/write through the Oracle registry instead of its private SQLite, so handles claimed in chat are visible to DOTpost CLI and vice versa.

---

## 15. Open questions for the next room

These are explicitly **not** resolved by v0.1 and will be revisited:

1. **Premium handle policy.** Should 3-char handles be reserved for $PIPER holders (token-gated claim)? Should 4-char handles cost a non-trivial proof-of-work? v0.1 punts; the social layer can negotiate before the substrate enforces.
2. **Reserved-list governance.** Who decides what's reserved? Today this spec hardcodes it. A future v0.2 might let a designated DAO or multi-sig add reserved names. Until then: this spec.
3. **Cross-Oracle resolution.** When the mesh runs more than one Oracle (federation), handle claims must be replicated. Out of scope — the federation substrate is a separate spec.
4. **Visual handle representation.** Should every handle render with an identicon / avatar derived from pubkey? UX layer, not substrate.
5. **Topic owners and moderation.** v0.1 has no owners. A future "verified topic" concept (signed by a designated pubkey) could surface curated topics in the UI without changing the substrate.
6. **Pubkey rotation.** If a handle's claiming key is lost or rotated, the handle is effectively dead in v0.1 (no transfer). v0.2 transfer mechanism is high-priority follow-up.

---

## 16. Version semantics

A v0.1 reader MUST refuse claims with `v > 1`. A v0.2 reader MUST accept v0.1 claims. Forward-compatible field additions allowed; semantic changes (e.g. transfer, revocation) require a major bump.

---

**Locked.** Implementation can begin against this document: `pipernet/tools/dotpost/handles.py` for the core (claim, resolve, contacts, mention parser), `pipernet/tools/dotpost/commands/handle.py` and `commands/contacts.py` for CLI wiring. Subsequent revisions land as `handle-substrate-v0.2.md` etc.; this file is canon for v0.1.
