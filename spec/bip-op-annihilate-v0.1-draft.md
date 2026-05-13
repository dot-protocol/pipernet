# BIP: OP_ANNIHILATE — Ephemeral Single-Use Covenants

## Preamble

```
  BIP: TBD
  Layer: Consensus (Soft Fork)
  Title: OP_ANNIHILATE — Ephemeral Single-Use Covenants
  Author: Pipernet contributors and affiliated researchers
  Comments-Summary: Seeking technical feedback and implementation feasibility study
  Status: Draft
  Type: Standards Track
  Created: 2026-05-13
  License: BSD-2-Clause
```

---

## Abstract

This BIP proposes `OP_ANNIHILATE_COMMIT` and `OP_ANNIHILATE_WITNESS` as two new Bitcoin Script opcodes that enable single-use covenants at the UTXO level. A UTXO that includes `OP_ANNIHILATE_COMMIT <commitment_hash>` in its `script_pubkey` binds itself, at creation, to a rule: *this output can be spent exactly once. Any subsequent attempt to spend it is consensus-invalid.*

Unlike Bitcoin's native double-spend protection (which operates globally across all nodes), OP_ANNIHILATE moves single-use semantics into the unit itself. The spending witness must include an `annihilation_proof` that proves the UTXO will be locally invalidated upon spending, not merely transferred. This opcode enables Bitcoin outputs to carry self-documenting, substrate-independent single-use properties, a pattern we term the *single-use covenant*.

---

## Motivation

### Single-Use is a Substrate-Independent Pattern

Bitcoin's consensus prevents double-spending globally: once a UTXO is spent, no node will accept a second spend of the same output. However, this protection operates *outside the unit*. The output's `script_pubkey` itself carries no declaration of single-use semantics. If Bitcoin Script is to support self-describing, composable primitives (whether for ephemeral contracts, capability-bound credentials, or agent-native identities), it must be possible for a UTXO to assert: "I am single-use by rule."

Three years of Pipernet protocol research (off-chain instantiations: coordination tasks in Oracle graphs, handle claims in identity namespaces) have shown that single-use is a common *pattern*, not a Bitcoin-specific feature. The pattern appears identically in on-chain (UTXO consensus) and off-chain (eventual-consistency read-time enforcement) substrates. This BIP formalizes the on-chain instantiation.

### Enabling Dot-Compatible Units

Recent cryptographic research into *microdots* (credential units that carry their own address, authorization, and destruction rule) requires a Bitcoin primitive that can express "this credential is single-use by cryptographic law, not by social convention." Current Script cannot express this cleanly. `OP_ANNIHILATE` fills this gap, allowing UTXOs to serve as DOT-shaped packets: units carrying (a) address, (b) authorization, and (c) destruction rule.

### Prior Art and Precedent

- **Hal Finney, *RPOW: Reusable Proofs of Work* (2004):** The first attempt to encode single-use into a cryptographic object. RPOW predates Bitcoin and was made obsolete by consensus-based double-spend prevention, not by logical refutation. This BIP recovers the insight.
- **BIP-119 (Jeremy Rubin, CheckTemplateVerify):** Introduced covenant semantics via template binding. OP_ANNIHILATE is complementary: where CTV binds the shape of subsequent transactions, OP_ANNIHILATE binds the *cardinality* (exactly one) of spending attempts.
- **BIP-348 (Pieter Wuille et al., CHECKSIGFROMSTACK):** Enables signatures to operate on stack-provided data, not just the transaction digest. OP_ANNIHILATE's proof shape can leverage CSFS for compact attestation.

---

## Specification

### Opcode Definitions

#### OP_ANNIHILATE_COMMIT (TBD_opcode_1)

**Semantics:** Reads the next stack item as a 32-byte hash and pushes a special "annihilation flag" to an auxiliary verification state. The flag marks this UTXO as subject to single-use enforcement.

**Format:** `OP_ANNIHILATE_COMMIT <32_bytes>`

**Stack effect:**
```
Input:  [commitment_hash, ...]
Output: [...] + auxiliary state: annihilation_required=true, commitment=commitment_hash
```

**Constraints:**
- The stack item must be exactly 32 bytes. If it is not, the script fails.
- The opcode can appear anywhere in the script; typically early after `OP_DUP` or in a Tapscript leaf.
- Multiple occurrences of `OP_ANNIHILATE_COMMIT` are allowed. All commitments must be satisfied by the witness.

#### OP_ANNIHILATE_WITNESS (TBD_opcode_2)

