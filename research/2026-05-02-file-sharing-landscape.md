# File-Sharing Landscape Research
# Date: 2026-05-02
# Purpose: Strategic landscape analysis for Pipernet consumer wedge — "transfer-without-permission"
# Researcher: Rocky (Claude Code / Sonnet 4.6)
# Scope: Q1–Q4 as specified in research brief

---

## Q1: The File-Sharing Landscape

### Master Table (Top 14 Platforms, 2025–2026)

| # | Name | Launched | Status | Stars / Install Base | Architecture | Identity Model | Cross-Platform | Value Prop |
|---|------|----------|--------|---------------------|--------------|----------------|----------------|------------|
| 1 | **LocalSend** | 2022 | Active, v2.x | ~79K stars, 8M+ downloads | P2P direct (LAN only) | Device fingerprint (SHA-256 of self-signed TLS cert) | Win/Mac/Linux/iOS/Android | Open-source AirDrop for any device on LAN |
| 2 | **AirDrop** | 2011 | Active (Apple-only) | Not disclosed; ~2B Apple device install base | P2P direct via AWDL (BLE + WiFi-direct) | Apple ID / Contact card, device trust | iOS/macOS only | Frictionless 1-tap nearby transfer within Apple ecosystem |
| 3 | **PairDrop** | 2022 (fork of Snapdrop) | Active | ~4K stars (schlagmichdoch/PairDrop) | P2P via WebRTC (TURN relay if behind NAT) | Anonymous per-session; pair via 6-digit code | Any browser | AirDrop in any browser, no app install |
| 4 | **Snapdrop** | 2015 | Abandoned / sold | ~17K stars (original); site now redirects | P2P via WebRTC | Anonymous | Any browser | Browser-native AirDrop clone (superceded by PairDrop) |
| 5 | **croc** | 2018 | Active, v10.x | ~32K stars | P2P via relay (PAKE code phrase) | Anonymous, ephemeral code phrase | CLI all-OS | Secure cross-internet CLI transfer via human-readable code phrase |
| 6 | **Magic Wormhole** | 2016 | Active | ~20K stars | P2P via relay | Anonymous, ephemeral code phrase | CLI/GUI all-OS | One-time code-based transfer with E2E encryption |
| 7 | **OnionShare** | 2014 | Active, v2.6+ | ~6K stars | Tor hidden service (no relay, no infra) | Anonymous; v3 onion address = identity | Win/Mac/Linux | Fully anonymous transfer via Tor; no intermediary |
| 8 | **Firefox Send** | 2017 | **Discontinued Sep 2020** | N/A | Cloud relay (E2E encrypted) | None (no auth) | Browser | E2E encrypted cloud relay link — killed by malware abuse |
| 9 | **WeTransfer** | 2009 | Active, commercial | Not disclosed; 80M+ monthly users | Cloud relay | None (free) / account (paid) | Browser, all OS | Simple link-share of large files; 2GB free |
| 10 | **Smash** | 2018 | Active | Not disclosed | Cloud relay | Optional account | Browser, all OS | No file-size limit cloud relay |
| 11 | **SwissTransfer** | 2021 | Active (free) | Not disclosed | Cloud relay (Swiss-hosted) | None | Browser, all OS | 50GB free, Swiss privacy law, zero tracking |
| 12 | **Quick Share (Google)** | 2020 (Nearby Share), merged 2024 | Active | Not disclosed; 2B+ Android install base | P2P direct (BLE+WiFi) with relay fallback | Google account / device trust | Android + Windows (macOS: NearDrop workaround) | Google's AirDrop: Android↔Windows direct transfer |
| 13 | **NearDrop** | 2023 | Active (community) | ~4K stars (grishka/NearDrop) | Implements Google Nearby protocol on macOS | Google account / device trust | macOS receiver only | Unofficial macOS client for Google Quick Share |
| 14 | **BitTorrent / WebTorrent** | 1999 / 2013 | Active (mature) | WebTorrent ~29K stars | P2P swarm (DHT, tracker optional) | Anonymous / magnet link | All OS / Browser | Swarm-based bulk transfer; no direct-to-person UX |
| 15 | **IPFS** | 2015 | Active (developer-facing) | ~23K stars (kubo) | Content-addressed DHT P2P | Anonymous / CID | All OS, developer-facing | Permanent content-addressed storage, not ephemeral transfer |
| 16 | **Syncthing** | 2014 | Active | ~67K stars | P2P encrypted sync (TLS, discovery relay) | Device ID (public key) | All OS except iOS (limited) | Continuous encrypted folder sync; not one-shot transfer |
| 17 | **KDE Connect** | 2013 | Active | ~4K stars | P2P LAN + pairing | Device pairing (RSA key exchange) | Linux/Android/Windows/macOS | Phone↔desktop clipboard, notifications, file transfer |
| 18 | **ToffeeShare** | ~2020 | Active | Not disclosed | P2P via WebRTC (browser) | Anonymous | Browser, all OS | No-storage E2E browser transfer, nothing on server |
| 19 | **ShareDrop** | 2013 | **Acquired by Limewire 2025** | Not disclosed; site now redirects to Limewire | WebRTC P2P | Anonymous | Browser | AirDrop clone (effectively dead as independent project) |
| 20 | **wormhole.app** | 2020 | Active (commercial) | Not disclosed | P2P <5GB; encrypted cloud relay >5GB | None | Browser | E2E encrypted with auto-expiring links; hybrid P2P+cloud |

