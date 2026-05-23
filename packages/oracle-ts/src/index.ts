// SPDX-License-Identifier: Apache-2.0
// Part of @axxis/oracle — https://github.com/dot-protocol/oracle-sdk-ts

/**
 * @axxis/oracle — TypeScript SDK for Oracle, the Kin knowledge graph.
 *
 * Hello-world:
 * ```ts
 * import { Oracle, loadKeypair } from '@axxis/oracle';
 *
 * const oracle = new Oracle({ keypair: loadKeypair('key.json') });
 * await oracle.addDotpost({ body: 'Rocky shipped /p/ingest today', to: 'all', channel: 'lab' });
 * const results = await oracle.search('what did rocky ship');
 * console.log(results[0].statement);
 * ```
 */

export { Oracle, type OracleOptions } from './client.js';
export {
  generateKeypair,
  loadKeypair,
  saveKeypair,
  deriveDefaultHandle,
} from './signing.js';
export {
  AuthError,
  IngestError,
  NotFoundError,
  OracleError,
  RateLimitError,
} from './errors.js';
export {
  schemas,
  type AskResponse,
  type Capabilities,
  type Citation,
  type CommunitySibling,
  type ConnectionGraph,
  type HebbianNeighbor,
  type Keypair,
  type Observation,
  type SearchResult,
  type SelfInfo,
  type TypedEdge,
} from './types.js';
