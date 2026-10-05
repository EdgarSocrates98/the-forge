"""ExplainReportBuilder: the versioned ``explain`` report of a persisted run (requirement 11).

Read-only over the run directory: every artifact is read once, redacted again (defence in
depth against an artifact edited on disk) and kept verbatim under ``artifacts.<name>`` so
the Wave B/C text renderer keeps working on the same data. Typed sections are parsed from
those raw artifacts; an artifact that is absent leaves its section None and listed in
``not_recorded`` (runs written before a section existed, 15.4); one that cannot be read or
parsed is also listed there, dropped from ``artifacts`` and noted as an
``explain-unreadable: <name>`` limitation (its divergence, if hashed, is in ``integrity``).

Sections expected of each kind: an ``ask`` (or plan node) run has task, routing, context,
provider, result, risk, telemetry, verification and reproducibility; a plan run has task,
routing, plan, workspace-descriptor, plan-result, graph, telemetry and reproducibility
(installation only exists when a provider was missing). A missing reproducibility is
``unknown`` with reason ``not recorded`` (14.4).
"""

from collections import Counter
from typing import Any, Final, TypeVar

from theforge.contracts import (
    ContextPack,
    ExecutionReceipt,
    ExecutionResult,
    ExplainReport,
    RoutingDecision,
    TaskSpec,
    from_dict,
)
from theforge.contracts.base import ContractError
from theforge.contracts.canonical import utc_now
from theforge.contracts.codes import family_of
from theforge.contracts.explain import (
    ContextSection,
    PlanSection,
    ProviderSection,
    ResultSection,
    RoutingSection,
)
from theforge.contracts.installation import InstallationPlan
from theforge.contracts.plan import ExecutionPlan, PlanResult
from theforge.contracts.verification import ReproducibilityInfo, VerificationResult
from theforge.contracts.workspace import WorkspaceDescriptor
from theforge.errors import PersistenceError
from theforge.explain.hashcheck import verify_run_hashes
from theforge.meta import PRODUCER
from theforge.runs import ARTIFACT_TYPES, ARTIFACTS, RunStore
from theforge.security.redact import redact

T = TypeVar("T")

# Wave B routing notes, kept verbatim in RoutingSection.notes.
ROUTING_NOTE_PREFIXES: Final = ("capability-alias", "capability-deprecated",
                                "capability-overlap")
UNREADABLE_PREFIX: Final = "explain-unreadable:"
_DRIFT_PREFIX: Final = "context-drift:"
_ROUNDS: Final = ("context-r1", "context-r2")
_SIGNAL_KINDS: Final = ("dependencies", "file_globs", "keywords")
RUN_SECTIONS: Final = ("task", "routing", "context", "provider", "result", "risk",
                       "telemetry", "verification", "reproducibility")
PLAN_SECTIONS: Final = ("task", "routing", "plan", "workspace-descriptor", "plan-result",
                        "graph", "telemetry", "reproducibility")
_PLAN_ARTIFACTS: Final = ("plan", "plan-result", "workspace-descriptor", "graph")
NOT_RECORDED_REASON: Final = "not recorded"


class _Artifacts:
    """The run's artifacts read once: raw (redacted) by name, and which were unreadable."""

    def __init__(self, store: RunStore, run_id: str) -> None:
        self.raw: dict[str, Any] = {}
        self.unreadable: list[str] = []
        for name in ARTIFACTS:
            try:
                data = store.read_optional(run_id, name)
            except PersistenceError:
                self.unreadable.append(name)
                continue
            if data is not None:
                self.raw[name] = redact(data)

    def typed(self, name: str, cls: type[T]) -> T | None:
        data = self.raw.get(name)
        if data is None:
            return None
        try:
            return from_dict(cls, data, f"$.{name}", strict=True)
        except ContractError:
            del self.raw[name]
            self.unreadable.append(name)
            return None


def _routing(decision: RoutingDecision) -> RoutingSection:
    selected = {(s.provider, s.capability) for s in decision.selected}
    signals: list[str] = []
    for candidate in decision.candidates:
        if (candidate.provider, candidate.capability) not in selected:
            continue
        for kind in _SIGNAL_KINDS:
            for hit in getattr(candidate.matched, kind):
                if (signal := f"{kind}:{hit}") not in signals:
                    signals.append(signal)
    return RoutingSection(
        status=decision.status, pattern=decision.pattern, reason=decision.reason,
        confidence=decision.confidence.level, signals=signals,
        candidates=list(decision.candidates), selected=list(decision.selected),
        fallbacks=list(decision.fallbacks_used),
        notes=[note for note in decision.limitations
               if note.startswith(ROUTING_NOTE_PREFIXES)])


def _drift(telemetry: dict[str, Any] | None, receipt: ExecutionReceipt | None) -> list[str]:
    """Drifted paths: the run telemetry, else the receipt ``context-drift:`` limitations."""
    if telemetry is not None:
        return [str(path) for path in telemetry.get("context_drift") or []]
    if receipt is None:
        return []
    return [note.removeprefix(_DRIFT_PREFIX).strip() for note in receipt.limitations
            if note.startswith(_DRIFT_PREFIX)]


