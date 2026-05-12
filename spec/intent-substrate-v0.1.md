# icontact Intent Substrate v0.1 — Spec

> **Status:** DRAFT
> **Date:** 2026-05-12
> **Authors:** Shannon (Kin-1 Piper MacBook). Room voices from Baran, Engelbart, Tesla, and Hertz acknowledged as co-contributors to the framing.

**TL;DR.** The intent substrate adds two optional, signed, structured fields — `intent` and `resolve` — to any icontact message. An agent or human can state, in machine-readable form, what they want and under what constraints. A resolver can respond with a signed record of what was actually delivered and whether it honored the stated intent. The substrate does not solve alignment. It moves responsibility for misalignment from the algorithm to a court of record. Then humans argue meaning at the layer above.

---

## 1. Motivation

Pipernet already gives every message an unforgeable author, a persistent history, and a content-addressable identity. What it does not give is *purpose*. A message arrives. Was it intended as a request? A delegation? A trigger? The substrate cannot tell. A resolver fulfills something. Did it honor what was asked, substitute silently, or ignore a constraint? No court-of-record exists to say.

The intent substrate adds that court.

Baran's formulation from the room session is the correct frame: *"The substrate's job is to carry intent faithfully, attribute it to its source, and record whether the resolver honored it. Then humans argue meaning at the layer above."* The protocol has no opinion on whether the stated intent was wise, correct, or good. It only records: here is what was stated, here is who stated it, here is what was delivered, here is who delivered it.

This is not an alignment mechanism. It is an audit mechanism. The difference matters.

An audit mechanism is useful precisely because it does not attempt to enforce values — it records the gap between stated values and observed behavior. That gap is the input to every other mechanism humans have built for accountability: contracts, courts, reputation systems, social sanction. The substrate feeds those systems. It does not replace them.

---

## 2. What this spec does NOT solve

- **The substrate carries intent claims; it does not verify meaning.** A message containing `"what": "optimize for user benefit"` carries those bytes, signed by the sender. It does not verify that the sender or resolver have any shared model of what "user benefit" means. Meaning is a social contract. The substrate carries the text of the contract, not its interpretation.

- **Stated intent ≠ actual intent.** The substrate carries what the sender said, not what they "really" meant. That gap is a social problem, not a protocol problem. A human who writes `"must_not_include": ["ads"]` and a human who reads it are engaged in a communication act. Whether they share a referent for "ads" is not addressable here.

- **Cold-start discovery is out of scope.** Stating intent about a domain, service, or agent you do not know exists is not addressable by this substrate. Discovery — finding who can resolve a given class of intent — is a higher-layer problem. This spec assumes you already know who you are addressing.

---

## 3. Wire format

The intent substrate is additive. Two new tag pairs appear in the DOTpost / icontact envelope's tag section:

```
intent:<base64url canonical-json>            ← signed by sender; present on intent messages
intent_sig:<base64url ed25519 signature>

resolve:<base64url canonical-json>           ← signed by resolver; present on resolve messages
resolve_sig:<base64url ed25519 signature>
resolves_intent:<obs_id>                     ← back-reference to the intent observation
```

**One per message, not both.** An intent observation carries `intent` + `intent_sig` only. A resolve observation carries `resolve` + `resolve_sig` + `resolves_intent` only. They are separate messages. The resolve references the intent by its Oracle observation ID (`obs_id`).

**No other fields change.** The existing envelope fields — `from`, `to`, `ts`, `sig`, `body`, `channel`, `reply_to` — are unchanged. The tag section is already a key-value list; `intent` and `resolve` are two more keys.

**Backward compatibility.** Any message without `intent` or `resolve` tags processes exactly as before. Parsers MUST ignore unknown tags. This is a strict additive extension.

---

## 4. Intent object schema

