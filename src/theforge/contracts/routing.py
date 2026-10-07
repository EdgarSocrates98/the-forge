"""RoutingDecision: auditable record of why a provider was (not) selected."""

from dataclasses import dataclass, field
from typing import Literal

from theforge.contracts.base import ContractError
from theforge.contracts.negotiation import CapabilityNegotiationResult
from theforge.contracts.types import CapabilityState, PlanPattern, Producer

ROUTING_SCHEMA = "theforge/RoutingDecision/v1"


@dataclass(frozen=True, kw_only=True)
class MatchedSignals:
    dependencies: list[str] = field(default_factory=list)
    file_globs: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class Candidate:
    provider: str
    capability: str
    matched: MatchedSignals = field(default_factory=MatchedSignals)
    rank_key: list[int] = field(default_factory=list)
    state: CapabilityState = "supported"


@dataclass(frozen=True, kw_only=True)
class Selection:
    provider: str
    capability: str
    action: str
    role: Literal["primary", "specialist"] = "primary"


@dataclass(frozen=True, kw_only=True)
class Confidence:
    level: Literal["high", "low"]
    measured_signals: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class ShadowRecommendation:
    """History-preferred alternative to the selected provider (Cycle 4, Wave H).

    Champion/challenger evidence, advisory only (§51-55, §102-103): the shadow
    names what measured history would have picked — it is never executed and
    never changes ``selected``. The challenger had to clear the promotion bar
    on evidence (enough runs, verified rate at least the incumbent's, strictly
    cheaper context when the incumbent has comparable history); the bar itself
    is what ``evidence`` records, so a reader can audit the claim. ``maturity``
    is ``warming``/``mature`` — cold history never advises (§55).
    """

    provider: str
    capability: str
    maturity: Literal["warming", "mature"]
    evidence: list[str] = field(default_factory=list)
    advisory: Literal[True] = True

    def __post_init__(self) -> None:
        if not self.provider or not self.capability:
            raise ContractError("shadow recommendation: provider/capability required")
        if not self.evidence:
            raise ContractError("shadow recommendation: evidence must not be empty")
        if not self.advisory:
            raise ContractError("shadow recommendation is advisory by definition")


@dataclass(frozen=True, kw_only=True)
class RoutingDecision:
    schema: str = ROUTING_SCHEMA
    producer: Producer
    created_at: str
    status: Literal["routed", "ambiguous", "no_route"]
    task_id: str
    candidates: list[Candidate] = field(default_factory=list)
    selected: list[Selection] = field(default_factory=list)
    pattern: PlanPattern = "route"  # additive: decisions recorded without it are "route"
    # Cycle 4 (additive): the per-provider negotiation results when the task
    # carried a CapabilityRequirement — the raw dimensions behind the choice,
    # including the rejected offers (§14); empty when no requirement applied.
    negotiation: list[CapabilityNegotiationResult] = field(default_factory=list)
    # Cycle 4 Wave H (additive): the history-preferred challenger, advisory —
    # shadow evaluation only; promotion stays a human/policy decision (§52).
    shadow: ShadowRecommendation | None = None
    reason: str
    confidence: Confidence
    fallbacks_used: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != ROUTING_SCHEMA:
            raise ContractError(f"unsupported schema {self.schema!r}, expected {ROUTING_SCHEMA!r}")
        if self.status == "routed" and not self.selected:
            raise ContractError("routed decision requires a selection")