def _context(pack: ContextPack, rounds: int, drift: list[str]) -> ContextSection:
    workspace = pack.workspace
    return ContextSection(
        budget_bytes=pack.budget_bytes, used_bytes=pack.used_bytes, files=len(pack.files),
        excluded=len(pack.excluded), truncated=pack.truncated,
        tier_bytes=dict(pack.tier_bytes), rounds=rounds,
        unmatched=workspace.unmatched_files if workspace else None,
        git=workspace.git if workspace else None, drift=drift)


def _result(result: ExecutionResult) -> ResultSection:
    by_epistemic = Counter(evidence.epistemic for evidence in result.evidence)
    return ResultSection(status=result.status, findings=list(result.findings),
                         evidence_by_epistemic=dict(sorted(by_epistemic.items())),
                         artifacts=len(result.artifacts),
                         duration_ms=result.metrics.duration_ms)


def _plan(found: _Artifacts) -> PlanSection | None:
    plan = found.typed("plan", ExecutionPlan)
    result = found.typed("plan-result", PlanResult)
    descriptor = found.typed("workspace-descriptor", WorkspaceDescriptor)
    installation = found.typed("installation", InstallationPlan)
    if plan is None:
        return None
    return PlanSection(plan=plan, result=result, workspace_descriptor=descriptor,
                       installation=installation)


def build_explain_report(store: RunStore, run_id: str, *,
                         created_at: str | None = None) -> ExplainReport:
    """The ``ExplainReport`` of run ``run_id``; reads only, never starts a provider.

    Raises ``ValueError`` for a malformed run id and ``LookupError`` for an unknown run.
    ``created_at`` fixes the report time (byte-identical re-renders); default: now.
    """
    if not store.run_dir(run_id).is_dir():
        raise LookupError(f"unknown run {run_id}")
    found = _Artifacts(store, run_id)
    receipt = found.typed("receipt", ExecutionReceipt)
    task = found.typed("task", TaskSpec)
    decision = found.typed("routing", RoutingDecision)
    pack = found.typed("context", ContextPack)
    result = found.typed("result", ExecutionResult)
    verification = found.typed("verification", VerificationResult)
    for name in ("risk", "telemetry", *_ROUNDS, "handoff", "graph", "diagnostic",
                 "decision"):
        found.typed(name, ARTIFACT_TYPES[name])  # drop the ones that do not parse
    plan = _plan(found)
    telemetry = found.raw.get("telemetry")
    is_plan = (receipt.kind == "plan" if receipt is not None
               else any(name in found.raw for name in _PLAN_ARTIFACTS))
    rounds = sum(1 for name in _ROUNDS if name in found.raw)
    error = receipt.error if receipt is not None else None
    reproducibility = receipt.reproducibility if receipt is not None else None

    sections: dict[str, bool] = {
        "receipt": receipt is not None, "task": task is not None,
        "routing": decision is not None, "context": pack is not None,
        "provider": receipt is not None and receipt.provider is not None,
        "result": result is not None, "risk": "risk" in found.raw,
        "telemetry": telemetry is not None, "verification": verification is not None,
        "reproducibility": reproducibility is not None, "plan": plan is not None,
        "workspace-descriptor": plan is not None and plan.workspace_descriptor is not None,
        "plan-result": plan is not None and plan.result is not None,
        "graph": "graph" in found.raw,
    }
    expected = ("receipt", *(PLAN_SECTIONS if is_plan else RUN_SECTIONS))
    not_recorded = [name for name in expected if not sections[name]]
    not_recorded += [name for name in found.unreadable if name not in not_recorded]

    provider = receipt.provider if receipt is not None else None
    return ExplainReport(
        producer=PRODUCER, created_at=created_at or utc_now(), run_id=run_id,
        kind="plan" if is_plan else "run",
        status=receipt.status if receipt is not None else None,
        intent=task.intent if task else None,
        targets=list(task.targets) if task else [],
        profile=task.budget_profile if task else None,
        routing=_routing(decision) if decision else None,
        context=(_context(pack, rounds, _drift(telemetry, receipt)) if pack else None),
        provider=(ProviderSection(id=provider.id, version=provider.version,
                                  trust=provider.trust,
                                  observed_version=provider.observed_version,
                                  fingerprint=provider.fingerprint)
                  if provider is not None else None),
        result=_result(result) if result else None,
        risk=found.raw.get("risk"), telemetry=telemetry, verification=verification,
        reproducibility=reproducibility or ReproducibilityInfo(
            level="unknown", reasons=[NOT_RECORDED_REASON]), plan=plan,
        parent_run=receipt.parent_run if receipt else None,
        replay_of=receipt.replay_of if receipt else None,
        error=error, error_family=family_of(error.code) if error else None,
        integrity=verify_run_hashes(store, run_id),
        limitations=[*(receipt.limitations if receipt else []),
                     *(f"{UNREADABLE_PREFIX} {name}" for name in found.unreadable)],
        unknowns=list(receipt.unknowns) if receipt else [],
        not_recorded=not_recorded, artifacts=dict(found.raw))

