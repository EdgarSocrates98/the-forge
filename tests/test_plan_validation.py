"""Relational invariants of plan, handoff, graph and plan result (task 1.4).

Each invariant has a valid and an invalid case asserting the expected ``FORGE-*`` code;
a plan with several faults reports every violation at once (1.2).
"""

from dataclasses import replace
from typing import Any

import pytest

from theforge.contracts.codes import Codes
from theforge.contracts.graph import GraphEdge, GraphNode, WorkspaceGraph
from theforge.contracts.handoff import Handoff, HandoffItem, HandoffOrigin
from theforge.contracts.integrity import (
    IntegrityError,
    check_graph_edge,
    validate_graph,
    validate_handoff,
    validate_plan_result,
    validate_plan_structure,
)
from theforge.contracts.plan import (
    ExecutionPlan,
    NodeOutcome,
    PlanDependency,
    PlanNode,
    PlanResult,
    Synthesis,
)
from theforge.contracts.types import (
    MAX_CLAIM_CHARS,
    MAX_HANDOFF_BYTES,
    MAX_HANDOFF_ITEMS,
    MAX_PLAN_NODES,
    Producer,
)
from theforge.contracts.verification import ReproducibilityInfo

P = Producer(id="theforge", version="1")
TS = "2026-01-01T00:00:00Z"
SHA = "a" * 64


def dep(nid: str, epistemic: Any = "explicit", rule: str | None = None) -> PlanDependency:
    return PlanDependency(node=nid, epistemic=epistemic, rule=rule, evidence="plan file")


def pnode(nid: str, *deps: str, inputs: list[str] | None = None) -> PlanNode:
    return PlanNode(id=nid, role="standalone", provider="demo", capability="demo.echo",
                    action="echo", depends_on=[dep(d) for d in deps],
                    inputs=list(deps) if inputs is None else inputs)


def plan(*nodes: PlanNode, pattern: Any = "pipeline") -> ExecutionPlan:
    return ExecutionPlan(producer=P, created_at=TS, status="validated", plan_run="p1",
                         task_id="t1", pattern=pattern, source="file", profile="max",
                         nodes=list(nodes))


def codes(violations: list[Any]) -> list[tuple[str, str | None]]:
    return [(v.code, v.node) for v in violations]


# --- plan structure ---------------------------------------------------------------------


def test_valid_pipeline_and_route_plans_have_no_violations() -> None:
    assert validate_plan_structure(plan(pnode("a"), pnode("b", "a"), pnode("c", "a", "b"))) == []
    assert validate_plan_structure(plan(pnode("a"), pattern="route")) == []


@pytest.mark.parametrize("bad_id", ["A", "1a", "a_b", "", "a" * 33])
def test_invalid_node_id(bad_id: str) -> None:
    assert codes(validate_plan_structure(plan(pnode(bad_id)))) == [
        (Codes.PLAN_INVALID, bad_id)]


def test_duplicate_node_id() -> None:
    assert codes(validate_plan_structure(plan(pnode("a"), pnode("a")))) == [
        (Codes.PLAN_INVALID, "a")]


def test_dependency_on_missing_node() -> None:
    violations = validate_plan_structure(plan(pnode("a"), pnode("b", "zz")))
    assert codes(violations) == [(Codes.PLAN_INVALID, "b")]
    assert "zz" in violations[0].detail


def test_cycle_is_reported() -> None:
    violations = validate_plan_structure(plan(pnode("a", "b"), pnode("b", "a"), pnode("c")))
    assert codes(violations) == [(Codes.PLAN_INVALID, "a")]
    assert "cycle" in violations[0].detail and "a, b" in violations[0].detail


def test_self_dependency_is_a_cycle() -> None:
    assert codes(validate_plan_structure(plan(pnode("a", "a")))) == [(Codes.PLAN_INVALID, "a")]


def test_inputs_outside_dependencies() -> None:
    violations = validate_plan_structure(plan(pnode("a"), pnode("b", inputs=["a"])))
    assert codes(violations) == [(Codes.PLAN_INVALID, "b")]
    assert "inputs" in violations[0].detail


def test_inputs_may_be_a_subset_of_dependencies() -> None:
    assert validate_plan_structure(plan(pnode("a"), pnode("b", "a", inputs=[]))) == []


def test_node_limit() -> None:
    at_limit = [pnode(f"n{i}") for i in range(MAX_PLAN_NODES)]
    assert validate_plan_structure(plan(*at_limit)) == []
    over = [pnode(f"n{i}") for i in range(MAX_PLAN_NODES + 1)]
    assert codes(validate_plan_structure(plan(*over))) == [(Codes.PLAN_LIMIT, None)]


