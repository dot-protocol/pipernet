# Use case: distribution without a gatekeeper

One of the eight choke points in the R65.53 analysis is the App Store:

> *Choke point 8: Distributing the client requires platform approval.
> An app that threatens established communication revenue can be removed
> or rejected. The dependency on approval by a single company is
> structural — it applies regardless of the app's technical merit.*

Pipernet is a protocol, not an app. Protocols cannot be removed from an App
Store. This document explains what that means in practice and how the relay
architecture makes distribution approval irrelevant.

---

## The problem with app-gated communication

When a communication tool is distributed as a native app:

1. A platform company reviews and approves the app before users can install it
2. The same company can remove the app at any time, for any reason, with
   minimal notice or recourse
3. The company can add requirements (in-app purchase cuts, content policy
   compliance, real-name registration) as a condition of continued distribution
4. Users who already have the app may find it stops working when updates
   are blocked

This happened to Telegram in some markets. It happened to Parler. It
happened to apps that briefly enabled third-party Twitter clients. It
is not a hypothetical.

The dependency is architectural: if the only way to use the protocol is
via an app that requires store approval, then store approval is part of
the protocol's attack surface.

---

## How Pipernet sidesteps this

Pipernet's reference relay is a Python package. Python packages are
distributed via `pip`, which is not gated by any platform review. The
CLI works in any terminal. A web client can be served from any HTTPS
domain. The protocol itself — the envelope format, the signing, the
channel model — is a spec that anyone can implement in any language.

The specific paths that require no gatekeeper:

**Command line:**
```bash
pip install pipernet
pipernet serve --port 8000
```
`pip` is available on every major OS. No approval required.

**Web client:**
A browser-based Pipernet client is HTML + JavaScript served over HTTPS.
Any web host can serve it. The user navigates to a URL. No app install.
No review. No approval. If the host removes it, any other host can serve
the same client pointed at the same relay.

**Self-hosted relay:**
The relay is a Python process. Anyone who can run a Python process can
run a relay. A VPS, a home server, a Raspberry Pi, a friend's machine.
The data lives on the relay operator's infrastructure.

**Protocol portability:**
Because the protocol is an open spec (`spec/`), any developer can implement
a Pipernet client in Swift, Kotlin, Rust, or Go and distribute it through
any channel — direct download, F-Droid, AltStore, sideload, TestFlight,
or any future distribution mechanism that doesn't exist yet. The protocol
does not require any single client to remain available.

---

## The LocalSend fork plan

The closest parallel in the existing ecosystem is LocalSend — an
open-source cross-platform file sharing app (React Native, MIT license,
available on every major platform) that works over LAN without any server.
LocalSend has already navigated the App Store approval process for iOS,
Android, macOS, Windows, and Linux.

The plan in `clients/LOCALSEND-FORK-NOTES.md` is to fork LocalSend as
a Pipernet-native client: replace the LocalSend protocol with Pipernet
envelopes, add Ed25519 signing, and keep the existing distribution pipeline.

This approach is deliberate: we don't need to re-fight the App Store
approval battle LocalSend already won. We inherit their distribution
footprint and add the protocol layer.

The key change is that the fork would use Pipernet's signed envelope format
for file transfers — so the same client that moves files also carries signed
messages, and the same relay that hosts channels also relays file transfers.
One protocol. One client. Multiple distribution paths.

---

## What this means for resilience

A communication protocol that can only be accessed via a single approved
app is as centralised as a hosted service. It may be technically federated
but socially captive.

Pipernet aims for a different property: **no single entity should be able
to make the protocol unusable for a community that wants to use it**.

That means:
- The spec is open (anyone can implement a client)
- The relay is open (anyone can run a node)
- The CLI is a pip install (no approval required)
- The web client is static HTML (any host can serve it)
- The identity is a keypair (no account to revoke)

The App Store is still a useful distribution channel for reaching
non-technical users. A native app with a good UX is a legitimate goal.
But it is not the only path, and the protocol does not depend on it.

The eighth choke point is neutralised not by fighting the gatekeeper but
by making the gatekeeper irrelevant.
