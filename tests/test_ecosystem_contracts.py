"""Cycle 3.1 Phase 48 — ecosystem contract tests: the six boundaries, offline.

Each adapter runs in replay mode (``--replay <scenario>``), so the specialist is
never imported but the full subprocess/JSON contract path is exercised: the same
``describe``/``execute``/``health`` ops, the same ``ExecutionResult`` parsing,
the same handoff construction and the same hash anchoring as a real provider.
The ``scenarios/cross`` recordings were captured from live specialist runs that
consumed a handoff (``record_execute --handoff``), so consumption — not just
delivery — is proved at both engineer boundaries.

Flows covered:
  1. Doctor Data bundle  -> The Forge  (data.scan result + native/handoff.json)
  2. Doctor API bundle   -> The Forge  (api.diagnose result + native/handoff.json)
  3. Forge handoff       -> Spark Forge AWS (pyspark.static-analysis consumes it)
  4. Forge handoff       -> API Forge   (api.analyze consumes it)
  5. Spark receipt       -> The Forge   (ExecutionReceipt + hash chain)
  6. API receipt         -> The Forge   (provider_receipt bound + hash chain)
"""

import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from cross_workspace import CrossWorkspace, mounted_cross_workspace
from helpers import make_workspace
from theforge.contracts import from_dict
from theforge.contracts.handoff import Handoff
from theforge.contracts.receipt import ExecutionReceipt
from theforge.explain import build_explain_report
from theforge.explain.hashcheck import verify_run_hashes
from theforge.forger import Forger, PlanCommand, PlanExecutor
from theforge.registry import Registry
from theforge.runs import RunStore

NATIVE = Path(__file__).parent / "fixtures" / "native"


def _replay(adapter: str, scenario: str = "default") -> list[str]:
    return [sys.executable, "-m", f"theforge_{adapter}", "--replay",
            str(NATIVE / adapter / scenario)]


# The entry id must equal the manifest's declared provider id.
DD_ENTRY = {"id": "forge-doctor-data", "argv": _replay("doctordata"), "trust": "local"}
DA_ENTRY = {"id": "forge-doctor-api", "argv": _replay("doctorapi"), "trust": "local"}
SPARK_ENTRY = {"id": "spark-forge-aws", "argv": _replay("sparkforge_aws"), "trust": "local"}
SPARK_CROSS = {"id": "spark-forge-aws", "argv": _replay("sparkforge_aws", "scenarios/cross"),
               "trust": "local"}
API_ENTRY = {"id": "api-forge", "argv": _replay("apiforge"), "trust": "local"}
API_CROSS = {"id": "api-forge", "argv": _replay("apiforge", "scenarios/cross"),
             "trust": "local"}


@pytest.fixture
def cross() -> Iterator[CrossWorkspace]:
    with mounted_cross_workspace(git=True) as workspace:
        yield workspace


def _executor(root: Path, entries: list[dict[str, Any]]) -> tuple[PlanExecutor, RunStore]:
    forge = make_workspace(root, entries)
    store = RunStore(forge)
    return PlanExecutor(Forger(root, Registry(forge), store)), store


def _node(nid: str, provider: str, capability: str, action: str,
          *deps: str) -> dict[str, Any]:
    node: dict[str, Any] = {"id": nid, "role": "standalone", "provider": provider,
                            "capability": capability, "action": action}
    if deps:
        node["depends_on"] = [{"node": d, "epistemic": "explicit",
                               "evidence": "contract test"} for d in deps]
        node["inputs"] = list(deps)
    return node


def _run(root: Path, entries: list[dict[str, Any]], nodes: list[dict[str, Any]],
         *, profile: str = "max") -> tuple[Any, RunStore]:
    executor, store = _executor(root, entries)
    plan = root / "plan.json"
    plan.write_text(json.dumps({"task_id": "t", "pattern": "pipeline", "source": "file",
                                # The file must carry a real BudgetProfile; the
                                # command profile (possibly "auto") wins anyway.
                                "profile": "max", "nodes": nodes}),
                    encoding="utf-8")
    out = executor.run(PlanCommand(intent="ecosystem contract", profile=profile,
                                   plan_file=plan, execute=True))
    return out, store


def _child(out: Any, nid: str) -> str:
    outcome = next(o for o in out.result.nodes if o.node == nid)
    assert outcome.status == "ok" and outcome.run_id is not None
    return outcome.run_id


# --- 1/2. Doctor bundle -> The Forge ----------------------------------------------------------


