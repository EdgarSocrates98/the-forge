"""Relational invariants of plan, handoff, graph and plan result (task 1.4), plus the
topological order and the registry-aware plan validation (task 2.2).

Each invariant has a valid and an invalid case asserting the expected ``FORGE-*`` code;
a plan with several faults reports every violation at once (1.2).
"""

import itertools
import json
from dataclasses import replace
from pathlib import Path
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
from theforge.contracts.manifest import Capability, ForgeManifest
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
from theforge.errors import UsageError
from theforge.meta import PRODUCER
from theforge.planning import (
    MAX_PLAN_FILE_BYTES,
    blocked_by,
    check_plan,
    checked_plan,
    load_plan_file,
    topological_order,
)
from theforge.profiles import profile_for
from theforge.registry import ProviderEntry, RegistryRecord

P = Producer(id="theforge", version="1")
TS = "2026-01-01T00:00:00Z"
SHA = "a" * 64


def dep(nid: str, epistemic: Any = "explicit", rule: str | None = None) -> PlanDependency:
    return PlanDependency(node=nid, epistemic=epistemic, rule=rule, evidence="plan file")


def pnode(nid: str, *deps: str, inputs: list[str] | None = None) -> PlanNode:
    return PlanNode(
        id=nid,
        role="standalone",
        provider="demo",
        capability="demo.echo",
        action="echo",
        depends_on=[dep(d) for d in deps],
        inputs=list(deps) if inputs is None else inputs,
    )


def plan(*nodes: PlanNode, pattern: Any = "pipeline") -> ExecutionPlan:
    return ExecutionPlan(
        producer=P,
        created_at=TS,
        status="validated",
        plan_run="p1",
        task_id="t1",
        pattern=pattern,
        source="file",
        profile="max",
        nodes=list(nodes),
    )


def codes(violations: list[Any]) -> list[tuple[str, str | None]]:
    return [(v.code, v.node) for v in violations]


# --- plan structure ---------------------------------------------------------------------


def test_valid_pipeline_and_route_plans_have_no_violations() -> None:
    assert validate_plan_structure(plan(pnode("a"), pnode("b", "a"), pnode("c", "a", "b"))) == []
    assert validate_plan_structure(plan(pnode("a"), pattern="route")) == []


@pytest.mark.parametrize("bad_id", ["A", "1a", "a_b", "", "a" * 33])
def test_invalid_node_id(bad_id: str) -> None:
    assert codes(validate_plan_structure(plan(pnode(bad_id)))) == [(Codes.PLAN_INVALID, bad_id)]


def test_duplicate_node_id() -> None:
    assert codes(validate_plan_structure(plan(pnode("a"), pnode("a")))) == [
        (Codes.PLAN_INVALID, "a")
    ]


def test_duplicate_dependency() -> None:
    twice = PlanNode(
        id="b",
        role="consumer",
        provider="demo",
        capability="demo.echo",
        action="echo",
        depends_on=[dep("a"), dep("a", "inferred", "rule-x")],
        inputs=["a"],
    )
    violations = validate_plan_structure(plan(pnode("a"), twice))
    assert codes(violations) == [(Codes.PLAN_INVALID, "b")]
    assert "twice" in violations[0].detail and "'a'" in violations[0].detail


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


def test_unknown_pattern_is_reserved() -> None:
    # Every declared pattern executes (Wave E); a value outside the Literal — only
    # reachable by bypassing contract parsing — is still refused as reserved.
    violations = validate_plan_structure(plan(pnode("a"), pattern="scatter"))
    assert codes(violations) == [(Codes.PLAN_PATTERN_RESERVED, None)]
    assert "reserved" in violations[0].detail


def test_delegate_plan_runs_independent_subtasks() -> None:
    assert validate_plan_structure(plan(pnode("a"), pnode("b"), pattern="delegate")) == []


