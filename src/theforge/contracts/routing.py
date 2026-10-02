"""RoutingDecision: auditable record of why a provider was (not) selected."""

from dataclasses import dataclass, field
from typing import Literal

from theforge.contracts.base import ContractError
from theforge.contracts.types import Producer

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
class RoutingDecision:
    schema: str = ROUTING_SCHEMA
    producer: Producer
    created_at: str
    status: Literal["routed", "ambiguous", "no_route"]
    task_id: str
    candidates: list[Candidate] = field(default_factory=list)
    selected: list[Selection] = field(default_factory=list)
    pattern: Literal["route"] = "route"
    reason: str
    confidence: Confidence
    fallbacks_used: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.status == "routed" and not self.selected:
            raise ContractError("routed decision requires a selection")
