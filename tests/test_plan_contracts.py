"""Plan, handoff and additive protocol fields (cross-forge-foundation, task 1.2)."""

import ast
from pathlib import Path
from typing import Any, get_args

import pytest

from theforge.contracts import (
    ContractError,
    ExecuteRequest,
    ForgeManifest,
    RoutingDecision,
    from_dict,
    to_dict,
)
from theforge.contracts import types as T
from theforge.contracts.codes import Codes
from theforge.contracts.handoff import HANDOFF_SCHEMA, Handoff, HandoffItem, HandoffOrigin
from theforge.contracts.plan import (
    PLAN_RESULT_SCHEMA,
    PLAN_SCHEMA,
    ExecutionPlan,
    NodeOutcome,
    PlanDependency,
    PlanEstimate,
    PlanRequest,
    PlanResult,
    Synthesis,
)
from theforge.contracts.verification import ReproducibilityInfo
from theforge.planning.execution import NodeExecution, SourceResult

P = {"id": "theforge", "version": "1"}
SHA = "a" * 64
TASK = {"producer": P, "created_at": "2026-01-01T00:00:00Z", "id": "t1", "intent": "x",
        "workspace_root": "/ws"}
CONTEXT = {"producer": P, "created_at": "2026-01-01T00:00:00Z", "status": "complete",
           "task_id": "t1", "provider_id": "demo", "root": "/ws", "budget_bytes": 10}
CONTRACTS_DIR = Path(__file__).parents[1] / "src" / "theforge" / "contracts"