def test_delegate_plan_rejects_specialist_dependencies() -> None:
    violations = validate_plan_structure(plan(pnode("a"), pnode("b", "a"), pattern="delegate"))
    assert codes(violations) == [(Codes.PLAN_INVALID, "b")]
    assert "delegate" in violations[0].detail


def proposer(nid: str, provider: str | None = None) -> PlanNode:
    return replace(
        pnode(nid), role="proposer", provider=provider if provider is not None else f"demo-{nid}"
    )


def referee(nid: str, *proposer_ids: str) -> PlanNode:
    return PlanNode(
        id=nid,
        role="referee",
        provider="demo",
        capability="demo.echo",
        action="echo",
        depends_on=[dep(p) for p in proposer_ids],
        inputs=list(proposer_ids),
    )


def test_debate_plan_shape() -> None:
    p = plan(proposer("a"), proposer("b"), referee("r", "a", "b"), pattern="debate")
    assert validate_plan_structure(p) == []


def test_debate_plan_needs_two_proposers_and_one_referee() -> None:
    assert (Codes.PLAN_INVALID, None) in codes(
        validate_plan_structure(plan(proposer("a"), referee("r", "a"), pattern="debate"))
    )
    no_referee = codes(
        validate_plan_structure(plan(proposer("a"), proposer("b"), pattern="debate"))
    )
    assert (Codes.PLAN_INVALID, None) in no_referee


def test_debate_referee_must_depend_on_and_read_every_proposer() -> None:
    missing_dep = plan(proposer("a"), proposer("b"), referee("r", "a"), pattern="debate")
    assert codes(validate_plan_structure(missing_dep)) == [
        (Codes.PLAN_INVALID, "r"),
        (Codes.PLAN_INVALID, "r"),
    ]  # depends_on and inputs
    no_input = plan(
        proposer("a"),
        proposer("b"),
        replace(referee("r", "a", "b"), inputs=["a"]),
        pattern="debate",
    )
    assert codes(validate_plan_structure(no_input)) == [(Codes.PLAN_INVALID, "r")]


def test_debate_proposers_must_span_two_providers() -> None:
    """The cross-domain boundary (cycle 3.1): a debate with every proposer on one
    provider is that specialist's internal disagreement — it is refused at
    structure-check time, never replayed as plan nodes."""
    same = plan(
        proposer("a", "demo"), proposer("b", "demo"), referee("r", "a", "b"), pattern="debate"
    )
    violations = validate_plan_structure(same)
    assert (Codes.PLAN_INVALID, None) in codes(violations)
    assert any("cross-domain boundary" in v.detail for v in violations)
    # Mixed slates stay valid: three proposers across two providers.
    mixed = plan(
        proposer("a", "demo"),
        proposer("b", "demo"),
        proposer("c", "other"),
        referee("r", "a", "b", "c"),
        pattern="debate",
    )
    assert validate_plan_structure(mixed) == []


def test_debate_rejects_other_roles_and_dependent_proposers() -> None:
    odd = plan(proposer("a"), proposer("b"), pnode("x"), referee("r", "a", "b"), pattern="debate")
    assert codes(validate_plan_structure(odd)) == [(Codes.PLAN_INVALID, "x")]
    dependent = plan(
        proposer("a"),
        replace(proposer("b"), depends_on=[dep("a")]),
        referee("r", "a", "b"),
        pattern="debate",
    )
    assert (Codes.PLAN_INVALID, "b") in codes(validate_plan_structure(dependent))


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
    nodes = [
        pnode("a", "b"),
        pnode("b", "a"),
        pnode("a"),
        pnode("Bad"),
        pnode("c", "ghost"),
        pnode("d", inputs=["a"]),
    ]
    nodes += [pnode(f"x{i}") for i in range(MAX_PLAN_NODES)]
    found = codes(validate_plan_structure(plan(*nodes, pattern="scatter")))
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
    origin = HandoffOrigin(
        plan_run="p1", node="a", run_id="r1", provider=Producer(id="spark", version="2.0")
    )
    return HandoffItem(
        kind="evidence",
        id=f"e{i}",
        origin=origin,
        epistemic="observed",
        subject=subject,
        claim=claim,
    )


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
    nodes = [
        GraphNode(id="workspace:.", kind="workspace"),
        GraphNode(id="repository:api", kind="repository"),
    ]
    return WorkspaceGraph(producer=P, created_at=TS, plan_run="p1", nodes=nodes, edges=edges)


