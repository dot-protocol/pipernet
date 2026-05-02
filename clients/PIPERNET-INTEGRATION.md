# Pipernet Integration Plan — LocalSend Fork

**Status:** Stage 2 (site wired) — Stage 2D (Flutter builds) blocked on Flutter install  
**Branch:** `pipernet-fork`  
**Upstream commit at fork:** `5ccc6dea`  
**Upstream license:** Apache 2.0 with explicit patent grant — fully forkable  
**Last updated:** 2026-05-03

---

## Scope: Stage 2 (Mac DMG + Android APK)

This document is the exact execution checklist for the agent who runs stage 2D onward. Read top to bottom, do not skip steps.

---

## Prerequisites

```bash
# 1. Install Flutter (if not present — 2GB download, get Blaze's approval first)
brew install --cask flutter

# 2. Verify build readiness
flutter doctor
# Required for macOS: Xcode installed, command line tools, CocoaPods
# Required for Android: Android SDK, Java 17+
# If flutter doctor shows errors, fix them before proceeding

# 3. Get into the fork directory
cd pipernet/clients/localsend   # relative to repo root
git checkout pipernet-fork
```

---

## Step 1: pubspec.yaml

File: `app/pubspec.yaml`

Change:
```yaml
name: localsend_app
description: An open source cross-platform alternative to AirDrop
homepage: https://localsend.org/
version: 1.17.0+58
```

To:
```yaml
name: pied_piper
description: Drop files across devices, across networks. No accounts.
homepage: https://piedpiper.fun/
version: 0.1.0+1
```

---

## Step 2: macOS bundle identity

File: `app/macos/Runner/Configs/AppInfo.xcconfig`

Change:
```
PRODUCT_NAME = LocalSend
PRODUCT_BUNDLE_IDENTIFIER = org.localsend.localsendApp
PRODUCT_COPYRIGHT = Copyright © 2022 org.localsend. All rights reserved.
```

To:
```
PRODUCT_NAME = Pied Piper
PRODUCT_BUNDLE_IDENTIFIER = fun.piedpiper.dotdrop
PRODUCT_COPYRIGHT = Copyright © 2026 dot-protocol. All rights reserved.
```

---

## Step 3: Android bundle identity

File: `app/android/app/build.gradle`

Change:
```gradle
namespace "org.localsend.localsend_app"
```

To:
```gradle
namespace "fun.piedpiper.dotdrop"
```

Also change `applicationId` in the `defaultConfig` block if it's separate:
```gradle
applicationId "fun.piedpiper.dotdrop"
```

File: `app/android/app/src/main/AndroidManifest.xml`

Find the `android:label` attribute on `<application>` and change:
```xml
android:label="LocalSend"
```
to:
```xml
android:label="Pied Piper"
```

---

## Step 4: App name strings (localization)

File: `app/lib/gen/strings_en.g.dart`

Find the `appName` getter (should be around line 1-20 of the file):
```dart
String get appName => 'LocalSend';
```
Change to:
```dart
String get appName => 'Pied Piper';
```

There are a few other user-facing "LocalSend" strings in this file. Replace them carefully:
- `appDirectory`: `'(LocalSend folder)'` → `'(Pied Piper folder)'`
- `About LocalSend` → `About Pied Piper`
- In `encryptionHint`: `LocalSend uses a self-signed certificate` → `Pied Piper uses a self-signed certificate`
- In network interfaces description: `LocalSend uses all available network interfaces` → `Pied Piper uses all available network interfaces`

DO NOT rename references like "LocalSend Protocol" in technical/spec contexts — only rename user-facing labels.

---

## Step 5: App icon (placeholder)

For stage 2, use a solid-color placeholder icon that matches the site aesthetic.

The Pied Piper favicon is in the piedpiper-fun repo at `favicon.svg`.

