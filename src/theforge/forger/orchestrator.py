"""The Forger: task -> route -> revalidate -> health -> policy -> context -> execute -> receipt.

Execute may be negotiated: a result carrying a context request is never the final result;
it extends the ContextPack (``context-rN``) and the provider runs again, within the rounds
of the task's profile (8.3-8.6). The final result is then checked for context drift at the
profile's verification level: drift demotes its evidence and ends the run ``partial``
(6.1-6.3, 6.7). Tokens are the provider's own count or ``unknown``, never bytes (7.2-7.4).

Every artifact is persisted as soon as it exists, so a run that fails midway is
still explainable. The routing artifact is the exception: it is written once, with the
final decision (after registry revalidation and fallback). No path reports success
without a valid ExecutionResult.

A run may pin its provider (no health fallback is ever tried for it), be bound to a plan
node (plan and node in the task, the plan's pattern in the routing decision, the handoff
persisted before execute and delivered in the request) and point at the run it replays.
A node's estimated operation class can only make the policy stricter (10.2). Every run
that executed a provider records its ``VerificationResult``; a declared artifact whose
hash diverges ends the run ``partial`` (9.5, 9.6). Every outcome records its
reproducibility level (14.1, 14.2), and an unexpected internal error its redacted
diagnostic, persisted as an artifact only when debug is asked for (13.5).
"""

import time
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import MappingProxyType
from typing import Final, Literal

from theforge.complexity import (
    ComplexityConfig,
    assess,
    load_complexity_config,
    task_inputs,
)
from theforge.context import (
    build_context_pack,
    effective_tiers,
    extend_context_pack,
    scan_workspace,
)
from theforge.context.fingerprints import FingerprintStore
from theforge.context.git import read_git_state
from theforge.context.scan import WorkspaceScan
from theforge.context.verify import DRIFT_LIMITATION_PREFIX, DriftReport, apply_drift, check_drift
from theforge.contracts import (
    Candidate,
    Capability,
    Confidence,
    ContextPack,
    ContextRequest,
    ContractError,
    ErrorInfo,
    ExecuteRequest,
    ExecutionReceipt,
    ExecutionResult,
    IntegrityError,
    Metric,
    Metrics,
    PolicyDecision,
    ReceiptInputs,
    ReceiptProvider,
    RiskDimensions,
    RoutingDecision,
    Selection,
    TaskSpec,
    from_dict,
    to_dict,
)
from theforge.contracts.canonical import utc_now
from theforge.contracts.codes import Codes
from theforge.contracts.diagnostic import Diagnostic
from theforge.contracts.handoff import Handoff
from theforge.contracts.integrity import (
    check_producer,
    validate_context_pack,
    validate_context_request,
    validate_result,
)
from theforge.contracts.types import (
    OperationClass,
    Outcome,
    PlanPattern,
    Producer,
    ProfileRequest,
    Reproducibility,
)
from theforge.contracts.verification import (
    ReproducibilityInfo,
    VerificationCheck,
    VerificationResult,
)
from theforge.diagnostics import build_diagnostic
from theforge.economy import resolve_budget
from theforge.errors import PersistenceError, UsageError
from theforge.forger.reproducibility import assess_run
from theforge.forger.telemetry import TelemetryRecorder
from theforge.forger.verification import (
    ARTIFACT_HASH_LIMITATION,
    INDEPENDENT_FAILED_LIMITATION,
    build_verification,
    request_verdict,
    select_verifier,
)
from theforge.intel import record_decision
from theforge.meta import PRODUCER, VERSION
from theforge.metrics import load_performance, record_performance
from theforge.planning.estimate import stricter_decision
from theforge.policy import assess_dimensions, build_risk_assessment, evaluate, load_policy
from theforge.profiles import (
    MAX_NEGOTIATION_ROUNDS,
    PROFILES,
    ContextProfile,
    assumed_profile,
    profile_for,
)
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

# Derived from the profiles table (compat name; adapters mirror these values).
EXECUTE_TIMEOUTS: Final[Mapping[str, float]] = MappingProxyType(
    {name: profile.execute_timeout_s for name, profile in PROFILES.items()}
)
# Receipt limitation when the run telemetry could not be built (the receipt still goes).
TELEMETRY_UNAVAILABLE_LIMITATION: Final = "telemetry-unavailable"
# Receipt limitation when a handoff reaches a capability that does not declare
# ``accepts_handoff`` (4.7): "<prefix>: <provider>/<capability>".
HANDOFF_UNDECLARED_LIMITATION: Final = "handoff-use-undeclared"
# Receipt limitation when the VerificationResult of an executed run could not be
# persisted during terminalization (the receipt still goes, without its hash).
VERIFICATION_UNAVAILABLE_LIMITATION: Final = "verification-unavailable"
# Terminalization state machine: one run, at most one _finish, one receipt.
TerminalState = Literal["open", "finalizing", "finalized"]


@dataclass(frozen=True, kw_only=True)
class NodeBinding:
    """The plan node a run executes (4.6), set by the plan executor.

    ``handoff`` comes already redacted from ``planning.handoff``; ``estimate_class`` is the
    node's estimated operation class (10.2); ``upstream`` holds the reproducibility levels
    of the nodes the handoff came from (14.2).
    """

    plan_run: str
    node: str
    pattern: PlanPattern
    handoff: Handoff | None = None
    estimate_class: OperationClass | None = None
    upstream: tuple[Reproducibility, ...] = ()


