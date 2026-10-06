"""Cross-forge proof with the real Spark Forge and API Forge (cross-forge-foundation 8.3).

Marker ``real_provider`` (excluded from the default selection, collected by ``python -m pytest
-m real_provider`` as run by the scheduled real-provider workflow). It uses the Wave B
environment contract of ``real_providers.py``: without ``THEFORGE_REAL_SPARKFORGE_PYTHON`` /
``THEFORGE_REAL_APIFORGE_PYTHON`` naming interpreters with the adapter and the specialist the
test skips with the reason, or fails when ``THEFORGE_REAL_PROVIDERS_REQUIRED=1``. See
``docs/real-providers.md``.

Both real adapters are registered in the test's isolated user ``providers.toml`` (``id``/
``argv``/``trust`` only) and the proof task runs through the CLI, ``theforge plan --profile max
--execute``, on the mounted ``cross`` workspace (one git repository per directory): the plan is
``spark-forge/pyspark.static-analysis`` -> ``api-forge/api.analyze``, the API node receives at
least one item that originates in the Spark Forge with its original epistemic status and —
because ``api.analyze`` declares ``accepts_handoff`` — consumes them through the specialist's
upstream-facts intake, surfacing them as ``upstream:<id>`` evidence whose ``derived_from``
names the Spark node run; the plan ends ``ok`` or ``partial`` with a synthesis referencing
both node runs, and ``theforge explain`` of the plan run reports no divergence (exit 0).

It also runs the mandatory handoff A/B proof: the persisted ``context`` and ``handoff`` of the
API node's run feed the real adapter's ``execute`` twice — once with the handoff, once without —
and the two results must differ observably (upstream-derived evidence only in the first).

Finally it checks the replay scenarios owned by this spec against the live outputs (top-level
keys and native id formats of the API Forge case files of the hand-built recording; the Spark
Forge recording re-executed live on the same workspace), the live counterpart of the drift
checks of ``test_real_providers.py``.
"""

import json
import re
import subprocess
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from typing import Any

import pytest

import real_providers as rp
from cross_workspace import CrossWorkspace, mounted_cross_workspace
from theforge.cli.main import main
from theforge.contracts import PROTOCOL_V1, ExecutionReceipt, ExecutionResult
from theforge.contracts.budget import RunBudget
from theforge.contracts.capability_graph import CapabilityGraph
from theforge.contracts.complexity import ComplexityAssessment
from theforge.contracts.plan import ExecutionPlan, PlanResult
from theforge.contracts.verification import VerificationResult
from theforge.runs import RunStore
from theforge.state import init_workspace

PROOF_TASK = "Projete um pipeline Spark que produza dados para uma API"
EXPECTED_NODES = [("n1", "spark-forge", "pyspark.static-analysis", "pyspark"),
                  ("n2", "api-forge", "api.analyze", "analyze")]
NATIVE = Path(__file__).parent / "fixtures" / "native"
API_RECORDING = NATIVE / "apiforge" / "scenarios" / "cross" / "api.analyze.analyze.json"
SPARK_RECORDING = (NATIVE / "sparkforge" / "scenarios" / "cross"
                   / "pyspark.static-analysis.pyspark.json")
NATIVE_ID = {"spark-forge": re.compile(r"f_[0-9a-f]{6}"),
             "api-forge": re.compile(r"(?:fact|upstream):[0-9a-f]{16}")}


@pytest.fixture
def forges() -> tuple[rp.RealForge, rp.RealForge]:
    return rp.require_forge("spark"), rp.require_forge("api")


@pytest.fixture
def cross() -> Iterator[CrossWorkspace]:
    with mounted_cross_workspace(git=True) as workspace:
        yield workspace


def _cli(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, Any, str]:
    code = main(list(argv))
    out, err = capsys.readouterr()
    return code, json.loads(out) if out.strip() else None, err


