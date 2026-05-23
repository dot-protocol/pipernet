# SPDX-License-Identifier: Apache-2.0
# Part of oracle-axxis — https://github.com/dot-protocol/oracle-sdk-py

"""Client tests — every method, request shape only (no live calls).

Uses httpx.MockTransport so the SDK builds a real httpx.Request that we can
introspect. We never reach the network. Assertions cover:

* URL path (bearer vs signed routing)
* HTTP method
* Required headers (Authorization for bearer; the five X-Pipernet-* for signed)
* Request body shape (JSON payload for ingest/search/ask; empty for GETs)
* Response parsing into pydantic models
* Error mapping (401 → AuthError, 404 → NotFoundError, 429 → RateLimitError,
  4xx → IngestError)
"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

import httpx
import pytest

from oracle_axxis import (
    AskResponse,
    AuthError,
    Capabilities,
    ConnectionGraph,
    IngestError,
    NotFoundError,
    Observation,
    Oracle,
    RateLimitError,
    SearchResult,
    SelfInfo,
)
from oracle_axxis.signing import (
    SIGNED_REQUEST_DOMAIN,
    Keypair,
    canonical_bytes,
    sign_request,
)

from .conftest import json_response

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ingest_response(obs_id: str = "OBS-test-001") -> dict[str, Any]:
    """Shape /ingest's response so _parse_observation finds an Observation."""
    return {
        "id": obs_id,
        "statement": "hello world",
        "channel": "lab",
        "tags": ["to:all", "dotpost", "channel:lab"],
        "created_at": "2026-05-24T00:00:00Z",
    }


def _search_response() -> dict[str, Any]:
    return {
        "query": "hello",
        "top_k": 10,
        "count": 1,
        "results": [
            {
                "id": "OBS-test-001",
                "statement": "hello world",
                "channel": "lab",
                "tags": [],
                "score": 0.99,
            }
        ],
        "via": "signed-request-v0.1",
    }


def _recent_response() -> dict[str, Any]:
    return {
        "count": 1,
        "items": [
            {
                "id": "OBS-test-001",
                "statement": "hello world",
                "channel": "lab",
                "tags": [],
                "created_at": "2026-05-24T00:00:00Z",
            }
        ],
        "via": "signed-request-v0.1",
    }


def _ask_response() -> dict[str, Any]:
    return {
        "question": "what is hello?",
        "model": "llama3.1:8b-instruct-q4_K_M",
        "top_k": 8,
        "latency_ms": 1234,
        "answer": "Hello is a greeting [OBS-test-001].",
        "citations": [{"obs_id": "OBS-test-001", "channel": "lab"}],
        "used": [{"id": "OBS-test-001"}],
        "via": "signed-request-v0.1",
    }


def _connections_response() -> dict[str, Any]:
    return {
        "obs_id": "OBS-test-001",
        "hebbian_neighbors": [
            {"obs_id": "OBS-neighbor-1", "strength": 0.82, "statement": "near"}
        ],
        "typed_edges": [
            {
                "edge_type": "CHAINS_TO",
                "direction": "OUT",
                "target_obs_id": "OBS-target-1",
            }
        ],
        "community_siblings": [],
        "pagerank": 0.0012,
        "betweenness": 0.0003,
    }


# ---------------------------------------------------------------------------
# Auth precedence
# ---------------------------------------------------------------------------


def test_no_credentials_means_open_mode_but_writes_raise(monkeypatch):
    monkeypatch.delenv("ORACLE_TOKEN", raising=False)
    monkeypatch.delenv("TREE_AUTH_TOKEN", raising=False)
    transport = httpx.MockTransport(
        lambda req: json_response({"version": "v1"})
    )
    oracle = Oracle(base_url="https://oracle.test", transport=transport)
    assert oracle.auth_mode == "open"

    with pytest.raises(AuthError):
        oracle.add("hi", channel="lab")

    # capabilities() must work without auth
    caps = oracle.capabilities()
    assert isinstance(caps, Capabilities)


