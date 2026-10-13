"""Cycle 2.1 wave C: the terminal-receipt invariant and verification preservation.

One run -> at most one terminalization path -> one authoritative receipt. ``_finish``
moves a trace ``open -> finalizing -> finalized`` exactly once; re-entry is a controlled
``PERSIST_WRITE``, never a second receipt. And a run whose provider executed keeps its
``VerificationResult`` even when the core fails afterwards — checks that never ran are
``not_performed``, never invented.
"""

from pathlib import Path
from typing import Any

import pytest

from helpers import SPARK_ENTRY, bad_entry, case_a, make_workspace
from theforge.contracts import (
    ContractError,
    ExecutionReceipt,
    TaskSpec,
    VerificationResult,
)
from theforge.contracts.canonical import sha256_of, utc_now
from theforge.contracts.codes import Codes
from theforge.errors import PersistenceError
from theforge.forger import AskRequest, Forger, PlanCommand, PlanExecutor
from theforge.forger.orchestrator import _Trace
from theforge.forger.telemetry import TelemetryRecorder
from theforge.meta import PRODUCER
from theforge.profiles import profile_for
from theforge.registry import Registry
from theforge.runs import RunStore, new_run_id


def _forger(root: Path, store: RunStore | None = None) -> tuple[Forger, RunStore]:
    forge = root / ".forge"
    store = store if store is not None else RunStore(forge)
    return Forger(root, Registry(forge), store), store


def _trace(store: RunStore) -> _Trace:
    """A minimal open trace: task persisted, nothing else ran yet."""
    run_id = new_run_id()
    store.create(run_id)
    task = TaskSpec(
        producer=PRODUCER, created_at=utc_now(), id=run_id, intent="x", workspace_root="/ws"
    )
    return _Trace(
        run_id=run_id,
        started_at=utc_now(),
        task=task,
        telemetry=TelemetryRecorder(run_id, profile_for("balanced")),
        task_sha=store.write(run_id, "task", task),
        request=AskRequest(intent="x"),
    )


def test_finish_terminalizes_exactly_once(tmp_path: Path) -> None:
    """``_finish`` on a non-open trace is refused: the first receipt stands alone."""
    forger, store = _forger(tmp_path)
    trace = _trace(store)
    forger._finish(trace, Forger._placeholder(trace.run_id, "first"), "no_route")
    receipt_sha = store.persisted_sha256(trace.run_id, "receipt")
    assert store.read(trace.run_id, "receipt")["status"] == "no_route"
    assert trace.terminal == "finalized"
    for state in ("finalizing", "finalized"):
        trace.terminal = state
        with pytest.raises(PersistenceError, match=f"_finish called on a {state} run"):
            forger._finish(trace, Forger._placeholder(trace.run_id, "second"), "refused")
    assert store.read(trace.run_id, "receipt")["status"] == "no_route"
    assert store.persisted_sha256(trace.run_id, "receipt") == receipt_sha


def test_receipt_write_failure_is_terminal_not_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A contract-level failure inside ``_finish`` never loops into a second attempt."""
    make_workspace(tmp_path, [])
    forger, store = _forger(tmp_path)
    attempts = 0
    real_write = store.write

    def write(run_id: str, name: str, contract: Any) -> str:
        nonlocal attempts
        if name == "receipt":
            attempts += 1
            raise ContractError("receipt would not validate")
        return real_write(run_id, name, contract)

    monkeypatch.setattr(store, "write", write)
    with pytest.raises(PersistenceError, match="terminalization failed"):
        forger.ask(AskRequest(intent="eco", capability="demo.echo"))
    assert attempts == 1  # no second _finish, ever


def test_persistence_failure_leaves_no_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A receipt that cannot be persisted means no receipt — the error propagates once."""
    make_workspace(tmp_path, [])
    forger, store = _forger(tmp_path)
    real_write = store.write

    def write(run_id: str, name: str, contract: Any) -> str:
        if name == "receipt":
            raise PersistenceError(f"disk full: {name}")
        return real_write(run_id, name, contract)

    monkeypatch.setattr(store, "write", write)
    with pytest.raises(PersistenceError, match="disk full"):
        forger.ask(AskRequest(intent="eco", capability="demo.echo"))
    (run_id,) = store.list_runs()
    assert store.read_optional(run_id, "receipt") is None