To generate icons from the SVG:
```bash
# macOS: requires imagemagick
brew install imagemagick

# Convert SVG to required PNG sizes (run from piedpiper-fun repo root)
convert -background none favicon.svg \
  -resize 1024x1024 /tmp/pp-icon-1024.png

# Then use flutter_launcher_icons or manually replace:
# macOS: app/macos/Runner/Assets.xcassets/AppIcon.appiconset/
# Android: app/android/app/src/main/res/mipmap-*/ic_launcher.png
```

If imagemagick is not available or icon replacement is complex, skip for stage 2 and note it in the release body.

---

## Step 6: Theme colors

File: `app/lib/config/theme.dart` (or wherever LocalSend defines its color scheme)

Inspect the file first. LocalSend uses Material 3. The accent/seed color is likely a blue or teal. For Pied Piper, use a near-black seed that produces a neutral palette on light mode and a dark-neutral on dark mode — matching piedpiper.fun's aesthetic of `#0b0b0b` dark / `#f5f5f5` light.

```dart
// Replace the seedColor with a neutral near-black
// colorScheme: ColorScheme.fromSeed(seedColor: Color(0xFF0A0A0A), ...)
```

This is a best-effort change for stage 2. The key thing is the name is right. Theme can be iterated.

---

## Step 7: NOTICE.md (mandatory — upstream attribution)

Create `NOTICE.md` at the repo root:

```markdown
# Pied Piper / dotdrop — Upstream Attribution

This application is a fork of [LocalSend](https://github.com/localsend/localsend),
created by Tien Do Nam and contributors.

LocalSend is licensed under the Apache License, Version 2.0.
The original license is preserved in `LICENSE`.

Fork point: commit `5ccc6dea` (feat: move target discovery out of external isolate)

Changes made in this fork are documented in `PIPERNET-INTEGRATION.md`.
```

---

## Step 8: Build macOS

```bash
cd clients/localsend/app   # relative to pipernet repo root

# Install Flutter deps
flutter pub get

# Build macOS release
flutter build macos --release

# Output: build/macos/Build/Products/Release/Pied Piper.app
```

Package as DMG:
```bash
# Install create-dmg if not present
brew install create-dmg

# Create DMG
create-dmg \
  --volname "Pied Piper" \
  --window-pos 200 120 \
  --window-size 600 400 \
  --icon-size 100 \
  --app-drop-link 440 150 \
  "PiedPiper-0.1.0-mac.dmg" \
  "build/macos/Build/Products/Release/Pied Piper.app"
```

Smoke test before publishing: open the .app, confirm it shows "Pied Piper", confirm send-to-self works on LAN.

---

## Step 9: Build Android

```bash
cd clients/localsend/app   # relative to pipernet repo root

# Build Android debug APK (unsigned — no signing key needed for stage 2)
flutter build apk --debug

# Output: build/app/outputs/flutter-apk/app-debug.apk
```

Note: For stage 2, debug APK is fine (sideload only, no Play Store). Stage 3 task: generate proper signing keystore and build a release APK.

---

## Step 10: GitHub release

Repository: `https://github.com/dot-protocol/dotdrop`

If the repo doesn't exist, create it:
```bash
gh repo create dot-protocol/dotdrop --public --description "Pied Piper native client. Fork of LocalSend."
```

Tag and publish:
```bash
# From the localsend fork root (pipernet/clients/localsend)

# Tag the commit
git tag v0.1.0
git push origin v0.1.0

# Create GitHub release with assets (paths relative to where you built)
gh release create v0.1.0 \
  PiedPiper-0.1.0-mac.dmg \
  clients/localsend/app/build/app/outputs/flutter-apk/app-debug.apk \
  --title "dotdrop v0.1.0" \
  --notes "First cut. macOS and Android.

The protocol underneath is LocalSend — credit at NOTICE.md. The next cuts merge in the relay path so a drop can cross networks, not just the room."
```

---

## Step 11: Wire piedpiper.fun

