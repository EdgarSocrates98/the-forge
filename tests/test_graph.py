"""GraphBuilder (task 2.6): minimal workspace/provider/plan graph where every edge has evidence.

Requirements 8.1-8.6: nodes for workspace, repositories, providers, capabilities, plan
nodes, evidence and artifacts; every edge carries its evidence and epistemic status (an
inferred edge names its rule); an edge without evidence, with a missing endpoint or
inferred without a rule is dropped with a ``FORGE-WORKSPACE-GRAPH-EDGE`` limitation; the
same inputs yield the same JSON; the graph is a plain run artifact (no graph store).
"""

from dataclasses import replace
from typing import Any

from theforge.contracts.base import from_dict, to_dict
from theforge.contracts.canonical import canonical_json, sha256_of
from theforge.contracts.codes import Codes
from theforge.contracts.graph import GraphEdge, GraphNode, WorkspaceGraph
from theforge.contracts.handoff import Handoff, HandoffItem, HandoffOrigin
from theforge.contracts.integrity import validate_graph
from theforge.contracts.manifest import Capability, ForgeManifest
from theforge.contracts.plan import ExecutionPlan, NodeOutcome, PlanDependency, PlanNode
from theforge.contracts.result import Artifact, Evidence, ExecutionResult
from theforge.contracts.types import Producer
from theforge.contracts.workspace import RepositoryInfo, WorkspaceDescriptor, WorkspaceRelation
from theforge.meta import PRODUCER
from theforge.planning.execution import NodeExecution
from theforge.planning.graph import GraphBuilder, build_graph
from theforge.registry import ProviderEntry, RegistryRecord

PLAN_RUN = "plan-run-1"
CREATED = "2026-10-04T00:00:00.000000Z"
SPARK = Producer(id="fixture-spark", version="1.2.3")
API = Producer(id="fixture-api", version="0.9.0")
PLAN_SHA = "1" * 64
MANIFEST_SPARK = "2" * 64
MANIFEST_API = "3" * 64
RESULT_SPARK = "4" * 64
RESULT_API = "5" * 64
ART_HASH = "6" * 64
WS_TOML = ".forge/config/workspace.toml"
EDGE_CODE = Codes.WORKSPACE_GRAPH_EDGE


def descriptor(*, root_repo: bool = False) -> WorkspaceDescriptor:
    paths = [".", "orders-api", "data-pipeline"] if root_repo else ["data-pipeline", "orders-api"]
    return WorkspaceDescriptor(
        producer=PRODUCER,
        created_at=CREATED,
        root="/ws",
        repositories=[RepositoryInfo(path=p) for p in paths],
        relations=[
            WorkspaceRelation(
                source=".",
                target="data-pipeline",
                kind="contains",
                epistemic="observed",
                evidence="data-pipeline/.git",
            ),
            WorkspaceRelation(
                source=".",
                target="orders-api",
                kind="contains",
                epistemic="observed",
                evidence="orders-api/.git",
            ),
            WorkspaceRelation(
                source="orders-api",
                target="data-pipeline",
                kind="depends_on",
                epistemic="explicit",
                evidence=WS_TOML,
            ),
        ],
    )


def cap(cid: str) -> Capability:
    return Capability(
        id=cid,
        actions=["analyze"],
        default_action="analyze",
        state="stable",
        operation_class="read_only",
    )


def rec(pid: str, sha: str | None, *caps: str) -> RegistryRecord:
    manifest = ForgeManifest(
        id=pid,
        version="1",
        protocols=["forge/v1"],
        ops=["describe", "health", "execute"],
        capabilities=[cap(c) for c in caps],
    )
    return RegistryRecord(
        entry=ProviderEntry(id=pid, argv=["x"], trust="local"),
        state="ready",
        manifest=manifest,
        manifest_sha256=sha,
        protocol="forge/v1",
    )


