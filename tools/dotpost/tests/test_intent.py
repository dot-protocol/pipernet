"""
test_intent — Intent.to_canonical_bytes() is stable; sign/verify round-trip.
"""
import unittest

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from dotpost.intent import Intent, Resolve, _utcnow_iso
from dotpost.canonical import canonicalize
from dotpost.identity import sign, verify


def _new_key() -> tuple[Ed25519PrivateKey, bytes]:
    """Generate a fresh keypair for testing."""
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return priv, pub


class TestIntent(unittest.TestCase):
    def _make_intent(self, **kwargs) -> Intent:
        defaults = {"what": "Translate doc to French"}
        defaults.update(kwargs)
        return Intent(**defaults)

    def test_minimal_intent(self):
        intent = self._make_intent()
        self.assertEqual(intent.what, "Translate doc to French")
        self.assertTrue(intent.refuse_substitution)  # default True
        self.assertEqual(intent.v, "1")

    def test_what_required(self):
        with self.assertRaises(ValueError):
            Intent(what="")

    def test_invalid_version(self):
        with self.assertRaises(ValueError):
            Intent(what="test", v="2")

    def test_invalid_expires_at(self):
        with self.assertRaises(ValueError):
            Intent(what="test", expires_at="not-a-date")

    def test_canonical_bytes_stable(self):
        """Same intent produces identical canonical bytes on multiple calls."""
        intent = self._make_intent(
            what="Build a dashboard",
            values=["privacy", "open_source"],
            constraints={"budget_max_usd": 500},
            expires_at="2026-06-01T00:00:00Z",
        )
        b1 = intent.to_canonical_bytes()
        b2 = intent.to_canonical_bytes()
        self.assertEqual(b1, b2)

    def test_canonical_bytes_key_order(self):
        """Canonical bytes have sorted keys regardless of dict insertion order."""
        import json
        intent = self._make_intent(
            constraints={"z_key": 1, "a_key": 2},
        )
        raw = json.loads(intent.to_canonical_bytes())
        if "constraints" in raw:
            self.assertEqual(list(raw["constraints"].keys()), sorted(raw["constraints"].keys()))

    def test_sign_verify_round_trip(self):
        """Sign then verify returns True with matching pubkey."""
        priv, pub = _new_key()
        intent = self._make_intent(what="Design a landing page")
        intent_b64, sig_b64 = intent.sign(priv)
        self.assertTrue(intent.verify(pub, intent_b64, sig_b64))

    def test_verify_wrong_pubkey_fails(self):
        """Verify fails with a different key."""
        priv1, _ = _new_key()
        _, pub2 = _new_key()
        intent = self._make_intent(what="Wrong key test")
        intent_b64, sig_b64 = intent.sign(priv1)
        self.assertFalse(intent.verify(pub2, intent_b64, sig_b64))

    def test_verify_tampered_payload_fails(self):
        """Verify fails if intent_b64 is changed after signing."""
        priv, pub = _new_key()
        intent = self._make_intent(what="Tamper test")
        intent_b64, sig_b64 = intent.sign(priv)
        # Tamper: replace b64 with different content.
        import base64
        tampered_obj = {"v": "1", "what": "TAMPERED", "refuse_substitution": True, "addressed_to": "all"}
        tampered_b64 = base64.urlsafe_b64encode(
            canonicalize(tampered_obj)
        ).rstrip(b"=").decode("ascii")
        self.assertFalse(intent.verify(pub, tampered_b64, sig_b64))

    def test_from_b64_round_trip(self):
        """Intent.from_b64 reconstructs the intent faithfully."""
        priv, _ = _new_key()
        intent = self._make_intent(
            what="Round-trip test",
            values=["privacy"],
            expires_at="2026-12-31T00:00:00Z",
        )
        intent_b64, _ = intent.sign(priv)
        recovered = Intent.from_b64(intent_b64)
        self.assertEqual(recovered.what, intent.what)
        self.assertEqual(recovered.values, intent.values)
        self.assertEqual(recovered.expires_at, intent.expires_at)
        self.assertEqual(recovered.to_canonical_bytes(), intent.to_canonical_bytes())

    def test_to_dict_excludes_empty_optional_fields(self):
        """to_dict() omits empty constraints/values/context_refs."""
        intent = self._make_intent(what="Simple intent")
        d = intent.to_dict()
        self.assertNotIn("constraints", d)
        self.assertNotIn("values", d)
        self.assertNotIn("context_refs", d)


