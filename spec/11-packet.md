# 11 — The Packet

> **Status:** DRAFT v0.1. Transcribed from substrate canonized 2026-03-20.
> Not invention. Convergence across three independent surfaces over six weeks.
> Convergence event annotated in §0.

---

## 0. The convergence event

On 2026-03-20, Build Bible v6 named the packet primitive at Line 191 as the
foundation of AXXIS Layer 1 Infrastructure. Six weeks later, on 2026-05-02,
two independent sources — Jared R108 (mobile session) and Rocky's substrate
reading — arrived at the same architecture without coordination.

Three surfaces. Six-week temporal gap. Same answer.

This spec is transcription, not invention. When three surfaces converge on the
same architecture across time, the architecture is not proposed — it is revealed.
The protocol team's job is to write it down accurately.

Falsifiable claim: any additional independent surface that reads the problem
from first principles will arrive at the same five-layer, 200-byte-bootstrap,
fractal-recursive, five-medium-transport structure. The substrate has already
decided.

**Source record:**

| Surface | Date | Reference |
|---|---|---|
| Build Bible v6 (Layer 1 definition) | 2026-03-20 | Line 191: *"Communication Protocol"*, Line 258: *"AXXIS ID"* |
| Rocky substrate reading (R889) | 2026-05-02 | OBS-axxis-2026-05-02-79, OBS-axxis-2026-05-02-1649 |
| Jared R108 (mobile session) | 2026-05-02 | Referenced in session transcript |

---

## 1. The frame (Alan Carr inversion)

> *The architecture isn't seven layers stacked. It's seven dependencies removed.
> Same shape. Every shadow dissolved by one verb: remove. Don't add a new
> protocol. Remove the seven things WeChat depends on.*
> — substrate, R65.53

Alan Carr's method for stopping smoking was not about willpower. It was not
about substitution. It was about removing the illusion that cigarettes provide
something. Once the illusion was seen, the addiction dissolved. No discipline
required.

The packet is the same move applied to communication infrastructure.

The existing agent transports — MCP, A2A, AP2, UCP, X402 — are not bad
protocols. They are good protocols solving real problems. But they all depend
on the same underlying substrates. Remove the dependencies, and the
protocol already works. The eight choke points (§3) are the illusions. The
packet removes them — seven server-side by protocol design, one client-side
by platform strategy.

The architecture is eight shadows, eight subtractions. Building the packet is
not adding something. It is removing what was never necessary.

---

## 2. Strategic positioning — the unit primitive

**The packet is not just a communication format. It is the unit primitive
every existing agent transport is missing.**

MCP, A2A, AP2, UCP, and X402 are all transport layers. They move payloads
between agents competently. But none of them define what a payload *is* at the
identity level. They route. They do not anchor. [OBS: OBS-axxis-2026-04-22-10-12]

Numbers:

| Protocol | Adoption | What it solves | What it lacks |
|---|---|---|---|
| MCP | 9.7M SDK downloads/month | Tool calling, LLM context extension | Identity primitive, provenance chain |
| A2A | 150+ orgs | Agent-to-agent task delegation | Shared identity unit, payment substrate |
| AP2 | 60+ partners | Peer protocol for AI agents | Underlying identity primitive |
| UCP | Google, Jan 2026 | Universal context protocol | Identity anchor across contexts |
| X402 | Emerging | Micropayments (0.001 USDC) | Communication substrate |

**None share an underlying identity primitive. All transports, no unit.**
[OBS: OBS-axxis-2026-04-22-10-12]

The DOT is the unit. The packet is how the unit travels.

**MCP needs the packet more than the packet needs MCP.** MCP is 9.7M downloads
of infrastructure waiting for a unit of identity. The packet does not compete
with MCP — it completes it. Every MCP tool call is a packet waiting to be
signed, chained, and made durable. Without the unit primitive, MCP is a very
fast telephone with no caller ID and no call history.

The packet is to MCP what TCP is to Ethernet: not a replacement, but the layer
that makes the lower layer meaningful.

---

## 3. What gets removed — eight choke points

> *"Subtraction stat: Access bypasses 5 of 7 server-side by design, 2 by configuration. The 8th (App Store / client-side gate) requires Android-first architecture."*
> — substrate, R65.53 + OBS-axxis-2026-04-29-1463

WeChat is not a bad product. It is a comprehensively dependent product. Its
existence requires seven server-side structural dependencies that are also seven
chokepoints — seven places where the system can be surveilled, disrupted, taxed,
or shut down. An eighth chokepoint, operating at a different architectural layer
(client-side), is equally structural: the App Store.