def test_plan_without_nodes() -> None:
    assert codes(validate_plan_structure(plan())) == [(Codes.PLAN_INVALID, None)]


@pytest.mark.parametrize("pattern", ["delegate", "parallel", "debate"])
def test_reserved_pattern(pattern: str) -> None:
    violations = validate_plan_structure(plan(pnode("a"), pattern=pattern))
    assert codes(violations) == [(Codes.PLAN_PATTERN_RESERVED, None)]
    assert "reserved" in violations[0].detail


def test_route_plan_with_more_than_one_node() -> None:
    violations = validate_plan_structure(plan(pnode("a"), pnode("b"), pattern="route"))
    assert codes(violations) == [(Codes.PLAN_INVALID, None)]


def test_inferred_dependency_without_rule_bypassing_construction() -> None:
    d = dep("a", "inferred", "intent-order")
    object.__setattr__(d, "rule", None)  # defensively: a bypassed local invariant
    bad = replace(pnode("b"), depends_on=[d], inputs=["a"])
    assert codes(validate_plan_structure(plan(pnode("a"), bad))) == [(Codes.PLAN_INVALID, "b")]
    good = replace(pnode("b"), depends_on=[dep("a", "inferred", "intent-order")], inputs=["a"])
    assert validate_plan_structure(plan(pnode("a"), good)) == []


def test_every_violation_is_reported_at_once() -> None:
    nodes = [pnode("a", "b"), pnode("b", "a"), pnode("a"), pnode("Bad"),
             pnode("c", "ghost"), pnode("d", inputs=["a"])]
    nodes += [pnode(f"x{i}") for i in range(MAX_PLAN_NODES)]
    found = codes(validate_plan_structure(plan(*nodes, pattern="debate")))
    assert found == [
        (Codes.PLAN_LIMIT, None),
        (Codes.PLAN_PATTERN_RESERVED, None),
        (Codes.PLAN_INVALID, "a"),  # duplicate id
        (Codes.PLAN_INVALID, "Bad"),  # invalid id
        (Codes.PLAN_INVALID, "c"),  # missing dependency
        (Codes.PLAN_INVALID, "d"),  # inputs outside depends_on
        (Codes.PLAN_INVALID, "a"),  # cycle a <-> b
    ]


def test_structure_validation_is_deterministic() -> None:
    p = plan(pnode("a", "b"), pnode("b", "a"), pnode("c", "ghost"))
    assert validate_plan_structure(p) == validate_plan_structure(p)


# --- handoff ----------------------------------------------------------------------------


def item(i: int, claim: str = "c", subject: str = "s") -> HandoffItem:
    origin = HandoffOrigin(plan_run="p1", node="a", run_id="r1",
                           provider=Producer(id="spark", version="2.0"))
    return HandoffItem(kind="evidence", id=f"e{i}", origin=origin, epistemic="observed",
                       subject=subject, claim=claim)


def handoff(items: list[HandoffItem]) -> Handoff:
    return Handoff(producer=P, created_at=TS, plan_run="p1", target_node="b", items=items)


def test_handoff_within_limits() -> None:
    validate_handoff(handoff([item(i) for i in range(MAX_HANDOFF_ITEMS)]))


def test_handoff_over_item_limit() -> None:
    with pytest.raises(IntegrityError) as err:
        validate_handoff(handoff([item(i) for i in range(MAX_HANDOFF_ITEMS + 1)]))
    assert err.value.code == Codes.PLAN_LIMIT and err.value.field == "items"


def test_handoff_over_byte_limit() -> None:
    subject = "x" * 2048
    count = MAX_HANDOFF_BYTES // len(subject) + 1  # within the item limit
    assert count <= MAX_HANDOFF_ITEMS
    below = MAX_HANDOFF_BYTES // (len(subject) + 512)  # item overhead is well under 512 B
    validate_handoff(handoff([item(i, subject=subject) for i in range(below)]))
    with pytest.raises(IntegrityError) as err:
        validate_handoff(handoff([item(i, subject=subject) for i in range(count)]))
    assert err.value.code == Codes.PLAN_LIMIT
    assert [v.field for v in err.value.violations] == [None]


def test_handoff_claim_over_cap_bypassing_construction() -> None:
    long = item(0)
    object.__setattr__(long, "claim", "x" * (MAX_CLAIM_CHARS + 1))
    with pytest.raises(IntegrityError) as err:
        validate_handoff(handoff([item(1), long]))
    assert err.value.code == Codes.PLAN_LIMIT and err.value.field == "items[1].claim"


# --- graph ------------------------------------------------------------------------------


def graph(edges: list[GraphEdge]) -> WorkspaceGraph:
    nodes = [GraphNode(id="workspace:.", kind="workspace"),
             GraphNode(id="repository:api", kind="repository")]
    return WorkspaceGraph(producer=P, created_at=TS, plan_run="p1", nodes=nodes, edges=edges)


