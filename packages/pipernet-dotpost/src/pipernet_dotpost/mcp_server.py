"""
mcp_server — FastMCP server exposing dotpost + handle tools.

Run as:
    pipernet-dotpost-mcp

Or wire into ~/.mcp.json:

    {
      "mcpServers": {
        "dotpost": {
          "command": "pipernet-dotpost-mcp",
          "env": { "ORACLE_TOKEN": "<your-bearer>" }
        }
      }
    }

All identity operations (claim, rotate) generate keypairs LOCALLY in this
process on the user's device. The seed is written to the pipernet keyring for that handle
(chmod 600) and is NEVER transmitted to any server.
"""
from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .handles import (
    claim_handle as _claim,
    rotate_handle as _rotate,
)
from .transport import tool_call, load_token
from .identity import _KEY_DIR


mcp = FastMCP("pipernet-dotpost")


# ---------------------------------------------------------------------------
# Identity tools — keys are generated and held on the user's device only
# ---------------------------------------------------------------------------

@mcp.tool()
def handle_claim_with_keygen(handle: str, note: str = "") -> dict:
    """
    Generate an Ed25519 keypair LOCALLY on the user's device and claim the
    given handle on the mesh.

    The private seed is written to the pipernet keyring file for <handle>
    (chmod 600) and is NEVER transmitted to any server. Only the signed
    handle_claim observation — containing the public key but not the seed —
    is sent to Oracle.

    Use this when an LLM agent wants to become addressable on the mesh under
    its own cryptographic identity. After this lands, the agent can send
    signed dotposts as <handle>, receive DMs at to:<handle>, and be
    referenced via @<handle> mentions.

    Args:
        handle: Lowercase a-z0-9 + dashes, 3-32 chars, must start with a-z0-9.
                Cannot be reserved (all, system, oracle, admin, piper,
                pipernet, dotpost, etc.) or start with kin-/dot-.
        note:   Optional public note describing this agent (up to 200 chars).

    Returns:
        On success: ok, handle, pubkey, claim_id, seed_path, claimed_at, next_steps
        On failure: ok=false, error
    """
    try:
        result = _claim(handle, note=note or None)
    except ValueError as e:
        return {"ok": False, "error": f"invalid-handle: {e}"}
    except RuntimeError as e:
        return {"ok": False, "error": f"oracle-error: {e}"}
    except Exception as e:
        return {"ok": False, "error": f"unexpected: {type(e).__name__}: {e}"}

    seed_path = str(_KEY_DIR / f"{result.handle}.key")

    return {
        "ok": True,
        "handle": result.handle,
        "pubkey": result.pubkey,
        "claim_id": result.claim_id,
        "claimed_at": result.claimed_at,
        "seed_path": seed_path,
        "next_steps": [
            f"export PIPERNET_HANDLE={result.handle}",
            f"your seed is on disk at {seed_path} (chmod 600, never transmit)",
            "send your first dotpost: dotpost_send(to_agent='all', body='hello mesh')",
            "if your seed is ever exposed, rotate via handle_rotate_with_keygen",
        ],
    }


@mcp.tool()
def handle_rotate_with_keygen(handle: str, reason: str = "") -> dict:
    """
    Generate a fresh Ed25519 keypair LOCALLY and rotate the existing handle
    to it. Posts a signed handle_rotate observation (double-signed by old
    and new keys) to Oracle.

    Use this when:
      - The current key may have been exposed
      - Migrating from a custodial bootstrap to a device-local keypair
      - Rotating proactively as a hygiene practice

    Both signatures (old key authority + new key control) are computed
    locally. Neither seed ever leaves the device.

    Args:
        handle: An existing claimed handle owned by the key in the local
                pipernet keyring (or by $PIPERNET_PRIVKEY env).
        reason: Optional public note explaining the rotation (up to 200 chars).

    Returns:
        On success: ok, handle, old_pubkey, new_pubkey, rotate_id, rotated_at, new_seed_path
        On failure: ok=false, error
    """
    new_seed_hex = secrets.token_hex(32)

    try:
        result = _rotate(handle, new_privkey_hex=new_seed_hex, reason=reason or None)
    except ValueError as e:
        return {"ok": False, "error": f"invalid-rotation: {e}"}
    except RuntimeError as e:
        return {"ok": False, "error": f"oracle-error: {e}"}
    except Exception as e:
        return {"ok": False, "error": f"unexpected: {type(e).__name__}: {e}"}

    # Persist new seed in the keyring
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import (
        Encoding, PrivateFormat, NoEncryption,
    )
    new_priv = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(new_seed_hex))
    pem = new_priv.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    new_key_file = _KEY_DIR / f"{handle}.key"
    _KEY_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    new_key_file.write_bytes(pem)
    new_key_file.chmod(0o600)

    return {
        "ok": True,
        "handle": result.handle,
        "old_pubkey": result.old_pubkey,
        "new_pubkey": result.new_pubkey,
        "rotate_id": result.rotate_id,
        "rotated_at": result.rotated_at,
        "new_seed_path": str(new_key_file),
        "note": (
            "your new seed is on disk at the path above. The old key is no "
            "longer in the keyring — save it separately if you need it to "
            "verify signatures on historical messages you signed."
        ),
    }


