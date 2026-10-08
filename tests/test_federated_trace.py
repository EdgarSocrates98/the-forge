"""Cycle 5 wave W/X: federated trace correlation — plan runs carry a
``correlation_id`` (the tree root), node child runs inherit it and link
``parent_run``; economy ledger extended to the federated axes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from helpers import SPARK_PLAN_ENTRY, make_workspace
from theforge.contracts import from_dict
from theforge.contracts.canonical import sha256_of, utc_now
from theforge.contracts.economy import (
    ECONOMY_METRICS,
    EconomyMetric,
    ProviderEconomyReceipt,
)
from theforge.contracts.telemetry import RunTelemetry
from theforge.forger import Forger, PlanCommand, PlanExecutor
from theforge.registry import Registry
from theforge.runs import RunStore


def _plan_file(path: Path, nodes: list[dict[str, Any]]) -> Path:
    path.write_text(
        json.dumps(
            {
                "task_id": "corr",
                "pattern": "pipeline",
                "source": "file",
                "profile": "max",
                "nodes": nodes,
            }
        ),
        encoding="utf-8",
    )
    return path


def _node(nid: str, action: str = "diagnose") -> dict[str, Any]:
    return {
        "id": nid,
        "role": "standalone",
        "provider": "fixture-spark",
        "capability": "spark.performance",
        "action": action,
    }


class TestCorrelation:
    def test_plan_run_is_tree_root(self, tmp_path: Path) -> None:
        forge_dir = make_workspace(tmp_path, [SPARK_PLAN_ENTRY])
        store = RunStore(forge_dir)
        plan_file = _plan_file(tmp_path / "p.json", [_node("a")])
        out = PlanExecutor(Forger(tmp_path, Registry(forge_dir), store)).run(
            PlanCommand(intent="corr", profile="max", plan_file=plan_file, execute=True)
        )
        assert out.status == "ok"
        telemetry = from_dict(RunTelemetry, store.read(out.run_id, "telemetry"), "$", strict=True)
        assert telemetry.correlation_id == out.run_id
        assert telemetry.parent_run is None

    def test_node_run_inherits_correlation(self, tmp_path: Path) -> None:
        forge_dir = make_workspace(tmp_path, [SPARK_PLAN_ENTRY])
        store = RunStore(forge_dir)
        plan_file = _plan_file(tmp_path / "p.json", [_node("a"), _node("b", action="review")])
        out = PlanExecutor(Forger(tmp_path, Registry(forge_dir), store)).run(
            PlanCommand(intent="corr", profile="max", plan_file=plan_file, execute=True)
        )
        assert out.result is not None
        for node in out.result.nodes:
            assert node.run_id is not None
            telemetry = from_dict(
                RunTelemetry, store.read(node.run_id, "telemetry"), "$", strict=True
            )
            assert telemetry.parent_run == out.run_id
            assert telemetry.correlation_id == out.run_id
            receipt = store.read(node.run_id, "receipt")
            assert receipt["parent_run"] == out.run_id

    def test_env_correlation_wins(self, tmp_path: Path, monkeypatch) -> None:
        forge_dir = make_workspace(tmp_path, [SPARK_PLAN_ENTRY])
        store = RunStore(forge_dir)
        monkeypatch.setenv("THEFORGE_CORRELATION_ID", "fed-42")
        plan_file = _plan_file(tmp_path / "p.json", [_node("a")])
        out = PlanExecutor(Forger(tmp_path, Registry(forge_dir), store)).run(
            PlanCommand(intent="corr", profile="max", plan_file=plan_file, execute=True)
        )
        plan_t = from_dict(RunTelemetry, store.read(out.run_id, "telemetry"), "$", strict=True)
        assert plan_t.correlation_id == "fed-42"
        node_run = out.result.nodes[0].run_id
        node_t = from_dict(RunTelemetry, store.read(node_run, "telemetry"), "$", strict=True)
        assert node_t.correlation_id == "fed-42"


class TestEconomyV2:
    def test_federated_axes_exist_unresolved(self) -> None:
        receipt = ProviderEconomyReceipt(provider="p")
        for name in ("remote_calls", "artifact_bytes", "verification_calls", "retry_calls"):
            assert name in ECONOMY_METRICS
            metric = getattr(receipt, name)
            assert metric.status == "unresolved" and metric.value is None

    def test_federated_axes_measured(self) -> None:
        receipt = ProviderEconomyReceipt(
            provider="p",
            remote_calls=EconomyMetric(value=2.0, status="measured"),
            artifact_bytes=EconomyMetric(value=512.0, status="estimated"),
            verification_calls=EconomyMetric(value=1.0, status="measured"),
            retry_calls=EconomyMetric(value=0.0, status="measured"),
        )
        assert receipt.remote_calls.value == 2.0

    def test_unresolved_blocks_rollup_total(self) -> None:
        from theforge.contracts import ExecutionResult, PlanNode
        from theforge.contracts.plan import NodeOutcome
        from theforge.contracts.types import Producer
        from theforge.planning.economy import compose_economy
        from theforge.planning.execution import NodeExecution

        def _exec(nid: str, remote: float | None) -> NodeExecution:
            node = PlanNode(
                id=nid,
                role="standalone",
                provider="p",
                capability="p.cap",
                action="act",
            )
            economy = {
                "schema": "theforge/ProviderEconomyReceipt/v1",
                "provider": "p",
                "remote_calls": (
                    {"value": remote, "status": "measured"}
                    if remote is not None
                    else {"status": "unresolved"}
                ),
            }
            result = from_dict(
                ExecutionResult,
                {
                    "producer": {"id": "p", "version": "0"},
                    "created_at": utc_now(),
                    "status": "ok",
                    "provider_economy": economy,
                },
            )
            return NodeExecution(
                node=node,
                provider=Producer(id="p", version="0"),
                handoff=None,
                result=result,
                reached_execute=True,
                outcome=NodeOutcome(
                    node=nid,
                    status="ok",
                    run_id=f"r-{nid}",
                    receipt_sha256=sha256_of({"r": nid}),
                    result_sha256=sha256_of({"res": nid}),
                ),
            )

        rollup = compose_economy("pr", [_exec("a", 2.0), _exec("b", None)])
        assert rollup is not None
        # One contributor unresolved → the total cannot claim a number.
        assert rollup.totals["remote_calls"].status == "unresolved"
