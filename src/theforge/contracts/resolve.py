"""Semantic routing fallback contracts (Cycle 3 Wave K).

``ResolveRequest`` is the minimal input the resolver sees (K1): the task, the
eligible candidates with the evidence signals that scored them, why the
deterministic router could not decide, and the workspace technology summary —
never the repository. ``RoutingProposal`` is its answer (K2): one pick among the
offered candidates plus its declared confidence, evidence, alternatives and
unknowns. Both cross the Forge Protocol in the ``resolve`` op: open schemas.
"""

from dataclasses import dataclass, field
from typing import Literal

from theforge.contracts.base import ContractError
from theforge.contracts.routing import MatchedSignals
from theforge.contracts.task import TaskSpec

RESOLVE_REQUEST_SCHEMA = "theforge/ResolveRequest/v1"
ROUTING_PROPOSAL_SCHEMA = "theforge/RoutingProposal/v1"


@dataclass(frozen=True, kw_only=True)
class ResolveCandidate:
    """One routing-eligible (provider, capability) the resolver may pick (K1)."""

    provider: str
    capability: str
    actions: list[str]
    state: str = ""
    matched: MatchedSignals = field(default_factory=MatchedSignals)


@dataclass(frozen=True, kw_only=True)
class ResolveRequest:
    """Request payload of the ``resolve`` op (crosses the protocol: open schema).

    Bounded by construction: the task summary, the candidate set the router
    already proved eligible, the ambiguity reason and technology names — the
    resolver never receives files, packs or the repository.
    """

    schema: str = RESOLVE_REQUEST_SCHEMA
    task: TaskSpec
    candidates: list[ResolveCandidate]
    ambiguity: str = ""
    technologies: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != RESOLVE_REQUEST_SCHEMA:
            raise ContractError(
                f"unsupported schema {self.schema!r}, expected {RESOLVE_REQUEST_SCHEMA}"
            )


@dataclass(frozen=True, kw_only=True)
class ProposalChoice:
    """The resolver's pick: ``action`` empty means the capability default."""

    provider: str
    capability: str
    action: str = ""

    def __post_init__(self) -> None:
        if not self.provider or not self.capability:
            raise ContractError("routing proposal choice requires a provider and a capability")


@dataclass(frozen=True, kw_only=True)
class RoutingProposal:
    """Response payload of the ``resolve`` op (K2, open schema).

    Advisory only: the core re-checks ``choice`` against the offered set and the
    picked provider then passes the same health, policy, context and
    verification gauntlet as any deterministic selection. The proposal's own
    ``confidence`` describes the resolver's claim, never the run's evidence —
    a resolved decision records confidence ``low`` either way.
    """

    schema: str = ROUTING_PROPOSAL_SCHEMA
    choice: ProposalChoice
    confidence: Literal["high", "medium", "low"] = "low"
    reason: str = ""
    evidence: list[str] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != ROUTING_PROPOSAL_SCHEMA:
            raise ContractError(
                f"unsupported schema {self.schema!r}, expected {ROUTING_PROPOSAL_SCHEMA}"
            )
