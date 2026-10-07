"""Plan executor: planning and persistence of the plan run (cross-forge-foundation 5.1),
sequential execution, partial failure and plan closing (5.2), and the offline end-to-end
scenario matrix of the cross-forge proof (8.1), with the fixture providers.

Every end-to-end scenario of the matrix ends with the ``explain`` report of its plan run
pointing no divergence (the plan run's artifacts and its child runs' receipts re-verified).
No network, credentials nor sibling repositories are involved."""

import json
import time
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest

from cross_workspace import CrossWorkspace, mounted_cross_workspace
from helpers import (
    API_PLAN_ENTRY,
    SPARK_ENTRY,
    SPARK_PLAN_ENTRY,
    bad_entry,
    make_workspace,
)
from theforge.contracts import (
    ExecutionReceipt,
    GlobalStopDecision,
    Response,
    RunTelemetry,
)
from theforge.contracts.codes import Codes
from theforge.contracts.diagnostic import Diagnostic
from theforge.contracts.graph import WorkspaceGraph
from theforge.contracts.installation import InstallationPlan
from theforge.contracts.plan import ExecutionPlan, PlanResult
from theforge.contracts.verification import VerificationResult
from theforge.contracts.workspace import WorkspaceDescriptor
from theforge.errors import UsageError
from theforge.explain import build_explain_report
from theforge.forger import Forger, PlanCommand, PlanExecutor, PlanOutcome
from theforge.forger import plan_executor as plan_executor_module
from theforge.forger.orchestrator import HANDOFF_UNDECLARED_LIMITATION
from theforge.planning import handoff as handoff_module
from theforge.protocol import ProviderTransport, SubprocessTransport
from theforge.registry import Registry
from theforge.runs import RunStore

PROOF_TASK = "Projete um pipeline Spark que produza dados para uma API"
PLAN_ARTIFACTS = (
    "task",
    "workspace-descriptor",
    "routing",
    "plan",
    "graph",
    "global-stop",
    "telemetry",
    "receipt",
)


class _Spy:
    """Transport factory recording every call (responding provider, op, start, end,
    payload) and whether a plan was on disk when the first execute call started."""

    def __init__(self, store: RunStore | None = None) -> None:
        self.calls: list[tuple[str, str, float, float, dict[str, Any]]] = []
        self.store = store
        self.plan_on_disk_at_first_execute: bool | None = None

    def __call__(self, argv: Sequence[str]) -> ProviderTransport:
        return _SpyTransport(self, argv)

    def ops(self, op: str) -> list[str]:
        return [pid for pid, o, *_ in self.calls if o == op]


class _SpyTransport:
    def __init__(self, spy: _Spy, argv: Sequence[str]) -> None:
        self.spy, self.argv = spy, list(argv)
        self.inner = SubprocessTransport(argv)

    def call(self, op: str, payload: dict[str, Any], *, timeout: float,
             cwd: Path | None = None, check_protocol: bool = True) -> Response:
        if op == "execute" and self.spy.plan_on_disk_at_first_execute is None:
            store = self.spy.store
            assert store is not None
            self.spy.plan_on_disk_at_first_execute = any(
                store.read_optional(run, "plan") is not None for run in store.list_runs())
        start = time.perf_counter()
        response = self.inner.call(op, payload, timeout=timeout, cwd=cwd,
                                   check_protocol=check_protocol)
        self.spy.calls.append((response.producer.id, op, start, time.perf_counter(),
                               payload))
        return response


@pytest.fixture
def cross() -> Iterator[CrossWorkspace]:
    with mounted_cross_workspace(git=True) as workspace:
        yield workspace


def _executor(root: Path, entries: list[dict[str, Any]]) -> tuple[PlanExecutor, RunStore, _Spy]:
    forge = make_workspace(root, entries)
    store = RunStore(forge)
    spy = _Spy(store)
    forger = Forger(root, Registry(forge), store, transport_factory=spy)
    return PlanExecutor(forger), store, spy


def _plan_file(path: Path, nodes: list[dict[str, Any]], pattern: str = "pipeline") -> Path:
    path.write_text(json.dumps({"task_id": "from-file", "pattern": pattern, "source": "file",
                                "profile": "max", "nodes": nodes}), encoding="utf-8")
    return path