def records() -> list[RegistryRecord]:
    return [
        rec("fixture-spark", MANIFEST_SPARK, "pyspark.static-analysis"),
        rec("fixture-api", MANIFEST_API, "api.analyze"),
    ]


def dep(node: str, *, inferred: bool = False) -> PlanDependency:
    if inferred:
        return PlanDependency(
            node=node,
            epistemic="inferred",
            rule="intent-order",
            evidence="keyword 'spark'@3 < keyword 'api'@9",
        )
    return PlanDependency(node=node, epistemic="explicit", evidence="plan file")


def nodes(*, inferred: bool = False) -> list[PlanNode]:
    return [
        PlanNode(
            id="spark",
            role="producer",
            provider="fixture-spark",
            capability="pyspark.static-analysis",
            action="analyze",
            targets=["data-pipeline"],
        ),
        PlanNode(
            id="api",
            role="consumer",
            provider="fixture-api",
            capability="api.analyze",
            action="analyze",
            targets=["orders-api/src", "orders-api"],
            depends_on=[dep("spark", inferred=inferred)],
            inputs=["spark"],
        ),
    ]


def plan(*, inferred: bool = False, plan_nodes: list[PlanNode] | None = None) -> ExecutionPlan:
    return ExecutionPlan(
        producer=PRODUCER,
        created_at=CREATED,
        status="validated",
        plan_run=PLAN_RUN,
        task_id="t1",
        pattern="pipeline",
        source="decomposed" if inferred else "file",
        profile="max",
        nodes=plan_nodes if plan_nodes is not None else nodes(inferred=inferred),
    )


def ev(eid: str, producer: Producer = SPARK) -> Evidence:
    return Evidence(id=eid, epistemic="observed", subject=f"s-{eid}", claim="c", producer=producer)


def spark_result() -> ExecutionResult:
    return ExecutionResult(
        producer=SPARK,
        created_at=CREATED,
        status="ok",
        evidence=[ev("e2"), ev("e1")],
        artifacts=[Artifact(path="report.json", sha256=ART_HASH)],
    )


def api_result() -> ExecutionResult:
    return ExecutionResult(producer=API, created_at=CREATED, status="ok", evidence=[ev("a1", API)])


def handoff() -> Handoff:
    origin = HandoffOrigin(plan_run=PLAN_RUN, node="spark", run_id="run-spark", provider=SPARK)
    return Handoff(
        producer=PRODUCER,
        created_at=CREATED,
        plan_run=PLAN_RUN,
        target_node="api",
        items=[
            HandoffItem(
                kind="decision",
                id="outcome",
                origin=origin,
                epistemic="observed",
                subject="spark",
                claim="status=ok",
            ),
            HandoffItem(
                kind="evidence",
                id="e1",
                origin=origin,
                epistemic="observed",
                subject="s-e1",
                claim="c",
            ),
            HandoffItem(
                kind="evidence",
                id="e2",
                origin=origin,
                epistemic="observed",
                subject="s-e2",
                claim="c",
            ),
            HandoffItem(kind="artifact", id="report.json", origin=origin, hash=ART_HASH),
        ],
    )


def executions(
    the_plan: ExecutionPlan, *, spark_sha: str | None = RESULT_SPARK, hoff: Handoff | None = None
) -> list[NodeExecution]:
    by_id = {n.id: n for n in the_plan.nodes}
    return [
        NodeExecution(
            node=by_id["spark"],
            outcome=NodeOutcome(
                node="spark", status="ok", run_id="run-spark", result_sha256=spark_sha
            ),
            result=spark_result(),
            handoff=None,
            provider=SPARK,
        ),
        NodeExecution(
            node=by_id["api"],
            outcome=NodeOutcome(
                node="api", status="ok", run_id="run-api", result_sha256=RESULT_API
            ),
            result=api_result(),
            handoff=hoff or handoff(),
            provider=API,
        ),
    ]


