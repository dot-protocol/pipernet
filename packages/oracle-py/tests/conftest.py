# SPDX-License-Identifier: Apache-2.0
# Part of oracle-axxis — https://github.com/dot-protocol/oracle-sdk-py

"""Test fixtures — deterministic keypair + httpx MockTransport plumbing."""

from __future__ import annotations

from typing import Any, Callable

import httpx
import pytest

from oracle_axxis import Oracle
from oracle_axxis.signing import Keypair

# Fixed 32-byte seed → deterministic Ed25519 keypair. The pubkey is derived
# inside the fixture so tests don't have to hardcode it; PyNaCl computes it
# from the seed at fixture time.
TEST_SEED_HEX = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"


@pytest.fixture
def test_keypair() -> Keypair:
    """Deterministic Ed25519 keypair for reproducible signature assertions."""
    from nacl.signing import SigningKey  # type: ignore[import-untyped]

    seed = bytes.fromhex(TEST_SEED_HEX)
    sk = SigningKey(seed)
    pubkey_hex = bytes(sk.verify_key).hex()
    return Keypair(
        pubkey_hex=pubkey_hex,
        privkey_hex=TEST_SEED_HEX,
        handle="testagent",
    )


Recorder = list[httpx.Request]


def make_mock_transport(
    handler: Callable[[httpx.Request], httpx.Response],
) -> tuple[httpx.MockTransport, Recorder]:
    """Build a MockTransport that records every request before delegating."""
    recorded: Recorder = []

    def _wrapped(request: httpx.Request) -> httpx.Response:
        recorded.append(request)
        return handler(request)

    return httpx.MockTransport(_wrapped), recorded


def json_response(payload: Any, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, json=payload)


@pytest.fixture
def bearer_oracle_factory() -> Callable[..., tuple[Oracle, Recorder]]:
    """Factory: returns (Oracle, recorded-requests) for bearer-auth tests."""

    def _factory(
        handler: Callable[[httpx.Request], httpx.Response],
        *,
        api_key: str = "test-bearer-token",
        base_url: str = "https://oracle.test",
    ) -> tuple[Oracle, Recorder]:
        transport, recorded = make_mock_transport(handler)
        client = Oracle(api_key=api_key, base_url=base_url, transport=transport)
        return client, recorded

    return _factory


@pytest.fixture
def signed_oracle_factory(
    test_keypair: Keypair,
) -> Callable[..., tuple[Oracle, Recorder]]:
    """Factory: returns (Oracle, recorded-requests) for signed-auth tests."""

    def _factory(
        handler: Callable[[httpx.Request], httpx.Response],
        *,
        base_url: str = "https://oracle.test",
    ) -> tuple[Oracle, Recorder]:
        transport, recorded = make_mock_transport(handler)
        client = Oracle(keypair=test_keypair, base_url=base_url, transport=transport)
        return client, recorded

    return _factory