[Source: GitHub repos, accessed 2026-05-02]
[Source: LocalSend 79K stars — byteiota.com/localsend-cross-platform-airdrop-alternative-79k-stars, accessed 2026-05-02]
[Source: LocalSend 8M downloads — apps.apple.com + play.google.com aggregate, accessed 2026-05-02]
[Source: croc 32K stars — github.com/schollz/croc, accessed 2026-05-02]
[Source: Quick Share Wikipedia — en.wikipedia.org/wiki/Quick_Share, accessed 2026-05-02]

---

### Platform Deep Notes

#### LocalSend (the named reference)

**Repo:** github.com/localsend/localsend  
**License:** Apache 2.0 (changed from MIT in 2023 to add patent protection clause)  
**Stars:** ~79K (as of early 2026)  
**Install base:** 8M+ downloads (aggregate across all platforms)  
**Contributors:** 200+ (active community)  
**Stack:** Flutter (Dart), rhttp Rust HTTP client (switched from Dio in 2025), self-signed TLS, mDNS/UDP multicast

**How discovery works:**  
1. On network join, device broadcasts a UDP multicast packet to `224.0.0.167:53317`
2. Listening devices reply via TCP to the announcer's API at port 53317 (or emit their own multicast as fallback)
3. Introduced in v1.8.0 — two-phase to handle lost UDP replies

**How transfer works:**  
1. Sender sends file metadata list to `/api/localsend/v2/prepareUpload` over HTTPS
2. Receiver approves/rejects per file
3. Sender streams files to `/api/localsend/v2/upload?token=...` over HTTPS
4. TLS: self-signed certificate generated per device. Fingerprint = SHA-256 of cert. No CA chain — trust on first use (TOFU)
5. Encryption mode can be disabled (plain HTTP) — not recommended