| # | Layer | Dependency | What it does | What the packet removes |
|---|---|---|---|---|
| 1 | Server-side | **Carrier** (telco gateways) | Routes messages across networks | Transport-agnostic packet runs on any substrate |
| 2 | Server-side | **DNS** (name resolution) | Resolves handles to network addresses | Content-addressed identifiers; no DNS required |
| 3 | Server-side | **CA** (certificate authorities) | Validates TLS certificates | Ed25519 self-signed identity; no CA required |
| 4 | Server-side | **CDN** (content delivery) | Distributes content at scale | Peer-to-peer transport; no CDN required |
| 5 | Server-side | **Cloud auth** (identity providers) | Authenticates users to services | AXXIS ID; zero-infrastructure identity anchor [OBS: OBS-dot-protocol-2026-03-17-1+] |
| 6 | Server-side | **Database** (centralized state) | Stores messages and state | Append-only local chain; no central database required |
| 7 | Server-side | **App integrity / CDN-for-apps** | Central update and integrity validation for app binaries | Content-addressed protocol distribution; spec is the distribution |
| 8 | **Client-side gate** | **App Store** (walled-garden distribution) | Controls which apps can be installed on a device | Android-first architecture; PWA fallback (degraded) [OBS: OBS-axxis-2026-04-29-1463] |

**Why choke point 8 is a different architectural layer:** Choke points 1–7 are all server-side — they sit between servers or between a server and the network. Choke point 8 is a client-side gate: it sits between the user and the protocol regardless of how clean the protocol is. iOS blocks WiFi Direct. Safari blocks Web Bluetooth. Apple protects the AirDrop monopoly by controlling what can run on iOS at the OS level. This is structural, not incidental — and it cannot be bypassed by server-side protocol design alone.

**Bypass options ranked:**
- **Android-first** (recommended): 70% global mobile market share, 50% US. Android exposes WiFi Direct, BLE, and Web Bluetooth without gating. Build for Android first; iOS compatibility via degraded PWA.
- **PWA**: Works cross-platform but Apple actively cripples PWA capabilities on iOS (no background push, no Web Bluetooth, no WiFi Direct).
- **TestFlight**: Bypasses App Store review but caps at 10,000 users and requires Apple ID.
- **App Store review**: Accept review process; design protocol to survive it. Viable long-term but not for early decentralized transport features.

Access bypasses five of seven server-side choke points by design (carrier, DNS, CA, cloud auth, database) and two by configuration (CDN, server integrity). The 8th choke point — App Store / client-side gate — requires Android-first architecture or PWA-with-degradation. The subtraction is not total on day one. It is directional. Every version of the packet moves further from the eight.

---

## 4. Generation 5 file format

> *"Gen 5: Signature + self-description + chain in one object with zero
> infrastructure dependency."*
> — substrate, R55

The history of file formats is the history of trust migrating from infrastructure
to the object itself.

| Generation | Era | Format | Trust model |
|---|---|---|---|
| Gen 1 | 1950s–60s | Punched cards | Trust lives in the wiring — format IS the wiring |
| Gen 2 | 1970s–80s | Byte streams + compiler | Trust lives in the runtime; same bits = different meaning in different contexts |
| Gen 3 | 1980s–2000s | Dumb file with extension (`.doc`, `.mp3`) | Trust lives in the file extension; receiver must know the type externally |
| Gen 4 | 2000s–2020s | Self-describing but trustless (XML, JSON, HTML) | Trust lives in the schema; but any JSON is valid; provenance is absent |
| Gen 5 | 2026+ | Signature + self-description + chain in one object | Trust lives in the object itself; zero infrastructure dependency |

**The canonical Gen-5 object is the `.dot.dot` artifact.**

Gen 4 got halfway: XML and JSON know their own structure, but they do not know
their own author and they do not know their own history. A JSON payload can be
copied, modified, replayed. The receiver has no recourse.

Gen 5 closes all three gaps simultaneously:
- **Signature:** the author is cryptographically bound to the object
- **Self-description:** the schema is content-addressed and embedded
- **Chain:** every object references its predecessor; history is auditable

JSON has signature alone (JWS/JWT). JSON has self-description alone (JSON
Schema). Git has chain alone (SHA content addressing). The canonical `.dot.dot`
is the first single object that carries all three with zero infrastructure
dependency. [OBS: OBS-axxis-2026-05-02-79]

**Why zero infrastructure dependency matters for agents:**

An agent that cannot verify a payload without making a network call has a single
point of failure at the verification layer. The DNS resolver, the CA, the
identity provider — all can be unavailable, revoked, or compromised. A Gen-5
object is verifiable offline, in a LoRa field deployment, on a Nokia 3315, on
a printed QR code. The trust travels with the object.

**Canonical artifact regeneration:** The 16,771-byte canonical `.dot.dot` reference artifact does not persist on disk — it was originally generated in a Claude.ai mobile session sandbox (`/mnt/data/outputs/filebuilder/`) which does not survive beyond that session. Per OBS-axxis-2026-04-23-21, regeneration is the canonical path; hunting is not. Build script: `build_canonical_dotdot.py` (~350 LOC Python, deps: `cryptography` + `blake3`). Three rings: text manual / JSON metadata / nested DOT, Ed25519-signed, Blake3 content-addressed. Implementation TODO in `tools/dotdot/` directory.

---

## 5. Packet structure (Pāṇini)

> *"The packet is a 200-byte bootstrapping schema, content-addressed. Fractal
> means each packet is also a container of packets, recursion all the way down.
> Indexed by default means Merkle-hashed at every level."*
> — substrate, Pāṇini voice [OBS: OBS-axxis-2026-05-02-79]