def test_doctor_data_bundle_enters_the_forge(tmp_path: Path) -> None:
    out, store = _run(tmp_path, [DD_ENTRY],
                      [_node("n1", "forge-doctor-data", "data.scan", "analyze")])
    assert out.status == "ok"
    run_id = _child(out, "n1")

    result = store.read(run_id, "result")
    assert result["status"] == "ok" and result["findings"] and result["evidence"]
    # The doctor's native HandoffBundle landed as a declared, hashed artifact.
    assert [a["path"] for a in result["artifacts"]] == ["native/handoff.json"]
    bundle_path = store.run_dir(run_id) / "work" / "native" / "handoff.json"
    assert bundle_path.is_file()
    bundle = json.loads(bundle_path.read_text("utf-8"))
    assert bundle["contract_version"] == "forge-contracts/1" and bundle["findings"]
    # Bundle -> ExecutionResult -> receipt: the whole chain verifies.
    assert verify_run_hashes(store, run_id).divergences == []


def test_doctor_api_bundle_enters_the_forge(tmp_path: Path) -> None:
    out, store = _run(tmp_path, [DA_ENTRY],
                      [_node("n1", "forge-doctor-api", "api.diagnose", "analyze")])
    assert out.status == "ok"
    run_id = _child(out, "n1")

    result = store.read(run_id, "result")
    assert result["status"] == "ok" and result["evidence"]
    assert [a["path"] for a in result["artifacts"]] == ["native/handoff.json"]
    assert verify_run_hashes(store, run_id).divergences == []


# --- 3/4. Forge handoff -> specialist ----------------------------------------------------------


def _assert_handoff_consumed(store: RunStore, plan_run: str, consumer_run: str,
                             producer_id: str) -> Handoff:
    """The delivered handoff is a valid Handoff artifact, anchored on the
    consumer's receipt, and the recorded call consumed it (no audit limitation)."""
    receipt = store.read(consumer_run, "receipt")
    assert receipt["inputs"]["handoff_sha256"] is not None

    handoff = from_dict(Handoff, store.read(consumer_run, "handoff"), strict=True)
    assert handoff.plan_run == plan_run and handoff.items
    assert all(item.origin.provider.id == producer_id for item in handoff.items)

    result = store.read(consumer_run, "result")
    limitations = " ".join(result.get("limitations", []))
    assert "not consumed" not in limitations and "does not carry" not in limitations
    return handoff


def test_forge_handoff_enters_spark_forge(cross: CrossWorkspace) -> None:
    out, store = _run(cross.root, [DD_ENTRY, SPARK_CROSS], [
        _node("n1", "forge-doctor-data", "data.scan", "analyze"),
        _node("n2", "spark-forge-aws", "pyspark.static-analysis", "pyspark", "n1")])
    assert out.status == "ok"
    spark_run = _child(out, "n2")

    handoff = _assert_handoff_consumed(store, out.run_id, spark_run, "forge-doctor-data")
    assert verify_run_hashes(store, spark_run).divergences == []
    # Every item carries the producer's evidence id — provenance, not raw text.
    assert all(item.id for item in handoff.items)
    # Consumption left upstream-derived evidence on the specialist's result.
    consumed = [e["id"] for e in store.read(spark_run, "result")["evidence"]
                if e["id"].startswith("upstream:")]
    assert consumed


def test_forge_handoff_enters_api_forge(cross: CrossWorkspace) -> None:
    out, store = _run(cross.root, [DA_ENTRY, API_CROSS], [
        _node("n1", "forge-doctor-api", "api.diagnose", "analyze"),
        _node("n2", "api-forge", "api.analyze", "analyze", "n1")])
    assert out.status == "ok"
    api_run = _child(out, "n2")

    _assert_handoff_consumed(store, out.run_id, api_run, "forge-doctor-api")
    assert verify_run_hashes(store, api_run).divergences == []
    consumed = [e["id"] for e in store.read(api_run, "result")["evidence"]
                if e["id"].startswith("upstream:")]
    assert consumed


# --- 5/6. Specialist receipt -> The Forge -------------------------------------------------------