def graph(**kw: Any) -> WorkspaceGraph:
    the_plan = kw.pop("the_plan", None) or plan()
    return build_graph(
        PLAN_RUN,
        kw.pop("desc", None) or descriptor(),
        kw.pop("recs", None) or records(),
        the_plan,
        PLAN_SHA,
        kw.pop("execs", None) or executions(the_plan),
        created_at=CREATED,
    )


def edge_set(g: WorkspaceGraph) -> set[tuple[str, str, str, str, str, str | None]]:
    return {(e.source, e.kind, e.target, e.epistemic, e.evidence, e.rule) for e in g.edges}


def edge_codes(g: WorkspaceGraph) -> list[str]:
    return [lim for lim in g.limitations if lim.startswith(EDGE_CODE)]


# --- 8.1 / 8.2: nodes and edges of an executed plan ------------------------------------------


def test_nodes_cover_every_kind_of_an_executed_plan() -> None:
    g = graph()
    assert {n.id for n in g.nodes} == {
        "workspace:.",
        "repository:data-pipeline",
        "repository:orders-api",
        "provider:fixture-api",
        "provider:fixture-spark",
        "capability:fixture-api/api.analyze",
        "capability:fixture-spark/pyspark.static-analysis",
        "plan_node:api",
        "plan_node:spark",
        "evidence:api/a1",
        "evidence:spark/e1",
        "evidence:spark/e2",
        "artifact:spark/report.json",
    }
    assert {n.id: n.kind for n in g.nodes}["artifact:spark/report.json"] == "artifact"
    assert g.plan_run == PLAN_RUN and g.producer == PRODUCER and not g.truncated


def test_expected_edges_with_evidence_of_an_executed_plan() -> None:
    plan_ev, man_s, man_a = (
        f"plan:{PLAN_SHA}",
        f"manifest:{MANIFEST_SPARK}",
        f"manifest:{MANIFEST_API}",
    )
    res_s, res_a = f"result:{RESULT_SPARK}", f"result:{RESULT_API}"
    hoff = f"handoff:{sha256_of(to_dict(handoff()))}"
    assert edge_set(graph()) == {
        (
            "workspace:.",
            "contains",
            "repository:data-pipeline",
            "observed",
            "data-pipeline/.git",
            None,
        ),
        ("workspace:.", "contains", "repository:orders-api", "observed", "orders-api/.git", None),
        (
            "repository:orders-api",
            "depends_on",
            "repository:data-pipeline",
            "explicit",
            WS_TOML,
            None,
        ),
        (
            "provider:fixture-spark",
            "declares",
            "capability:fixture-spark/pyspark.static-analysis",
            "explicit",
            man_s,
            None,
        ),
        (
            "provider:fixture-api",
            "declares",
            "capability:fixture-api/api.analyze",
            "explicit",
            man_a,
            None,
        ),
        (
            "plan_node:spark",
            "uses",
            "capability:fixture-spark/pyspark.static-analysis",
            "explicit",
            plan_ev,
            None,
        ),
        ("plan_node:api", "uses", "capability:fixture-api/api.analyze", "explicit", plan_ev, None),
        ("plan_node:spark", "targets", "repository:data-pipeline", "explicit", plan_ev, None),
        ("plan_node:api", "targets", "repository:orders-api", "explicit", plan_ev, None),
        ("plan_node:api", "depends_on", "plan_node:spark", "explicit", plan_ev, None),
        ("plan_node:spark", "produced", "evidence:spark/e1", "observed", res_s, None),
        ("plan_node:spark", "produced", "evidence:spark/e2", "observed", res_s, None),
        ("plan_node:spark", "produced", "artifact:spark/report.json", "observed", res_s, None),
        ("plan_node:api", "produced", "evidence:api/a1", "observed", res_a, None),
        ("evidence:spark/e1", "handed_off_to", "plan_node:api", "observed", hoff, None),
        ("evidence:spark/e2", "handed_off_to", "plan_node:api", "observed", hoff, None),
    }
    assert edge_codes(graph()) == []
    validate_graph(graph())


