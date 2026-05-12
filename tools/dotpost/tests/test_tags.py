"""
test_tags — tag validation regex, parse round-trips, build helpers.
"""
import unittest

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from dotpost.tags import (
    validate_group_name,
    parse_to_arg,
    parse_groups_arg,
    parse_comma_list,
    build_send_tags,
    build_group_tags,
    build_intent_tags,
    build_resolve_tags,
    BROADCAST_HANDLE,
)


class TestValidateGroupName(unittest.TestCase):
    def test_valid_names(self):
        for name in ["arch", "room-design", "a1b2", "x", "ab-cd-ef"]:
            self.assertEqual(validate_group_name(name), name)

    def test_invalid_names(self):
        for name in ["-bad", "BAD", "has space", "under_score", ""]:
            with self.assertRaises(ValueError):
                validate_group_name(name)


class TestParseToArg(unittest.TestCase):
    def test_broadcast(self):
        self.assertEqual(parse_to_arg("all"), ("broadcast", None))

    def test_handle(self):
        self.assertEqual(parse_to_arg("shannon"), ("handle", "shannon"))

    def test_group_valid(self):
        self.assertEqual(parse_to_arg("group:room-design"), ("group", "room-design"))

    def test_group_invalid(self):
        with self.assertRaises(ValueError):
            parse_to_arg("group:UPPER")


class TestParseGroupsArg(unittest.TestCase):
    def test_none_returns_empty(self):
        self.assertEqual(parse_groups_arg(None), [])

    def test_empty_returns_empty(self):
        self.assertEqual(parse_groups_arg(""), [])

    def test_single(self):
        self.assertEqual(parse_groups_arg("arch"), ["arch"])

    def test_multiple(self):
        self.assertEqual(parse_groups_arg("arch,room-design"), ["arch", "room-design"])

    def test_spaces_stripped(self):
        self.assertEqual(parse_groups_arg(" arch , cmo "), ["arch", "cmo"])

    def test_invalid_raises(self):
        with self.assertRaises(ValueError):
            parse_groups_arg("arch,BAD")


class TestParseCommaList(unittest.TestCase):
    def test_none_empty(self):
        self.assertEqual(parse_comma_list(None), [])

    def test_single(self):
        self.assertEqual(parse_comma_list("item1"), ["item1"])

    def test_multiple(self):
        self.assertEqual(parse_comma_list("a,b,c"), ["a", "b", "c"])

    def test_strips_whitespace(self):
        self.assertEqual(parse_comma_list(" a , b "), ["a", "b"])


class TestBuildSendTags(unittest.TestCase):
    def test_dm_tags(self):
        tags = build_send_tags("shannon", "jared")
        self.assertIn("dotpost", tags)
        self.assertIn("from:shannon", tags)
        self.assertIn("to:jared", tags)
        self.assertIn("mesh", tags)
        self.assertNotIn("broadcast", tags)

    def test_broadcast_tags(self):
        tags = build_send_tags("shannon", BROADCAST_HANDLE)
        self.assertIn("broadcast", tags)
        self.assertIn("to:all", tags)

    def test_reply_to_tags(self):
        tags = build_send_tags("shannon", "jared", reply_to="OBS-123")
        self.assertIn("reply", tags)
        self.assertIn("in_reply_to:OBS-123", tags)

    def test_extra_tags_appended(self):
        tags = build_send_tags("shannon", "jared", extra=["custom-tag"])
        self.assertIn("custom-tag", tags)


class TestBuildGroupTags(unittest.TestCase):
    def test_group_tags(self):
        tags = build_group_tags("shannon", "arch")
        self.assertIn("to:group:arch", tags)
        self.assertIn("group:arch", tags)
        self.assertIn("group-post", tags)
        self.assertIn("from:shannon", tags)

    def test_invalid_group_raises(self):
        with self.assertRaises(ValueError):
            build_group_tags("shannon", "INVALID")

    def test_reply_to(self):
        tags = build_group_tags("shannon", "arch", reply_to="OBS-X")
        self.assertIn("reply", tags)
        self.assertIn("in_reply_to:OBS-X", tags)


class TestBuildIntentTags(unittest.TestCase):
    def test_intent_tags(self):
        tags = build_intent_tags("shannon", "abc123", "sig456")
        self.assertIn("dotpost", tags)
        self.assertIn("intent", tags)
        self.assertIn("from:shannon", tags)
        self.assertIn("intent:abc123", tags)
        self.assertIn("intent_sig:sig456", tags)
        self.assertIn("to:all", tags)

    def test_context_refs(self):
        tags = build_intent_tags("shannon", "abc", "sig", context_refs=["obs:1", "obs:2"])
        self.assertIn("context_ref:obs:1", tags)
        self.assertIn("context_ref:obs:2", tags)


class TestBuildResolveTags(unittest.TestCase):
    def test_resolve_tags(self):
        tags = build_resolve_tags("baran", "res_b64", "sig_b64", "OBS-intent-1")
        self.assertIn("dotpost", tags)
        self.assertIn("resolve", tags)
        self.assertIn("from:baran", tags)
        self.assertIn("resolve:res_b64", tags)
        self.assertIn("resolve_sig:sig_b64", tags)
        self.assertIn("resolves_intent:OBS-intent-1", tags)


if __name__ == "__main__":
    unittest.main()
