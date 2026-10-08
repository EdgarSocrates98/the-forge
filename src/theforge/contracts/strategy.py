"""Strategy policy + plan simulation contracts (Cycle 5, Waves Q/G/U).

``StrategyPolicy`` is the only channel by which experiment outcomes influence
future routing: it exists only for a *promoted* experiment with approval
evidence, and it goes stale the moment the provider surface it was measured
on changes. ``PlanSimulation`` is the pre-execution estimate — it never
invents costs (``cost_known`` flag) and it is hash-linked into the run receipt.
"""

from dataclasses import dataclass, field
from typing import Literal

from theforge.contracts.base import ContractError
from theforge.contracts.targets import DATA_CLASSIFICATIONS, DataClassification
from theforge.contracts.types import SHA256_RE, Producer, check_sha256

STRATEGY_POLICY_SCHEMA = "theforge/StrategyPolicy/v1"
PLAN_SIMULATION_SCHEMA = "theforge/PlanSimulation/v1"
COUNTERFACTUAL_SCHEMA = "theforge/CounterfactualPlanComparison/v1"

_MAX_LIST = 64


@dataclass(frozen=True, kw_only=True)
class StrategyPolicy:
    """A governed routing preference distilled from a promoted experiment (v1).

    ``evidence`` binds the experiment contract, its approval hash and the
    measured sample; the policy is scoped by exact surface fingerprint — a
    surface change makes the policy non-authoritative, by construction.
    """

    schema: str = STRATEGY_POLICY_SCHEMA
    producer: Producer
    created_at: str
    id: str = field(metadata={"pattern": SHA256_RE.pattern})
    capability: str = ""
    task_family: str | None = None
    surface_fingerprint: str = ""
    prefer: list[str] = field(default_factory=list, metadata={"min_items": 1})
    experiment_id: str = ""
    approval_sha256: str = field(metadata={"pattern": SHA256_RE.pattern})
    sample_runs: int = 0
    metrics: dict[str, float] = field(default_factory=dict)
    valid_from: str = ""
    valid_until: str | None = None
    stale: bool = False
    limitations: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != STRATEGY_POLICY_SCHEMA:
            raise ContractError(f"strategy policy: unsupported schema {self.schema!r}")
        check_sha256(self.id, field="strategy policy: id")
        check_sha256(self.approval_sha256, field="strategy policy: approval_sha256")
        if not self.capability or not self.surface_fingerprint or not self.experiment_id:
            raise ContractError(
                "strategy policy: capability, surface_fingerprint and experiment_id are required"
            )
        if not self.prefer:
            raise ContractError("strategy policy: prefer must not be empty")
        for entry in self.prefer:
            if not entry or len(entry) > 120:
                raise ContractError("strategy policy: prefer entries are bounded strings")
        if isinstance(self.sample_runs, bool) or not isinstance(self.sample_runs, int):
            raise ContractError("strategy policy: sample_runs must be an integer")
        if self.sample_runs <= 0:
            raise ContractError("strategy policy: sample_runs must be positive")
        for name, value in self.metrics.items():
            if not name or len(name) > 60:
                raise ContractError("strategy policy: metric names are bounded strings")
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ContractError(f"strategy policy: metric {name!r} must be numeric")
        if not self.valid_from:
            raise ContractError("strategy policy: valid_from is required")


@dataclass(frozen=True, kw_only=True)
class SimulatedNode:
    """One plan node's simulated footprint."""

    node: str
    provider: str
    capability: str
    execution_target: str | None = None
    network: Literal["none", "egress", "required", "unknown"] = "unknown"
    mutations: Literal["none", "local", "external", "unknown"] = "unknown"
    credentials: Literal["none", "required", "unknown"] = "unknown"
    verification: Literal["none", "forge", "provider", "independent"] = "none"

    def __post_init__(self) -> None:
        if not self.node or not self.provider or not self.capability:
            raise ContractError("simulated node: node/provider/capability are required")


@dataclass(frozen=True, kw_only=True)
class PlanSimulation:
    """A pre-execution estimate of a plan's footprint (v1).

    ``risk_flags`` carries the structural classifications (``local-only``,
    ``network``, ``external-mutation``, ``destructive``, ``credential-bearing``,
    ``cross-account``); ``cost`` stays ``unknown`` unless a measured model
    exists — never an invented number.
    """

    schema: str = PLAN_SIMULATION_SCHEMA
    producer: Producer
    created_at: str
    plan_sha256: str = field(metadata={"pattern": SHA256_RE.pattern})
    nodes: list[SimulatedNode] = field(default_factory=list)
    providers: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    cost: Literal["known", "unknown"] = "unknown"
    data_classification: DataClassification = "unknown"
    limitations: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != PLAN_SIMULATION_SCHEMA:
            raise ContractError(f"plan simulation: unsupported schema {self.schema!r}")
        check_sha256(self.plan_sha256, field="plan simulation: plan_sha256")
        if self.data_classification not in DATA_CLASSIFICATIONS:
            raise ContractError(
                f"plan simulation: unknown data_classification {self.data_classification!r}"
            )
        for flag in self.risk_flags:
            if not flag or len(flag) > 60:
                raise ContractError("plan simulation: risk_flags are bounded strings")
        if len(self.nodes) > _MAX_LIST or len(self.providers) > _MAX_LIST:
            raise ContractError("plan simulation: nodes/providers exceed bound")


@dataclass(frozen=True, kw_only=True)
class CounterfactualPlanComparison:
    """A bounded what-if between two plans (v1).

    Records only *known* differences, ``unknowns`` and the evidence the
    comparison drew on — a counterfactual never asserts the alternative
    "would definitely be better".
    """

    schema: str = COUNTERFACTUAL_SCHEMA
    producer: Producer
    created_at: str
    base_sha256: str = field(metadata={"pattern": SHA256_RE.pattern})
    alternative_sha256: str = field(metadata={"pattern": SHA256_RE.pattern})
    differences: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    predicted_bounds: dict[str, str] = field(default_factory=dict)
    evidence_refs: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != COUNTERFACTUAL_SCHEMA:
            raise ContractError(f"counterfactual: unsupported schema {self.schema!r}")
        for name in ("base_sha256", "alternative_sha256"):
            check_sha256(getattr(self, name), field=f"counterfactual: {name}")
        if self.base_sha256 == self.alternative_sha256:
            raise ContractError("counterfactual: base and alternative are the same plan")
        if not self.differences and not self.unknowns:
            raise ContractError("counterfactual: a comparison must record differences or unknowns")
        if len(self.differences) > _MAX_LIST or len(self.unknowns) > _MAX_LIST:
            raise ContractError("counterfactual: differences/unknowns exceed bound")
