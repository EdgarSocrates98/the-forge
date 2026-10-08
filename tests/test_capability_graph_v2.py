"""Cycle 5 wave C/D: capability graph v2 — artifact-aware relations
(``accepts``/``verifies``/``refines``), capability verification/specialization
(``verified_by``/``specializes``), standalone ``CapabilityRelation`` freshness,
and the intelligence nodes the workspace graph gained (execution, failure,
decision).
"""

from __future__ import annotations

from typing import Any

import pytest

from theforge.capability_graph import (
    accepted_types,
    artifact_verifiers,
    build_capability_graph,
    produces_consumes_order,
    relation_fresh,
    specializations,
    verified_by,
)
from theforge.contracts import (
    Capability,
    CapabilityRelation,
    CapabilityRelations,
    ContractError,
    ForgeManifest,
)
from theforge.contracts.canonical import utc_now
from theforge.contracts.graph import GraphNode
from theforge.contracts.plan import (
    DecisionOption,
    DecisionRecord,
    ExecutionPlan,
    NodeOutcome,
    PlanNode,
)
from theforge.contracts.workspace import (
    RepositoryInfo,
    WorkspaceDescriptor,
)
from theforge.meta import PRODUCER
from theforge.planning.execution import NodeExecution
from theforge.planning.graph import build_graph
from theforge.registry.config import ProviderEntry
from theforge.registry.registry import RegistryRecord


def _record(pid: str, manifest: ForgeManifest | None) -> RegistryRecord:
    return RegistryRecord(
        entry=ProviderEntry(id=pid, argv=["x"], trust="local"),
        state="ready" if manifest else "broken",
        manifest=manifest,
    )


def _manifest(pid: str, *caps: Capability) -> ForgeManifest:
    return ForgeManifest(
        id=pid,
        version="0.1",
        protocols=["forge/v1"],
        ops=["describe", "health", "execute"],
        capabilities=list(caps),
    )


def _cap(cid: str, **kw: Any) -> Capability:
    return Capability(
        id=cid,
        actions=["run"],
        default_action="run",
        state="supported",
        operation_class="read_only",
        **kw,
    )


class TestRelationContract:
    def test_artifact_relations_validate_ids(self) -> None:
        CapabilityRelations(accepts=["report.v1"], verifies=["finding.v1"], refines=["plan.v1"])
        for field in ("accepts", "verifies", "refines"):
            with pytest.raises(ContractError):
                CapabilityRelations(**{field: ["not an id"]})

    def test_capability_relations_validate_refs(self) -> None:
        CapabilityRelations(verified_by=["other/verifier.run"], specializes=["etl.run"])
        for field in ("verified_by", "specializes"):
            with pytest.raises(ContractError):
                CapabilityRelations(**{field: ["bad ref !!"]})

    def test_relation_requires_evidence_and_known_kind(self) -> None:
        with pytest.raises(ContractError):
            CapabilityRelation(
                producer=PRODUCER,
                created_at=utc_now(),
                source="a/x",
                relation="produces",
                target="report.v1",
                evidence=[],
            )
        with pytest.raises(ContractError):
            CapabilityRelation(
                producer=PRODUCER,
                created_at=utc_now(),
                source="a/x",
                relation="teleports",
                target="report.v1",
                evidence=["e"],
            )


