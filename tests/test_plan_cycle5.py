"""Cycle 5 wave E/G: artifact-aware plan semantics — optional/mandatory nodes,
early global stop, conditions, and the pre-execution PlanSimulation bound to
the plan receipt.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from helpers import SPARK_PLAN_ENTRY, bad_entry, make_workspace
from theforge.capability_graph import build_capability_graph
from theforge.contracts import (
    Capability,
    CapabilityRelations,
    ExecutionInfo,
    ForgeManifest,
    PlanSimulation,
    from_dict,
)
from theforge.contracts.canonical import utc_now
from theforge.contracts.integrity import validate_plan_structure
from theforge.contracts.plan import (
    ExecutionPlan,
    NodeOutcome,
    PlanDependency,
    PlanNode,
)
from theforge.contracts.types import Producer
from theforge.forger import Forger, PlanCommand, PlanExecutor
from theforge.meta import PRODUCER
from theforge.planning.execution import NodeExecution
from theforge.registry import Registry
from theforge.registry.config import ProviderEntry
from theforge.registry.registry import RegistryRecord
from theforge.runs import RunStore
from theforge.simulation import simulate_plan

P1 = Producer(id="p1", version="0.1")
P2 = Producer(id="p2", version="0.1")


def _record(pid: str, manifest: ForgeManifest | None) -> RegistryRecord:
    return RegistryRecord(
        entry=ProviderEntry(id=pid, argv=["x"], trust="local"),
        state="ready" if manifest else "broken",
        manifest=manifest,
    )


def _manifest(
    pid: str,
    *caps: Capability,
    local: bool = True,
    offline: bool = True,
    requires_network: bool = False,
) -> ForgeManifest:
    return ForgeManifest(
        id=pid,
        version="0.1",
        protocols=["forge/v1"],
        ops=["describe", "health", "execute"],
        capabilities=list(caps),
        execution=ExecutionInfo(local=local, offline=offline, requires_network=requires_network),
    )


def _cap(cid: str, **kw: Any) -> Capability:
    kw.setdefault("operation_class", "read_only")
    return Capability(
        id=cid,
        actions=["run"],
        default_action="run",
        state="supported",
        **kw,
    )


def _node(nid: str, provider: str = "p1", **kw: Any) -> PlanNode:
    kw.setdefault("role", "standalone")
    return PlanNode(id=nid, provider=provider, capability="x.y", action="run", **kw)


def _plan(*nodes: PlanNode) -> ExecutionPlan:
    return ExecutionPlan(
        producer=PRODUCER,
        created_at=utc_now(),
        status="validated",
        plan_run="pr",
        task_id="t1",
        pattern="pipeline",
        source="decomposed",
        profile="max",
        nodes=list(nodes),
    )


class TestSimulation:
    def test_declared_footprint(self) -> None:
        m = _manifest("p1", _cap("x.y", operation_class="local_mutation"), requires_network=True)
        plan = _plan(_node("a"))
        sim = simulate_plan(plan, {"p1": _record("p1", m)})
        node = sim.nodes[0]
        assert node.network == "required" and node.mutations == "local"
        assert sim.cost == "unknown"
        assert "network" in sim.risk_flags and "local-only" not in sim.risk_flags
        assert sim.plan_sha256 and sim.providers == ["p1"]

    def test_missing_manifest_is_unknown_not_benign(self) -> None:
        sim = simulate_plan(_plan(_node("a", provider="ghost")), {})
        node = sim.nodes[0]
        assert node.network == "unknown" and node.mutations == "unknown"
        assert any("ghost" in lim for lim in sim.limitations)

    def test_local_only_flag(self) -> None:
        m = _manifest("p1", _cap("x.y"))
        sim = simulate_plan(_plan(_node("a")), {"p1": _record("p1", m)})
        assert "local-only" in sim.risk_flags

    def test_destructive_and_external_mutation_flags(self) -> None:
        m = _manifest(
            "p1",
            _cap("x.y", operation_class="destructive"),
            _cap("z.w", operation_class="external_mutation"),
        )
        plan = _plan(_node("a"), _node("b", provider="p1"))
        sim = simulate_plan(plan, {"p1": _record("p1", m)})
        assert "external-mutation" in sim.risk_flags and "destructive" in sim.risk_flags

    def test_verification_independence(self) -> None:
        m1 = _manifest(
            "p1",
            _cap(
                "x.y",
                relations=CapabilityRelations(produces=["report.v1"], verified_by=["p2/check.run"]),
            ),
        )
        m2 = _manifest(
            "p2", _cap("check.run", relations=CapabilityRelations(verifies=["report.v1"]))
        )
        records = {"p1": _record("p1", m1), "p2": _record("p2", m2)}
        graph = build_capability_graph(list(records.values()), run_id="r")
        plan = _plan(_node("a", verification_required=True, expected_outputs=["report.v1"]))
        sim = simulate_plan(plan, records, graph=graph)
        assert sim.nodes[0].verification == "independent"
        assert not sim.limitations

    def test_verification_required_without_verifier_is_a_limitation(self) -> None:
        m = _manifest("p1", _cap("x.y"))
        sim = simulate_plan(
            _plan(_node("a", verification_required=True)),
            {"p1": _record("p1", m)},
            graph=None,
        )
        assert sim.nodes[0].verification == "forge"
        assert any("independent" in lim for lim in sim.limitations) or any(
            "capability graph" in lim for lim in sim.limitations
        )

    def test_data_classification_is_the_maximum(self) -> None:
        m = _manifest("p1", _cap("x.y"))
        plan = _plan(
            _node("a", data_classification="public"),
            _node("b", data_classification="confidential"),
        )
        sim = simulate_plan(plan, {"p1": _record("p1", m)})
        assert sim.data_classification == "confidential"
        # unclassified plan -> unknown, never "public"
        sim2 = simulate_plan(_plan(_node("a")), {"p1": _record("p1", m)})
        assert sim2.data_classification == "unknown"


class TestStructureValidation:
    def test_unknown_condition_rejected(self) -> None:
        violations = validate_plan_structure(_plan(_node("a", condition="when-moon-full")))
        assert any("condition" in v.detail for v in violations)

    def test_conditional_needs_depends_on(self) -> None:
        violations = validate_plan_structure(_plan(_node("a", condition="on-success")))
        assert any("depends_on" in v.detail for v in violations)
        ok = _plan(
            _node("a"),
            _node(
                "b",
                condition="on-success",
                depends_on=[PlanDependency(node="a", epistemic="explicit", evidence="e")],
            ),
        )
        assert not validate_plan_structure(ok)

    def test_optional_referee_rejected(self) -> None:
        violations = validate_plan_structure(_plan(_node("a", role="referee", optional=True)))
        assert any("referee" in v.detail and "optional" in v.detail for v in violations)


class TestConditionSkip:
    """`_condition_unmet` over recorded outcomes (executor uses it per node)."""

    def _executions(self, statuses: dict[str, str]) -> list[NodeExecution]:
        return [
            NodeExecution(
                node=_node(nid),
                outcome=NodeOutcome(node=nid, status=status),
                result=None,
                handoff=None,
                provider=None,
            )
            for nid, status in statuses.items()
        ]

    def test_on_failure_skips_when_all_ok(self) -> None:
        from theforge.forger.plan_executor import _condition_unmet

        node = _node(
            "b",
            condition="on-failure",
            depends_on=[PlanDependency(node="a", epistemic="explicit", evidence="e")],
        )
        unmet = _condition_unmet(node, self._executions({"a": "ok"}))
        assert unmet is not None and unmet[0] == "a"
        # a failure lets the node run
        assert _condition_unmet(node, self._executions({"a": "provider_failure"})) is None

    def test_on_success_skips_when_dep_failed(self) -> None:
        from theforge.forger.plan_executor import _condition_unmet

        node = _node(
            "b",
            condition="on-success",
            depends_on=[PlanDependency(node="a", epistemic="explicit", evidence="e")],
        )
        assert _condition_unmet(node, self._executions({"a": "provider_failure"})) is not None
        assert _condition_unmet(node, self._executions({"a": "ok"})) is None


def _plan_file(path: Path, nodes: list[dict[str, Any]], pattern: str = "pipeline") -> Path:
    path.write_text(
        json.dumps(
            {
                "task_id": "from-file",
                "pattern": pattern,
                "source": "file",
                "profile": "max",
                "nodes": nodes,
            }
        ),
        encoding="utf-8",
    )
    return path


def _file_node(nid: str, provider: str, capability: str, action: str, **kw: Any) -> dict[str, Any]:
    node: dict[str, Any] = {
        "id": nid,
        "role": "standalone",
        "provider": provider,
        "capability": capability,
        "action": action,
    }
    node.update(kw)
    return node


class TestEarlyStopE2E:
    def test_optional_pruned_mandatory_runs(self, tmp_path: Path) -> None:
        """Two always-failing attempts on node `a` trip the repeated-failure stop;
        optional `b` is pruned, verification-required `c` still runs (§43-44)."""
        forge_dir = make_workspace(tmp_path, [SPARK_PLAN_ENTRY, bad_entry("crash", "bad-crash")])
        # retry.toml: two attempts so one crash node reaches the failure limit.
        (forge_dir / "config").mkdir(parents=True, exist_ok=True)
        (forge_dir / "config" / "retry.toml").write_text(
            '[retry]\nmax_attempts = 2\nretryable_codes = ["FORGE-PROTO-EXIT"]\n',
            encoding="utf-8",
        )
        store = RunStore(forge_dir)
        plan_file = _plan_file(
            tmp_path / "plan.json",
            [
                _file_node("a", "bad-crash", "bad.thing", "run"),
                _file_node("b", "fixture-spark", "spark.performance", "diagnose", optional=True),
                _file_node(
                    "c",
                    "fixture-spark",
                    "spark.performance",
                    "review",
                    verification_required=True,
                ),
            ],
        )
        out = PlanExecutor(Forger(tmp_path, Registry(forge_dir), store)).run(
            PlanCommand(intent="early stop", profile="max", plan_file=plan_file, execute=True)
        )
        assert out.result is not None
        by_id = {n.node: n for n in out.result.nodes}
        assert by_id["a"].status == "provider_failure"
        assert by_id["b"].status == "skipped"
        assert by_id["b"].error is not None and by_id["b"].error.code == "FORGE-PLAN-GLOBAL-STOP"
        assert by_id["b"].blocked_by == "a"
        assert by_id["c"].status == "ok"  # mandatory verification never skipped

    def test_simulation_persisted_and_bound(self, tmp_path: Path) -> None:
        forge_dir = make_workspace(tmp_path, [SPARK_PLAN_ENTRY])
        store = RunStore(forge_dir)
        plan_file = _plan_file(
            tmp_path / "plan.json",
            [_file_node("a", "fixture-spark", "spark.performance", "diagnose")],
        )
        out = PlanExecutor(Forger(tmp_path, Registry(forge_dir), store)).run(
            PlanCommand(intent="simulate", profile="max", plan_file=plan_file, execute=True)
        )
        assert out.status == "ok"
        raw = store.read_optional(out.run_id, "simulation")
        assert raw is not None
        sim = from_dict(PlanSimulation, raw, "$", strict=True)
        assert sim.cost == "unknown" and sim.nodes[0].node == "a"
        receipt = store.read(out.run_id, "receipt")
        assert receipt["plan"]["simulation_sha256"] == store.persisted_sha256(
            out.run_id, "simulation"
        )
