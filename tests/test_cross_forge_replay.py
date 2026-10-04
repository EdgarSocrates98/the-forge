"""Cross-forge proof with the Wave B adapters in replay (cross-forge-foundation 8.2).

The real-provider-integration adapters run in ``--replay`` over the replay scenarios owned by
this spec, ``tests/fixtures/native/{sparkforge,apiforge}/scenarios/cross/`` (complete Wave B
scenarios: ``environment.json``, ``health.json`` and one recording per exercised action over the
``cross`` proof workspace). They are registered as ``spark-forge`` and ``api-forge`` and the
proof task runs through the ``PlanExecutor`` in ``max`` on the mounted workspace: the
decomposition is ``pyspark.static-analysis`` -> ``api.analyze``, the handoff of the Spark node
reaches the API node, which ignores it without error (it does not declare ``accepts_handoff``:
a ``handoff-use-undeclared`` limitation), and the synthesis references both node runs, whose
evidence carries the specialists' native ids.

The Spark Forge recording was made with ``theforge_sparkforge.record_execute`` from the local
real Spark Forge; the API Forge one is hand-built (``"provenance": "hand-built"``) from the case
files of a live API Forge run until the first run of the real-provider workflow re-records it.
Wave B's ``default`` scenarios are not used here.
"""

import json
import re
import sys
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest

from cross_workspace import CrossWorkspace, mounted_cross_workspace
from helpers import make_workspace
from theforge.contracts import ExecutionReceipt, ExecutionResult, Response
from theforge.contracts.plan import ExecutionPlan, PlanResult
from theforge.explain import build_explain_report
from theforge.forger import Forger, PlanCommand, PlanExecutor
from theforge.forger.orchestrator import HANDOFF_UNDECLARED_LIMITATION
from theforge.protocol import ProviderTransport, SubprocessTransport
from theforge.registry import Registry
from theforge.runs import RunStore

NATIVE = Path(__file__).parent / "fixtures" / "native"
SCENARIOS = {"spark-forge": ("theforge_sparkforge", NATIVE / "sparkforge" / "scenarios" / "cross"),
             "api-forge": ("theforge_apiforge", NATIVE / "apiforge" / "scenarios" / "cross")}
PROOF_TASK = "Projete um pipeline Spark que produza dados para uma API"
EXPECTED_NODES = [("n1", "spark-forge", "pyspark.static-analysis", "pyspark"),
                  ("n2", "api-forge", "api.analyze", "analyze")]
# Native evidence ids of the specialists (Wave B): Spark Forge facts, API Forge facts.
NATIVE_ID = {"spark-forge": re.compile(r"f_[0-9a-f]{6}"),
             "api-forge": re.compile(r"fact:[0-9a-f]{16}")}


def _entries() -> list[dict[str, Any]]:
    return [{"id": pid, "argv": [sys.executable, "-m", module, "--replay", str(scenario)],
             "trust": "local"} for pid, (module, scenario) in SCENARIOS.items()]


