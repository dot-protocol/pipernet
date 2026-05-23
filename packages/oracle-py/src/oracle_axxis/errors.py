# SPDX-License-Identifier: Apache-2.0
# Part of oracle-axxis — https://github.com/dot-protocol/oracle-sdk-py

"""oracle_axxis.errors — exception hierarchy."""

from __future__ import annotations


class OracleError(Exception):
    """Base class for all oracle_axxis errors."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class AuthError(OracleError):
    """Raised when authentication fails or no credentials are provided.

    HTTP equivalents: 401 bad_signature, and any time no credentials exist.
    """


class RateLimitError(OracleError):
    """Raised when the per-pubkey rate limit (60 reads/min) is exceeded.

    HTTP equivalent: 429 rate_limit.
    The ``retry_after_s`` attribute carries the server-suggested wait time.
    """

    def __init__(self, message: str, *, retry_after_s: float | None = None) -> None:
        super().__init__(message, status_code=429)
        self.retry_after_s = retry_after_s


class IngestError(OracleError):
    """Raised when an observation could not be ingested.

    HTTP equivalent: 400 bad_request or any 4xx on /ingest / /p/ingest.
    """


class NotFoundError(OracleError):
    """Raised when a requested resource (observation, connection graph) is missing.

    HTTP equivalent: 404 not_found.
    """

    def __init__(self, message: str = "not found") -> None:
        super().__init__(message, status_code=404)
