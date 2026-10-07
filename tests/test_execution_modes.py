"""Cycle 3 Wave E: delegate, parallel and debate execution, and the DecisionRecord.

Three layers: ``compose_decision`` over synthetic node executions (unit), the
level-scheduled concurrent engine with a fake ``_run_node`` (bounded parallelism,
deterministic recording, partial failure), and end-to-end plan-file runs with the
fixture providers (delegate, parallel, debate with a referee that declares the
decision-convention evidence).
"""

import json
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from helpers import (
    API_DEBATE_ENTRY,
    API_DOMAIN_ENTRY,
    API_PLAN_ENTRY,
    REFEREE_ENTRY,
    SPARK_DEBATE_ENTRY,
    SPARK_DOMAIN_ENTRY,
    SPARK_PLAN_ENTRY,
    bad_entry,
    make_workspace,
)
from theforge.contracts.base import ContractError
from theforge.contracts.handoff import Handoff, HandoffItem, HandoffOrigin
from theforge.contracts.plan import (
    DecisionRecord,
    ExecutionPlan,
    NodeOutcome,
    PlanNode,
    PlanResult,
)
from theforge.contracts.receipt import ExecutionReceipt
from theforge.contracts.result import Evidence, ExecutionResult, Finding
from theforge.contracts.task import TaskSpec
from theforge.contracts.types import MAX_PARALLEL_NODES, ErrorInfo, Producer
from theforge.contracts.verification import ReproducibilityInfo
from theforge.forger import Forger, PlanCommand, PlanExecutor
from theforge.planning.decision import compose_decision
from theforge.planning.execution import NodeExecution
from theforge.registry import Registry
from theforge.runs import RunStore

P = Producer(id="theforge", version="1")
TS = "2026-01-01T00:00:00Z"
SHA = "a" * 64

TASK = TaskSpec(producer=P, created_at=TS, id="t1", intent="choose the design",
                workspace_root=".", targets=["."])


def _dep(nid: str) -> dict[str, Any]:
    return {"node": nid, "epistemic": "explicit", "evidence": "plan file"}


def _plan(pattern: str, nodes: list[PlanNode]) -> ExecutionPlan:
    return ExecutionPlan(producer=P, created_at=TS, status="validated", plan_run="p1",
                         task_id="t1", pattern=pattern, source="file", profile="max",
                         nodes=nodes)


def _mode_node(nid: str, role: str, *deps: str) -> PlanNode:
    return PlanNode(id=nid, role=role, provider="p", capability="p.cap",  # type: ignore[arg-type]
                    action="act", depends_on=[_dep_obj(d) for d in deps],
                    inputs=list(deps))


def _dep_obj(nid: str):
    from theforge.contracts.plan import PlanDependency
    return PlanDependency(node=nid, epistemic="explicit", evidence="plan file")


def _exec(node: PlanNode, *, status: str = "ok",
          evidence: list[Evidence] | None = None,
          findings: list[Finding] | None = None,
          handoff: Handoff | None = None) -> NodeExecution:
    run_id = None if status == "skipped" else f"r-{node.id}"
    valid = status in ("ok", "partial")
    result = (ExecutionResult(producer=Producer(id=node.provider, version="0"),
                              created_at=TS, status=status,  # type: ignore[arg-type]
                              evidence=evidence or [], findings=findings or [])
              if valid else None)
    return NodeExecution(
        node=node, provider=Producer(id=node.provider, version="0"), handoff=handoff,
        result=result, reached_execute=valid,
        outcome=NodeOutcome(node=node.id, status=status, run_id=run_id,  # type: ignore[arg-type]
                            receipt_sha256=SHA if run_id else None,
                            result_sha256=SHA if valid else None,
                            blocked_by=None if status != "skipped" else "a"))


def _handoff(source: str, target: PlanNode) -> Handoff:
    origin = HandoffOrigin(plan_run="p1", node=source, run_id=f"r-{source}",
                           provider=Producer(id="p", version="0"))
    items = [HandoffItem(kind="evidence", id="e1", origin=origin, epistemic="observed",
                         subject="s", claim="c")]
    return Handoff(producer=P, created_at=TS, plan_run="p1", target_node=target.id,
                   items=items)