class _Spy:
    """Transport factory recording (responding provider, op, payload) of every call."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def __call__(self, argv: Sequence[str]) -> ProviderTransport:
        return _SpyTransport(self, argv)


class _SpyTransport:
    def __init__(self, spy: _Spy, argv: Sequence[str]) -> None:
        self.spy, self.inner = spy, SubprocessTransport(argv)

    def call(self, op: str, payload: dict[str, Any], *, timeout: float,
             cwd: Path | None = None, check_protocol: bool = True) -> Response:
        response = self.inner.call(op, payload, timeout=timeout, cwd=cwd,
                                   check_protocol=check_protocol)
        self.spy.calls.append((response.producer.id, op, payload))
        return response


@pytest.fixture(scope="module")
def proof(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[Any, RunStore, _Spy]]:
    """One replay run of the proof task (the adapters are slow to start: run it once)."""
    with pytest.MonkeyPatch.context() as patch:  # isolated user dirs, as conftest does
        patch.setenv("THEFORGE_CONFIG_DIR", str(tmp_path_factory.mktemp("user-config")))
        patch.setenv("THEFORGE_CACHE_DIR", str(tmp_path_factory.mktemp("user-cache")))
        with mounted_cross_workspace(git=True) as cross:
            yield _run_proof(cross)


def _run_proof(cross: CrossWorkspace) -> tuple[Any, RunStore, _Spy]:
    forge = make_workspace(cross.root, _entries())
    store, spy = RunStore(forge), _Spy()
    executor = PlanExecutor(Forger(cross.root, Registry(forge), store, transport_factory=spy))
    out = executor.run(PlanCommand(intent=PROOF_TASK, profile="max", execute=True))
    return out, store, spy


def test_cross_scenarios_are_complete() -> None:
    """Every exercised action has its recording, next to environment and health."""
    for _pid, (_module, scenario) in SCENARIOS.items():
        assert (scenario / "environment.json").is_file(), scenario
        assert (scenario / "health.json").is_file(), scenario
    for _node, pid, capability, action in EXPECTED_NODES:
        scenario = SCENARIOS[pid][1]
        recordings = sorted(p.name for p in scenario.glob(f"{capability}.{action}*.json"))
        assert recordings == [f"{capability}.{action}.json"], (scenario, recordings)
    api = json.loads((SCENARIOS["api-forge"][1] / "api.analyze.analyze.json")
                     .read_text(encoding="utf-8"))
    assert api["provenance"] == "hand-built"  # until the real workflow re-records it
    spark = json.loads((SCENARIOS["spark-forge"][1] / "pyspark.static-analysis.pyspark.json")
                       .read_text(encoding="utf-8"))
    assert "provenance" not in spark  # recorded by record_execute from the real Spark Forge
    assert spark["arguments"]["path"] == "data-pipeline/jobs"


def test_proof_task_decomposes_into_spark_then_api(proof: tuple[Any, RunStore, _Spy]) -> None:
    out, store, spy = proof
    assert out.status == "ok", out.error
    plan = store.read_contract(out.run_id, "plan", ExecutionPlan)
    assert plan.source == "decomposed" and plan.pattern == "pipeline"
    assert [(n.id, n.provider, n.capability, n.action) for n in plan.nodes] == EXPECTED_NODES
    assert [d.node for d in plan.nodes[1].depends_on] == ["n1"]
    executes = [(pid, payload["capability"]) for pid, op, payload in spy.calls
                if op == "execute"]
    assert executes == [("spark-forge", "pyspark.static-analysis"),
                        ("api-forge", "api.analyze")]


def test_handoff_is_delivered_and_ignored_without_error(
        proof: tuple[Any, RunStore, _Spy]) -> None:
    out, store, spy = proof
    result = store.read_contract(out.run_id, "plan-result", PlanResult)
    n1, n2 = result.nodes
    assert (n1.status, n2.status) == ("ok", "ok")
    assert n1.run_id is not None and n2.run_id is not None
    handoff = store.read(n2.run_id, "handoff")
    assert handoff["items"] and not handoff["truncated"]
    assert {item["origin"]["node"] for item in handoff["items"]} == {"n1"}
    assert {item["origin"]["provider"]["id"] for item in handoff["items"]} == {"spark-forge"}
    (api_execute,) = [payload for pid, op, payload in spy.calls
                      if op == "execute" and pid == "api-forge"]
    assert api_execute["handoff"] == handoff  # delivered == persisted
    (spark_execute,) = [payload for pid, op, payload in spy.calls
                        if op == "execute" and pid == "spark-forge"]
    assert spark_execute.get("handoff") is None  # n1 has no input
    # The API Forge adapter answers ok ignoring the field; the core records the limitation.
    receipt = store.read_contract(n2.run_id, "receipt", ExecutionReceipt)
    assert receipt.status == "ok" and receipt.error is None
    assert f"{HANDOFF_UNDECLARED_LIMITATION}: api-forge/api.analyze" in receipt.limitations
    first = store.read_contract(n1.run_id, "receipt", ExecutionReceipt)
    assert not [n for n in first.limitations if n.startswith(HANDOFF_UNDECLARED_LIMITATION)]


def test_synthesis_references_both_runs_with_native_evidence_ids(
        proof: tuple[Any, RunStore, _Spy]) -> None:
    out, store, _ = proof
    result = store.read_contract(out.run_id, "plan-result", PlanResult)
    synthesis = result.synthesis
    assert [(s.node, s.provider, s.status) for s in synthesis.nodes] == [
        ("n1", "spark-forge", "ok"), ("n2", "api-forge", "ok")]
    assert [(h.source, h.target) for h in synthesis.handoffs] == [("n1", "n2")]
    for node in synthesis.nodes:
        assert node.run_id is not None
        node_result = store.read_contract(node.run_id, "result", ExecutionResult)
        ids = [e.id for e in node_result.evidence]
        assert ids and all(NATIVE_ID[node.provider].fullmatch(i) for i in ids), ids
        assert sum(node.evidence_by_epistemic.values()) == len(ids)
        for finding in node.findings:  # copies keep the native evidence ids
            assert set(finding.evidence_ids) <= set(ids)
    # The handoff items of n1's evidence keep its native ids and epistemic status.
    n1_run = synthesis.nodes[0].run_id
    n2_run = synthesis.nodes[1].run_id
    assert n1_run is not None and n2_run is not None
    source = {e.id: e for e in store.read_contract(n1_run, "result", ExecutionResult).evidence}
    items = [i for i in store.read(n2_run, "handoff")["items"] if i["kind"] == "evidence"]
    assert items
    for item in items:
        assert item["id"] in source and item["epistemic"] == source[item["id"]].epistemic


def test_plan_run_explains_without_divergence(proof: tuple[Any, RunStore, _Spy]) -> None:
    out, store, _ = proof
    report = build_explain_report(store, out.run_id)
    assert report.kind == "plan" and report.status == "ok"
    assert report.integrity.divergences == [], report.integrity.divergences