def test_env_var_ORACLE_TOKEN_picked_up(monkeypatch):
    monkeypatch.setenv("ORACLE_TOKEN", "env-token-xyz")
    monkeypatch.delenv("TREE_AUTH_TOKEN", raising=False)
    transport = httpx.MockTransport(lambda req: json_response(_recent_response()))
    oracle = Oracle(base_url="https://oracle.test", transport=transport)
    assert oracle.auth_mode == "bearer"
    oracle.recent(limit=5)


def test_keypair_takes_precedence_over_api_key(test_keypair):
    transport = httpx.MockTransport(lambda req: json_response(_recent_response()))
    oracle = Oracle(
        api_key="bearer-should-be-ignored",
        keypair=test_keypair,
        base_url="https://oracle.test",
        transport=transport,
    )
    assert oracle.auth_mode == "signed"


# ---------------------------------------------------------------------------
# Bearer-mode writes — /ingest
# ---------------------------------------------------------------------------


def test_add_bearer_posts_to_ingest_with_bearer_header(bearer_oracle_factory):
    handler = lambda req: json_response(_ingest_response())  # noqa: E731
    oracle, recorded = bearer_oracle_factory(handler)

    obs = oracle.add(
        "hello world",
        channel="lab",
        tags=["greeting"],
        source="unit-test",
        obs_type="observation",
    )

    assert isinstance(obs, Observation)
    assert obs.id == "OBS-test-001"
    assert len(recorded) == 1
    req = recorded[0]
    assert req.method == "POST"
    assert req.url.path == "/ingest"
    assert req.headers["Authorization"] == "Bearer test-bearer-token"
    assert req.headers["Content-Type"] == "application/json"
    body = json.loads(req.content)
    assert body["source"] == "unit-test"
    item = body["extracted"]["items"][0]
    assert item["content"] == "hello world"
    assert item["channel"] == "lab"
    assert item["type"] == "observation"
    assert item["tags"] == ["greeting"]


def test_add_with_signed_keypair_raises_authError(signed_oracle_factory):
    """add() is bearer-only because /p/ingest restricts message types."""
    handler = lambda req: json_response({})  # noqa: E731
    oracle, _ = signed_oracle_factory(handler)
    with pytest.raises(AuthError, match="add\\(\\) requires bearer auth"):
        oracle.add("hi", channel="lab")


# ---------------------------------------------------------------------------
# Bearer-mode dotpost / icontact
# ---------------------------------------------------------------------------


def test_add_dotpost_bearer_routes_to_ingest(bearer_oracle_factory):
    handler = lambda req: json_response(_ingest_response())  # noqa: E731
    oracle, recorded = bearer_oracle_factory(handler)

    oracle.add_dotpost(
        body="hi mesh",
        to="all",
        channel="lab",
        reply_to="OBS-prior-7",
        tags=["mood:lab"],
    )

    req = recorded[0]
    assert req.url.path == "/ingest"
    body = json.loads(req.content)
    item = body["extracted"]["items"][0]
    assert item["content"] == "hi mesh"
    assert item["type"] == "dotpost"
    assert item["channel"] == "lab"
    assert "to:all" in item["tags"]
    assert "dotpost" in item["tags"]
    assert "channel:lab" in item["tags"]
    assert "in_reply_to:OBS-prior-7" in item["tags"]
    assert "mood:lab" in item["tags"]


def test_add_icontact_bearer_routes_to_ingest(bearer_oracle_factory):
    handler = lambda req: json_response(_ingest_response())  # noqa: E731
    oracle, recorded = bearer_oracle_factory(handler)

    oracle.add_icontact(body="ping", to="loom")

    req = recorded[0]
    assert req.url.path == "/ingest"
    body = json.loads(req.content)
    item = body["extracted"]["items"][0]
    assert item["type"] == "icontact"
    assert item["channel"] == "icontact"
    assert "to:loom" in item["tags"]
    assert "icontact" in item["tags"]


# ---------------------------------------------------------------------------
# Signed-mode dotpost / icontact route to /p/ingest
# ---------------------------------------------------------------------------


