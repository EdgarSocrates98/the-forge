"""The Forger: task -> route -> revalidate -> health -> policy -> context -> execute -> receipt.

Every artifact is persisted as soon as it exists, so a run that fails midway is
still explainable. The routing artifact is the exception: it is written once, with the
final decision (after registry revalidation and fallback). No path reports success
without a valid ExecutionResult.
"""

import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal

from theforge.context import build_context_pack, scan_workspace
from theforge.contracts import (
    Candidate,
    Capability,
    Confidence,
    ContractError,
    ErrorInfo,
    ExecuteRequest,
    ExecutionReceipt,
    ExecutionResult,
    IntegrityError,
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
from theforge.contracts.codes import Codes
from theforge.contracts.integrity import (
    check_producer,
    validate_context_pack,
    validate_result,
)
from theforge.contracts.types import BudgetProfile, Outcome, Producer
from theforge.errors import PersistenceError, UsageError
from theforge.meta import PRODUCER, VERSION
from theforge.policy import assess_dimensions, build_risk_assessment, evaluate, load_policy
from theforge.protocol import SubprocessTransport, TransportError, TransportFactory
from theforge.registry import (
    ProviderFingerprint,
    Registry,
    RegistryRecord,
    RevalidationOutcome,
    check_health,
    fingerprint,
    user_config_dir,
)
from theforge.routing import MIN_SIGNAL_TYPES, route
from theforge.routing.router import EXECUTE_OP
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
    approvals: frozenset[str] = frozenset()  # capability ids explicitly approved (--approve)


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
    risk_sha: str | None = None
    record: RegistryRecord | None = None
    identity: ProviderFingerprint | None = None
    decision: RoutingDecision | None = None
    limitations: list[str] = field(default_factory=list)


def _offers(record: RegistryRecord, capability_id: str, action: str) -> bool:
    capability = record.manifest.capability(capability_id) if record.manifest else None
    return capability is not None and action in capability.actions


def _require_op(record: RegistryRecord, op: str) -> ErrorInfo | None:
    """``None`` when the provider declares ``op``, else the unsupported-op error (2.1)."""
    if record.manifest is not None and op in record.manifest.ops:
        return None
    declared = ", ".join(record.manifest.ops) if record.manifest else "none"
    return ErrorInfo(code=Codes.PROTO_OP_UNSUPPORTED,
                     detail=f"{record.entry.id} does not declare op {op!r} (ops: {declared})")


def _unexecutable_request(
    task: TaskSpec, records: dict[str, RegistryRecord], allow_unverified: bool
) -> ErrorInfo | None:
    """2.1: an explicitly requested capability is refused with the unsupported-op code only
    when a routable provider declares it without ``execute`` and no other provider could be
    the one to run it: no declarer with ``execute`` (whatever its trust or state) and no
    non-blocked provider whose manifest is unknown. Otherwise the plain ``no_route`` (and its
    reason) stands. Nothing is spawned.
    """
    cap_id = task.requested_capability
    if not cap_id:
        return None
    blamed: ErrorInfo | None = None
    for record in sorted(records.values(), key=lambda r: r.entry.id):
        if record.entry.trust == "blocked":
            continue
        if record.manifest is None:
            return None  # unknown (not described, unreachable): it might be the executor
        capability = record.manifest.capability(cap_id)
        if capability is None or capability.state == "unsupported":
            continue
        error = _require_op(record, EXECUTE_OP)
        if error is None:
            return None  # an executing declarer exists; it was excluded for another reason
        if blamed is None and record.routable(allow_unverified):
            blamed = error
    return blamed


@dataclass(frozen=True)
class _Routed:
    decision: RoutingDecision
    records: dict[str, RegistryRecord]
    error: ErrorInfo | None = None


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
        try:
            return self._run(trace, task, request)
        except UsageError as exc:
            self._finish(trace, self._placeholder(run_id, f"usage error: {exc}"), "no_route",
                         error=ErrorInfo(code=Codes.USAGE, detail=str(exc)))
            raise
        except PersistenceError:
            raise
        except Exception as exc:  # noqa: BLE001 - invariant: a persisted task always gets a receipt
            error = ErrorInfo(code=Codes.INTERNAL, detail=f"{type(exc).__name__}: {exc}")
            decision = trace.decision or self._placeholder(
                run_id, f"internal error: {error.detail}")
            return self._finish(trace, decision, "provider_failure", error=error)

    @staticmethod
    def _placeholder(run_id: str, reason: str) -> RoutingDecision:
        return RoutingDecision(status="no_route", reason=reason, confidence=Confidence(level="low"),
                               task_id=run_id, producer=PRODUCER, created_at=utc_now())

    def _run(self, trace: _Trace, task: TaskSpec, request: AskRequest) -> AskOutcome:
        run_id = trace.run_id
        scan = scan_workspace(self.root, task.targets)
        routed = self._final_route(trace, task, request, scan.files)
        decision, records = routed.decision, routed.records
        if routed.error is not None:
            trace.routing_sha = self.store.write(run_id, "routing", decision)
            return self._finish(trace, decision, "provider_failure", error=routed.error)
        if decision.status != "routed":
            trace.routing_sha = self.store.write(run_id, "routing", decision)
            op_error = _unexecutable_request(task, records, request.allow_unverified)
            if op_error is not None:
                return self._finish(trace, decision, "refused", error=op_error)
            return self._finish(trace, decision, decision.status)

        decision, record, health_error = self._select_healthy(task, decision, records)
        trace.decision = decision
        trace.routing_sha = self.store.write(run_id, "routing", decision)
        if record is None or record.manifest is None:
            return self._finish(trace, decision, "provider_failure", error=health_error)
        trace.record = record
        trace.identity = fingerprint(record.entry)
        op_error = _require_op(record, EXECUTE_OP)
        if op_error is not None:
            return self._finish(trace, decision, "refused", error=op_error)

        selection = decision.selected[0]
        capability = record.manifest.capability(selection.capability)
        if capability is None:  # the router only selects declared capabilities
            raise RuntimeError(f"{record.entry.id} does not declare {selection.capability!r}")
        policy_error = self._apply_policy(trace, request, record, capability, selection)
        if policy_error is not None:
            return self._finish(trace, decision, "refused", error=policy_error)

        globs = list(capability.signals.file_globs)
        pack = build_context_pack(task, record.entry.id, globs, scan)
        try:
            validate_context_pack(pack)
        except IntegrityError as exc:  # the core built it: an internal error, never sent (1.7)
            return self._finish(trace, decision, "provider_failure", error=ErrorInfo(
                code=Codes.INTERNAL, detail=f"inconsistent context pack: {exc}"))
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

        expected = Producer(id=record.entry.id, version=record.manifest.version)
        # The envelope is checked like describe/health (1.6) before its status is trusted.
        envelope = check_producer(response.producer, expected=expected, field="$.producer")
        if envelope is not None:
            return self._finish(trace, decision, "provider_failure", error=ErrorInfo(
                code=envelope.code, detail=f"execute: {envelope.detail}", field=envelope.field))
        if response.status in ("refused", "error"):
            status: Outcome = "refused" if response.status == "refused" else "provider_failure"
            error = response.error or ErrorInfo(code=Codes.PROTO_SCHEMA,
                                                detail="error response without error body")
            return self._finish(trace, decision, status, error=error)
        try:
            result = from_dict(ExecutionResult, response.payload, "$.payload")
        except ContractError as exc:
            return self._finish(trace, decision, "provider_failure", error=ErrorInfo(
                code=Codes.PROTO_SCHEMA, detail=f"execute: {exc}"))
        try:  # relational invariants and producer id+version; invalid results are not persisted
            validate_result(result, expected=expected)
        except IntegrityError as exc:
            return self._finish(trace, decision, "provider_failure", error=ErrorInfo(
                code=exc.code, detail=f"execute: {exc}", field=exc.field))
        result_status: Literal["ok", "partial"] = "ok" if response.status == "ok" else "partial"
        result = replace(result, status=result_status, metrics=Metrics(
            duration_ms=Metric(value=round(duration_ms, 3), kind="measured"),
            context_bytes=Metric(value=float(pack.used_bytes), kind="measured"),
            tokens=Metric(value=None, kind="unknown"),
        ))
        trace.result_sha = self.store.write(run_id, "result", result)
        return self._finish(trace, decision, result_status, result=result)

    def _apply_policy(
        self, trace: _Trace, request: AskRequest, record: RegistryRecord,
        capability: Capability, selection: Selection,
    ) -> ErrorInfo | None:
        """Decide allow/ask/deny and persist the risk before any execute process (6.1-6.4).

        Only routable providers reach this point: ``blocked`` ones are excluded by the router.
        """
        assert record.manifest is not None
        warnings: list[str] = []
        config = load_policy(user_dir=self.registry.user_dir or user_config_dir(),
                             forge_dir=self.root / ".forge", warnings=warnings)
        trace.limitations.extend(f"policy: {w}" for w in warnings)
        dimensions = assess_dimensions(operation_class=capability.operation_class,
                                       execution=record.manifest.execution)
        policy = evaluate(dimensions=dimensions, trust=record.entry.trust, config=config,
                          approved=capability.id in request.approvals, capability=capability.id)
        risk = build_risk_assessment(run_id=trace.run_id, provider_id=record.entry.id,
                                     capability=capability, action=selection.action,
                                     dimensions=dimensions, decision=policy)
        trace.risk_sha = self.store.write(trace.run_id, "risk", risk)
        if policy.decision == "ask":
            return ErrorInfo(code=Codes.POLICY_APPROVAL_REQUIRED, detail=policy.reason,
                             unlock=policy.unlock)
        if policy.decision == "deny":
            return ErrorInfo(code=Codes.POLICY_DENIED, detail=policy.reason)
        return None

    def _final_route(
        self, trace: _Trace, task: TaskSpec, request: AskRequest, files: list[str]
    ) -> _Routed:
        """Route, revalidate every scored candidate and route again at most once (4.3).

        ``changed`` providers are invalidated and rediscovered; ``unreachable`` ones are
        excluded from the redone decision. A ``changed`` on the redone decision is a second
        divergence and fails the run. ``no_route`` is final and never revalidated.
        """
        dependencies = workspace_dependencies(self.root)

        def do_route(records: dict[str, RegistryRecord]) -> RoutingDecision:
            decision = route(task, list(records.values()), files, dependencies,
                             allow_unverified=request.allow_unverified)
            trace.decision = decision
            return decision

        records = {r.entry.id: r for r in self.registry.records()}
        decision = do_route(records)
        if decision.status == "no_route":
            return _Routed(decision, records)
        outcomes = self._revalidate(decision)
        changed = sorted(o.record.entry.id for o in outcomes if o.status == "changed")
        unreachable = sorted(o.record.entry.id for o in outcomes if o.status == "unreachable")
        if not changed and not unreachable:
            return _Routed(decision, records)

        for provider_id in changed:
            self.registry.invalidate(provider_id)
        records = {r.entry.id: r for r in self.registry.records()}
        for outcome in outcomes:
            if outcome.status == "unreachable":
                records[outcome.record.entry.id] = outcome.record
        decision = do_route(records)
        notes = [f"registry-revalidated: {', '.join(changed)}"] if changed else []
        if unreachable:
            notes.append(f"registry-unreachable: {', '.join(unreachable)}")
        decision = replace(decision, limitations=[*decision.limitations, *notes])
        trace.decision = decision
        if decision.status == "no_route":
            return _Routed(decision, records)
        again = sorted(o.record.entry.id for o in self._revalidate(decision)
                       if o.status == "changed")
        if again:
            return _Routed(decision, records, ErrorInfo(
                code=Codes.REGISTRY_MANIFEST_CHANGED,
                detail=f"manifest of {', '.join(again)} changed again after the registry "
                       "was rediscovered; refusing to route on an unstable registry"))
        return _Routed(decision, records)

    def _revalidate(self, decision: RoutingDecision) -> list[RevalidationOutcome]:
        provider_ids = sorted({c.provider for c in decision.candidates})
        return self.registry.revalidate(provider_ids) if provider_ids else []

    def _timeout(self, task: TaskSpec) -> float:
        if self.execute_timeout is not None:
            return self.execute_timeout
        return EXECUTE_TIMEOUTS[task.budget_profile]

    def _select_healthy(
        self, task: TaskSpec, decision: RoutingDecision, records: dict[str, RegistryRecord]
    ) -> tuple[RoutingDecision, RegistryRecord | None, ErrorInfo | None]:
        primary = decision.selected[0]
        tried: list[str] = []
        last_error: ErrorInfo | None = None
        for candidate in self._fallback_order(task, decision, records):
            record = records[candidate.provider]
            health = check_health(record, transport_factory=self.transport_factory,
                                  allow_unverified=self.registry.allow_unverified)
            if health.error is None:
                if not tried:
                    return decision, record, None
                switched = replace(
                    decision,
                    selected=[Selection(provider=candidate.provider,
                                        capability=candidate.capability, action=primary.action)],
                    fallbacks_used=tried,
                    reason=f"{decision.reason}; fallback to {candidate.provider} after "
                           f"unhealthy {', '.join(tried)}",
                )
                return switched, record, None
            tried.append(f"{candidate.provider}:{health.error.code}")
            last_error = health.error
        failed = replace(
            decision, fallbacks_used=tried,
            reason=f"{decision.reason}; no healthy provider offers "
                   f"{primary.capability}/{primary.action} (tried {', '.join(tried) or 'none'})")
        return failed, None, last_error

    def _fallback_order(
        self, task: TaskSpec, decision: RoutingDecision, records: dict[str, RegistryRecord]
    ) -> list[Candidate]:
        """Primary first, then compatible fallbacks only (3.9).

        A fallback declares the same capability, offers the resolved action, is routable
        and, on the signal path, has strong evidence (``types >= MIN_SIGNAL_TYPES``). On the
        explicit path ``rank_key`` is ``[trust_rank]``, so signal strength does not apply.
        """
        primary = decision.selected[0]
        explicit = bool(task.requested_capability)  # same truthiness as router.route
        first = [c for c in decision.candidates
                 if (c.provider, c.capability) == (primary.provider, primary.capability)]
        rest: list[Candidate] = []
        for c in decision.candidates:
            record = records.get(c.provider)
            if (c.provider == primary.provider or c.capability != primary.capability
                    or record is None
                    or not record.routable(self.registry.allow_unverified)
                    or not _offers(record, c.capability, primary.action)):
                continue
            if explicit or (c.rank_key and c.rank_key[0] >= MIN_SIGNAL_TYPES):
                rest.append(c)
        return first + rest

    def _finish(
        self, trace: _Trace, decision: RoutingDecision, status: Outcome, *,
        result: ExecutionResult | None = None, error: ErrorInfo | None = None,
    ) -> AskOutcome:
        record = trace.record
        provider = None
        if record is not None and record.manifest is not None:
            identity = trace.identity
            # observed_version: the version the provider itself reported when (re)described
            # right before this run; the manifest hash alone does not prove identity (4.6).
            provider = ReceiptProvider(id=record.entry.id, version=record.manifest.version,
                                       trust=record.entry.trust,
                                       manifest_sha256=record.manifest_sha256,
                                       executable=identity.executable if identity else None,
                                       fingerprint=identity.digest if identity else None,
                                       observed_version=record.manifest.version)
        receipt = ExecutionReceipt(
            producer=PRODUCER, created_at=utc_now(), status=status, run_id=trace.run_id,
            forge_version=VERSION,
            inputs=ReceiptInputs(task_sha256=trace.task_sha, routing_sha256=trace.routing_sha,
                                 context_sha256=trace.context_sha, risk_sha256=trace.risk_sha),
            provider=provider, result_sha256=trace.result_sha, started_at=trace.started_at,
            finished_at=utc_now(), error=error, limitations=list(trace.limitations),
        )
        self.store.write(trace.run_id, "receipt", receipt)
        return AskOutcome(run_id=trace.run_id, status=status, decision=decision,
                          receipt=receipt, result=result, error=error)