def edge(source: str, target: str) -> GraphEdge:
    return GraphEdge(
        source=source, target=target, kind="contains", epistemic="observed", evidence="api/.git"
    )


def test_graph_with_existing_endpoints() -> None:
    validate_graph(graph([edge("workspace:.", "repository:api")]))
    assert (
        check_graph_edge(edge("workspace:.", "repository:api"), {"workspace:.", "repository:api"})
        is None
    )


@pytest.mark.parametrize(
    ("source", "target"),
    [
        ("workspace:.", "repository:ghost"),
        ("repository:ghost", "workspace:."),
    ],
)
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
    return PlanResult(
        producer=P,
        created_at=TS,
        status=status,
        plan_run="p1",
        order=[n.node for n in nodes] if order is None else order,
        nodes=nodes,
        synthesis=Synthesis(nodes=[]),
        reproducibility=ReproducibilityInfo(level="unknown"),
    )


def result_codes(result: PlanResult) -> list[tuple[str, str | None]]:
    with pytest.raises(IntegrityError) as err:
        validate_plan_result(result)
    return [(v.code, v.field) for v in err.value.violations]


def test_valid_plan_results() -> None:
    validate_plan_result(presult("ok", [outcome("a"), outcome("b")]))
    validate_plan_result(
        presult(
            "partial",
            [
                outcome("a", "provider_failure"),
                outcome("b", "skipped", blocked_by="a"),
                outcome("c", "partial"),
            ],
        )
    )
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
    unknown = presult(
        "partial", [outcome("a", "partial"), outcome("b", "skipped", blocked_by="ghost")]
    )
    assert result_codes(unknown) == [(Codes.PLAN_INVALID, "nodes[1].blocked_by")]
    itself = presult("partial", [outcome("a", "partial"), outcome("b", "skipped", blocked_by="b")])
    assert result_codes(itself) == [(Codes.PLAN_INVALID, "nodes[1].blocked_by")]


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


# --- topological order and blocking (task 2.2) ------------------------------------------


def test_topological_order_breaks_ties_by_id() -> None:
    # Declaration order is irrelevant: ready nodes are taken by id.
    p = plan(pnode("d", "b", "c"), pnode("c", "a"), pnode("b", "a"), pnode("a"), pnode("e"))
    assert topological_order(p) == ["a", "b", "c", "d", "e"]


def test_topological_order_releases_newly_ready_nodes_by_id() -> None:
    # "z" is ready from the start but "b" (released by "a") sorts before it.
    p = plan(pnode("z"), pnode("b", "a"), pnode("a"))
    assert topological_order(p) == ["a", "b", "z"]


def test_topological_order_is_independent_of_declaration_order() -> None:
    nodes = [pnode("a"), pnode("b", "a"), pnode("c", "a"), pnode("d", "c", "b"), pnode("x")]
    expected = topological_order(plan(*nodes))
    assert expected == ["a", "b", "c", "d", "x"]
    for perm in itertools.permutations(nodes):
        assert topological_order(plan(*perm)) == expected


def test_topological_order_rejects_a_cycle() -> None:
    with pytest.raises(ValueError, match="cycle"):
        topological_order(plan(pnode("a", "b"), pnode("b", "a")))


def test_blocked_by_none_when_ancestors_succeeded() -> None:
    p = plan(pnode("a"), pnode("b", "a"))
    assert blocked_by("b", p, {}) is None
    assert blocked_by("a", p, {"b": "refused"}) is None  # descendants never block