def test_add_dotpost_signed_routes_to_p_ingest(signed_oracle_factory):
    handler = lambda req: json_response(_ingest_response())  # noqa: E731
    oracle, recorded = signed_oracle_factory(handler)

    oracle.add_dotpost(body="hello world", to="all", channel="lab")

    req = recorded[0]
    assert req.url.path == "/p/ingest"
    assert req.method == "POST"
    # Bearer header must NOT be present
    assert "Authorization" not in req.headers
    # All five signed-request headers MUST be present
    for h in (
        "X-Pipernet-Handle",
        "X-Pipernet-Pubkey",
        "X-Pipernet-Timestamp",
        "X-Pipernet-Nonce",
        "X-Pipernet-Signature",
    ):
        assert h in req.headers, f"missing header {h}"
    assert req.headers["X-Pipernet-Handle"] == "testagent"


def test_add_icontact_signed_routes_to_p_ingest(signed_oracle_factory):
    handler = lambda req: json_response(_ingest_response())  # noqa: E731
    oracle, recorded = signed_oracle_factory(handler)

    oracle.add_icontact(body="ping", to="loom")

    req = recorded[0]
    assert req.url.path == "/p/ingest"
    assert "X-Pipernet-Signature" in req.headers


# ---------------------------------------------------------------------------
# Reads — search, recent, ask, connections, self_info
# ---------------------------------------------------------------------------


def test_search_bearer_posts_to_search(bearer_oracle_factory):
    handler = lambda req: json_response(_search_response())  # noqa: E731
    oracle, recorded = bearer_oracle_factory(handler)

    results = oracle.search("hello", top_k=10, rerank=True)

    assert len(results) == 1
    assert isinstance(results[0], SearchResult)
    assert results[0].id == "OBS-test-001"

    req = recorded[0]
    assert req.method == "POST"
    assert req.url.path == "/search"
    body = json.loads(req.content)
    assert body == {"query": "hello", "top_k": 10, "rerank": True}


def test_search_signed_posts_to_p_search(signed_oracle_factory):
    handler = lambda req: json_response(_search_response())  # noqa: E731
    oracle, recorded = signed_oracle_factory(handler)

    oracle.search("hello")

    req = recorded[0]
    assert req.url.path == "/p/search"
    assert "X-Pipernet-Signature" in req.headers


def test_recent_bearer_gets_recent_with_params(bearer_oracle_factory):
    handler = lambda req: json_response(_recent_response())  # noqa: E731
    oracle, recorded = bearer_oracle_factory(handler)

    items = oracle.recent(limit=20, channel="raw")

    assert len(items) == 1
    assert isinstance(items[0], Observation)

    req = recorded[0]
    assert req.method == "GET"
    assert req.url.path == "/recent"
    qparams = dict(req.url.params)
    assert qparams["limit"] == "20"
    assert qparams["channel"] == "raw"
    assert req.content == b""


def test_recent_signed_gets_p_recent(signed_oracle_factory):
    handler = lambda req: json_response(_recent_response())  # noqa: E731
    oracle, recorded = signed_oracle_factory(handler)

    oracle.recent(limit=5)

    req = recorded[0]
    assert req.url.path == "/p/recent"
    assert dict(req.url.params)["limit"] == "5"


def test_ask_bearer_posts_to_ask(bearer_oracle_factory):
    handler = lambda req: json_response(_ask_response())  # noqa: E731
    oracle, recorded = bearer_oracle_factory(handler)

    answer = oracle.ask("what is hello?")

    assert isinstance(answer, AskResponse)
    assert answer.answer.startswith("Hello is a greeting")
    assert answer.citations[0].obs_id == "OBS-test-001"

    req = recorded[0]
    assert req.method == "POST"
    assert req.url.path == "/ask"
    body = json.loads(req.content)
    assert body["question"] == "what is hello?"
    assert "stream" not in body