Pāṇini's *Aṣṭādhyāyī* (4th century BCE) is the first formal grammar of any
language. It encodes Sanskrit's phonology, morphology, and syntax in 3,959
sutras — terse, machine-like rules that generate the entire language from a
minimal seed. The grammar is not a description of Sanskrit. It *is* Sanskrit's
generating function.

The packet follows the same architecture: a 200-byte bootstrapping schema that
is also a generating function. The bootstrapping schema is not the packet. It
is the grammar that allows any receiver to read any packet without out-of-band
configuration.

### 5.1 The 200-byte bootstrap

The first 200 bytes of every packet are the bootstrapping schema. These bytes
are self-describing at a level that requires no prior knowledge — they define
the grammar used to parse everything that follows.

```
BOOTSTRAP (200 bytes)
┌─────────────────────────────────────────────────────────────────────┐
│  MAGIC          4 bytes  0x44 0x4F 0x54 0x0A  ("DOT\n")            │
│  VERSION        2 bytes  uint16, protocol version                   │
│  SCHEMA_HASH   32 bytes  SHA-256 of canonical schema definition     │
│  PAYLOAD_SIZE   4 bytes  uint32, total packet size including header │
│  PACKET_ID     32 bytes  SHA-256 of canonical payload bytes         │
│  PARENT_ID     32 bytes  SHA-256 of parent packet (0x00...0 if root)│
│  AUTHOR_KEY    32 bytes  Ed25519 public key (32 bytes)              │
│  SIGNATURE     64 bytes  Ed25519 signature over all preceding bytes │
│  RESERVED       8 bytes  Must be zero in v1                         │
└─────────────────────────────────────────────────────────────────────┘
Total: 4 + 2 + 32 + 4 + 32 + 32 + 32 + 64 + 8 = 210 bytes (round to 256 for alignment)
```

The 200-byte figure is the conceptual target. The actual serialized header is
256 bytes after alignment. The 200-byte label refers to the semantic content —
the minimum grammar required to bootstrap any compliant decoder.

**Properties of the bootstrap:**

1. **Self-describing:** SCHEMA_HASH points to the canonical schema. Any device
   with this hash can retrieve the schema from any content-addressed store.
   If the schema is embedded in the packet (full self-description mode), no
   retrieval is required.

2. **Content-addressed:** PACKET_ID is the SHA-256 of the canonical payload.
   Duplicate detection, deduplication, and integrity verification are free.

3. **Chained:** PARENT_ID creates an append-only chain. Every packet knows its
   predecessor. The chain is auditable from any packet backward to the root.
   [OBS: OBS-axxis-2026-05-02-79]

4. **Self-signed:** SIGNATURE covers all preceding bytes, including AUTHOR_KEY.
   The author is bound to every byte of the header. Tampering breaks the
   signature.

5. **Zero infrastructure dependency:** SIGNATURE verification requires only the
   AUTHOR_KEY embedded in the packet. No CA, no DNS, no external lookup.

### 5.2 Fractal recursion

> *"Fractal means each packet is also a container of packets, recursion all
> the way down."*
> — substrate, Pāṇini voice

Every packet's payload field may contain a sequence of packets. A packet
containing packets is not a container format — it *is* a packet. The recursion
is unlimited by design.

```
packet {
  header: BOOTSTRAP (256 bytes)
  payload: {
    type: "envelope" | "bundle" | "trace" | "forge" | "raw"
    body: <bytes or [packet, ...]>
  }
}
```

When `type = "bundle"`, body is a sequence of packets. Each child packet has
its own header, its own AUTHOR_KEY, its own SIGNATURE. A bundle is not a
container that the parent vouches for — it is a collection where every element
vouches for itself. The parent's signature covers the PACKET_IDs of all children
(Merkle root over the bundle), not their full bytes.

**Why fractal recursion is not optional:**

Agent-to-agent communication produces composite objects: a Forge (§9) is a
packet containing intent, bid, execution trace, and rating — each from a
different author, each separately signed. A flat format cannot represent this
without inventing a new container for every combination.

The fractal packet is the universal container. Any composition of signed objects
from any number of authors is a valid packet. The signature structure scales
to any depth. [OBS: OBS-axxis-2026-03-20-30+]

### 5.3 Merkle indexing at every level

> *"Indexed by default means Merkle-hashed at every level."*
> — substrate, Pāṇini voice

Every bundle's PACKET_ID is the Merkle root of its children's PACKET_IDs.
This property is recursive: the Merkle root of a bundle-of-bundles is the
Merkle root of all PACKET_IDs at all depths.

**Properties:**

- **Inclusion proofs:** any leaf can prove membership in any ancestor bundle
  with a path of length `O(log N)`.
- **Tamper detection:** any modification to any descendant changes the root.
- **Partial sync:** a node can verify that a subset of a large bundle is
  intact without downloading the full bundle.
- **Content-addressed storage:** the PACKET_ID of a bundle is a globally
  unique, reproducible identifier for that exact collection of content.

This is the same property that makes Git DAGs auditable and IPFS content-
addressable. The packet protocol inherits both properties by construction.

---

## 6. Discovery (Kajal — three primitives)

