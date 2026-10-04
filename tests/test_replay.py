"""Replay: re-render, re-verify and re-execute of a persisted run, and every refusal of a
re-execute before any provider starts (cross-forge-foundation 6.3, requirement 14.5-14.9)."""

import json
from collections.abc import Iterator, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from cross_workspace import CrossWorkspace, mounted_cross_workspace
from helpers import API_PLAN_ENTRY, SPARK_PLAN_ENTRY, make_workspace, write_file
from theforge.contracts import ExecutionReceipt, ExecutionResult
from theforge.contracts.codes import Codes
from theforge.contracts.explain import Divergence
from theforge.contracts.plan import PlanResult
from theforge.errors import ReplayRefused, UsageError
from theforge.forger import AskRequest, Forger, PlanCommand, PlanExecutor, ReplayReport
from theforge.forger import replay as replay_module
from theforge.forger.replay import replay
from theforge.protocol import ProviderTransport, SubprocessTransport
from theforge.registry import Registry
from theforge.runs import RunStore

PROOF_TASK = "Projete um pipeline Spark que produza dados para uma API"
FIXED_AT = "2026-10-04T00:00:00Z"


class _Spy:
    """Transport factory recording every provider process the Forger starts."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, argv: Sequence[str]) -> ProviderTransport:
        self.calls.append(str(argv[-1]))
        return SubprocessTransport(argv)


def _forger(root: Path, entries: list[dict[str, Any]],
            spy: _Spy | None = None) -> tuple[Forger, RunStore]:
    forge = make_workspace(root, entries)
    store = RunStore(forge)
    kwargs: dict[str, Any] = {"transport_factory": spy} if spy is not None else {}
    return Forger(root, Registry(forge), store, **kwargs), store


def _echo(root: Path) -> tuple[Forger, RunStore, str, _Spy]:
    """An echo run (``reproducible``) and a Forger whose provider starts are spied."""
    forger, store = _forger(root, [])
    write_file(root, "notes.txt", "hello\n")
    out = forger.ask(AskRequest(intent="eco", capability="demo.echo"))
    assert out.status == "ok", out.error
    assert out.receipt.reproducibility is not None
    assert out.receipt.reproducibility.level == "reproducible"
    spy = _Spy()
    spied = Forger(root, Registry(root / ".forge", transport_factory=spy), store,
                   transport_factory=spy)
    return spied, store, out.run_id, spy


def _snapshot(store: RunStore, run_id: str) -> dict[str, bytes]:
    run_dir = store.run_dir(run_id)
    return {path.relative_to(run_dir).as_posix(): path.read_bytes()
            for path in sorted(run_dir.rglob("*")) if path.is_file()}


def _set_receipt(store: RunStore, run_id: str, **changes: Any) -> None:
    receipt = store.read_contract(run_id, "receipt", ExecutionReceipt)
    store.write(run_id, "receipt", replace(receipt, **changes))


def _refused(forger: Forger, store: RunStore, run_id: str) -> ReplayRefused:
    with pytest.raises(ReplayRefused) as caught:
        replay(forger, store, run_id, "execute")
    return caught.value


# --- modes ------------------------------------------------------------------------------------

def test_unknown_mode_and_unknown_run_are_rejected(tmp_path: Path) -> None:
    forger, store, run, spy = _echo(tmp_path)
    with pytest.raises(UsageError):
        replay(forger, store, run, "rerun")
    with pytest.raises(LookupError):
        replay(forger, store, "20000101T000000Z-00000000", "render")
    assert spy.calls == []


# --- render (14.6) ----------------------------------------------------------------------------

def test_render_reads_only_the_run_never_the_workspace_nor_providers(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    forger, store, run, spy = _echo(tmp_path)
    before = _snapshot(store, run)
    first = replay(forger, store, run, "render", created_at=FIXED_AT)

    (tmp_path / "notes.txt").unlink()  # the workspace content is gone

    def no_workspace(*_: Any) -> Any:
        raise AssertionError("render must not read the workspace")

    monkeypatch.setattr(replay_module, "reverify", no_workspace)
    second = replay(forger, store, run, "render", created_at=FIXED_AT)
    assert isinstance(second, ReplayReport) and second.mode == "render"
    assert second.report is not None and second.report == first.report
    assert second.report.run_id == run and second.report.created_at == FIXED_AT
    assert second.divergences == [] and second.new_run is None
    assert spy.calls == []
    assert _snapshot(store, run) == before


def test_render_carries_the_integrity_divergences(tmp_path: Path) -> None:
    forger, store, run, _ = _echo(tmp_path)
    path = store.run_dir(run) / "result.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["limitations"] = ["tampered"]
    path.write_text(json.dumps(data), encoding="utf-8")
    out = replay(forger, store, run, "render")
    assert [d.artifact for d in out.divergences] == ["result"]
    assert out.report is not None and out.report.integrity.divergences == out.divergences


# --- verify (14.7) ----------------------------------------------------------------------------

def test_verify_without_change_has_no_divergence_and_writes_nothing(tmp_path: Path) -> None:
    forger, store, run, spy = _echo(tmp_path)
    before = _snapshot(store, run)
    out = replay(forger, store, run, "verify")
    assert out.mode == "verify" and out.divergences == [] and out.report is None
    assert spy.calls == [] and _snapshot(store, run) == before


def test_verify_points_at_the_changed_and_the_deleted_context_file(tmp_path: Path) -> None:
    forger, store, run, spy = _echo(tmp_path)
    before = _snapshot(store, run)
    write_file(tmp_path, "notes.txt", "changed\n")
    out = replay(forger, store, run, "verify")
    assert out.divergences == [Divergence(artifact="workspace/notes.txt", kind="modified")]
    (tmp_path / "notes.txt").unlink()
    out = replay(forger, store, run, "verify")
    assert out.divergences == [Divergence(artifact="workspace/notes.txt", kind="missing")]
    assert spy.calls == [] and _snapshot(store, run) == before


def test_verify_combines_hash_and_context_divergences(tmp_path: Path) -> None:
    forger, store, run, _ = _echo(tmp_path)
    (store.run_dir(run) / "telemetry.json").unlink()
    write_file(tmp_path, "notes.txt", "changed\n")
    out = replay(forger, store, run, "verify")
    assert [(d.artifact, d.kind) for d in out.divergences] == [
        ("telemetry", "missing"), ("workspace/notes.txt", "modified")]


# --- execute (14.8) ---------------------------------------------------------------------------

def test_execute_creates_a_new_linked_run_with_the_same_result(tmp_path: Path) -> None:
    forger, store, run, spy = _echo(tmp_path)
    before = _snapshot(store, run)
    out = replay(forger, store, run, "execute")
    assert out.mode == "execute" and out.comparison == "same"
    assert out.new_run is not None and out.new_run != run
    new_receipt = store.read_contract(out.new_run, "receipt", ExecutionReceipt)
    assert new_receipt.replay_of == run and new_receipt.status == "ok"
    original = store.read_contract(run, "receipt", ExecutionReceipt)
    assert new_receipt.provider is not None and original.provider is not None
    assert new_receipt.provider.id == original.provider.id
    assert store.read(out.new_run, "routing")["selected"][0]["provider"] == "echo-forge"
    assert spy.calls  # the provider did run, for the new run only
    assert _snapshot(store, run) == before


def test_execute_reports_a_different_result(tmp_path: Path) -> None:
    forger, store, run, _ = _echo(tmp_path)
    result = store.read_contract(run, "result", ExecutionResult)
    store.write(run, "result", replace(result, unknowns=[*result.unknowns, "edited"]))
    out = replay(forger, store, run, "execute")
    assert out.comparison == "different"


def test_execute_without_an_original_result_is_no_result(tmp_path: Path) -> None:
    forger, store, run, _ = _echo(tmp_path)
    (store.run_dir(run) / "result.json").unlink()
    assert replay(forger, store, run, "execute").comparison == "no-result"


# --- refusals (14.9): nothing starts, the original stays intact -------------------------------

def test_unknown_reproducibility_is_refused(tmp_path: Path) -> None:
    forger, store, run, spy = _echo(tmp_path)
    _set_receipt(store, run, reproducibility=None)
    before = _snapshot(store, run)
    refused = _refused(forger, store, run)
    assert refused.code == Codes.REPLAY_NOT_REPRODUCIBLE
    assert refused.reasons == ("reproducibility is unknown (not recorded)",)
    assert spy.calls == [] and _snapshot(store, run) == before


def test_non_reproducible_run_is_refused_with_its_reasons(tmp_path: Path) -> None:
    forger, store, run, spy = _echo(tmp_path)
    receipt = store.read_contract(run, "receipt", ExecutionReceipt)
    assert receipt.reproducibility is not None
    _set_receipt(store, run, reproducibility=replace(
        receipt.reproducibility, level="non_reproducible", reasons=["requires network"]))
    refused = _refused(forger, store, run)
    assert refused.reasons == ("reproducibility is non_reproducible (requires network)",)
    assert spy.calls == []


def test_changed_context_is_refused(tmp_path: Path) -> None:
    forger, store, run, spy = _echo(tmp_path)
    before = _snapshot(store, run)
    write_file(tmp_path, "notes.txt", "changed\n")
    refused = _refused(forger, store, run)
    assert refused.code == Codes.REPLAY_NOT_REPRODUCIBLE
    assert refused.reasons == ("context changed: notes.txt",)
    assert spy.calls == [] and _snapshot(store, run) == before


def test_changed_provider_version_or_identity_is_refused(tmp_path: Path) -> None:
    forger, store, run, spy = _echo(tmp_path)
    receipt = store.read_contract(run, "receipt", ExecutionReceipt)
    assert receipt.provider is not None
    version = receipt.provider.version
    _set_receipt(store, run, provider=replace(receipt.provider, version="9.9.9",
                                              fingerprint="0" * 64))
    refused = _refused(forger, store, run)
    assert refused.code == Codes.REPLAY_NOT_REPRODUCIBLE
    assert refused.reasons == (
        f"provider echo-forge version changed: 9.9.9 -> {version}",
        "provider echo-forge identity changed (executable fingerprint)")
    assert spy.calls == []


def test_unregistered_provider_is_refused(tmp_path: Path) -> None:
    forger, store, run, spy = _echo(tmp_path)
    receipt = store.read_contract(run, "receipt", ExecutionReceipt)
    assert receipt.provider is not None
    _set_receipt(store, run, provider=replace(receipt.provider, id="ghost"))
    assert _refused(forger, store, run).reasons == ("provider ghost is no longer registered",)
    assert spy.calls == []


@pytest.fixture
def cross() -> Iterator[CrossWorkspace]:
    with mounted_cross_workspace(git=True) as workspace:
        yield workspace


def test_plan_and_plan_node_runs_are_unsupported(cross: CrossWorkspace) -> None:
    forger, store = _forger(cross.root, [SPARK_PLAN_ENTRY, API_PLAN_ENTRY])
    out = PlanExecutor(forger).run(PlanCommand(intent=PROOF_TASK, profile="max",
                                               execute=True))
    assert out.status == "ok", out.error
    node_run = store.read_contract(out.run_id, "plan-result", PlanResult).nodes[0].run_id
    assert node_run is not None
    spy = _Spy()
    spied = Forger(cross.root, Registry(cross.root / ".forge", transport_factory=spy), store,
                   transport_factory=spy)
    before = {run: _snapshot(store, run) for run in (out.run_id, node_run)}
    for run in (out.run_id, node_run):
        refused = _refused(spied, store, run)
        assert refused.code == Codes.REPLAY_UNSUPPORTED, run
    assert spy.calls == []
    assert {run: _snapshot(store, run) for run in before} == before
    # verify follows the plan's node runs and their context, read-only
    assert replay(spied, store, out.run_id, "verify").divergences == []
    assert spy.calls == []
