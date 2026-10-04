"""ExecutionPlan, PlanResult and the payloads of the `plan` op.

Local invariants live here (schema, status <-> violations, inferred dependency names
its rule). Relational invariants (unique/valid ids, existing dependencies, cycles,
inputs within dependencies, node limit, reserved patterns) are checked by
``validate_plan_structure`` so that every violation is reported at once.
"""

import re
from dataclasses import dataclass, field
from typing import Final, Literal

from theforge.contracts.base import ContractError
from theforge.contracts.result import Finding
from theforge.contracts.task import TaskSpec
from theforge.contracts.types import (
    BudgetProfile,
    ErrorInfo,
    OperationClass,
    Outcome,
    PlanPattern,
    Producer,
)
from theforge.contracts.verification import ReproducibilityInfo

PLAN_SCHEMA = "theforge/ExecutionPlan/v1"
PLAN_RESULT_SCHEMA = "theforge/PlanResult/v1"
# Format of a plan node id (checked relationally, so it is reported as a violation).
PLAN_NODE_ID: Final = re.compile(r"^[a-z][a-z0-9-]{0,31}$")

NodeRole = Literal["producer", "consumer", "standalone"]
NodeStatus = Literal["ok", "partial", "refused", "provider_failure", "no_route", "skipped"]


@dataclass(frozen=True, kw_only=True)
class PlanDependency:
    node: str  # node this one depends on
    epistemic: Literal["explicit", "inferred"]
    rule: str | None = None  # required when inferred (e.g. "intent-order")
    evidence: str  # e.g. "keyword 'spark'@3 < keyword 'api'@9" or "plan file"

    def __post_init__(self) -> None:
        if self.epistemic == "inferred" and not self.rule:
            raise ContractError(f"inferred dependency on {self.node!r}: rule is required")


@dataclass(frozen=True, kw_only=True)
class PlanEstimate:
    """Response payload of the `plan` op (crosses the protocol: open schema)."""

    context_needed: list[str] = field(default_factory=list)  # relative paths or globs
    operation_class: OperationClass | None = None
    expected_artifacts: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class PlanNode:
    id: str
    role: NodeRole
    provider: str
    capability: str
    action: str
    targets: list[str] = field(default_factory=lambda: ["."])  # context input
    depends_on: list[PlanDependency] = field(default_factory=list)
    inputs: list[str] = field(default_factory=list)  # artifact input: ids within depends_on
    estimate: PlanEstimate | None = None
    limitations: list[str] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class PlanViolation:
    code: str  # a Codes.PLAN_* value
    node: str | None
    detail: str


@dataclass(frozen=True, kw_only=True)
class ExecutionPlan:
    schema: str = PLAN_SCHEMA
    producer: Producer
    created_at: str
    status: Literal["validated", "rejected"]
    plan_run: str
    task_id: str
    pattern: PlanPattern
    source: Literal["decomposed", "file"]
    profile: BudgetProfile
    nodes: list[PlanNode]
    violations: list[PlanViolation] = field(default_factory=list)  # empty <=> validated
    limitations: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != PLAN_SCHEMA:
            raise ContractError(f"unsupported schema {self.schema!r}, expected {PLAN_SCHEMA!r}")
        if (self.status == "validated") == bool(self.violations):
            raise ContractError(f"plan status {self.status!r} does not match "
                                f"{len(self.violations)} violations")


@dataclass(frozen=True, kw_only=True)
class PlanRequest:
    """Request payload of the `plan` op (crosses the protocol: open schema)."""

    task: TaskSpec
    capability: str
    action: str


@dataclass(frozen=True, kw_only=True)
class NodeOutcome:
    node: str
    status: NodeStatus
    run_id: str | None = None  # None when skipped
    receipt_sha256: str | None = None
    result_sha256: str | None = None
    blocked_by: str | None = None  # required when skipped (validate_plan_result)
    error: ErrorInfo | None = None
    reproducibility: ReproducibilityInfo | None = None


@dataclass(frozen=True, kw_only=True)
class SynthesisNode:
    node: str
    provider: str
    capability: str
    action: str
    status: NodeStatus
    run_id: str | None
    findings: list[Finding] = field(default_factory=list)  # copies, original ids
    evidence_by_epistemic: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class SynthesisHandoff:
    source: str
    target: str
    items: int
    truncated: bool


@dataclass(frozen=True, kw_only=True)
class Synthesis:
    nodes: list[SynthesisNode]
    handoffs: list[SynthesisHandoff] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)  # "<node>: <status> <code>: <detail>"
    limitations: list[str] = field(default_factory=list)  # aggregated, "<node>: " prefix
    unknowns: list[str] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class PlanResult:
    schema: str = PLAN_RESULT_SCHEMA
    producer: Producer
    created_at: str
    status: Outcome  # ok | partial | refused | provider_failure
    plan_run: str
    order: list[str]  # effective execution order
    nodes: list[NodeOutcome]
    synthesis: Synthesis
    reproducibility: ReproducibilityInfo
    limitations: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != PLAN_RESULT_SCHEMA:
            raise ContractError(
                f"unsupported schema {self.schema!r}, expected {PLAN_RESULT_SCHEMA!r}")