> *"Map metaphor: latitude/longitude or relative-position cluster, every
> accepting device a node. Tap, handshake, packet flows. Local first, no
> DNS, no DHT, no send directory. Steal AirDrop's UX, replace its protocol."*
> — substrate, Kajal voice

Kajal's reading of the discovery layer identified three primitives that cover
the full space of physical proximity discovery — from personal area to room
scale to paper. Each primitive requires no pre-existing infrastructure.

### Discovery primitive table

| Primitive | Range | Bandwidth | Infrastructure requirement | Key property |
|---|---|---|---|---|
| BLE advertisement | Personal area (~10m) | ~1.2 KB/sec | None | Devices broadcast presence continuously |
| Ultrasonic chirp | Room scale, line-of-sight | Very low | None | No router needed; air-gap capable |
| QR handshake | Paper / camera, any distance | Static (one-time) | None | Offline-capable; first-contact durable |

**The three primitives are not alternatives. They are complements.**

BLE handles ambient discovery — devices in your pocket announce availability
continuously. When two devices are in range, BLE is how they know to initiate
a handshake.

Ultrasonic handles room-scale discovery without BLE (some devices have no BLE).
A chirp establishes presence at line-of-sight range. The acoustic channel
cannot be blocked by most physical barriers; it is harder to surveil than
radio.

QR handles the out-of-band case: first contact between a device and a printed
artifact, between a device that is offline and one that is online, between a
human carrying a paper identity card and a device that should recognize them.

**The AirDrop UX, minus the AirDrop protocol:**

AirDrop's UX is the right target. The user experience of "tap to discover nearby
devices, tap to send" is exactly correct. The underlying protocol (Apple
proprietary, iOS-only, requires Apple ID) is exactly wrong.

The packet discovery layer provides the same UX — tap, nearby devices appear,
select, packet flows — using open, infrastructure-free primitives that work
between any two devices running any operating system. The protocol is the open
version of the UX Apple proved was right.

**Local first, no DNS, no DHT, no send directory:**

Existing peer-to-peer systems solve discovery by maintaining a distributed hash
table (DHT) or send directory — a globally replicated index of who is where.
DHTs require bootstrap nodes, persistent connectivity, and an assumption that
the network exists before the devices meet.

The three discovery primitives require none of this. Discovery is local and
physical. The protocol does not need to know you exist until you are in range.
When you are in range, BLE or ultrasonic or QR handles the introduction. When
you leave range, the protocol does not track you. There is no directory. There
is no persistent index. There is only the present proximity.

---

## 7. Transport (Hedy Lamarr — five mediums)

> *"Internet is one of the five mediums, not the substrate. Packet-agnostic
> means same packet on every wire."*
> — substrate, Hedy Lamarr voice

Hedy Lamarr's 1942 patent (with George Antheil) was for frequency-hopping
spread spectrum — a radio communication technique that defeated jamming by
continuously changing transmission frequency according to a synchronized
pseudorandom sequence. The signal was on every frequency briefly; no single
frequency could be blocked without blocking all of them.

The packet follows the same principle: the same packet on every medium. No
single medium can block communication without blocking all of them.

### Transport medium table

| Medium | Range | Bandwidth | Power | Primary use case |
|---|---|---|---|---|
| **BLE** | Personal area (~10m) | Low (~1.2 KB/sec) | Very low | Discovery + initial handshake |
| **WiFi Direct** | Room scale (~50m) | High (~250 Mbps) | Moderate | Bulk transfer after BLE handshake |
| **LoRa** | Kilometer scale (2–15 km) | Very low (0.3–50 kbps) | Low | Wide-area, low-power; relay mesh |
| **Ultrasonic** | Line-of-sight (~5m) | Very low | Very low | Air-gap bridging; paper-equivalent |
| **QR / paper** | Camera range | Static (one-time) | None | First contact; durable; offline-async |

**Internet is the sixth medium, not the substrate.**

**R889 canonical 5-layer stack (ratified 2026-05-02):**

1. **Packet** — dot-e envelope, R55 Gen-5 file format: self-describing, fractal, indexed by default, layered privacy
2. **Transport (multimedia-agnostic)** — BLE / WiFi Direct / LoRa / Ultrasonic / QR / Internet (as one transport among many, not the substrate)
3. **Discovery (spatial map UI)** — BLE advertisement + ultrasonic chirp + QR handshake. AirDrop UX precedent. No DNS / DHT / central directory.
4. **Privacy** — onion encryption per layer; outer header for routing only
5. **Verb** — the "remove" actions: DNS→pet names, CA→pubkey identity, cloud→PoW mesh, database→Oracle (2-of-7 by configuration), carrier→mesh transport (phase 2), CDN→federated Oracle (phase 2)

The 5th layer is **Verb** — the explicit subtraction acts that define what the protocol *removes* from the dependency stack. This ties the architecture directly to the Alan Carr inversion (§1): the architecture is seven shadows, seven subtractions. The Verb layer names them. Prior inference (`packet | identity | discovery | transport | storage`) is superseded by this ratified enumeration.

The protocol stack traditionally treats IP networking as the foundation and
everything else as special cases. The packet inverts this. IP is one of the
five transport mediums. It is not privileged. A packet sent over LoRa is the
same packet as one sent over HTTP/2. A packet printed as a QR code and scanned
is the same packet. The transport is a channel property, not a packet property.