def test_proof_task_runs_across_the_real_spark_forge_and_api_forge(
        forges: tuple[rp.RealForge, rp.RealForge], cross: CrossWorkspace,
        user_config_dir: Path, tmp_path: Path,
        capsys: pytest.CaptureFixture[str]) -> None:
    spark, api = forges
    init_workspace(cross.root)
    rp.register(user_config_dir, spark.entry(), api.entry())
    root = str(cross.root)

    code, data, err = _cli(capsys, "plan", PROOF_TASK, "--profile", "max", "--execute",
                           "--root", root, "--json")
    assert data is not None, err
    assert data["status"] in ("ok", "partial"), (data["status"], data["error"], err)
    assert code == 0, err
    plan_run = data["run_id"]
    store = RunStore(cross.root / ".forge")

    # Decomposition into the data node then the API node (6.1).
    plan = store.read_contract(plan_run, "plan", ExecutionPlan)
    assert [(n.id, n.provider, n.capability, n.action) for n in plan.nodes] == EXPECTED_NODES
    result = store.read_contract(plan_run, "plan-result", PlanResult)
    assert result.order == ["n1", "n2"]
    n1, n2 = result.nodes
    assert n1.status in ("ok", "partial") and n2.status in ("ok", "partial"), result.nodes
    assert n1.run_id is not None and n2.run_id is not None
    for outcome, provider in ((n1, "spark-forge"), (n2, "api-forge")):
        assert outcome.run_id is not None
        receipt =store.read_contract(outcome.run_id, "receipt", ExecutionReceipt)
        assert receipt.parent_run == plan_run and receipt.plan_node == outcome.node
        assert receipt.provider is not None and receipt.provider.id == provider

    # The API node received Spark Forge items with their original epistemic status (6.2).
    source = {e.id: e for e in store.read_contract(n1.run_id, "result", ExecutionResult)
              .evidence}
    handoff = store.read(n2.run_id, "handoff")
    from_spark = [item for item in handoff["items"]
                  if item["origin"]["provider"]["id"] == "spark-forge"
                  and item["origin"]["run_id"] == n1.run_id]
    assert from_spark, handoff
    evidence = [item for item in from_spark if item["kind"] == "evidence"]
    assert evidence, from_spark
    for item in evidence:
        assert item["id"] in source and item["epistemic"] == source[item["id"]].epistemic

    # api.analyze declares accepts_handoff: the handoff is consumed, not only delivered.
    receipt = store.read_contract(n2.run_id, "receipt", ExecutionReceipt)
    assert not [n for n in receipt.limitations if n.startswith("handoff-use-undeclared")]
    consumed = [e for e in store.read_contract(n2.run_id, "result", ExecutionResult).evidence
                if e.derived_from is not None]
    handed = {item["id"]: item for item in handoff["items"]}
    assert consumed and {e.derived_from.item for e in consumed
                         if e.derived_from is not None} == set(handed)
    for entry in consumed:
        origin = entry.derived_from
        assert origin is not None
        assert (origin.provider, origin.node, origin.run_id, origin.plan_run) == (
            "spark-forge", "n1", n1.run_id, plan_run)
        item = handed[origin.item]
        if item.get("epistemic") is not None:  # the epistemic status survives verbatim
            assert entry.epistemic == item["epistemic"]
    verification = store.read(n2.run_id, "verification")
    assert verification["forge"]["status"] == "passed"
    assert [d for d in verification["forge"]["details"]
            if d.startswith("handoff-provenance: passed")]

    # The synthesis references both node runs, with the specialists' native evidence ids.
    synthesis = result.synthesis
    assert [(s.node, s.provider, s.run_id) for s in synthesis.nodes] == [
        ("n1", "spark-forge", n1.run_id), ("n2", "api-forge", n2.run_id)]
    assert [(h.source, h.target) for h in synthesis.handoffs] == [("n1", "n2")]
    for node in synthesis.nodes:
        assert node.run_id is not None
        ids = [e.id for e in store.read_contract(node.run_id, "result", ExecutionResult)
               .evidence]
        assert ids and all(NATIVE_ID[node.provider].fullmatch(i) for i in ids), ids

    # explain of the plan run: no divergence, exit 0.
    code, report, err = _cli(capsys, "explain", plan_run, "--root", root, "--json")
    assert code == 0, err
    assert report["kind"] == "plan" and report["integrity"]["divergences"] == []

    # --- Cycle 3 reality chain (wave X): structured verification on the real
    # provider run, plus the wave J/Q observability surfaces answering on it.
    verified = store.read_contract(n2.run_id, "verification", VerificationResult)
    assert verified.forge.status == "passed"
    if verified.independent.status == "passed":
        # Independent verification (wave G) may only rest on a verifier other
        # than the provider it checked.
        assert [b for b in verified.independent.basis
                if b.startswith("verifier:") and "api-forge" not in b]

    # trace of a real provider run: the span tree exists and is non-empty.
    code, trace, err = _cli(capsys, "trace", n2.run_id, "--root", root, "--json")
    assert code == 0, err
    assert trace["spans"], trace

    # The registry+workspace capability graph answers read-only on the mounted
    # workspace: both real providers and both used capabilities are visible.
    code, graph_data, err = _cli(capsys, "graph", "--root", root, "--json")
    assert code == 0, err
    listed = {node["id"] for node in graph_data["nodes"]}
    assert "capability:spark-forge/pyspark.static-analysis" in listed
    assert "capability:api-forge/api.analyze" in listed
    assert graph_data["edges"]

    # The measured branch of the chain: --profile auto is the path where the
    # complexity engine assesses the task (a pinned profile legitimately skips
    # the measurement). The plan run it produces must persist the assessment,
    # the capability graph it planned over and the resolved budget — and the
    # human explain must render the measured "why".
    code, auto_plan, err = _cli(capsys, "plan", PROOF_TASK, "--profile", "auto",
                                "--root", root, "--json")
    assert code == 0 and auto_plan["status"] == "planned", (auto_plan, err)
    auto_run = auto_plan["run_id"]
    complexity = store.read_contract(auto_run, "complexity", ComplexityAssessment)
    assert complexity.requested_profile == "auto"
    assert complexity.profile_reason.strip()
    assert 0.0 <= complexity.confidence <= 1.0
    budget = store.read_contract(auto_run, "budget", RunBudget)
    assert budget.profile == complexity.selected_profile
    capability_graph = store.read_contract(
        auto_run, "capability-graph", CapabilityGraph)
    node_ids = {node.id for node in capability_graph.nodes}
    for provider, capability in (("spark-forge", "pyspark.static-analysis"),
                                 ("api-forge", "api.analyze")):
        assert f"provider:{provider}" in node_ids
        assert f"capability:{provider}/{capability}" in node_ids
    code = main(["explain", auto_run, "--root", root])
    out, err = capsys.readouterr()
    assert code == 0, err
    assert "Complexity:" in out, out

    # Live counterpart of the hand-built API Forge cross recording (drift of its shape).
    recorded = json.loads(API_RECORDING.read_text(encoding="utf-8"))["case_files"]
    work = store.work_dir(n2.run_id)
    live: dict[str, Any] = {}
    for artifact in store.read_contract(n2.run_id, "result", ExecutionResult).artifacts:
        path = PurePosixPath(artifact.path)
        if path.parts[0] == "case" and path.suffix == ".json":
            live[path.relative_to("case").as_posix()] = json.loads(
                (work / artifact.path).read_text(encoding="utf-8"))
    assert sorted(live) == sorted(recorded)
    drift = {name: (rp.top_keys(recorded[name]), rp.top_keys(live[name]))
             for name in recorded if rp.top_keys(recorded[name]) != rp.top_keys(live[name])}
    assert drift == {}, f"{API_RECORDING.name}: top-level keys drifted {drift}"
    id_drift = {name: (sorted(rp.id_shapes(recorded[name])), sorted(rp.id_shapes(live[name])))
                for name in recorded
                if rp.id_shapes(recorded[name]) != rp.id_shapes(live[name])}
    assert id_drift == {}, f"{API_RECORDING.name}: id formats drifted {id_drift}"

    # A/B (6.3): the very execute request of n2, replayed live against the real adapter
    # once with its handoff and once without. The outputs must differ observably: only the
    # first carries upstream-derived evidence and the persisted upstream facts.
    context = store.read(n2.run_id, "context")
    payload = {"task": {"intent": PROOF_TASK, "budget_profile": "max"},
               "capability": "api.analyze", "action": "analyze", "context": context,
               "handoff": handoff}
    with_upstream = _adapter_execute(api, payload, tmp_path / "ab" / "with")
    without = _adapter_execute(api, {k: v for k, v in payload.items() if k != "handoff"},
                                 tmp_path / "ab" / "without")
    assert with_upstream["status"] in ("ok", "partial"), with_upstream
    assert without["status"] in ("ok", "partial"), without
    derived = [e for e in with_upstream["payload"]["evidence"] if e.get("derived_from")]
    assert derived and {e["derived_from"]["item"] for e in derived} == set(handed)
    assert [e for e in without["payload"]["evidence"] if e.get("derived_from")] == []
    assert len(with_upstream["payload"]["evidence"]) > len(without["payload"]["evidence"])
    for expected in (True, False):
        persisted = json.loads(
            (tmp_path / "ab" / ("with" if expected else "without") / "case" / "facts.json")
            .read_text(encoding="utf-8"))
        upstream_facts = [f for f in persisted["facts"]
                          if f["source"].get("extractor") == "theforge/handoff"]
        assert bool(upstream_facts) is expected

    # The execute recorder produces the same fixture the live run produced: n2's own
    # persisted handoff drives --upstream, and the recorded case matches the scenario's
    # shapes (top-level keys and native id formats).
    handoff_path = store.run_dir(n2.run_id) / "handoff.json"
    out_dir = tmp_path / "recorded"
    rp.run_native([str(api.python), "-m", "theforge_apiforge.record_execute",
                   "--workspace", str(cross.root), "--capability", "api.analyze",
                   "--action", "analyze", "--arg", "contract=orders-api/openapi.yaml",
                   "--arg", "project=orders-api", "--handoff", str(handoff_path),
                   "--out", str(out_dir)], tmp_path)
    rerecorded = json.loads((out_dir / API_RECORDING.name).read_text(encoding="utf-8"))
    assert rerecorded["provenance"] == "recorded"
    assert rerecorded["argv"][-2:] == ["--upstream", "upstream-facts.json"]
    assert sorted(rerecorded["case_files"]) == sorted(recorded)
    drift = {name: (rp.top_keys(recorded[name]), rp.top_keys(rerecorded["case_files"][name]))
             for name in recorded
             if rp.top_keys(recorded[name]) != rp.top_keys(rerecorded["case_files"][name])}
    assert drift == {}, f"re-recorded {API_RECORDING.name}: top-level keys drifted {drift}"
    id_drift = {name: (sorted(rp.id_shapes(recorded[name])),
                       sorted(rp.id_shapes(rerecorded["case_files"][name])))
                for name in recorded
                if rp.id_shapes(recorded[name])
                != rp.id_shapes(rerecorded["case_files"][name])}
    assert id_drift == {}, f"re-recorded {API_RECORDING.name}: id formats drifted {id_drift}"


