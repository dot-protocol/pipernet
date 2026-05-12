"""
test_canonical — canonicalize() is deterministic and matches RFC 8785 subset.
"""
import json
import unittest

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from dotpost.canonical import canonicalize


class TestCanonical(unittest.TestCase):
    def test_sorted_keys(self):
        """Keys are sorted lexicographically."""
        obj = {"z": 1, "a": 2, "m": 3}
        result = canonicalize(obj)
        parsed = json.loads(result)
        self.assertEqual(list(parsed.keys()), ["a", "m", "z"])

    def test_no_whitespace(self):
        """Output has no spaces or newlines."""
        obj = {"key": "value", "number": 42}
        result = canonicalize(obj).decode("utf-8")
        self.assertNotIn(" ", result)
        self.assertNotIn("\n", result)

    def test_utf8_encoding(self):
        """Output is valid UTF-8 bytes."""
        obj = {"emoji": "🚀", "unicode": "Ünïcödé"}
        result = canonicalize(obj)
        self.assertIsInstance(result, bytes)
        # Should decode without error.
        decoded = result.decode("utf-8")
        self.assertIn("🚀", decoded)

    def test_deterministic_same_input(self):
        """Same input always produces same bytes."""
        obj = {"b": [3, 1, 2], "a": {"nested": True}}
        r1 = canonicalize(obj)
        r2 = canonicalize(obj)
        self.assertEqual(r1, r2)

    def test_deterministic_different_key_order(self):
        """Dict key order does not affect output."""
        obj1 = {"a": 1, "b": 2}
        obj2 = {"b": 2, "a": 1}
        self.assertEqual(canonicalize(obj1), canonicalize(obj2))

    def test_nested_keys_sorted(self):
        """Nested dict keys are also sorted."""
        obj = {"outer": {"z": 99, "a": 1}}
        result = json.loads(canonicalize(obj))
        self.assertEqual(list(result["outer"].keys()), ["a", "z"])

    def test_test_vector(self):
        """Fixed test vector produces expected bytes (spec §6)."""
        obj = {"v": "1", "what": "test", "refuse_substitution": True}
        expected = b'{"refuse_substitution":true,"v":"1","what":"test"}'
        self.assertEqual(canonicalize(obj), expected)

    def test_empty_dict(self):
        """Empty dict serializes to '{}'."""
        self.assertEqual(canonicalize({}), b"{}")

    def test_list_preserved(self):
        """Lists maintain their order (not sorted)."""
        obj = {"items": [3, 1, 2]}
        result = json.loads(canonicalize(obj))
        self.assertEqual(result["items"], [3, 1, 2])


if __name__ == "__main__":
    unittest.main()
