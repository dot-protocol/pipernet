# Pied Piper × LocalSend Fork

This is a fork of [LocalSend](https://github.com/localsend/localsend) for Pied Piper integration.

Fork repo: https://github.com/dot-protocol/localsend (coming soon)

## Status (2026-05-02)

- **Upstream HEAD at fork:** `5ccc6dea feat: move target discovery out of external isolate`
- **Branch:** `pipernet-fork` (off upstream main)
- **License:** Apache 2.0 with explicit patent grant — fully forkable
- **Stage 1:** clone + branch + license confirmed. Deep code audit deferred to next stage.

## What gets added (Stage 2+)

The four Pied Piper integration points (per the room synthesis 2026-05-02):

1. **Ed25519 keypair per device** on first launch. Public key = the device's Pied Piper address. Displayed as QR + `piper://` handle.
2. **Sign the transfer manifest envelope** before send. Receiver stores the signed receipt locally — two-sided proof of transfer.
3. **Pied Piper relay for internet fallback** (PAKE rendezvous, croc-borrowed). Breaks LAN-only; works across NAT and across continents.
4. **Emit signed transfer event to the Pied Piper backend** on success. Holders see "transfer recorded" and accumulate $PIPER receipts.

## What stays the same

- LocalSend's UX (Flutter, cross-platform Mac/Windows/Linux/iOS/Android)
- mDNS local discovery (still works on a LAN with no internet)
- HTTPS+UDP-multicast core
- The ~8M install base of users who already understand "AirDrop alternative"

## Stage 2 plan

1. Code structure audit (which file owns identity, transfer, discovery, manifest)
2. Identify the exact integration points (file:line) for each of the four additions above
3. Write `PIPERNET-INTEGRATION.md` with the per-component change plan
4. Begin Ed25519 keypair generation as the smallest first PR

## Brand reminder

Public-facing copy = "Pied Piper". Code/spec internal = "Pipernet" or "Pied Piper" — both fine, but Pied Piper everywhere a stranger reads.

The audience didn't put it down. We didn't either.