def _node(nid: str, provider: str, capability: str, action: str,
          after: str | None = None, *, inputs: bool = True) -> dict[str, Any]:
    node: dict[str, Any] = {"id": nid, "role": "standalone", "provider": provider,
                            "capability": capability, "action": action}
    if after is not None:
        node["role"] = "consumer"
        node["depends_on"] = [{"node": after, "epistemic": "explicit", "evidence": "plan file"}]
        node["inputs"] = [after] if inputs else []
    return node


def _assert_closed(store: RunStore, out: PlanOutcome) -> ExecutionReceipt:
    """Every plan outcome: receipt of kind plan bound to its telemetry and graph by hash, and
    an ``explain`` report of the plan run without divergence."""
    receipt = store.read_contract(out.run_id, "receipt", ExecutionReceipt)
    assert receipt.kind == "plan" and receipt.status == out.status
    assert receipt.provider is None and receipt.plan is not None
    telemetry = store.read_contract(out.run_id, "telemetry", RunTelemetry)
    assert receipt.telemetry_sha256 == store.persisted_sha256(out.run_id, "telemetry")
    assert receipt.plan.graph_sha256 == store.persisted_sha256(out.run_id, "graph")
    assert receipt.plan.workspace_descriptor_sha256 == store.persisted_sha256(
        out.run_id, "workspace-descriptor")
    assert receipt.plan.plan_sha256 == store.persisted_sha256(out.run_id, "plan")
    if out.result is not None:
        assert receipt.plan.global_stop_sha256 == store.persisted_sha256(
            out.run_id, "global-stop"
        )
        stop = store.read_contract(out.run_id, "global-stop", GlobalStopDecision)
        assert stop.run_id == out.run_id
        assert stop.action in ("stop_sufficient_evidence", "stop_no_expected_gain")
    assert receipt.inputs.routing_sha256 == store.persisted_sha256(out.run_id, "routing")
    store.read_contract(out.run_id, "workspace-descriptor", WorkspaceDescriptor)
    store.read_contract(out.run_id, "graph", WorkspaceGraph)
    assert telemetry.run_id == out.run_id
    assert telemetry.fallbacks_used.value == 0 and telemetry.negotiation_rounds.value == 0
    assert telemetry.scan_ms.kind == "measured" and telemetry.routing_ms.kind == "measured"
    assert {"context_ms", "provider_ms"} <= set(telemetry.unknowns)
    assert plan_executor_module.PLAN_TELEMETRY_LIMITATION in telemetry.limitations
    # Telemetry records the EFFECTIVE profile: the requested one, or what the
    # complexity assessment resolved ``auto`` to (bound by hash when written).
    requested = store.read(out.run_id, "task")["budget_profile"]
    complexity = store.read_optional(out.run_id, "complexity")
    assert receipt.inputs.complexity_sha256 == store.persisted_sha256(
        out.run_id, "complexity")
    if requested == "auto" and complexity is not None:
        assert telemetry.profile.name == complexity["selected_profile"]
    else:
        assert telemetry.profile.name == requested
    _assert_explained(store, out)  # every closed plan run explains without divergence (8.1)
    if out.result is not None:
        report = build_explain_report(store, out.run_id)
        assert report.plan is not None and report.plan.global_stop is not None
        assert report.plan.global_stop.run_id == out.run_id
    return receipt


def _assert_explained(store: RunStore, out: PlanOutcome) -> None:
    """The ``explain`` report of the plan run: a plan report without any divergence."""
    report = build_explain_report(store, out.run_id)
    assert report.kind == "plan" and report.status == out.status
    assert report.integrity.divergences == [], report.integrity.divergences
    assert "task" in report.integrity.checked  # the receipt anchors the re-verified hashes


def _child_runs(store: RunStore, plan_run: str) -> list[str]:
    return [run for run in store.list_runs()
            if (store.read_optional(run, "receipt") or {}).get("parent_run") == plan_run]


# --- 5.1 planning and persistence ------------------------------------------------------------