def test_root_repository_is_contained_by_the_workspace() -> None:
    g = graph(desc=descriptor(root_repo=True))
    edges = edge_set(g)
    assert ("workspace:.", "contains", "repository:.", "observed", "./.git", None) in edges
    assert (
        "repository:.",
        "contains",
        "repository:orders-api",
        "observed",
        "orders-api/.git",
        None,
    ) in edges
    validate_graph(g)


def test_target_outside_any_repository_points_to_the_workspace() -> None:
    the_plan = plan(plan_nodes=[replace(nodes()[0], targets=["."]), nodes()[1]])
    g = graph(the_plan=the_plan)
    assert (
        "plan_node:spark",
        "targets",
        "workspace:.",
        "explicit",
        f"plan:{PLAN_SHA}",
        None,
    ) in edge_set(g)


# --- 8.3: inferred dependency carries its rule ---------------------------------------------


def test_decomposed_plan_dependency_is_inferred_with_rule() -> None:
    the_plan = plan(inferred=True)
    g = graph(the_plan=the_plan)
    deps = [e for e in g.edges if e.kind == "depends_on" and e.source.startswith("plan_node:")]
    assert [(e.epistemic, e.rule, e.evidence) for e in deps] == [
        ("inferred", "intent-order", f"plan:{PLAN_SHA}")
    ]


# --- 8.4: invalid edges are dropped with a limitation --------------------------------------


def test_builder_rejects_edge_with_missing_endpoint() -> None:
    b = GraphBuilder(PLAN_RUN)
    b.add_node(GraphNode(id="plan_node:a", kind="plan_node"))
    ok = b.add_edge(
        GraphEdge(
            source="plan_node:a",
            target="repository:ghost",
            kind="targets",
            epistemic="explicit",
            evidence="plan:x",
        )
    )
    g = b.build(created_at=CREATED)
    assert ok is False and g.edges == []
    assert len(edge_codes(g)) == 1 and "repository:ghost" in g.limitations[0]


def test_builder_proposals_without_evidence_or_rule_are_dropped() -> None:
    b = GraphBuilder(PLAN_RUN)
    for nid in ("plan_node:a", "plan_node:b"):
        b.add_node(GraphNode(id=nid, kind="plan_node"))
    assert (
        b.propose(
            source="plan_node:a",
            target="plan_node:b",
            kind="depends_on",
            epistemic="explicit",
            evidence="  ",
        )
        is False
    )
    assert (
        b.propose(
            source="plan_node:a",
            target="plan_node:b",
            kind="depends_on",
            epistemic="inferred",
            evidence="plan:x",
        )
        is False
    )
    assert (
        b.propose(
            source="plan_node:a",
            target="plan_node:b",
            kind="depends_on",
            epistemic="inferred",
            evidence="plan:x",
            rule="intent-order",
        )
        is True
    )
    g = b.build(created_at=CREATED)
    assert len(g.edges) == 1 and len(edge_codes(g)) == 2
    assert all(lim.startswith(f"{EDGE_CODE}: ") for lim in g.limitations)


def test_result_without_hash_drops_produced_edges_with_limitation() -> None:
    the_plan = plan()
    g = graph(the_plan=the_plan, execs=executions(the_plan, spark_sha=None))
    produced = [e for e in g.edges if e.kind == "produced"]
    assert [e.source for e in produced] == ["plan_node:api"]
    assert len(edge_codes(g)) == 3  # e1, e2, report.json
    validate_graph(g)