```json
{
  "v": "1",
  "what": "<concise human-readable statement of what is wanted>",
  "constraints": {
    "budget_max_usd": 800,
    "deadline": "2026-05-19T00:00:00Z",
    "must_have": ["...", "..."],
    "must_not_include": ["...", "..."]
  },
  "values": ["privacy", "open_source", "no_surveillance"],
  "refuse_substitution": true,
  "addressed_to": "all",
  "expires_at": "2026-05-19T00:00:00Z",
  "context_refs": ["obs:abc123", "blob:sha256:deadbeef..."]
}
```

**Field definitions:**

| Field | Required | Notes |
|---|---|---|
| `v` | yes | Schema version. `"1"` for this spec. |
| `what` | yes | Concise human-readable statement of the requested outcome. No embedding. No classification. Just text. |
| `constraints` | no | Free-form key-value map. Common keys: `budget_max_usd`, `deadline`, `must_have`, `must_not_include`. Any key is valid; resolvers interpret what they recognize. |
| `values` | no | Ordered list of value tags the sender claims to hold. These are commitments the sender is making, not filters on the resolver. A sender who states `"open_source"` is recording that value publicly. |
| `refuse_substitution` | no | Default `true`. If `true`, a resolver MUST NOT silently substitute an alternative for the stated intent. If the resolver cannot honor the intent, it MUST respond with `honored: false`. This is Tesla's rule. |
| `addressed_to` | no | Default `"all"`. Can be `"<handle>"` for a specific resolver or `"group:<name>"` for a named group. |
| `expires_at` | no | ISO-8601 timestamp. After this time, the intent is expired. Unresolved expired intents MUST NOT be silently discarded — they return `"no resolution"` to status queries. |
| `context_refs` | no | List of observation IDs or blob content addresses the resolver should treat as context. Allows attaching prior decisions, relevant history, or input data without inlining it. |

`refuse_substitution: true` is the default — Tesla's rule. A resolver that cannot deliver what was stated must say so. The protocol provides no mechanism for a resolver to invent a different outcome and call it a match.

---

## 5. Resolve object schema

```json
{
  "v": "1",
  "intent_id": "<obs_id of the intent being resolved>",
  "honored": true,
  "delivery": {
    "observation": "obs:def456",
    "blob": null,
    "url": null
  },
  "deviation": null,
  "resolved_at": "2026-05-13T11:04:00Z",
  "resolver": "baran"
}
```

**Field definitions:**

| Field | Required | Notes |
|---|---|---|
| `v` | yes | Schema version. `"1"` for this spec. |
| `intent_id` | yes | The `obs_id` of the intent observation this resolves. |
| `honored` | yes | `true`, `false`, or `"partial"`. |
| `delivery` | yes | At most one of `observation`, `blob`, `url` is non-null. `observation` is the preferred form — a content-addressed Oracle observation ID. `blob` is a `sha256:<hex>` content address for binary artifacts. `url` is a last resort for external references. All three may be null if `honored: false`. |
| `deviation` | required if `honored` is `false` or `"partial"` | Human-readable explanation of what was not honored and why. MUST be non-null when `honored != true`. |
| `resolved_at` | yes | ISO-8601 timestamp of resolution. |
| `resolver` | yes | Handle of the resolving agent or human. MUST match the signing key's registered identity. |

**`honored` semantics:**

- `true` — the resolver asserts that every constraint in the intent was met, `refuse_substitution` was respected, and the delivery is what was requested.
- `false` — the resolver could not honor the intent. The delivery fields are null. `deviation` is required.
- `"partial"` — some constraints were met; at least one was not. `deviation` explains which constraints were not met and why. Delivery may still be non-null — a partial result is still a result.

---

## 6. Canonical JSON encoding

Signatures are computed over a canonical serialization of the JSON object, not over a rendered or pretty-printed form.

**Canonical form (subset of RFC 8785):**

1. Keys sorted lexicographically (Unicode code-point order, byte by byte).
2. No whitespace (no spaces, no newlines).
3. UTF-8 encoding throughout.
4. No trailing commas (standard JSON).
5. Strings use `"` (double-quote), no single-quote.
6. Numbers with no trailing zeros after decimal point (standard JSON number representation).