def test_plan_only_persists_the_plan_with_estimates_and_starts_no_node(
        cross: CrossWorkspace) -> None:
    executor, store, spy = _executor(cross.root, [SPARK_PLAN_ENTRY, API_PLAN_ENTRY])
    out = executor.run(PlanCommand(intent=PROOF_TASK, profile="max"))
    assert out.status == "planned" and out.error is None and out.result is None
    assert spy.ops("execute") == []
    plan = store.read_contract(out.run_id, "plan", ExecutionPlan)
    assert plan == out.plan and plan.status == "validated" and plan.source == "decomposed"
    assert [(n.id, n.provider) for n in plan.nodes] == [("n1", "fixture-spark"),
                                                       ("n2", "fixture-api")]
    n1, n2 = plan.nodes
    assert n1.estimate is not None and n1.estimate.unknowns == ["input data volume"]
    assert n2.estimate is not None and n2.estimate.operation_class == "read_only"
    assert sorted(spy.ops("plan")) == ["fixture-api", "fixture-spark"]
    assert sorted(spy.ops("health")) == ["fixture-api", "fixture-spark"]  # once per provider
    assert store.read(out.run_id, "routing")["pattern"] == "pipeline"
    descriptor = store.read_contract(out.run_id, "workspace-descriptor", WorkspaceDescriptor)
    assert {r.path for r in descriptor.repositories} == {"data-pipeline", "orders-api"}
    assert store.read_optional(out.run_id, "installation") is None  # nothing is missing
    assert store.read_optional(out.run_id, "plan-result") is None
    receipt = _assert_closed(store, out)
    assert receipt.plan is not None and receipt.plan.plan_result_sha256 is None
    assert receipt.reproducibility is not None
    assert receipt.reproducibility.level == "unknown"
    telemetry = store.read_contract(out.run_id, "telemetry", RunTelemetry)
    assert telemetry.providers_executed.value == 0
    assert _child_runs(store, out.run_id) == []


def test_auto_plan_floors_to_max_when_the_task_needs_two_providers(
        cross: CrossWorkspace) -> None:
    """``--profile auto`` on a two-provider intent: the assessment must not pick a
    profile that forbids the split — the provider floor raises it to ``max``."""
    executor, store, _ = _executor(cross.root, [SPARK_PLAN_ENTRY, API_PLAN_ENTRY])
    out = executor.run(PlanCommand(intent=PROOF_TASK))  # profile auto
    assert out.status == "planned" and out.error is None
    assert store.read(out.run_id, "task")["budget_profile"] == "auto"
    assessment = store.read(out.run_id, "complexity")
    assert assessment["requested_profile"] == "auto"
    assert assessment["selected_profile"] == "max"
    assert "providers required" in assessment["profile_reason"]
    plan = store.read_contract(out.run_id, "plan", ExecutionPlan)
    assert [(n.id, n.provider) for n in plan.nodes] == [("n1", "fixture-spark"),
                                                       ("n2", "fixture-api")]
    assert plan.profile == "max"
    _assert_closed(store, out)


def test_rejected_plan_file_is_refused_with_its_first_violation(tmp_path: Path) -> None:
    executor, store, spy = _executor(tmp_path, [SPARK_ENTRY])
    plan_file = _plan_file(tmp_path / "plan.json", [
        _node("n1", "fixture-spark", "spark.performance", "diagnose"),
        _node("n2", "ghost", "ghost.thing", "run", after="n1")])
    out = executor.run(PlanCommand(intent="spark then ghost", profile="max",
                                   plan_file=plan_file, execute=True))
    assert out.status == "refused"
    assert out.error is not None and out.error.code == Codes.PLAN_CAPABILITY
    assert "ghost" in out.error.detail
    assert spy.ops("execute") == [] and spy.ops("plan") == []
    plan = store.read_contract(out.run_id, "plan", ExecutionPlan)
    assert plan.status == "rejected" and plan.source == "file"
    assert plan.plan_run == out.run_id and plan.task_id == out.run_id
    installation = store.read_contract(out.run_id, "installation", InstallationPlan)
    assert [(i.provider, i.nodes) for i in installation.items] == [("ghost", ["n2"])]
    receipt = _assert_closed(store, out)
    assert receipt.plan is not None
    assert receipt.plan.installation_sha256 == store.persisted_sha256(out.run_id,
                                                                      "installation")
    assert _child_runs(store, out.run_id) == []