**Semantics:** Verifies that the spending witness includes a valid `annihilation_proof` that matches any commitment(s) created by preceding `OP_ANNIHILATE_COMMIT` opcodes. Marks the current UTXO as "annihilated" in the transaction's consensus state.

**Format:** `OP_ANNIHILATE_WITNESS` (consumes a stack item: the proof)

**Stack effect:**
```
Input:  [annihilation_proof, ...]
Output: [...], or script fails if proof is invalid
Consensus side effect: Mark UTXO as consumed (cannot be spent again in same block or future)
```

### Script Pubkey Example

A simple single-use output template:

```
OP_ANNIHILATE_COMMIT <dot_hash>
OP_CHECKSIG  // or other authorization, e.g., time-locked CHECKLOCKTIMEVERIFY
```

### Witness Example

A spending witness must include:

```
<annihilation_proof>
<signature>  // or whatever satisfies the authorization part
```

The `annihilation_proof` encodes a cryptographic attestation that the UTXO will be destroyed. Section 4 (Proof Shapes) details three candidate formats.

### Soft-Fork Activation Strategy

Pre-activation (before block height X):
- `OP_ANNIHILATE_COMMIT` behaves as `OP_NOP` (accepts any 32-byte stack item, pushes nothing).
- `OP_ANNIHILATE_WITNESS` behaves as `OP_NOP`.
- Existing UTXOs with these opcodes are unaffected.

Post-activation (block height X onwards):
- `OP_ANNIHILATE_COMMIT` enforces the commitment rule: auxiliary state is set.
- `OP_ANNIHILATE_WITNESS` enforces proof validation: spending fails if proof is invalid or absent.
- Validity checks apply only to *new* transactions; prior transactions remain valid.

**Compatibility with MAST and Taproot:**
- OP_ANNIHILATE opcodes operate in Tapscript leaf execution (BIP-342).
- Existing key-path spends (OP_1 <pubkey>) are unaffected.
- Script-path spends using leaves without OP_ANNIHILATE opcodes are unaffected.
- Soft-fork compatibility is enforced via the OP_NOP repurposing.

---

## Proof Shapes (Three Candidate Approaches)

The `annihilation_proof` witness field is deliberately left extensible. We propose **one primary shape** and two alternatives.

### Primary: Signature-Based Attestation (Recommended)

**Proof form:** A signature over the canonical commit value, using BIP-348 (CHECKSIGFROMSTACK).

**Pseudocode:**
```
annihilation_proof = SIGN(privkey, canonical_commit)
  where canonical_commit = H(outpoint || nonce || commitment_hash)

Verification:
  pubkey_from_script = extract from script_pubkey
  recovered_msg = VERIFY_SIG(pubkey, annihilation_proof)
  assert recovered_msg == H(current_outpoint || nonce || commitment_hash)
  mark UTXO as consumed
```

**Advantages:**
- Reuses existing signature algorithms (ECDSA, Schnorr).
- Compact: 64 bytes (Schnorr) or 71 bytes (DER-encoded ECDSA).
- Composable with CTV (can sign over template hash) and CSFS (stack-provided data).
- No new cryptographic assumptions.

**Disadvantages:**
- Requires the witness creator to know the signing key (no third-party proofs).
- Nonce handling must be specified carefully to prevent proof reuse across different outpoints.

### Alternative 1: Hash-Chain Preimage

**Proof form:** A preimage chain proving that the UTXO was destroyed at origin.

**Pseudocode:**
```
annihilation_proof = preimage_1 ... preimage_N
  where H(preimage_N) == commitment_hash
  and H(preimage_{i-1}) == preimage_i for all i

Verification:
  for preimage in annihilation_proof:
    assert H(preimage) matches the prior hash
  assert final_hash == commitment_hash
  mark UTXO as consumed
```

**Advantages:**
- No key material required; any witness creator can generate a proof.
- Parallelizable: multiple proofs can be verified concurrently.

**Disadvantages:**
- Larger witness sizes (linear in chain length).
- Vulnerability to second-preimage attacks if H() is weak.
- No binding to the actual outpoint; a proof generated for one UTXO could theoretically apply to another with the same commitment (unless outpoint is included in the hash).

### Alternative 2: Zero-Knowledge Proof

**Proof form:** A zero-knowledge succinct non-interactive argument (SNARK) or similar proof that the UTXO was destroyed without revealing the destruction secret.