def _debate() -> tuple[PlanNode, PlanNode, PlanNode]:
    a = _mode_node("a", "proposer")
    b = _mode_node("b", "proposer")
    ref = _mode_node("ref", "referee", "a", "b")
    return a, b, ref


def _decision_evidence(claim: str, subject: str = "rationale") -> Evidence:
    return Evidence(id="decision", epistemic="confirmed", subject=subject, claim=claim,
                    producer=Producer(id="p", version="0"))


# --- compose_decision ------------------------------------------------------------------------


def test_decision_record_of_a_resolved_debate() -> None:
    a, b, ref = _debate()
    executions = [
        _exec(a, evidence=[Evidence(id="e1", epistemic="observed", subject="s",
                                    claim="c", producer=P)],
              findings=[Finding(id="f1", title="proposal A"),
                        Finding(id="r1", title="risk A", severity="high")]),
        _exec(b, findings=[Finding(id="f1", title="proposal B")]),
        _exec(ref, evidence=[_decision_evidence("a", "a has the stronger evidence")],
              handoff=_handoff("a", ref)),
    ]
    record = compose_decision(TASK, _plan("debate", [a, b, ref]), executions)
    assert record.chosen == "a" and record.rejected == ["b"]
    assert record.rationale == "a has the stronger evidence"
    assert record.confidence == "high" and record.limitations == []
    assert record.question == TASK.intent and record.referee == "ref"
    assert {o.node for o in record.options} == {"a", "b"}
    by_node = {o.node: o for o in record.options}
    assert by_node["a"].position == "proposal A"  # first finding title, verbatim
    assert by_node["a"].evidence == ["e1"]
    assert by_node["a"].risks == ["r1: risk A"]
    assert by_node["b"].position == "proposal B" and by_node["b"].risks == []
    assert record.evidence == ["a:e1"]  # the items the referee received, by origin
    assert sorted(record.tradeoffs) == ["a: f1: proposal A", "a: r1: risk A",
                                        "b: f1: proposal B"]


def test_decision_record_is_unresolved_without_the_convention() -> None:
    a, b, ref = _debate()
    record = compose_decision(TASK, _plan("debate", [a, b, ref]),
                              [_exec(a), _exec(b), _exec(ref)])
    assert record.chosen == "unresolved" and record.rejected == []
    assert any("did not declare" in n for n in record.limitations)
    assert record.unknowns and record.confidence == "unknown"


def test_decision_record_rejects_a_choice_outside_the_options() -> None:
    a, b, ref = _debate()
    record = compose_decision(TASK, _plan("debate", [a, b, ref]),
                              [_exec(a), _exec(b),
                               _exec(ref, evidence=[_decision_evidence("ghost")])])
    assert record.chosen == "unresolved"
    assert any("not a proposer node" in n for n in record.limitations)


def test_decision_record_is_unresolved_when_the_referee_did_not_run() -> None:
    a, b, ref = _debate()
    record = compose_decision(TASK, _plan("debate", [a, b, ref]),
                              [_exec(a), _exec(b), _exec(ref, status="skipped")])
    assert record.chosen == "unresolved" and record.confidence == "unknown"
    assert any("referee did not produce a valid result" in n for n in record.limitations)


def test_decision_record_local_invariants() -> None:
    a, b, ref = _debate()
    options = compose_decision(TASK, _plan("debate", [a, b, ref]),
                             [_exec(a), _exec(b), _exec(ref)]).options
    with pytest.raises(ContractError, match="not a proposer"):
        DecisionRecord(producer=P, created_at=TS, plan_run="p1", referee="ref",
                       question="q", options=options, chosen="ghost",
                       rejected=["a", "b"])
    with pytest.raises(ContractError, match="rejected"):
        DecisionRecord(producer=P, created_at=TS, plan_run="p1", referee="ref",
                       question="q", options=options, chosen="a", rejected=[])