@pytest.mark.parametrize(("workspace", "intent", "profile", "status"), [
    ("cross", PROOF_TASK, "balanced", "ambiguous"),
    ("empty", "write a poem about the sea", "max", "no_route"),
])
def test_undecomposable_task_ends_without_plan_nor_node(
        tmp_path: Path, workspace: str, intent: str, profile: str, status: str) -> None:
    if workspace == "cross":
        with mounted_cross_workspace(git=False) as cross:
            _undecomposable(cross.root, intent, profile, status)
    else:
        _undecomposable(tmp_path, intent, profile, status)


def _undecomposable(root: Path, intent: str, profile: str, status: str) -> None:
    executor, store, spy = _executor(root, [SPARK_PLAN_ENTRY, API_PLAN_ENTRY])
    out = executor.run(PlanCommand(intent=intent, profile=profile,  # type: ignore[arg-type]
                                   execute=True))
    assert out.status == status and out.plan is None and out.error is None
    assert spy.ops("execute") == [] and spy.ops("plan") == []
    assert store.read_optional(out.run_id, "plan") is None
    assert store.read(out.run_id, "routing")["status"] == status
    receipt = _assert_closed(store, out)
    assert receipt.plan is not None and receipt.plan.plan_sha256 is None
    if status == "ambiguous":  # the decomposition's limitation reaches the receipt
        assert any(n.startswith("multi-provider decomposition not allowed by profile")
                   for n in receipt.limitations)


def test_unreadable_plan_file_is_a_usage_error_with_a_plan_receipt(tmp_path: Path) -> None:
    executor, store, spy = _executor(tmp_path, [SPARK_ENTRY])
    bad = tmp_path / "plan.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(UsageError) as exc:
        executor.run(PlanCommand(intent="x", plan_file=bad, execute=True))
    assert exc.value.code == Codes.PLAN_FILE
    (run,) = store.list_runs()
    receipt = store.read_contract(run, "receipt", ExecutionReceipt)
    assert receipt.kind == "plan" and receipt.status == "refused"
    assert receipt.error is not None and receipt.error.code == Codes.PLAN_FILE
    assert receipt.telemetry_sha256 == store.persisted_sha256(run, "telemetry")
    assert spy.ops("execute") == []


@pytest.mark.parametrize("debug", [False, True])
def test_unexpected_error_becomes_an_internal_failure_receipt(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, debug: bool) -> None:
    executor, store, _ = _executor(tmp_path, [SPARK_ENTRY])

    def boom(*_: Any, **__: Any) -> Any:
        raise RuntimeError("decomposer exploded token=supersecretvalue123")

    monkeypatch.setattr(plan_executor_module, "decompose", boom)
    out = executor.run(PlanCommand(intent="analise o job spark", debug=debug))
    assert out.status == "provider_failure"
    assert out.error is not None and out.error.code == Codes.INTERNAL
    assert out.diagnostic is not None and out.diagnostic.stage == "plan:routing"
    receipt = _assert_closed(store, out)
    assert receipt.error is not None and receipt.error.code == Codes.INTERNAL
    persisted = store.read_optional(out.run_id, "diagnostic")
    assert (persisted is not None) == debug
    if persisted is not None:
        assert "supersecretvalue123" not in json.dumps(persisted)
        store.read_contract(out.run_id, "diagnostic", Diagnostic)


# --- 5.2 execution, partial failure and closing ----------------------------------------------

