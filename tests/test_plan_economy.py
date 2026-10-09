"""Cycle 3.1 Wave F: economy and trace federation.

``compose_economy`` unit tests cover the Phase 19-21 rules: UNKNOWN != ZERO
(unresolved metrics never carry a value and block the sum), only compatible
values aggregate (not_applicable contributes nothing), and disagreeing sources
are named as conflicts — never silently averaged. The e2e proves the whole
binding: node results -> ProviderEconomyReceipt -> EconomyRollup artifact ->
PlanResult/PlanRefs hashes -> explain. Phase 22 links the node span to the
provider-native trace via ``native_trace_ref``.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from helpers import API_PLAN_ENTRY, SPARK_PLAN_ENTRY, fixture_argv, make_workspace
from theforge.contracts.base import ContractError, from_dict
from theforge.contracts.economy import (
    ECONOMY_ROLLUP_SCHEMA,
    EconomyMetric,
)
from theforge.contracts.plan import NodeOutcome, PlanNode
from theforge.contracts.result import ExecutionResult
from theforge.contracts.task import TaskSpec
from theforge.contracts.telemetry import (
    NATIVE_TRACE_PATH_MAX,
    NATIVE_TRACE_SUMMARY_MAX,
    NativeTrace,
)
from theforge.contracts.types import Producer
from theforge.forger import Forger, PlanCommand, PlanExecutor
from theforge.planning.economy import compose_economy
from theforge.planning.execution import NodeExecution
from theforge.registry import Registry
from theforge.runs import RunStore

P = Producer(id="theforge", version="1")
TS = "2026-01-01T00:00:00Z"
SHA = "a" * 64
PROVIDERS = Path(__file__).parent / "fixtures" / "providers"

SPARK_ECON_ENTRY = dict(
    SPARK_PLAN_ENTRY,
    argv=fixture_argv("fixture_forge.py", str(PROVIDERS / "fixture-spark-econ.json")),
)
API_ECON_ENTRY = dict(
    API_PLAN_ENTRY, argv=fixture_argv("fixture_forge.py", str(PROVIDERS / "fixture-api-econ.json"))
)

TASK = TaskSpec(
    producer=P,
    created_at=TS,
    id="t1",
    intent="bounded federation",
    workspace_root=".",
    targets=["."],
)


def _node(nid: str, provider: str = "p") -> PlanNode:
    return PlanNode(
        id=nid,
        role="standalone",
        provider=provider,  # type: ignore[arg-type]
        capability="p.cap",
        action="act",
    )


def _exec(nid: str, economy: dict[str, Any] | None = None, status: str = "ok") -> NodeExecution:
    node = _node(nid)
    valid = status in ("ok", "partial")
    # The provider emits JSON; the core parses it — build the result through
    # the same path (dict -> from_dict -> typed contract).
    result = (
        from_dict(
            ExecutionResult,
            {
                "producer": {"id": "p", "version": "0"},
                "created_at": TS,
                "status": "ok",
                **({"provider_economy": economy} if economy else {}),
            },
        )
        if valid
        else None
    )
    return NodeExecution(
        node=node,
        provider=Producer(id="p", version="0"),
        handoff=None,
        result=result,
        reached_execute=valid,
        outcome=NodeOutcome(
            node=nid,
            status=status,  # type: ignore[arg-type]
            run_id=f"r-{nid}" if valid else None,
            receipt_sha256=SHA if valid else None,
            result_sha256=SHA if valid else None,
            blocked_by=None if status != "skipped" else "a",
        ),
    )


def _receipt(**metrics: dict[str, Any]) -> dict[str, Any]:
    return {"schema": "theforge/ProviderEconomyReceipt/v1", "provider": "p", "run": "r1", **metrics}


# --- EconomyMetric / ProviderEconomyReceipt invariants (Phase 20) --------------------------


def test_economy_metric_unresolved_never_carries_a_value() -> None:
    with pytest.raises(ContractError, match="cannot carry a value"):
        EconomyMetric(value=0, status="unresolved")
    with pytest.raises(ContractError, match="cannot carry a value"):
        EconomyMetric(value=0.0, status="not_applicable")


def test_economy_metric_measured_requires_a_value() -> None:
    with pytest.raises(ContractError, match="requires a numeric value"):
        EconomyMetric(status="measured")
    with pytest.raises(ContractError, match="requires a numeric value"):
        EconomyMetric(status="estimated")
    with pytest.raises(ContractError, match="cannot be negative"):
        EconomyMetric(value=-1, status="measured")


def test_provider_economy_round_trip_on_result() -> None:
    receipt = _receipt(
        context_bytes={"value": 512, "status": "measured"}, provider_tokens={"status": "unresolved"}
    )
    result = from_dict(
        ExecutionResult,
        {
            "producer": {"id": "p", "version": "0"},
            "created_at": TS,
            "status": "ok",
            "provider_economy": receipt,
        },
        strict=True,
    )
    assert result.provider_economy is not None
    assert result.provider_economy.context_bytes.value == 512
    assert result.provider_economy.provider_tokens.status == "unresolved"
    assert result.provider_economy.provider_tokens.value is None


# --- compose_economy (Phase 21) -------------------------------------------------------------


def test_compose_economy_is_none_without_receipts() -> None:
    assert compose_economy("p1", [_exec("n1"), _exec("n2")]) is None


def test_compose_economy_sums_compatible_values() -> None:
    a = _receipt(
        context_bytes={"value": 100, "status": "measured"},
        wall_time_ms={"value": 10, "status": "measured"},
    )
    b = _receipt(
        context_bytes={"value": 50, "status": "measured"},
        wall_time_ms={"value": 5, "status": "estimated"},
        run="r2",
    )
    rollup = compose_economy("p1", [_exec("n1", a), _exec("n2", b)])
    assert rollup is not None and rollup.schema == ECONOMY_ROLLUP_SCHEMA
    assert [entry.node for entry in rollup.receipts] == ["n1", "n2"]
    assert rollup.totals["context_bytes"].value == 150
    assert rollup.totals["context_bytes"].status == "measured"
    # A mixed measured+estimated total degrades to estimated — honesty in the sum.
    assert rollup.totals["wall_time_ms"].value == 15
    assert rollup.totals["wall_time_ms"].status == "estimated"
    assert rollup.conflicts == []


def test_compose_economy_unresolved_blocks_the_sum() -> None:
    a = _receipt(cost_usd={"value": 0.5, "status": "measured"})
    b = _receipt(cost_usd={"status": "unresolved"}, run="r2")
    rollup = compose_economy("p1", [_exec("n1", a), _exec("n2", b)])
    assert rollup is not None
    # Never a partial sum: unknown + measured is unknown, not "0.5 so far".
    assert rollup.totals["cost_usd"].value is None
    assert rollup.totals["cost_usd"].status == "unresolved"
    assert any("cost_usd" in note and "n2" in note for note in rollup.limitations)


def test_compose_economy_not_applicable_never_blocks() -> None:
    a = _receipt(model_calls={"value": 2, "status": "measured"})
    b = _receipt(model_calls={"status": "not_applicable"}, run="r2")
    c = _receipt(model_calls={"status": "not_applicable"}, run="r3")
    rollup = compose_economy("p1", [_exec("n1", a), _exec("n2", b), _exec("n3", c)])
    assert rollup is not None
    assert rollup.totals["model_calls"].value == 2
    assert rollup.totals["model_calls"].status == "measured"
    only_na = compose_economy("p1", [_exec("n1", c)])
    assert only_na is not None
    assert only_na.totals["model_calls"].status == "not_applicable"


def test_compose_economy_conflicting_sources_never_average() -> None:
    a = _receipt(cost_usd={"value": 0.5, "status": "measured"})
    b = _receipt(cost_usd={"value": 0.9, "status": "measured"})
    rollup = compose_economy("p1", [_exec("n1", a), _exec("n2", b)])
    assert rollup is not None
    assert rollup.conflicts and "cost_usd" in rollup.conflicts[0]
    assert rollup.totals["cost_usd"].status == "unresolved"
    assert rollup.totals["cost_usd"].value is None


def test_compose_economy_skips_nodes_without_a_valid_result() -> None:
    rollup = compose_economy("p1", [_exec("n1", status="refused")])
    assert rollup is None


# --- NativeTrace (Phase 22) ------------------------------------------------------------------


def test_native_trace_bounds_and_ref() -> None:
    with pytest.raises(ContractError, match="ref must not be empty"):
        NativeTrace(ref="")
    with pytest.raises(ContractError, match="summary"):
        NativeTrace(ref="tr:1", summary="x" * (NATIVE_TRACE_SUMMARY_MAX + 1))
    with pytest.raises(ContractError, match="critical_path"):
        NativeTrace(ref="tr:1", critical_path=["s"] * (NATIVE_TRACE_PATH_MAX + 1))
    trace = NativeTrace(ref="tr:1", critical_path=["a", "b"])
    assert trace.critical_path == ["a", "b"]


# --- e2e: pipeline rollup + span link -------------------------------------------------------


def _executor(root: Path, entries: list[dict[str, Any]]) -> tuple[PlanExecutor, RunStore]:
    forge = make_workspace(root, entries)
    store = RunStore(forge)
    return PlanExecutor(Forger(root, Registry(forge), store)), store


def _plan_file(path: Path, nodes: list[dict[str, Any]], pattern: str) -> Path:
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


def _file_node(nid: str, provider: str, capability: str, action: str, *deps: str) -> dict[str, Any]:
    node: dict[str, Any] = {
        "id": nid,
        "role": "standalone",
        "provider": provider,
        "capability": capability,
        "action": action,
    }
    if deps:
        node["depends_on"] = [
            {"node": d, "epistemic": "explicit", "evidence": "plan file"} for d in deps
        ]
        node["inputs"] = list(deps)
    return node


def test_plan_rolls_up_provider_economy(tmp_path: Path) -> None:
    """Phase 21 e2e: two providers reporting economy produce the bound rollup."""
    executor, store = _executor(tmp_path, [SPARK_ECON_ENTRY, API_ECON_ENTRY])
    plan_file = _plan_file(
        tmp_path / "plan.json",
        [
            _file_node("n1", "fixture-spark", "spark.performance", "diagnose"),
            _file_node("n2", "fixture-api", "api.contract", "review", "n1"),
        ],
        "pipeline",
    )
    out = executor.run(
        PlanCommand(intent="bounded economy", profile="max", plan_file=plan_file, execute=True)
    )
    assert out.status == "ok" and out.result is not None

    rollup = store.read_optional(out.run_id, "economy")
    assert rollup is not None and rollup["schema"] == ECONOMY_ROLLUP_SCHEMA
    assert out.result.economy_sha256 is not None
    receipt = store.read(out.run_id, "receipt")
    assert receipt["plan"]["economy_sha256"] == out.result.economy_sha256

    by_node = {entry["node"]: entry["receipt"] for entry in rollup["receipts"]}
    assert set(by_node) == {"n1", "n2"}
    assert by_node["n1"]["provider"] == "fixture-spark"
    assert by_node["n1"]["provider_tokens"]["status"] == "estimated"
    totals = rollup["totals"]
    assert totals["context_bytes"] == {"value": 6144, "status": "measured"}
    assert totals["tool_calls"] == {"value": 4, "status": "measured"}
    assert totals["model_calls"] == {"status": "not_applicable", "value": None}
    assert totals["wall_time_ms"] == {"value": 1112, "status": "measured"}
    # spark estimated tokens + api unresolved: the metric cannot total.
    assert totals["provider_tokens"]["status"] == "unresolved"
    assert totals["provider_tokens"]["value"] is None
    # api estimated cost + spark unresolved: same rule.
    assert totals["cost_usd"]["status"] == "unresolved"
    assert totals["cost_usd"]["value"] is None
    assert rollup["conflicts"] == []


def test_plan_links_the_native_trace_on_the_node_span(tmp_path: Path) -> None:
    """Phase 22 e2e: the node span carries ``native_trace_ref``, not the spans."""
    executor, store = _executor(tmp_path, [SPARK_ECON_ENTRY, API_PLAN_ENTRY])
    plan_file = _plan_file(
        tmp_path / "plan.json",
        [
            _file_node("n1", "fixture-spark", "spark.performance", "diagnose"),
            _file_node("n2", "fixture-api", "api.contract", "review", "n1"),
        ],
        "pipeline",
    )
    out = executor.run(
        PlanCommand(intent="trace federation", profile="max", plan_file=plan_file, execute=True)
    )
    assert out.status == "ok" and out.result is not None

    telemetry = store.read(out.run_id, "telemetry")
    spans = {s["name"]: s for s in telemetry["spans"]}
    assert spans["node:n1"]["attributes"]["native_trace_ref"] == "sparktrace://run-7"
    assert "native_trace_ref" not in spans["node:n2"]["attributes"]

    # The child run's result carries the bounded pointer; explain exposes it.
    n1 = next(o for o in out.result.nodes if o.node == "n1")
    assert n1.run_id is not None
    result = store.read(n1.run_id, "result")
    assert result["native_trace"]["ref"] == "sparktrace://run-7"
    assert result["native_trace"]["critical_path"] == ["analyze", "emit"]

    from theforge.explain import build_explain_report

    report = build_explain_report(store, n1.run_id)
    assert report.result is not None and report.result.native_trace is not None
    assert report.result.native_trace.ref == "sparktrace://run-7"


def test_economy_absent_when_no_node_reports(tmp_path: Path) -> None:
    """No provider economy -> no artifact, no refs, no explain section."""
    executor, store = _executor(tmp_path, [SPARK_PLAN_ENTRY, API_PLAN_ENTRY])
    plan_file = _plan_file(
        tmp_path / "plan.json",
        [_file_node("n1", "fixture-spark", "spark.performance", "diagnose")],
        "pipeline",
    )
    out = executor.run(
        PlanCommand(intent="silent economy", profile="max", plan_file=plan_file, execute=True)
    )
    assert out.status == "ok" and out.result is not None
    assert out.result.economy_sha256 is None
    assert store.read_optional(out.run_id, "economy") is None
    assert store.read(out.run_id, "receipt")["plan"]["economy_sha256"] is None