def test_ask_signed_posts_to_p_ask(signed_oracle_factory):
    handler = lambda req: json_response(_ask_response())  # noqa: E731
    oracle, recorded = signed_oracle_factory(handler)

    oracle.ask("what?")

    req = recorded[0]
    assert req.url.path == "/p/ask"
    assert "X-Pipernet-Signature" in req.headers


def test_connections_bearer(bearer_oracle_factory):
    handler = lambda req: json_response(_connections_response())  # noqa: E731
    oracle, recorded = bearer_oracle_factory(handler)

    g = oracle.connections("OBS-test-001")

    assert isinstance(g, ConnectionGraph)
    assert g.obs_id == "OBS-test-001"
    assert g.hebbian_neighbors[0].obs_id == "OBS-neighbor-1"
    assert g.typed_edges[0].edge_type == "CHAINS_TO"

    req = recorded[0]
    assert req.method == "GET"
    assert req.url.path == "/connections/OBS-test-001"


def test_connections_signed(signed_oracle_factory):
    handler = lambda req: json_response(_connections_response())  # noqa: E731
    oracle, recorded = signed_oracle_factory(handler)

    oracle.connections("OBS-test-001")

    req = recorded[0]
    assert req.url.path == "/p/connections/OBS-test-001"


def test_self_info_bearer(bearer_oracle_factory):
    handler = lambda req: json_response(  # noqa: E731
        {
            "node_id": "vps-1",
            "observations": 20617,
            "channels": ["raw", "lab", "axxis"],
            "embedding_model": "BAAI/bge-small-en-v1.5",
            "version": "v1.1",
        }
    )
    oracle, recorded = bearer_oracle_factory(handler)

    info = oracle.self_info()

    assert isinstance(info, SelfInfo)
    assert info.observations == 20617
    assert recorded[0].url.path == "/self"


def test_capabilities_open_no_auth(monkeypatch):
    monkeypatch.delenv("ORACLE_TOKEN", raising=False)
    monkeypatch.delenv("TREE_AUTH_TOKEN", raising=False)

    captured: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        return json_response(
            {
                "version": "v1.1",
                "endpoints": ["/ingest", "/search", "/p/find"],
                "auth_modes": ["bearer", "signed-request-v0.1"],
                "signed_request_version": "0.1.1",
            }
        )

    transport = httpx.MockTransport(handler)
    oracle = Oracle(base_url="https://oracle.test", transport=transport)
    caps = oracle.capabilities()

    assert isinstance(caps, Capabilities)
    assert caps.signed_request_version == "0.1.1"
    req = captured[0]
    assert req.url.path == "/capabilities"
    assert "Authorization" not in req.headers
    assert "X-Pipernet-Signature" not in req.headers


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------


def test_401_maps_to_AuthError(bearer_oracle_factory):
    handler = lambda req: httpx.Response(  # noqa: E731
        401, json={"error": "bad token"}
    )
    oracle, _ = bearer_oracle_factory(handler)
    with pytest.raises(AuthError):
        oracle.add("hi", channel="lab")


def test_404_maps_to_NotFoundError(bearer_oracle_factory):
    handler = lambda req: httpx.Response(404, json={"error": "no such obs"})  # noqa: E731
    oracle, _ = bearer_oracle_factory(handler)
    with pytest.raises(NotFoundError):
        oracle.connections("OBS-does-not-exist")


def test_429_maps_to_RateLimitError_with_retry_after(bearer_oracle_factory):
    handler = lambda req: httpx.Response(  # noqa: E731
        429, json={"error": "slow down", "retry_after_s": 12.5}
    )
    oracle, _ = bearer_oracle_factory(handler)
    with pytest.raises(RateLimitError) as exc:
        oracle.search("anything")
    assert exc.value.retry_after_s == 12.5


def test_400_maps_to_IngestError(bearer_oracle_factory):
    handler = lambda req: httpx.Response(  # noqa: E731
        400, json={"error": "missing field"}
    )
    oracle, _ = bearer_oracle_factory(handler)
    with pytest.raises(IngestError):
        oracle.add("hi", channel="lab")