def test_proof_task_runs_two_nodes_with_the_first_handoff_in_the_second(
        cross: CrossWorkspace) -> None:
    executor, store, spy = _executor(cross.root, [SPARK_PLAN_ENTRY, API_PLAN_ENTRY])
    out = executor.run(PlanCommand(intent=PROOF_TASK, profile="max", execute=True))
    assert out.status == "ok", out.error
    assert spy.plan_on_disk_at_first_execute is True  # plan persisted before the 1st node
    # Sequential, in topological order, without overlap (3.1, 3.8).
    executes = [(pid, start, end) for pid, op, start, end, _ in spy.calls if op == "execute"]
    assert [pid for pid, *_ in executes] == ["fixture-spark", "fixture-api"]
    assert executes[0][2] <= executes[1][1]

    result = store.read_contract(out.run_id, "plan-result", PlanResult)
    assert result == out.result and result.status == "ok" and result.order == ["n1", "n2"]
    n1, n2 = result.nodes
    assert n1.run_id is not None and n2.run_id is not None
    assert sorted(_child_runs(store, out.run_id)) == sorted([n1.run_id, n2.run_id])
    for outcome in (n1, n2):
        assert outcome.status == "ok"
        assert outcome.receipt_sha256 == store.persisted_sha256(outcome.run_id, "receipt")
        assert outcome.result_sha256 == store.persisted_sha256(outcome.run_id, "result")
        # Every node run is verified and its reproducibility recorded (3.2, 9.1, 14.1).
        node_receipt = store.read_contract(outcome.run_id, "receipt", ExecutionReceipt)
        verification = store.read_contract(outcome.run_id, "verification",
                                           VerificationResult)
        assert node_receipt.verification_sha256 == store.persisted_sha256(
            outcome.run_id, "verification")
        assert verification.forge.status == "passed"
        assert node_receipt.reproducibility is not None
        assert node_receipt.reproducibility == outcome.reproducibility
    # The handoff of n1 reached n2: persisted in n2's run and echoed by the fixture.
    handoff = store.read(n2.run_id, "handoff")
    assert {item["origin"]["node"] for item in handoff["items"]} == {"n1"}
    assert spy.calls[-1][4]["handoff"] == handoff
    # Evidence bus (Wave D): n1's run verification crosses as a typed item.
    [ver_item] = [i for i in handoff["items"] if i["kind"] == "verification"]
    assert ver_item["epistemic"] == "observed" and "forge=passed" in ver_item["claim"]
    child = store.read_contract(n2.run_id, "receipt", ExecutionReceipt)
    assert (child.parent_run, child.plan_node) == (out.run_id, "n2")
    claims = [e["claim"] for e in store.read(n2.run_id, "result")["evidence"]]
    assert f"received {len(handoff['items'])} handoff items" in claims
    # fixture-api does not declare accepts_handoff: a limitation, never a failure (4.7, 4.8).
    assert f"{HANDOFF_UNDECLARED_LIMITATION}: fixture-api/api.contract" in child.limitations
    assert store.read_optional(n1.run_id, "handoff") is None  # n1 has no input

    assert [h.source for h in result.synthesis.handoffs] == ["n1"]
    assert [s.node for s in result.synthesis.nodes] == ["n1", "n2"]
    graph = store.read_contract(out.run_id, "graph", WorkspaceGraph)
    assert any(e.kind == "handed_off_to" for e in graph.edges)
    assert any(e.kind == "produced" for e in graph.edges)
    receipt = _assert_closed(store, out)
    assert receipt.plan is not None
    assert receipt.plan.plan_result_sha256 == store.persisted_sha256(out.run_id, "plan-result")
    assert receipt.reproducibility == result.reproducibility
    telemetry = store.read_contract(out.run_id, "telemetry", RunTelemetry)
    assert telemetry.providers_executed.value == 2


def test_truncated_handoff_is_a_limitation_of_the_dependent_node_run(
        cross: CrossWorkspace, monkeypatch: pytest.MonkeyPatch) -> None:
    # n1's result yields more items than the (lowered) limit: the handoff is cut (4.4).
    monkeypatch.setattr(handoff_module, "MAX_HANDOFF_ITEMS", 1)
    executor, store, spy = _executor(cross.root, [SPARK_PLAN_ENTRY, API_PLAN_ENTRY])
    out = executor.run(PlanCommand(intent=PROOF_TASK, profile="max", execute=True))
    assert out.status == "ok", out.error
    assert out.result is not None
    n1, n2 = out.result.nodes
    assert n1.run_id is not None and n2.run_id is not None
    handoff = store.read(n2.run_id, "handoff")
    assert handoff["truncated"] is True and len(handoff["items"]) == 1
    assert handoff["dropped"] >= 1
    assert handoff["items"][0]["kind"] == "decision"  # the priority prefix is kept
    note = f"handoff-truncated: dropped {handoff['dropped']} items"
    assert note in handoff["limitations"]
    assert spy.calls[-1][4]["handoff"] == handoff  # delivered == persisted
    child = store.read_contract(n2.run_id, "receipt", ExecutionReceipt)
    assert (child.parent_run, child.plan_node) == (out.run_id, "n2")
    assert note in child.limitations  # the dependent node's run records the truncation
    first = store.read_contract(n1.run_id, "receipt", ExecutionReceipt)
    assert not [n for n in first.limitations if n.startswith("handoff-truncated")]