def edge(source: str, target: str) -> GraphEdge:
    return GraphEdge(source=source, target=target, kind="contains", epistemic="observed",
                     evidence="api/.git")


def test_graph_with_existing_endpoints() -> None:
    validate_graph(graph([edge("workspace:.", "repository:api")]))
    assert check_graph_edge(edge("workspace:.", "repository:api"),
                            {"workspace:.", "repository:api"}) is None


@pytest.mark.parametrize(("source", "target"), [
    ("workspace:.", "repository:ghost"), ("repository:ghost", "workspace:."),
])
def test_graph_edge_with_missing_endpoint(source: str, target: str) -> None:
    with pytest.raises(IntegrityError) as err:
        validate_graph(graph([edge("workspace:.", "repository:api"), edge(source, target)]))
    assert err.value.code == Codes.WORKSPACE_GRAPH_EDGE
    assert err.value.field == "edges[1]" and "repository:ghost" in err.value.detail


# --- plan result ------------------------------------------------------------------------


def outcome(nid: str, status: Any = "ok", **kw: Any) -> NodeOutcome:
    if status != "skipped":
        kw.setdefault("run_id", f"r-{nid}")
        kw.setdefault("receipt_sha256", SHA)
    if status in ("ok", "partial"):
        kw.setdefault("result_sha256", SHA)
    return NodeOutcome(node=nid, status=status, **kw)


def presult(status: Any, nodes: list[NodeOutcome], order: list[str] | None = None) -> PlanResult:
    return PlanResult(producer=P, created_at=TS, status=status, plan_run="p1",
                      order=[n.node for n in nodes] if order is None else order,
                      nodes=nodes, synthesis=Synthesis(nodes=[]),
                      reproducibility=ReproducibilityInfo(level="unknown"))


def result_codes(result: PlanResult) -> list[tuple[str, str | None]]:
    with pytest.raises(IntegrityError) as err:
        validate_plan_result(result)
    return [(v.code, v.field) for v in err.value.violations]


def test_valid_plan_results() -> None:
    validate_plan_result(presult("ok", [outcome("a"), outcome("b")]))
    validate_plan_result(presult("partial", [
        outcome("a", "provider_failure"), outcome("b", "skipped", blocked_by="a"),
        outcome("c", "partial")]))
    validate_plan_result(presult("provider_failure", [outcome("a", "provider_failure")]))
    validate_plan_result(presult("refused", [outcome("a", "refused")]))


@pytest.mark.parametrize("status", ["ambiguous", "no_route", "planned"])
def test_plan_result_status_outside_execution_outcomes(status: str) -> None:
    assert result_codes(presult(status, [outcome("a")])) == [(Codes.PLAN_INVALID, "status")]


def test_ok_plan_result_requires_every_node_ok() -> None:
    bad = presult("ok", [outcome("a"), outcome("b", "partial")])
    assert result_codes(bad) == [(Codes.PLAN_INVALID, "nodes[1].status")]


def test_ok_plan_result_requires_every_result_hash() -> None:
    bad = presult("ok", [outcome("a", result_sha256=None)])
    assert result_codes(bad) == [(Codes.PLAN_INVALID, "nodes[0].result_sha256")]


def test_skipped_node_requires_a_blocking_node() -> None:
    bad = presult("partial", [outcome("a", "partial"), outcome("b", "skipped")])
    assert result_codes(bad) == [(Codes.PLAN_INVALID, "nodes[1].blocked_by")]
    unknown = presult("partial", [outcome("a", "partial"),
                                  outcome("b", "skipped", blocked_by="ghost")])
    assert result_codes(unknown) == [(Codes.PLAN_INVALID, "nodes[1].blocked_by")]


@pytest.mark.parametrize("order", [["a"], ["a", "b", "c"], ["a", "a"], ["b", "c"]])
def test_order_must_be_a_permutation_of_the_nodes(order: list[str]) -> None:
    bad = presult("ok", [outcome("a"), outcome("b")], order=order)
    assert result_codes(bad) == [(Codes.PLAN_INVALID, "order")]


def test_permuted_order_is_valid() -> None:
    validate_plan_result(presult("ok", [outcome("a"), outcome("b")], order=["b", "a"]))


def test_plan_result_reports_every_violation() -> None:
    bad = presult("planned", [outcome("a", "partial"), outcome("b", "skipped")], order=["a"])
    assert result_codes(bad) == [
        (Codes.PLAN_INVALID, "status"),
        (Codes.PLAN_INVALID, "nodes[1].blocked_by"),
        (Codes.PLAN_INVALID, "order"),
    ]