class TestResolve(unittest.TestCase):
    def _make_resolve(self, **kwargs) -> Resolve:
        defaults = {
            "intent_id": "OBS-test-intent-1",
            "honored": True,
            "resolver": "baran",
            "resolved_at": "2026-05-13T11:00:00Z",
        }
        defaults.update(kwargs)
        return Resolve(**defaults)

    def test_minimal_resolve(self):
        resolve = self._make_resolve()
        self.assertEqual(resolve.intent_id, "OBS-test-intent-1")
        self.assertTrue(resolve.honored)
        self.assertEqual(resolve.resolver, "baran")

    def test_intent_id_required(self):
        with self.assertRaises(ValueError):
            Resolve(intent_id="", honored=True, resolver="baran",
                    resolved_at="2026-05-13T11:00:00Z")

    def test_deviation_required_when_refused(self):
        with self.assertRaises(ValueError):
            self._make_resolve(honored=False, deviation=None)

    def test_deviation_required_when_partial(self):
        with self.assertRaises(ValueError):
            self._make_resolve(honored="partial", deviation=None)

    def test_deviation_not_required_when_honored(self):
        r = self._make_resolve(honored=True)
        self.assertIsNone(r.deviation)

    def test_invalid_honored_value(self):
        with self.assertRaises(ValueError):
            self._make_resolve(honored="maybe")

    def test_invalid_resolved_at(self):
        with self.assertRaises(ValueError):
            self._make_resolve(resolved_at="bad-date")

    def test_sign_verify_round_trip(self):
        priv, pub = _new_key()
        resolve = self._make_resolve()
        resolve_b64, sig_b64 = resolve.sign(priv)
        self.assertTrue(resolve.verify(pub, resolve_b64, sig_b64))

    def test_partial_sign_verify(self):
        priv, pub = _new_key()
        resolve = self._make_resolve(
            honored="partial",
            deviation="Delivered Monday instead of Friday",
        )
        resolve_b64, sig_b64 = resolve.sign(priv)
        self.assertTrue(resolve.verify(pub, resolve_b64, sig_b64))

    def test_canonical_bytes_stable(self):
        resolve = self._make_resolve()
        b1 = resolve.to_canonical_bytes()
        b2 = resolve.to_canonical_bytes()
        self.assertEqual(b1, b2)

    def test_partial_as_string_in_honored(self):
        """'partial' string value is accepted."""
        resolve = self._make_resolve(honored="partial", deviation="Some constraint missed")
        d = resolve.to_dict()
        self.assertEqual(d["honored"], "partial")

    def test_false_in_honored(self):
        """False bool value is preserved."""
        resolve = self._make_resolve(honored=False, deviation="Could not fulfill")
        d = resolve.to_dict()
        self.assertFalse(d["honored"])


