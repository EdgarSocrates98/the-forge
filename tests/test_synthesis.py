"""Synthesizer (task 2.5): deterministic plan synthesis.

Requirements 5.1-5.4: per-node listing (provider, capability, action, status, run,
findings with original ids, evidence count by epistemic status), handoffs between
nodes with count and truncation, failed/not-executed nodes with reason, aggregated
limitations and unknowns prefixed by node; deterministic, no epistemic upgrade, no
finding created.
"""

import copy

import pytest

from theforge.contracts.base import from_dict, to_dict
from theforge.contracts.canonical import canonical_json
from theforge.contracts.handoff import Handoff, HandoffItem, HandoffOrigin
from theforge.contracts.plan import (
    ExecutionPlan,
    NodeOutcome,
    PlanDependency,
    PlanNode,
    Synthesis,
)
from theforge.contracts.result import Evidence, ExecutionResult, Finding
from theforge.contracts.types import ErrorInfo, Producer
from theforge.meta import PRODUCER
from theforge.planning.execution import NodeExecution
from theforge.planning.synthesis import synthesize

PLAN_RUN = "plan-run-1"
CREATED = "2026-10-04T00:00:00.000000Z"
SPARK = Producer(id="fixture-spark", version="1.2.3")
API = Producer(id="fixture-api", version="0.9.0")


def ev(eid: str, epistemic: str, producer: Producer = SPARK) -> Evidence:
    return Evidence(
        id=eid,
        epistemic=epistemic,
        subject=f"s-{eid}",  # type: ignore[arg-type]
        claim=f"claim {eid}",
        producer=producer,
    )


def node(
    nid: str,
    provider: str,
    capability: str,
    *,
    inputs: list[str] | None = None,
    limitations: list[str] | None = None,
) -> PlanNode:
    deps = [
        PlanDependency(node=i, epistemic="inferred", rule="intent-order", evidence="e")
        for i in inputs or []
    ]
    return PlanNode(
        id=nid,
        role="producer" if not inputs else "consumer",
        provider=provider,
        capability=capability,
        action="analyze",
        depends_on=deps,
        inputs=list(inputs or []),
        limitations=list(limitations or []),
    )


def spark_result() -> ExecutionResult:
    return ExecutionResult(
        producer=SPARK,
        created_at=CREATED,
        status="ok",
        findings=[
            Finding(id="SPARKFORGE-F2", title="shuffle", severity="high", evidence_ids=["e1"]),
            Finding(id="SPARKFORGE-F1", title="collect", evidence_ids=["e2"]),
        ],
        evidence=[
            ev("e1", "confirmed"),
            ev("e2", "observed"),
            ev("e3", "observed"),
            ev("e4", "inferred"),
        ],
        limitations=["static only"],
        unknowns=["cluster size"],
    )


def api_result() -> ExecutionResult:
    return ExecutionResult(
        producer=API,
        created_at=CREATED,
        status="partial",
        findings=[Finding(id="AF-1", title="no auth", severity="medium", evidence_ids=["a1"])],
        evidence=[ev("a1", "proposed", API), ev("a2", "unresolved", API)],
        limitations=["openapi only"],
        unknowns=[],
    )


def handoff_for(
    target: str,
    sources: dict[str, int],
    *,
    truncated: bool = False,
    limitations: list[str] | None = None,
) -> Handoff:
    items: list[HandoffItem] = []
    for src, count in sources.items():
        origin = HandoffOrigin(plan_run=PLAN_RUN, node=src, run_id=f"run-{src}", provider=SPARK)
        items.append(
            HandoffItem(kind="decision", id="outcome", origin=origin, epistemic="observed")
        )
        items.extend(
            HandoffItem(kind="evidence", id=f"x{i}", origin=origin, epistemic="observed")
            for i in range(count - 1)
        )
    return Handoff(
        producer=PRODUCER,
        created_at=CREATED,
        plan_run=PLAN_RUN,
        target_node=target,
        items=items,
        truncated=truncated,
        dropped=3 if truncated else 0,
        limitations=list(limitations or []),
    )


