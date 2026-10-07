"""ExplainReport: the stable structure of ``theforge explain --json``.

Version rule: new fields are only added as optional with a default; removing a field or
changing its type requires ``ExplainReport/v2``. Sections without recorded data are
None and listed in ``not_recorded``; raw redacted artifacts stay under ``artifacts``.
"""

from dataclasses import dataclass, field
from typing import Any, Literal

from theforge.contracts.base import ContractError
from theforge.contracts.context import GitSummary
from theforge.contracts.installation import InstallationPlan
from theforge.contracts.plan import ExecutionPlan, PlanResult
from theforge.contracts.result import Finding, ProviderReceipt
from theforge.contracts.routing import Candidate, Selection
from theforge.contracts.types import ErrorInfo, Metric, Producer
from theforge.contracts.verification import ReproducibilityInfo, VerificationResult
from theforge.contracts.workspace import WorkspaceDescriptor

EXPLAIN_SCHEMA = "theforge/ExplainReport/v1"


@dataclass(frozen=True, kw_only=True)
class Divergence:
    artifact: str  # artifact name, "work/<path>" or "<child_run>/receipt"
    kind: Literal["modified", "missing", "unreadable"]
    expected: str | None = None
    actual: str | None = None


@dataclass(frozen=True, kw_only=True)
class IntegrityReport:
    checked: list[str] = field(default_factory=list)
    divergences: list[Divergence] = field(default_factory=list)
    unrecorded: list[str] = field(default_factory=list)  # present without a recorded hash


@dataclass(frozen=True, kw_only=True)
class RoutingSection:
    status: str
    pattern: str
    reason: str
    confidence: str
    signals: list[str]
    candidates: list[Candidate]
    selected: list[Selection]
    fallbacks: list[str]
    # Wave B notes kept verbatim from RoutingDecision.limitations (capability-alias...).
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class ContextSection:
    budget_bytes: int
    used_bytes: int
    files: int
    excluded: int
    truncated: bool
    tier_bytes: dict[str, int]
    rounds: int
    unmatched: int | None = None  # WorkspaceSummary.unmatched_files (Wave C)
    git: GitSummary | None = None  # WorkspaceSummary.git (Wave C)
    drift: list[str] = field(default_factory=list)  # context drift (Wave C)
    # Items per tier/signals and exclusions are not duplicated: see artifacts.context*.


@dataclass(frozen=True, kw_only=True)
class ProviderSection:
    id: str
    version: str
    trust: str
    observed_version: str | None = None
    fingerprint: str | None = None
    surface_fingerprint: str | None = None
    native_surface_fingerprint: str | None = None
    # The provider-native receipt/explain pointer of this run (nested explain
    # drill-down), copied from the run receipt. None when the run carried none.
    provider_receipt: ProviderReceipt | None = None


@dataclass(frozen=True, kw_only=True)
class ResultSection:
    status: str
    findings: list[Finding]
    evidence_by_epistemic: dict[str, int]
    artifacts: int
    duration_ms: Metric


@dataclass(frozen=True, kw_only=True)
class PlanSection:
    plan: ExecutionPlan
    result: PlanResult | None = None
    workspace_descriptor: WorkspaceDescriptor | None = None  # workspace-descriptor artifact
    installation: InstallationPlan | None = None


@dataclass(frozen=True, kw_only=True)
class ExplainReport:
    schema: str = EXPLAIN_SCHEMA
    producer: Producer
    created_at: str
    run_id: str
    kind: Literal["run", "plan"]
    status: str | None  # receipt Outcome; None when not recorded
    intent: str | None = None
    targets: list[str] = field(default_factory=list)
    profile: str | None = None
    routing: RoutingSection | None = None
    context: ContextSection | None = None
    provider: ProviderSection | None = None
    result: ResultSection | None = None
    risk: dict[str, Any] | None = None  # raw RiskAssessment (Wave A)
    telemetry: dict[str, Any] | None = None  # raw RunTelemetry (Wave C), plan runs too
    verification: VerificationResult | None = None
    reproducibility: ReproducibilityInfo  # "unknown" when not recorded
    plan: PlanSection | None = None
    parent_run: str | None = None
    replay_of: str | None = None
    resumed_from: str | None = None  # the plan run this run resumed (receipt field)
    error: ErrorInfo | None = None
    error_family: str | None = None
    integrity: IntegrityReport
    limitations: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    not_recorded: list[str] = field(default_factory=list)  # sections without recorded data
    artifacts: dict[str, Any] = field(default_factory=dict)  # raw redacted artifacts by name

    def __post_init__(self) -> None:
        if self.schema != EXPLAIN_SCHEMA:
            raise ContractError(
                f"unsupported schema {self.schema!r}, expected {EXPLAIN_SCHEMA!r}")
