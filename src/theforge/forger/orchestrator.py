"""The Forger: task -> route -> health -> context -> execute -> receipt.

Every artifact is persisted as soon as it exists, so a run that fails midway is
still explainable. No path reports success without a valid ExecutionResult.
"""

import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal

from theforge.context import build_context_pack, scan_workspace
from theforge.contracts import (
    Candidate,
    ContractError,
    ErrorInfo,
    ExecuteRequest,
    ExecutionReceipt,
    ExecutionResult,
    Metric,
    Metrics,
    ReceiptInputs,
    ReceiptProvider,
    RoutingDecision,
    Selection,
    TaskSpec,
    from_dict,
    to_dict,
)
from theforge.contracts.canonical import utc_now
from theforge.contracts.types import BudgetProfile, Outcome
from theforge.meta import PRODUCER, VERSION
from theforge.protocol import SubprocessTransport, TransportError, TransportFactory
from theforge.registry import Registry, RegistryRecord, check_health
from theforge.routing import MIN_SIGNAL_TYPES, route
from theforge.routing.signals import workspace_dependencies
from theforge.runs import RunStore, new_run_id

EXECUTE_TIMEOUTS: dict[str, float] = {"economy": 60.0, "balanced": 180.0, "max": 600.0}


@dataclass(frozen=True, kw_only=True)
class AskRequest:
    intent: str
    targets: list[str] = field(default_factory=lambda: ["."])
    capability: str | None = None
    action: str | None = None
    profile: BudgetProfile = "balanced"
    allow_unverified: bool = False


@dataclass(frozen=True, kw_only=True)
class AskOutcome:
    run_id: str
    status: Outcome
    decision: RoutingDecision
    receipt: ExecutionReceipt
    result: ExecutionResult | None = None
    error: ErrorInfo | None = None


@dataclass
class _Trace:
    run_id: str
    started_at: str
    task_sha: str
    routing_sha: str | None = None
    context_sha: str | None = None
    result_sha: str | None = None
    record: RegistryRecord | None = None


