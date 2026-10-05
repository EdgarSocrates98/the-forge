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
least one item that originates in the Spark Forge with its original epistemic status, the plan
ends ``ok`` or ``partial`` with a synthesis referencing both node runs, and ``theforge explain``
of the plan run reports no divergence (exit 0).

It also checks the replay scenarios owned by this spec against the live outputs (top-level keys
of the API Forge case files of the hand-built recording, native id formats of both Forges), the
live counterpart of the drift checks of ``test_real_providers.py``.
"""

import json
import re
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from typing import Any

import pytest

import real_providers as rp
from cross_workspace import CrossWorkspace, mounted_cross_workspace
from theforge.cli.main import main
from theforge.contracts import ExecutionReceipt, ExecutionResult
from theforge.contracts.plan import ExecutionPlan, PlanResult
from theforge.runs import RunStore
from theforge.state import init_workspace

PROOF_TASK = "Projete um pipeline Spark que produza dados para uma API"
EXPECTED_NODES = [("n1", "spark-forge", "pyspark.static-analysis", "pyspark"),
                  ("n2", "api-forge", "api.analyze", "analyze")]
NATIVE = Path(__file__).parent / "fixtures" / "native"
API_RECORDING = NATIVE / "apiforge" / "scenarios" / "cross" / "api.analyze.analyze.json"
NATIVE_ID = {"spark-forge": re.compile(r"f_[0-9a-f]{6}"),
             "api-forge": re.compile(r"fact:[0-9a-f]{16}")}


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
        user_config_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
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
    drift = {name: (sorted(recorded[name]), sorted(live[name])) for name in recorded
             if sorted(recorded[name]) != sorted(live[name])}
    assert drift == {}, f"{API_RECORDING.name}: top-level keys drifted {drift}"
