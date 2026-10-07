"""Context ROI and strategy-experiment contracts (Cycle 4.1)."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from theforge.contracts.base import ContractError
from theforge.contracts.types import SHA256_RE, Producer, check_sha256

CONTEXT_ROI_SCHEMA = "theforge/ContextROI/v1"
CONTEXT_RECOMMENDATION_SCHEMA = "theforge/ContextBudgetRecommendation/v1"
STRATEGY_EXPERIMENT_SCHEMA = "theforge/StrategyExperiment/v1"

HistoryMaturity = Literal["absent", "cold", "warming", "mature", "stale"]
ExperimentState = Literal[
    "planned",
    "shadow",
    "observing",
    "eligible_for_review",
    "promoted",
    "rejected",
    "stale",
    "cancelled",
]


@dataclass(frozen=True, kw_only=True)
class ContextROI:
    schema: str = CONTEXT_ROI_SCHEMA
    producer: Producer
    created_at: str
    provider: str
    capability: str
    surface_fingerprint: str
    task_family: str | None
    runs: int
    measured_runs: int
    delivered_bytes: int
    delivered_items: int
    cited_items: int
    utilization_ratio: float | None
    maturity: HistoryMaturity
    delivered_runs: int = 0
    verified_runs: int = 0
    limitations: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != CONTEXT_ROI_SCHEMA:
            raise ContractError(f"context roi: unsupported schema {self.schema!r}")
        if not self.provider or not self.capability or not self.surface_fingerprint:
            raise ContractError("context roi: provider/capability/surface are required")
        for name in (
            "runs",
            "measured_runs",
            "delivered_bytes",
            "delivered_items",
            "cited_items",
            "delivered_runs",
            "verified_runs",
        ):
            if getattr(self, name) < 0:
                raise ContractError(f"context roi: {name} cannot be negative")
        if self.measured_runs > self.runs:
            raise ContractError("context roi: measured_runs exceeds runs")
        if self.delivered_runs > self.runs:
            raise ContractError("context roi: delivered_runs exceeds runs")
        if self.verified_runs > self.runs:
            raise ContractError("context roi: verified_runs exceeds runs")
        if self.cited_items > self.delivered_items:
            raise ContractError("context roi: cited_items exceeds delivered_items")
        if self.utilization_ratio is not None and not 0 <= self.utilization_ratio <= 1:
            raise ContractError("context roi: utilization_ratio must be in [0,1]")


@dataclass(frozen=True, kw_only=True)
class ContextBudgetRecommendation:
    schema: str = CONTEXT_RECOMMENDATION_SCHEMA
    producer: Producer
    created_at: str
    provider: str
    capability: str
    surface_fingerprint: str
    task_family: str | None
    current_budget_bytes: int
    suggested_budget_bytes: int
    maturity: Literal["warming", "mature"]
    basis: list[str] = field(metadata={"min_items": 1})
    advisory: Literal[True] = True

    def __post_init__(self) -> None:
        if self.schema != CONTEXT_RECOMMENDATION_SCHEMA:
            raise ContractError(
                f"context recommendation: unsupported schema {self.schema!r}"
            )
        if self.current_budget_bytes <= 0 or self.suggested_budget_bytes <= 0:
            raise ContractError("context recommendation: budgets must be positive")
        if self.suggested_budget_bytes >= self.current_budget_bytes:
            raise ContractError(
                "context recommendation: suggestion must reduce the current budget"
            )
        if not self.basis:
            raise ContractError("context recommendation: basis must not be empty")


@dataclass(frozen=True, kw_only=True)
class StrategyExperiment:
    schema: str = STRATEGY_EXPERIMENT_SCHEMA
    producer: Producer
    created_at: str
    experiment_id: str
    capability: str
    task_family: str | None
    champion: str
    challenger: str
    champion_surface: str
    challenger_surface: str
    state: ExperimentState = "planned"
    discovery_before: str | None = None
    evaluation_after: str | None = None
    minimum_runs: int = 8
    minimum_verified_runs: int = 5
    observations: int = 0
    verified_observations: int = 0
    reasons: list[str] = field(default_factory=list)
    approval_sha256: str | None = field(
        default=None,
        metadata={"pattern": SHA256_RE.pattern},
    )
    operator_approval_required: Literal[True] = True

    def __post_init__(self) -> None:
        if self.schema != STRATEGY_EXPERIMENT_SCHEMA:
            raise ContractError(f"strategy experiment: unsupported schema {self.schema!r}")
        if not all((
            self.experiment_id,
            self.capability,
            self.champion,
            self.challenger,
            self.champion_surface,
            self.challenger_surface,
        )):
            raise ContractError("strategy experiment: identity fields must not be empty")
        if self.champion == self.challenger:
            raise ContractError("strategy experiment: champion and challenger must differ")
        if self.minimum_runs <= 0 or self.minimum_verified_runs <= 0:
            raise ContractError("strategy experiment: minimums must be positive")
        if self.minimum_verified_runs > self.minimum_runs:
            raise ContractError(
                "strategy experiment: minimum_verified_runs exceeds minimum_runs"
            )
        if self.observations < 0 or self.verified_observations < 0:
            raise ContractError("strategy experiment: observations cannot be negative")
        if self.verified_observations > self.observations:
            raise ContractError(
                "strategy experiment: verified observations exceed observations"
            )
        if not self.operator_approval_required:
            raise ContractError("strategy experiment: promotion requires operator approval")
        if self.approval_sha256 is not None:
            check_sha256(self.approval_sha256, field="approval_sha256")
        governed_states = {
            "eligible_for_review", "promoted", "rejected", "stale", "cancelled"
        }
        if self.state in governed_states and not self.reasons:
            raise ContractError(
                f"strategy experiment: state {self.state!r} requires reasons"
            )
        if self.state == "promoted" and self.approval_sha256 is None:
            raise ContractError(
                "strategy experiment: promoted state requires approval_sha256"
            )
        timestamps: dict[str, datetime] = {}
        for name in ("discovery_before", "evaluation_after"):
            raw = getattr(self, name)
            if raw is None:
                continue
            try:
                parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    raise ValueError("timezone offset required")
                timestamps[name] = parsed
            except ValueError as exc:
                raise ContractError(
                    f"strategy experiment: {name} must be an ISO-8601 timestamp"
                ) from exc
        if (
            "discovery_before" in timestamps
            and "evaluation_after" in timestamps
            and timestamps["evaluation_after"] < timestamps["discovery_before"]
        ):
            raise ContractError(
                "strategy experiment: evaluation_after cannot precede discovery_before"
            )
