"""PlanExecutor: plan, persist and run a multi-provider plan, one node at a time.

The plan run persists, in order: ``task`` -> ``workspace-descriptor`` -> ``routing`` ->
``plan`` (with the nodes' estimates) -> ``installation`` (when something is missing) ->
[node runs] -> ``plan-result`` -> ``graph`` -> ``telemetry`` -> ``receipt`` (``kind="plan"``).
The plan is on disk before the first node starts (1.7); ``graph``, ``telemetry`` and the
receipt are written on every outcome, the receipt last (it binds everything by hash).

Outcomes: a rejected plan ends ``refused`` with its first violation; an ``ambiguous`` or
``no_route`` decomposition keeps that outcome; planning only ends ``planned`` (2.8). An
executed plan runs its nodes sequentially in topological order (3.1, 3.8): each node is a
complete child run of the ``Forger`` (provider pinned, plan binding, handoff, estimated
operation class and the ``--approve`` capabilities); a node whose ancestor has no valid
result is ``skipped`` with that ancestor, independent nodes still run (3.4, 3.5). The plan
status follows the design rules (3.6) and its reproducibility combines the nodes' (14.3).
An unexpected error becomes a ``provider_failure`` receipt with ``Codes.INTERNAL`` and a
redacted diagnostic, persisted as an artifact only with debug (13.5).

Nothing here knows a provider domain: plans come from the decomposer or from a file, and
every provider is reached through the ``Forger`` or the protocol helpers of ``planning``.
"""

import json
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Final

from theforge.capability_graph import build_capability_graph
from theforge.complexity import ComplexityConfig, assess, load_complexity_config, task_inputs
from theforge.context import scan_workspace
from theforge.context.scan import WorkspaceScan
from theforge.contracts import (
    Confidence,
    ErrorInfo,
    ExecutionReceipt,
    ExecutionResult,
    ReceiptInputs,
    RoutingDecision,
    RunTelemetry,
    Selection,
    TaskSpec,
)
from theforge.contracts.canonical import utc_now
from theforge.contracts.capability_graph import CapabilityGraph
from theforge.contracts.codes import Codes
from theforge.contracts.diagnostic import Diagnostic
from theforge.contracts.handoff import Handoff
from theforge.contracts.integrity import validate_plan_result
from theforge.contracts.plan import (
    ExecutionPlan,
    NodeOutcome,
    NodeStatus,
    PlanNode,
    PlanResult,
    SemanticPlanProposal,
)
from theforge.contracts.receipt import PlanRefs
from theforge.contracts.types import (
    CONCURRENT_PATTERNS,
    MAX_PARALLEL_NODES,
    BudgetProfile,
    Outcome,
    Producer,
    ProfileRequest,
    Reproducibility,
)
from theforge.contracts.verification import ReproducibilityInfo, VerificationResult
from theforge.contracts.workspace import WorkspaceDescriptor
from theforge.diagnostics import build_diagnostic
from theforge.errors import PersistenceError, UsageError
from theforge.forger.orchestrator import (
    AskOutcome,
    AskRequest,
    Forger,
    NodeBinding,
    TerminalState,
)
from theforge.forger.reproducibility import NO_EXECUTION, combine_levels
from theforge.forger.telemetry import TelemetryRecorder
from theforge.meta import PRODUCER, VERSION
from theforge.planning.decision import compose_decision
from theforge.planning.decompose import (
    Decomposition,
    decompose,
    decomposed_plan,
    decomposition_dependencies,
)
from theforge.planning.estimate import request_estimate
from theforge.planning.execution import NodeExecution, SourceResult
from theforge.planning.graph import build_graph
from theforge.planning.handoff import build_handoff
from theforge.planning.installation import build_installation_plan
from theforge.planning.order import blocked_by, topological_order
from theforge.planning.propose import (
    options_of,
    planner_capability,
    proposal_plan,
    request_proposal,
)
from theforge.planning.synthesis import synthesize
from theforge.planning.validate import checked_plan, load_plan_file
from theforge.profiles import ContextProfile, assumed_profile, profile_for
from theforge.registry import RegistryRecord, check_health, user_config_dir
from theforge.registry.health import HealthOutcome
from theforge.routing import route
from theforge.runs import new_run_id
from theforge.workspace.describe import describe_workspace

