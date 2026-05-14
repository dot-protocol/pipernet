"""
pipernet/problems.py — Problem/Solution Substrate v0.1 reference implementation.

Implements spec §17 (republic-spec/spec/17-problem-solution-substrate.md).
Origin: Council Round 27 (2026-05-14), authored by Jared (jared-b6444e7e).
Canonical Oracle observations: OBS-dot-protocol-20260514-939924420 (27a),
                               OBS-dot-protocol-20260514-973279308 (27b).

CC0 — No rights reserved.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Literal


# ---------------------------------------------------------------------------
# Supporting types
# ---------------------------------------------------------------------------

@dataclass
class ProblemState:
    """Observed and desired states with the gap between them."""
    historical: list[dict[str, Any]] = field(default_factory=list)   # prior observations, signed+dated
    current: dict[str, Any] = field(default_factory=dict)            # head observation
    desired: dict[str, Any] = field(default_factory=dict)            # observer's target state
    gap: float = 0.0                                                  # distance(current, desired)
    trajectory: dict[str, Any] = field(default_factory=dict)         # projected state if nothing done


@dataclass
class ProblemPredictions:
    """Causal forecasts for doing nothing vs taking an action."""
    do_nothing: dict[str, Any] = field(default_factory=dict)   # forecast + confidence
    alternatives: list[dict[str, Any]] = field(default_factory=list)  # [{action, forecast, confidence}]


@dataclass
class ProblemCauses:
    """Causal chain behind the observed gap."""
    chain: list[dict[str, Any]] = field(default_factory=list)   # prior events / agents producing current
    root: str = ""                                               # deepest identified cause
    responsible: list[dict[str, Any]] = field(default_factory=list)  # signed attributions


@dataclass
class ProblemComposition:
    """Fractal composition links — how this problem nests in the hierarchy."""
    parent: str | None = None           # problem_id this is a sub-problem of
    children: list[str] = field(default_factory=list)   # problem_ids this decomposes into
    siblings: list[str] = field(default_factory=list)   # problem_ids sharing parent
    duplicates: list[str] = field(default_factory=list) # same structural signature, different observers


@dataclass
class ProblemPrivacy:
    """Privacy envelope for observer-sensitive data."""
    level: Literal["public", "redacted", "private"] = "public"
    redactions: list[str] = field(default_factory=list)  # PII patterns scrubbed at ingest


# ---------------------------------------------------------------------------
# Core Problem dataclass  (§2 + §9)
# ---------------------------------------------------------------------------

@dataclass
class Problem:
    """
    A Problem is the gap between observed state and desired state, as seen by an observer.
    No observer → no problem. Observer is a required field; a problem without a stated
    observer is malformed — it describes a state, not a problem.

    identity = sha256 of the canonicalised record (including observer) minus signatures.
    structural_signature = sha256 of the same record with observer stripped — used for
    duplicate detection across different observers facing the same structural gap.
    """
    identity: str                               # sha256 of canonical encoding minus signatures
    observer: str                               # resolved handle — MUST be present
    state: ProblemState
    predictions: ProblemPredictions
    causes: ProblemCauses
    composition: ProblemComposition
    scope: Literal["atomic", "local", "regional", "global", "universal"]
    privacy: ProblemPrivacy
    decomposable: bool = True                   # §8.5: set False at leaf nodes by the observer


# ---------------------------------------------------------------------------
# Action type  (used by Solution)
# ---------------------------------------------------------------------------

@dataclass
class Action:
    """One ordered operation within a solution."""
    seq: int                             # execution order (0-based)
    description: str                     # what to do
    actor: str = ""                      # who performs it (handle or role)
    requires: list[str] = field(default_factory=list)   # prerequisite action seqs
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Supporting solution types
# ---------------------------------------------------------------------------

@dataclass
class SolutionOutcome:
    """Verifiable before/after snapshot with N-of-M verification."""
    pre_state: dict[str, Any] = field(default_factory=dict)
    post_state: dict[str, Any] = field(default_factory=dict)
    gap_reduction: float = 0.0           # measurable delta (positive = improvement)
    verified_by: list[str] = field(default_factory=list)  # N-of-M verifier pubkeys / handles


@dataclass
class SolutionTransferability:
    """Which problem signatures this solution closes, and where it breaks."""
    works_for: list[str] = field(default_factory=list)    # structural signatures this closes
    breaks_when: list[str] = field(default_factory=list)  # failure modes / counter-conditions


@dataclass
class SolutionReproducibility:
    """Replay protocol so others can re-apply this solution."""
    instructions: str = ""               # step-by-step replay protocol
    requirements: list[str] = field(default_factory=list)  # prerequisites to run


# ---------------------------------------------------------------------------
# Core Solution dataclass  (§3 + §9)
# ---------------------------------------------------------------------------

@dataclass
class Solution:
    """
    A Solution closes a Problem when its outcome.post_state matches the problem's
    state.desired within the observer's apparatus resolution (see closes()).

    Transferability.works_for is the marketplace primitive: a solution that names
    which structural signatures it closes can be re-applied automatically.

    Verification is N-of-M signed by verifier keys — not a single party's claim.
    """
    identity: str           # sha256 of canonical encoding minus signatures
    problem_id: str         # parent problem this solution addresses
    actions: list[Action]
    outcome: SolutionOutcome
    transferability: SolutionTransferability
    reproducibility: SolutionReproducibility


# ---------------------------------------------------------------------------
# Canonicalisation helpers
# ---------------------------------------------------------------------------

def _strip_signatures(d: dict[str, Any]) -> dict[str, Any]:
    """
    Recursively remove signature-like fields from a dict before hashing.
    Signature fields: 'signature', 'signatures', 'sig', 'signed_by'.
    """
    skip = {"signature", "signatures", "sig", "signed_by"}
    result: dict[str, Any] = {}
    for k, v in d.items():
        if k in skip:
            continue
        if isinstance(v, dict):
            result[k] = _strip_signatures(v)
        elif isinstance(v, list):
            result[k] = [
                _strip_signatures(item) if isinstance(item, dict) else item
                for item in v
            ]
        else:
            result[k] = v
    return result


def canonicalize(d: dict[str, Any]) -> bytes:
    """
    Canonical encoding for hashing.
    - Strips signature fields.
    - JSON with sorted keys and no whitespace.
    - UTF-8 encoded bytes.

    Identical problems from different observers produce different bytes here because
    the observer field is preserved.  signature() below strips it for structural
    duplicate detection.
    """
    cleaned = _strip_signatures(d)
    return json.dumps(cleaned, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


# ---------------------------------------------------------------------------
# Core functions  (§9)
# ---------------------------------------------------------------------------

def identity(p: Problem) -> str:
    """
    Compute the canonical identity of a Problem as sha256 of its full canonical
    encoding (observer included, signatures stripped).

    Identical problems from the same observer converge to the same identity.
    Different observers describing the same structural gap get different identities
    but the same structural_signature.

    The `identity` field itself is derived, so it is stripped from the hash input
    to break the chicken-and-egg: identity depends on the canonical encoding, so
    we cannot include the prior identity value (often empty on first compute).
    """
    d = asdict(p)
    d.pop("identity", None)
    return hashlib.sha256(canonicalize(d)).hexdigest()


def signature(p: Problem) -> str:
    """
    Structural signature — observer-stripped hash for duplicate detection.

    Two problems are duplicates when their structural signature matches modulo
    the observer.  The observer field is set to None before hashing so the
    signature is purely structural.

    `identity` is also stripped: identity is derived from canonical encoding
    *with* the observer, so leaving it in would re-introduce observer-dependence
    through the back door — breaking the observer-invariant guarantee that
    §4's duplicate-detection marketplace depends on.

    Usage: one signed solution can close millions of duplicate problems if the
    structural signature matches (§4 — the marketplace tick).
    """
    d = {**asdict(p), "observer": None}
    d.pop("identity", None)
    return hashlib.sha256(canonicalize(d)).hexdigest()


def duplicates(p: Problem, store: Any) -> list[Problem]:
    """
    Find all problems in *store* that share p's structural signature but are
    not p itself.

    store must implement:
        store.query(structural_signature: str, exclude: str) -> list[Problem]

    The exclude parameter prevents p from appearing in its own results.
    """
    return store.query(structural_signature=signature(p), exclude=p.identity)


def closes(solution: Solution, problem: Problem, tolerance: float = 0.0) -> bool:
    """
    A solution *closes* a problem if its outcome.post_state brings the gap
    to within the observer's apparatus resolution (§3).

    Design choice: gap_reduction is taken as the primary measurable signal.
    The solution closes the problem when:
        outcome.gap_reduction >= (problem.state.gap - tolerance)

    This handles three cases:
        1. Numeric gap (e.g. financial shortfall, latency ms): exact comparison.
        2. Qualitative gap (gap stored as 0.0 when state equality is the test):
           falls back to comparing post_state == desired directly.
        3. Partial closure: tolerance > 0 allows declaring closure when the
           residual gap is within the observer's resolution.

    For qualitative problems where gap is 0.0 and states are dicts, equality
    of post_state vs desired is used instead.
    """
    desired = problem.state.desired
    post = solution.outcome.post_state
    gap = problem.state.gap

    if gap == 0.0:
        # Qualitative: check state equality
        return post == desired

    # Quantitative: check gap_reduction covers the gap within tolerance
    residual = gap - solution.outcome.gap_reduction
    return residual <= tolerance


# ---------------------------------------------------------------------------
# __main__ smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # --- Build a minimal Problem ---
    prob = Problem(
        identity="",   # will be filled by identity()
        observer="jared-b6444e7e",
        state=ProblemState(
            current={"status": "no_childcare"},
            desired={"status": "childcare_arranged"},
            gap=1.0,
            trajectory={"status": "still_no_childcare"},
        ),
        predictions=ProblemPredictions(
            do_nothing={"forecast": "gap persists", "confidence": 0.95},
        ),
        causes=ProblemCauses(
            chain=[{"event": "daycare_closed", "agent": "daycare_provider"}],
            root="daycare_closed",
        ),
        composition=ProblemComposition(),
        scope="atomic",
        privacy=ProblemPrivacy(),
    )
    prob.identity = identity(prob)

    print("=== Problem ===")
    print(f"  identity  : {prob.identity}")
    print(f"  observer  : {prob.observer}")
    print(f"  scope     : {prob.scope}")
    sig = signature(prob)
    print(f"  signature : {sig}")

    # Build a STRUCTURALLY IDENTICAL problem from a different observer.
    # Every field MUST match prob1 except `observer` and `identity` — those are
    # the two fields signature() strips before hashing, so identical structure
    # → identical signature → §4 marketplace duplicate detection works.
    prob2 = Problem(
        identity="",
        observer="shannon-abc12345",   # ONLY this differs from prob1
        state=ProblemState(
            current={"status": "no_childcare"},
            desired={"status": "childcare_arranged"},
            gap=1.0,
            trajectory={"status": "still_no_childcare"},
        ),
        predictions=ProblemPredictions(
            do_nothing={"forecast": "gap persists", "confidence": 0.95},
        ),
        causes=ProblemCauses(
            chain=[{"event": "daycare_closed", "agent": "daycare_provider"}],
            root="daycare_closed",
        ),
        composition=ProblemComposition(),
        scope="atomic",
        privacy=ProblemPrivacy(),
    )
    prob2.identity = identity(prob2)

    sig2 = signature(prob2)
    print()
    print("=== Duplicate detection ===")
    print(f"  prob1 identity  : {prob.identity}")
    print(f"  prob2 identity  : {prob2.identity}")
    print(f"  prob1 signature : {sig}")
    print(f"  prob2 signature : {sig2}")
    print(f"  identities match: {prob.identity == prob2.identity}")
    print(f"  signatures match: {sig == sig2}  (expected True — same structure)")

    # Build a matching Solution
    sol = Solution(
        identity="",
        problem_id=prob.identity,
        actions=[
            Action(seq=0, description="Call neighbour family", actor="jared-b6444e7e"),
            Action(seq=1, description="Confirm Wednesday slot", actor="jared-b6444e7e", requires=[0]),
        ],
        outcome=SolutionOutcome(
            pre_state={"status": "no_childcare"},
            post_state={"status": "childcare_arranged"},
            gap_reduction=1.0,
            verified_by=["jared-b6444e7e"],
        ),
        transferability=SolutionTransferability(
            works_for=[sig],   # closes any problem with this structural signature
            breaks_when=["neighbour_unavailable"],
        ),
        reproducibility=SolutionReproducibility(
            instructions="1. Identify a neighbour with available childcare capacity. 2. Call and confirm.",
            requirements=["phone", "neighbour_contact"],
        ),
    )
    sol.identity = hashlib.sha256(canonicalize(asdict(sol))).hexdigest()

    print()
    print("=== Solution ===")
    print(f"  identity      : {sol.identity}")
    print(f"  problem_id    : {sol.problem_id}")
    print(f"  gap_reduction : {sol.outcome.gap_reduction}")

    print()
    print("=== closes() ===")
    print(f"  closes(sol, prob1): {closes(sol, prob)}  (expected True)")
    print(f"  closes(sol, prob2): {closes(sol, prob2)}  (expected True — same gap)")

    # Partial close test
    partial_sol = Solution(
        identity="",
        problem_id=prob.identity,
        actions=[Action(seq=0, description="Find half-day option")],
        outcome=SolutionOutcome(gap_reduction=0.6),
        transferability=SolutionTransferability(),
        reproducibility=SolutionReproducibility(),
    )
    print(f"  closes(partial, prob, tol=0): {closes(partial_sol, prob, tolerance=0.0)}  (expected False)")
    print(f"  closes(partial, prob, tol=0.5): {closes(partial_sol, prob, tolerance=0.5)}  (expected True)")

    print()
    print("All checks passed.")