class TestGraphBuilder:
    def test_artifact_relations_become_edges(self) -> None:
        m = _manifest(
            "forge-a",
            _cap(
                "etl.run",
                relations=CapabilityRelations(accepts=["source-spec.v1"], produces=["report.v1"]),
            ),
            _cap(
                "check.plan",
                relations=CapabilityRelations(verifies=["report.v1"], refines=["plan.v1"]),
            ),
        )
        graph = build_capability_graph([_record("forge-a", m)], run_id="r")
        by_kind = {(e.kind, e.target) for e in graph.edges}
        assert ("accepts", "artifact_type:source-spec.v1") in by_kind
        assert ("verifies", "artifact_type:report.v1") in by_kind
        assert ("refines", "artifact_type:plan.v1") in by_kind
        for e in graph.edges:
            if e.kind in ("accepts", "verifies", "refines"):
                assert e.epistemic == "explicit" and e.evidence

    def test_capability_relations_become_edges(self) -> None:
        m = _manifest(
            "forge-a",
            _cap(
                "etl.run",
                relations=CapabilityRelations(verified_by=["check.plan"], specializes=["base.run"]),
            ),
            _cap("check.plan"),
            _cap("base.run"),
        )
        graph = build_capability_graph([_record("forge-a", m)], run_id="r")
        edges = {(e.kind, e.source, e.target) for e in graph.edges}
        assert (
            "verified_by",
            "capability:forge-a/etl.run",
            "capability:forge-a/check.plan",
        ) in edges
        assert (
            "specializes",
            "capability:forge-a/etl.run",
            "capability:forge-a/base.run",
        ) in edges

    def test_queries(self) -> None:
        m = _manifest(
            "forge-a",
            _cap(
                "etl.run",
                relations=CapabilityRelations(
                    produces=["report.v1"],
                    accepts=["source-spec.v1"],
                    verified_by=["forge-a/check.plan"],
                ),
            ),
            _cap("check.plan", relations=CapabilityRelations(verifies=["report.v1"])),
            _cap("etl.fast", relations=CapabilityRelations(specializes=["etl.run"])),
        )
        graph = build_capability_graph([_record("forge-a", m)], run_id="r")
        assert artifact_verifiers(graph, "report.v1") == ["forge-a/check.plan"]
        # `verified_by` points at the verifier: check verifies etl.run's output.
        assert verified_by(graph, "forge-a/etl.run") == ["forge-a/check.plan"]
        assert specializations(graph, "etl.run") == ["forge-a/etl.fast"]
        assert accepted_types(graph, "forge-a/etl.run") == ["source-spec.v1"]


class TestOrdering:
    def test_consumer_acceptor_verifier_run_after_producer(self) -> None:
        m = _manifest(
            "forge-a",
            _cap("make.art", relations=CapabilityRelations(produces=["report.v1"])),
            _cap("use.art", relations=CapabilityRelations(consumes=["report.v1"])),
            _cap("acc.art", relations=CapabilityRelations(accepts=["report.v1"])),
            _cap("ver.art", relations=CapabilityRelations(verifies=["report.v1"])),
            _cap("ref.art", relations=CapabilityRelations(refines=["report.v1"])),
        )
        graph = build_capability_graph([_record("forge-a", m)], run_id="r")
        order, cyclic = produces_consumes_order(
            graph,
            [
                "forge-a/ver.art",
                "forge-a/use.art",
                "forge-a/acc.art",
                "forge-a/make.art",
                "forge-a/ref.art",
            ],
        )
        assert not cyclic
        assert order.index("forge-a/make.art") < order.index("forge-a/use.art")
        assert order.index("forge-a/make.art") < order.index("forge-a/acc.art")
        assert order.index("forge-a/make.art") < order.index("forge-a/ver.art")
        assert order.index("forge-a/make.art") < order.index("forge-a/ref.art")

    def test_verified_capability_runs_before_verifier(self) -> None:
        m = _manifest(
            "forge-a",
            _cap("work.art", relations=CapabilityRelations(verified_by=["check.plan"])),
            _cap("check.plan"),
        )
        graph = build_capability_graph([_record("forge-a", m)], run_id="r")
        order, cyclic = produces_consumes_order(graph, ["forge-a/check.plan", "forge-a/work.art"])
        assert not cyclic
        assert order.index("forge-a/work.art") < order.index("forge-a/check.plan")


class TestRelationFreshness:
    def _relation(self, surface: str | None) -> CapabilityRelation:
        return CapabilityRelation(
            producer=PRODUCER,
            created_at=utc_now(),
            source="a/x",
            relation="produces",
            target="report.v1",
            evidence=["manifest a/x"],
            surface=surface,
        )

    def test_unscoped_relation_is_always_fresh(self) -> None:
        assert relation_fresh(self._relation(None), None)
        assert relation_fresh(self._relation(None), "surface-x")

    def test_scoped_relation_stale_on_surface_change(self) -> None:
        rel = self._relation("surface-1")
        assert relation_fresh(rel, "surface-1")
        assert not relation_fresh(rel, "surface-2")
        # unknown current surface -> a scoped relation cannot be trusted
        assert not relation_fresh(rel, None)


