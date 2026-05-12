"""
test_handles — Unit tests for the handle substrate reference implementation.

All Oracle calls are mocked to avoid hitting the live service.
"""
import json
import unittest
from unittest.mock import patch, MagicMock
import zlib
import base64
from datetime import datetime, timezone
import sys
from pathlib import Path

# Add parent dirs to path so imports work.
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from handles import (
    claim_handle,
    resolve_handle,
    add_contact,
    remove_contact,
    list_contacts,
    parse_mentions,
    mention_tags,
)


def _base64url_encode(data: bytes) -> str:
    """Helper to encode like the real implementation."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _base64url_decode(s: str) -> bytes:
    """Helper to decode like the real implementation."""
    padding = (4 - len(s) % 4) % 4
    s_padded = s + "=" * padding
    return base64.urlsafe_b64decode(s_padded)


class TestHandleValidation(unittest.TestCase):
    """Test handle validation rules."""

    @patch("handles.handles.tool_call")
    def test_claim_valid_handle(self, mock_tool_call):
        """Happy path: claim a valid handle."""
        mock_tool_call.return_value = {"obs_id": "OBS-123"}
        result = claim_handle("shannon", note="test session")
        self.assertEqual(result.handle, "shannon")
        self.assertTrue(result.pubkey.startswith("ed25519:"))
        self.assertEqual(result.claim_id, "OBS-123")

    def test_claim_rejects_reserved(self):
        """Reserved handles are rejected."""
        with self.assertRaises(ValueError) as ctx:
            claim_handle("all")
        self.assertIn("reserved", str(ctx.exception))

    def test_claim_rejects_too_short(self):
        """Handles < 3 chars are rejected."""
        with self.assertRaises(ValueError) as ctx:
            claim_handle("ab")
        self.assertIn("invalid", str(ctx.exception))

    def test_claim_rejects_bad_chars(self):
        """Handles with invalid chars are rejected."""
        with self.assertRaises(ValueError) as ctx:
            claim_handle("shan@non")
        self.assertIn("invalid", str(ctx.exception))

    def test_claim_rejects_starts_with_hyphen(self):
        """Handles starting with hyphen are rejected."""
        with self.assertRaises(ValueError) as ctx:
            claim_handle("-shannon")
        self.assertIn("invalid", str(ctx.exception))

    def test_claim_rejects_kin_prefix(self):
        """kin-* prefix is reserved."""
        with self.assertRaises(ValueError) as ctx:
            claim_handle("kin-test")
        self.assertIn("reserved", str(ctx.exception))

    @patch("handles.handles.tool_call")
    def test_claim_normalizes_case(self, mock_tool_call):
        """Handles are normalized to lowercase."""
        mock_tool_call.return_value = {"obs_id": "OBS-456"}
        result = claim_handle("SHANNON")
        self.assertEqual(result.handle, "shannon")

    def test_claim_too_long(self):
        """Handles > 32 chars are rejected."""
        long_handle = "a" * 33
        with self.assertRaises(ValueError) as ctx:
            claim_handle(long_handle)
        self.assertIn("invalid", str(ctx.exception))


class TestResolveHandle(unittest.TestCase):
    """Test handle resolution."""

    @patch("handles.handles.tool_call")
    def test_resolve_unclaimed(self, mock_tool_call):
        """Resolving an unclaimed handle returns None."""
        mock_tool_call.return_value = {}
        result = resolve_handle("unclaimed")
        self.assertIsNone(result)

    @patch("handles.handles.tool_call")
    def test_resolve_valid_claim(self, mock_tool_call):
        """Resolving a valid claim returns the pubkey."""
        # Build a valid claim object.
        pubkey_b64 = "a" * 43  # Fake 32-byte base64.
        claim_obj = {
            "v": 1,
            "kind": "handle_claim",
            "handle": "shannon",
            "pubkey": f"ed25519:{pubkey_b64}",
            "claimed_at": "2026-05-12T15:30:00Z",
            "note": "test",
        }
        canonical = json.dumps(claim_obj, sort_keys=True, separators=(",", ":")).encode()

        # Mock Oracle response.
        mock_tool_call.return_value = {
            "items": [
                {
                    "id": "OBS-123",
                    "created_at": "2026-05-12T15:30:00Z",
                    "tags": [
                        "handle_claim:shannon",
                        f"handle_pubkey:{pubkey_b64}",
                        f"claim_z:{_base64url_encode(zlib.compress(canonical, level=3))}",
                        f"claim_sig:fake_sig_here",
                    ],
                }
            ]
        }

        # This will fail signature verification (fake sig), so returns None.
        result = resolve_handle("shannon")
        self.assertIsNone(result)

    @patch("handles.handles.tool_call")
    def test_resolve_oldest_first(self, mock_tool_call):
        """When multiple claims exist, oldest wins (first-valid-write)."""
        pubkey_b64_a = "a" * 43
        pubkey_b64_b = "b" * 43
        claim_obj_a = {
            "v": 1,
            "kind": "handle_claim",
            "handle": "test",
            "pubkey": f"ed25519:{pubkey_b64_a}",
            "claimed_at": "2026-05-12T10:00:00Z",
            "note": "",
        }
        claim_obj_b = {
            "v": 1,
            "kind": "handle_claim",
            "handle": "test",
            "pubkey": f"ed25519:{pubkey_b64_b}",
            "claimed_at": "2026-05-12T20:00:00Z",
            "note": "",
        }

        # Both claims present; Oracle returns them in arbitrary order.
        canonical_a = json.dumps(claim_obj_a, sort_keys=True, separators=(",", ":")).encode()
        canonical_b = json.dumps(claim_obj_b, sort_keys=True, separators=(",", ":")).encode()

        mock_tool_call.return_value = {
            "items": [
                {
                    "id": "OBS-B",
                    "created_at": "2026-05-12T20:00:00Z",
                    "tags": [
                        "handle_claim:test",
                        f"handle_pubkey:{pubkey_b64_b}",
                        f"claim_z:{_base64url_encode(zlib.compress(canonical_b, level=3))}",
                        f"claim_sig:fake_sig_b",
                    ],
                },
                {
                    "id": "OBS-A",
                    "created_at": "2026-05-12T10:00:00Z",
                    "tags": [
                        "handle_claim:test",
                        f"handle_pubkey:{pubkey_b64_a}",
                        f"claim_z:{_base64url_encode(zlib.compress(canonical_a, level=3))}",
                        f"claim_sig:fake_sig_a",
                    ],
                },
            ]
        }

        # Will skip both due to fake sigs, returns None.
        result = resolve_handle("test")
        self.assertIsNone(result)


class TestContacts(unittest.TestCase):
    """Test contact list operations."""

    @patch("handles.handles.resolve_handle")
    @patch("handles.handles.tool_call")
    def test_add_contact_unresolved(self, mock_tool_call, mock_resolve):
        """Adding a contact that doesn't resolve is refused."""
        mock_resolve.return_value = None
        with self.assertRaises(ValueError) as ctx:
            add_contact("nonexistent")
        self.assertIn("contact-resolve-failed", str(ctx.exception))

    @patch("handles.handles.resolve_handle")
    @patch("handles.handles.tool_call")
    def test_add_contact_success(self, mock_tool_call, mock_resolve):
        """Successfully add a contact."""
        mock_resolve.return_value = MagicMock(pubkey="ed25519:abc")
        mock_tool_call.return_value = {"obs_id": "OBS-contact-1"}

        obs_id = add_contact("jared", alias="Jared (iPhone)", tags=["mesh-core"])
        self.assertEqual(obs_id, "OBS-contact-1")

    @patch("handles.handles.tool_call")
    def test_remove_contact_success(self, mock_tool_call):
        """Successfully remove a contact."""
        mock_tool_call.return_value = {"obs_id": "OBS-remove-1"}
        obs_id = remove_contact("jared")
        self.assertEqual(obs_id, "OBS-remove-1")

    @patch("handles.handles.tool_call")
    def test_list_contacts_empty(self, mock_tool_call):
        """Listing contacts when none exist returns empty list."""
        mock_tool_call.return_value = {}
        contacts = list_contacts("shannon")
        self.assertEqual(contacts, [])

    @patch("handles.handles.tool_call")
    def test_list_contacts_after_add_remove(self, mock_tool_call):
        """Contact list collapses add/remove events."""
        # Build mock observations: add contact A, add contact B, remove contact A.
        contact_a_obj = {
            "v": 1,
            "kind": "contact",
            "self": "shannon",
            "contact": "jared",
            "alias": "Jared",
            "added_at": "2026-05-12T10:00:00Z",
            "tags": ["mesh-core"],
        }
        contact_b_obj = {
            "v": 1,
            "kind": "contact",
            "self": "shannon",
            "contact": "stewart",
            "alias": "Stewart",
            "added_at": "2026-05-12T11:00:00Z",
            "tags": ["cmo"],
        }
        remove_a_obj = {
            "v": 1,
            "kind": "contact_remove",
            "self": "shannon",
            "contact": "jared",
            "removed_at": "2026-05-12T12:00:00Z",
        }

        canonical_a = json.dumps(contact_a_obj, sort_keys=True, separators=(",", ":")).encode()
        canonical_b = json.dumps(contact_b_obj, sort_keys=True, separators=(",", ":")).encode()
        canonical_remove = json.dumps(remove_a_obj, sort_keys=True, separators=(",", ":")).encode()

        mock_tool_call.return_value = {
            "items": [
                {
                    "id": "OBS-add-A",
                    "created_at": "2026-05-12T10:00:00Z",
                    "tags": [
                        "contact_for:shannon",
                        "contact:jared",
                        f"contact_z:{_base64url_encode(zlib.compress(canonical_a, level=3))}",
                    ],
                },
                {
                    "id": "OBS-add-B",
                    "created_at": "2026-05-12T11:00:00Z",
                    "tags": [
                        "contact_for:shannon",
                        "contact:stewart",
                        f"contact_z:{_base64url_encode(zlib.compress(canonical_b, level=3))}",
                    ],
                },
                {
                    "id": "OBS-remove-A",
                    "created_at": "2026-05-12T12:00:00Z",
                    "tags": [
                        "contact_for:shannon",
                        "contact_remove:jared",
                        f"contact_z:{_base64url_encode(zlib.compress(canonical_remove, level=3))}",
                    ],
                },
            ]
        }

        contacts = list_contacts("shannon")
        # Expect only stewart (jared was added then removed).
        self.assertEqual(len(contacts), 1)
        self.assertEqual(contacts[0].contact, "stewart")
        self.assertEqual(contacts[0].alias, "Stewart")


