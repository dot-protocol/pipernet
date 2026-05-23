# SPDX-License-Identifier: Apache-2.0
# Part of oracle-axxis — https://github.com/dot-protocol/oracle-sdk-py

"""oracle_axxis.types — Pydantic v2 data models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Observation(BaseModel):
    """A single knowledge observation stored in Oracle."""

    id: str
    statement: str
    channel: str = "raw"
    tags: list[str] = Field(default_factory=list)
    created_at: str | None = None
    source: str | None = None
    type: str | None = None
    confidence: str | None = None
    evidence: str | None = None

    model_config = {"extra": "allow"}


class SearchResult(BaseModel):
    """An observation returned from a search, with a relevance score."""

    id: str
    statement: str
    channel: str = "raw"
    tags: list[str] = Field(default_factory=list)
    created_at: str | None = None
    source: str | None = None
    type: str | None = None
    confidence: str | None = None
    evidence: str | None = None
    score: float = 0.0

    model_config = {"extra": "allow"}


class Citation(BaseModel):
    """A cited observation in an AskResponse."""

    obs_id: str
    channel: str | None = None
    ts: str | None = None
    statement: str | None = None

    model_config = {"extra": "allow"}


class AskResponse(BaseModel):
    """Response from the /ask or /p/ask RAG endpoint."""

    question: str
    answer: str
    model: str | None = None
    top_k: int | None = None
    latency_ms: float | None = None
    citations: list[Citation] = Field(default_factory=list)
    used: list[dict[str, Any]] = Field(default_factory=list)
    via: str | None = None

    model_config = {"extra": "allow"}


class HebbianNeighbor(BaseModel):
    """A Hebbian-related observation."""

    obs_id: str
    strength: float = 0.0
    statement: str | None = None

    model_config = {"extra": "allow"}


class TypedEdge(BaseModel):
    """A typed relationship edge from an observation."""

    edge_type: str
    direction: str  # "OUT" or "IN"
    target_obs_id: str
    statement: str | None = None

    model_config = {"extra": "allow"}


class CommunitySibling(BaseModel):
    """An observation in the same Louvain community."""

    obs_id: str
    statement: str | None = None

    model_config = {"extra": "allow"}


class ConnectionGraph(BaseModel):
    """Graph neighbourhood for a single observation from /connections/<obs_id>."""

    obs_id: str
    hebbian_neighbors: list[HebbianNeighbor] = Field(default_factory=list)
    typed_edges: list[TypedEdge] = Field(default_factory=list)
    community_siblings: list[CommunitySibling] = Field(default_factory=list)
    pagerank: float | None = None
    betweenness: float | None = None

    model_config = {"extra": "allow"}


class SelfInfo(BaseModel):
    """Server self-report from /self (bearer) or /p/self (signed)."""

    node_id: str | None = None
    observations: int | None = None
    channels: list[str] = Field(default_factory=list)
    embedding_model: str | None = None
    version: str | None = None

    model_config = {"extra": "allow"}


class Capabilities(BaseModel):
    """Server capability report from /capabilities (no auth required)."""

    version: str | None = None
    endpoints: list[str] = Field(default_factory=list)
    auth_modes: list[str] = Field(default_factory=list)
    signed_request_version: str | None = None

    model_config = {"extra": "allow"}