def test_blocked_by_is_transitive_and_takes_the_first_ancestor_in_order() -> None:
    p = plan(pnode("a"), pnode("b", "a"), pnode("c", "b"), pnode("x"), pnode("y", "x", "c"))
    assert blocked_by("c", p, {"a": "refused"}) == "a"
    assert blocked_by("y", p, {"a": "refused"}) == "a"
    # Two failed ancestors: the first one in topological order.
    assert blocked_by("y", p, {"x": "provider_failure", "b": "refused"}) == "b"
    assert blocked_by("x", p, {"a": "refused"}) is None


# --- check_plan: structure + registry + profile (task 2.2) -------------------------------


def cap(
    cid: str,
    actions: tuple[str, ...] = ("run",),
    state: Any = "supported",
    aliases: tuple[str, ...] = (),
    deprecated: bool = False,
    replaced_by: str | None = None,
) -> Capability:
    return Capability(
        id=cid,
        actions=list(actions),
        default_action=actions[0],
        state=state,
        operation_class="read_only",
        aliases=list(aliases),
        deprecated=deprecated,
        replaced_by=replaced_by,
    )


def rec(pid: str, *caps: Capability, state: Any = "ready") -> RegistryRecord:
    manifest = ForgeManifest(
        id=pid,
        version="1",
        protocols=["forge/v1"],
        ops=["describe", "health", "execute"],
        capabilities=list(caps),
    )
    return RegistryRecord(
        entry=ProviderEntry(id=pid, argv=["x"], trust="local"),
        state=state,
        manifest=manifest if state == "ready" else None,
        manifest_sha256="0" * 64,
        protocol="forge/v1",
    )


RECORDS = {
    "spark": rec(
        "spark", cap("pyspark.static-analysis", ("analyze", "lint"), aliases=("spark.lint",))
    ),
    "api": rec(
        "api",
        cap("api.analyze", ("analyze",)),
        cap("api.old", ("analyze",), deprecated=True, replaced_by="api.analyze"),
        cap("api.none", ("analyze",), state="unsupported"),
    ),
    "down": rec("down", state="unreachable"),
}


def rnode(
    nid: str, provider: str, capability: str, action: str = "analyze", *deps: str
) -> PlanNode:
    return PlanNode(
        id=nid,
        role="standalone",
        provider=provider,
        capability=capability,
        action=action,
        depends_on=[dep(d) for d in deps],
        inputs=list(deps),
    )


def test_check_plan_accepts_a_valid_plan() -> None:
    p = plan(
        rnode("spark", "spark", "pyspark.static-analysis"),
        rnode("api", "api", "api.analyze", "analyze", "spark"),
    )
    assert check_plan(p, RECORDS, profile_for("max")) == []


def test_check_plan_reports_each_registry_violation() -> None:
    p = plan(
        rnode("a", "ghost", "x.y"),
        rnode("b", "down", "x.y"),
        rnode("c", "api", "api.missing"),
        rnode("d", "api", "api.none"),
        rnode("e", "spark", "pyspark.static-analysis", "deploy"),
    )
    got = check_plan(p, RECORDS, profile_for("max"))
    assert codes(got) == [(Codes.PLAN_CAPABILITY, n) for n in "abcde"]
    details = [v.detail for v in got]
    assert "'ghost' is not registered" in details[0]
    assert "'down' is not ready (unreachable)" in details[1]
    assert "does not declare capability 'api.missing'" in details[2]
    assert "'api.none'" in details[3] and "unsupported" in details[3]
    assert "action 'deploy'" in details[4]


def test_check_plan_accepts_an_alias_capability() -> None:
    p = plan(rnode("a", "spark", "spark.lint", "lint"))
    assert check_plan(p, RECORDS, profile_for("max")) == []