class TestCompressedIntent(unittest.TestCase):
    """v0.5.0 compressed sign/verify for Intent."""

    def _make_intent(self, **kwargs) -> Intent:
        defaults = {"what": "Ship the landing page by Friday"}
        defaults.update(kwargs)
        return Intent(**defaults)

    def test_compressed_roundtrip(self):
        """to_compressed_b64 + from_compressed_b64 recovers identical Intent."""
        priv, _ = _new_key()
        intent = self._make_intent(values=["privacy"], expires_at="2026-12-31T00:00:00Z")
        comp_b64, _ = intent.to_compressed_b64(priv)
        recovered = Intent.from_compressed_b64(comp_b64)
        self.assertEqual(recovered.what, intent.what)
        self.assertEqual(recovered.values, intent.values)
        self.assertEqual(recovered.expires_at, intent.expires_at)
        self.assertEqual(recovered.to_canonical_bytes(), intent.to_canonical_bytes())

    def test_verify_compressed_valid(self):
        """verify_compressed returns True with correct pubkey."""
        priv, pub = _new_key()
        intent = self._make_intent(what="Compressed verify test")
        comp_b64, sig_b64 = intent.to_compressed_b64(priv)
        self.assertTrue(Intent.verify_compressed(comp_b64, sig_b64, pub))

    def test_verify_compressed_wrong_key_fails(self):
        """verify_compressed returns False with a different pubkey."""
        priv1, _ = _new_key()
        _, pub2 = _new_key()
        intent = self._make_intent(what="Wrong key compressed")
        comp_b64, sig_b64 = intent.to_compressed_b64(priv1)
        self.assertFalse(Intent.verify_compressed(comp_b64, sig_b64, pub2))

    def test_compressed_sig_is_over_canonical_not_compressed(self):
        """The sig from to_compressed_b64 verifies against canonical bytes (not compressed)."""
        from dotpost.compression import decompress
        from dotpost.identity import verify
        import base64
        priv, pub = _new_key()
        intent = self._make_intent(what="Sig is over canonical")
        comp_b64, sig_b64 = intent.to_compressed_b64(priv)
        # Manually decompress and verify against canonical bytes
        padding = 4 - len(comp_b64) % 4
        if padding != 4:
            comp_b64_padded = comp_b64 + "=" * padding
        else:
            comp_b64_padded = comp_b64
        compressed = base64.urlsafe_b64decode(comp_b64_padded)
        canonical = decompress(compressed)
        sig = base64.urlsafe_b64decode(sig_b64 + "=" * (4 - len(sig_b64) % 4))
        self.assertTrue(verify(pub, sig, canonical))
        # Sig does NOT verify directly against compressed bytes
        self.assertFalse(verify(pub, sig, compressed))


class TestCompressedResolve(unittest.TestCase):
    """v0.5.0 compressed sign/verify for Resolve."""

    def _make_resolve(self, **kwargs) -> Resolve:
        defaults = {
            "intent_id": "OBS-test-intent-comp-1",
            "honored": True,
            "resolver": "baran",
            "resolved_at": "2026-05-13T11:00:00Z",
        }
        defaults.update(kwargs)
        return Resolve(**defaults)

    def test_compressed_roundtrip(self):
        """to_compressed_b64 + from_compressed_b64 recovers identical Resolve."""
        priv, _ = _new_key()
        resolve = self._make_resolve()
        comp_b64, _ = resolve.to_compressed_b64(priv)
        recovered = Resolve.from_compressed_b64(comp_b64)
        self.assertEqual(recovered.intent_id, resolve.intent_id)
        self.assertEqual(recovered.resolver, resolve.resolver)
        self.assertEqual(recovered.to_canonical_bytes(), resolve.to_canonical_bytes())

    def test_verify_compressed_valid(self):
        """verify_compressed returns True with correct pubkey."""
        priv, pub = _new_key()
        resolve = self._make_resolve()
        comp_b64, sig_b64 = resolve.to_compressed_b64(priv)
        self.assertTrue(Resolve.verify_compressed(comp_b64, sig_b64, pub))

    def test_verify_compressed_wrong_key_fails(self):
        """verify_compressed returns False with a different pubkey."""
        priv1, _ = _new_key()
        _, pub2 = _new_key()
        resolve = self._make_resolve()
        comp_b64, sig_b64 = resolve.to_compressed_b64(priv1)
        self.assertFalse(Resolve.verify_compressed(comp_b64, sig_b64, pub2))

    def test_partial_compressed_roundtrip(self):
        """Partial resolve with deviation survives compressed roundtrip."""
        priv, pub = _new_key()
        resolve = self._make_resolve(honored="partial", deviation="Missed deadline by 1 day")
        comp_b64, sig_b64 = resolve.to_compressed_b64(priv)
        self.assertTrue(Resolve.verify_compressed(comp_b64, sig_b64, pub))
        recovered = Resolve.from_compressed_b64(comp_b64)
        self.assertEqual(recovered.deviation, "Missed deadline by 1 day")


class TestIdentitySignVerify(unittest.TestCase):
    def test_sign_verify(self):
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        priv = Ed25519PrivateKey.generate()
        pub = priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        data = b"hello world canonical bytes"
        sig = sign(priv, data)
        self.assertTrue(verify(pub, sig, data))

    def test_verify_wrong_data_fails(self):
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        priv = Ed25519PrivateKey.generate()
        pub = priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        sig = sign(priv, b"correct data")
        self.assertFalse(verify(pub, sig, b"tampered data"))


if __name__ == "__main__":
    unittest.main()
