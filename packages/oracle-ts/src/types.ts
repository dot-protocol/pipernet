// SPDX-License-Identifier: Apache-2.0
// Part of @axxis/oracle — https://github.com/dot-protocol/oracle-sdk-ts

import { z } from 'zod';

/**
 * Runtime-validation schemas. Server responses are parsed through these via
 * `.passthrough()` so we keep any extra fields the server returns while still
 * type-narrowing the documented ones.
 */

export const ObservationSchema = z
  .object({
    id: z.string(),
    statement: z.string(),
    channel: z.string().default('raw'),
    tags: z.array(z.string()).default([]),
    created_at: z.string().nullable().optional(),
    source: z.string().nullable().optional(),
    type: z.string().nullable().optional(),
    confidence: z.string().nullable().optional(),
    evidence: z.string().nullable().optional(),
  })
  .passthrough();

export const SearchResultSchema = ObservationSchema.extend({
  score: z.number().default(0),
}).passthrough();

export const CitationSchema = z
  .object({
    obs_id: z.string(),
    channel: z.string().nullable().optional(),
    ts: z.string().nullable().optional(),
    statement: z.string().nullable().optional(),
  })
  .passthrough();

export const AskResponseSchema = z
  .object({
    question: z.string(),
    answer: z.string(),
    model: z.string().nullable().optional(),
    top_k: z.number().int().nullable().optional(),
    latency_ms: z.number().nullable().optional(),
    citations: z.array(CitationSchema).default([]),
    used: z.array(z.record(z.unknown())).default([]),
    via: z.string().nullable().optional(),
  })
  .passthrough();

export const HebbianNeighborSchema = z
  .object({
    obs_id: z.string(),
    strength: z.number().default(0),
    statement: z.string().nullable().optional(),
  })
  .passthrough();

export const TypedEdgeSchema = z
  .object({
    edge_type: z.string(),
    direction: z.enum(['OUT', 'IN']),
    target_obs_id: z.string(),
    statement: z.string().nullable().optional(),
  })
  .passthrough();

export const CommunitySiblingSchema = z
  .object({
    obs_id: z.string(),
    statement: z.string().nullable().optional(),
  })
  .passthrough();

export const ConnectionGraphSchema = z
  .object({
    obs_id: z.string(),
    hebbian_neighbors: z.array(HebbianNeighborSchema).default([]),
    typed_edges: z.array(TypedEdgeSchema).default([]),
    community_siblings: z.array(CommunitySiblingSchema).default([]),
    pagerank: z.number().nullable().optional(),
    betweenness: z.number().nullable().optional(),
  })
  .passthrough();

export const SelfInfoSchema = z
  .object({
    node_id: z.string().nullable().optional(),
    observations: z.number().int().nullable().optional(),
    channels: z.array(z.string()).default([]),
    embedding_model: z.string().nullable().optional(),
    version: z.string().nullable().optional(),
  })
  .passthrough();

export const CapabilitiesSchema = z
  .object({
    version: z.string().nullable().optional(),
    endpoints: z.array(z.string()).default([]),
    auth_modes: z.array(z.string()).default([]),
    signed_request_version: z.string().nullable().optional(),
  })
  .passthrough();

// Inferred TypeScript types — what callers see at compile time.

export type Observation = z.infer<typeof ObservationSchema>;
export type SearchResult = z.infer<typeof SearchResultSchema>;
export type Citation = z.infer<typeof CitationSchema>;
export type AskResponse = z.infer<typeof AskResponseSchema>;
export type HebbianNeighbor = z.infer<typeof HebbianNeighborSchema>;
export type TypedEdge = z.infer<typeof TypedEdgeSchema>;
export type CommunitySibling = z.infer<typeof CommunitySiblingSchema>;
export type ConnectionGraph = z.infer<typeof ConnectionGraphSchema>;
export type SelfInfo = z.infer<typeof SelfInfoSchema>;
export type Capabilities = z.infer<typeof CapabilitiesSchema>;

/** A loaded Ed25519 keypair, both halves hex-encoded. */
export interface Keypair {
  /** 32-byte Ed25519 public key, hex (64 chars). */
  pubkeyHex: string;
  /** 32-byte Ed25519 private key (seed), hex (64 chars). */
  privkeyHex: string;
}

/**
 * Namespace export for callers who want to validate untrusted payloads at
 * runtime — e.g. `schemas.Observation.parse(raw)`.
 */
export const schemas = {
  Observation: ObservationSchema,
  SearchResult: SearchResultSchema,
  Citation: CitationSchema,
  AskResponse: AskResponseSchema,
  HebbianNeighbor: HebbianNeighborSchema,
  TypedEdge: TypedEdgeSchema,
  CommunitySibling: CommunitySiblingSchema,
  ConnectionGraph: ConnectionGraphSchema,
  SelfInfo: SelfInfoSchema,
  Capabilities: CapabilitiesSchema,
} as const;