def test_check_plan_limits_distinct_providers_by_profile() -> None:
    p = plan(
        rnode("a", "spark", "pyspark.static-analysis"),
        rnode("b", "api", "api.analyze", "analyze", "a"),
    )
    assert codes(check_plan(p, RECORDS, profile_for("economy"))) == [(Codes.PLAN_LIMIT, None)]
    assert check_plan(p, RECORDS, profile_for("max")) == []
    same = plan(
        rnode("a", "spark", "pyspark.static-analysis"),
        rnode("b", "spark", "pyspark.static-analysis", "lint", "a"),
    )
    assert check_plan(same, RECORDS, profile_for("economy")) == []


def test_check_plan_adds_registry_violations_to_structural_ones() -> None:
    p = plan(
        rnode("a", "ghost", "x.y", "analyze", "missing"),
        rnode("b", "api", "api.analyze"),
        rnode("c", "spark", "pyspark.static-analysis"),
        pattern="scatter",
    )
    assert codes(check_plan(p, RECORDS, profile_for("balanced"))) == [
        (Codes.PLAN_PATTERN_RESERVED, None),
        (Codes.PLAN_INVALID, "a"),
        (Codes.PLAN_CAPABILITY, "a"),
        (Codes.PLAN_LIMIT, None),
    ]


def test_checked_plan_sets_status_from_violations() -> None:
    good = checked_plan(plan(rnode("a", "api", "api.analyze")), RECORDS, profile_for("max"))
    assert (good.status, good.violations) == ("validated", [])
    bad = checked_plan(plan(rnode("a", "ghost", "x.y")), RECORDS, profile_for("max"))
    assert bad.status == "rejected"
    assert codes(bad.violations) == [(Codes.PLAN_CAPABILITY, "a")]


# --- load_plan_file (task 2.2) -----------------------------------------------------------


def plan_doc(**overrides: Any) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "schema": "theforge/ExecutionPlan/v1",
        "task_id": "t-file",
        "pattern": "pipeline",
        "source": "decomposed",
        "profile": "max",
        "nodes": [
            {
                "id": "spark",
                "role": "producer",
                "provider": "spark",
                "capability": "spark.lint",
                "action": "lint",
            },
            {
                "id": "api",
                "role": "consumer",
                "provider": "api",
                "capability": "api.old",
                "action": "analyze",
                "inputs": ["spark"],
                "depends_on": [{"node": "spark", "epistemic": "explicit", "evidence": "plan file"}],
            },
        ],
    }
    doc.update(overrides)
    return doc


def write_plan(tmp_path: Path, doc: Any) -> Path:
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def load(path: Path, profile: Any = "max") -> ExecutionPlan:
    return load_plan_file(path, RECORDS, plan_run="run-1", profile=profile, created_at=TS)


def test_load_plan_file_overrides_run_controlled_fields(tmp_path: Path) -> None:
    forged = plan_doc(
        plan_run="evil",
        producer={"id": "evil", "version": "9"},
        created_at="1999-01-01T00:00:00Z",
        status="rejected",
        violations=[{"code": Codes.PLAN_INVALID, "node": None, "detail": "x"}],
    )
    p = load(write_plan(tmp_path, forged))
    assert (p.plan_run, p.producer, p.created_at) == ("run-1", PRODUCER, TS)
    assert (p.status, p.violations, p.source) == ("validated", [], "file")
    assert p.task_id == "t-file"
    bare = {k: v for k, v in plan_doc().items() if k != "source"}
    assert load(write_plan(tmp_path, bare)).source == "file"


def test_load_plan_file_resolves_aliases_with_the_wave_b_notes(tmp_path: Path) -> None:
    p = load(write_plan(tmp_path, plan_doc()))
    spark, api = p.nodes
    assert spark.capability == "pyspark.static-analysis"
    assert spark.limitations == [
        "capability-alias: 'spark.lint' resolved to 'pyspark.static-analysis' (spark)"
    ]
    assert api.capability == "api.old"
    assert api.limitations == [
        "capability-deprecated: 'api.old' (api) is deprecated; replaced_by 'api.analyze'"
    ]
    assert check_plan(p, RECORDS, profile_for("max")) == []