def executed(
    n: PlanNode,
    res: ExecutionResult | None,
    status: str,
    *,
    provider: Producer | None = SPARK,
    handoff: Handoff | None = None,
    error: ErrorInfo | None = None,
    blocked: str | None = None,
) -> NodeExecution:
    run_id = None if status == "skipped" else f"run-{n.id}"
    outcome = NodeOutcome(
        node=n.id,
        status=status,
        run_id=run_id,  # type: ignore[arg-type]
        blocked_by=blocked,
        error=error,
    )
    return NodeExecution(
        node=n,
        outcome=outcome,
        result=res,
        handoff=handoff,
        provider=None if status == "skipped" else provider,
    )


def run(execs: list[NodeExecution]) -> Synthesis:
    """Synthesize ``execs`` against the plan made of their nodes (effective order)."""
    plan = ExecutionPlan(
        producer=PRODUCER,
        created_at=CREATED,
        status="validated",
        plan_run=PLAN_RUN,
        task_id="t1",
        pattern="pipeline",
        source="decomposed",
        profile="max",
        nodes=sorted({e.node.id: e.node for e in execs}.values(), key=lambda n: n.id),
    )
    return synthesize(plan, execs)


def two_node_ok() -> list[NodeExecution]:
    n1 = node(
        "spark",
        "fixture-spark",
        "pyspark.static-analysis",
        limitations=["capability alias 'spark.lint' -> 'pyspark.static-analysis'"],
    )
    n2 = node("api", "fixture-api", "api.analyze", inputs=["spark"])
    h = handoff_for(
        "api", {"spark": 4}, truncated=True, limitations=["handoff-truncated: dropped 3 items"]
    )
    return [
        executed(n1, spark_result(), "ok"),
        executed(n2, api_result(), "partial", provider=API, handoff=h),
    ]


def test_lists_each_node_with_findings_and_evidence_counts() -> None:
    syn = run(two_node_ok())
    assert [n.node for n in syn.nodes] == ["spark", "api"]
    s, a = syn.nodes
    assert (s.provider, s.capability, s.action, s.status, s.run_id) == (
        "fixture-spark",
        "pyspark.static-analysis",
        "analyze",
        "ok",
        "run-spark",
    )
    assert [f.id for f in s.findings] == ["SPARKFORGE-F2", "SPARKFORGE-F1"]
    assert s.evidence_by_epistemic == {"confirmed": 1, "inferred": 1, "observed": 2}
    assert (a.provider, a.status, a.run_id) == ("fixture-api", "partial", "run-api")
    assert a.evidence_by_epistemic == {"proposed": 1, "unresolved": 1}
    assert syn.failures == []


def test_records_handoffs_with_count_and_truncation() -> None:
    syn = run(two_node_ok())
    assert [(h.source, h.target, h.items, h.truncated) for h in syn.handoffs] == [
        ("spark", "api", 4, True)
    ]


def test_handoff_per_declared_input_including_missing_one() -> None:
    n1 = node("a", "p", "c.one")
    n2 = node("b", "p", "c.two")
    n3 = node("c", "p", "c.three", inputs=["a", "b"])
    h = handoff_for("c", {"a": 2}, limitations=["handoff-input-missing: b"])
    execs = [
        executed(n1, spark_result(), "ok"),
        executed(
            n2,
            None,
            "provider_failure",
            error=ErrorInfo(code="FORGE-PROVIDER-CRASH", detail="exit 3"),
        ),
        executed(n3, spark_result(), "ok", handoff=h),
    ]
    syn = run(execs)
    assert [(h.source, h.target, h.items, h.truncated) for h in syn.handoffs] == [
        ("a", "c", 2, False),
        ("b", "c", 0, False),
    ]
    assert "c: handoff-input-missing: b" in syn.limitations