__all__ = ["PLAN_TELEMETRY_LIMITATION", "PlanCommand", "PlanExecutor", "PlanOutcome",
           "plan_status"]

# Telemetry limitation of every plan run: context, provider and file counters are per node.
PLAN_TELEMETRY_LIMITATION: Final = "plan run: per-node metrics are in each node run telemetry"
# Receipt limitation when the graph could not be built (the receipt still goes).
GRAPH_UNAVAILABLE_LIMITATION: Final = "graph-unavailable"
# Same rule as the Forger: a telemetry failure never costs the plan its receipt.
TELEMETRY_UNAVAILABLE_LIMITATION: Final = "telemetry-unavailable"

_VALID: Final = frozenset({"ok", "partial"})
# Child run outcome -> node status; a pinned run is ``routed`` or ``no_route``, so anything
# else (``ambiguous``) can only be a Forger bug and is reported as ``no_route``.
_NODE_STATUS: Final[Mapping[Outcome, NodeStatus]] = {
    "ok": "ok", "partial": "partial", "refused": "refused",
    "provider_failure": "provider_failure", "no_route": "no_route"}


@dataclass(frozen=True, kw_only=True)
class PlanCommand:
    intent: str
    targets: list[str] = field(default_factory=lambda: ["."])
    # ``auto``: assessed after routing, with the workspace descriptor available (node
    # runs then re-assess against their own routing — a node's run keeps ``auto``).
    profile: ProfileRequest = "auto"
    plan_file: Path | None = None  # plan --from FILE; None: decompose the intent
    execute: bool = False  # False: plan only (outcome ``planned``)
    approvals: frozenset[str] = frozenset()  # capability ids approved for every node (3.7)
    allow_unverified: bool = False
    debug: bool = False  # also persist the diagnostic of an internal error


@dataclass(frozen=True, kw_only=True)
class PlanOutcome:
    run_id: str
    status: Outcome
    plan: ExecutionPlan | None
    result: PlanResult | None
    error: ErrorInfo | None
    diagnostic: Diagnostic | None = None


@dataclass
class _PlanTrace:
    run_id: str
    started_at: str
    task: TaskSpec
    task_sha: str
    command: PlanCommand
    telemetry: TelemetryRecorder
    stage: str = "plan:task"  # last stage entered, for the diagnostic of an internal error
    records: dict[str, RegistryRecord] = field(default_factory=dict)
    descriptor: WorkspaceDescriptor | None = None
    descriptor_sha: str | None = None
    capability_graph_sha: str | None = None  # CapabilityGraph of the registry+workspace
    capability_graph: CapabilityGraph | None = None  # the persisted graph object
    semantic_proposal_sha: str | None = None  # tier-2 SemanticPlanProposal, when asked
    decision_sha: str | None = None  # DecisionRecord of a debate plan, when produced
    routing_sha: str | None = None
    plan: ExecutionPlan | None = None
    plan_sha: str | None = None
    installation_sha: str | None = None
    executions: list[NodeExecution] = field(default_factory=list)
    plan_result_sha: str | None = None
    complexity_config: ComplexityConfig | None = None  # loaded when profile is ``auto``
    complexity_sha: str | None = None  # the run's ComplexityAssessment, when auto
    terminal: TerminalState = "open"  # one terminalization path per run
    limitations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _Planned:
    decision: RoutingDecision
    plan: ExecutionPlan | None
    status: Outcome  # the decomposition outcome when there is no plan


def plan_status(outcomes: Sequence[NodeOutcome]) -> tuple[Outcome, ErrorInfo | None]:
    """Status of an executed plan (3.6) and, without any valid result, its error.

    ``ok`` when every node is ``ok``; ``partial`` when some node has a valid result and
    some is not ``ok``; otherwise ``refused`` when every attempted node was refused, else
    ``provider_failure``, with the error of the first failed node (``node <id>: ...``).
    """
    if outcomes and all(o.status == "ok" for o in outcomes):
        return "ok", None
    if any(o.status in _VALID for o in outcomes):
        return "partial", None
    attempted = [o for o in outcomes if o.status != "skipped"]
    status: Outcome = ("refused" if attempted and all(o.status == "refused" for o in attempted)
                       else "provider_failure")
    first = next((o for o in attempted if o.error is not None), None)
    if first is None or first.error is None:
        return status, ErrorInfo(code=Codes.PLAN_INVALID, detail="no node was executed")
    error = first.error
    return status, replace(error, detail=f"node {first.node}: {error.detail}")


