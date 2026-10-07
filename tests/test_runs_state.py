import json
import os
import secrets
import subprocess
from pathlib import Path
from typing import Any

import pytest

from theforge.contracts import (
    CapabilityGraph,
    ComplexityAssessment,
    ContextPack,
    ContractError,
    DecisionRecord,
    Diagnostic,
    ErrorInfo,
    ExecutionPlan,
    ExecutionReceipt,
    ExecutionResult,
    Handoff,
    GlobalStopDecision,
    InstallationPlan,
    IntegrityError,
    Metric,
    PlanRefs,
    PlanResult,
    PlanState,
    PolicyDecision,
    Producer,
    ProfileSnapshot,
    ReceiptInputs,
    RiskAssessment,
    RiskDimensions,
    RoutingProposal,
    RunBudget,
    RunTelemetry,
    SemanticPlanProposal,
    TaskSpec,
    VerificationResult,
    WorkspaceDescriptor,
    WorkspaceGraph,
    from_dict,
)
from theforge.contracts.canonical import sha256_of, utc_now
from theforge.contracts.codes import Codes
from theforge.contracts.risk import OPERATION_CLASS_LIMITATION
from theforge.errors import PersistenceError, UsageError
from theforge.meta import PRODUCER
from theforge.runs import ARTIFACT_TYPES, ARTIFACTS, RUN_ID, RunStore, new_run_id
from theforge.state import find_forge_dir, init_workspace, require_forge_dir


def make_task(intent: str = "eco password=hunter2xyz") -> TaskSpec:
    return TaskSpec(producer=PRODUCER, created_at=utc_now(), id="t1", intent=intent,
                    workspace_root="/ws")


def test_new_run_id_format() -> None:
    assert RUN_ID.match(new_run_id())


def test_write_read_redacts_and_hashes(tmp_path: Path) -> None:
    store = RunStore(tmp_path / ".forge")
    run_id = new_run_id()
    store.create(run_id)
    digest = store.write(run_id, "task", make_task())
    data = store.read(run_id, "task")
    assert data["intent"] == "eco password=[REDACTED]"
    assert digest == sha256_of(data)
    assert store.read_optional(run_id, "result") is None
    assert store.list_runs() == [run_id]
    assert store.work_dir(run_id).is_dir()


def test_run_id_validation(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="invalid run id"):
        RunStore(tmp_path).run_dir("../../etc")