def _adapter_execute(forge: rp.RealForge, payload: dict[str, Any], cwd: Path
                     ) -> dict[str, Any]:
    """One ``execute`` request against the real API Forge adapter, as the core sends it."""
    cwd.mkdir(parents=True, exist_ok=True)
    request = json.dumps({"protocol": PROTOCOL_V1, "kind": "Request", "op": "execute",
                          "request_id": "req-ab", "payload": payload})
    proc = subprocess.run([*forge.argv(), "execute"], input=request, capture_output=True,
                          text=True, encoding="utf-8", timeout=rp.NATIVE_TIMEOUT,
                          cwd=cwd, env=rp.safe_env(), check=False)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_spark_cross_recording_matches_the_live_native_output(
        forges: tuple[rp.RealForge, rp.RealForge], cross: CrossWorkspace,
        tmp_path: Path) -> None:
    """The Spark Forge half of the cross recording, re-executed live on the mounted
    workspace: same tool, same arguments, same output and judge shapes and id formats as
    the replay recording (the ``spark`` counterpart of the API case-file check above)."""
    spark, _api = forges
    recorded = json.loads(SPARK_RECORDING.read_text(encoding="utf-8"))
    out = tmp_path / "live"
    argv = [str(spark.python), "-m", "theforge_sparkforge.record_execute",
            "--workspace", str(cross.root), "--capability", "pyspark.static-analysis",
            "--action", "pyspark", "--out", str(out)]
    argv += [f"--arg={name}={value}" for name, value in recorded["arguments"].items()
             if name not in ("detail_level", "limit")]
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    rp.run_native(argv, scratch)
    live = json.loads((out / SPARK_RECORDING.name).read_text(encoding="utf-8"))
    assert rp.left_in(scratch) == set()
    assert live["tool"] == recorded["tool"] and live["arguments"] == recorded["arguments"]
    pairs = {
        "recording": (recorded, live),
        "output": (recorded["output"], live["output"]),
        "judge": (recorded["judge"], live["judge"]),
        "judge.output": (recorded["judge"]["output"], live["judge"]["output"]),
    }
    drift = {name: (rp.top_keys(old), rp.top_keys(new)) for name, (old, new) in pairs.items()
             if rp.top_keys(old) != rp.top_keys(new)}
    assert drift == {}, f"{SPARK_RECORDING.name}: top-level keys drifted {drift}"
    id_drift = {name: (sorted(rp.id_shapes(old)), sorted(rp.id_shapes(new)))
                for name, (old, new) in pairs.items()
                if rp.id_shapes(old) != rp.id_shapes(new)}
    assert id_drift == {}, f"{SPARK_RECORDING.name}: id formats drifted {id_drift}"