class PlanExecutor:
    def __init__(self, forger: Forger) -> None:
        self.forger = forger

    def run(self, command: PlanCommand) -> PlanOutcome:
        store = self.forger.store
        run_id = new_run_id()
        started = utc_now()
        store.create(run_id)
        task = TaskSpec(
            producer=PRODUCER, created_at=started, id=run_id, intent=command.intent,
            workspace_root=str(self.forger.root), targets=list(command.targets),
            budget_profile=command.profile)
        # The complexity policy of an auto run: loaded once, never raises.
        config = None
        config_warnings: list[str] = []
        if command.profile == "auto":
            config = load_complexity_config(
                user_dir=self.forger.registry.user_dir or user_config_dir(),
                forge_dir=self.forger.root / ".forge", warnings=config_warnings)
        telemetry = TelemetryRecorder(
            run_id, profile_for(config.fallback_profile) if config is not None
            else assumed_profile(command.profile))
        # Measured on every outcome: a plan that never executes records explicit zeros.
        for counter in ("providers_executed", "fallbacks_used", "negotiation_rounds",
                        "semantic_planner_calls"):
            telemetry.count(counter, 0)
        telemetry.note(PLAN_TELEMETRY_LIMITATION)
        trace = _PlanTrace(run_id=run_id, started_at=started, task=task,
                           task_sha=store.write(run_id, "task", task), command=command,
                           telemetry=telemetry, complexity_config=config)
        trace.limitations.extend(config_warnings)
        try:
            return self._run(trace)
        except UsageError as exc:  # e.g. an unreadable plan file (Codes.PLAN_FILE)
            self._finish(trace, "refused", error=ErrorInfo(code=exc.code, detail=str(exc)))
            raise
        except PersistenceError:
            raise
        except Exception as exc:  # noqa: BLE001 - invariant: a persisted task always gets a receipt
            error = ErrorInfo(code=Codes.INTERNAL, detail=f"{type(exc).__name__}: {exc}")
            if trace.terminal != "open":
                raise PersistenceError(
                    f"run {run_id}: terminalization failed ({error.detail}); refusing a "
                    f"second _finish", code=Codes.PERSIST_WRITE) from exc
            return self._finish(trace, "provider_failure", error=error, exception=exc)

    # --- planning ------------------------------------------------------------------------

    def _run(self, trace: _PlanTrace) -> PlanOutcome:
        store, command = self.forger.store, trace.command
        profile = assumed_profile(command.profile)  # refined by the assessment in _plan
        trace.stage = "plan:registry"
        trace.records = {r.entry.id: r for r in self.forger.registry.records()}
        trace.stage = "plan:workspace"
        with trace.telemetry.phase("scan"):
            scan = scan_workspace(self.forger.root, command.targets)
            descriptor = describe_workspace(self.forger.root, list(trace.records.values()),
                                            scan)
        trace.descriptor = descriptor
        trace.descriptor_sha = store.write(trace.run_id, "workspace-descriptor", descriptor)
        # The capability graph of this registry+workspace is plan evidence: persisted
        # before planning so explain/replay can audit what the planner could see.
        capability_graph = build_capability_graph(
            trace.records, descriptor, run_id=trace.run_id)
        trace.capability_graph = capability_graph
        trace.capability_graph_sha = store.write(
            trace.run_id, "capability-graph", capability_graph)
        trace.limitations.extend(f"capability-graph: {item}"
                                 for item in capability_graph.limitations)
        trace.stage = "plan:routing"
        with trace.telemetry.phase("routing"):
            planned = self._plan(trace, scan, descriptor, profile)
        trace.routing_sha = store.write(trace.run_id, "routing", planned.decision)
        plan = planned.plan
        if plan is not None and plan.status == "validated":
            trace.stage = "plan:estimate"
            plan = self._with_estimates(trace, plan)
        trace.stage = "plan:health"
        health = self._health(plan, trace.records) if plan is not None else {}
        installation = build_installation_plan(trace.run_id, plan, trace.records, health)
        if plan is not None:
            trace.plan = plan
            trace.plan_sha = store.write(trace.run_id, "plan", plan)  # before any node (1.7)
        if installation is not None:
            trace.installation_sha = store.write(trace.run_id, "installation", installation)

        if plan is None:
            return self._finish(trace, planned.status)
        if plan.status == "rejected":
            first = plan.violations[0]
            return self._finish(trace, "refused",
                                error=ErrorInfo(code=first.code, detail=first.detail))
        if not command.execute:
            return self._finish(trace, "planned")
        return self._execute(trace, plan)

    def _plan(self, trace: _PlanTrace, scan: WorkspaceScan, descriptor: WorkspaceDescriptor,
              profile: ContextProfile) -> _Planned:
        """The plan of the run: from the plan file, or decomposed from the intent."""
        command, task, records = trace.command, trace.task, trace.records
        if command.plan_file is not None:
            profile_name = command.profile
            if profile_name == "auto":  # a file plan fixes its structure: its profile wins
                profile_name = _file_profile(command.plan_file)
                trace.limitations.append(
                    f"auto profile: plan file declares {profile_name!r}; used as-is")
            loaded = load_plan_file(command.plan_file, records, plan_run=trace.run_id,
                                    profile=profile_name)
            profile = profile_for(profile_name)
            trace.telemetry.set_profile(profile)
            plan = checked_plan(replace(loaded, task_id=task.id), records, profile)
            return _Planned(_file_decision(task, plan), plan, "refused")
        decision = route(task, list(records.values()), scan.files,
                         decomposition_dependencies(self.forger.root, descriptor),
                         allow_unverified=command.allow_unverified)
        if trace.complexity_config is not None:  # --profile auto: measured, then resolved
            assessment = assess(
                task_inputs(task, scan, decision, records, descriptor=descriptor,
                            decomposable=True),
                trace.complexity_config)
            trace.complexity_sha = self.forger.store.write(
                trace.run_id, "complexity", assessment)
            trace.limitations.extend(
                f"complexity: {item}" for item in assessment.limitations)
            profile = profile_for(assessment.selected_profile)
            trace.telemetry.set_profile(profile)
        decomposition = decompose(task, decision, records, descriptor, scan, profile,
                                  graph=trace.capability_graph)
        if decomposition.status != "planned":
            trace.limitations.extend(decomposition.limitations)
            semantic = self._semantic(trace, decomposition, profile)
            if semantic is not None:
                return semantic
            return _Planned(decomposition.decision, None, decomposition.status)
        plan = decomposed_plan(decomposition, task, records, profile, plan_run=trace.run_id)
        return _Planned(decomposition.decision, plan, "refused")

    def _semantic(self, trace: _PlanTrace, decomposition: "Decomposition",
                  profile: ContextProfile) -> _Planned | None:
        """Tier 2: a ``SemanticPlanProposal`` from a planner provider, validated by
        ``proposal_plan`` + ``check_plan``. Only an ``ambiguous`` decomposition with
        a non-``economy`` profile asks; every failure degrades to the deterministic
        outcome with a limitation (the planner never gets to invent options: it
        picks among the routing-eligible set, and the validator re-checks it)."""
        if decomposition.status != "ambiguous":
            return None
        if profile.name == "economy":
            trace.limitations.append(
                "ambiguous decomposition: semantic planner disabled by profile 'economy'")
            return None
        picked = planner_capability(
            trace.records, allow_unverified=trace.command.allow_unverified)
        if picked is None:
            trace.limitations.append(
                "ambiguous decomposition: no provider declares a semantic-planning "
                "capability (proposes_plans)")
            return None
        record, capability = picked
        options = options_of(decomposition.decision, trace.records)
        if not options:
            trace.limitations.append(
                "ambiguous decomposition: no eligible options for a proposal")
            return None
        proposal, note = request_proposal(
            record, capability, trace.task, options, decomposition.decision.reason,
            transport_factory=self.forger.transport_factory,
            allow_unverified=trace.command.allow_unverified)
        if note is not None:
            trace.limitations.append(f"ambiguous decomposition: {note}")
        if proposal is None:
            return None
        trace.semantic_proposal_sha = self.forger.store.write(
            trace.run_id, "semantic-proposal", proposal)
        trace.telemetry.count("semantic_planner_calls", 1)
        plan = proposal_plan(proposal, trace.task, trace.records, profile,
                             plan_run=trace.run_id, planner=record.entry.id)
        decision = _semantic_decision(decomposition.decision, plan, proposal,
                                      record.entry.id)
        if plan.status == "rejected" and plan.violations:
            trace.limitations.append(
                f"semantic proposal rejected: {plan.violations[0].detail}")
        return _Planned(decision, plan, "refused")

    def _with_estimates(self, trace: _PlanTrace, plan: ExecutionPlan) -> ExecutionPlan:
        """Each node with its provider's estimate, or the limitation saying why not (10.1)."""
        nodes: list[PlanNode] = []
        for node in plan.nodes:
            node_task = replace(trace.task, targets=list(node.targets),
                                requested_capability=node.capability,
                                requested_action=node.action)
            estimate, note = request_estimate(
                trace.records[node.provider], node_task, node.capability, node.action,
                transport_factory=self.forger.transport_factory,
                allow_unverified=trace.command.allow_unverified)
            notes = [*node.limitations, note] if note is not None else list(node.limitations)
            nodes.append(replace(node, estimate=estimate, limitations=notes))
        return replace(plan, nodes=nodes)

    def _health(self, plan: ExecutionPlan,
                records: Mapping[str, RegistryRecord]) -> dict[str, HealthOutcome]:
        """Health of each distinct registered provider of the plan, consulted once (10.5)."""
        providers = sorted({node.provider for node in plan.nodes} & set(records))
        return {pid: check_health(records[pid],
                                  transport_factory=self.forger.transport_factory,
                                  allow_unverified=self.forger.registry.allow_unverified)
                for pid in providers}

    # --- execution -----------------------------------------------------------------------

    def _execute(self, trace: _PlanTrace, plan: ExecutionPlan) -> PlanOutcome:
        trace.stage = "plan:execute"
        order = topological_order(plan)
        nodes = {node.id: node for node in plan.nodes}
        if plan.pattern in CONCURRENT_PATTERNS:
            self._execute_concurrent(trace, plan, order, nodes)
        else:
            failed: dict[str, str] = {}
            sources: list[SourceResult] = []
            levels: dict[str, Reproducibility] = {}
            for nid in order:
                node = nodes[nid]
                blocker = blocked_by(nid, plan, failed)
                if blocker is not None:
                    execution = _skipped(node, blocker)
                else:
                    execution = self._run_node(trace, plan, node, sources, levels)
                self._record(trace, execution, failed, sources, levels)

        trace.stage = "plan:synthesis"
        outcomes = [e.outcome for e in trace.executions]
        status, error = plan_status(outcomes)
        # A debate composes its DecisionRecord before the PlanResult so the result
        # points at the decision artifact (and surfaces its limitations/unknowns).
        decision_sha = None
        decision_notes: list[str] = []
        decision_unknowns: list[str] = []
        if plan.pattern == "debate":
            decision = compose_decision(trace.task, plan, trace.executions)
            decision_sha = self.forger.store.write(trace.run_id, "decision", decision)
            trace.decision_sha = decision_sha
            decision_notes = decision.limitations
            decision_unknowns = decision.unknowns
        result = PlanResult(
            producer=PRODUCER, created_at=utc_now(), status=status, plan_run=trace.run_id,
            order=order, nodes=outcomes, synthesis=synthesize(plan, trace.executions),
            reproducibility=combine_levels([o.reproducibility for o in outcomes
                                            if o.reproducibility is not None]),
            decision_sha256=decision_sha,
            limitations=decision_notes, unknowns=decision_unknowns)
        validate_plan_result(result)
        trace.plan_result_sha = self.forger.store.write(trace.run_id, "plan-result", result)
        return self._finish(trace, status, error=error, result=result)

    def _execute_concurrent(
        self, trace: _PlanTrace, plan: ExecutionPlan, order: list[str],
        nodes: Mapping[str, PlanNode],
    ) -> None:
        """Level-scheduled execution for concurrent patterns (E2): nodes whose
        dependencies are all done run in parallel, bounded by ``MAX_PARALLEL_NODES``;
        results are recorded in the deterministic topological ``order``, never in
        completion order. Blocking, receipts and failure semantics are the sequential
        ones: a node whose ancestor failed is skipped, independent nodes continue."""
        deps = {n.id: tuple(d.node for d in n.depends_on if d.node in nodes)
                for n in plan.nodes}
        done: dict[str, NodeExecution] = {}
        failed: dict[str, str] = {}
        sources: list[SourceResult] = []
        levels: dict[str, Reproducibility] = {}
        while len(done) < len(order):
            ready = [nid for nid in order
                     if nid not in done and all(d in done for d in deps[nid])]
            if not ready:  # unreachable on a validated acyclic plan; never hang
                break
            runnable: list[PlanNode] = []
            for nid in ready:
                blocker = blocked_by(nid, plan, failed)
                if blocker is not None:
                    done[nid] = _skipped(nodes[nid], blocker)
                else:
                    runnable.append(nodes[nid])
            if runnable:
                workers = min(len(runnable), MAX_PARALLEL_NODES)
                with ThreadPoolExecutor(max_workers=workers,
                                        thread_name_prefix="forge-node") as pool:
                    futures = {pool.submit(self._run_node, trace, plan, node,
                                           list(sources), dict(levels)): node.id
                               for node in runnable}
                    for future in as_completed(futures):
                        execution = future.result()
                        done[execution.node.id] = execution
            for nid in ready:  # deterministic order: topological, not completion
                self._record(trace, done[nid], failed, sources, levels)

    def _record(self, trace: _PlanTrace, execution: NodeExecution,
                failed: dict[str, str], sources: list[SourceResult],
                levels: dict[str, Reproducibility]) -> None:
        """Bookkeeping of one finished node: order, failures, handoff sources and
        reproducibility levels for downstream nodes, and the provider counter."""
        trace.executions.append(execution)
        outcome = execution.outcome
        if execution.reached_execute:
            trace.telemetry.count("providers_executed", 1)
        if execution.result is None:
            failed[outcome.node] = outcome.status
            return
        assert outcome.run_id is not None and execution.provider is not None
        node = execution.node
        sources.append(SourceResult(
            node=outcome.node, run_id=outcome.run_id, provider=execution.provider,
            status=outcome.status, capability=node.capability, action=node.action,
            result=execution.result, verification=execution.verification))
        if outcome.reproducibility is not None:
            levels[outcome.node] = outcome.reproducibility.level

    def _run_node(self, trace: _PlanTrace, plan: ExecutionPlan, node: PlanNode,
                  sources: Sequence[SourceResult],
                  levels: Mapping[str, Reproducibility]) -> NodeExecution:
        """One child run of the Forger for ``node``, its valid result re-read from disk."""
        command, store = trace.command, self.forger.store
        handoff = build_handoff(trace.run_id, node, sources, records=trace.records)
        binding = NodeBinding(
            plan_run=trace.run_id, node=node.id, pattern=plan.pattern, handoff=handoff,
            estimate_class=node.estimate.operation_class if node.estimate else None,
            upstream=tuple(levels[i] for i in node.inputs if i in levels))
        asked = self.forger.ask(AskRequest(
            intent=command.intent, targets=list(node.targets), capability=node.capability,
            action=node.action, profile=command.profile,
            allow_unverified=command.allow_unverified, approvals=command.approvals,
            provider=node.provider, node=binding, debug=command.debug))
        reached = self._reached_execute(asked)
        child = asked.run_id
        result = (store.read_contract(child, "result", ExecutionResult)
                  if asked.status in _VALID else None)
        delivered = (store.read_contract(child, "handoff", Handoff)
                     if asked.receipt.inputs.handoff_sha256 is not None else None)
        verification = (store.read_contract(child, "verification", VerificationResult)
                        if asked.receipt.verification_sha256 is not None else None)
        provider = asked.receipt.provider
        outcome = NodeOutcome(
            node=node.id, status=_NODE_STATUS.get(asked.status, "no_route"), run_id=child,
            receipt_sha256=store.persisted_sha256(child, "receipt"),
            result_sha256=asked.receipt.result_sha256, error=_node_error(asked),
            reproducibility=asked.receipt.reproducibility)
        return NodeExecution(
            node=node, outcome=outcome, result=result, handoff=delivered,
            verification=verification, reached_execute=reached,
            provider=Producer(id=provider.id, version=provider.version) if provider else None)

    def _reached_execute(self, asked: AskOutcome) -> bool:
        """Whether the child run called ``execute`` (its own telemetry says so)."""
        if asked.receipt.telemetry_sha256 is None:
            return asked.receipt.verification_sha256 is not None
        telemetry = self.forger.store.read_contract(asked.run_id, "telemetry", RunTelemetry)
        return bool(telemetry.providers_executed.value)

    # --- closing -------------------------------------------------------------------------

    def _write_graph(self, trace: _PlanTrace) -> tuple[str | None, list[str]]:
        if trace.descriptor is None:
            return None, []
        try:
            plan = trace.plan
            graph = build_graph(
                trace.run_id, trace.descriptor, list(trace.records.values()), plan,
                trace.plan_sha, trace.executions,
                created_at=plan.created_at if plan is not None else trace.started_at)
            return self.forger.store.write(trace.run_id, "graph", graph), list(graph.limitations)
        except PersistenceError:
            raise
        except Exception as exc:  # noqa: BLE001 - the graph must never block the receipt
            return None, [f"{GRAPH_UNAVAILABLE_LIMITATION}: {type(exc).__name__}: {exc}"]

    def _write_telemetry(self, trace: _PlanTrace) -> tuple[str | None, list[str]]:
        try:
            telemetry = trace.telemetry.build()
            sha = self.forger.store.write(trace.run_id, "telemetry", telemetry)
            return sha, list(telemetry.limitations)
        except PersistenceError:
            raise
        except Exception as exc:  # noqa: BLE001 - telemetry must never block the receipt
            return None, [f"{TELEMETRY_UNAVAILABLE_LIMITATION}: {type(exc).__name__}: {exc}"]

    def _finish(self, trace: _PlanTrace, status: Outcome, *, error: ErrorInfo | None = None,
                result: PlanResult | None = None,
                exception: BaseException | None = None) -> PlanOutcome:
        """The one terminalization path: open -> finalizing -> finalized, exactly once."""
        if trace.terminal != "open":
            raise PersistenceError(
                f"run {trace.run_id}: _finish called on a {trace.terminal} run",
                code=Codes.PERSIST_WRITE)
        trace.terminal = "finalizing"
        store = self.forger.store
        diagnostic: Diagnostic | None = None
        if exception is not None and error is not None and error.code == Codes.INTERNAL:
            diagnostic = build_diagnostic(exception, stage=trace.stage, code=Codes.INTERNAL)
            if trace.command.debug:
                store.write(trace.run_id, "diagnostic", diagnostic)
        graph_sha, graph_notes = self._write_graph(trace)
        telemetry_sha, telemetry_notes = self._write_telemetry(trace)
        limitations = list(trace.limitations)
        if trace.plan is not None:
            limitations.extend(trace.plan.limitations)
        for note in (*graph_notes, *telemetry_notes):
            if note not in limitations:
                limitations.append(note)
        reproducibility = (result.reproducibility if result is not None else
                           ReproducibilityInfo(level="unknown",
                                               reasons=[f"{NO_EXECUTION} ({status})"]))
        receipt = ExecutionReceipt(
            producer=PRODUCER, created_at=utc_now(), status=status, run_id=trace.run_id,
            forge_version=VERSION, kind="plan",
            inputs=ReceiptInputs(task_sha256=trace.task_sha, routing_sha256=trace.routing_sha,
                                 complexity_sha256=trace.complexity_sha),
            started_at=trace.started_at, finished_at=utc_now(), error=error,
            limitations=limitations, telemetry_sha256=telemetry_sha,
            reproducibility=reproducibility,
            plan=PlanRefs(plan_sha256=trace.plan_sha,
                          workspace_descriptor_sha256=trace.descriptor_sha,
                          graph_sha256=graph_sha, installation_sha256=trace.installation_sha,
                          capability_graph_sha256=trace.capability_graph_sha,
                          semantic_proposal_sha256=trace.semantic_proposal_sha,
                          decision_sha256=trace.decision_sha,
                          plan_result_sha256=trace.plan_result_sha))
        store.write(trace.run_id, "receipt", receipt)
        trace.terminal = "finalized"
        return PlanOutcome(run_id=trace.run_id, status=status, plan=trace.plan, result=result,
                           error=error, diagnostic=diagnostic)


