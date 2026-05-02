/**
 * examples/javascript/send_envelope.js
 * ----------------------------------------
 * Send a signed Pipernet envelope from JavaScript using the relay HTTP API.
 * Runs in Node.js 18+ (built-in fetch) or any modern browser.
 *
 * Prerequisites:
 *   - A running Pipernet relay:  pipernet serve --port 8000
 *   - A registered pubkey for the sender handle (see below)
 *   - The sender's private key available as a hex string (from keygen)
 *
 * Note: Ed25519 signing in the browser/Node uses the Web Crypto API.
 * This example shows the full signing flow without depending on the
 * Python CLI — useful for building native JS/TS clients.
 *
 * Run:
 *   node examples/javascript/send_envelope.js
 *
 * To use in a browser, paste the sendEnvelope() function into your app
 * and store the private key in a secure location (IndexedDB, not localStorage).
 */

const RELAY_URL = process.env.RELAY_URL || "http://localhost:8000";
const HANDLE    = process.env.HANDLE    || "alice-js";
const CHANNEL   = process.env.CHANNEL   || "demo";

// ---------------------------------------------------------------------------
// Crypto helpers (Web Crypto API — works in Node 18+ and all modern browsers)
// ---------------------------------------------------------------------------

/**
 * Import an Ed25519 private key from raw bytes (32 bytes).
 * The Web Crypto API needs the private key in PKCS#8 format for Ed25519.
 * We build the PKCS#8 wrapper manually.
 */
async function importPrivateKey(privateKeyHex) {
  const privateBytes = hexToBytes(privateKeyHex);

  // PKCS#8 DER wrapper for Ed25519 private key (RFC 5958)
  // Header: 30 2e 02 01 00 30 05 06 03 2b 65 70 04 22 04 20 + 32 bytes key
  const pkcs8Header = new Uint8Array([
    0x30, 0x2e, 0x02, 0x01, 0x00, 0x30, 0x05, 0x06,
    0x03, 0x2b, 0x65, 0x70, 0x04, 0x22, 0x04, 0x20,
  ]);
  const pkcs8 = new Uint8Array(pkcs8Header.length + privateBytes.length);
  pkcs8.set(pkcs8Header);
  pkcs8.set(privateBytes, pkcs8Header.length);

  return await crypto.subtle.importKey(
    "pkcs8",
    pkcs8.buffer,
    { name: "Ed25519" },
    false,         // not extractable
    ["sign"],
  );
}

function hexToBytes(hex) {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < hex.length; i += 2) {
    bytes[i / 2] = parseInt(hex.slice(i, i + 2), 16);
  }
  return bytes;
}

function bytesToHex(bytes) {
  return Array.from(bytes).map(b => b.toString(16).padStart(2, "0")).join("");
}

/**
 * Canonical JSON: sorted keys, no whitespace.
 * Must match the Python `canonical()` function in cli/core.py.
 */
function canonical(obj) {
  return JSON.stringify(obj, Object.keys(obj).sort());
}

// ---------------------------------------------------------------------------
// Build and sign an envelope
// ---------------------------------------------------------------------------

/**
 * Build a signed Pipernet envelope.
 *
 * @param {object} params
 * @param {string} params.handle        - sender handle
 * @param {string} params.channel       - target channel name
 * @param {string} params.body          - message text
 * @param {string} params.privateKeyHex - 64-hex-char Ed25519 private key
 * @returns {Promise<object>}            signed envelope
 */
async function buildEnvelope({ handle, channel, body, privateKeyHex }) {
  const sequence  = Date.now(); // Lamport clock seed; relay may normalise
  const timestamp = new Date().toISOString();

  // The payload that gets signed (must match spec/01-envelope.md canonical form)
  const payload = {
    body: [["txt", body]],
    channel,
    from: handle,
    modes: [],
    parent: null,
    sequence,
    timestamp,
  };

  const privateKey = await importPrivateKey(privateKeyHex);
  const canonical_bytes = new TextEncoder().encode(canonical(payload));
  const signature_bytes = await crypto.subtle.sign("Ed25519", privateKey, canonical_bytes);

  return {
    ...payload,
    signature: bytesToHex(new Uint8Array(signature_bytes)),
  };
}

// ---------------------------------------------------------------------------
// Relay helpers
// ---------------------------------------------------------------------------

async function registerPubkey(relayUrl, handle, pubkeyHex) {
  const res = await fetch(`${relayUrl}/pubkeys`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ handle, pubkey_hex: pubkeyHex }),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`pubkey registration failed: ${res.status} ${err}`);
  }
  return await res.json();
}

async function sendEnvelope(relayUrl, channel, envelope) {
  const res = await fetch(`${relayUrl}/channels/${channel}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(envelope),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`relay rejected envelope: ${res.status} ${err}`);
  }
  return await res.json();
}

async function readChannel(relayUrl, channel) {
  const res = await fetch(`${relayUrl}/channels/${channel}`);
  if (!res.ok) throw new Error(`channel read failed: ${res.status}`);
  return await res.json();
}

// ---------------------------------------------------------------------------
// Demo: generate a keypair, register, send, read back
// ---------------------------------------------------------------------------

async function demo() {
  // Generate an ephemeral keypair for this demo.
  // In a real app, you would generate once and store securely.
  const keyPair = await crypto.subtle.generateKey(
    { name: "Ed25519" },
    true,           // extractable (so we can export the public key)
    ["sign", "verify"],
  );

  // Export the raw public key (32 bytes → 64 hex chars)
  const pubKeyRaw   = await crypto.subtle.exportKey("raw", keyPair.publicKey);
  const pubKeyHex   = bytesToHex(new Uint8Array(pubKeyRaw));

  // Export the private key in PKCS#8, then extract the 32-byte seed
  const privPkcs8   = await crypto.subtle.exportKey("pkcs8", keyPair.privateKey);
  const privBytes   = new Uint8Array(privPkcs8).slice(-32); // last 32 bytes = seed
  const privKeyHex  = bytesToHex(privBytes);

  console.log(`Demo handle:  ${HANDLE}`);
  console.log(`Pubkey (hex): ${pubKeyHex}`);
  console.log(`Relay:        ${RELAY_URL}`);
  console.log("");

  // 1. Register pubkey on relay
  console.log("Registering pubkey...");
  const reg = await registerPubkey(RELAY_URL, HANDLE, pubKeyHex);
  console.log(`  registered: ${reg.registered}`);
  console.log("");

  // 2. Build and send a signed envelope
  console.log("Signing and sending envelope...");
  const envelope = await buildEnvelope({
    handle:        HANDLE,
    channel:       CHANNEL,
    body:          "hello from send_envelope.js",
    privateKeyHex: privKeyHex,
  });
  console.log(`  signature: ${envelope.signature.slice(0, 16)}...`);

  const response = await sendEnvelope(RELAY_URL, CHANNEL, envelope);
  console.log(`  relay accepted: from=${response.from} seq=${response.sequence}`);
  console.log("");

  // 3. Read back the channel
  console.log(`Reading channel '${CHANNEL}'...`);
  const envelopes = await readChannel(RELAY_URL, CHANNEL);
  console.log(`  ${envelopes.length} envelope(s)`);
  for (const e of envelopes.slice(-3)) {
    const text = (e.body || []).find(p => Array.isArray(p) && p[0] === "txt")?.[1] ?? "";
    console.log(`  [${e.from}] ${text}`);
  }
}

demo().catch(err => {
  console.error("Error:", err.message);
  process.exit(1);
});