def test_internal_error_before_execute_writes_no_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No provider ever ran: failing the run must not invent a verification artifact."""
    make_workspace(tmp_path, [])

    def boom(*_: Any, **__: Any) -> Any:
        raise RuntimeError("scan blew up")

    monkeypatch.setattr("theforge.forger.orchestrator.scan_workspace", boom)
    forger, store = _forger(tmp_path)
    out = forger.ask(AskRequest(intent="eco", capability="demo.echo", debug=True))
    assert out.status == "provider_failure"
    assert out.error is not None and out.error.code == Codes.INTERNAL
    assert store.read_optional(out.run_id, "verification") is None
    assert store.read(out.run_id, "receipt")["status"] == "provider_failure"
    diagnostic = store.read_optional(out.run_id, "diagnostic")
    assert diagnostic is not None and diagnostic["stage"] == "scan"


def test_internal_error_after_execute_preserves_the_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The provider answered and the result was validated; the drift check then crashed.

    The run still records its VerificationResult: self-report and evidence reported,
    forge checks that ran passed, context re-verification honestly not performed.
    """
    make_workspace(tmp_path, [SPARK_ENTRY])
    case_a(tmp_path)

    def boom(*_: Any, **__: Any) -> Any:
        raise RuntimeError("drift check blew up")

    monkeypatch.setattr("theforge.forger.orchestrator.check_drift", boom)
    forger, store = _forger(tmp_path)
    out = forger.ask(AskRequest(intent="analise esse Glue Job porque está lento", debug=True))
    assert out.status == "provider_failure"
    assert out.error is not None and out.error.code == Codes.INTERNAL
    verification = store.read_contract(out.run_id, "verification", VerificationResult)
    assert out.receipt.verification_sha256 == sha256_of(store.read(out.run_id, "verification"))
    assert verification.self_report.status == "reported"
    assert verification.provider_evidence.status == "reported"  # a valid result existed
    assert verification.forge.status == "passed"
    assert any(
        "context-reverification" in d and "not performed" in d for d in verification.forge.details
    )
    diagnostic = store.read_optional(out.run_id, "diagnostic")
    assert diagnostic is not None and diagnostic["stage"] == "verification"


def test_provider_failure_records_verification_and_one_receipt(tmp_path: Path) -> None:
    """An execute call that crashes records verification: attempted, no response."""
    make_workspace(tmp_path, [bad_entry("crash", "bad-a")])
    forger, store = _forger(tmp_path)
    out = forger.ask(AskRequest(intent="run it", capability="bad.thing"))
    assert out.status == "provider_failure"
    verification = store.read_contract(out.run_id, "verification", VerificationResult)
    assert verification.self_report.status == "not_performed"
    assert verification.forge.status == "not_performed"
    assert store.read_contract(out.run_id, "receipt", ExecutionReceipt).status == "provider_failure"


def test_telemetry_failure_keeps_the_terminal_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A telemetry build failure costs the run its telemetry hash, never its receipt."""
    make_workspace(tmp_path, [])

    def boom(self: TelemetryRecorder) -> Any:
        raise RuntimeError("telemetry blew up")

    monkeypatch.setattr(TelemetryRecorder, "build", boom)
    forger, _ = _forger(tmp_path)
    out = forger.ask(AskRequest(intent="eco", capability="demo.echo"))
    assert out.status == "ok"
    assert out.receipt.telemetry_sha256 is None
    assert any("telemetry-unavailable" in note for note in out.receipt.limitations)


def test_plan_graph_failure_keeps_the_plan_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A graph build failure is a receipt limitation; the plan run still terminalizes."""
    make_workspace(tmp_path, [])

    def boom(*_: Any, **__: Any) -> Any:
        raise RuntimeError("graph blew up")

    monkeypatch.setattr("theforge.forger.plan_executor.build_graph", boom)
    forger, store = _forger(tmp_path)
    out = PlanExecutor(forger).run(PlanCommand(intent="nothing to decompose"))
    receipt = store.read_contract(out.run_id, "receipt", ExecutionReceipt)
    assert receipt.kind == "plan"
    assert receipt.plan is not None and receipt.plan.graph_sha256 is None
    assert any("graph-unavailable" in note for note in receipt.limitations)


def test_plan_receipt_write_failure_is_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same invariant for plan runs: a mid-finalize failure never triggers a retry."""
    make_workspace(tmp_path, [])
    forger, store = _forger(tmp_path)
    attempts = 0
    real_write = store.write

    def write(run_id: str, name: str, contract: Any) -> str:
        nonlocal attempts
        if name == "receipt":
            attempts += 1
            raise ContractError("receipt would not validate")
        return real_write(run_id, name, contract)

    monkeypatch.setattr(store, "write", write)
    with pytest.raises(PersistenceError, match="terminalization failed"):
        PlanExecutor(forger).run(PlanCommand(intent="nothing to decompose"))
    assert attempts == 1