@dataclass(frozen=True, kw_only=True)
class AskRequest:
    intent: str
    targets: list[str] = field(default_factory=lambda: ["."])
    capability: str | None = None
    action: str | None = None
    # ``auto``: the complexity engine picks the effective profile after routing and
    # records the decision as the run's ComplexityAssessment artifact.
    profile: ProfileRequest = "auto"
    allow_unverified: bool = False
    approvals: frozenset[str] = frozenset()  # capability ids explicitly approved (--approve)
    provider: str | None = None  # pinned provider: replaces the selection, never falls back
    node: NodeBinding | None = None  # plan node this run executes
    replay_of: str | None = None  # original run of a re-execute replay
    debug: bool = False  # also persist the diagnostic of an internal error as an artifact


@dataclass(frozen=True, kw_only=True)
class AskOutcome:
    run_id: str
    status: Outcome
    decision: RoutingDecision
    receipt: ExecutionReceipt
    result: ExecutionResult | None = None
    error: ErrorInfo | None = None
    verification: VerificationResult | None = None
    diagnostic: Diagnostic | None = None


@dataclass
class _Trace:
    run_id: str
    started_at: str
    task_sha: str
    task: TaskSpec  # persisted verbatim; the verify op payload needs it
    telemetry: TelemetryRecorder  # phases and counters of this run, written by _finish (10.x)
    request: AskRequest
    profile: ContextProfile | None = None  # resolved at routing (auto or assumed)
    stage: str = "task"  # last stage entered, for the diagnostic of an internal error
    routing_sha: str | None = None
    context_sha: str | None = None
    result_sha: str | None = None
    risk_sha: str | None = None
    context_round_shas: list[str] = field(default_factory=list)  # context-r1, context-r2
    drift: DriftReport | None = None  # post-execution check of the final result (6.x, 9.1-9.3)
    last_pack: ContextPack | None = None  # the last persisted pack (context or context-rN)
    record: RegistryRecord | None = None
    identity: ProviderFingerprint | None = None
    decision: RoutingDecision | None = None
    capability: Capability | None = None
    action: str = ""  # the selected action, for the verify op payload
    handoff: Handoff | None = None  # as persisted: exactly what the provider receives
    handoff_sha: str | None = None
    complexity_sha: str | None = None  # ComplexityAssessment: --profile auto, or a promotion
    complexity_config: ComplexityConfig | None = None  # the loaded policy of an auto run
    budget_sha: str | None = None  # RunBudget, written once the profile resolves
    profile_basis: str | None = None  # evidence-backed reason the effective profile was chosen
    executed: bool = False  # an execute call was attempted (reproducibility, 14.1)
    response_status: str | None = None  # the provider's own status, when it answered
    result_seen: ExecutionResult | None = None  # validated result, before drift demotion
    verification: VerificationResult | None = None
    verification_sha: str | None = None
    terminal: TerminalState = "open"  # one terminalization path per run
    limitations: list[str] = field(default_factory=list)


def _norm_path(path: str) -> str:
    """Comparable form of a pack path vs. an evidence path (both provider-shaped)."""
    return path.replace("\\", "/").lstrip("/").removeprefix("./")


def honest_tokens(reported: Metric) -> Metric:
    """The provider's token count as reported when it is one, else ``unknown`` (7.2-7.4).

    Only a non-negative value with kind ``measured`` or ``estimated`` is kept, value and
    kind unchanged; the core never estimates tokens itself (bytes are not tokens).
    """
    if (reported.kind in ("measured", "estimated") and reported.value is not None
            and reported.value >= 0):
        return Metric(value=reported.value, kind=reported.kind)
    return Metric(value=None, kind="unknown")


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
        resolved = record.manifest.resolve(cap_id)  # an alias counts like the canonical id
        if resolved is None or resolved[0].state == "unsupported":
            continue
        error = _require_op(record, EXECUTE_OP)
        if error is None:
            return None  # an executing declarer exists; it was excluded for another reason
        if blamed is None and record.routable(allow_unverified):
            blamed = error
    return blamed


