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
def _require_int(name: str, value: object, *, positive: bool = False) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractError(f"{name} must be an integer")
    if positive and value <= 0:
        raise ContractError(f"{name} must be positive")
    if not positive and value < 0:
        raise ContractError(f"{name} cannot be negative")


def _require_ratio(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"{name} must be numeric")
    if not 0 <= float(value) <= 1:
        raise ContractError(f"{name} must be in [0,1]")


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
            _require_int(f"context roi: {name}", getattr(self, name))
        if self.measured_runs > self.runs:
            raise ContractError("context roi: measured_runs exceeds runs")
        if self.delivered_runs > self.runs:
            raise ContractError("context roi: delivered_runs exceeds runs")
        if self.verified_runs > self.runs:
            raise ContractError("context roi: verified_runs exceeds runs")
        if self.cited_items > self.delivered_items:
            raise ContractError("context roi: cited_items exceeds delivered_items")
        if self.utilization_ratio is not None:
            _require_ratio("context roi: utilization_ratio", self.utilization_ratio)


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
        _require_int(
            "context recommendation: current_budget_bytes",
            self.current_budget_bytes,
            positive=True,
        )
        _require_int(
            "context recommendation: suggested_budget_bytes",
            self.suggested_budget_bytes,
            positive=True,
        )
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
        _require_int(
            "strategy experiment: minimum_runs",
            self.minimum_runs,
            positive=True,
        )
        _require_int(
            "strategy experiment: minimum_verified_runs",
            self.minimum_verified_runs,
            positive=True,
        )
        if self.minimum_verified_runs > self.minimum_runs:
            raise ContractError(
                "strategy experiment: minimum_verified_runs exceeds minimum_runs"
            )
        _require_int("strategy experiment: observations", self.observations)
        _require_int(
            "strategy experiment: verified_observations",
            self.verified_observations,
        )
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