The home page CTA is already wired to `/install` (done in stage 2 site work).

The `/install` page at `piedpiper-fun/install/index.html` already points to:
```
https://github.com/dot-protocol/dotdrop/releases/latest
```

After the GitHub release exists, the links are live. No further site changes needed.

Optionally add a footer link in `piedpiper-fun/index.html`:
```html
<a href="/install">install</a>
```
Between the existing `app` and `holders` links.

---

## Step 12: Commit + push piedpiper-fun

Already done in stage 2 (site work). Vercel auto-deploys on push to main.

If making further changes:
```bash
# from the piedpiper-fun repo root
git add .
git commit -m "your message"
git push   # Vercel auto-deploys
```

---

## Stage 3 deferred tasks

These are intentionally NOT in stage 2:

| Task | Reason deferred |
|------|----------------|
| Proper Android signing keystore | Requires keytool setup, test APK fine for stage 2 |
| iOS build | Requires Apple Developer account + provisioning |
| Windows build | Lower priority per Jared's advice |
| Linux build | Lower priority |
| App Store / Play Store listing | After proper signing + review cycle |
| Real Pied Piper icon (not placeholder) | Need final SVG from design pass |
| Integration point 1: Ed25519 keypair | Stage 3 — core Pipernet integration |
| Integration point 2: Signed transfer manifest | Stage 3 |
| Integration point 3: Relay fallback | Stage 3 — relay.piedpiper.fun integration |
| Integration point 4: Transfer event emit | Stage 3 |

---

## Integration points (stage 3+ detailed plan)

### Integration point 1: Ed25519 keypair

**Files to modify:**
- `app/lib/config/init.dart` — add keypair generation on first launch
- `app/lib/model/persistence/` — new `PiperIdentity` model
- `app/lib/pages/home_page.dart` — show QR + `piper://` handle

**Approach:**
- Use `dart:typed_data` + `cryptography` package (add to pubspec.yaml)
- On first launch: `Ed25519().newKeyPair()` → serialize seed to secure storage
- Public key = 32 bytes base58-encoded → the device's Pied Piper address
- Show on home screen as: `piper://[address]` with QR code

### Integration point 2: Signed transfer manifest

**Files to modify:**
- `common/lib/src/model/` — add `SignedManifest` wrapper
- `app/lib/` wherever transfer initiation happens (look for `PrepareUploadRequest`)

**Approach:**
- Before sending: sign the transfer manifest (`file hashes + sender pubkey + timestamp`) with Ed25519
- Bundle signature into the PrepareUploadRequest
- Receiver: verify signature on receipt, store signed manifest locally
- Two-sided receipt: sender gets ACK signed by receiver, receiver keeps sender-signed manifest

### Integration point 3: Relay fallback

**Files to modify:**
- `app/lib/provider/` — discovery provider, add relay discovery path
- `common/lib/src/api/` — add relay client

**Approach:**
- Current flow: mDNS broadcast → device found on LAN
- New flow: if mDNS finds nothing in 5s → try relay at `https://relay.piedpiper.fun`
  - `POST /channels/relay-discovery` with sender pubkey + OTP
  - Receiver (on relay) gets notified, opens P2P connection through relay as TURN-style intermediary
  - Use the existing Pipernet relay SSE + POST API

### Integration point 4: Transfer event emit

**Files to modify:**
- `app/lib/` — post-transfer success handler (look for where receiver marks transfer complete)

**Approach:**
- On successful transfer completion: emit to `https://relay.piedpiper.fun/channels/transfer-events`
- Payload: `{from: senderPubkey, to: receiverPubkey, filehash: sha256, timestamp: iso}`
- Backend accumulates events per holder address
- Future: accumulate $PIPER receipts per transfer

---

*This document is the complete execution spec for stage 2D onwards.*  
*Updated by: Rocky sub-agent, 2026-05-03*