def test_load_plan_file_keeps_unknowns_for_check_plan(tmp_path: Path) -> None:
    doc = plan_doc(
        nodes=[
            {
                "id": "a",
                "role": "standalone",
                "provider": "ghost",
                "capability": "x.y",
                "action": "run",
            },
            {
                "id": "b",
                "role": "standalone",
                "provider": "api",
                "capability": "api.nope",
                "action": "run",
            },
        ]
    )
    p = load(write_plan(tmp_path, doc))
    assert [(n.provider, n.capability, n.limitations) for n in p.nodes] == [
        ("ghost", "x.y", []),
        ("api", "api.nope", []),
    ]
    assert codes(check_plan(p, RECORDS, profile_for("max"))) == [
        (Codes.PLAN_CAPABILITY, "a"),
        (Codes.PLAN_CAPABILITY, "b"),
    ]


def test_load_plan_file_applies_the_command_line_profile(tmp_path: Path) -> None:
    p = load(write_plan(tmp_path, plan_doc(profile="max")), profile="economy")
    assert p.profile == "economy"
    assert p.limitations == [
        "profile: plan file profile 'max' overridden by command line profile 'economy'"
    ]
    same = load(write_plan(tmp_path, plan_doc(profile="economy")), profile="economy")
    assert same.limitations == []


def test_file_and_generated_plans_get_the_same_validation(tmp_path: Path) -> None:
    loaded = load(write_plan(tmp_path, plan_doc()))
    generated = replace(
        plan(*loaded.nodes),
        source="decomposed",
        plan_run="run-1",
        producer=PRODUCER,
        task_id="t-file",
    )
    for name in ("economy", "max"):
        profile = profile_for(name)
        assert check_plan(loaded, RECORDS, profile) == check_plan(generated, RECORDS, profile)
    assert codes(check_plan(loaded, RECORDS, profile_for("economy"))) == [(Codes.PLAN_LIMIT, None)]


@pytest.mark.parametrize(
    "content",
    [
        "{not json",
        "[]",
        json.dumps(plan_doc(extra="field")),
        json.dumps(plan_doc(pattern="swarm")),
        json.dumps(
            plan_doc(
                nodes=[
                    {
                        "id": "a",
                        "role": "standalone",
                        "provider": "api",
                        "capability": "api.analyze",
                        "action": "analyze",
                        "depends_on": [{"node": "b", "epistemic": "inferred", "evidence": "x"}],
                    }
                ]
            )
        ),
        json.dumps({k: v for k, v in plan_doc().items() if k != "nodes"}),
        json.dumps(plan_doc(schema="theforge/ExecutionPlan/v2")),
    ],
    ids=[
        "not-json",
        "not-object",
        "unknown-field",
        "bad-pattern",
        "inferred-no-rule",
        "missing-nodes",
        "bad-schema",
    ],
)
def test_load_plan_file_off_contract_is_a_plan_usage_error(tmp_path: Path, content: str) -> None:
    path = tmp_path / "plan.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(UsageError) as info:
        load(path)
    assert info.value.code == Codes.PLAN_FILE


def test_load_plan_file_unreadable_or_too_large(tmp_path: Path) -> None:
    with pytest.raises(UsageError) as missing:
        load(tmp_path / "absent.json")
    assert missing.value.code == Codes.PLAN_FILE
    big = tmp_path / "big.json"
    big.write_bytes(b" " * (MAX_PLAN_FILE_BYTES + 1) + b"{}")
    with pytest.raises(UsageError, match="exceeds") as large:
        load(big)
    assert large.value.code == Codes.PLAN_FILE
