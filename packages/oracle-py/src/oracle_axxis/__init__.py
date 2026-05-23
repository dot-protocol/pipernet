# SPDX-License-Identifier: Apache-2.0
# Part of oracle-axxis — https://github.com/dot-protocol/oracle-sdk-py

"""oracle-axxis — Python SDK for Oracle (https://oracle.axxis.world).

Mem0-shaped surface (``add()``, ``search()``) for the bearer-auth path; a
constrained write surface (``add_dotpost()``, ``add_icontact()``) for the
public signed-request path. ``ask()`` is the dialog primitive — RAG over
Oracle with inline citations. ``connections()`` returns the Hebbian +
typed-edge + community neighbourhood for any observation.

Hello world::

    from oracle_axxis import Oracle

    oracle = Oracle(keypair="key.json")
    oracle.add_dotpost(body="hello world", to="all", channel="lab")
    results = oracle.search("hello")
    print(results[0].statement)
"""

from __future__ import annotations

from .client import AsyncOracle, Oracle
from .errors import (
    AuthError,
    IngestError,
    NotFoundError,
    OracleError,
    RateLimitError,
)
from .signing import Keypair, canonical_bytes, sign_request
from .types import (
    AskResponse,
    Capabilities,
    Citation,
    CommunitySibling,
    ConnectionGraph,
    HebbianNeighbor,
    Observation,
    SearchResult,
    SelfInfo,
    TypedEdge,
)

__version__ = "0.1.0"

__all__ = [
    # Clients
    "Oracle",
    "AsyncOracle",
    # Auth
    "Keypair",
    "canonical_bytes",
    "sign_request",
    # Types
    "Observation",
    "SearchResult",
    "AskResponse",
    "Citation",
    "ConnectionGraph",
    "HebbianNeighbor",
    "TypedEdge",
    "CommunitySibling",
    "SelfInfo",
    "Capabilities",
    # Errors
    "OracleError",
    "AuthError",
    "RateLimitError",
    "IngestError",
    "NotFoundError",
    # Version
    "__version__",
]