**Pseudocode:**
```
annihilation_proof = SNARK_PROOF
  where private_input = destruction_secret
  public_input = commitment_hash, outpoint
  relation = "commitment_hash is H(destruction_secret) AND
              destruction_secret is valid according to some rule"

Verification:
  assert SNARK_PROOF validates against (commitment_hash, outpoint)
  mark UTXO as consumed
```

**Advantages:**
- Smallest witness sizes.
- No secrets revealed.
- Flexible rule specification via the relation.

**Disadvantages:**
- Complex prover infrastructure required on spending side.
- Verification cost is high (100s of ms per proof).
- New cryptographic assumptions (trusted setup, depending on scheme).
- Prover/verifier may have bugs; ecosystem maturity is lower than signatures.

---

## Rationale

### Why Commitment at Creation, Not at Spend?

Committing at creation time allows the output's creator to declare "this is single-use" upfront. If commitment were deferred to spend time, the rule would be opaque until the spend is broadcast — preventing verification of the property before acceptance into the mempool. Single-use is most useful as a *promise* made at output creation; commitment at creation time expresses that promise in consensus.

### Why Composable with CTV and CSFS, Not a Replacement?

CTV (BIP-119) constrains the *template* of the next transaction. OP_ANNIHILATE constrains the *cardinality*: exactly one next transaction. These are orthogonal concerns:
- CTV + OP_ANNIHILATE: "The next transaction must look like this template *and* this output cannot be spent more than once."
- CTV without OP_ANNIHILATE: "The next transaction must look like this template, but the output could theoretically appear in multiple confirmed transactions (if consensus rules were relaxed)."
- OP_ANNIHILATE without CTV: "Any transaction that spends this output is valid, but only one transaction will be honored."

Composability is critical for on-chain security: we want both constraints available simultaneously.

### Why Is the Proof in the Witness, Not the Script?

The `script_pubkey` defines the rule; the `witness` provides the proof. This separation is standard (e.g., signatures in witness, pubkey in script). For OP_ANNIHILATE, the commitment is immutable in the script; the proof of annihilation is witness data that varies per spending attempt. Keeping them separate allows easy script templating (the script can be reused for all instances of the pattern) while varying the proof per spend.

### Why First-Valid-Write Wins, Not Concurrent-Spends Allowed?

Bitcoin's consensus already provides first-valid-write: the first spend into a block wins; all subsequent spends of the same UTXO are invalid. OP_ANNIHILATE does not invent this rule; it inherits it. The opcode merely *asserts* at creation time that single-use is mandatory, not optional.

---

## Backwards Compatibility

### Soft-Fork Mechanism

OP_ANNIHILATE is activated via a soft fork. The opcodes begin as OP_NOP equivalents:

- Pre-activation: `OP_ANNIHILATE_COMMIT` accepts any 32 bytes and succeeds.
- Post-activation: `OP_ANNIHILATE_COMMIT` still accepts any 32 bytes but *enforces* the commitment rule in conjunction with witness validation.

Existing UTXOs created before activation (which may contain these opcodes if deployed as no-ops by early adopters) remain valid and spendable after activation. Only *new* transactions post-activation are subject to the enforcement rules.

### MAST and Taproot Compatibility

OP_ANNIHILATE operates within Tapscript leaf execution (BIP-342). It does not interfere with:
- **Key-path spends:** Spends via the plain pubkey (OP_1 <pubkey>) bypass Tapscript entirely.
- **Leaves without OP_ANNIHILATE:** Other script paths in the same Taproot output are unaffected.
- **Existing consensus rules:** OP_ANNIHILATE is an additional rule; it does not remove or weaken prior rules.

### Interaction with BIP-119 (CTV) and BIP-348 (CSFS)

Both BIPs are compatible. A single Tapscript leaf can include CTV for template binding and OP_ANNIHILATE for single-use enforcement. A single witness can provide both the template proof (for CTV) and the annihilation proof (for OP_ANNIHILATE). No conflicts arise.

---

## Reference Implementation

### Pseudocode for Consensus Check

