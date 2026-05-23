// SPDX-License-Identifier: Apache-2.0
// Part of @axxis/oracle — https://github.com/dot-protocol/oracle-sdk-ts

import { readFileSync, writeFileSync } from 'node:fs';
import { randomBytes } from 'node:crypto';
import * as ed from '@noble/ed25519';
import { sha512 } from '@noble/hashes/sha512';
import { sha256 } from '@noble/hashes/sha256';

import type { Keypair } from './types.js';

// @noble/ed25519 v2 requires a sync sha512 implementation to use sync APIs.
// Wire it up via @noble/hashes once at module load. Idempotent.
(
  ed as unknown as { etc: { sha512Sync?: (...m: Uint8Array[]) => Uint8Array } }
).etc.sha512Sync = (...m: Uint8Array[]) => sha512(concatBytes(...m));

// ---- low-level byte helpers ----

function concatBytes(...arrs: Uint8Array[]): Uint8Array {
  let total = 0;
  for (const a of arrs) total += a.length;
  const out = new Uint8Array(total);
  let off = 0;
  for (const a of arrs) {
    out.set(a, off);
    off += a.length;
  }
  return out;
}

function hexToBytes(hex: string): Uint8Array {
  if (hex.length % 2 !== 0) throw new Error('hex string has odd length');
  const out = new Uint8Array(hex.length / 2);
  for (let i = 0; i < out.length; i++) {
    const byte = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
    if (Number.isNaN(byte)) throw new Error(`invalid hex at offset ${i * 2}`);
    out[i] = byte;
  }
  return out;
}

function bytesToHex(b: Uint8Array): string {
  let s = '';
  for (let i = 0; i < b.length; i++) {
    const byte = b[i];
    if (byte === undefined) continue;
    s += byte.toString(16).padStart(2, '0');
  }
  return s;
}

function bytesToBase64(b: Uint8Array): string {
  if (typeof Buffer !== 'undefined') return Buffer.from(b).toString('base64');
  let s = '';
  for (let i = 0; i < b.length; i++) {
    const byte = b[i];
    if (byte === undefined) continue;
    s += String.fromCharCode(byte);
  }
  return globalThis.btoa(s);
}

// ---- signed-request canonical bytes (spec §3.2) ----

const SIGNED_REQUEST_DOMAIN = 'pipernet-signed-v1';

/** Hex sha256 of arbitrary bytes (UTF-8 string body → bytes first). */
export function sha256Hex(body: string | Uint8Array): string {
  const bytes = typeof body === 'string' ? new TextEncoder().encode(body) : body;
  return bytesToHex(sha256(bytes));
}

/** Empty-body sha256 hex per spec §3.2 ("e3b0c4..."). */
export const EMPTY_BODY_SHA256_HEX =
  'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855';

/**
 * Build canonical signature bytes per signed-request-v0.1 §3.2.
 *
 * Fields joined by `\n` in this exact order:
 *   domain, METHOD, path, query, sha256(body)_hex, handle, pubkey_b64, ts, nonce_b64
 *
 * Empty query string and empty body MUST still occupy their line (just an empty
 * segment between newlines). Don't omit.
 */
export function canonicalBytes(args: {
  method: string;
  path: string;
  queryString: string;
  bodyHashHex: string;
  handle: string;
  pubkeyB64: string;
  timestamp: string;
  nonceB64: string;
}): Uint8Array {
  const parts = [
    SIGNED_REQUEST_DOMAIN,
    args.method.toUpperCase(),
    args.path,
    args.queryString,
    args.bodyHashHex,
    args.handle,
    args.pubkeyB64,
    args.timestamp,
    args.nonceB64,
  ];
  return new TextEncoder().encode(parts.join('\n'));
}

/** Sign canonical bytes with an Ed25519 private key (hex seed). Returns 64-byte sig. */
export function signEd25519(canonical: Uint8Array, privkeyHex: string): Uint8Array {
  const seed = hexToBytes(privkeyHex);
  if (seed.length !== 32) {
    throw new Error(`Ed25519 private key must be 32 bytes (got ${seed.length})`);
  }
  return ed.sign(canonical, seed);
}

/** ISO-8601 UTC timestamp, Z suffix, second precision (e.g. "2026-05-24T01:23:45Z"). */
export function nowIso(): string {
  return new Date().toISOString().replace(/\.\d{3}Z$/, 'Z');
}

/** Cryptographically random nonce, base64 of `numBytes` (default 16). */
export function makeNonceB64(numBytes = 16): string {
  return bytesToBase64(new Uint8Array(randomBytes(numBytes)));
}

/** Encode a hex-encoded 32-byte pubkey as base64 for the X-Pipernet-Pubkey header. */
export function pubkeyHexToB64(pubkeyHex: string): string {
  const bytes = hexToBytes(pubkeyHex);
  if (bytes.length !== 32) {
    throw new Error(`Ed25519 public key must be 32 bytes (got ${bytes.length})`);
  }
  return bytesToBase64(bytes);
}

/**
 * Derive a deterministic handle from a pubkey for fresh keypairs that haven't
 * filed a `handle_claim` yet. Format: `pk` + first 16 hex chars.
 * Matches server regex `^[a-z0-9][a-z0-9-]{0,63}$` — colon is NOT allowed.
 */
export function deriveDefaultHandle(pubkeyHex: string): string {
  if (pubkeyHex.length < 16) throw new Error('pubkey hex too short');
  return `pk${pubkeyHex.slice(0, 16).toLowerCase()}`;
}

// ---- keypair I/O ----

/**
 * Load a keypair from a JSON file:
 * ```json
 * { "pubkeyHex": "abcd…", "privkeyHex": "abcd…" }
 * ```
 *
 * Synchronous on purpose — matches `loadKeypair('key.json')` ergonomics from
 * the hello-world example.
 */
export function loadKeypair(path: string): Keypair {
  const raw = readFileSync(path, 'utf-8');
  const parsed: unknown = JSON.parse(raw);
  if (
    !parsed ||
    typeof parsed !== 'object' ||
    typeof (parsed as { pubkeyHex?: unknown }).pubkeyHex !== 'string' ||
    typeof (parsed as { privkeyHex?: unknown }).privkeyHex !== 'string'
  ) {
    throw new Error(`keypair file ${path} must contain {pubkeyHex, privkeyHex} strings`);
  }
  const kp = parsed as Keypair;
  if (kp.pubkeyHex.length !== 64) throw new Error('pubkeyHex must be 64 hex chars (32 bytes)');
  if (kp.privkeyHex.length !== 64) throw new Error('privkeyHex must be 64 hex chars (32 bytes)');
  return kp;
}

/** Save a keypair to a JSON file (caller is responsible for `chmod 0600`). */
export function saveKeypair(path: string, kp: Keypair): void {
  writeFileSync(path, JSON.stringify(kp, null, 2), 'utf-8');
}

/**
 * Generate a fresh Ed25519 keypair.
 *
 * `privkeyHex` is the 32-byte Ed25519 seed (NOT the expanded 64-byte secret).
 * `pubkeyHex` is the derived 32-byte public key.
 */
export function generateKeypair(): Keypair {
  const seed = new Uint8Array(randomBytes(32));
  const pub = ed.getPublicKey(seed);
  return {
    pubkeyHex: bytesToHex(pub),
    privkeyHex: bytesToHex(seed),
  };
}

// ---- exports for tests ----
export const _internals = {
  concatBytes,
  hexToBytes,
  bytesToHex,
  bytesToBase64,
  SIGNED_REQUEST_DOMAIN,
};