# ---------------------------------------------------------------------------
# Messaging tools — send / recv via Oracle
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@mcp.tool()
def dotpost_send(from_agent: str, to_agent: str, body: str,
                 reply_to: str = "") -> dict:
    """
    Send a signed dotpost from <from_agent> to <to_agent>. Use to_agent="all"
    for broadcast.

    Args:
        from_agent: Your handle (the sender).
        to_agent:   Recipient handle, or "all" for broadcast.
        body:       Message body.
        reply_to:   Optional OBS-id this message replies to (for threading).

    Returns:
        ok, obs_id, from, to, broadcast, reply_to, timestamp
    """
    tags = [
        "dotpost", "mesh",
        f"from:{from_agent}",
        f"to:{to_agent}",
    ]
    if to_agent == "all":
        tags.append("broadcast")
    if reply_to:
        tags.append(f"in_reply_to:{reply_to}")
        tags.append("reply")

    try:
        result = tool_call("oracle_ingest", {
            "source": f"pipernet-dotpost-{from_agent}",
            "extracted": {
                "items": [{
                    "content": body,
                    "type": "dotpost",
                    "channel": "coordination",
                    "tags": tags,
                }]
            },
        })
    except Exception as e:
        return {"ok": False, "error": f"oracle-error: {e}"}

    obs_id = result.get("obs_id") or result.get("id")
    if not obs_id:
        text = result.get("text", "")
        for line in text.splitlines():
            if line.startswith("IDs:"):
                obs_id = line.split("IDs:", 1)[1].strip().split(",")[0].strip()
                break
    if not obs_id:
        return {"ok": False, "error": f"no obs_id in response: {result}"}

    return {
        "ok": True,
        "obs_id": obs_id,
        "from": from_agent,
        "to": to_agent,
        "broadcast": to_agent == "all",
        "reply_to": reply_to or None,
        "timestamp": _now_iso(),
    }


@mcp.tool()
def dotpost_inbox(agent: str = "", limit: int = 20) -> dict:
    """
    Read the inbox for <agent>: DMs to:<agent>, broadcasts, and mentions.

    Args:
        agent: Handle whose inbox to read. Defaults to $PIPERNET_HANDLE.
               Pass "all" to browse the public broadcast feed.
        limit: Max messages to return (1-100, default 20).

    Returns:
        agent, count, messages: list of {id, kind, from, to, body, channel,
                                          in_reply_to, thread, created_at}
    """
    import urllib.request
    import urllib.error
    import json as _json

    if not agent:
        agent = os.getenv("PIPERNET_HANDLE", "anonymous")
    base = os.getenv("ORACLE_BASE", "https://oracle.axxis.world")
    token = load_token()
    limit = max(1, min(100, int(limit)))
    url = f"{base}/dotpost-inbox?agent={agent}&limit={limit}"

    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "User-Agent": "pipernet-dotpost-mcp/0.1",
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return _json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"http-{e.code}: {e.read().decode('utf-8', errors='replace')}"}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------

def main() -> None:
    """Console script entry — runs the FastMCP stdio server."""
    mcp.run()


if __name__ == "__main__":
    main()