```
// Called during transaction validation for each input
// script_pubkey: the output's script (may contain OP_ANNIHILATE_COMMIT)
// witness: the spending witness (must contain annihilation_proof if required)

function validate_annihilate(script_pubkey, witness, outpoint):
  annihilation_required = false
  commitment_hash = null
  
  // Parse script_pubkey for OP_ANNIHILATE_COMMIT
  for opcode in parse(script_pubkey):
    if opcode == OP_ANNIHILATE_COMMIT:
      next_item = pop(script_pubkey)
      assert len(next_item) == 32
      annihilation_required = true
      commitment_hash = next_item
      
  if not annihilation_required:
    return OK
    
  // Parse witness for proof
  annihilation_proof = extract_from_witness(witness)
  if annihilation_proof is None:
    return FAIL_MISSING_PROOF
    
  // Validate proof against commitment (shape-dependent; default: signature)
  canonical_msg = H(outpoint || annihilation_proof[:16] || commitment_hash)
  pubkey = extract_pubkey_from_script(script_pubkey)
  
  if VERIFY_SCHNORR_SIG(pubkey, annihilation_proof[16:80], canonical_msg):
    mark_utxo_as_spent(outpoint)
    return OK
  else:
    return FAIL_INVALID_PROOF

// In UTXO database:
// UTXOs annihilated by OP_ANNIHILATE cannot be re-indexed.
// Attempting to spend an annihilated UTXO is an error.
```

### Test Vectors (Outline)

The reference implementation must include:

1. **Valid annihilation (primary proof shape):** A Schnorr-signed proof matching a commitment hash.
2. **Valid annihilation (hash-chain proof):** A preimage chain matching the commitment.
3. **Invalid annihilation (wrong proof):** A proof that does not validate against the commitment; transaction must fail.
4. **Invalid annihilation (missing proof):** A witness with no annihilation proof when one is required; transaction must fail.
5. **Double-spend attempt:** Two transactions attempting to spend the same annihilated UTXO; only the first is valid.
6. **Soft-fork compatibility (pre-activation):** A transaction with OP_ANNIHILATE_COMMIT executed as OP_NOP succeeds pre-activation.
7. **MAST interaction:** A Taproot output with one leaf containing OP_ANNIHILATE and another leaf without; spending via the annihilate-free leaf succeeds.
8. **CTV + OP_ANNIHILATE:** A Tapscript leaf with both BIP-119 (CTV) and this opcode; a witness satisfying both constraints succeeds.

(Full test vector suite with actual transaction data will be included in the reference implementation pull request.)

---

## Activation

### Activation Mechanism

We propose **Speedy Trial** style activation (BIP-9 variant, as used in BIP-119):

- **Activation period:** 2016 blocks (~2 weeks) with miner signaling at version bit TBD.
- **Threshold:** 95% of blocks in the period signal support.
- **Timeout:** If not activated within 12 months, the deployment is deferred for community review.
- **Fallback:** Standard BIP-9 with a longer signaling window (e.g., 1 year) if Speedy Trial is rejected.

This timeline aligns with Bitcoin Core's precedent for CTV (BIP-119) and similar opcodes.

### Rationale for Activation Approach

Speedy Trial reduces uncertainty: either strong consensus (95%+ miners) exists and activation happens quickly, or consensus is lacking and the community can reassess. Twelve months provides ample time for node operators to upgrade; Taproot and prior soft forks used similar windows.

---

## Open Questions

### RBF (Replace-by-Fee) Interaction

Can a spending transaction with an annihilation proof be replaced by a second spending transaction (also valid, but with a different proof)? Current Bitcoin RBF policy would allow it if fees are higher. OP_ANNIHILATE does not *prevent* RBF at the script level, but the interaction should be specified:

- **Option A (Conservative):** Annihilated UTXOs are opt-out for RBF; a spend with a valid annihilation proof cannot be replaced.
- **Option B (Permissive):** RBF is allowed; both spending transactions are valid, but only one will confirm due to Bitcoin's consensus rules. The first-valid-write rule handles the outcome.

**Recommendation:** Option A. RBF is valuable, but single-use semantics are stronger if spending transactions are immutable post-broadcast.

### Lightning HTLC Interaction

HTLC scripts (Hash Time Locked Contracts) use `OP_HASH160` and time checks. Can OP_ANNIHILATE coexist with HTLC branches in the same Tapscript?

**Answer:** Yes. A Tapscript leaf can contain either HTLC logic or OP_ANNIHILATE logic (or both, if carefully structured). The interaction is orthogonal: time and annihilation are independent constraints. However, mixed scripts should be specified carefully in a companion BIP.

### MEV and Sandwich Attacks

If OP_ANNIHILATE proofs are short (64 bytes for Schnorr), can a mempool watcher front-run a spend, broadcast a competing spend with a different proof, and capture MEV?