def node(nid: str = "a", **overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {"id": nid, "role": "standalone", "provider": "demo",
                            "capability": "demo.echo", "action": "echo"}
    data.update(overrides)
    return data


def plan_dict(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "producer": P, "created_at": "2026-01-01T00:00:00Z", "status": "validated",
        "plan_run": "p1", "task_id": "t1", "pattern": "route", "source": "decomposed",
        "profile": "balanced", "nodes": [node()],
    }
    data.update(overrides)
    return data


def origin() -> dict[str, Any]:
    return {"plan_run": "p1", "node": "a", "run_id": "r1",
            "provider": {"id": "spark", "version": "2.0"}}


def handoff_dict(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "producer": P, "created_at": "2026-01-01T00:00:00Z", "plan_run": "p1",
        "target_node": "b",
        "items": [
            {"kind": "decision", "id": "outcome", "origin": origin(), "epistemic": "observed",
             "claim": "status=ok capability=demo.echo action=echo"},
            {"kind": "evidence", "id": "e1", "origin": origin(), "epistemic": "inferred",
             "subject": "job.py", "claim": "reads s3", "location": {"path": "job.py", "line": 3},
             "hash": SHA},
            {"kind": "finding", "id": "f1", "origin": origin(), "subject": "x",
             "severity": "high", "evidence_ids": ["e1"]},
            {"kind": "artifact", "id": "out/report.json", "origin": origin(), "hash": SHA},
        ],
    }
    data.update(overrides)
    return data


def plan_result_dict(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "producer": P, "created_at": "2026-01-01T00:00:00Z", "status": "partial",
        "plan_run": "p1", "order": ["a", "b"],
        "nodes": [
            {"node": "a", "status": "provider_failure", "run_id": "r1",
             "receipt_sha256": SHA, "error": {"code": "FORGE-RESULT-INVALID", "detail": "x"},
             "reproducibility": {"level": "unknown", "reasons": ["no result"]}},
            {"node": "b", "status": "skipped", "blocked_by": "a"},
        ],
        "synthesis": {
            "nodes": [{"node": "a", "provider": "demo", "capability": "demo.echo",
                       "action": "echo", "status": "provider_failure", "run_id": "r1",
                       "findings": [{"id": "f1", "title": "t"}],
                       "evidence_by_epistemic": {"observed": 1}}],
            "handoffs": [{"source": "a", "target": "b", "items": 0, "truncated": False}],
            "failures": ["a: provider_failure FORGE-RESULT-INVALID: x"],
        },
        "reproducibility": {"level": "non_reproducible", "reasons": ["a: external"]},
    }
    data.update(overrides)
    return data


def roundtrip(cls: type[Any], data: dict[str, Any]) -> Any:
    obj = from_dict(cls, data, strict=True)
    again = from_dict(cls, to_dict(obj), strict=True)
    assert again == obj
    return obj


# --- shared types: single definition --------------------------------------------------


def test_shared_types_and_limits() -> None:
    assert get_args(T.PlanPattern) == ("route", "delegate", "parallel", "pipeline", "debate")
    assert frozenset(get_args(T.PlanPattern)) == T.EXECUTABLE_PATTERNS
    assert frozenset({"delegate", "parallel", "debate"}) == T.CONCURRENT_PATTERNS
    assert T.MAX_PARALLEL_NODES > 0
    assert "planned" in get_args(T.Outcome)
    assert get_args(T.EdgeEpistemic) == ("explicit", "observed", "inferred")
    assert get_args(T.Reproducibility) == (
        "reproducible", "partially_reproducible", "non_reproducible", "unknown")
    assert (T.MAX_PLAN_NODES, T.MAX_HANDOFF_ITEMS, T.MAX_HANDOFF_BYTES, T.MAX_CLAIM_CHARS,
            T.MAX_REPO_DEPTH, T.MAX_REPOSITORIES, T.MAX_GRAPH_NODES) == (
        8, 256, 262_144, 500, 3, 64, 2_000)


SHARED = {"PlanPattern", "EXECUTABLE_PATTERNS", "Outcome", "EdgeEpistemic", "Reproducibility",
          "MAX_PLAN_NODES", "MAX_HANDOFF_ITEMS", "MAX_HANDOFF_BYTES", "MAX_CLAIM_CHARS",
          "MAX_REPO_DEPTH", "MAX_REPOSITORIES", "MAX_GRAPH_NODES"}


def test_shared_names_are_assigned_only_in_types_module() -> None:
    offenders: list[str] = []
    for path in sorted(CONTRACTS_DIR.glob("*.py")):
        if path.name == "types.py":
            continue
        for stmt in ast.parse(path.read_text(encoding="utf-8")).body:
            targets: list[ast.expr] = []
            if isinstance(stmt, ast.Assign):
                targets = list(stmt.targets)
            elif isinstance(stmt, ast.AnnAssign):
                targets = [stmt.target]
            offenders += [f"{path.name}:{t.id}" for t in targets
                          if isinstance(t, ast.Name) and t.id in SHARED]
    assert offenders == []


# --- additive fields keep old data valid -----------------------------------------------


def routing_dict(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "schema": "theforge/RoutingDecision/v1", "producer": P,
        "created_at": "2026-01-01T00:00:00Z", "status": "no_route", "task_id": "t1",
        "reason": "none", "confidence": {"level": "low"},
    }
    data.update(overrides)
    return data


def test_routing_decision_without_pattern_rereads_strictly_as_route() -> None:
    decision = from_dict(RoutingDecision, routing_dict(), strict=True)
    assert decision.pattern == "route"
    assert from_dict(RoutingDecision, to_dict(decision), strict=True) == decision


def test_routing_decision_accepts_every_plan_pattern_and_rejects_unknown() -> None:
    for pattern in get_args(T.PlanPattern):
        assert from_dict(RoutingDecision, routing_dict(pattern=pattern),
                         strict=True).pattern == pattern
    with pytest.raises(ContractError, match="pattern"):
        from_dict(RoutingDecision, routing_dict(pattern="swarm"), strict=True)


def test_execute_request_without_handoff_stays_valid() -> None:
    req = from_dict(ExecuteRequest, {"task": TASK, "capability": "demo.echo",
                                     "action": "echo", "context": CONTEXT}, strict=True)
    assert req.handoff is None


def test_execute_request_carries_handoff() -> None:
    data = {"task": TASK, "capability": "demo.echo", "action": "echo", "context": CONTEXT,
            "handoff": handoff_dict()}
    req = roundtrip(ExecuteRequest, data)
    assert req.handoff is not None and len(req.handoff.items) == 4


def test_manifest_without_new_fields_has_compatible_defaults() -> None:
    data = {"id": "demo", "version": "1", "protocols": ["forge/v1"],
            "ops": ["describe", "health", "execute"],
            "capabilities": [{"id": "demo.echo", "actions": ["echo"], "default_action": "echo",
                              "state": "supported", "operation_class": "read_only"}],
            "execution": {"local": True}}
    manifest = from_dict(ForgeManifest, data, strict=True)
    assert manifest.capabilities[0].accepts_handoff is False
    assert manifest.execution.deterministic is None
    data["capabilities"][0]["accepts_handoff"] = True  # type: ignore[index]
    data["execution"] = {"deterministic": True}
    declared = roundtrip(ForgeManifest, data)
    assert declared.capabilities[0].accepts_handoff is True
    assert declared.execution.deterministic is True


# --- plan -------------------------------------------------------------------------------


def test_plan_rereads_strictly_with_defaults() -> None:
    plan = roundtrip(ExecutionPlan, plan_dict())
    assert plan.schema == PLAN_SCHEMA
    assert plan.nodes[0].targets == ["."] and plan.nodes[0].depends_on == []
    assert plan.violations == [] and plan.nodes[0].estimate is None


def test_full_pipeline_plan_rereads_strictly() -> None:
    nodes = [
        node("spark", role="producer", estimate={"context_needed": ["jobs/*.py"],
                                                 "operation_class": "read_only",
                                                 "expected_artifacts": ["out.json"],
                                                 "unknowns": ["u"]}),
        node("api", role="consumer", targets=["orders-api"], inputs=["spark"],
             depends_on=[{"node": "spark", "epistemic": "inferred", "rule": "intent-order",
                          "evidence": "keyword 'spark'@3 < keyword 'api'@9"}],
             limitations=["capability-alias: x"]),
    ]
    plan = roundtrip(ExecutionPlan, plan_dict(pattern="pipeline", nodes=nodes,
                                              limitations=["l"], unknowns=["u"]))
    assert plan.nodes[1].depends_on[0].rule == "intent-order"


def test_rejected_plan_carries_violations() -> None:
    violation = {"code": "FORGE-PLAN-INVALID", "node": "a", "detail": "cycle"}
    plan = roundtrip(ExecutionPlan, plan_dict(status="rejected", violations=[violation]))
    assert plan.violations[0].code == "FORGE-PLAN-INVALID"


def test_plan_status_must_agree_with_violations() -> None:
    with pytest.raises(ContractError, match="violations"):
        from_dict(ExecutionPlan, plan_dict(status="rejected"), strict=True)
    with pytest.raises(ContractError, match="violations"):
        from_dict(ExecutionPlan, plan_dict(violations=[
            {"code": "FORGE-PLAN-INVALID", "node": None, "detail": "x"}]), strict=True)


def test_plan_rejects_wrong_schema_unknown_field_and_pattern() -> None:
    with pytest.raises(ContractError, match="schema"):
        from_dict(ExecutionPlan, plan_dict(schema="theforge/ExecutionPlan/v2"), strict=True)
    with pytest.raises(ContractError, match="unknown field"):
        from_dict(ExecutionPlan, plan_dict(extra=1), strict=True)
    with pytest.raises(ContractError, match="pattern"):
        from_dict(ExecutionPlan, plan_dict(pattern="swarm"), strict=True)


def test_inferred_dependency_without_rule_is_rejected_locally() -> None:
    with pytest.raises(ContractError, match="rule"):
        PlanDependency(node="a", epistemic="inferred", evidence="x")
    with pytest.raises(ContractError, match="rule"):
        from_dict(ExecutionPlan, plan_dict(nodes=[node("b", depends_on=[
            {"node": "a", "epistemic": "inferred", "evidence": "x"}])]), strict=True)
    assert PlanDependency(node="a", epistemic="explicit", evidence="plan file").rule is None


def test_plan_request_and_estimate_cross_the_protocol_leniently() -> None:
    req = roundtrip(PlanRequest, {"task": TASK, "capability": "demo.echo", "action": "echo"})
    assert req.task.id == "t1"
    estimate = from_dict(PlanEstimate, {"context_needed": ["a"], "future": 1})
    assert estimate.operation_class is None and estimate.context_needed == ["a"]
    assert roundtrip(PlanEstimate, {}) == PlanEstimate()


def test_plan_result_rereads_strictly() -> None:
    result = roundtrip(PlanResult, plan_result_dict())
    assert result.schema == PLAN_RESULT_SCHEMA
    assert result.nodes[1].blocked_by == "a" and result.nodes[1].run_id is None
    assert result.synthesis.nodes[0].findings[0].id == "f1"
    assert result.reproducibility == ReproducibilityInfo(level="non_reproducible",
                                                         reasons=["a: external"])


def test_plan_result_rejects_wrong_schema_and_bad_reproducibility() -> None:
    with pytest.raises(ContractError, match="schema"):
        from_dict(PlanResult, plan_result_dict(schema="x"), strict=True)
    with pytest.raises(ContractError, match="level"):
        from_dict(PlanResult, plan_result_dict(reproducibility={"level": "maybe"}), strict=True)


# --- handoff ----------------------------------------------------------------------------


def test_handoff_rereads_strictly() -> None:
    handoff = roundtrip(Handoff, handoff_dict())
    assert handoff.schema == HANDOFF_SCHEMA and handoff.truncated is False
    evidence = handoff.items[1]
    assert evidence.epistemic == "inferred"
    assert evidence.origin == HandoffOrigin(plan_run="p1", node="a", run_id="r1",
                                            provider=T.Producer(id="spark", version="2.0"))


def test_handoff_claim_is_capped() -> None:
    ok = {"kind": "decision", "id": "outcome", "origin": origin(), "epistemic": "observed",
          "claim": "x" * T.MAX_CLAIM_CHARS}
    assert from_dict(HandoffItem, ok, strict=True).claim == "x" * T.MAX_CLAIM_CHARS
    with pytest.raises(ContractError, match="claim"):
        from_dict(HandoffItem, {**ok, "claim": "x" * (T.MAX_CLAIM_CHARS + 1)}, strict=True)


def test_handoff_item_shape_per_kind() -> None:
    base = {"origin": origin()}
    with pytest.raises(ContractError, match="epistemic"):
        from_dict(HandoffItem, {**base, "kind": "evidence", "id": "e1"})
    with pytest.raises(ContractError, match="epistemic"):
        from_dict(HandoffItem, {**base, "kind": "finding", "id": "f1", "epistemic": "observed"})
    with pytest.raises(ContractError, match="hash"):
        from_dict(HandoffItem, {**base, "kind": "artifact", "id": "out.json"})
    with pytest.raises(ContractError, match="sha256"):
        from_dict(HandoffItem, {**base, "kind": "artifact", "id": "o", "hash": "nope"})


def test_handoff_truncation_fields_are_consistent() -> None:
    assert roundtrip(Handoff, handoff_dict(truncated=True, dropped=3)).dropped == 3
    with pytest.raises(ContractError, match="dropped"):
        from_dict(Handoff, handoff_dict(dropped=2), strict=True)
    with pytest.raises(ContractError, match="dropped"):
        from_dict(Handoff, handoff_dict(truncated=True, dropped=-1), strict=True)
    with pytest.raises(ContractError, match="schema"):
        from_dict(Handoff, handoff_dict(schema="theforge/Handoff/v2"), strict=True)


# --- in-memory execution values ---------------------------------------------------------


def test_execution_values_hold_plan_contracts() -> None:
    plan = from_dict(ExecutionPlan, plan_dict(), strict=True)
    outcome = NodeOutcome(node="a", status="skipped", blocked_by="x")
    execution = NodeExecution(node=plan.nodes[0], outcome=outcome, result=None, handoff=None,
                              provider=None)
    assert execution.outcome.status == "skipped"
    from theforge.contracts import ExecutionResult
    result = ExecutionResult(producer=T.Producer(id="demo", version="1"),
                             created_at="2026-01-01T00:00:00Z", status="ok")
    source = SourceResult(node="a", run_id="r1", provider=T.Producer(id="demo", version="1"),
                          status="ok", capability="demo.echo", action="echo", result=result)
    assert source.result.status == "ok"
    assert Synthesis(nodes=[]).failures == []


# --- receipt extensions (task 1.5) ------------------------------------------------------


def receipt_dict(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "producer": P, "created_at": "2026-01-01T00:00:00Z", "status": "ok", "run_id": "r1",
        "forge_version": "1", "inputs": {"task_sha256": SHA}, "started_at": "t",
        "finished_at": "t"}
    data.update(overrides)
    return data


def test_receipt_written_before_wave_d_rereads_as_run_with_nothing_recorded() -> None:
    from theforge.contracts import ExecutionReceipt
    receipt = roundtrip(ExecutionReceipt, receipt_dict())
    assert receipt.kind == "run" and receipt.plan is None
    assert receipt.verification_sha256 is None and receipt.reproducibility is None
    assert receipt.parent_run is None and receipt.replay_of is None
    assert receipt.inputs.handoff_sha256 is None


def test_node_and_replay_receipts_reread_strictly() -> None:
    from theforge.contracts import ExecutionReceipt
    receipt = roundtrip(ExecutionReceipt, receipt_dict(
        parent_run="p1", plan_node="a", replay_of="r0", verification_sha256=SHA,
        reproducibility={"level": "reproducible", "reasons": []},
        inputs={"task_sha256": SHA, "handoff_sha256": SHA}))
    assert receipt.plan_node == "a" and receipt.inputs.handoff_sha256 == SHA
    assert receipt.reproducibility == ReproducibilityInfo(level="reproducible")


def test_plan_receipt_requires_plan_refs_and_no_provider() -> None:
    from theforge.contracts import ExecutionReceipt
    refs = {"plan_sha256": SHA, "plan_result_sha256": SHA}
    planned = roundtrip(ExecutionReceipt, receipt_dict(
        kind="plan", status="planned", plan={"plan_sha256": SHA}))
    assert planned.plan is not None and planned.plan.plan_result_sha256 is None
    assert planned.plan.global_stop_sha256 is None
    assert roundtrip(ExecutionReceipt, receipt_dict(kind="plan", plan=refs)).kind == "plan"
    with pytest.raises(ContractError, match="plan references are required"):
        from_dict(ExecutionReceipt, receipt_dict(kind="plan"), strict=True)
    provider = {"id": "demo", "version": "1", "trust": "local"}
    with pytest.raises(ContractError, match="provider must be absent"):
        from_dict(ExecutionReceipt, receipt_dict(kind="plan", plan=refs, provider=provider),
                  strict=True)
    with pytest.raises(ContractError, match="only for plan receipts"):
        from_dict(ExecutionReceipt, receipt_dict(plan=refs), strict=True)


def test_plan_receipt_without_a_plan_only_for_runs_that_produced_none() -> None:
    from theforge.contracts import ExecutionReceipt
    error = {"code": Codes.PLAN_FILE, "detail": "unreadable"}
    for status, extra in (("ambiguous", {}), ("no_route", {}),
                          ("refused", {"error": error})):
        receipt = roundtrip(ExecutionReceipt, receipt_dict(
            kind="plan", status=status, plan={}, **extra))
        assert receipt.plan is not None and receipt.plan.plan_sha256 is None
    for status in ("planned", "ok", "partial"):
        with pytest.raises(ContractError, match="plan.plan_sha256 is required"):
            from_dict(ExecutionReceipt, receipt_dict(kind="plan", status=status, plan={}),
                      strict=True)


def test_planned_status_only_on_plan_receipts() -> None:
    from theforge.contracts import ExecutionReceipt
    with pytest.raises(ContractError, match="'planned' is only valid for plan receipts"):
        from_dict(ExecutionReceipt, receipt_dict(status="planned"), strict=True)


def test_parent_run_and_plan_node_go_together() -> None:
    from theforge.contracts import ExecutionReceipt
    for extra in ({"parent_run": "p1"}, {"plan_node": "a"}):
        with pytest.raises(ContractError, match="go together"):
            from_dict(ExecutionReceipt, receipt_dict(**extra), strict=True)