class Forger:
    def __init__(
        self, root: Path, registry: Registry, store: RunStore, *,
        transport_factory: TransportFactory = SubprocessTransport,
        execute_timeout: float | None = None,
    ) -> None:
        self.root = root.resolve()
        self.registry = registry
        self.store = store
        self.transport_factory = transport_factory
        self.execute_timeout = execute_timeout

    def ask(self, request: AskRequest) -> AskOutcome:
        run_id = new_run_id()
        started = utc_now()
        self.store.create(run_id)
        task = TaskSpec(
            producer=PRODUCER, created_at=started, id=run_id, intent=request.intent,
            workspace_root=str(self.root), targets=list(request.targets),
            budget_profile=request.profile, requested_capability=request.capability,
            requested_action=request.action,
        )
        trace = _Trace(run_id=run_id, started_at=started,
                       task_sha=self.store.write(run_id, "task", task))
        records = {r.entry.id: r for r in self.registry.records()}
        scan = scan_workspace(self.root, task.targets)
        decision = route(task, list(records.values()), scan.files,
                         workspace_dependencies(self.root),
                         allow_unverified=request.allow_unverified)
        if decision.status != "routed":
            trace.routing_sha = self.store.write(run_id, "routing", decision)
            return self._finish(trace, decision, decision.status)

        decision, record, health_error = self._select_healthy(decision, records)
        trace.routing_sha = self.store.write(run_id, "routing", decision)
        if record is None or record.manifest is None:
            return self._finish(trace, decision, "provider_failure", error=health_error)
        trace.record = record

        selection = decision.selected[0]
        capability = record.manifest.capability(selection.capability)
        globs = list(capability.signals.file_globs) if capability else []
        pack = build_context_pack(task, record.entry.id, globs, scan)
        trace.context_sha = self.store.write(run_id, "context", pack)

        payload = to_dict(ExecuteRequest(task=task, capability=selection.capability,
                                         action=selection.action, context=pack))
        started_exec = time.perf_counter()
        try:
            response = self.transport_factory(record.entry.argv).call(
                "execute", payload, timeout=self._timeout(task),
                cwd=self.store.work_dir(run_id))
        except TransportError as exc:
            return self._finish(trace, decision, "provider_failure",
                                error=ErrorInfo(code=exc.code, detail=exc.detail))
        duration_ms = (time.perf_counter() - started_exec) * 1000

        if response.status in ("refused", "error"):
            status: Outcome = "refused" if response.status == "refused" else "provider_failure"
            error = response.error or ErrorInfo(code="FORGE-PROTO-SCHEMA",
                                                detail="error response without error body")
            return self._finish(trace, decision, status, error=error)
        try:
            result = from_dict(ExecutionResult, response.payload, "$.payload")
        except ContractError as exc:
            return self._finish(trace, decision, "provider_failure", error=ErrorInfo(
                code="FORGE-PROTO-SCHEMA", detail=f"execute: {exc}"))
        result_status: Literal["ok", "partial"] = "ok" if response.status == "ok" else "partial"
        result = replace(result, status=result_status, metrics=Metrics(
            duration_ms=Metric(value=round(duration_ms, 3), kind="measured"),
            context_bytes=Metric(value=float(pack.used_bytes), kind="measured"),
            tokens=Metric(value=None, kind="unknown"),
        ))
        trace.result_sha = self.store.write(run_id, "result", result)
        return self._finish(trace, decision, result_status, result=result)

    def _timeout(self, task: TaskSpec) -> float:
        if self.execute_timeout is not None:
            return self.execute_timeout
        return EXECUTE_TIMEOUTS[task.budget_profile]

    def _select_healthy(
        self, decision: RoutingDecision, records: dict[str, RegistryRecord]
    ) -> tuple[RoutingDecision, RegistryRecord | None, ErrorInfo | None]:
        primary = decision.selected[0]
        tried: list[str] = []
        last_error: ErrorInfo | None = None
        for candidate in self._fallback_order(decision):
            record = records[candidate.provider]
            health = check_health(record, transport_factory=self.transport_factory,
                                  allow_unverified=self.registry.allow_unverified)
            if health.error is None:
                if not tried:
                    return decision, record, None
                capability = (record.manifest.capability(candidate.capability)
                              if record.manifest else None)
                action = primary.action
                if capability is not None and action not in capability.actions:
                    action = capability.default_action
                switched = replace(
                    decision,
                    selected=[Selection(provider=candidate.provider,
                                        capability=candidate.capability, action=action)],
                    fallbacks_used=tried,
                    reason=f"{decision.reason}; fallback to {candidate.provider} after "
                           f"unhealthy {', '.join(tried)}",
                )
                return switched, record, None
            tried.append(f"{candidate.provider}:{health.error.code}")
            last_error = health.error
        return replace(decision, fallbacks_used=tried), None, last_error

    @staticmethod
    def _fallback_order(decision: RoutingDecision) -> list[Candidate]:
        primary = decision.selected[0]
        key = (primary.provider, primary.capability)
        first = [c for c in decision.candidates if (c.provider, c.capability) == key]
        rest = [c for c in decision.candidates
                if (c.provider, c.capability) != key
                and (len(c.rank_key) == 1 or c.rank_key[0] >= MIN_SIGNAL_TYPES)]
        return first + rest

    def _finish(
        self, trace: _Trace, decision: RoutingDecision, status: Outcome, *,
        result: ExecutionResult | None = None, error: ErrorInfo | None = None,
    ) -> AskOutcome:
        record = trace.record
        provider = None
        if record is not None and record.manifest is not None:
            provider = ReceiptProvider(id=record.entry.id, version=record.manifest.version,
                                       trust=record.entry.trust,
                                       manifest_sha256=record.manifest_sha256)
        receipt = ExecutionReceipt(
            producer=PRODUCER, created_at=utc_now(), status=status, run_id=trace.run_id,
            forge_version=VERSION,
            inputs=ReceiptInputs(task_sha256=trace.task_sha, routing_sha256=trace.routing_sha,
                                 context_sha256=trace.context_sha),
            provider=provider, result_sha256=trace.result_sha, started_at=trace.started_at,
            finished_at=utc_now(), error=error,
        )
        self.store.write(trace.run_id, "receipt", receipt)
        return AskOutcome(run_id=trace.run_id, status=status, decision=decision,
                          receipt=receipt, result=result, error=error)