def test_failures_list_node_and_reason() -> None:
    n1 = node("spark", "fixture-spark", "pyspark.static-analysis")
    n2 = node("api", "fixture-api", "api.analyze", inputs=["spark"])
    execs = [
        executed(
            n1,
            None,
            "provider_failure",
            error=ErrorInfo(code="FORGE-PROVIDER-CRASH", detail="exit 3"),
        ),
        executed(n2, None, "skipped", blocked="spark"),
    ]
    syn = run(execs)
    assert syn.failures == [
        "spark: provider_failure FORGE-PROVIDER-CRASH: exit 3",
        "api: skipped: blocked by spark",
    ]
    assert [n.status for n in syn.nodes] == ["provider_failure", "skipped"]
    assert syn.nodes[1].run_id is None and syn.nodes[1].findings == []
    assert syn.nodes[0].evidence_by_epistemic == {}
    assert syn.handoffs == []  # the skipped node received no handoff


def test_refused_without_error_and_ok_without_result_are_failures() -> None:
    n1 = node("one", "p", "c.one")
    n2 = node("two", "p", "c.two")
    syn = run([executed(n1, None, "refused"), executed(n2, None, "ok")])
    assert syn.failures == ["one: refused: no valid result", "two: ok: no valid result"]


def test_limitations_and_unknowns_are_aggregated_with_node_prefix() -> None:
    syn = run(two_node_ok())
    assert syn.limitations == [
        "spark: capability alias 'spark.lint' -> 'pyspark.static-analysis'",
        "spark: static only",
        "api: handoff-truncated: dropped 3 items",
        "api: openapi only",
    ]
    assert syn.unknowns == ["spark: cluster size"]


def test_duplicate_limitations_of_a_node_are_listed_once() -> None:
    n1 = node("one", "p", "c.one", limitations=["static only"])
    syn = run([executed(n1, spark_result(), "ok")])
    assert syn.limitations == ["one: static only"]


def test_same_executions_same_synthesis() -> None:
    first = canonical_json(to_dict(run(two_node_ok())))
    second = canonical_json(to_dict(run(two_node_ok())))
    assert first == second
    # strict reread of the contract
    syn = run(two_node_ok())
    assert from_dict(Synthesis, to_dict(syn), strict=True) == syn


def test_never_upgrades_epistemic_nor_creates_findings() -> None:
    execs = two_node_ok()
    syn = run(execs)
    for execution, sn in zip(execs, syn.nodes, strict=True):
        assert execution.result is not None
        expected: dict[str, int] = {}
        for e in execution.result.evidence:
            expected[e.epistemic] = expected.get(e.epistemic, 0) + 1
        assert sn.evidence_by_epistemic == expected
        assert [to_dict(f) for f in sn.findings] == [to_dict(f) for f in execution.result.findings]
    all_ids = {f.id for sn in syn.nodes for f in sn.findings}
    assert all_ids == {"SPARKFORGE-F1", "SPARKFORGE-F2", "AF-1"}


def test_does_not_mutate_inputs_and_copies_findings() -> None:
    execs = two_node_ok()
    before = [copy.deepcopy(to_dict(e.result)) for e in execs if e.result]
    syn = run(execs)
    syn.nodes[0].findings[0].evidence_ids.append("tampered")
    assert [to_dict(e.result) for e in execs if e.result] == before


def test_duplicate_node_is_a_caller_bug() -> None:
    execs = two_node_ok()
    with pytest.raises(ValueError, match="duplicate"):
        run([execs[0], execs[0]])


def test_executions_must_match_the_plan_nodes() -> None:
    execs = two_node_ok()
    plan = ExecutionPlan(
        producer=PRODUCER,
        created_at=CREATED,
        status="validated",
        plan_run=PLAN_RUN,
        task_id="t1",
        pattern="pipeline",
        source="decomposed",
        profile="max",
        nodes=[execs[0].node],
    )
    with pytest.raises(ValueError, match="not in the plan"):
        synthesize(plan, execs)
    with pytest.raises(ValueError, match="without execution"):
        synthesize(plan, [])