def test_spark_receipt_enters_the_forge(tmp_path: Path) -> None:
    (tmp_path / "jobs").mkdir()
    (tmp_path / "jobs" / "job.py").write_text("import pyspark\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("pyspark\n", encoding="utf-8")
    out, store = _run(tmp_path, [SPARK_ENTRY],
                      [_node("n1", "spark-forge-aws", "pyspark.static-analysis", "pyspark")])
    assert out.status == "ok"
    run_id = _child(out, "n1")

    receipt = from_dict(ExecutionReceipt, store.read(run_id, "receipt"), strict=True)
    # Supply-chain identity on record: executable fingerprint + versions + surface.
    assert receipt.provider is not None
    assert receipt.provider.fingerprint and receipt.provider.observed_version
    assert receipt.provider.manifest_sha256 and receipt.provider.surface_fingerprint
    assert verify_run_hashes(store, run_id).divergences == []
    report = build_explain_report(store, run_id)
    assert report.result is not None and report.result.status == "ok"


def test_api_receipt_enters_the_forge(tmp_path: Path) -> None:
    (tmp_path / "openapi.yaml").write_text("openapi: 3.0.0\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("import fastapi\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
    out, store = _run(tmp_path, [API_ENTRY],
                      [_node("n1", "api-forge", "api.analyze", "analyze")])
    assert out.status == "ok"
    run_id = _child(out, "n1")

    receipt = from_dict(ExecutionReceipt, store.read(run_id, "receipt"), strict=True)
    # The provider-native receipt (the apiforge case) crossed as a bounded pointer.
    assert receipt.provider_receipt is not None
    assert receipt.provider_receipt.ref.startswith("case:")
    assert receipt.provider_receipt.sha256
    assert verify_run_hashes(store, run_id).divergences == []


# --- 7. Final ecosystem proof (Phases 56-58) ----------------------------------------------------


def test_final_ecosystem_proof_chain(cross: CrossWorkspace) -> None:
    """The full mesh chain offline (specialist-replay): task -> complexity ->
    capability graph -> observe -> engineer -> verify -> synthesis ->
    receipts -> explain -> trace, for both domains at once."""
    out, store = _run(cross.root, [DD_ENTRY, DA_ENTRY, SPARK_CROSS, API_CROSS], [
        _node("n1", "forge-doctor-data", "data.scan", "analyze"),
        _node("n2", "spark-forge-aws", "pyspark.static-analysis", "pyspark", "n1"),
        _node("n3", "forge-doctor-api", "api.diagnose", "analyze"),
        _node("n4", "api-forge", "api.analyze", "analyze", "n3"),
    ])
    assert out.status == "ok"
    plan_run = out.run_id
    receipt = store.read(plan_run, "receipt")
    assert receipt["kind"] == "plan"

    # Task -> CapabilityGraph -> budget: every upstream artifact the chain
    # consumes is persisted and hash-bound (complexity is assessed only on
    # decomposed runs — a plan file fixes its profile, by design).
    refs = store.read(plan_run, "plan-result")
    assert refs is not None
    for name in ("task", "workspace-descriptor", "capability-graph",
                 "routing", "budget", "telemetry"):
        assert store.read_optional(plan_run, name) is not None, name

    runs = {n: _child(out, n) for n in ("n1", "n2", "n3", "n4")}

    # observe -> engineer: each engineer consumed its doctor's evidence.
    dd_handoff = _assert_handoff_consumed(store, plan_run, runs["n2"],
                                          "forge-doctor-data")
    da_handoff = _assert_handoff_consumed(store, plan_run, runs["n4"],
                                          "forge-doctor-api")
    assert dd_handoff.items and da_handoff.items

    # engineer -> verify: the independent verification of each engineer ran
    # against the OTHER domain's doctor (can_verify edges, declared).
    for nid, verifier_id in (("n2", "forge-doctor-data"),
                             ("n4", "forge-doctor-api")):
        verification = store.read_optional(runs[nid], "verification")
        assert verification is not None, nid
        basis = json.dumps(verification)
        assert f"verifier:{verifier_id}" in basis, (nid, verification)
        assert verification["independent"]["status"] == "passed", nid

    # receipts: every run carries provider identity + fingerprints; the whole
    # run set (plan + children + verifies) verifies byte-for-byte (Phase 58).
    for nid, run_id in runs.items():
        child = from_dict(ExecutionReceipt, store.read(run_id, "receipt"),
                          strict=True)
        assert child.parent_run == plan_run and child.plan_node == nid
        assert child.provider is not None
        assert child.provider.fingerprint and child.provider.manifest_sha256
        assert child.provider.surface_fingerprint
    for run_id in store.list_runs():
        assert verify_run_hashes(store, run_id).divergences == [], run_id

    # explain (Phase 57): every required section resolves on the plan run and
    # on each child — task, routing, plan, evidence, verification, trace.
    plan_report = build_explain_report(store, plan_run)
    assert plan_report.kind == "plan" and plan_report.plan is not None
    assert plan_report.plan.result is not None
    assert "plan" not in plan_report.not_recorded
    for nid, run_id in runs.items():
        report = build_explain_report(store, run_id)
        assert report.kind == "run" and report.result is not None
        assert report.parent_run == plan_run
        # trace: the run's spans exist and name the provider call.
        telemetry = report.telemetry or {}
        spans = [s["name"] for s in telemetry.get("spans", [])]
        assert any(name.startswith("provider:") for name in spans), (nid, spans)