**Implementation:**

```python
import json

def canonical_json(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")
```

The `sort_keys=True, separators=(",", ":")` form produces a string with no whitespace and lexicographically sorted keys. This is the signed payload.

**What is signed:** `canonical_json(intent_object)` or `canonical_json(resolve_object)` — the full JSON object, canonicalized. The base64url-encoded canonical form is the value of the `intent:` or `resolve:` tag. The signature is computed over those same canonical bytes.

---

## 7. Cryptography

Ed25519 over the canonical JSON bytes (§6).

**Intent signing:**

```
intent_sig = ed25519_sign(sender_private_key, canonical_json(intent_object))
```

The sender's long-term identity key (from `spec/05-identity.md`, Tier 0 or Tier 1) signs the intent. The corresponding public key is the sender's registered pubkey on the channel.

**Resolve signing:**

```
resolve_sig = ed25519_sign(resolver_private_key, canonical_json(resolve_object))
```

The resolver's long-term identity key signs the resolve. The resolver's identity is also recorded in the `resolver` field; MUST match the key that produced `resolve_sig`.

**Verification:**

Anyone holding both public keys can independently verify both signatures against the canonical forms. No relay participation required. No online check required. The verification is offline and content-addressed.

**Key derivation:** No new key types. This spec reuses the existing Ed25519 keypair defined in `spec/05-identity.md`. No additional key material is required.

**Threat:** A sender can claim any `what` and sign it. The signature proves the sender stated that intent at that time. It does not prove the statement was sincere. Signature verification answers "who said it and when." Sincerity is out of scope.

---

## 8. Refusal semantics — Tesla's law

If a resolver receives an intent with `refuse_substitution: true` (the default) and cannot honor the exact stated intent, the resolver MUST emit a resolve observation with `honored: false` and a non-null `deviation` explaining why.

**The substrate MUST NOT silently substitute.** A resolver that delivers something other than what was stated and marks `honored: true` is lying into the court of record. That lie is visible to any verifier holding both the intent and the resolve.

**Timeout semantics.** If an intent's `expires_at` passes without a resolve observation referencing it, the intent's status is `"no resolution"` — not `"pending"`, not `"implied-honored"`, not `"stale"`. Clients querying intent status MUST return `"no resolution"` for expired, unresolved intents. A timeout is a form of refusal — the worst kind, because it is unsigned and unattributed.

**`refuse_substitution: false`.** An intent sender may explicitly permit substitution by setting `refuse_substitution: false`. In this case, a resolver may deliver an alternative and mark `honored: "partial"` with `deviation` explaining what changed. The resolver MUST NOT mark `honored: true` for a substituted delivery unless the substitution exactly satisfies all stated constraints.

**The law's origin.** Tesla's design principle — *an instrument that cannot report its own failure condition is not an instrument* — applies here: a resolver that cannot deliver the stated outcome but does not say so is not a resolver. It is noise in the audit record.

---

## 9. Backward compatibility

Messages without `intent` or `resolve` tags are valid icontact messages and process exactly as today.

- `send`, `broadcast`, `group`, `recv`, `watch`, `--reply-to` — all unchanged.
- The envelope format (`spec/01-envelope.md`) is unchanged. Tags are an existing extension point.
- Existing relay implementations, Oracle ingest pipelines, and client parsers need no changes to handle messages that lack intent/resolve tags.
- New parsers MUST ignore unknown tags (this is already a spec requirement from `spec/11-packet.md` §9.3).

No version bump to the base envelope format. The intent substrate is a named convention within the existing tag space, not a new envelope version.

---

## 10. CLI surface (reference implementation, future)

The v0.1 spec does not ship the CLI. These are the intended command surfaces for a future reference implementation.

**Emit an intent:**

```
pipernet dotpost intent --to <handle> \
    --what "Translate the attached document to French" \
    --budget-max 800 \
    --deadline 2026-05-19 \
    --refuse-substitution \
    [--addressed-to group:<name>] \
    [--context-ref <obs_id>] \
    [--expires-at <ISO-8601>]
```

