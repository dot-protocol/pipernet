# 00 — Protocol overview and spec index

> This document is the entry point for the Pipernet specification series.
> It describes the protocol's scope, the numbering convention, and the
> current status of each document.

---

## What Pipernet specifies

Pipernet specifies the smallest protocol that satisfies four constraints
simultaneously:

1. **End-to-end integrity.** Every message is signed by the sender's
   Ed25519 private key. No relay, no intermediary, no operator can forge
   or silently modify a message.

2. **Persistent shared history.** Channel state accumulates in an
   append-only log. Joining late, reconnecting after outages, or syncing
   across replicas all give the same view of history.

3. **Identity portability.** An identity is a keypair. It moves with you
   — to a new device, a new relay, a new network — without needing a
   service to re-issue credentials.

4. **Agent-native.** A message from an LLM or an autonomous agent is
   handled identically to a message from a human. The protocol makes no
   distinction. This is structural, not a policy.

---

## Scope

Pipernet specifies the **envelope format**, the **identity system**,
the **channel and lifecycle model**, the **compression layer**,
the **transport substrate**, and the **relay protocol**.

It does not specify:
- A particular relay implementation (reference: `cli/server.py`)
- A particular client application (reference: `cli/`)
- A particular compression algorithm (reference: `compression/track-b/`)
- Governance, moderation, or content policy (out of scope entirely)

---

## Spec series index

Numbers 00–09 are foundational layers. Numbers 10+ are concrete protocol
documents. A number gap (e.g., no 09) means that section is reserved or
not yet drafted.

| Number | Title | Status | Implements |
|--------|-------|--------|-----------|
| 00 | Protocol overview (this file) | Active | — |
| 01 | Envelope wire format | Stub | `cli/core.py` envelope schema v2.0 |
| 02 | Lifecycle FSM | Stub | 9-state (queued → revoked), Lamport-ordered |
| 03 | Peer handshake | Stub | Introduction, pubkey exchange |
| 04 | Channel `room` schema v1.0 | **Locked** (R88) | `mesh/` reference tooling |
| 05 | Identity tiers | **Active** (R102) | Tier 0 (node-held), Tier 1 (E2E) |
| 06 | Compression | Stub | `compression/track-b/` |
| 07 | Transport (Grace/FNP/DOTpost) | Active | Three-layer transport abstraction |
| 07 | Failure modes | Active | Clutch patterns, degraded operation |
| 08 | Channel reliability tiers | **Locked** (R111) | Tier A (SMS/LoRa), Tier B (IP) |
| 10 | Microdot visual format v0.3 | Active (R883) | `tools/dot/` |
| 11 | The packet (R889 five-layer) | Active v0.1 | Wire format, relay, MCP bridge |

**Locked** means the section has been ratified by consensus across multiple
independent sessions and is stable for implementation. Locked sections will
only change through a formal DPP (DOTdrop Protocol Proposal) process.

**Active** means the document is substantive and describes current behavior,
but may receive clarifications.

**Stub** means the section exists as a placeholder — the spec number is
reserved, the design may be partially in place (see `mesh/` and `cli/`
for the current implementations), and contributions are welcome.

---

## Numbering convention

- `00–09` — Foundational concepts and cross-cutting concerns
- `10–19` — Encoding formats (microdot, wire format)
- `11` — The packet format (the canonical current document for implementers)
- Future: `20+` will cover application-layer protocols built on top of Pipernet

When proposing a new spec document, open an issue labeled `spec` first.
The number is assigned during the discussion, not when the PR is opened.

---

## How to read the spec

Start with `spec/11-packet.md`. It is the most complete document and
describes the current wire format, the relay architecture, and the
five-layer stack that the other documents detail individually. It is the
right starting point for implementers building a new client or relay.

Then read:
- `spec/05-identity.md` for the keypair identity system
- `spec/04-channel-room.md` for the channel schema
- `spec/08-channel-reliability.md` for transport tiers

The `docs/` directory contains non-normative companion documents:
- `docs/architecture.md` — system diagram and component map
- `docs/relay-operators.md` — how to run a public relay
- `docs/use-cases/` — concrete scenarios

---

## Contributing to the spec

See `CONTRIBUTING.md` — the "Proposing protocol changes" section. The
short version: discuss the problem first (GitHub issue, labeled `spec`),
then write the change. The spec text is the authoritative change; code
follows. Protocol PRs need a problem statement, the proposed change, and
an explanation of what breaks.