def _file_profile(path: Path) -> BudgetProfile:
    """The profile a plan file declares, for ``--profile auto --from FILE``; invalid
    or missing values read as ``balanced`` (``load_plan_file`` reports the real error)."""
    try:
        data = json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, ValueError):
        return "balanced"
    value = data.get("profile") if isinstance(data, dict) else None
    return value if value in ("economy", "balanced", "max") else "balanced"


def _semantic_decision(
    decision: RoutingDecision, plan: ExecutionPlan, proposal: SemanticPlanProposal,
    planner: str,
) -> RoutingDecision:
    """Routing artifact of a tier-2 plan: the proposal's nodes, its rationale as the
    reason, and its confidence/unknowns carried into the decision's confidence."""
    chain = " -> ".join(f"{n.provider}/{n.capability}" for n in plan.nodes)
    return replace(
        decision, status="routed" if plan.nodes else decision.status,
        pattern=plan.pattern,
        selected=[Selection(provider=n.provider, capability=n.capability, action=n.action,
                            role="primary" if i == 0 else "specialist")
                  for i, n in enumerate(plan.nodes)],
        reason=(f"semantic plan proposed by {planner} "
                f"({plan.status}): {len(plan.nodes)} nodes: {chain or 'none'}; "
                f"{proposal.rationale or 'no rationale stated'}"),
        confidence=Confidence(
            level="high" if proposal.confidence == "high" and plan.status == "validated"
            else "low",
            measured_signals=list(decision.confidence.measured_signals),
            unresolved=list(proposal.unknowns)))