def test_unknown_capability_and_missing_manifest_hash_are_dropped() -> None:
    recs = [rec("fixture-spark", None, "pyspark.static-analysis")]  # api provider absent
    g = graph(recs=recs)
    edges = edge_set(g)
    assert not any(e[1] == "declares" for e in edges)
    assert not any(e[0] == "plan_node:api" and e[1] == "uses" for e in edges)
    assert (
        "plan_node:spark",
        "uses",
        "capability:fixture-spark/pyspark.static-analysis",
        "explicit",
        f"plan:{PLAN_SHA}",
        None,
    ) in edges
    lims = edge_codes(g)
    assert any("capability:fixture-api/api.analyze" in lim for lim in lims)
    assert any("declares" in lim for lim in lims)
    validate_graph(g)


def test_handoff_item_of_unknown_evidence_is_dropped() -> None:
    hoff = handoff()
    origin = hoff.items[0].origin
    hoff = replace(
        hoff,
        items=[
            *hoff.items,
            HandoffItem(kind="evidence", id="ghost", origin=origin, epistemic="observed"),
        ],
    )
    the_plan = plan()
    g = graph(the_plan=the_plan, execs=executions(the_plan, hoff=hoff))
    assert any("evidence:spark/ghost" in lim for lim in edge_codes(g))
    validate_graph(g)


# --- 8.5: determinism -----------------------------------------------------------------------


def test_same_inputs_produce_the_same_json_in_any_input_order() -> None:
    the_plan = plan()
    first = graph(the_plan=the_plan)
    shuffled_plan = replace(the_plan, nodes=list(reversed(the_plan.nodes)))
    desc = descriptor()
    second = graph(
        the_plan=shuffled_plan,
        desc=replace(
            desc,
            relations=list(reversed(desc.relations)),
            repositories=list(reversed(desc.repositories)),
        ),
        recs=list(reversed(records())),
        execs=list(reversed(executions(shuffled_plan))),
    )
    assert canonical_json(to_dict(first)) == canonical_json(to_dict(second))
    assert [n.id for n in first.nodes] == sorted(n.id for n in first.nodes)
    keys = [(e.source, e.kind, e.target) for e in first.edges]
    assert keys == sorted(keys)


def test_graph_round_trips_strictly() -> None:
    g = graph()
    assert from_dict(WorkspaceGraph, to_dict(g), strict=True) == g


def test_duplicate_nodes_and_edges_are_kept_once() -> None:
    b = GraphBuilder(PLAN_RUN)
    for _ in range(2):
        b.add_node(GraphNode(id="plan_node:a", kind="plan_node"))
        b.add_node(GraphNode(id="plan_node:b", kind="plan_node"))
        b.propose(
            source="plan_node:a",
            target="plan_node:b",
            kind="depends_on",
            epistemic="explicit",
            evidence="plan:x",
        )
    g = b.build(created_at=CREATED)
    assert len(g.nodes) == 2 and len(g.edges) == 1


# --- node limit -----------------------------------------------------------------------------


def test_evidence_and_artifacts_are_truncated_above_the_node_limit() -> None:
    the_plan = plan()
    execs = executions(the_plan)
    full = graph(the_plan=the_plan, execs=execs)
    structural = sum(1 for n in full.nodes if n.kind not in ("evidence", "artifact"))
    limit = structural + 2
    g = build_graph(
        PLAN_RUN,
        descriptor(),
        records(),
        the_plan,
        PLAN_SHA,
        execs,
        created_at=CREATED,
        max_nodes=limit,
    )
    kept = [n.id for n in g.nodes if n.kind in ("evidence", "artifact")]
    assert g.truncated and len(g.nodes) == limit
    assert kept == ["artifact:spark/report.json", "evidence:api/a1"]  # first in id order
    assert any(lim.startswith("graph-truncated:") for lim in g.limitations)
    assert edge_codes(g) == []  # edges of cut nodes are not rejections
    validate_graph(g)


# --- 8.6: plain artifact, no store ----------------------------------------------------------


def test_build_graph_is_pure(tmp_path: Any, monkeypatch: Any) -> None:
    monkeypatch.chdir(tmp_path)
    graph()
    assert list(tmp_path.iterdir()) == []