# --- concurrent scheduling (fake _run_node: no child runs, pure engine) -----------------------


def _plan_file(path: Path, nodes: list[dict[str, Any]], pattern: str) -> Path:
    path.write_text(json.dumps({"task_id": "from-file", "pattern": pattern,
                                "source": "file", "profile": "max", "nodes": nodes}),
                    encoding="utf-8")
    return path


def _file_node(nid: str, provider: str, capability: str, action: str,
               *deps: str, role: str = "standalone", inputs: bool = True) -> dict[str, Any]:
    node: dict[str, Any] = {"id": nid, "role": role, "provider": provider,
                            "capability": capability, "action": action}
    if deps:
        node["depends_on"] = [_dep(d) for d in deps]
        node["inputs"] = list(deps) if inputs else []
    return node


def _executor(root: Path, entries: list[dict[str, Any]]) -> tuple[PlanExecutor, RunStore]:
    """Executor over the real subprocess transport: describe/health/plan reach the
    fixture providers; ``_run_node`` is faked only in the scheduling unit tests."""
    forge = make_workspace(root, entries)
    store = RunStore(forge)
    return PlanExecutor(Forger(root, Registry(forge), store)), store


def _fake_ok(node: PlanNode) -> NodeExecution:
    return _exec(node)


@pytest.fixture
def concurrency() -> dict[str, Any]:
    return {"active": 0, "max": 0, "lock": threading.Lock(), "done": []}


def _sleepy(concurrency: dict[str, Any], delay: float = 0.05):
    def fake(self: PlanExecutor, trace: Any, plan: ExecutionPlan, node: PlanNode,
             sources: Any, levels: Any, parent: Any = None) -> NodeExecution:
        with concurrency["lock"]:
            concurrency["active"] += 1
            concurrency["max"] = max(concurrency["max"], concurrency["active"])
        time.sleep(delay)
        with concurrency["lock"]:
            concurrency["active"] -= 1
            concurrency["done"].append(node.id)
        return _fake_ok(node)
    return fake


def test_parallel_levels_run_bounded_and_recorded_in_topological_order(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, concurrency: dict[str, Any]) -> None:
    executor, store = _executor(tmp_path, [SPARK_PLAN_ENTRY, API_PLAN_ENTRY])
    monkeypatch.setattr(PlanExecutor, "_run_node", _sleepy(concurrency))
    nodes = [_file_node(f"n{i}", "fixture-spark", "spark.performance", "diagnose")
             for i in range(1, 6)]  # five independent nodes > MAX_PARALLEL_NODES
    nodes.append(_file_node("top", "fixture-api", "api.contract", "review", "n1", "n2"))
    plan_file = _plan_file(tmp_path / "plan.json", nodes, "parallel")
    out = executor.run(PlanCommand(intent="six nodes", profile="max",
                                   plan_file=plan_file, execute=True))
    assert out.status == "ok" and out.result is not None
    assert concurrency["max"] > 1 and concurrency["max"] <= MAX_PARALLEL_NODES
    assert out.result.order == ["n1", "n2", "n3", "n4", "n5", "top"]
    assert [o.node for o in out.result.nodes] == out.result.order  # topological, not arrival
    assert sorted(concurrency["done"]) == sorted(out.result.order)


def test_delegate_subtasks_have_no_handoffs_and_run_together(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, concurrency: dict[str, Any]) -> None:
    executor, _ = _executor(tmp_path, [SPARK_PLAN_ENTRY, API_PLAN_ENTRY])
    seen_sources: dict[str, list[str]] = {}

    def fake(self: PlanExecutor, trace: Any, plan: ExecutionPlan, node: PlanNode,
             sources: Any, levels: Any, parent: Any = None) -> NodeExecution:
        seen_sources[node.id] = [s.node for s in sources]
        return _sleepy(concurrency)(self, trace, plan, node, sources, levels)

    monkeypatch.setattr(PlanExecutor, "_run_node", fake)
    plan_file = _plan_file(tmp_path / "plan.json", [
        _file_node("n1", "fixture-spark", "spark.performance", "diagnose"),
        _file_node("n2", "fixture-api", "api.contract", "review")], "delegate")
    out = executor.run(PlanCommand(intent="two subtasks", profile="max",
                                   plan_file=plan_file, execute=True))
    assert out.status == "ok" and concurrency["max"] == 2  # a single level, both together
    assert seen_sources == {"n1": [], "n2": []}  # delegate: no specialist handoff


