"""Cycle 3 wave B: CapabilityGraph/v1 — derived from manifests and the workspace
descriptor only (never hardcoded domains), every edge evidenced, queries for
planning (executors/verifiers/consumers/order)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from helpers import API_ENTRY, SPARK_ENTRY, case_a, make_workspace
from theforge.capability_graph import (
    build_capability_graph,
    complements,
    conflicts,
    consumers,
    executors,
    producers,
    produces_consumes_order,
    reviewers,
    verifiers,
)
from theforge.contracts import (
    Capability,
    CapabilityGraph,
    CapabilityRelations,
    ContractError,
    ExecutionReceipt,
    ForgeManifest,
    from_dict,
    to_dict,
)
from theforge.contracts.canonical import utc_now
from theforge.contracts.capability_graph import CapEdge, CapNode
from theforge.contracts.workspace import (
    RepositoryInfo,
    Technology,
    WorkspaceDescriptor,
)
from theforge.forger import Forger, PlanCommand, PlanExecutor
from theforge.meta import PRODUCER
from theforge.registry import Registry
from theforge.registry.config import ProviderEntry
from theforge.registry.registry import RegistryRecord
from theforge.runs import RunStore


def _record(pid: str, manifest: ForgeManifest | None) -> RegistryRecord:
    return RegistryRecord(
        entry=ProviderEntry(id=pid, argv=["x"], trust="local"),
        state="ready" if manifest else "broken",
        manifest=manifest,
    )


def _manifest(pid: str, *caps: Capability, domains: list[str] | None = None) -> ForgeManifest:
    return ForgeManifest(
        id=pid,
        version="0.1",
        protocols=["forge/v1"],
        ops=["describe", "health", "execute"],
        domains=domains or [],
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


def _descriptor() -> WorkspaceDescriptor:
    return WorkspaceDescriptor(
        producer=PRODUCER,
        created_at=utc_now(),
        root=".",
        repositories=[RepositoryInfo(path=".")],
        technologies=[
            Technology(
                name="pyspark",
                repository=".",
                source="dependency_manifest",
                evidence="requirements.txt",
                matched_by=["forge-a/etl.run"],
            )
        ],
    )


def _graph(
    *records: RegistryRecord, descriptor: WorkspaceDescriptor | None = None
) -> CapabilityGraph:
    return build_capability_graph(list(records), descriptor, run_id="r")


class TestContract:
    def test_node_kind_and_prefix(self) -> None:
        CapNode(id="capability:a/b.c", kind="capability")
        with pytest.raises(ContractError):
            CapNode(id="capability:a/b.c", kind="provider")  # prefix mismatch
        with pytest.raises(ContractError):
            CapNode(id="x:y", kind="bogus")  # type: ignore[arg-type]

    def test_edge_needs_evidence(self) -> None:
        with pytest.raises(ContractError):
            CapEdge(
                source="capability:a/b.c",
                target="artifact_type:x",
                kind="produces",
                epistemic="explicit",
                evidence=" ",
            )

    def test_inferred_edge_needs_rule(self) -> None:
        with pytest.raises(ContractError):
            CapEdge(source="a", target="b", kind="requires", epistemic="inferred", evidence="e")
        with pytest.raises(ContractError):
            CapEdge(
                source="a",
                target="b",
                kind="requires",
                epistemic="explicit",
                evidence="e",
                rule="r",
            )

    def test_dangling_edge_rejected(self) -> None:
        with pytest.raises(ContractError):
            CapabilityGraph(
                producer=PRODUCER,
                created_at=utc_now(),
                run_id="r",
                nodes=[CapNode(id="capability:a/b.c", kind="capability")],
                edges=[
                    CapEdge(
                        source="capability:a/b.c",
                        target="capability:ghost/x.y",
                        kind="requires",
                        epistemic="explicit",
                        evidence="declared",
                    )
                ],
            )

    def test_duplicate_nodes_rejected(self) -> None:
        with pytest.raises(ContractError):
            CapabilityGraph(
                producer=PRODUCER,
                created_at=utc_now(),
                run_id="r",
                nodes=[
                    CapNode(id="provider:a", kind="provider"),
                    CapNode(id="provider:a", kind="provider"),
                ],
            )

    def test_round_trip(self) -> None:
        g = _graph(
            _record(
                "forge-a",
                _manifest(
                    "forge-a",
                    _cap("etl.run", relations=CapabilityRelations(produces=["orders.facts"])),
                ),
            )
        )
        assert from_dict(CapabilityGraph, to_dict(g), "$") == g


class TestRelationsContract:
    def test_bad_artifact_type(self) -> None:
        with pytest.raises(ContractError):
            CapabilityRelations(produces=["Not A Type!"])

    def test_bad_capability_ref(self) -> None:
        with pytest.raises(ContractError):
            CapabilityRelations(can_verify=["UPPER/case"])

    def test_defaults_empty(self) -> None:
        assert _cap("a.b").relations.produces == []


class TestBuilder:
    def test_manifest_structure(self) -> None:
        g = _graph(_record("forge-a", _manifest("forge-a", _cap("etl.run"), domains=["data"])))
        kinds = {(n.kind, n.id) for n in g.nodes}
        assert ("provider", "provider:forge-a") in kinds
        assert ("capability", "capability:forge-a/etl.run") in kinds
        assert ("action", "action:forge-a/etl.run/run") in kinds
        assert ("domain", "domain:data") in kinds
        edge_kinds = {(e.kind, e.source, e.target) for e in g.edges}
        assert ("has_capability", "provider:forge-a", "capability:forge-a/etl.run") in edge_kinds
        assert ("in_domain", "provider:forge-a", "domain:data") in edge_kinds

    def test_declared_relations(self) -> None:
        g = _graph(
            _record(
                "forge-a",
                _manifest(
                    "forge-a",
                    _cap(
                        "etl.run",
                        relations=CapabilityRelations(
                            produces=["orders.facts"], requires=["own.dep"]
                        ),
                    ),
                    _cap("own.dep"),
                ),
            ),
            _record(
                "forge-b",
                _manifest(
                    "forge-b",
                    _cap(
                        "api.serve",
                        relations=CapabilityRelations(
                            consumes=["orders.facts"],
                            can_verify=["forge-a/etl.run"],
                            complements=["etl.run"],
                            conflicts=["etl.run"],
                        ),
                    ),
                ),
            ),
        )
        kinds = {(e.kind, e.source, e.target) for e in g.edges}
        assert ("produces", "capability:forge-a/etl.run", "artifact_type:orders.facts") in kinds
        assert (
            "requires",
            "capability:forge-a/etl.run",
            "capability:forge-a/own.dep",
        ) in kinds  # bare ref -> same provider
        assert ("consumes", "capability:forge-b/api.serve", "artifact_type:orders.facts") in kinds
        assert ("can_verify", "capability:forge-b/api.serve", "capability:forge-a/etl.run") in kinds
        assert (
            "complements",
            "capability:forge-b/api.serve",
            "capability:forge-b/etl.run",
        ) in kinds
        assert ("conflicts", "capability:forge-b/api.serve", "capability:forge-b/etl.run") in kinds

    def test_capability_identity_collision_stays_namespaced(self) -> None:
        """§50: two providers declaring the same capability id produce distinct
        namespaced nodes — identity is provider-qualified, never merged."""
        g = _graph(
            _record(
                "forge-a",
                _manifest(
                    "forge-a",
                    _cap("etl.run", relations=CapabilityRelations(produces=["orders.facts"])),
                ),
            ),
            _record(
                "forge-b",
                _manifest(
                    "forge-b",
                    _cap("etl.run", relations=CapabilityRelations(produces=["orders.facts"])),
                ),
            ),
        )
        node_ids = {n.id for n in g.nodes}
        assert "capability:forge-a/etl.run" in node_ids
        assert "capability:forge-b/etl.run" in node_ids
        # Both feed the same artifact type — no silent collapse into one node.
        produces = {(e.source, e.target) for e in g.edges if e.kind == "produces"}
        assert ("capability:forge-a/etl.run", "artifact_type:orders.facts") in produces
        assert ("capability:forge-b/etl.run", "artifact_type:orders.facts") in produces
        # Producers of the artifact type resolve to BOTH namespaced capabilities.
        assert producers(g, "orders.facts") == ["forge-a/etl.run", "forge-b/etl.run"]
        # Executor lookup by the bare id returns both providers — ambiguity is
        # visible to the planner, never silently collapsed.
        assert executors(g, "forge-a/etl.run") == ["forge-a"]
        assert executors(g, "forge-b/etl.run") == ["forge-b"]

    def test_unresolved_target_named_not_dropped(self) -> None:
        g = _graph(
            _record(
                "forge-a",
                _manifest(
                    "forge-a",
                    _cap("etl.run", relations=CapabilityRelations(requires=["ghost/nope.x"])),
                ),
            )
        )
        assert any(e.target == "capability:ghost/nope.x" for e in g.edges)
        assert any("ghost/nope.x" in lim for lim in g.limitations)

    def test_provider_without_manifest_is_named(self) -> None:
        g = _graph(_record("broken-p", None))
        assert g.nodes == []
        assert any("broken-p" in lim for lim in g.limitations)

    def test_workspace_nodes_observed(self) -> None:
        g = _graph(
            _record("forge-a", _manifest("forge-a", _cap("etl.run"))), descriptor=_descriptor()
        )
        assert ("repository", "repository:.") in {(n.kind, n.id) for n in g.nodes}
        tech_id = "technology:.:pyspark"
        edge_kinds = {(e.kind, e.source, e.target) for e in g.edges}
        assert ("uses_technology", "repository:.", tech_id) in edge_kinds
        assert ("relevant_to", "capability:forge-a/etl.run", tech_id) in edge_kinds

    def test_no_descriptor_is_a_limitation(self) -> None:
        g = _graph(_record("forge-a", _manifest("forge-a", _cap("etl.run"))))
        assert any("no workspace descriptor" in lim for lim in g.limitations)

    def test_deterministic_ordering(self) -> None:
        records = [
            _record("forge-b", _manifest("forge-b", _cap("y.z"))),
            _record("forge-a", _manifest("forge-a", _cap("a.b"))),
        ]
        a = _graph(*records)
        b = _graph(*reversed(records))
        assert [n.id for n in a.nodes] == [n.id for n in b.nodes]
        assert [(e.source, e.kind, e.target) for e in a.edges] == [
            (e.source, e.kind, e.target) for e in b.edges
        ]


class TestQueries:
    def _g(self) -> CapabilityGraph:
        return _graph(
            _record(
                "forge-a",
                _manifest(
                    "forge-a",
                    _cap("etl.run", relations=CapabilityRelations(produces=["orders.facts"])),
                ),
            ),
            _record(
                "forge-b",
                _manifest(
                    "forge-b",
                    _cap(
                        "api.serve",
                        relations=CapabilityRelations(
                            consumes=["orders.facts"],
                            can_verify=["forge-a/etl.run"],
                            can_review=["etl.run"],
                        ),
                    ),  # bare ref
                    _cap("etl.run"),
                ),
            ),
        )

    def test_executors_producers_consumers(self) -> None:
        g = self._g()
        assert executors(g, "forge-a/etl.run") == ["forge-a"]
        assert executors(g, "etl.run") == ["forge-a", "forge-b"]  # bare matches all
        assert producers(g, "orders.facts") == ["forge-a/etl.run"]
        assert consumers(g, "orders.facts") == ["forge-b/api.serve"]

    def test_verifiers_reviewers(self) -> None:
        g = self._g()
        assert verifiers(g, "forge-a/etl.run") == ["forge-b/api.serve"]
        assert verifiers(g, "api.serve") == []
        # bare ref in declaration resolved to the declaring provider
        assert reviewers(g, "forge-b/etl.run") == ["forge-b/api.serve"]

    def test_complements_and_conflicts_are_symmetric(self) -> None:
        g = _graph(
            _record(
                "forge-a",
                _manifest(
                    "forge-a",
                    _cap(
                        "etl.run",
                        relations=CapabilityRelations(
                            complements=["monitor.watch"], conflicts=["etl.legacy"]
                        ),
                    ),
                    _cap("monitor.watch"),
                    _cap("etl.legacy"),
                ),
            )
        )
        assert complements(g, "forge-a/etl.run") == ["forge-a/monitor.watch"]
        # symmetric: the complement target sees the relation back
        assert complements(g, "forge-a/monitor.watch") == ["forge-a/etl.run"]
        assert conflicts(g, "forge-a/etl.legacy") == ["forge-a/etl.run"]

    def test_order_requires_and_produce_consume(self) -> None:
        g = self._g()
        order, unresolved = produces_consumes_order(g, ["forge-b/api.serve", "forge-a/etl.run"])
        assert order == ["forge-a/etl.run", "forge-b/api.serve"]
        assert unresolved == []

    def test_order_cycle_named(self) -> None:
        g = _graph(
            _record(
                "p",
                _manifest(
                    "p",
                    _cap("a.x", relations=CapabilityRelations(requires=["b.y"])),
                    _cap("b.y", relations=CapabilityRelations(requires=["a.x"])),
                ),
            )
        )
        order, unresolved = produces_consumes_order(g, ["p/a.x", "p/b.y"])
        assert order == []
        assert unresolved == ["p/a.x", "p/b.y"]

    def test_order_missing_refs_kept_in_input_order(self) -> None:
        g = self._g()
        order, unresolved = produces_consumes_order(
            g, ["ghost/x.y", "forge-b/api.serve", "forge-a/etl.run"]
        )
        assert order == ["forge-a/etl.run", "forge-b/api.serve", "ghost/x.y"]
        assert unresolved == []


class TestPlanRun:
    def test_plan_run_persists_and_binds_the_graph(self, tmp_path: Path) -> None:
        make_workspace(tmp_path, [SPARK_ENTRY, API_ENTRY])
        case_a(tmp_path)
        forge_dir = tmp_path / ".forge"
        store = RunStore(forge_dir)
        out = PlanExecutor(Forger(tmp_path, Registry(forge_dir), store)).run(
            PlanCommand(intent="analise o job spark")
        )
        assert out.status in ("planned", "refused", "ambiguous", "no_route")
        raw = store.read_optional(out.run_id, "capability-graph")
        assert raw is not None
        graph = from_dict(CapabilityGraph, raw, "$")
        assert any(n.kind == "capability" for n in graph.nodes)
        receipt = store.read_contract(out.run_id, "receipt", ExecutionReceipt)
        assert receipt.plan is not None
        assert receipt.plan.capability_graph_sha256 == store.persisted_sha256(
            out.run_id, "capability-graph"
        )

    def test_plan_run_graph_carries_declared_relations(self, tmp_path: Path) -> None:
        """The plan fixtures declare produces/consumes/can_review: the persisted
        graph must carry them as cross-provider edges (B4 end to end)."""
        from helpers import API_PLAN_ENTRY, SPARK_PLAN_ENTRY

        make_workspace(tmp_path, [SPARK_PLAN_ENTRY, API_PLAN_ENTRY])
        case_a(tmp_path)
        forge_dir = tmp_path / ".forge"
        store = RunStore(forge_dir)
        out = PlanExecutor(Forger(tmp_path, Registry(forge_dir), store)).run(
            PlanCommand(
                intent="Projete um pipeline Spark que produza dados para uma API", profile="max"
            )
        )
        assert out.status == "planned"
        graph = from_dict(CapabilityGraph, store.read(out.run_id, "capability-graph"), "$")
        edges = {(e.kind, e.source, e.target) for e in graph.edges}
        spark = "capability:fixture-spark/spark.performance"
        assert ("produces", spark, "artifact_type:spark.analysis-report") in edges
        assert (
            "consumes",
            "capability:fixture-api/api.contract",
            "artifact_type:spark.analysis-report",
        ) in edges
        assert ("can_review", "capability:fixture-api/api.contract", spark) in edges
        # the queries answer the B5 questions over the real manifests
        assert producers(graph, "spark.analysis-report") == ["fixture-spark/spark.performance"]
        assert consumers(graph, "spark.analysis-report") == ["fixture-api/api.contract"]
        order, unresolved = produces_consumes_order(
            graph, ["fixture-api/api.contract", "fixture-spark/spark.performance"]
        )
        assert (
            order == ["fixture-spark/spark.performance", "fixture-api/api.contract"]
            and unresolved == []
        )


class TestMeshView:
    """Cycle 3.1 Phase 83: the domain mesh projection — observe/engineer/verify
    per domain, derived only from declared relations and manifest domains."""

    def test_observe_engineer_verify_per_domain(self) -> None:
        from theforge.capability_graph import mesh_view

        graph = _graph(
            _record(
                "doc-data",
                _manifest(
                    "doc-data",
                    _cap(
                        "data.scan",
                        relations=CapabilityRelations(produces=["data.diagnostic-evidence"]),
                    ),
                    _cap(
                        "data.verify", relations=CapabilityRelations(can_verify=["eng/spark.job"])
                    ),
                    domains=["data"],
                ),
            ),
            _record(
                "doc-api",
                _manifest(
                    "doc-api",
                    _cap(
                        "api.diagnose",
                        relations=CapabilityRelations(produces=["api.diagnostic-evidence"]),
                    ),
                    _cap(
                        "api.verify",
                        relations=CapabilityRelations(can_verify=["apieng/api.analyze"]),
                    ),
                    domains=["api"],
                ),
            ),
            _record(
                "eng",
                _manifest(
                    "eng",
                    _cap(
                        "spark.job",
                        relations=CapabilityRelations(consumes=["data.diagnostic-evidence"]),
                    ),
                    domains=["data"],
                ),
            ),
            _record(
                "apieng",
                _manifest(
                    "apieng",
                    _cap(
                        "api.analyze",
                        relations=CapabilityRelations(consumes=["api.diagnostic-evidence"]),
                    ),
                    domains=["api"],
                ),
            ),
        )
        mesh = mesh_view(graph)
        rows = {row["domain"]: row for row in mesh["domains"]}
        assert set(rows) == {"data", "api"}
        assert rows["data"] == {
            "domain": "data",
            "observe": ["doc-data/data.scan"],
            "engineer": ["eng/spark.job"],
            "verify": ["doc-data/data.verify"],
        }
        assert rows["api"]["verify"] == ["doc-api/api.verify"]
        assert mesh["unplaced_verify"] == []

    def test_verifier_declared_domains_narrow_the_placement(self) -> None:
        """A verifier whose manifest declares ``api`` does not land under
        ``data`` even when the engineer it verifies also consumes there."""
        from theforge.capability_graph import mesh_view

        graph = _graph(
            _record(
                "doc-api",
                _manifest(
                    "doc-api",
                    _cap("api.verify", relations=CapabilityRelations(can_verify=["eng/job.run"])),
                    domains=["api"],
                ),
            ),
            _record(
                "doc",
                _manifest(
                    "doc",
                    _cap("obs.scan", relations=CapabilityRelations(produces=["data.e", "api.e"])),
                ),
            ),
            _record(
                "eng",
                _manifest(
                    "eng",
                    _cap("job.run", relations=CapabilityRelations(consumes=["data.e", "api.e"])),
                    domains=["data", "api"],
                ),
            ),
        )
        mesh = mesh_view(graph)
        rows = {row["domain"]: row for row in mesh["domains"]}
        assert rows["api"]["verify"] == ["doc-api/api.verify"]
        assert rows["data"]["verify"] == []
        assert mesh["unplaced_verify"] == []

    def test_unplaced_verify_named(self) -> None:
        from theforge.capability_graph import mesh_view

        graph = _graph(
            _record(
                "doc",
                _manifest(
                    "doc",
                    _cap("obs.scan", relations=CapabilityRelations(produces=["data.e"])),
                    _cap(
                        "obs.verify", relations=CapabilityRelations(can_verify=["stray/orphan.cap"])
                    ),
                    domains=["data"],
                ),
            ),
            _record(
                "eng",
                _manifest(
                    "eng",
                    _cap("job.run", relations=CapabilityRelations(consumes=["data.e"])),
                    domains=["data"],
                ),
            ),
            _record("stray", _manifest("stray", _cap("orphan.cap"))),
        )  # produces/consumes nothing
        mesh = mesh_view(graph)
        assert mesh["domains"][0]["verify"] == []
        assert mesh["unplaced_verify"] == ["doc/obs.verify -> stray/orphan.cap"]

    def test_empty_graph_gives_empty_mesh(self) -> None:
        from theforge.capability_graph import mesh_view

        assert mesh_view(_graph()) == {"domains": [], "unplaced_verify": []}
