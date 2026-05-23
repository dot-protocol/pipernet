// SPDX-License-Identifier: Apache-2.0
// Part of @axxis/oracle — https://github.com/dot-protocol/oracle-sdk-ts

/**
 * Base class for all Oracle SDK errors.
 *
 * Mirrors the Python `oracle_axxis.errors.OracleError` exception.
 */
export class OracleError extends Error {
  readonly statusCode: number | undefined;

  constructor(message: string, opts?: { statusCode?: number; cause?: unknown }) {
    super(message, opts?.cause !== undefined ? { cause: opts.cause } : undefined);
    this.name = 'OracleError';
    this.statusCode = opts?.statusCode;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/**
 * Raised when authentication fails or no credentials are provided.
 *
 * HTTP equivalents: 401 bad_signature, and any time no credentials exist.
 */
export class AuthError extends OracleError {
  constructor(message: string, opts?: { statusCode?: number; cause?: unknown }) {
    super(message, opts);
    this.name = 'AuthError';
    Object.setPrototypeOf(this, AuthError.prototype);
  }
}

/**
 * Raised when the per-pubkey rate limit (60 reads/min) is exceeded.
 *
 * HTTP equivalent: 429 rate_limit.
 * The `retryAfterS` field carries the server-suggested wait time in seconds.
 */
export class RateLimitError extends OracleError {
  readonly retryAfterS: number | undefined;

  constructor(message: string, opts?: { retryAfterS?: number; cause?: unknown }) {
    super(message, { statusCode: 429, ...(opts?.cause !== undefined ? { cause: opts.cause } : {}) });
    this.name = 'RateLimitError';
    this.retryAfterS = opts?.retryAfterS;
    Object.setPrototypeOf(this, RateLimitError.prototype);
  }
}

/**
 * Raised when an observation could not be ingested.
 *
 * HTTP equivalent: 400 bad_request or any 4xx on `/ingest` / `/p/ingest`.
 */
export class IngestError extends OracleError {
  constructor(message: string, opts?: { statusCode?: number; cause?: unknown }) {
    super(message, opts);
    this.name = 'IngestError';
    Object.setPrototypeOf(this, IngestError.prototype);
  }
}

/**
 * Raised when a requested resource (observation, connection graph) is missing.
 *
 * HTTP equivalent: 404 not_found.
 */
export class NotFoundError extends OracleError {
  constructor(message = 'not found', opts?: { cause?: unknown }) {
    super(message, { statusCode: 404, ...(opts?.cause !== undefined ? { cause: opts.cause } : {}) });
    this.name = 'NotFoundError';
    Object.setPrototypeOf(this, NotFoundError.prototype);
  }
}