class TestWorkspaceIntelligenceNodes:
    """Wave C: the run graph records executions, failures and decisions."""

    def _descriptor(self) -> WorkspaceDescriptor:
        return WorkspaceDescriptor(
            producer=PRODUCER,
            created_at=utc_now(),
            root=".",
            repositories=[RepositoryInfo(path=".")],
        )

    def _plan(self) -> ExecutionPlan:
        return ExecutionPlan(
            producer=PRODUCER,
            created_at=utc_now(),
            status="validated",
            plan_run="pr",
            task_id="t1",
            pattern="pipeline",
            source="decomposed",
            profile="max",
            nodes=[
                PlanNode(
                    id="a",
                    role="producer",
                    provider="p1",
                    capability="x.y",
                    action="run",
                    targets=["."],
                ),
                PlanNode(
                    id="b",
                    role="consumer",
                    provider="p1",
                    capability="y.z",
                    action="run",
                    targets=["."],
                ),
            ],
        )

    def _executions(self) -> list[NodeExecution]:
        plan = self._plan()
        by_id = {n.id: n for n in plan.nodes}
        return [
            NodeExecution(
                node=by_id["a"],
                outcome=NodeOutcome(node="a", status="ok", run_id="run-a"),
                result=None,
                handoff=None,
                provider=None,
            ),
            NodeExecution(
                node=by_id["b"],
                outcome=NodeOutcome(node="b", status="provider_failure", run_id="run-b"),
                result=None,
                handoff=None,
                provider=None,
            ),
        ]

    def test_execution_and_failure_nodes(self) -> None:
        graph = build_graph("pr", self._descriptor(), [], self._plan(), None, self._executions())
        kinds = {(n.kind, n.id) for n in graph.nodes}
        assert ("execution", "execution:a") in kinds
        assert ("execution", "execution:b") in kinds
        assert ("failure", "failure:b") in kinds
        edges = {(e.kind, e.source, e.target) for e in graph.edges}
        assert ("executed_by", "plan_node:a", "execution:a") in edges
        assert ("produced", "execution:b", "failure:b") in edges

    def test_decision_node_links_to_chosen(self) -> None:
        decision = DecisionRecord(
            producer=PRODUCER,
            created_at=utc_now(),
            plan_run="pr",
            referee="a",
            question="which?",
            options=[
                DecisionOption(node="a", provider="p1", capability="x.y", status="ok"),
                DecisionOption(node="b", provider="p1", capability="y.z", status="ok"),
            ],
            chosen="a",
            rejected=["b"],
        )
        graph = build_graph(
            "pr",
            self._descriptor(),
            [],
            self._plan(),
            None,
            self._executions(),
            decision=decision,
        )
        node_ids = {n.id for n in graph.nodes}
        assert "decision:a" in node_ids
        edges = {(e.kind, e.source, e.target) for e in graph.edges}
        assert ("derived_from", "decision:a", "plan_node:a") in edges
        assert ("supports", "decision:a", "plan_node:a") in edges

    def test_decision_unresolved_has_no_supports(self) -> None:
        decision = DecisionRecord(
            producer=PRODUCER,
            created_at=utc_now(),
            plan_run="pr",
            referee="a",
            question="which?",
            options=[
                DecisionOption(node="a", provider="p1", capability="x.y", status="ok"),
                DecisionOption(node="b", provider="p1", capability="y.z", status="ok"),
            ],
        )
        graph = build_graph(
            "pr",
            self._descriptor(),
            [],
            self._plan(),
            None,
            self._executions(),
            decision=decision,
        )
        assert "decision:a" in {n.id for n in graph.nodes}
        assert not [e for e in graph.edges if e.kind == "supports"]


class TestNodeEdgeKinds:
    def test_new_kinds_accepted(self) -> None:
        # Kind membership is schema-level (Literal); construction is permissive.
        GraphNode(id="memory:x", kind="memory")
        GraphNode(id="decision:x", kind="decision")
        GraphNode(id="execution:x", kind="execution")
        GraphNode(id="failure:x", kind="failure")