**Answer:** Not uniquely. The competing proof must be valid for the same commitment hash. If the commitment hash depends on the outpoint and a nonce (as we recommend), the attacker cannot generate a proof without knowing the nonce. Standard commitmentsecurity applies.

### Taprootized Commitment Visibility

Is the commitment hash visible on-chain? Yes; it is part of the `script_pubkey` in Tapscript. Privacy concern?

**Answer:** Minimal. The commitment hash itself reveals nothing (it is a 32-byte hash). The structure of the output (that it is annihilatable) is visible, as are all Script operations. Users concerned with privacy can use larger merkle branches (MAST) to hide the commitment. This is not unique to OP_ANNIHILATE.

### Package Relay Interaction

Bitcoin Core is moving toward package relay (multiple transactions validated as a unit). Does OP_ANNIHILATE interact safely?

**Answer:** Yes, but the interaction must be validated. A package consisting of two transactions that both attempt to spend the same annihilated UTXO should be rejected at package validation time, not later. This may require updates to package relay policy.

---

## Acknowledgements

- **Hal Finney** for RPOW (2004), the original insight that computational work could be single-use.
- **Jeremy Rubin** (BIP-119, CheckTemplateVerify) for demonstrating the viability of covenant opcodes in Bitcoin.
- **Pieter Wuille and contributors** (Taproot, Tapscript, BIP-342) for the infrastructure that makes nested covenants possible.
- **The Harrier Room session** (2026-04-22, `OBS-axxis-20260422-1010` in the Axxis Oracle) for the initial seed proposal and motivation.
- **The Pipernet coordination and handle substrates** (v0.1, 2026-05-12) for demonstrating the single-use covenant pattern off-chain and establishing the abstract properties.
- **The Bitcoin Core development team** for four decades of consensus engineering and precedent in soft-fork activation.

---

## References

- [BIP-2](https://github.com/bitcoin/bips/blob/master/bip-0002.mediawiki) — Bitcoin Improvement Proposals
- [BIP-9](https://github.com/bitcoin/bips/blob/master/bip-0009.mediawiki) — Versionbits with Timeout and Delay
- [BIP-119](https://github.com/bitcoin/bips/blob/master/bip-0119.mediawiki) — Covenants with CheckTemplateVerify (Jeremy Rubin)
- [BIP-341](https://github.com/bitcoin/bips/blob/master/bip-0341.mediawiki) — Taproot: SegWit version 1 Spending Rules
- [BIP-342](https://github.com/bitcoin/bips/blob/master/bip-0342.mediawiki) — Tapscript
- [BIP-348](https://github.com/bitcoin/bips/blob/master/bip-0348.mediawiki) — CHECKSIGFROMSTACK (Pieter Wuille)
- Hal Finney, "RPOW - Reusable Proofs of Work" (2004), http://www.finney.org/~hal/rpow.html
- Single-Use Covenant specification (Pipernet, 2026-05-13) — `pipernet/spec/single-use-covenant-v0.1.md`

---

## Appendix A: Example Tapscript Leaf

A full example of a DOT-compatible single-use output using OP_ANNIHILATE and Taproot:

```
// Output script (Taproot internal key path unused)
// Tapscript leaf (one of possibly many):

OP_DUP
OP_ANNIHILATE_COMMIT <SHA256(dot_origin || nonce)>
OP_CHECKSIG
<pubkey>
```

Witness to spend (satisfying the leaf):
```
<annihilation_proof (64 bytes, Schnorr)>
<signature>
```

The output is DOT-shaped: it carries its own address (the Taproot UTXO), its own authorization (pubkey + signature), and its own destruction rule (OP_ANNIHILATE with the commitment).

---

## Appendix B: Proof Shape Decision Tree

Implementers choosing a proof shape can use this tree:

1. **Is the proof signer known at script creation time?**
   - Yes → Use **Signature-Based Attestation** (primary). Smaller, faster, more composable.
   - No → Proceed to (2).

2. **Is witness size a critical constraint (e.g., very high frequency, ultra-low fees)?**
   - Yes → Use **Zero-Knowledge Proof** (Alternative 2) if infrastructure is available. Otherwise, signature-based with short nonce.
   - No → Proceed to (3).

3. **Is proof reusability allowed (same proof for multiple spends)?**
   - Yes → Use **Hash-Chain Preimage** (Alternative 1). Enables parallel proof generation.
   - No → Default to **Signature-Based** (primary).

For the first mainnet deployment, **Signature-Based Attestation** is recommended as the baseline.

---

*End of BIP Draft v0.1*