def test_policy_refusal_of_the_first_node_blocks_the_second(tmp_path: Path) -> None:
    executor, store, spy = _executor(
        tmp_path, [bad_entry("plan-estimate-stricter", "bad-s"), SPARK_ENTRY])
    plan_file = _plan_file(tmp_path / "plan.json", [
        _node("n1", "bad-s", "bad.thing", "run"),
        _node("n2", "fixture-spark", "spark.performance", "diagnose", after="n1")])
    out = executor.run(PlanCommand(intent="bad then spark", profile="max",
                                   plan_file=plan_file, execute=True))
    assert out.status == "refused"
    assert out.error is not None and out.error.code == Codes.POLICY_APPROVAL_REQUIRED
    assert out.error.detail.startswith("node n1: ")
    assert spy.ops("execute") == []
    assert out.result is not None
    n1, n2 = out.result.nodes
    assert n1.status == "refused" and n1.run_id is not None
    assert (n2.status, n2.blocked_by, n2.run_id) == ("skipped", "n1", None)
    assert n2.error is not None and n2.error.code == Codes.PLAN_DEPENDENCY_FAILED
    assert out.result.reproducibility.level == "unknown"
    assert _child_runs(store, out.run_id) == [n1.run_id]
    _assert_closed(store, out)
    telemetry = store.read_contract(out.run_id, "telemetry", RunTelemetry)
    assert telemetry.providers_executed.value == 0


def test_independent_node_still_runs_after_another_fails(tmp_path: Path) -> None:
    executor, store, spy = _executor(tmp_path, [bad_entry("refuse", "bad-r"), SPARK_ENTRY])
    plan_file = _plan_file(tmp_path / "plan.json", [
        _node("a", "bad-r", "bad.thing", "run"),
        _node("b", "fixture-spark", "spark.performance", "diagnose"),
        _node("c", "fixture-spark", "spark.performance", "review", after="a")])
    out = executor.run(PlanCommand(intent="three nodes", profile="max",
                                   plan_file=plan_file, execute=True))
    assert out.status == "partial" and out.error is None
    assert out.result is not None
    statuses = {n.node: (n.status, n.blocked_by) for n in out.result.nodes}
    assert statuses == {"a": ("refused", None), "b": ("ok", None), "c": ("skipped", "a")}
    assert out.result.order == ["a", "b", "c"]
    assert spy.ops("execute") == ["bad-r", "fixture-spark"]
    assert any(f.startswith("a: ") for f in out.result.synthesis.failures)
    _assert_closed(store, out)
    telemetry = store.read_contract(out.run_id, "telemetry", RunTelemetry)
    assert telemetry.providers_executed.value == 2


def test_failure_at_the_root_of_a_chain_blocks_every_descendant_by_the_root(
        tmp_path: Path) -> None:
    executor, store, spy = _executor(tmp_path, [bad_entry("refuse", "bad-r"), SPARK_ENTRY])
    plan_file = _plan_file(tmp_path / "plan.json", [
        _node("n1", "bad-r", "bad.thing", "run"),
        _node("n2", "fixture-spark", "spark.performance", "diagnose", after="n1"),
        _node("n3", "fixture-spark", "spark.performance", "review", after="n2")])
    out = executor.run(PlanCommand(intent="three in a chain", profile="max",
                                   plan_file=plan_file, execute=True))
    assert out.status == "refused"
    assert out.result is not None and out.result.order == ["n1", "n2", "n3"]
    statuses = {n.node: (n.status, n.blocked_by, n.run_id is None)
                for n in out.result.nodes}
    # The grandchild names the root that failed, not its skipped parent (3.4).
    assert statuses == {"n1": ("refused", None, False), "n2": ("skipped", "n1", True),
                        "n3": ("skipped", "n1", True)}
    for skipped in out.result.nodes[1:]:
        assert skipped.error is not None
        assert skipped.error.code == Codes.PLAN_DEPENDENCY_FAILED
    assert spy.ops("execute") == ["bad-r"]
    assert _child_runs(store, out.run_id) == [out.result.nodes[0].run_id]
    _assert_closed(store, out)


