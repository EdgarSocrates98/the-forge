"""HashCheck: every hash recorded in a receipt against the artifact on disk, the provider
artifacts under ``work/`` and, for plan runs, the node runs (cross-forge-foundation 6.1)."""

import hashlib
import json
import subprocess
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from cross_workspace import CrossWorkspace, mounted_cross_workspace
from helpers import API_PLAN_ENTRY, SPARK_PLAN_ENTRY, bad_entry, make_workspace, write_file
from theforge.contracts import ExecutionReceipt, ExecutionResult
from theforge.contracts.explain import Divergence, IntegrityReport
from theforge.contracts.plan import PlanResult
from theforge.contracts.result import Artifact
from theforge.explain import verify_run_hashes
from theforge.forger import AskRequest, Forger, PlanCommand, PlanExecutor
from theforge.registry import Registry
from theforge.runs import RunStore

PROOF_TASK = "Projete um pipeline Spark que produza dados para uma API"


def _forger(root: Path, entries: list[dict[str, Any]]) -> tuple[Forger, RunStore]:
    forge = make_workspace(root, entries)
    store = RunStore(forge)
    return Forger(root, Registry(forge), store), store


def _echo_run(root: Path) -> tuple[RunStore, str]:
    forger, store = _forger(root, [])
    write_file(root, "notes.txt", "hello\n")
    out = forger.ask(AskRequest(intent="eco", capability="demo.echo"))
    assert out.status == "ok", out.error
    return store, out.run_id


def _with_artifact(store: RunStore, run_id: str, rel: str, content: bytes) -> None:
    """Make the run declare ``rel`` (written under work/) as a provider artifact."""
    path = store.work_dir(run_id) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    result = store.read_contract(run_id, "result", ExecutionResult)
    artifact = Artifact(path=rel, sha256=hashlib.sha256(content).hexdigest())
    result_sha = store.write(run_id, "result", replace(result, artifacts=[artifact]))
    receipt = store.read_contract(run_id, "receipt", ExecutionReceipt)
    store.write(run_id, "receipt", replace(receipt, result_sha256=result_sha))


def _rewrite(store: RunStore, run_id: str, name: str, change: Any) -> None:
    path = store.run_dir(run_id) / f"{name}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _snapshot(directory: Path) -> dict[str, tuple[bytes, int]]:
    return {str(p.relative_to(directory)): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in sorted(directory.rglob("*")) if p.is_file()}


@pytest.fixture
def cross() -> Iterator[CrossWorkspace]:
    with mounted_cross_workspace(git=True) as workspace:
        yield workspace


def test_untouched_run_has_no_divergence_and_checks_every_recorded_hash(
        tmp_path: Path) -> None:
    store, run = _echo_run(tmp_path)
    report = verify_run_hashes(store, run)
    assert isinstance(report, IntegrityReport)
    assert report.divergences == [] and report.unrecorded == []
    for name in ("task", "routing", "context", "result", "telemetry", "verification"):
        assert name in report.checked


def test_altered_result_is_modified(tmp_path: Path) -> None:
    store, run = _echo_run(tmp_path)
    expected = store.persisted_sha256(run, "result")
    _rewrite(store, run, "result", lambda d: d.update(status="partial"))
    report = verify_run_hashes(store, run)
    assert report.divergences == [Divergence(artifact="result", kind="modified",
                                             expected=expected,
                                             actual=store.persisted_sha256(run, "result"))]


def test_deleted_context_is_missing(tmp_path: Path) -> None:
    store, run = _echo_run(tmp_path)
    expected = store.persisted_sha256(run, "context")
    (store.run_dir(run) / "context.json").unlink()
    report = verify_run_hashes(store, run)
    assert report.divergences == [Divergence(artifact="context", kind="missing",
                                             expected=expected)]


def test_corrupted_telemetry_is_unreadable(tmp_path: Path) -> None:
    store, run = _echo_run(tmp_path)
    expected = store.persisted_sha256(run, "telemetry")
    (store.run_dir(run) / "telemetry.json").write_text("{not json", encoding="utf-8")
    report = verify_run_hashes(store, run)
    assert report.divergences == [Divergence(artifact="telemetry", kind="unreadable",
                                             expected=expected)]


def test_missing_and_unreadable_receipt(tmp_path: Path) -> None:
    store, run = _echo_run(tmp_path)
    receipt = store.run_dir(run) / "receipt.json"
    receipt.write_text("[]", encoding="utf-8")
    assert verify_run_hashes(store, run).divergences == [
        Divergence(artifact="receipt", kind="unreadable")]
    receipt.unlink()
    assert verify_run_hashes(store, run) == IntegrityReport(
        divergences=[Divergence(artifact="receipt", kind="missing")])


def test_provider_artifact_altered_or_deleted_under_work(tmp_path: Path) -> None:
    store, run = _echo_run(tmp_path)
    _with_artifact(store, run, "out/report.txt", b"rows: 3\n")
    report = verify_run_hashes(store, run)
    assert report.divergences == [] and "work/out/report.txt" in report.checked

    expected = hashlib.sha256(b"rows: 3\n").hexdigest()
    (store.work_dir(run) / "out/report.txt").write_bytes(b"rows: 4\n")
    assert verify_run_hashes(store, run).divergences == [
        Divergence(artifact="work/out/report.txt", kind="modified", expected=expected,
                   actual=hashlib.sha256(b"rows: 4\n").hexdigest())]

    (store.work_dir(run) / "out/report.txt").unlink()
    assert verify_run_hashes(store, run).divergences == [
        Divergence(artifact="work/out/report.txt", kind="missing", expected=expected)]