class TestMentions(unittest.TestCase):
    """Test mention parsing."""

    def test_parse_mentions_valid(self):
        """Parse valid mentions from body."""
        mentions = parse_mentions("hey @shannon and @jared, discuss?")
        self.assertEqual(sorted(mentions), ["jared", "shannon"])

    def test_parse_mentions_duplicate(self):
        """Duplicate mentions are deduplicated."""
        mentions = parse_mentions("@shannon @shannon @jared")
        self.assertEqual(sorted(mentions), ["jared", "shannon"])

    def test_parse_mentions_case_insensitive(self):
        """Mentions are parsed as lowercase (input is lowercased first)."""
        mentions = parse_mentions("@shannon @Jared")
        # Both are found (input is lowercased before regex matching).
        self.assertEqual(sorted(mentions), ["jared", "shannon"])

    def test_parse_mentions_too_short(self):
        """Mentions that are too short (@x) are rejected."""
        mentions = parse_mentions("@a @ab @shannon")
        self.assertEqual(mentions, ["shannon"])

    def test_parse_mentions_invalid_chars(self):
        """Mentions with invalid chars (@) are split by the regex."""
        mentions = parse_mentions("@shan@non @valid-name")
        # The regex finds @shan (3 chars), @non (3 chars), @valid-name.
        self.assertEqual(sorted(mentions), ["non", "shan", "valid-name"])

    def test_mention_tags(self):
        """Generate mention tags from body."""
        tags = mention_tags("hey @shannon and @jared")
        self.assertEqual(sorted(tags), ["mention:jared", "mention:shannon"])


if __name__ == "__main__":
    unittest.main()