def _file_decision(task: TaskSpec, plan: ExecutionPlan) -> RoutingDecision:
    """Routing artifact of a plan read from a file: its nodes, in declaration order."""
    chain = " -> ".join(f"{n.provider}/{n.capability}" for n in plan.nodes)
    if not plan.nodes:
        return RoutingDecision(producer=PRODUCER, created_at=utc_now(), status="no_route",
                               task_id=task.id, pattern=plan.pattern,
                               reason="plan file has no nodes",
                               confidence=Confidence(level="low"))
    return RoutingDecision(
        producer=PRODUCER, created_at=utc_now(), status="routed", task_id=task.id,
        pattern=plan.pattern,
        selected=[Selection(provider=n.provider, capability=n.capability, action=n.action,
                            role="primary" if i == 0 else "specialist")
                  for i, n in enumerate(plan.nodes)],
        reason=f"plan file ({plan.status}): {len(plan.nodes)} nodes: {chain}",
        confidence=Confidence(level="high" if plan.status == "validated" else "low"))


def _skipped(node: PlanNode, blocker: str) -> NodeExecution:
    """A node not executed because ``blocker`` (an ancestor) has no valid result (3.4)."""
    outcome = NodeOutcome(
        node=node.id, status="skipped", blocked_by=blocker,
        error=ErrorInfo(code=Codes.PLAN_DEPENDENCY_FAILED,
                        detail=f"node {node.id}: dependency {blocker} has no valid result"),
        reproducibility=ReproducibilityInfo(level="unknown",
                                            reasons=[f"not executed: blocked by {blocker}"]))
    return NodeExecution(node=node, outcome=outcome, result=None, handoff=None, provider=None)


def _node_error(asked: AskOutcome) -> ErrorInfo | None:
    """The child's error; a ``no_route`` child has none, so its routing reason becomes one."""
    if asked.error is not None or asked.status in _VALID:
        return asked.error
    return ErrorInfo(code=Codes.PLAN_CAPABILITY, detail=asked.decision.reason)