def test_unknown_artifact_name(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    run_id = new_run_id()
    store.create(run_id)
    with pytest.raises(ValueError, match="unknown run artifact"):
        store.write(run_id, "secrets", make_task())


def test_run_id_rejects_trailing_newline(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="invalid run id"):
        RunStore(tmp_path).run_dir(new_run_id() + "\n")


def test_read_optional_validates_artifact_name(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    run_id = new_run_id()
    store.create(run_id)
    with pytest.raises(ValueError, match="unknown run artifact"):
        store.read_optional(run_id, "../../x")


def test_read_optional_corrupt_json_is_persistence_error(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    run_id = new_run_id()
    store.create(run_id)
    (store.run_dir(run_id) / "task.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(PersistenceError, match="cannot read"):
        store.read_optional(run_id, "task")


def test_read_optional_non_dict_is_persistence_error(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    run_id = new_run_id()
    store.create(run_id)
    (store.run_dir(run_id) / "task.json").write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(PersistenceError, match="cannot read"):
        store.read_optional(run_id, "task")


def test_persistence_error(tmp_path: Path) -> None:
    not_a_dir = tmp_path / "forge-file"
    not_a_dir.write_text("x")
    with pytest.raises(PersistenceError):
        RunStore(not_a_dir).create(new_run_id())


def test_init_workspace(tmp_path: Path) -> None:
    created = init_workspace(tmp_path)
    assert ".forge/config/providers.toml" in created
    assert ".forge/.gitignore" in created
    assert ".forge/registry" not in created
    assert "!config/" in (tmp_path / ".forge" / ".gitignore").read_text(encoding="utf-8")
    assert init_workspace(tmp_path) == []
    assert find_forge_dir(tmp_path) == tmp_path / ".forge"
    other = tmp_path / "other"
    other.mkdir()
    assert find_forge_dir(other) is None
    with pytest.raises(UsageError, match="theforge init"):
        require_forge_dir(other)


# --- 3.5: risk artifact, strict typed reads, receipt validation on write ---------------

H_OTHER = "b" * 64
TS = "2025-01-01T00:00:00.000000Z"


def _store_with_run(tmp_path: Path) -> tuple[RunStore, str]:
    store = RunStore(tmp_path / ".forge")
    run_id = new_run_id()
    store.create(run_id)
    return store, run_id


def make_result() -> ExecutionResult:
    return ExecutionResult(producer=Producer(id="echo", version="1.0.0"), created_at=utc_now(),
                           status="ok")


def make_receipt(run_id: str, **overrides: Any) -> ExecutionReceipt:
    base: dict[str, Any] = {
        "producer": PRODUCER, "created_at": utc_now(), "status": "ok", "run_id": run_id,
        "forge_version": "0.1.0", "inputs": ReceiptInputs(task_sha256="a" * 64),
        "result_sha256": None, "started_at": utc_now(), "finished_at": utc_now(),
    }
    base.update(overrides)
    return ExecutionReceipt(**base)


def make_risk(run_id: str) -> RiskAssessment:
    levels: dict[str, Any] = dict.fromkeys(
        ("read_only", "local_mutation", "external_read", "external_mutation", "destructive",
         "credentials", "cross_account"), "no")
    return RiskAssessment(
        producer=PRODUCER, created_at=utc_now(), run_id=run_id, provider_id="echo",
        capability="echo.reflect", action="analyze", operation_class="read_only",
        source="provider_declaration", dimensions=RiskDimensions(**levels),
        policy=PolicyDecision(decision="allow", rule="default", reason="read only",
                              approved=False),
        limitations=[OPERATION_CLASS_LIMITATION],
    )


def test_risk_is_a_known_artifact_in_run_order() -> None:
    assert ARTIFACTS == ("task", "workspace-descriptor", "routing", "plan", "installation",
                         "risk", "handoff", "context", "context-r1", "context-r2", "result",
                         "plan-state", "plan-result", "graph", "capability-graph",
                         "semantic-proposal", "routing-proposal", "decision", "economy",
                         "verification", "telemetry", "diagnostic", "complexity",
                         "budget", "receipt")
    assert ARTIFACT_TYPES["complexity"] is ComplexityAssessment
    assert ARTIFACT_TYPES["budget"] is RunBudget
    assert ARTIFACT_TYPES["capability-graph"] is CapabilityGraph
    assert ARTIFACT_TYPES["semantic-proposal"] is SemanticPlanProposal
    assert ARTIFACT_TYPES["routing-proposal"] is RoutingProposal
    assert ARTIFACT_TYPES["decision"] is DecisionRecord
    assert ARTIFACT_TYPES["plan-state"] is PlanState
    assert set(ARTIFACT_TYPES) == set(ARTIFACTS)
    assert ARTIFACT_TYPES["risk"] is RiskAssessment
    assert ARTIFACT_TYPES["receipt"] is ExecutionReceipt


def test_negotiation_round_and_telemetry_artifacts_are_typed() -> None:
    assert ARTIFACT_TYPES["context-r1"] is ContextPack
    assert ARTIFACT_TYPES["context-r2"] is ContextPack
    assert ARTIFACT_TYPES["telemetry"] is RunTelemetry


def make_telemetry(run_id: str) -> RunTelemetry:
    snapshot = ProfileSnapshot(
        name="balanced", budget_bytes=262144, max_files=64,
        tiers=["excerpt", "metadata", "reference", "requested"],
        effective_tiers=["metadata", "reference"], negotiation_rounds=1, max_providers=1,
        fallback=True, verification="conditional", execute_timeout_s=180.0)
    return RunTelemetry(producer=PRODUCER, created_at=utc_now(), run_id=run_id,
                        profile=snapshot, scan_ms=Metric(value=1.5, kind="measured"),
                        limitations=["provider said password=hunter2xyz"])


def test_telemetry_is_redacted_hashed_on_disk_and_reread_strictly(tmp_path: Path) -> None:
    store, run_id = _store_with_run(tmp_path)
    digest = store.write(run_id, "telemetry", make_telemetry(run_id))
    on_disk = store.read(run_id, "telemetry")
    assert on_disk["limitations"] == ["provider said password=[REDACTED]"]
    assert "hunter2xyz" not in (store.run_dir(run_id) / "telemetry.json").read_text("utf-8")
    assert digest == sha256_of(on_disk) == store.persisted_sha256(run_id, "telemetry")
    loaded = store.read_contract(run_id, "telemetry", RunTelemetry)
    assert loaded.limitations == ["provider said password=[REDACTED]"]
    assert loaded.scan_ms == Metric(value=1.5, kind="measured")
    assert loaded.routing_ms == Metric()


def test_negotiation_round_pack_round_trips_through_strict_read(tmp_path: Path) -> None:
    store, run_id = _store_with_run(tmp_path)
    pack = ContextPack(producer=PRODUCER, created_at=utc_now(), status="complete",
                       task_id="t1", provider_id="echo", root=".", budget_bytes=10, round=1)
    for name in ("context-r1", "context-r2"):
        digest = store.write(run_id, name, pack)
        assert digest == sha256_of(store.read(run_id, name))
        assert store.read_contract(run_id, name, ContextPack) == pack
    assert (store.run_dir(run_id) / "context-r1.json").is_file()


def test_run_without_new_artifacts_reads_them_as_absent(tmp_path: Path) -> None:
    store, run_id = _store_with_run(tmp_path)
    store.write(run_id, "task", make_task())
    for name in ("context-r1", "context-r2", "telemetry"):
        assert store.read_optional(run_id, name) is None
        assert store.persisted_sha256(run_id, name) is None
    with pytest.raises(LookupError):
        store.read_contract(run_id, "telemetry", RunTelemetry)


def test_risk_round_trips_through_strict_read(tmp_path: Path) -> None:
    store, run_id = _store_with_run(tmp_path)
    risk = make_risk(run_id)
    digest = store.write(run_id, "risk", risk)
    assert digest == sha256_of(store.read(run_id, "risk"))
    assert store.read_contract(run_id, "risk", RiskAssessment) == risk


def test_absent_risk_reads_as_not_recorded(tmp_path: Path) -> None:
    store, run_id = _store_with_run(tmp_path)
    assert store.read_optional(run_id, "risk") is None
    with pytest.raises(LookupError):
        store.read_contract(run_id, "risk", RiskAssessment)


def test_read_contract_rejects_unknown_keys(tmp_path: Path) -> None:
    store, run_id = _store_with_run(tmp_path)
    store.write(run_id, "task", make_task())
    path = store.run_dir(run_id) / "task.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["injected"] = True
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ContractError, match=r"injected: unknown field"):
        store.read_contract(run_id, "task", TaskSpec)
    assert store.read(run_id, "task")["injected"] is True  # dict read stays tolerant


def test_read_contract_rejects_mismatched_type(tmp_path: Path) -> None:
    store, run_id = _store_with_run(tmp_path)
    store.write(run_id, "task", make_task())
    with pytest.raises(ValueError, match="artifact 'task' is TaskSpec"):
        store.read_contract(run_id, "task", RiskAssessment)


def test_cycle1_run_remains_readable(tmp_path: Path) -> None:
    store, run_id = _store_with_run(tmp_path)
    run = store.run_dir(run_id)
    producer = {"id": "theforge", "version": "0.1.0"}
    task = {"schema": "theforge/TaskSpec/v1", "producer": producer, "created_at": TS,
            "status": "created", "id": "t1", "intent": "eco", "workspace_root": "/ws"}
    receipt = {"schema": "theforge/ExecutionReceipt/v1", "producer": producer,
               "created_at": TS, "status": "provider_failure", "run_id": run_id,
               "forge_version": "0.1.0",
               "inputs": {"task_sha256": "a" * 64, "routing_sha256": None,
                          "context_sha256": None},
               "provider": None, "result_sha256": None, "started_at": TS, "finished_at": TS,
               "error": {"code": "FORGE-PROTO-EXIT", "detail": "exit 1"},
               "limitations": [], "unknowns": []}
    (run / "task.json").write_text(json.dumps(task), encoding="utf-8")
    (run / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    assert store.read(run_id, "receipt")["status"] == "provider_failure"
    loaded = store.read_contract(run_id, "receipt", ExecutionReceipt)
    assert loaded.inputs.risk_sha256 is None
    assert store.read_contract(run_id, "task", TaskSpec).intent == "eco"
    assert store.read_optional(run_id, "risk") is None


def test_success_receipt_matching_persisted_result_is_written(tmp_path: Path) -> None:
    store, run_id = _store_with_run(tmp_path)
    result_sha = store.write(run_id, "result", make_result())
    receipt = make_receipt(run_id, result_sha256=result_sha)
    store.write(run_id, "receipt", receipt)
    assert store.read_contract(run_id, "receipt", ExecutionReceipt) == receipt
    assert store.read_contract(run_id, "result", ExecutionResult).status == "ok"


def test_success_receipt_without_result_hash_is_refused(tmp_path: Path) -> None:
    store, run_id = _store_with_run(tmp_path)
    store.write(run_id, "result", make_result())
    with pytest.raises(IntegrityError) as exc:
        store.write(run_id, "receipt", make_receipt(run_id, result_sha256=None))
    assert exc.value.code == Codes.RECEIPT_INVALID
    assert store.read_optional(run_id, "receipt") is None


def test_success_receipt_with_mismatching_hash_is_refused(tmp_path: Path) -> None:
    store, run_id = _store_with_run(tmp_path)
    store.write(run_id, "result", make_result())
    with pytest.raises(IntegrityError) as exc:
        store.write(run_id, "receipt",
                    make_receipt(run_id, status="partial", result_sha256=H_OTHER))
    assert exc.value.code == Codes.RECEIPT_INVALID
    assert store.read_optional(run_id, "receipt") is None


def test_success_receipt_without_persisted_result_is_refused(tmp_path: Path) -> None:
    store, run_id = _store_with_run(tmp_path)
    with pytest.raises(IntegrityError) as exc:
        store.write(run_id, "receipt", make_receipt(run_id, result_sha256=H_OTHER))
    assert exc.value.code == Codes.RECEIPT_INVALID


def test_failure_receipt_without_result_is_written(tmp_path: Path) -> None:
    store, run_id = _store_with_run(tmp_path)
    receipt = make_receipt(run_id, status="refused",
                           error=ErrorInfo(code=Codes.RECEIPT_INVALID, detail="x"))
    store.write(run_id, "receipt", receipt)
    assert store.read(run_id, "receipt")["status"] == "refused"


def test_receipt_with_malformed_hash_is_refused(tmp_path: Path) -> None:
    store, run_id = _store_with_run(tmp_path)
    bad = make_receipt(run_id, status="refused", inputs=ReceiptInputs(task_sha256="h"),
                       error=ErrorInfo(code=Codes.RECEIPT_INVALID, detail="x"))
    with pytest.raises(IntegrityError) as exc:
        store.write(run_id, "receipt", bad)
    assert exc.value.code == Codes.RECEIPT_INVALID
    assert store.read_optional(run_id, "receipt") is None


# --- cross-forge-foundation 1.5: plan artifacts, plan receipts, older runs ---------------

# Random per session: a redaction fixture, not a credential.
SECRET = "password=" + secrets.token_hex(8)
WP = {"id": "theforge", "version": "1"}
WTS = "2026-01-01T00:00:00Z"
H_A = "a" * 64


def _wave_d_artifacts() -> dict[str, tuple[type, dict[str, Any]]]:
    origin = {"plan_run": "p1", "node": "a", "run_id": "r1",
              "provider": {"id": "spark", "version": "2.0"}}
    return {
        "plan": (ExecutionPlan, {
            "producer": WP, "created_at": WTS, "status": "validated", "plan_run": "p1",
            "task_id": "t1", "pattern": "route", "source": "decomposed", "profile": "max",
            "nodes": [{"id": "a", "role": "standalone", "provider": "demo",
                       "capability": "demo.echo", "action": "echo"}],
            "limitations": [SECRET]}),
        "plan-result": (PlanResult, {
            "producer": WP, "created_at": WTS, "status": "ok", "plan_run": "p1",
            "order": ["a"], "nodes": [{"node": "a", "status": "ok", "run_id": "r1",
                                       "result_sha256": H_A}],
            "synthesis": {"nodes": []}, "reproducibility": {"level": "unknown"},
            "limitations": [SECRET]}),
        "global-stop": (GlobalStopDecision, {
            "producer": WP, "created_at": WTS, "run_id": "p1",
            "action": "stop_sufficient_evidence", "information_gain": "unknown",
            "reasons": [SECRET]}),
        "workspace-descriptor": (WorkspaceDescriptor, {
            "producer": WP, "created_at": WTS, "root": "/ws",
            "repositories": [{"path": "."}], "limitations": [SECRET]}),
        "graph": (WorkspaceGraph, {
            "producer": WP, "created_at": WTS, "plan_run": "p1",
            "nodes": [{"id": "workspace:.", "kind": "workspace"}], "limitations": [SECRET]}),
        "installation": (InstallationPlan, {
            "producer": WP, "created_at": WTS, "run_id": "p1",
            "items": [{"provider": "spark", "state": "unavailable", "reason": SECRET,
                       "suggested_action": "install java", "source": "health"}]}),
        "handoff": (Handoff, {
            "producer": WP, "created_at": WTS, "plan_run": "p1", "target_node": "b",
            "items": [{"kind": "evidence", "id": "e1", "origin": origin,
                       "epistemic": "inferred", "claim": SECRET}]}),
        "verification": (VerificationResult, {
            "producer": WP, "created_at": WTS, "run_id": "r1",
            "self_report": {"status": "reported"}, "provider_evidence": {"status": "reported"},
            "forge": {"status": "passed"}, "independent": {"status": "not_performed"},
            "limitations": [SECRET]}),
        "diagnostic": (Diagnostic, {
            "producer": WP, "created_at": WTS, "stage": "cli:plan", "code": "FORGE-INTERNAL",
            "family": "internal", "error_type": "RuntimeError", "message": SECRET}),
    }


def test_wave_d_artifacts_are_known_and_typed() -> None:
    for name, (cls, _) in _wave_d_artifacts().items():
        assert name in ARTIFACTS and ARTIFACT_TYPES[name] is cls
    # The multi-repo descriptor is not the ContextPack workspace summary.
    assert "workspace" not in ARTIFACTS


@pytest.mark.parametrize("name", sorted(_wave_d_artifacts()))
def test_wave_d_artifact_is_redacted_hashed_and_reread_strictly(
        tmp_path: Path, name: str) -> None:
    cls, data = _wave_d_artifacts()[name]
    store, run_id = _store_with_run(tmp_path)
    if name == "plan-result":
        stop_cls, stop_data = _wave_d_artifacts()["global-stop"]
        stop_sha = store.write(
            run_id, "global-stop", from_dict(stop_cls, stop_data, strict=True)
        )
        data = {**data, "global_stop_sha256": stop_sha}
    digest = store.write(run_id, name, from_dict(cls, data, strict=True))
    text = (store.run_dir(run_id) / f"{name}.json").read_text("utf-8")
    assert "hunter2xyz" not in text and "password=[REDACTED]" in text
    assert digest == sha256_of(store.read(run_id, name)) == store.persisted_sha256(run_id, name)
    loaded = store.read_contract(run_id, name, cls)
    assert isinstance(loaded, cls)
    raw = store.read(run_id, name)
    raw["injected"] = True
    (store.run_dir(run_id) / f"{name}.json").write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ContractError, match="injected: unknown field"):
        store.read_contract(run_id, name, cls)


def _write_plan_run(store: RunStore, run_id: str) -> tuple[str, str, str, str]:
    artifacts = _wave_d_artifacts()
    plan_cls, plan_data = artifacts["plan"]
    plan_sha = store.write(run_id, "plan", from_dict(plan_cls, plan_data, strict=True))
    stop_cls, stop_data = artifacts["global-stop"]
    stop_data = {**stop_data, "run_id": run_id}
    stop_sha = store.write(
        run_id, "global-stop", from_dict(stop_cls, stop_data, strict=True)
    )
    result_cls, result_data = artifacts["plan-result"]
    result_data = {
        **result_data,
        "plan_run": run_id,
        "global_stop_sha256": stop_sha,
    }
    result_sha = store.write(
        run_id, "plan-result", from_dict(result_cls, result_data, strict=True)
    )
    telemetry_sha = store.write(run_id, "telemetry", make_telemetry(run_id))
    return plan_sha, result_sha, telemetry_sha, stop_sha


def make_plan_receipt(
        run_id: str,
        plan_sha: str,
        plan_result: str | None,
        *,
        global_stop_sha256: str | None = None,
        **overrides: Any,
) -> ExecutionReceipt:
    refs = PlanRefs(
        plan_sha256=plan_sha,
        plan_result_sha256=plan_result,
        global_stop_sha256=global_stop_sha256,
    )
    return make_receipt(run_id, kind="plan", plan=refs, **overrides)


def test_plan_receipt_matching_disk_is_written_and_reread(tmp_path: Path) -> None:
    store, run_id = _store_with_run(tmp_path)
    plan_sha, result_sha, telemetry_sha, stop_sha = _write_plan_run(store, run_id)
    receipt = make_plan_receipt(
        run_id,
        plan_sha,
        result_sha,
        telemetry_sha256=telemetry_sha,
        global_stop_sha256=stop_sha,
    )
    store.write(run_id, "receipt", receipt)
    assert store.read_contract(run_id, "receipt", ExecutionReceipt) == receipt


def test_planned_receipt_without_plan_result_is_written(tmp_path: Path) -> None:
    store, run_id = _store_with_run(tmp_path)
    plan_cls, plan_data = _wave_d_artifacts()["plan"]
    plan_sha = store.write(run_id, "plan", from_dict(plan_cls, plan_data, strict=True))
    telemetry_sha = store.write(run_id, "telemetry", make_telemetry(run_id))
    receipt = make_plan_receipt(run_id, plan_sha, None, status="planned",
                                telemetry_sha256=telemetry_sha)
    store.write(run_id, "receipt", receipt)
    assert store.read(run_id, "receipt")["status"] == "planned"


@pytest.mark.parametrize("diverging", ["plan-result", "telemetry", "missing-plan-result"])
def test_plan_receipt_with_diverging_hash_is_refused_without_writing(
        tmp_path: Path, diverging: str) -> None:
    store, run_id = _store_with_run(tmp_path)
    plan_sha, result_sha, telemetry_sha, stop_sha = _write_plan_run(store, run_id)
    if diverging == "plan-result":
        receipt = make_plan_receipt(
            run_id, plan_sha, H_OTHER, telemetry_sha256=telemetry_sha,
            global_stop_sha256=stop_sha
        )
        field = "plan.plan_result_sha256"
    elif diverging == "telemetry":
        receipt = make_plan_receipt(
            run_id, plan_sha, result_sha, telemetry_sha256=H_OTHER,
            global_stop_sha256=stop_sha
        )
        field = "telemetry_sha256"
    else:
        receipt = make_plan_receipt(
            run_id, plan_sha, None, telemetry_sha256=telemetry_sha,
            global_stop_sha256=stop_sha
        )
        field = "plan.plan_result_sha256"
    with pytest.raises(IntegrityError) as exc:
        store.write(run_id, "receipt", receipt)
    assert exc.value.code == Codes.RECEIPT_INVALID and exc.value.field == field
    assert store.read_optional(run_id, "receipt") is None


def test_plan_receipt_with_malformed_plan_hash_is_refused(tmp_path: Path) -> None:
    store, run_id = _store_with_run(tmp_path)
    receipt = make_plan_receipt(run_id, "nope", None, status="planned")
    with pytest.raises(IntegrityError) as exc:
        store.write(run_id, "receipt", receipt)
    assert exc.value.field == "plan.plan_sha256"


@pytest.mark.parametrize("field", ["verification_sha256", "inputs.handoff_sha256"])
def test_run_receipt_with_malformed_new_hash_is_refused(tmp_path: Path, field: str) -> None:
    store, run_id = _store_with_run(tmp_path)
    error = ErrorInfo(code=Codes.RECEIPT_INVALID, detail="x")
    if field == "verification_sha256":
        bad = make_receipt(run_id, status="refused", error=error, verification_sha256="x")
    else:
        bad = make_receipt(run_id, status="refused", error=error,
                           inputs=ReceiptInputs(task_sha256=H_A, handoff_sha256="x"))
    with pytest.raises(IntegrityError) as exc:
        store.write(run_id, "receipt", bad)
    assert exc.value.field == field


def test_run_receipt_ignores_plan_artifacts_and_telemetry(tmp_path: Path) -> None:
    """kind=run validation is unchanged: telemetry/plan-result on disk are not compared."""
    store, run_id = _store_with_run(tmp_path)
    _write_plan_run(store, run_id)
    result_sha = store.write(run_id, "result", make_result())
    store.write(run_id, "receipt", make_receipt(run_id, result_sha256=result_sha,
                                                telemetry_sha256=H_OTHER))


def test_run_written_in_previous_format_rereads_with_nothing_new_recorded(
        tmp_path: Path) -> None:
    store, run_id = _store_with_run(tmp_path)
    receipt = {"schema": "theforge/ExecutionReceipt/v1", "producer": WP, "created_at": TS,
               "status": "ok", "run_id": run_id, "forge_version": "0.3.0",
               "inputs": {"task_sha256": H_A, "context_round_sha256": []},
               "provider": {"id": "echo", "version": "1.0.0", "trust": "builtin"},
               "result_sha256": H_A, "telemetry_sha256": H_A, "started_at": TS,
               "finished_at": TS, "error": None, "limitations": [], "unknowns": []}
    (store.run_dir(run_id) / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    loaded = store.read_contract(run_id, "receipt", ExecutionReceipt)
    assert loaded.kind == "run" and loaded.plan is None
    assert loaded.verification_sha256 is None and loaded.reproducibility is None
    assert loaded.inputs.handoff_sha256 is None
    for name in ("verification", "handoff", "plan", "plan-result", "graph",
                 "workspace-descriptor", "installation", "diagnostic"):
        assert store.read_optional(run_id, name) is None


# --- cycle-2.1 wave C: hostile artifact entries are never followed -------------------------
# A run artifact must be a regular file physically inside the run directory: a link (to
# anything, inside or outside the store), a directory or a broken link is a controlled
# PERSIST_READ on every read path — never content from outside the runs directory.


def _link(link: Path, target: Path, *, directory: bool = False) -> None:
    """Link ``link`` to ``target``; skip when the host allows neither links nor junctions."""
    try:
        link.symlink_to(target, target_is_directory=directory)
        return
    except OSError:
        pass
    if os.name == "nt" and directory:
        made = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                              capture_output=True, check=False)
        if made.returncode == 0 and os.path.lexists(link):
            return
    pytest.skip("symlinks not permitted on this platform")


def _assert_unreadable(store: RunStore, run_id: str, name: str = "task") -> None:
    """Every read path of the artifact is a controlled PERSIST_READ, never content."""
    reads = (lambda: store.read_optional(run_id, name),
             lambda: store.read(run_id, name),
             lambda: store.persisted_sha256(run_id, name),
             lambda: store.read_contract(run_id, name, ARTIFACT_TYPES[name]))
    for read in reads:
        with pytest.raises(PersistenceError) as exc:
            read()
        assert exc.value.code == Codes.PERSIST_READ


def test_artifact_symlink_to_external_secret_is_unreadable(tmp_path: Path) -> None:
    store, run_id = _store_with_run(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "task.json"
    secret.write_text(json.dumps({"intent": "leak hunter2"}), encoding="utf-8")
    _link(store.run_dir(run_id) / "task.json", secret)
    _assert_unreadable(store, run_id)
    # The link itself still exists and no external bytes were read into the run.
    assert os.path.islink(store.run_dir(run_id) / "task.json")


def test_artifact_symlink_to_another_run_is_unreadable(tmp_path: Path) -> None:
    """A link whose target stays inside the store is still a link: never followed."""
    store, run_id = _store_with_run(tmp_path)
    other = new_run_id()
    store.create(other)
    store.write(other, "task", make_task())
    _link(store.run_dir(run_id) / "task.json", store.run_dir(other) / "task.json")
    _assert_unreadable(store, run_id)
    # The honest artifact of the other run is unaffected.
    assert store.read(other, "task")["intent"] == "eco password=[REDACTED]"


def test_artifact_that_is_a_directory_is_unreadable(tmp_path: Path) -> None:
    store, run_id = _store_with_run(tmp_path)
    (store.run_dir(run_id) / "task.json").mkdir()
    _assert_unreadable(store, run_id)


def test_artifact_dir_symlink_is_unreadable(tmp_path: Path) -> None:
    store, run_id = _store_with_run(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    _link(store.run_dir(run_id) / "task.json", outside, directory=True)
    _assert_unreadable(store, run_id)


def test_broken_artifact_symlink_is_unreadable_not_absent(tmp_path: Path) -> None:
    """A dangling link is present-but-hostile, not "absent" (it must not read as None)."""
    store, run_id = _store_with_run(tmp_path)
    _link(store.run_dir(run_id) / "task.json", tmp_path / "nowhere" / "task.json")
    _assert_unreadable(store, run_id)


def test_run_dir_link_escaping_the_store_is_unreadable(tmp_path: Path) -> None:
    """A symlinked run directory pointing outside makes its artifacts unreadable."""
    store = RunStore(tmp_path / ".forge")
    run_id = new_run_id()
    store.runs_dir.mkdir(parents=True)
    outside = tmp_path / "outside" / run_id
    outside.mkdir(parents=True)
    (outside / "task.json").write_text(json.dumps({"intent": "leak"}), encoding="utf-8")
    _link(store.runs_dir / run_id, outside, directory=True)
    _assert_unreadable(store, run_id)


def test_write_over_a_linked_artifact_is_refused(tmp_path: Path) -> None:
    store, run_id = _store_with_run(tmp_path)
    secret = tmp_path / "secret.json"
    secret.write_text("{}", encoding="utf-8")
    artifact = store.run_dir(run_id) / "task.json"
    _link(artifact, secret)
    with pytest.raises(PersistenceError) as exc:
        store.write(run_id, "task", make_task())
    assert exc.value.code == Codes.PERSIST_WRITE
    assert os.path.islink(artifact)  # the link survives; nothing was written through it