@pytest.mark.parametrize(("approvals", "bad_status"), [
    (frozenset(), "refused"),
    (frozenset({"spark.performance"}), "refused"),  # another capability releases nothing
    (frozenset({"bad.thing"}), "ok"),
])
def test_approval_releases_only_the_nodes_of_its_capability(
        tmp_path: Path, approvals: frozenset[str], bad_status: str) -> None:
    executor, store, spy = _executor(tmp_path, [bad_entry("mutating", "bad-m"), SPARK_ENTRY])
    plan_file = _plan_file(tmp_path / "plan.json", [
        _node("n1", "bad-m", "bad.thing", "run"),
        _node("n2", "fixture-spark", "spark.performance", "diagnose")])
    out = executor.run(PlanCommand(intent="two nodes", profile="max", plan_file=plan_file,
                                   execute=True, approvals=approvals))
    assert out.result is not None
    assert [(n.node, n.status) for n in out.result.nodes] == [("n1", bad_status),
                                                              ("n2", "ok")]
    assert out.status == ("ok" if bad_status == "ok" else "partial")
    assert ("bad-m" in spy.ops("execute")) == (bad_status == "ok")
    _assert_closed(store, out)


def test_plan_status_rules() -> None:
    from theforge.contracts import ErrorInfo
    from theforge.contracts.plan import NodeOutcome

    def node(nid: str, status: str, code: str | None = None) -> NodeOutcome:
        error = ErrorInfo(code=code, detail="why") if code else None
        return NodeOutcome(node=nid, status=status, error=error,  # type: ignore[arg-type]
                           blocked_by="a" if status == "skipped" else None)

    status_of = plan_executor_module.plan_status
    assert status_of([node("a", "ok"), node("b", "ok")]) == ("ok", None)
    assert status_of([node("a", "partial"), node("b", "ok")])[0] == "partial"
    assert status_of([node("a", "ok"), node("b", "refused", Codes.POLICY_DENIED)])[0] == \
        "partial"
    refused = status_of([node("a", "refused", Codes.POLICY_DENIED),
                         node("b", "skipped", Codes.PLAN_DEPENDENCY_FAILED)])
    assert refused[0] == "refused" and refused[1] is not None
    assert (refused[1].code, refused[1].detail) == (Codes.POLICY_DENIED, "node a: why")
    failure = status_of([node("a", "refused", Codes.POLICY_DENIED),
                         node("b", "provider_failure", Codes.PROTO_SCHEMA)])
    assert failure[0] == "provider_failure" and failure[1] is not None
    assert failure[1].code == Codes.POLICY_DENIED  # the first failed node


# --- 8.1 offline end-to-end scenario matrix ---------------------------------------------------
# Covered above, each closed by ``_assert_closed`` (explain without divergence): the proof task
# in ``max`` (with estimates), the rejected plan file, the stricter estimate (policy ``ask``
# refuses the node), the ``balanced`` profile (``ambiguous``) and plan-only (``planned``).

def test_valid_plan_file_runs_its_nodes_with_the_handoff(cross: CrossWorkspace) -> None:
    executor, store, spy = _executor(cross.root, [SPARK_PLAN_ENTRY, API_PLAN_ENTRY])
    plan_file = _plan_file(cross.root.parent / "plan.json", [
        _node("data", "fixture-spark", "spark.performance", "review"),
        _node("api", "fixture-api", "api.contract", "lint", after="data")])
    out = executor.run(PlanCommand(intent="explicit spark then api", profile="max",
                                   plan_file=plan_file, execute=True))
    assert out.status == "ok", out.error
    plan = store.read_contract(out.run_id, "plan", ExecutionPlan)
    assert plan.status == "validated" and plan.source == "file"
    assert plan.task_id == out.run_id  # the file's task_id is replaced by the run's
    assert [(n.id, n.provider, n.action) for n in plan.nodes] == [
        ("data", "fixture-spark", "review"), ("api", "fixture-api", "lint")]
    assert all(n.estimate is not None for n in plan.nodes)
    assert [pid for pid, op, *_ in spy.calls if op == "execute"] == ["fixture-spark",
                                                                      "fixture-api"]
    assert out.result is not None and out.result.order == ["data", "api"]
    data, api = out.result.nodes
    assert api.run_id is not None
    handoff = store.read(api.run_id, "handoff")
    assert {item["origin"]["node"] for item in handoff["items"]} == {"data"}
    assert [h.source for h in out.result.synthesis.handoffs] == ["data"]
    _assert_closed(store, out)


