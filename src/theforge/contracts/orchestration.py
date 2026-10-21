"""OrchestrationReport: the consolidated answer of the orchestrator lane
(lf-0031, PHASE 9+12).

What it is: the deterministic, receipted summary of one ``orchestrate``
pass — which specialists discovery found, which capabilities the delegation
router justified, what each governed delegation returned, and the findings
consolidated by declared analysis class. What it is not: a claim of
correctness. Findings keep their source's declared severity/confidence;
correlation across providers is recorded (``correlated=True`` plus the
``providers`` list), never promoted into independent proof — co-occurrence
is not causality.

Buckets the spec names are literal fields:

- ``findings``: every consolidated finding carries ``finding_class``
  (STATIC | RUNTIME | ARCHITECTURAL | UNSPECIFIED — the class the emitting
  capability declared, never inferred) and ``correlated``.
- ``unresolved``: named refusals, absent specialists, runs without a
  handoff — each entry carries the ``DelegationFailure`` code and detail.
- ``recommended``: deterministic next actions derived from the refusals —
  an optional specialist that is absent is a recommendation, never a
  failure of the run.

``kind`` separates the honest stages: ``plan`` reports carry picks and
refusals but no execution evidence; ``run`` reports additionally carry
delegation stages and evidence handoffs.
"""

from dataclasses import dataclass, field
from typing import Literal

from theforge.contracts.base import ContractError
from theforge.contracts.manifest import CAPABILITY_ID, PROVIDER_ID
from theforge.contracts.specialist_delegation import (
    CORRELATION_ID,
    DELEGATION_FAILURES,
    DELEGATION_RISKS,
    DelegationFailure,
    DelegationRisk,
)

ORCHESTRATION_REPORT_SCHEMA = "theforge/OrchestrationReport/v1"

# Report classes are the declared FindingClass of the emitting capability,
# upper-cased, plus UNSPECIFIED for capabilities that declared none.
ReportClass = Literal["STATIC", "RUNTIME", "ARCHITECTURAL", "UNSPECIFIED"]

OrchestrationKind = Literal["plan", "run"]

# How far one picked delegation got: the plan pick (``planned``), an argv
# execution result (``prepared``/``completed``/``failed``/``blocked`` — the
# DelegationStage vocabulary lower-cased) or a refusal (``refused``).
EntryStatus = Literal[
    "planned", "prepared", "completed", "failed", "blocked", "refused"
]


@dataclass(frozen=True, kw_only=True)
class OrchestrationEntry:
    """One picked capability: what was selected, why, and how far it ran."""

    provider: str = field(metadata={"pattern": PROVIDER_ID.pattern})
    capability: str = field(metadata={"pattern": CAPABILITY_ID.pattern})
    status: EntryStatus = "planned"
    finding_class: ReportClass = "UNSPECIFIED"
    risks: list[DelegationRisk] = field(default_factory=list)
    justification: list[str] = field(default_factory=list)
    command: list[str] = field(default_factory=list)
    delegation_stage: str = ""
    # received | absent | invalid — whether an EvidenceHandoff was emitted.
    handoff_status: str = ""
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not PROVIDER_ID.match(self.provider):
            raise ContractError(f"invalid provider {self.provider!r}")
        if not CAPABILITY_ID.match(self.capability):
            raise ContractError(f"invalid capability {self.capability!r}")
        for risk in self.risks:
            if risk not in DELEGATION_RISKS:
                raise ContractError(f"invalid risk {risk!r}")


@dataclass(frozen=True, kw_only=True)
class OrchestrationFinding:
    """A consolidated finding: source finding(s) plus provenance.

    ``providers`` lists every specialist that reported the same finding id —
    length > 1 is the correlation the report records. Correlation is
    co-occurrence, not corroboration: each provider's contribution stays
    its own claim.
    """

    id: str
    finding_class: ReportClass
    severity: str
    confidence: str
    summary: str = ""
    providers: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    correlated: bool = False
    evidence_refs: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.id:
            raise ContractError("finding id must be non-empty")
        if not self.providers:
            raise ContractError(f"finding {self.id!r}: providers must not be empty")
        if self.correlated and len(set(self.providers)) < 2:
            raise ContractError(
                f"finding {self.id!r}: correlated requires two distinct providers"
            )


@dataclass(frozen=True, kw_only=True)
class OrchestrationUnresolved:
    """One named gap in the orchestration — never an anonymous failure."""

    code: DelegationFailure
    detail: str
    provider: str = ""

    def __post_init__(self) -> None:
        if self.code not in DELEGATION_FAILURES:
            raise ContractError(f"invalid unresolved code {self.code!r}")


@dataclass(frozen=True, kw_only=True)
class OrchestrationRecommendation:
    """A deterministic next step derived from the plan's evidence."""

    action: str
    why: str
    provider: str = ""

    def __post_init__(self) -> None:
        if not self.action or not self.why:
            raise ContractError("a recommendation needs action and why")


@dataclass(frozen=True, kw_only=True)
class OrchestrationProvenance:
    """What produced this report: discovery context, plan hash, receipts."""

    discovery_digest: str = ""
    plan_sha256: str = ""
    delegation_tasks: list[str] = field(default_factory=list)
    receipts: list[str] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class OrchestrationReport:
    """``theforge/OrchestrationReport/v1`` — the consolidated report."""

    schema: str = ORCHESTRATION_REPORT_SCHEMA
    kind: OrchestrationKind
    intent: str
    correlation_id: str = ""
    generated_at: str = ""
    plan_status: str = ""  # planned | ambiguous | unavailable | refused
    entries: list[OrchestrationEntry] = field(default_factory=list)
    findings: list[OrchestrationFinding] = field(default_factory=list)
    unresolved: list[OrchestrationUnresolved] = field(default_factory=list)
    recommended: list[OrchestrationRecommendation] = field(default_factory=list)
    provenance: OrchestrationProvenance = field(default_factory=OrchestrationProvenance)
    limitations: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != ORCHESTRATION_REPORT_SCHEMA:
            raise ContractError(
                f"unsupported schema {self.schema!r}, expected {ORCHESTRATION_REPORT_SCHEMA!r}"
            )
        if self.correlation_id and not CORRELATION_ID.match(self.correlation_id):
            raise ContractError(f"invalid correlation_id {self.correlation_id!r}")