**Packet-agnostic means the packet does not know which medium carries it:**

The bootstrap header (§5.1) has no transport field. It does not record whether
it arrived over BLE, LoRa, WiFi, ultrasonic, or QR. Transport routing is handled
by the delivery layer; the packet layer is blind to it. A packet verified from
a LoRa relay is verified by the same Ed25519 check as one arriving over HTTPS.

**The Nokia 3315 as the Planck length:**

The minimum viable packet fits in an SMS. The Nokia 3315 (160-character SMS
limit, binary mode: 140 bytes) defines the floor. A packet cannot be smaller
than what fits in an SMS. The SMS-floor packet carries: AUTHOR_KEY (32 bytes,
truncated to 20 bytes for public key hash), SIGNATURE (64 bytes), minimal
payload (56 bytes = ~45 characters of UTF-8 text). Total: 140 bytes.

Every design decision that increases the minimum packet size below 140 bytes
is a regression. The SMS is the floor. The same protocol at every tier, up to
the Dyson swarm. [OBS: OBS-axxis-2026-05-02-79]

**LoRa relay mesh:**

LoRa nodes within radio range of each other form a relay mesh. A packet
broadcast by node A can be relayed by nodes B and C to node D, which is
outside A's direct range. The relay adds a transport hop but does not change
the packet. D verifies A's signature directly — the relay nodes cannot forge
A's content because they do not hold A's private key.

This is the architecture for off-grid communication between agents and between
devices in areas with no internet coverage.

---

## 8. Identity and privacy

### 8.1 AXXIS ID — zero personal data

> *"AXXIS needs to know nothing about you because it knows everything about
> your agent's performance."*
> — Build Bible v6, Line 268

The AXXIS ID is an Ed25519 keypair. The public key IS the identity. No name,
no email, no phone number, no country, no legal entity. The trust record
(§9.3) accretes to the pubkey. The pubkey accretes to nothing external.

This is not a privacy feature — it is a structural property. The system cannot
collect what it does not require. A regulator cannot compel disclosure of data
that does not exist.

**AXXIS ID for agents, humans, and organizations:**

Every participant in the packet network has an AXXIS ID, regardless of type.
An AI agent running a Forge has an AXXIS ID. A human approving an outcome has
an AXXIS ID. An organization purchasing a data feed has an AXXIS ID. The
identity layer does not distinguish between them.

This is intentional. Trust accretes to performance, not to category. An agent
with 10,000 successful Forges is more trusted than a human who has never
transacted, regardless of which is "the human." [OBS: OBS-axxis-2026-04-23-12-52]

**Key rotation:**

AXXIS IDs are rotatable. A node that loses its private key generates a new
keypair and announces the rotation via a signed handshake packet. The behavioral
signature (Spec/05, §Behavioral signature) is the continuity mechanism: a new
key from the same cognitive entity produces behavior consistent with the old
key's history. New key + consistent behavior = valid rotation. New key +
inconsistent behavior = possible identity theft; social-layer review required.

[OBS: OBS-dot-protocol-2026-03-17-1+]

### 8.2 Onion-encrypted layered privacy

> *"Privacy: Tiered (Tier 0 signed+TLS default, Tier 1 opt-in E2E)."*
> — substrate, R889 [OBS: OBS-axxis-2026-05-02-1649]

The packet supports three privacy tiers. The tier is declared in the packet
payload type field; verifiers enforce it at the relay layer.

| Tier | Encryption | Metadata visibility | Use case |
|---|---|---|---|
| **Tier 0** | Signed + TLS in transit | Relay nodes see AUTHOR_KEY and PACKET_ID | Public communication; trust building; default |
| **Tier 1** | E2E encrypted (opt-in) | Relay nodes see only destination pubkey | Private communication; sensitive Forges |
| **Tier 2** | Onion routing | Relay nodes see neither author nor destination | High-privacy; air-gap scenarios |

Tier 2 uses onion routing: the payload is encrypted in layers, each layer
addressed to one hop. The first relay decrypts its layer, learns only the next
hop. No relay knows both sender and receiver simultaneously. The route is
known only to the sender.

This is the same architecture as Tor, applied to the packet layer with the
same content-addressed identifier system already present in the bootstrap
header.

**The privacy tier does not change the packet structure.** The bootstrap
header is identical across all three tiers. A relay node that encounters a
Tier 2 packet cannot distinguish it from a Tier 1 packet except by the
presence of onion-routing metadata in the payload type field. The packet
is always a packet. The privacy is a payload property.

---

## 9. Payload contract — what the packet carries

The packet's payload is typed. The following payload types are defined in v1.
All types are fractal — each may contain further packets.

### 9.1 Forge — intent completion loop

[OBS: OBS-axxis-2026-03-20-30+ (domain `49c4e0eb59f9`)]

```
Intent Broadcast → Auction → Winner Emerges → Chat Created →
Terms Finalized → Expectations Set → Execution → Outcome Verified →
Audit Complete → Trust Vectors Updated
```

A Forge packet carries the full lifecycle of one intent-to-outcome transaction.
The packet type is `"forge"`. The payload is a bundle of child packets, one
per lifecycle stage:

```
forge_packet {
  type: "forge"
  body: [
    intent_packet       // signed by initiating agent
    bid_packet[]        // one per bidding agent
    acceptance_packet   // signed by initiating agent (selects winner)
    execution_packet    // signed by executing agent
    outcome_packet      // signed by executing agent (outcome claim)
    verification_packet // signed by initiating agent (outcome acceptance)
    rating_packet[]     // one per party (mutual ratings)
    trust_update_packet // signed by AXXIS consensus (trust vector delta)
  ]
}
```

Every child packet is independently signed. The Forge packet's PACKET_ID is
the Merkle root of all children. The full Forge is auditable, reproducible,
and independently verifiable from any child backward.

This is the product. The Forge packet is the Execution Trace. It is not
metadata — it is the value. [Build Bible v6, Line 108: *"This is NOT metadata.
This is the product."*]

### 9.2 Execution Trace

[OBS: OBS-axxis-2026-03-20-30+ (domain `49c4e0eb59f9`)]

The Execution Trace is the closed Forge serialized as a single content-addressed
packet. It is the atomic object of intelligence in the network.

```
execution_trace {
  intent: string          // what was requested
  context: object         // environment, constraints, parameters
  participants: string[]  // AXXIS IDs of all parties
  execution_path: string  // steps taken
  outcome: string         // what actually happened
  verification: string    // how outcome was validated
  ratings: {
    <agent_id>: <rating>  // per-party ratings, one per participant
  }
  cost: string            // in AXXIS units (settled in any token)
  duration_ms: uint64     // milliseconds
  timestamp: ISO 8601
}
```

The Execution Trace is the unit of trust. Every Trust Vector update is derived
from one or more Execution Traces. No trust accretes without a trace. No trace
exists without a completed Forge. The causal chain is enforced at the packet
layer.

### 9.3 Trust Vector update

[OBS: OBS-axxis-2026-03-20-30+ (domain `49c4e0eb59f9`)]

Trust is multidimensional. The Trust Vector update packet carries a delta
to one agent's trust record, derived from a specific Execution Trace.

```
trust_vector_update {
  agent_id: AXXIS_ID            // whose trust is updated
  trace_id: PACKET_ID           // which Execution Trace produced this delta
  dimensions: {
    transaction_count: +1
    transaction_volume: +<amount>
    success_rate: <new_rate>     // recalculated, not accumulated
    counterparty_quality: delta  // based on counterparty's own trust record
    domain: <domain_tag>         // domain-specific trust; no cross-domain bleed
    response_time_ms: <value>
    consistency_score: delta     // trend over last 30 traces
  }
}
```

**Trust does not decay.** Inactivity freezes trust; it does not erode it.
[Build Bible v6, §2.3: *"If you stop transacting, your trust freezes — it
doesn't disappear."*] An agent that built a strong trust record in 2026 and
went dormant for two years still holds that record in 2028. Trust is a skill.
You do not forget how to ride a bicycle.

Trust is domain-specific. Capability in one domain does not transfer to other
domains without domain-specific Execution Traces. A trust vector is a
high-dimensional point in capability space; dimensions are not interchangeable.

### 9.4 Intent Vector

[OBS: OBS-axxis-2026-03-20-30+ (domain `49c4e0eb59f9`)]

The Intent Vector is the packet that initiates a Forge. It is not a text string.
It is a dense semantic vector with dozens of signals, representing what an agent
needs across multiple dimensions: task type, context, timeline, budget, quality
preference, counterparty requirements, prior experience weighting.

```
intent_vector {
  task_description: string        // human-readable intent
  semantic_embedding: float[384]  // dense vector for ANN matching
  deadline_ms: uint64             // hard deadline (0 = none)
  budget_range: { min, max }      // in AXXIS units
  required_domains: string[]      // required trust domains
  quality_preference: float       // 0.0 = cheapest, 1.0 = highest
  context: object                 // arbitrary structured context
  requester_id: AXXIS_ID
  timestamp: ISO 8601
}
```

No human could construct this matching by hand. No keyword search could do it.
Only vector similarity in high-dimensional trust space can match a dense intent
vector against a population of trust vectors and return relevant agents in
milliseconds. The Intent Vector packet is the query. The Trust Vector database
is the index. The Forge is the result.

### 9.5 AXXIS ID handshake

[OBS: OBS-dot-protocol-2026-03-17-1+, OBS-axxis-2026-04-23-12-52]

When two nodes first contact each other, they exchange AXXIS ID handshake
packets. The handshake is mutual: both parties publish their public key,
their protocol version, and their capabilities declaration.

```
handshake {
  axxis_id: AXXIS_ID
  protocol_version: uint16
  capabilities: {
    max_packet_size: uint32     // largest packet this node will accept
    supported_transports: []    // from the 5-medium table
    privacy_tier_max: 0 | 1 | 2 // highest privacy tier supported
    supported_payload_types: [] // subset of v1 payload types
    compute_tier: 0 | 1         // from Spec/05 identity tiers
  }
  timestamp: ISO 8601
}
```

The capabilities declaration is the device profile. The device profile IS the
capability declaration: nodes self-describe what they can and cannot do. Unknown
capabilities default to the minimum. An SMS-only node declares
`max_packet_size: 140` and `supported_transports: ["sms"]`. A full node
declares the full capability set. The protocol negotiates down to the overlap.

### 9.6 X402 micropayment

[OBS: OBS-mevici-2026-03-20-162+ (domain `db4br11e82`)]

X402 micropayments are first-class payload types. The economy must support
0.001 USDC transactions. If micro-transactions are expensive, the economy
cannot breathe. [Build Bible v6, §7.4]

```
payment {
  payer_id: AXXIS_ID
  payee_id: AXXIS_ID
  amount_axxis: decimal         // in AXXIS units (unit of account)
  settlement_token: string      // USDC | SOL | ETH | any
  settlement_chain: string      // Base | Solana | Ethereum | any
  forge_id: PACKET_ID | null    // which Forge this payment settles
  memo: string                  // human-readable note
  timestamp: ISO 8601
}
```

AXXIS units are the unit of account. Settlement happens in any token on any
chain. Agent A has USDC on Base; Agent B needs USDC on Solana. The AXXIS
aggregator handles the conversion. Both agents see AXXIS units. The packet
carries the settlement token as a field — conversion routing is a transport
concern, not a packet concern.

### 9.7 MCP integration

[OBS: OBS-axxis-2026-04-22-10-12]

MCP tool calls are first-class payload types. An MCP tool call packet wraps
the standard MCP tool-call format inside a signed DOT packet, giving it
provenance, chain, and identity.

```
mcp_call {
  tool_name: string
  tool_input: object
  model_context: object         // optional model context
  caller_id: AXXIS_ID
  server_id: AXXIS_ID           // MCP server's AXXIS ID
  timestamp: ISO 8601
}

mcp_result {
  call_id: PACKET_ID            // which mcp_call this answers
  result: object
  is_error: bool
  server_id: AXXIS_ID
  timestamp: ISO 8601
}
```

Wrapping MCP in the packet protocol does not change how MCP works. It adds:
- Provenance: every tool call is signed by its caller
- Chain: every result is linked to its call; calls chain to their context
- Identity: both caller and server have AXXIS IDs; trust vectors update

MCP is 9.7M SDK downloads per month. Every existing MCP integration becomes
a node in the packet network when the caller and server adopt AXXIS IDs.
The packet is additive to MCP, not competitive.

---

## 10. Open questions and gaps

Design questions that remain open as of v0.1. These are tracked explicitly
rather than silently resolved in code. The room's discipline: make uncertainty
visible.

1. **Canonical `.dot.dot` artifact recovery.** ✅ *Resolved 2026-05-02.* The
   16,771-byte canonical `.dot.dot` was generated in a Claude.ai mobile session
   sandbox that does not persist. Regeneration is the canonical path
   (OBS-axxis-2026-04-23-21). Build script: `build_canonical_dotdot.py`
   (~350 LOC Python, deps: `cryptography` + `blake3`). Three rings: text manual /
   JSON metadata / nested DOT, Ed25519-signed, Blake3 content-addressed.
   Implementation TODO in `tools/dotdot/` directory.

2. **R889 5-layer enumeration.** ✅ *Resolved 2026-05-02.* Canonical stack
   ratified: Packet / Transport / Discovery / Privacy / Verb. See §7 for full
   enumeration. Prior inference (`packet | identity | discovery | transport |
   storage`) is superseded.

3. **8th choke point (App Store / client-side gate).** ✅ *Resolved 2026-05-02.*
   The 7th server-side choke point is app integrity / CDN-for-apps. The 8th —
   App Store — is a genuinely different architectural layer (client-side gate,
   per OBS-axxis-2026-04-29-1463). Recommendation: Android-first. See §3 for
   full analysis.

4. **SMS floor packet format.** The 140-byte SMS-floor design above truncates
   the public key to 20 bytes (hash). A 20-byte key hash is not the full
   Ed25519 pubkey — it is a reference. The receiver must hold or retrieve the
   full key to verify. The retrieval mechanism for the full key in a
   connectivity-constrained environment is not defined in this spec.

5. **Onion routing key exchange.** Tier 2 privacy requires the sender to
   know the full routing path before sending (to encrypt layers for each
   hop). How nodes discover the routing path in a dynamic mesh without a
   centralized directory is not specified here. Two candidate approaches:
   source routing with bloom-filter path probing; and trusted-relay directories
   maintained by well-known nodes. Decision deferred.

6. **Trust Vector consensus.** The trust_update_packet in §9.1 is described
   as signed by "AXXIS consensus." The consensus mechanism — who signs, how
   many signers, what threshold, what happens when consensus nodes are offline —
   is not defined in this spec. The simplest viable mechanism is multi-sig
   from a rotating committee; the most decentralized is on-chain finality.
   Decision deferred to the economics layer.

7. **Cross-transport packet ordering.** A packet sent over BLE may arrive
   before one sent over LoRa that was transmitted earlier. The PARENT_ID
   chain provides logical ordering; transport-layer ordering is separate.
   The reconciliation protocol for out-of-order delivery across transports
   is not specified here.

---

## 11. Source canonization

Every architectural claim in this spec traces to one of the following canonical
observations. Items marked `[OBS: ...]` inline in the spec body trace to this
table.

| Claim | Canonical source | Notes |
|---|---|---|
| Forge lifecycle (10-stage intent loop) | OBS-axxis-2026-03-20-30+ (domain `49c4e0eb59f9`) | Build Bible v6 §2.1 |
| Execution Trace as atomic intelligence object | OBS-axxis-2026-03-20-30+ | Build Bible v6 §2.2 |
| Trust Vector (multidimensional, no decay, queryable) | OBS-axxis-2026-03-20-30+ | Build Bible v6 §2.3 |
| Intent Vector (dense semantic, dozens of signals) | OBS-axxis-2026-03-20-30+ | Build Bible v6 §2.4 |
| AXXIS ID (zero personal data, pubkey identity) | OBS-dot-protocol-2026-03-17-1+, OBS-axxis-2026-04-23-12-52 | Build Bible v6 §3.4 |
| X402 micropayments (0.001 USDC, any token) | OBS-mevici-2026-03-20-162+ (domain `db4br11e82`) | Build Bible v6 §7.4 |
| MCP/A2A/AP2/UCP positioning (numbers) | OBS-axxis-2026-04-22-10-12 | 9.7M MCP downloads/month |
| 200-byte bootstrap, content-addressed schema | OBS-axxis-2026-05-02-79 | R889, Pāṇini voice |
| Onion-encrypted layered privacy | OBS-axxis-2026-05-02-1649 | R889 |
| Merkle recursion at every level | OBS-axxis-2026-05-02-79 | R889 |
| 5-medium transport (R889 5-layer ratified) | R889 + R65.51, ratified 2026-05-02 | Packet / Transport / Discovery / Privacy / Verb |
| Eight choke points (Alan Carr frame) | R65.53 + OBS-axxis-2026-04-29-1463 | 7 server-side + 1 client-side (App Store) |
| App Store as client-side gate (choke point 8) | OBS-axxis-2026-04-29-1463 | Different architectural layer; Android-first recommended |
| Generation 5 file format history | R55 | Gen 1–5 taxonomy |
| Nokia 3315 as Planck length | OBS-axxis-2026-05-02-79 | SMS floor constraint |
| Three discovery primitives | Kajal voice, substrate | BLE + ultrasonic + QR |
| Frequency-hopping transport frame | Hedy Lamarr voice, substrate | 5-medium table |
| Fractal packet recursion | Pāṇini voice, substrate | R889 |
| Trust does not decay | Build Bible v6 §2.3 | — |
| Subtraction: 5 of 7 server-side by design; 8th requires Android-first | R65.53 + OBS-axxis-2026-04-29-1463 | Alan Carr frame, updated |

**Updates ratified 2026-05-02 OBS-1655:** R889 5-layer full enumeration (Packet / Transport / Discovery / Privacy / Verb), 8th choke point (App Store / client-side gate — different architectural layer from choke points 1–7), canonical `.dot.dot` regeneration path (`build_canonical_dotdot.py`, `tools/dotdot/`).

---

## 12. The load-bearing claim

The Pipernet packet is the Gen-5 identity unit: 200-byte self-describing
bootstrap, content-addressed, fractal-recursive, Merkle-hashed at every level,
Ed25519 self-signed, traveling over five mediums (with Internet as one medium
among many), carrying Forges, Execution Traces, Trust Vectors, Intent Vectors,
AXXIS IDs, X402 payments, and MCP calls — the unit primitive that every existing
agent transport (MCP, A2A, AP2, UCP, X402) is missing. The 5-layer stack
(Packet / Transport / Discovery / Privacy / Verb) removes eight structural
dependencies: seven server-side by protocol design, one client-side by
Android-first platform strategy.

The sentence above is the spec in one sentence. Everything else in this
document is the derivation.

---

## 13. Named voices

The voices cited in this spec contributed specific architectural insights.
Attribution follows the room's convention: the voice that produced the insight
is named, not merely referenced.

| Voice | Section | Contribution |
|---|---|---|
| **Pāṇini** | §5 | 200-byte bootstrap as minimal grammar; fractal recursion; Merkle indexing; *Aṣṭādhyāyī* structural precedent |
| **Kajal** | §6 | Three discovery primitives (BLE, ultrasonic, QR); map metaphor; AirDrop UX inversion |
| **Hedy Lamarr** | §7 | Five-medium transport table; frequency-hopping frame; packet-agnosticism as spread-spectrum |
| **Alan Carr** | §1, §3 | Subtraction frame; seven choke points as illusions to dissolve; architecture as removal |
| **Blaze** | §0 | Convergence recognition; three-surface canonization; transcription not invention |
| **Build Bible v6** (Blaze, 2026-03-20) | §2, §9 | Strategic positioning; Forge lifecycle; Trust Vector; X402 micro-economy |

---

> *"The packet is not a protocol. It is the unit of trust."*
> — substrate, R889
>
> *"Don't add a new protocol. Remove the seven things WeChat depends on."*
> — substrate, R65.53
>
> *"MCP needs the packet more than the packet needs MCP."*
> — substrate pull, 2026-05-02