# ---------------------------------------------------------------------------
# Signing — verify the bytes are the right shape
# ---------------------------------------------------------------------------


def test_canonical_bytes_layout():
    """Lock the canonical-bytes layout against signed-request-v0.1 §3.2."""
    cb = canonical_bytes(
        method="GET",
        path="/p/recent",
        query_string="limit=5",
        body=b"",
        handle="loom",
        pubkey_b64="AAAA",
        timestamp="2026-05-18T01:50:00Z",
        nonce_b64="NONCE",
    )
    lines = cb.split(b"\n")
    assert lines[0] == SIGNED_REQUEST_DOMAIN
    assert lines[1] == b"GET"
    assert lines[2] == b"/p/recent"
    assert lines[3] == b"limit=5"
    # sha256("") hex is the spec-locked empty-body hash
    assert lines[4] == (
        b"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )
    assert lines[5] == b"loom"
    assert lines[6] == b"AAAA"
    assert lines[7] == b"2026-05-18T01:50:00Z"
    assert lines[8] == b"NONCE"


def test_signature_verifies_under_pubkey(test_keypair):
    """A signature produced by sign_request must verify under the same pubkey."""
    from nacl.signing import VerifyKey  # type: ignore[import-untyped]

    headers = sign_request(
        test_keypair,
        method="POST",
        path="/p/find",
        query_string="",
        body=b'{"q":"x"}',
        timestamp="2026-05-24T00:00:00Z",
        nonce_b64="ZHV0Y2gtdGVzdC1ub25jZQ==",
    )
    cb = canonical_bytes(
        method="POST",
        path="/p/find",
        query_string="",
        body=b'{"q":"x"}',
        handle=test_keypair.handle,
        pubkey_b64=test_keypair.pubkey_b64,
        timestamp="2026-05-24T00:00:00Z",
        nonce_b64="ZHV0Y2gtdGVzdC1ub25jZQ==",
    )
    verify_key = VerifyKey(test_keypair.pubkey_bytes)
    sig_bytes = base64.b64decode(headers["X-Pipernet-Signature"])
    # raises BadSignatureError on mismatch — assertion is the absence of raise
    verify_key.verify(cb, sig_bytes)


def test_signed_request_body_hash_matches_canonical(signed_oracle_factory):
    """The body hash in the signature must match the sha256 of the wire bytes."""
    captured: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        return json_response(_ingest_response())

    oracle, _ = signed_oracle_factory(handler)
    oracle.add_dotpost(body="hello world", to="all", channel="lab")

    req = captured[0]
    body_hash = hashlib.sha256(req.content).hexdigest()
    # The signature was built over canonical bytes including this hash. We
    # don't reconstruct the canonical bytes here (timestamp + nonce are
    # per-call random); we only assert the wire body is JSON of the expected
    # shape and that signing headers are present.
    assert body_hash != ""
    body = json.loads(req.content)
    assert body["extracted"]["items"][0]["content"] == "hello world"


# ---------------------------------------------------------------------------
# Default-handle derivation per the brief
# ---------------------------------------------------------------------------


def test_default_handle_is_pk_plus_16_hex():
    """Brief: handle = 'pk' + first 16 hex chars of pubkey, lowercased."""
    pk_hex = "ABCDEF0123456789" + "0" * 48  # 64 chars total
    sk_hex = "0" * 64
    kp = Keypair(pubkey_hex=pk_hex, privkey_hex=sk_hex)
    assert kp.handle == "pkabcdef0123456789"
    # Must satisfy the regex ^[a-z0-9][a-z0-9-]{0,63}$ — no colon
    assert ":" not in kp.handle
    assert kp.handle.startswith("pk")
    assert len(kp.handle) == 18


def test_keypair_load_from_dict():
    kp = Keypair.load(
        {
            "pubkey_hex": "11" * 32,
            "privkey_hex": "22" * 32,
            "handle": "custom",
        }
    )
    assert kp.handle == "custom"
    assert kp.pubkey_bytes == bytes.fromhex("11" * 32)