def test_artifact_path_escaping_work_is_missing_and_never_read(tmp_path: Path) -> None:
    store, run = _echo_run(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"secret")
    sha = hashlib.sha256(b"secret").hexdigest()
    result = store.read_contract(run, "result", ExecutionResult)
    escaping = ["../../../../outside.txt", str(outside)]
    result_sha = store.write(run, "result", replace(
        result, artifacts=[Artifact(path=p, sha256=sha) for p in escaping]))
    receipt = store.read_contract(run, "receipt", ExecutionReceipt)
    store.write(run, "receipt", replace(receipt, result_sha256=result_sha))
    assert verify_run_hashes(store, run).divergences == [
        Divergence(artifact=f"work/{p}", kind="missing", expected=sha) for p in escaping]


def test_tampering_provider_artifact_is_a_divergence(tmp_path: Path) -> None:
    forger, store = _forger(tmp_path, [bad_entry("artifact-tamper", "bad-t")])
    out = forger.ask(AskRequest(intent="run it", capability="bad.thing"))
    assert out.status == "partial"
    kinds = [(d.artifact, d.kind) for d in verify_run_hashes(store, out.run_id).divergences]
    assert kinds == [("work/out/report.txt", "modified")]


def test_run_written_before_the_hashes_existed_has_no_divergence(tmp_path: Path) -> None:
    store, run = _echo_run(tmp_path)

    def older(data: dict[str, Any]) -> None:
        for key in ("telemetry_sha256", "verification_sha256", "reproducibility"):
            data.pop(key, None)

    _rewrite(store, run, "receipt", older)
    store.read_contract(run, "receipt", ExecutionReceipt)  # still a valid receipt
    report = verify_run_hashes(store, run)
    assert report.divergences == []
    assert report.unrecorded == ["verification", "telemetry"]
    assert "telemetry" not in report.checked and "result" in report.checked


def test_verification_writes_nothing_and_starts_no_provider(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store, run = _echo_run(tmp_path)
    _with_artifact(store, run, "out/report.txt", b"rows: 3\n")
    (store.run_dir(run) / "context.json").unlink()
    before = _snapshot(store.runs_dir)

    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("hash verification must never start a process")

    monkeypatch.setattr(subprocess, "Popen", refuse)
    assert verify_run_hashes(store, run).divergences
    assert _snapshot(store.runs_dir) == before


def _plan_run(root: Path) -> tuple[RunStore, str, PlanResult]:
    forger, store = _forger(root, [SPARK_PLAN_ENTRY, API_PLAN_ENTRY])
    out = PlanExecutor(forger).run(PlanCommand(intent=PROOF_TASK, profile="max",
                                               execute=True))
    assert out.status == "ok", out.error
    return store, out.run_id, store.read_contract(out.run_id, "plan-result", PlanResult)


def test_plan_run_checks_its_refs_telemetry_and_every_node_run(
        cross: CrossWorkspace) -> None:
    store, plan_run, result = _plan_run(cross.root)
    nodes = [n.run_id for n in result.nodes]
    assert all(nodes)
    before = _snapshot(store.runs_dir)
    report = verify_run_hashes(store, plan_run)
    assert report.divergences == [] and report.unrecorded == []
    for name in ("task", "workspace-descriptor", "plan", "graph", "plan-result",
                 "telemetry"):
        assert name in report.checked
    for child in nodes:
        for name in ("receipt", "result", "verification", "telemetry"):
            assert f"{child}/{name}" in report.checked
    assert _snapshot(store.runs_dir) == before


def test_plan_run_detects_an_altered_node_receipt_and_plan_telemetry(
        cross: CrossWorkspace) -> None:
    store, plan_run, result = _plan_run(cross.root)
    child = result.nodes[0].run_id
    assert child is not None
    _rewrite(store, child, "receipt", lambda d: d.update(limitations=["forged"]))
    _rewrite(store, plan_run, "telemetry", lambda d: d.update(run_id="forged"))
    report = verify_run_hashes(store, plan_run)
    assert [(d.artifact, d.kind) for d in report.divergences] == [
        ("telemetry", "modified"), (f"{child}/receipt", "modified")]
    receipt = next(d for d in report.divergences if d.artifact == f"{child}/receipt")
    assert receipt.expected == result.nodes[0].receipt_sha256
    assert receipt.actual == store.persisted_sha256(child, "receipt")


def test_plan_run_reports_a_deleted_node_run(cross: CrossWorkspace) -> None:
    store, plan_run, result = _plan_run(cross.root)
    child = result.nodes[1].run_id
    assert child is not None
    (store.run_dir(child) / "receipt.json").unlink()
    report = verify_run_hashes(store, plan_run)
    assert report.divergences == [Divergence(artifact=f"{child}/receipt", kind="missing",
                                             expected=result.nodes[1].receipt_sha256)]