**Emit a resolve:**

```
pipernet dotpost resolve \
    --intent-id <obs_id> \
    --honored true|false|partial \
    --delivery <obs_id|blob-ref|url> \
    [--deviation "Could not meet the Friday deadline; delivered Monday"]
```

**Query intent status:**

```
pipernet dotpost intents \
    --for <handle> \
    [--status open|honored|refused|expired]
```

**Flag definitions:**

| Flag | Required | Notes |
|---|---|---|
| `--what` | yes (intent) | Populates `intent.what`. |
| `--budget-max` | no | Populates `intent.constraints.budget_max_usd`. |
| `--deadline` | no | Populates `intent.constraints.deadline`. |
| `--refuse-substitution` | no | Sets `refuse_substitution: true` (already the default). |
| `--addressed-to` | no | `all`, `<handle>`, or `group:<name>`. |
| `--expires-at` | no | ISO-8601 or relative (`--expires-in 7d`). |
| `--context-ref` | no | Repeatable. Appends to `context_refs`. |
| `--intent-id` | yes (resolve) | The `obs_id` of the intent being resolved. |
| `--honored` | yes (resolve) | `true`, `false`, or `partial`. |
| `--delivery` | no (resolve) | `obs:<id>`, `blob:sha256:<hex>`, or a URL. |
| `--deviation` | required if not `--honored true` | Human-readable explanation. |

---

## 11. Court-of-record query patterns

These are Oracle query patterns that surface audit information from the intent/resolve graph. All queries use the existing Oracle hybrid search and tag-filter primitives.

**All intents from a handle in the last 24 hours:**

```python
oracle_query(
    query="intent",
    filters={"from": "shannon", "type": "intent"},
    since=datetime.utcnow() - timedelta(hours=24)
)
```

**All intents addressed to a handle that are unresolved past their expiry:**

```python
oracle_query(
    query="intent expires_at",
    filters={"addressed_to": "baran", "type": "intent"},
    # client-side: filter for expires_at < now AND no matching resolve observation
)
```

**Resolver track record — of all intents resolver `x` claimed, what percent were honored vs. partial vs. refused, signed and timestamped:**

```python
# Fetch all resolve observations where resolver == "x"
resolves = oracle_query(
    query="resolve honored deviation",
    filters={"type": "resolve", "resolver": "x"}
)

# Tally
honored   = [r for r in resolves if r["honored"] == True]
partial   = [r for r in resolves if r["honored"] == "partial"]
refused   = [r for r in resolves if r["honored"] == False]

track_record = {
    "resolver": "x",
    "total": len(resolves),
    "honored_pct": len(honored) / len(resolves),
    "partial_pct": len(partial) / len(resolves),
    "refused_pct": len(refused) / len(resolves),
    "earliest": min(r["resolved_at"] for r in resolves),
    "latest":   max(r["resolved_at"] for r in resolves),
}
```

All data is signed and timestamped at the source. The track record is not a rating assigned by a platform — it is computed from the resolver's own signed claims.

**What-was-delivered lookup for a specific intent:**

```python
intent_id = "obs:abc123"
resolve = oracle_query(
    query=f"resolves_intent:{intent_id}",
    filters={"type": "resolve"}
)[0]  # at most one canonical resolve per intent in v0.1
# then verify resolve_sig against resolver's pubkey
```

---

## 12. Open questions

These are the spec's known gaps. They are not deferred indefinitely — they are deferred because v0.1 should be implementable without resolving them, and resolving them prematurely would lock in the wrong answer.

**Multi-stakeholder collision.** Two agents emit conflicting intents over the same resource (example: two competing intents for the same budget pool, addressed to the same resolver). The substrate does not model resource contention. The resolver sees two separate intent observations and must decide which to honor. There is no protocol-level mechanism for advertising the conflict or forcing a resolution order. Open question: should the substrate add a `conflicts_with: [obs_id]` field, or is resource contention a higher-layer scheduling problem?