@dataclass(frozen=True)
class _Executed:
    """Outcome of the context phase plus the (possibly negotiated) execute calls.

    ``result`` is set only for the final, valid, request-free ExecutionResult; ``pack`` is
    the ContextPack of the last round and ``duration_ms`` sums every execute call.
    """

    status: Outcome
    result: ExecutionResult | None = None
    pack: ContextPack | None = None
    error: ErrorInfo | None = None
    duration_ms: float = 0.0
    response_status: str | None = None  # the provider's own status, when it answered
    exception: BaseException | None = None  # cause of an internal error, for its diagnostic


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
        node = request.node
        task = TaskSpec(
            producer=PRODUCER, created_at=started, id=run_id, intent=request.intent,
            workspace_root=str(self.root), targets=list(request.targets),
            budget_profile=request.profile, requested_capability=request.capability,
            requested_action=request.action,
            constraints={"plan": {"run": node.plan_run, "node": node.node}} if node else {},
        )
        # The complexity policy is loaded once per auto run (never raises; problems
        # surface as run limitations). Its fallback profile is also the provisional
        # telemetry profile until the assessment resolves the real one.
        config = None
        config_warnings: list[str] = []
        if task.budget_profile == "auto":
            config = load_complexity_config(
                user_dir=self.registry.user_dir or user_config_dir(),
                forge_dir=self.root / ".forge", warnings=config_warnings)
        telemetry = TelemetryRecorder(
            run_id, profile_for(config.fallback_profile) if config is not None
            else assumed_profile(task.budget_profile))
        # Always measured, so a run that never gets there records an explicit zero.
        for counter in ("providers_executed", "fallbacks_used", "negotiation_rounds"):
            telemetry.count(counter, 0)
        trace = _Trace(run_id=run_id, started_at=started, task=task,
                       telemetry=telemetry,
                       task_sha=self.store.write(run_id, "task", task), request=request,
                       complexity_config=config)
        trace.limitations.extend(config_warnings)
        try:
            self._record_handoff(trace)
            return self._run(trace, task, request)
        except UsageError as exc:
            self._finish(trace, self._placeholder(run_id, f"usage error: {exc}"), "no_route",
                         error=ErrorInfo(code=Codes.USAGE, detail=str(exc)))
            raise
        except PersistenceError:
            raise
        except Exception as exc:  # noqa: BLE001 - invariant: a persisted task always gets a receipt
            error = ErrorInfo(code=Codes.INTERNAL, detail=f"{type(exc).__name__}: {exc}")
            if trace.terminal != "open":
                # _finish itself failed midway: a second attempt cannot produce a
                # trustworthy receipt — report the terminalization failure, once.
                raise PersistenceError(
                    f"run {run_id}: terminalization failed ({error.detail}); refusing a "
                    f"second _finish", code=Codes.PERSIST_WRITE) from exc
            decision = trace.decision or self._placeholder(
                run_id, f"internal error: {error.detail}")
            return self._finish(trace, decision, "provider_failure", error=error,
                                exception=exc)

    def _record_handoff(self, trace: _Trace) -> None:
        """Persist a plan node's handoff before anything runs (4.6).

        The provider receives the handoff exactly as persisted (re-read from disk); its own
        limitations (truncation, missing inputs) become run limitations.
        """
        node = trace.request.node
        if node is None or node.handoff is None:
            return
        trace.stage = "handoff"
        trace.handoff_sha = self.store.write(trace.run_id, "handoff", node.handoff)
        trace.handoff = self.store.read_contract(trace.run_id, "handoff", Handoff)
        trace.limitations.extend(node.handoff.limitations)

    @staticmethod
    def _placeholder(run_id: str, reason: str) -> RoutingDecision:
        return RoutingDecision(status="no_route", reason=reason, confidence=Confidence(level="low"),
                               task_id=run_id, producer=PRODUCER, created_at=utc_now())

    def _run(self, trace: _Trace, task: TaskSpec, request: AskRequest) -> AskOutcome:
        run_id = trace.run_id
        telemetry = trace.telemetry
        trace.stage = "scan"
        with telemetry.phase("scan"):
            scan = scan_workspace(self.root, task.targets)
        telemetry.count("files_scanned", len(scan.files))
        trace.stage = "routing"
        with telemetry.phase("routing"):
            routed = self._final_route(trace, task, request, scan.files)
        if routed.error is None:
            routed = self._pin(trace, task, request, routed)
        if request.node is not None:  # the plan's pattern, whatever the outcome (4.6)
            routed = replace(routed, decision=replace(routed.decision,
                                                      pattern=request.node.pattern))
            trace.decision = routed.decision
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

        if trace.complexity_config is not None:  # --profile auto: measure, then resolve
            assessment = assess(
                task_inputs(task, scan, decision, records, handoff=trace.handoff),
                trace.complexity_config)
            trace.complexity_sha = self.store.write(run_id, "complexity", assessment)
            trace.limitations.extend(
                f"complexity: {item}" for item in assessment.limitations)
            profile = profile_for(assessment.selected_profile)
            trace.telemetry.set_profile(profile)
            trace.profile_basis = f"auto: {assessment.profile_reason}"
        else:
            profile = assumed_profile(task.budget_profile)
            # Explicit profiles are still measured: an assessment whose selected
            # profile outranks the requested one promotes the elastic bounds one
            # step (H2). The assessment is persisted when — and only when — it
            # actually promoted something (it is the adjustment's evidence).
            promo_warnings: list[str] = []
            assessment = assess(
                task_inputs(task, scan, decision, records, handoff=trace.handoff),
                load_complexity_config(
                    user_dir=self.registry.user_dir or user_config_dir(),
                    forge_dir=self.root / ".forge", warnings=promo_warnings))
            trace.limitations.extend(promo_warnings)
        effective, budget = resolve_budget(profile, run_id=run_id,
                                           assessment=assessment)
        if effective is not profile:
            profile = effective
            trace.telemetry.set_profile(profile)
            trace.profile_basis = f"promoted: {budget.adjustments[0]}"
            if trace.complexity_sha is None:
                trace.complexity_sha = self.store.write(run_id, "complexity", assessment)
                trace.limitations.extend(
                    f"complexity: {item}" for item in assessment.limitations)
        trace.limitations.extend(f"budget: {note}" for note in budget.adjustments)
        trace.budget_sha = self.store.write(run_id, "budget", budget)
        trace.profile = profile
        pinned = request.provider is not None
        trace.stage = "health"
        with telemetry.phase("routing"):  # health (and fallback) completes the routing
            decision, record, health_error = self._select_healthy(
                task, decision, records, profile, fallback=not pinned)
        telemetry.count("fallbacks_used", len(decision.fallbacks_used))
        if record is None and pinned:
            trace.limitations.append(f"pinned provider {request.provider}: "
                                     "fallback not attempted")
        elif record is None and not profile.fallback:
            trace.limitations.append(f"profile {profile.name}: fallback disabled")
        trace.decision = decision
        trace.routing_sha = self.store.write(run_id, "routing", decision)
        if record is None or record.manifest is None:
            return self._finish(trace, decision, "provider_failure", error=health_error)
        trace.record = record
        trace.identity = fingerprint(record.entry)
        telemetry.set_revalidation(record.manifest.context_revalidation)  # 6.5, 6.6
        op_error = _require_op(record, EXECUTE_OP)
        if op_error is not None:
            return self._finish(trace, decision, "refused", error=op_error)

        selection = decision.selected[0]
        capability = record.manifest.capability(selection.capability)
        if capability is None:  # the router only selects declared capabilities
            raise RuntimeError(f"{record.entry.id} does not declare {selection.capability!r}")
        trace.capability = capability
        trace.action = selection.action
        if trace.handoff is not None and not capability.accepts_handoff:  # 4.7
            trace.limitations.append(
                f"{HANDOFF_UNDECLARED_LIMITATION}: {record.entry.id}/{capability.id}")
        trace.stage = "policy"
        policy_error = self._apply_policy(trace, request, record, capability, selection)
        if policy_error is not None:
            return self._finish(trace, decision, "refused", error=policy_error)

        # One fingerprint store per run: the initial pack and every negotiated extension
        # share it, and it is written once, after the last round (5.5).
        fingerprints = FingerprintStore(self.root)
        try:
            executed = self._context_and_execute(trace, task, record, capability, selection,
                                                 scan, profile, fingerprints)
        finally:
            fingerprints.save()
            trace.limitations.extend(fingerprints.warnings)
            self._record_context(trace, fingerprints)
        # What the provider said survives an internal error past this point (9.x).
        trace.response_status = executed.response_status
        trace.result_seen = executed.result
        if executed.result is None:
            if trace.executed:
                self._record_verification(trace, record, executed.response_status, None)
            return self._finish(trace, decision, executed.status, error=executed.error,
                                exception=executed.exception)
        assert executed.pack is not None
        trace.stage = "verification"
        result = self._verify_context(trace, executed.result, executed.pack, profile)
        # The verification judges what the provider returned (before drift demotion).
        diverged = self._record_verification(trace, record, executed.response_status,
                                             executed.result)
        if diverged:  # a declared artifact is not what the provider said it wrote (9.5)
            trace.limitations.extend(diverged)
            result = replace(result, status="partial",
                             limitations=[*result.limitations, *diverged])
        result = replace(result, metrics=Metrics(
            duration_ms=Metric(value=round(executed.duration_ms, 3), kind="measured"),
            context_bytes=Metric(value=float(executed.pack.used_bytes), kind="measured"),
            tokens=honest_tokens(executed.result.metrics.tokens),
        ))
        trace.result_sha = self.store.write(run_id, "result", result)
        return self._finish(trace, decision, result.status, result=result)

    def _record_verification(
        self, trace: _Trace, record: RegistryRecord, response_status: str | None,
        result: ExecutionResult | None,
    ) -> list[str]:
        """Build and persist the run's ``VerificationResult`` (9.1-9.6).

        ``result`` is the validated result as the provider returned it (``None`` without
        one). Returns the demotion limitations: one per diverging declared artifact,
        plus the independent-verifier note when that check failed (Wave G).
        """
        assert record.manifest is not None
        verifier_id: str | None = None
        if result is None or trace.capability is None:
            independent = VerificationCheck(
                status="not_performed",
                details=["no valid result" if result is None
                         else "no capability recorded"])
        else:
            verifier, reason = select_verifier(
                self.registry.records(), producer=record,
                capability=trace.capability.id,
                allow_unverified=trace.request.allow_unverified)
            if verifier is None:
                independent = VerificationCheck(status="not_performed",
                                                details=[reason])
            else:
                verifier_id = verifier.entry.id
                independent = request_verdict(
                    verifier, run_id=trace.run_id, task=trace.task,
                    capability=trace.capability.id, action=trace.action,
                    result=result, handoff=trace.handoff,
                    transport_factory=self.transport_factory,
                    timeout=self._timeout(
                        trace.profile
                        or assumed_profile(trace.task.budget_profile)))
        verification = build_verification(
            trace.run_id, response_status, result, trace.drift,
            self.store.work_dir(trace.run_id),
            expected=Producer(id=record.entry.id, version=record.manifest.version),
            handoff=trace.handoff, independent=independent)
        trace.verification = verification
        trace.verification_sha = self.store.write(trace.run_id, "verification", verification)
        prefix = f"{ARTIFACT_HASH_LIMITATION}:"
        notes = [note for note in verification.limitations if note.startswith(prefix)]
        if verification.independent.status == "failed":
            notes.append(f"{INDEPENDENT_FAILED_LIMITATION}: {verifier_id}")
        return notes

    def _verify_context(
        self, trace: _Trace, result: ExecutionResult, pack: ContextPack,
        profile: ContextProfile,
    ) -> ExecutionResult:
        """Post-execution drift check on the final result and the last round's pack.

        Drift reported by the provider is always applied; re-verification follows the
        profile's level (``minimal`` records ``context-not-reverified`` instead). Drifted
        paths go to the result and to the receipt; drift ends the run ``partial`` (6.7).
        """
        report = check_drift(self.root, pack, result, profile.verification)
        trace.drift = report
        trace.telemetry.set_drift(report)
        trace.limitations.extend(report.limitations)
        trace.limitations.extend(f"{DRIFT_LIMITATION_PREFIX} {path}" for path in report.drifted)
        return apply_drift(result, report)

    def _context_and_execute(
        self, trace: _Trace, task: TaskSpec, record: RegistryRecord, capability: Capability,
        selection: Selection, scan: WorkspaceScan, profile: ContextProfile,
        fingerprints: FingerprintStore,
    ) -> _Executed:
        trace.stage = "context"
        with trace.telemetry.phase("context"):
            pack = self._build_context(trace, task, record, capability, scan, profile,
                                       fingerprints)
            try:
                validate_context_pack(pack)
            except IntegrityError as exc:  # the core built it: internal, never sent (1.7)
                return _Executed("provider_failure", exception=exc, error=ErrorInfo(
                    code=Codes.INTERNAL, detail=f"inconsistent context pack: {exc}"))
            trace.context_sha = self.store.write(trace.run_id, "context", pack)
            trace.last_pack = pack
        return self._execute_negotiated(trace, task, record, capability, selection, pack,
                                        scan, profile, fingerprints)

    def _execute_negotiated(
        self, trace: _Trace, task: TaskSpec, record: RegistryRecord, capability: Capability,
        selection: Selection, pack: ContextPack, scan: WorkspaceScan,
        profile: ContextProfile, fingerprints: FingerprintStore,
    ) -> _Executed:
        """At most ``negotiation_rounds + 1`` execute calls (8.3-8.6).

        Every response passes the same envelope, status, schema and integrity checks. One
        carrying a context request is never the result: it is refused with its specific code
        (undeclared, over the profile's rounds, malformed) or extends the pack, which is
        validated and persisted as ``context-rN`` before the provider runs again.
        """
        assert record.manifest is not None
        expected = Producer(id=record.entry.id, version=record.manifest.version)
        telemetry = trace.telemetry
        telemetry.count("providers_executed", 1)  # one provider per ask run, every round
        trace.executed = True
        trace.stage = "execute"
        total_ms = 0.0
        while True:
            payload = to_dict(ExecuteRequest(task=task, capability=selection.capability,
                                             action=selection.action, context=pack,
                                             handoff=trace.handoff))
            started_exec = time.perf_counter()
            try:
                with telemetry.phase("provider"):  # sums every round's execute (4.2)
                    response = self.transport_factory(record.entry.argv).call(
                        "execute", payload, timeout=self._timeout(profile),
                        cwd=self.store.work_dir(trace.run_id))
            except TransportError as exc:
                return _Executed("provider_failure",
                                 error=ErrorInfo(code=exc.code, detail=exc.detail))
            total_ms += (time.perf_counter() - started_exec) * 1000

            # The envelope is checked like describe/health (1.6) before its status is trusted.
            envelope = check_producer(response.producer, expected=expected, field="$.producer")
            if envelope is not None:
                return _Executed("provider_failure", error=ErrorInfo(
                    code=envelope.code, detail=f"execute: {envelope.detail}",
                    field=envelope.field))
            answered = response.status  # the provider's own word (verification self-report)
            trace.response_status = answered  # survives a core failure before the verdict
            if response.status in ("refused", "error"):
                status: Outcome = ("refused" if response.status == "refused"
                                   else "provider_failure")
                return _Executed(status, response_status=answered, error=response.error
                                 or ErrorInfo(code=Codes.PROTO_SCHEMA,
                                              detail="error response without error body"))
            try:
                result = from_dict(ExecutionResult, response.payload, "$.payload")
            except ContractError as exc:
                return _Executed("provider_failure", response_status=answered, error=ErrorInfo(
                    code=Codes.PROTO_SCHEMA, detail=f"execute: {exc}"))
            try:  # relational invariants and producer id+version; invalid results are dropped
                validate_result(result, expected=expected)
            except IntegrityError as exc:
                return _Executed("provider_failure", response_status=answered, error=ErrorInfo(
                    code=exc.code, detail=f"execute: {exc}", field=exc.field))

            if result.context_request is None:
                final: Literal["ok", "partial"] = "ok" if response.status == "ok" else "partial"
                return _Executed(final, result=replace(result, status=final), pack=pack,
                                 duration_ms=total_ms, response_status=answered)
            refusal = self._refuse_request(record, capability, result.context_request,
                                           pack, profile)
            if refusal is not None:
                return _Executed("provider_failure", response_status=answered, error=refusal)
            with telemetry.phase("context"):
                pack = extend_context_pack(pack, result.context_request, scan,
                                           profile=profile, fingerprints=fingerprints)
                try:
                    validate_context_pack(pack)
                except IntegrityError as exc:  # the core extended it: internal, never sent
                    return _Executed("provider_failure", response_status=answered,
                                     exception=exc, error=ErrorInfo(
                        code=Codes.INTERNAL,
                        detail=f"inconsistent context pack (round {pack.round}): {exc}"))
                trace.context_round_shas.append(
                    self.store.write(trace.run_id, f"context-r{pack.round}", pack))
                trace.last_pack = pack

    @staticmethod
    def _refuse_request(
        record: RegistryRecord, capability: Capability, request: ContextRequest,
        pack: ContextPack, profile: ContextProfile,
    ) -> ErrorInfo | None:
        """The negotiation failure, checked in order: undeclared, rounds, shape (8.4)."""
        if not capability.context.requests:
            return ErrorInfo(
                code=Codes.CONTEXT_REQUEST_UNSUPPORTED,
                detail=f"{record.entry.id} sent a context request but capability "
                       f"{capability.id} does not declare context.requests")
        rounds = min(profile.negotiation_rounds, MAX_NEGOTIATION_ROUNDS)
        if pack.round >= rounds:
            return ErrorInfo(
                code=Codes.CONTEXT_REQUEST_LIMIT,
                detail=f"{record.entry.id} asked for more context after {pack.round} "
                       f"round(s); profile {profile.name} allows {rounds}")
        try:
            validate_context_request(request)
        except IntegrityError as exc:
            return ErrorInfo(code=exc.code, detail=f"execute: {exc}",
                             field="$.payload.context_request")
        return None

    def _build_context(
        self, trace: _Trace, task: TaskSpec, record: RegistryRecord, capability: Capability,
        scan: WorkspaceScan, profile: ContextProfile, fingerprints: FingerprintStore,
    ) -> ContextPack:
        """Context phase (after policy): git signals and ContextPack round 0.

        Git problems never fail the run: they become run limitations (3.4). The fingerprint
        cache is owned by ``_run`` (written once, after the last negotiation round).
        """
        git = read_git_state(self.root)
        trace.limitations.extend(git.limitations)
        trace.telemetry.set_effective_tiers(effective_tiers(profile, capability.context))
        return build_context_pack(
            task, record.entry.id, list(capability.signals.file_globs), scan,
            profile=profile, capability_context=capability.context, git=git,
            fingerprints=fingerprints)

    @staticmethod
    def _record_context(trace: _Trace, fingerprints: FingerprintStore) -> None:
        """Context counters once the context phase ran: hashing work and the last pack."""
        telemetry, stats = trace.telemetry, fingerprints.stats
        telemetry.count("files_hashed", stats.files_hashed)
        telemetry.count("bytes_hashed", stats.bytes_hashed)
        telemetry.count("cache_hits", stats.hits)
        telemetry.count("cache_misses", stats.misses)
        if trace.last_pack is not None:
            telemetry.count("files_selected", len(trace.last_pack.files))
            telemetry.count("context_bytes", trace.last_pack.used_bytes)

    def _apply_policy(
        self, trace: _Trace, request: AskRequest, record: RegistryRecord,
        capability: Capability, selection: Selection,
    ) -> ErrorInfo | None:
        """Decide allow/ask/deny and persist the risk before any execute process (6.1-6.4).

        Only routable providers reach this point: ``blocked`` ones are excluded by the router.
        A plan node's estimated operation class is evaluated too and the stricter decision
        applies (10.2); the risk then records the estimated class as the effective one.
        """
        manifest = record.manifest
        assert manifest is not None
        warnings: list[str] = []
        config = load_policy(user_dir=self.registry.user_dir or user_config_dir(),
                             forge_dir=self.root / ".forge", warnings=warnings)
        trace.limitations.extend(f"policy: {w}" for w in warnings)

        def decide(operation_class: OperationClass) -> tuple[RiskDimensions, PolicyDecision]:
            dimensions = assess_dimensions(operation_class=operation_class,
                                           execution=manifest.execution)
            return dimensions, evaluate(
                dimensions=dimensions, trust=record.entry.trust, config=config,
                approved=capability.id in request.approvals, capability=capability.id)

        declared = capability.operation_class
        dimensions, policy = decide(declared)
        estimated = request.node.estimate_class if request.node is not None else None
        stricter_note: str | None = None
        if estimated is not None and estimated != declared:
            estimated_dimensions, estimated_policy = decide(estimated)
            if stricter_decision(policy, estimated_policy) is estimated_policy:
                dimensions, policy = estimated_dimensions, estimated_policy
                stricter_note = (f"operation-class: estimate {estimated} stricter than "
                                 f"declared {declared}")
        risk = build_risk_assessment(run_id=trace.run_id, provider_id=record.entry.id,
                                     capability=capability, action=selection.action,
                                     dimensions=dimensions, decision=policy)
        if stricter_note is not None and estimated is not None:
            risk = replace(risk, operation_class=estimated,
                           limitations=[*risk.limitations, stricter_note])
            trace.limitations.append(stricter_note)
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
        # Measured provider history, loaded once so both passes of a revalidated
        # routing see the same snapshot (a warning becomes a run limitation).
        performance, perf_warning = load_performance(self.root)
        if perf_warning is not None:
            trace.limitations.append(perf_warning)

        def do_route(records: dict[str, RegistryRecord]) -> RoutingDecision:
            decision = route(task, list(records.values()), files, dependencies,
                             allow_unverified=request.allow_unverified,
                             performance=performance)
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

    @staticmethod
    def _pin(trace: _Trace, task: TaskSpec, request: AskRequest, routed: _Routed) -> _Routed:
        """Replace the selection by the pinned provider (3.3), or ``no_route`` with a reason.

        The pinned provider must be a candidate of the final decision, still routable, with
        a capability offering the resolved action. Health fallback is never tried for it.
        """
        pinned = request.provider
        if pinned is None:
            return routed
        decision = routed.decision
        record = routed.records.get(pinned)
        candidate = next((c for c in decision.candidates if c.provider == pinned), None)
        action: str | None = None
        if (candidate is not None and record is not None and record.manifest is not None
                and record.routable(request.allow_unverified)):
            capability = record.manifest.capability(candidate.capability)
            if capability is not None:
                wanted = task.requested_action or capability.default_action
                action = wanted if wanted in capability.actions else None
        if candidate is None or action is None:
            target = task.requested_capability or "this task"
            pinned_decision = replace(
                decision, status="no_route", selected=[],
                reason=f"pinned provider {pinned} is not routable for {target}")
        else:
            pinned_decision = replace(
                decision, status="routed",
                selected=[Selection(provider=pinned, capability=candidate.capability,
                                    action=action)],
                reason=f"{decision.reason}; pinned provider {pinned}")
        trace.decision = pinned_decision
        return replace(routed, decision=pinned_decision)

    def _revalidate(self, decision: RoutingDecision) -> list[RevalidationOutcome]:
        provider_ids = sorted({c.provider for c in decision.candidates})
        return self.registry.revalidate(provider_ids) if provider_ids else []

    def _timeout(self, profile: ContextProfile) -> float:
        if self.execute_timeout is not None:
            return self.execute_timeout
        return profile.execute_timeout_s

    def _select_healthy(
        self, task: TaskSpec, decision: RoutingDecision, records: dict[str, RegistryRecord],
        profile: ContextProfile | None = None, *, fallback: bool = True,
    ) -> tuple[RoutingDecision, RegistryRecord | None, ErrorInfo | None]:
        """Health of the primary, then of compatible fallbacks when the profile allows (9.1).

        ``profile`` defaults to the task's profile; ``fallback=False`` (pinned provider)
        checks the primary only.
        """
        profile = profile if profile is not None else assumed_profile(task.budget_profile)
        primary = decision.selected[0]
        tried: list[str] = []
        last_error: ErrorInfo | None = None
        order = self._fallback_order(task, decision, records)
        if not profile.fallback or not fallback:
            order = order[:1]
        for candidate in order:
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

    def _write_telemetry(self, trace: _Trace) -> tuple[str | None, list[str]]:
        """Persist the run telemetry; return its hash and the limitations for the receipt.

        Idempotent if ``_finish`` is re-entered by the internal-error path (rounds are set,
        not added). A failure to build it never costs the run its receipt nor changes its
        status: the receipt goes without ``telemetry_sha256`` and with a limitation. Only a
        persistence failure propagates, as for every other artifact.
        """
        try:
            telemetry = replace(trace.telemetry.build(), negotiation_rounds=Metric(
                value=float(len(trace.context_round_shas)), kind="measured"))
            return self.store.write(trace.run_id, "telemetry", telemetry), telemetry.limitations
        except PersistenceError:
            raise
        except Exception as exc:  # noqa: BLE001 - telemetry must never block the receipt
            return None, [f"{TELEMETRY_UNAVAILABLE_LIMITATION}: {type(exc).__name__}: {exc}"]

    @staticmethod
    def _reproducibility(trace: _Trace, status: Outcome) -> ReproducibilityInfo:
        record, node = trace.record, trace.request.node
        return assess_run(
            executed=trace.executed, manifest=record.manifest if record else None,
            capability=trace.capability,
            fingerprint=trace.identity.digest if trace.identity else None,
            context_sha256=trace.context_sha, drift=trace.drift,
            verification=trace.verification, status=status,
            upstream=node.upstream if node is not None else ())

    def _diagnostic(self, trace: _Trace, exception: BaseException | None,
                    error: ErrorInfo | None) -> Diagnostic | None:
        """The redacted diagnostic of an internal error (13.5), persisted only with debug."""
        if exception is None or error is None or error.code != Codes.INTERNAL:
            return None
        diagnostic = build_diagnostic(exception, stage=trace.stage, code=Codes.INTERNAL)
        if trace.request.debug:
            self.store.write(trace.run_id, "diagnostic", diagnostic)
        return diagnostic

    def _late_verification(self, trace: _Trace) -> None:
        """Verification for a run that executed a provider but died before recording it.

        Reached only through the internal-error path (``_finish`` after an exception):
        on the normal path ``_record_verification`` already ran and
        ``verification_sha`` is set. Checks that never ran stay ``not_performed`` — the
        artifact never invents a verification that did not happen. A contract-level
        failure to persist it becomes a receipt limitation; a persistence failure
        propagates, like every other artifact write.
        """
        record = trace.record
        if (trace.verification_sha is not None or not trace.executed
                or record is None or record.manifest is None):
            return
        try:
            notes = self._record_verification(trace, record, trace.response_status,
                                              trace.result_seen)
        except PersistenceError:
            raise
        except Exception as exc:  # noqa: BLE001 - the run keeps its terminal receipt
            trace.limitations.append(f"{VERIFICATION_UNAVAILABLE_LIMITATION}: "
                                     f"{type(exc).__name__}: {exc}")
            return
        trace.limitations.extend(n for n in notes if n not in trace.limitations)

    def _record_economy(
        self, trace: _Trace, status: Outcome, result: ExecutionResult | None,
    ) -> None:
        """Context-ROI counters and the provider-performance store update (Wave H).

        The counters are always measured — an explicit zero when nothing was
        delivered. The metrics store updates only when ``execute`` was actually
        attempted; a store failure degrades to a limitation, never a failed run.
        """
        pack = trace.last_pack
        sent = {_norm_path(f.path) for f in pack.files} if pack is not None else set()
        cited: set[str] = set()
        if result is not None:
            for evidence in result.evidence:
                cited.add(_norm_path(evidence.subject))
                if evidence.location is not None:
                    cited.add(_norm_path(evidence.location.path))
        files_cited = len(sent & cited)
        trace.telemetry.count("files_cited", files_cited)
        trace.telemetry.count("evidence_returned",
                              len(result.evidence) if result is not None else 0)
        trace.telemetry.count("findings_returned",
                              len(result.findings) if result is not None else 0)
        record, capability = trace.record, trace.capability
        if not trace.executed or record is None or capability is None:
            return
        warning = record_performance(
            self.root, record.entry.id, capability.id, status=status,
            verified=(trace.verification is not None
                      and trace.verification.forge.status == "passed"),
            evidence=len(result.evidence) if result is not None else 0,
            artifacts=len(result.artifacts) if result is not None else 0,
            context_bytes=pack.used_bytes if pack is not None else 0,
            files_sent=len(pack.files) if pack is not None else 0,
            files_cited=files_cited,
            duration_ms=trace.telemetry.elapsed_ms("provider") or 0.0)
        if warning is not None:
            trace.limitations.append(warning)

    def _record_decisions(self, trace: _Trace, decision: RoutingDecision) -> None:
        """The reusable decisions of this run into the project memory (I3).

        Only decisions the system itself made are remembered — a user-pinned
        provider or explicit profile is the user's choice, not evidence to reuse.
        Best-effort: a memory write failure is a limitation, never a failed run.
        """
        record, capability = trace.record, trace.capability
        for warning in (
            record_decision(self.root, "routing", capability.id, record.entry.id,
                            decision.reason, trace.run_id)
            if decision.status == "routed" and record is not None
            and capability is not None else None,
            record_decision(self.root, "profile", "task-profile", trace.profile.name,
                            trace.profile_basis, trace.run_id)
            if trace.profile is not None and trace.profile_basis is not None else None,
        ):
            if warning is not None:
                trace.limitations.append(warning)

    def _finish(
        self, trace: _Trace, decision: RoutingDecision, status: Outcome, *,
        result: ExecutionResult | None = None, error: ErrorInfo | None = None,
        exception: BaseException | None = None,
    ) -> AskOutcome:
        """The one terminalization path: open -> finalizing -> finalized, exactly once.

        Re-entering on a ``finalizing`` or ``finalized`` run is a controlled
        ``PERSIST_WRITE`` error — never a second, silently different receipt.
        """
        if trace.terminal != "open":
            raise PersistenceError(
                f"run {trace.run_id}: _finish called on a {trace.terminal} run",
                code=Codes.PERSIST_WRITE)
        trace.terminal = "finalizing"
        diagnostic = self._diagnostic(trace, exception, error)
        self._late_verification(trace)
        self._record_economy(trace, status, result)
        self._record_decisions(trace, decision)
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
        # Telemetry before the receipt, on every outcome (10.4).
        telemetry_sha, telemetry_notes = self._write_telemetry(trace)
        limitations = list(trace.limitations)
        limitations.extend(n for n in telemetry_notes if n not in limitations)
        node = trace.request.node
        receipt = ExecutionReceipt(
            producer=PRODUCER, created_at=utc_now(), status=status, run_id=trace.run_id,
            forge_version=VERSION,
            inputs=ReceiptInputs(task_sha256=trace.task_sha, routing_sha256=trace.routing_sha,
                                 context_sha256=trace.context_sha, risk_sha256=trace.risk_sha,
                                 context_round_sha256=list(trace.context_round_shas),
                                 handoff_sha256=trace.handoff_sha,
                                 complexity_sha256=trace.complexity_sha,
                                 budget_sha256=trace.budget_sha),
            provider=provider, result_sha256=trace.result_sha, started_at=trace.started_at,
            finished_at=utc_now(), error=error, limitations=limitations,
            telemetry_sha256=telemetry_sha,
            parent_run=node.plan_run if node is not None else None,
            plan_node=node.node if node is not None else None,
            replay_of=trace.request.replay_of,
            verification_sha256=trace.verification_sha,
            reproducibility=self._reproducibility(trace, status),
        )
        self.store.write(trace.run_id, "receipt", receipt)
        trace.terminal = "finalized"
        return AskOutcome(run_id=trace.run_id, status=status, decision=decision,
                          receipt=receipt, result=result, error=error,
                          verification=trace.verification, diagnostic=diagnostic)