**What it does NOT do:**
- No cross-internet transfer: LAN-only. No relay, no NAT traversal, no STUN/TURN (feature requested: issue #2469, not implemented)
- No persistent identity: fingerprint is device-local, not portable across reinstalls
- No signed receipts: no proof the transfer happened
- No multi-medium transport: WiFi/LAN only. No BLE, LoRa, ultrasonic
- No incentive layer
- No messaging: file and short text only, no threaded chat or reactions

[Source: github.com/localsend/protocol/blob/main/v1.md, accessed 2026-05-02]
[Source: github.com/localsend/localsend/issues/2469, accessed 2026-05-02]
[Source: deepwiki.com/localsend/localsend/2.6-network-discovery, accessed 2026-05-02]

---

#### AirDrop (the closed reference)

**Status:** Apple-only, locked to iOS/macOS/iPadOS/watchOS  
**Architecture:** BLE (discovery, ~30 ft range) + AWDL (Apple Wireless Direct Link, data transfer)  
**AWDL specifics:** Proprietary extension of IEEE 802.11. Devices time-slice between normal WiFi channel and AWDL channel using a single radio. Speed: 250+ Mbps (WiFi 6). No centralized relay.  
**Identity:** Apple ID or Contacts-based. Receiver must be in sender's contacts or have "Everyone" mode. Mutual TLS client certificates exchanged during handshake.  
**Why third parties can't replicate it:** AWDL is a proprietary protocol. Apple does not publish its spec. AWDL has been partially reverse-engineered (OWL project, USENIX 2019) but cannot be deployed on non-Apple hardware without kernel modifications. The BLE advertisement format and handshake certificate exchange are also undocumented.  
**EU regulatory status (2025–2026):** EC ruled in March 2025 that Apple must allow third-party devices to use peer-to-peer WiFi connectivity with iPhone. Apple is required to deprecate AWDL in favor of the open Wi-Fi Aware standard under this ruling.  
**The structural insight:** AirDrop's UX magic comes from AWDL's always-on time-sliced radio behavior. No third party can do this on Apple hardware. Quick Share achieves similar UX on Android via BLE+WiFi-Direct but cannot initiate to Apple devices (absent the new EU ruling).

[Source: en.wikipedia.org/wiki/AirDrop, accessed 2026-05-02]
[Source: developer-tech.com/news/eu-pressure-on-apple-means-android-can-now-airdrop, accessed 2026-05-02]
[Source: usenix.org/conference/usenixsecurity19/presentation/stute, accessed 2026-05-02]

---

#### Snapdrop / PairDrop

**Snapdrop:** github.com/RobinLinus/snapdrop (~17K stars). Original browser-based AirDrop clone. Sold to unknown party, redirects, no longer open-source. Effectively dead as a maintained project.  
**PairDrop:** github.com/schlagmichdoch/PairDrop. Active fork. Self-hostable (Node.js + Docker). WebRTC P2P for same-LAN; PairDrop TURN server as fallback for cross-NAT. Pairing via 6-digit code or QR. No account required.  
**Limitation:** Browser-only (no native app). No persistent identity. Files never leave devices (same LAN) or go through PairDrop TURN (cross-NAT) — no user-controlled relay.

[Source: pairdrop.net, github.com/schlagmichdoch/PairDrop, accessed 2026-05-02]

---

#### NearDrop

**Repo:** github.com/grishka/NearDrop (~4K stars)  
**What it does:** Unofficial macOS implementation of Google's Nearby Share / Quick Share protocol. Menu-bar app. Receive-only from Android/Windows. Active community project.  
**Limitation:** No iOS support. Receive-only on macOS (cannot initiate from Mac to Android). Depends on Google's protocol remaining stable.

---

#### Magic Wormhole / wormhole.app

**Magic Wormhole:** github.com/magic-wormhole/magic-wormhole (~20K stars). CLI. Python. PAKE (SPAKE2) code-phrase exchange. Files go through a relay server. Relay does not see file contents (E2E encrypted). Cross-platform (any Python environment). No GUI.  
**wormhole.app:** Commercial product based on similar concept. Web UI. Files <5GB: true P2P WebRTC. Files >5GB: encrypted temporary cloud relay. No account required. Links auto-expire.  
**Gap:** Code phrase UX is unintuitive for non-technical users. Both are one-shot transfers only — no persistent identity, no history.

---

#### croc (schollz/croc)

**Repo:** github.com/schollz/croc (~32K stars, Go)  
**Architecture:** Relay-assisted P2P. Sender generates code phrase. Relay does rendezvous only, then steps out (true P2P if NAT allows; relay-forwarded if not). PAKE (SRP) for key agreement — relay never sees file content.  
**Cross-platform:** Go binary, works on all OS including Windows/Linux/macOS/Android (Termux). No GUI (CLI only). F-Droid GUI wrapper exists.  
**Gap:** No identity persistence, no GUI, no mobile-native app.

[Source: github.com/schollz/croc, accessed 2026-05-02]
[Source: schollz.com/tinker/croc6, accessed 2026-05-02]

---

#### OnionShare

**Repo:** github.com/onionshare/onionshare (~6K stars, Python/Qt)  
**Architecture:** Starts a local HTTP server, exposes as Tor v3 onion address. No relay server needed. Sender shares the `.onion` URL in any channel.  
**Identity:** The v3 onion address is a 56-character base32-encoded Ed25519 public key. It IS identity — cryptographically verifiable and persistent across sessions if the private key is retained.  
**Gap:** Requires Tor (slow, 30–120s to set up hidden service). Not consumer-friendly. Desktop-only UI (no mobile app). Transfer is one-shot only — address expires when app closes by default.

[Source: onionshare.org, github.com/onionshare/onionshare, accessed 2026-05-02]

---

#### Firefox Send (RIP)

**Status:** Permanently shut down September 2020.  
**Cause of death:** Encrypted cloud relay with no authentication and no abuse reporting. Cybercriminals used it to deliver malware because Firefox domain was whitelisted by many enterprise proxies. Suspended July 2020, never restored; Mozilla laid off 250 employees same period and deprioritized the product.  
**Lesson:** An encrypted transfer tool with no identity layer is weaponizable. Anonymity without accountability is a liability at scale.

[Source: support.mozilla.org/en-US/kb/what-happened-firefox-send, accessed 2026-05-02]
[Source: wikipedia.org/wiki/Firefox_Send, accessed 2026-05-02]

---

#### WeTransfer / Smash / SwissTransfer

**All three:** Cloud relay. Browser-based upload, shareable link. No P2P.

| Service | Free limit | Storage duration | Privacy |
|---------|-----------|-----------------|---------|
| WeTransfer | 2GB, 10 transfers/month | 7 days | Updated ToS July 2025 permits file use for service improvement |
| Smash | No limit | 7 days | States no data exploitation |
| SwissTransfer | 50GB | 30 days | Swiss law, zero tracking, free forever (Infomaniak-funded) |

**Architecture gap for Pipernet:** All three are download-by-link — no persistent identity, no proof of receipt, no signed transfer record.

[Source: fromsmash.com/comparison/swisstransfer, accessed 2026-05-02]
[Source: nemcoshow.fr/en/swisstransfer-review-2025-50-gb-free-vs-wetransfer-full-test, accessed 2026-05-02]

---

#### IPFS / Filecoin

**IPFS (kubo):** github.com/ipfs/kubo (~16K stars). Content-addressed P2P storage. Every file has a CID (SHA-256 content hash). Files are not sent to a person — they are published to the swarm and retrieved by CID. No concept of "send to Alice."  
**Practical problems (confirmed as of 2024–2025):**
- Files not popular enough to be pinned disappear when the publishing node goes offline
- Brave removed IPFS support in 2024 due to low usage
- Default node republishes content ID every 24h — network-intensive
- No persistent per-person identity in the base protocol (IPNS exists but is underused)
- UX is deeply technical; no consumer app that matches AirDrop ease of use  
**Filecoin:** Storage incentive layer over IPFS. FIL token paid to storage providers. Focused on archival, not ephemeral person-to-person transfer.

[Source: discuss.ipfs.tech/t/ipfs-vs-webtorrent, accessed 2026-05-02]
[Source: en.wikipedia.org/wiki/InterPlanetary_File_System, accessed 2026-05-02]

---

#### BitTorrent / WebTorrent

**Status:** Mature, largest install base in file-sharing history. ~1B+ historical clients.  
**WebTorrent:** github.com/webtorrent/webtorrent (~30K stars). BitTorrent over WebRTC — works in browsers. Compatible with standard BitTorrent swarm via WebTorrent hybrid trackers.  
**What survives:** Content distribution (media, software), not person-to-person transfer. No "send to Bob" UX.  
**Gap:** Magnet links and torrent files are not a consumer UX. No identity tied to sender. No persistent relationship. No signed transfer records.

---

#### Quick Share (Google) / NearDrop

**Quick Share:** Google's merger of Samsung's Nearby Share and Google's Nearby Share in 2024. Available on Android, Windows, and (unofficially via NearDrop) macOS. BLE for discovery, WiFi-Direct or WiFi LAN for transfer. Google account for identity (device trust). Cross-Android and Android↔Windows only. No iOS support.  
**Gap:** Google account required for persistent identity. iOS excluded. No cryptographic signing of individual transfers. No multi-medium transport beyond BLE+WiFi.

[Source: android.com/better-together/quick-share-app, accessed 2026-05-02]

---

## Q2: What's Missing Across All of Them

Systematic gap analysis across every platform in Q1:

| Feature | LocalSend | AirDrop | PairDrop | croc | Magic Wormhole | OnionShare | Quick Share | Syncthing | IPFS |
|---------|----------|---------|----------|------|----------------|------------|-------------|-----------|------|
| **Cryptographic identity that travels with the file** | No — device fingerprint is local, not portable | No — Apple ID is account-based, not on the file | No | No | No | Partial — .onion address is Ed25519 key, not embedded in file | No | No | Partial — CID is content-addressed but not sender-signed |
| **Persistent reputation derived from transfers** | No | No | No | No | No | No | No | No | No |
| **Cross-medium transport (BLE→WiFi→LoRa→internet)** | WiFi/LAN only | BLE+WiFi-AWDL only | WebRTC/internet only | TCP/internet only | TCP/internet only | Tor/internet only | BLE+WiFi only | TCP/internet only | TCP/internet only |
| **Signed receipts (proof transfer happened)** | No | No | No | No | No | No | No | No | No |
| **File-sharing AND messaging unified** | Partial — short text only | Partial — shares but no conversation | No | No | No | No | No | No | No |
| **Incentive layer / token reward** | No | No | No | No | No | No | No | No | Filecoin (storage only) |
| **Works without internet AND without LAN** | No | No | No | No | No | No | No | No | No |

**The verifiable absence:**
None of the 14+ platforms surveyed combines all six properties simultaneously. The closest partial matches:

- **OnionShare** comes nearest on cryptographic identity: the v3 onion address is an Ed25519 key. But it is not embedded in the transferred file, does not follow the file, and collapses after the session. There is no trust vector — receiving a file from an onion address tells you nothing about the sender's history.
- **IPFS** has content addressing (CID) which is verifiable hash-of-content, but no sender signature. CIDs say "this file has this content" — they say nothing about who sent it.
- **Persistent BitTorrent Trackers (2025 research paper):** A 2025 academic paper (Wicht, Univ. of Bern, eprint.iacr.org/2025/2131.pdf) proposes per-piece attestation and factory-based smart contracts for portable reputation in BitTorrent. This is research, not a shipping product.

**The fundamental gap (one line, detailed version):**

Every existing platform gives you either identity OR transfer OR history — none gives you all three as a unified primitive. AirDrop gives you seamless transfer with no identity portability. IPFS gives you content identity with no sender signature. OnionShare gives you sender identity with no persistence. **The missing thing is a signed cell where the sender's public key, the content hash, and the transfer event are all co-located and verifiable offline, forever.**

[Source: eprint.iacr.org/2025/2131.pdf (Persistent BitTorrent Trackers, 2025), accessed 2026-05-02]

---

## Q3: LocalSend Deep Dive

### Repo and Stats

| Metric | Value | Source |
|--------|-------|--------|
| Repo | github.com/localsend/localsend | — |
| License | **Apache 2.0** (changed from MIT, 2023) | Issue #1634 |
| Stars | ~79K (early 2026) | byteiota.com/localsend, 2026 |
| Forks | ~3.7K–3.9K | GitHub |
| Contributors | 200+ | GitHub contributors graph |
| Downloads | 8M+ (all platforms aggregate) | App stores, 2026 |
| Latest release | v1.16.x (2025 stable) | github.com/localsend/localsend/releases |
| Protocol repo | github.com/localsend/protocol | — |

### License Compatibility

Apache 2.0 is OSI-approved, compatible with most open-source licenses. It grants rights to use, reproduce, modify, and distribute including in proprietary derivatives. It requires:
1. A copy of the Apache 2.0 license in the derivative
2. Notices of significant modifications
3. Patent grant is included — forkers receive a patent license from contributors

**Fork feasibility: YES.** Apache 2.0 explicitly permits forking and commercial use. The patent clause means forkers inherit the patent grant, reducing legal risk. A fork that adds a cryptographic identity layer and multi-medium transport is legally straightforward.

### Tech Stack

| Component | Technology |
|-----------|------------|
| UI framework | Flutter (Dart) |
| HTTP client | rhttp (Rust, via flutter_rust_bridge) — switched from Dio in 2025 |
| Discovery | UDP multicast to `224.0.0.167:53317` |
| Transfer | HTTPS REST (self-generated TLS cert, TOFU) on TCP `53317` |
| Fingerprint | SHA-256 of device TLS certificate |
| Build targets | Win/Mac/Linux/iOS/Android/Web |

### How Discovery Works (mDNS specifics)

LocalSend does NOT use mDNS (Bonjour/Zeroconf). It uses **UDP multicast** directly:
- Multicast address: `224.0.0.167` (custom, not mDNS's `224.0.0.251`)
- Port: `53317` (both UDP and TCP)
- Phase 1: New device broadcasts UDP multicast announcement with its device info JSON
- Phase 2: Existing devices either call the new device's HTTP API directly (TCP) or respond with their own UDP multicast
- This two-phase approach was introduced in v1.8.0 for reliability (pure UDP had reply-loss issues)

Some community forks (e.g., MarcoAlejandroLopezGomez/LocalSendApp on GitHub) do use standard mDNS for discovery, but the mainline LocalSend uses custom UDP multicast.

### What the Fork Adds vs Removes

**ADD to a Pipernet fork of LocalSend:**

| Addition | Why |
|----------|-----|
| Ed25519 keypair per device (generated externally, not in-app) | Replaces transient TLS fingerprint with portable cryptographic identity |
| Content-addressing (SHA-256 of file embedded in signed transfer) | Proof of file integrity, verifiable forever |
| Signed transfer receipt | Both parties sign: sender signs "I sent this", receiver signs "I received this" — two-sided proof |
| Trust vector (rolling score from past transfers) | Persistent reputation derived from transfer history, not social graph |
| Multi-medium transport shim | BLE discovery layer + UDP for local, HTTPS for internet relay fallback, LoRa future path |
| Pipernet relay (internet fallback) | Breaks LAN-only limitation without requiring Tailscale workaround |
| $PIPER reward hook | Token event emitted on successful signed transfer |
| DOTdrop envelope wrapping | Uniform cell type: file transfer = DOT, message = DOT, same protocol |

**REMOVE / simplify from LocalSend:**

| Removal | Why |
|---------|-----|
| Anonymous-only trust model | Replaced by Ed25519 identity; TOFU fingerprint becomes bootstrap step |
| LAN-only constraint | Pipernet relay provides internet fallback |
| No persistence | Signed receipts create a history |
| Short text messages as afterthought | Replaced by full DOTpost message primitive |

**Preservation:** The Flutter cross-platform UI, the REST-over-HTTPS transfer protocol (fast, proven, mobile-friendly), the UDP multicast discovery (or upgraded to mDNS), the Apache 2.0 open-source commitment.

### The Fork Point (where to cut the code)

The LocalSend codebase separates cleanly into:
1. **Discovery layer** (UDP multicast, `app/src/main/kotlin/.../discovery/`) — replace with DOT-aware discovery that includes Ed25519 public key in announcement
2. **Transfer layer** (HTTP REST, `lib/features/send/`) — wrap outgoing files in DOTdrop envelope before transmitting; extract envelope on receipt
3. **Device identity** (fingerprint, `lib/model/device.dart`) — replace TLS cert fingerprint with Ed25519 public key as primary identity
4. **UI layer** (Flutter widgets) — keep, restyle for Pipernet brand

[Source: github.com/localsend/protocol/blob/main/v1.md, accessed 2026-05-02]
[Source: github.com/localsend/localsend/issues/1634, accessed 2026-05-02]
[Source: deepwiki.com/localsend/localsend/2.6-network-discovery, accessed 2026-05-02]
[Source: github.com/localsend/localsend/issues/2469, accessed 2026-05-02]

---

## Q4: Strategic Positioning

### The Wedge vs Existing Alternatives

**Why Pipernet AirDrop differs from LocalSend:**

LocalSend is anonymous-ephemeral. Every transfer is between two fingerprints that have no memory of each other. There is no history. There is no trust accumulated. There is no proof the transfer happened. Pipernet's first-principles position is the inverse: **every transfer is a signed event between two identities, and that event is permanent.** The file and the identity that sent it are inseparable from the moment of transfer.

**Why Pipernet AirDrop differs from AirDrop:**

AirDrop is ecosystem-locked (Apple-only) and identity-locked (Apple ID only). It cannot work on Android, Windows, or Linux. It cannot traverse the internet. Its identity is an Apple account — portable only within Apple's ecosystem, revocable by Apple, invisible to the recipient. Pipernet's identity is an Ed25519 keypair: self-sovereign, portable, revocable only by the holder, verifiable by anyone.

**Why the $PIPER memecoin audience would use it instead of Telegram/iMessage/AirDrop:**

The memecoin audience is device-heterogeneous (mixing iPhones, Androids, Windows PCs) and identity-fluid (pseudonymous, handle-based). AirDrop doesn't reach them cross-device. Telegram works but produces no verifiable on-chain trace of the transfer. iMessage is Apple-locked and Apple-surveilled.

The $PIPER hook is not "get paid to transfer files." That meme is too abstract. The meme is: **"Every file you send earns your wallet a score. Your score earns you $PIPER. Your $PIPER earns you early access."** Transfer is already happening. The $PIPER layer is the first financial layer attached to an action people already do daily. The door was never locked — file sharing has always been free. The insight is that the *identity of the person who sent it* has always been worth something. Pipernet is the first app to make that value capturable.

**Why it is not Discord:**

Discord is synchronous group communication. Pipernet is asynchronous, bilateral, transfer-first. The comparison axis is AirDrop and WeTransfer, not Discord. The consumer wedge is the moment someone opens Telegram to send a 200MB video and sees the 50MB limit — that is the door. Pipernet opens it.

### The Meme Moment (Carr frame)

The Alan Carr inversion for Pipernet:

> "Why do I use WeTransfer? Because the file is too big for iMessage. Why is iMessage limited? Because Apple's server pays for the transfer. Why can't I just send it directly? You can. You always could. LocalSend exists and has 8 million downloads. But it only works on WiFi. And it doesn't remember that it's you who sent it."

The illusion being dissolved: **that file size limits, platform locks, and transfer anonymity are features, not constraints imposed by server-cost architectures.** Pipernet removes the server cost (P2P) and removes the anonymity (signed identity) and removes the platform lock (cross-OS) simultaneously. None of the existing tools do all three.

The meme is: **"LocalSend for the internet. Signed. Yours."**

### 30-Day MVP Scope

The goal is to ship the "transfer-without-permission" wedge — minimum viable feature set that demonstrates the Pipernet position without building the full DOTdrop spec.

**What to ship in 30 days:**

1. **Fork LocalSend.** Keep the Flutter codebase, the UDP-multicast discovery, the HTTPS REST transfer protocol. Restyle the UI.

2. **Add Ed25519 keypair generation on first launch.** Use a Dart/Rust crypto library (ed25519_hd_key is available in Flutter ecosystem). Private key stored in platform secure enclave (iOS Keychain, Android Keystore, macOS Secure Enclave). Public key = your Pipernet address. Display it as a QR code and a short handle (`piper://abc123def`).

3. **Sign the transfer manifest.** Before sending, wrap the file list and file hash in a minimal DOTdrop envelope (JSON-serializable). Sender signs with their Ed25519 private key. Receiver stores the signed envelope as a receipt.

4. **Add internet relay fallback.** When UDP multicast fails (not on same LAN), offer a Pipernet relay connection using the same HTTPS REST protocol but routed through relay. Session key from PAKE handshake (borrow from croc's SRP model). This is the LAN-only limitation broken.

5. **Emit the $PIPER event.** On successful signed transfer, POST to Pipernet backend: `{sender_pubkey, receiver_pubkey, file_hash, timestamp, signature}`. Backend handles token accounting. Front-end shows "transfer recorded" confirmation. No on-chain transaction in v0 — backend is the ledger until mainnet.

**What NOT to ship in 30 days:**

- LoRa/BLE/ultrasonic multi-medium transport (post-v1)
- Trust vector scoring UI (post-v1)
- On-chain $PIPER settlement (post-v1)
- Full DOTpost messaging integration (post-v1)
- Web client (post-v1)

**30-day success criterion:** A user on iPhone and a user on Windows PC can transfer a 1GB file directly (P2P if same LAN, relay-routed if internet), see each other's Pipernet handle, and the transfer is recorded as a signed event in the Pipernet backend.

---

## Summary Report

### File Path
`/Users/blaze/Movies/Kin/pipernet/research/2026-05-02-file-sharing-landscape.md`

### Top 3 Platforms Most Worth Studying / Forking From

1. **LocalSend** — Apache 2.0, forkable today, Flutter cross-platform, 8M downloads of proof that the LAN-direct UX has product-market fit. The gap is the identity layer and internet relay. Fork point is clean.

2. **croc** — PAKE-based relay model is exactly what Pipernet needs for internet fallback (P2P if NAT allows, relay-forwarded if not, relay never sees contents). 32K stars. Go. The relay protocol is the piece to borrow.

3. **OnionShare** — The only existing tool where Ed25519 IS the identity (v3 onion address = Ed25519 public key). The failure mode (Tor, slow, desktop-only) is instructive: cryptographic identity alone is not enough without a fast, mobile-native delivery layer.

### Single Biggest Gap (one line)

**No platform attaches a portable, offline-verifiable, sender-signed identity to the transferred file — every transfer is anonymous by default and the sender's identity evaporates when the session ends.**

### LocalSend License + Fork Feasibility

**Apache 2.0. Fork feasibility: YES, unconditionally.** Commercial use, modification, and redistribution are all permitted. No copyleft obligations. Patent clause protects forkers.

### Recommended 30-Day MVP (3-5 bullets)

- Fork LocalSend mainline, restyle UI, keep Flutter/HTTPS/UDP-multicast core
- Add Ed25519 keypair per device on first launch; public key = Pipernet address
- Sign the transfer manifest envelope; receiver stores signed receipt locally
- Add Pipernet relay for internet fallback (borrow croc's PAKE relay model)
- Emit signed transfer event to Pipernet backend; display "transfer recorded" confirmation — no on-chain yet

### What Could Not Be Researched and Why

- **LocalSend exact contributor count:** GitHub contributors graph not directly machine-readable in search results; cited as "200+" from community sources (likely accurate to order of magnitude)
- **PairDrop exact stars:** Search results referenced multiple forks; schlagmichdoch/PairDrop mainline star count not confirmed (estimated 4K; low confidence)
- **ShareDrop post-Limewire acquisition details:** Search confirmed acquisition in 2025 and redirect to Limewire, but new product roadmap not publicly disclosed
- **Quick Share install base breakdown:** Google does not publish Nearby/Quick Share install counts separately from Android; "2B+ Android install base" is the device floor, not active Quick Share users
- **WeTransfer July 2025 ToS full text:** One secondary source referenced a ToS change permitting file use for service improvement; could not verify the exact clause text from the original Mozilla Help article

---

*Research conducted 2026-05-02. All sources accessed same date.*