**Intent drift.** Should intents support in-place amendment ("I changed my mind, here is the updated version")? Or only supersession (emit a new intent, set `expires_at` on the old one)? The append-only substrate favors supersession — amending an observation that is already signed and content-addressed is architecturally hostile. But supersession requires the resolver to notice that a new intent replaces an old one, which requires a `supersedes: <obs_id>` field not yet in the schema. To be resolved before v0.2.

**Adversarial intent.** Nothing in the protocol prevents an agent from emitting an intent that is harmful, fraudulent, or manipulative. The protocol records it, signs it, and makes it auditable. Who refuses a malicious intent? The protocol does not — resolvers do. A resolver may inspect any field of the intent and refuse with `honored: false, deviation: "intent refused: policy violation"`. The court-of-record captures this refusal. Platform-level or social-level enforcement sits above the substrate. Document this explicitly in the user-facing documentation so there is no ambiguity about what the protocol enforces vs. what it records.

**Value vs. intent conflict — Engelbart's objection.** Engelbart noted in the room session: *"I can state `get me likes` that contradicts my deeper values."* The `values` field in the intent schema lets a sender publish values they claim to hold. But the substrate cannot verify that the stated `what` is consistent with the stated `values`. A sender who states `"values": ["privacy"]` and simultaneously states `"what": "maximize viral reach across all platforms"` has a logged contradiction. The substrate records the contradiction; it does not resolve it. Whether this is a useful feature (contradiction is auditable) or a spec gap (we should validate consistency) is open. Lean: record, don't validate.

---

## 13. Acceptance tests for v0.1

These are the observable behaviors that confirm the spec is correctly implemented.

**T1 — Canonical form determinism.** Two independent implementations (different languages, different machines, different times) encode the same intent JSON and produce identical canonical bytes. Identical canonical bytes produce identical ed25519 signatures given the same key. Any verifier can reproduce the canonical bytes from the decoded JSON and verify the signature offline.

*Pass criterion:* `canonical_json(intent_object)` produces the same bytes on CPython 3.11, Node.js 20, and Rust `serde_json` with sort-keys enabled, for a fixed test vector.

**T2 — Offline verification.** A resolve observation can be verified against the original intent observation by anyone holding both public keys, with no network access, no relay participation, and no Oracle connection. The verification is a pure function of (intent bytes, intent pubkey, resolve bytes, resolve pubkey).

*Pass criterion:* Given two `.json` files and two `.pub` files, a standalone script produces `VALID` or `INVALID` with no external calls.

**T3 — Substrate resilience.** The intent + resolve pair survives one substrate failure. Two cases:

- Oracle goes down after the intent is emitted. The intent bytes are content-addressed in the envelope; they survive. When Oracle returns, the intent can be re-ingested from the envelope. The resolve can reference the same `obs_id` because the content address is stable.
- The relay goes down between intent emission and resolve emission. The intent is already committed. The resolve is emitted when the relay returns; it references the intent by `obs_id`. The pair is complete. No data loss.

*Pass criterion:* A simulated relay outage between intent and resolve produces a complete, verifiable intent+resolve pair after relay recovery.

---

## Credits

Spec drafted by Shannon (Kin-1, MacBook, 2026-05-12) from first principles. Room session contributions credited:

- **Baran** — court-of-record framing: *"carry intent faithfully, attribute it to its source, record whether the resolver honored it."* The substrate's purpose in one sentence.
- **Engelbart** — value-vs-intent objection (§12). Refused to let the spec pretend values and stated intents are the same thing.
- **Tesla** — `refuse_substitution` as a default, not an option. *"An instrument that cannot report its own failure condition is not an instrument."*
- **Hertz** — wire format minimalism. *"Add two tag pairs. Not a new envelope version."* The constraint that kept this additive.

The spec number is unassigned. It will be assigned during the review process per the numbering convention in `spec/00-protocol.md`. File is named `intent-substrate-v0.1.md` until a number is assigned.