def test_plan_op_error_is_a_limitation_and_the_plan_still_runs(tmp_path: Path) -> None:
    executor, store, spy = _executor(tmp_path, [bad_entry("plan-error", "bad-p"), SPARK_ENTRY])
    plan_file = _plan_file(tmp_path / "plan.json", [
        _node("n1", "bad-p", "bad.thing", "run"),
        _node("n2", "fixture-spark", "spark.performance", "diagnose", after="n1")])
    out = executor.run(PlanCommand(intent="bad then spark", profile="max",
                                   plan_file=plan_file, execute=True))
    assert out.status == "ok", out.error
    assert spy.ops("plan") == ["bad-p"]  # fixture-spark (base manifest) does not declare it
    plan = store.read_contract(out.run_id, "plan", ExecutionPlan)
    n1 = plan.nodes[0]
    assert n1.estimate is None
    (note,) = [n for n in n1.limitations if n.startswith("estimate: ")]
    assert Codes.PLAN_ESTIMATE in note and "BAD-PLAN-FAILED" in note
    assert out.result is not None
    assert f"n1: {note}" in out.result.synthesis.limitations
    assert spy.ops("execute") == ["bad-p", "fixture-spark"]
    _assert_closed(store, out)


def test_invalid_provider_yields_an_installation_plan_with_the_registry_detail(
        tmp_path: Path) -> None:
    executor, store, spy = _executor(tmp_path, [bad_entry("invalid-manifest", "bad-i"),
                                                SPARK_ENTRY])
    record = Registry(tmp_path / ".forge").get("bad-i")
    assert record.state == "invalid" and record.error
    plan_file = _plan_file(tmp_path / "plan.json", [
        _node("n1", "fixture-spark", "spark.performance", "diagnose"),
        _node("n2", "bad-i", "bad.thing", "run", after="n1")])
    out = executor.run(PlanCommand(intent="spark then invalid", profile="max",
                                   plan_file=plan_file, execute=True))
    assert out.status == "refused" and out.error is not None
    assert spy.ops("execute") == []
    installation = store.read_contract(out.run_id, "installation", InstallationPlan)
    assert installation.planning_only is True
    (item,) = installation.items
    assert (item.provider, item.state, item.source, item.nodes) == (
        "bad-i", "invalid", "registry", ["n2"])
    assert item.reason == record.error
    receipt = _assert_closed(store, out)
    assert receipt.plan is not None
    assert receipt.plan.installation_sha256 == store.persisted_sha256(out.run_id,
                                                                      "installation")


@pytest.mark.parametrize(("target", "declared"), [
    (API_PLAN_ENTRY, False),  # a v1 provider that knows nothing of handoffs
    (bad_entry("handoff-accept", "bad-h"), True),
])
def test_handoff_to_a_provider_with_or_without_handoff_knowledge_ends_ok(
        cross: CrossWorkspace, target: dict[str, Any], declared: bool) -> None:
    executor, store, _ = _executor(cross.root, [SPARK_PLAN_ENTRY, target])
    capability = "api.contract" if not declared else "bad.thing"
    action = "review" if not declared else "run"
    plan_file = _plan_file(cross.root.parent / "plan.json", [
        _node("n1", "fixture-spark", "spark.performance", "diagnose"),
        _node("n2", target["id"], capability, action, after="n1")])
    out = executor.run(PlanCommand(intent="spark then consumer", profile="max",
                                   plan_file=plan_file, execute=True))
    assert out.status == "ok", out.error
    assert out.result is not None
    n2 = out.result.nodes[1]
    assert n2.status == "ok" and n2.run_id is not None
    handoff = store.read(n2.run_id, "handoff")
    receipt = store.read_contract(n2.run_id, "receipt", ExecutionReceipt)
    undeclared = [n for n in receipt.limitations
                  if n.startswith(HANDOFF_UNDECLARED_LIMITATION)]
    if declared:
        assert undeclared == []
        result = store.read(n2.run_id, "result")
        assert f"handoff-items={len(handoff['items'])}" in result["limitations"]
    else:
        assert undeclared == [f"{HANDOFF_UNDECLARED_LIMITATION}: fixture-api/api.contract"]
    _assert_closed(store, out)