def test_parallel_partial_failure_skips_only_the_dependents(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    executor, _ = _executor(tmp_path, [SPARK_PLAN_ENTRY, API_PLAN_ENTRY])

    def fake(self: PlanExecutor, trace: Any, plan: ExecutionPlan, node: PlanNode,
             sources: Any, levels: Any, parent: Any = None) -> NodeExecution:
        if node.id == "bad":
            return NodeExecution(
                node=node, provider=None, handoff=None, result=None, reached_execute=True,
                outcome=NodeOutcome(
                    node="bad", status="provider_failure", run_id="r-bad",
                    error=ErrorInfo(code="FORGE-TEST", detail="boom"),
                    reproducibility=ReproducibilityInfo(level="unknown")))
        return _fake_ok(node)

    monkeypatch.setattr(PlanExecutor, "_run_node", fake)
    plan_file = _plan_file(tmp_path / "plan.json", [
        _file_node("bad", "fixture-spark", "spark.performance", "diagnose"),
        _file_node("down", "fixture-api", "api.contract", "review", "bad"),
        _file_node("free", "fixture-api", "api.contract", "lint")], "parallel")
    out = executor.run(PlanCommand(intent="one fails", profile="max",
                                   plan_file=plan_file, execute=True))
    assert out.status == "partial" and out.result is not None
    statuses = {n.node: (n.status, n.blocked_by) for n in out.result.nodes}
    assert statuses == {"bad": ("provider_failure", None), "down": ("skipped", "bad"),
                        "free": ("ok", None)}
    assert out.result.order == ["bad", "down", "free"]


# --- end to end with the fixture providers -----------------------------------------------------


def _assert_closed(store: RunStore, run_id: str, status: str) -> ExecutionReceipt:
    from theforge.explain import build_explain_report
    receipt = store.read_contract(run_id, "receipt", ExecutionReceipt)
    assert receipt.kind == "plan" and receipt.status == status
    report = build_explain_report(store, run_id)
    assert report.integrity.divergences == [], report.integrity.divergences
    return receipt


def test_debate_e2e_persists_a_bound_decision_record(tmp_path: Path) -> None:
    executor, store = _executor(tmp_path, [SPARK_PLAN_ENTRY, API_PLAN_ENTRY, REFEREE_ENTRY])
    plan_file = _plan_file(tmp_path / "plan.json", [
        _file_node("n1", "fixture-spark", "spark.performance", "diagnose",
                   role="proposer"),
        _file_node("n2", "fixture-api", "api.contract", "review", role="proposer"),
        _file_node("ref", "fixture-referee", "judge.decide", "decide", "n1", "n2",
                   role="referee")], "debate")
    out = executor.run(PlanCommand(intent="two designs, one referee", profile="max",
                                   plan_file=plan_file, execute=True))
    assert out.status == "ok" and out.result is not None
    assert out.result.order == ["n1", "n2", "ref"]
    # The referee ran a full child run with the proposers' handoff.
    ref = out.result.nodes[-1]
    assert ref.run_id is not None
    handoff = store.read(ref.run_id, "handoff")
    assert {item["origin"]["node"] for item in handoff["items"]} == {"n1", "n2"}
    # The DecisionRecord artifact: persisted, hash-bound by result and receipt.
    decision = store.read(out.run_id, "decision")
    assert decision["schema"] == "theforge/DecisionRecord/v1"
    assert decision["chosen"] == "n1" and decision["rejected"] == ["n2"]
    assert decision["confidence"] == "high"
    assert out.result.decision_sha256 == store.persisted_sha256(out.run_id, "decision")
    receipt = _assert_closed(store, out.run_id, "ok")
    assert receipt.plan is not None
    assert receipt.plan.decision_sha256 == store.persisted_sha256(out.run_id, "decision")
    # The decision is visible in the rendered explain report.
    from theforge.cli import render
    from theforge.contracts import to_dict
    from theforge.explain import build_explain_report
    text = render.explain_report(to_dict(build_explain_report(store, out.run_id)))
    assert "Decision:    n1" in text and "Rationale:" in text


def test_debate_e2e_without_the_convention_is_unresolved(tmp_path: Path) -> None:
    # The referee is a plain provider: no ``decision`` evidence -> honest unresolved.
    executor, store = _executor(tmp_path, [SPARK_PLAN_ENTRY, API_PLAN_ENTRY])
    plan_file = _plan_file(tmp_path / "plan.json", [
        _file_node("n1", "fixture-spark", "spark.performance", "diagnose",
                   role="proposer"),
        _file_node("n2", "fixture-api", "api.contract", "review", role="proposer"),
        _file_node("ref", "fixture-api", "api.contract", "lint", "n1", "n2",
                   role="referee")], "debate")
    out = executor.run(PlanCommand(intent="indecisive referee", profile="max",
                                   plan_file=plan_file, execute=True))
    assert out.status == "ok" and out.result is not None
    decision = store.read(out.run_id, "decision")
    assert decision["chosen"] == "unresolved" and decision["rejected"] == []
    assert any("did not declare" in n for n in decision["limitations"])
    assert out.result.unknowns == decision["unknowns"]
    _assert_closed(store, out.run_id, "ok")


def test_debate_e2e_cites_both_positions(tmp_path: Path) -> None:
    """Wave O concrete proof — the canonical cross-forge question: 'does this
    transformation belong in the Spark pipeline or the API?'. Each proposer's
    position, evidence and risks land on its DecisionOption verbatim; the
    record cites both, never a majority vote."""
    executor, store = _executor(tmp_path, [SPARK_DEBATE_ENTRY, API_DEBATE_ENTRY,
                                           REFEREE_ENTRY])
    plan_file = _plan_file(tmp_path / "plan.json", [
        _file_node("n1", "fixture-spark", "spark.performance", "diagnose",
                   role="proposer"),
        _file_node("n2", "fixture-api", "api.contract", "review", role="proposer"),
        _file_node("ref", "fixture-referee", "judge.decide", "decide", "n1", "n2",
                   role="referee")], "debate")
    out = executor.run(PlanCommand(
        intent="essa transformação deve ficar no pipeline Spark ou na API?",
        profile="max", plan_file=plan_file, execute=True))
    assert out.status == "ok" and out.result is not None
    decision = store.read(out.run_id, "decision")
    options = {o["node"]: o for o in decision["options"]}
    # Both positions cited, verbatim — proposal, evidence and risks each.
    assert options["n1"]["position"] == \
        "keep the transformation in the Spark pipeline"
    assert options["n1"]["evidence"] == ["e1"]
    assert options["n1"]["risks"] == [
        "r1: API-layer transforms couple the contract to data volume"]
    assert options["n2"]["position"] == \
        "move the transformation into the API layer"
    assert options["n2"]["evidence"] == ["e1"]
    assert options["n2"]["risks"] == []  # 'medium' is a tradeoff, not a risk
    assert sorted(decision["tradeoffs"]) == [
        "n1: p1: keep the transformation in the Spark pipeline",
        "n1: r1: API-layer transforms couple the contract to data volume",
        "n2: p1: move the transformation into the API layer",
        "n2: r1: pipeline placement adds a redeploy per schema change",
    ]
    # The referee's choice follows the evidence handed to it — recorded, never
    # invented by the core.
    assert decision["chosen"] == "n1" and decision["rejected"] == ["n2"]
    assert decision["rationale"] == \
        "n1's proposal is the one with evidence-backed tradeoffs"
    # The referee received every item the proposers produced (outcome,
    # findings, evidence, verification) — the full record of what the
    # choice weighed.
    assert decision["evidence"] == [
        "n1:e1", "n1:outcome", "n1:p1", "n1:r1", "n1:verification",
        "n2:e1", "n2:outcome", "n2:p1", "n2:r1", "n2:verification"]
    receipt = _assert_closed(store, out.run_id, "ok")
    assert receipt.plan is not None
    # The rendered explain report shows the positions, not just the winner.
    from theforge.cli import render
    from theforge.contracts import to_dict
    from theforge.explain import build_explain_report
    text = render.explain_report(to_dict(build_explain_report(store, out.run_id)))
    assert "keep the transformation in the Spark pipeline" in text
    assert "move the transformation into the API layer" in text
    assert "Decision:    n1" in text


def test_debate_e2e_hierarchical_domain_verdicts(tmp_path: Path) -> None:
    """Cycle 3.1 phases 39-40 — the hierarchical debate. Each proposer already
    resolved its *internal* debate and surfaces only the domain verdict
    (evidence ``id="decision"``, the projection of its own DecisionRecord).
    The referee weighs the two domain verdicts; the core composes one
    cross-domain record whose options stay at provider-node granularity —
    the specialists' internals are never replayed as plan nodes."""
    executor, store = _executor(tmp_path, [SPARK_DOMAIN_ENTRY, API_DOMAIN_ENTRY,
                                           REFEREE_ENTRY])
    plan_file = _plan_file(tmp_path / "plan.json", [
        _file_node("n1", "fixture-spark-domain", "spark.performance", "diagnose",
                   role="proposer"),
        _file_node("n2", "fixture-api-domain", "api.contract", "review",
                   role="proposer"),
        _file_node("ref", "fixture-referee", "judge.decide", "decide", "n1", "n2",
                   role="referee")], "debate")
    out = executor.run(PlanCommand(
        intent="essa transformação deve ficar no pipeline Spark ou na API?",
        profile="max", plan_file=plan_file, execute=True))
    assert out.status == "ok" and out.result is not None

    # The referee's handoff carried each domain verdict verbatim — epistemic
    # status and claim exactly as the specialist decided internally.
    ref_run = out.result.nodes[-1].run_id
    assert ref_run is not None
    handoff = store.read(ref_run, "handoff")
    verdicts = {item["origin"]["node"]: item for item in handoff["items"]
                if item["kind"] == "evidence" and item["id"] == "decision"}
    assert set(verdicts) == {"n1", "n2"}
    assert verdicts["n1"]["epistemic"] == "confirmed"
    assert verdicts["n1"]["claim"] == "data-side transformation"
    assert verdicts["n1"]["origin"]["provider"]["id"] == "fixture-spark-domain"
    assert verdicts["n2"]["claim"] == "api-side transformation"
    assert verdicts["n2"]["origin"]["provider"]["id"] == "fixture-api-domain"

    decision = store.read(out.run_id, "decision")
    assert decision["schema"] == "theforge/DecisionRecord/v1"
    # Cross-domain: the two options are the two domains — one per provider node.
    options = {o["node"]: o for o in decision["options"]}
    assert set(options) == {"n1", "n2"}
    assert options["n1"]["provider"] == "fixture-spark-domain"
    assert options["n2"]["provider"] == "fixture-api-domain"
    # The option cites the domain verdict as part of its evidence; the record's
    # evidence list names the verdict items handed to the referee by origin.
    assert "decision" in options["n1"]["evidence"]
    assert "decision" in options["n2"]["evidence"]
    assert "n1:decision" in decision["evidence"]
    assert "n2:decision" in decision["evidence"]
    # Nothing below node granularity enters the record: no internal role or
    # sub-option appears as an option, a rejection, or the choice.
    assert decision["chosen"] == "n1" and decision["rejected"] == ["n2"]
    assert all(o["node"] in {"n1", "n2"} for o in decision["options"])
    _assert_closed(store, out.run_id, "ok")


def test_debate_e2e_single_provider_slate_is_refused(tmp_path: Path) -> None:
    """Phase 39 enforced end to end: proposers on one provider are that
    specialist's internal disagreement — the plan is refused before any node
    runs, with the boundary as the reason."""
    executor, store = _executor(tmp_path, [SPARK_PLAN_ENTRY, REFEREE_ENTRY])
    plan_file = _plan_file(tmp_path / "plan.json", [
        _file_node("n1", "fixture-spark", "spark.performance", "diagnose",
                   role="proposer"),
        _file_node("n2", "fixture-spark", "spark.performance", "review",
                   role="proposer"),
        _file_node("ref", "fixture-referee", "judge.decide", "decide", "n1", "n2",
                   role="referee")], "debate")
    out = executor.run(PlanCommand(intent="internal spark disagreement",
                                   profile="max", plan_file=plan_file,
                                   execute=True))
    assert out.status == "refused"
    assert out.result is None  # rejected before any node ran
    assert out.error is not None and out.error.code == "FORGE-PLAN-INVALID"
    assert "cross-domain boundary" in out.error.detail
    assert out.plan is not None
    assert any("cross-domain boundary" in v.detail for v in out.plan.violations)
    assert store.read_optional(out.run_id, "decision") is None


def test_delegate_e2e_runs_independent_specialists(tmp_path: Path) -> None:
    executor, store = _executor(tmp_path, [SPARK_PLAN_ENTRY, API_PLAN_ENTRY])
    plan_file = _plan_file(tmp_path / "plan.json", [
        _file_node("n1", "fixture-spark", "spark.performance", "diagnose"),
        _file_node("n2", "fixture-api", "api.contract", "review")], "delegate")
    out = executor.run(PlanCommand(intent="two bounded subtasks", profile="max",
                                   plan_file=plan_file, execute=True))
    assert out.status == "ok" and out.result is not None
    assert out.result.order == ["n1", "n2"]
    for node in out.result.nodes:
        assert node.status == "ok" and node.run_id is not None
        assert store.read_optional(node.run_id, "handoff") is None  # no specialist wiring
        child = store.read_contract(node.run_id, "receipt", ExecutionReceipt)
        assert child.parent_run == out.run_id
    _assert_closed(store, out.run_id, "ok")


def test_parallel_e2e_partial_failure_keeps_independent_nodes(tmp_path: Path) -> None:
    executor, store = _executor(tmp_path, [bad_entry("refuse", "bad-r"),
                                           SPARK_PLAN_ENTRY, API_PLAN_ENTRY])
    plan_file = _plan_file(tmp_path / "plan.json", [
        _file_node("a", "bad-r", "bad.thing", "run"),
        _file_node("b", "fixture-spark", "spark.performance", "diagnose"),
        _file_node("c", "fixture-api", "api.contract", "review", "a")], "parallel")
    out = executor.run(PlanCommand(intent="one refuses, one free, one dependent",
                                   profile="max", plan_file=plan_file, execute=True))
    assert out.status == "partial" and out.result is not None
    statuses = {n.node: (n.status, n.blocked_by) for n in out.result.nodes}
    assert statuses == {"a": ("refused", None), "b": ("ok", None),
                        "c": ("skipped", "a")}
    assert out.result.order == ["a", "b", "c"]
    _assert_closed(store, out.run_id, "partial")


def test_concurrent_plan_result_is_validated_and_hash_bound(tmp_path: Path) -> None:
    executor, store = _executor(tmp_path, [SPARK_PLAN_ENTRY, API_PLAN_ENTRY])
    plan_file = _plan_file(tmp_path / "plan.json", [
        _file_node("n1", "fixture-spark", "spark.performance", "diagnose"),
        _file_node("n2", "fixture-api", "api.contract", "review")], "parallel")
    out = executor.run(PlanCommand(intent="parallel pair", profile="max",
                                   plan_file=plan_file, execute=True))
    assert out.status == "ok" and out.result is not None
    result = store.read_contract(out.run_id, "plan-result", PlanResult)
    assert result == out.result and result.decision_sha256 is None
    receipt = _assert_closed(store, out.run_id, "ok")
    assert receipt.plan is not None and receipt.plan.decision_sha256 is None
    assert receipt.plan.plan_result_sha256 == store.persisted_sha256(
        out.run_id, "plan-result")
