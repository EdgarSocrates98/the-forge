"""Relational contract invariants (requirements 1.1-1.8, 1.11, 2.6).

Each invariant has at least one valid and one invalid case asserting the specific code.
"""

from typing import Any

import pytest

from theforge.contracts import (
    Artifact,
    ContextFile,
    ContextPack,
    ContractError,
    Evidence,
    ExecutionReceipt,
    ExecutionResult,
    Finding,
    Producer,
    ReceiptInputs,
    ReceiptProvider,
)
from theforge.contracts.canonical import utc_now
from theforge.contracts.codes import Codes
from theforge.contracts.integrity import (
    IntegrityError,
    Violation,
    check_artifact_path,
    check_producer,
    check_timestamp,
    validate_context_pack,
    validate_receipt,
    validate_result,
)
from theforge.contracts.types import ErrorInfo

H1 = "a" * 64
H2 = "b" * 64
PROD = Producer(id="echo", version="1.0.0")
TS = "2026-01-01T00:00:00.000000Z"


def evidence(eid: str) -> Evidence:
    return Evidence(id=eid, epistemic="observed", subject="s", claim="c", producer=PROD)


def result(**overrides: Any) -> ExecutionResult:
    base: dict[str, Any] = {
        "producer": PROD,
        "created_at": TS,
        "status": "ok",
        "evidence": [evidence("e1"), evidence("e2")],
        "findings": [
            Finding(id="f1", title="t", evidence_ids=["e1"]),
            Finding(id="f2", title="t", evidence_ids=["e1", "e2"]),
        ],
        "artifacts": [Artifact(path="out/report.md", sha256=H1)],
    }
    base.update(overrides)
    return ExecutionResult(**base)


def codes_of(exc: pytest.ExceptionInfo[IntegrityError]) -> list[str]:
    return [v.code for v in exc.value.violations]


# --- IntegrityError shape -------------------------------------------------------------


def test_integrity_error_is_contract_error() -> None:
    assert issubclass(IntegrityError, ContractError)


def test_valid_result_passes() -> None:
    validate_result(result(), expected=PROD)


def test_utc_now_result_passes() -> None:
    validate_result(result(created_at=utc_now()), expected=PROD)


# --- 1.1 duplicate evidence ids -------------------------------------------------------


def test_duplicate_evidence_ids_rejected() -> None:
    bad = result(evidence=[evidence("e1"), evidence("e1"), evidence("e2")])
    with pytest.raises(IntegrityError) as exc:
        validate_result(bad, expected=PROD)
    assert exc.value.code == Codes.RESULT_DUP_EVIDENCE
    assert "e1" in str(exc.value)


# --- 1.2 duplicate finding ids --------------------------------------------------------


def test_duplicate_finding_ids_rejected() -> None:
    bad = result(findings=[Finding(id="f1", title="a"), Finding(id="f1", title="b")])
    with pytest.raises(IntegrityError) as exc:
        validate_result(bad, expected=PROD)
    assert exc.value.code == Codes.RESULT_DUP_FINDING


# --- 1.3 dangling evidence references -------------------------------------------------


def test_dangling_evidence_reference_rejected_and_named() -> None:
    bad = result(findings=[Finding(id="f1", title="t", evidence_ids=["e1", "ghost"])])
    with pytest.raises(IntegrityError) as exc:
        validate_result(bad, expected=PROD)
    assert exc.value.code == Codes.RESULT_DANGLING_EVIDENCE
    assert "ghost" in str(exc.value)
    assert exc.value.violations[0].field == "findings[0].evidence_ids[1]"


# --- 1.4 artifact path containment (lexical, never opened) ----------------------------


@pytest.mark.parametrize(
    "path", ["report.md", "out/report.md", "./out/r.md", "a/b.c/d", "deep/..name/x"]
)
def test_contained_artifact_paths_accepted(path: str) -> None:
    assert check_artifact_path(path) is None


@pytest.mark.parametrize(
    "path",
    [
        "",
        "/etc/passwd",
        "../escape",
        "out/../../escape",
        "out/..",
        "C:/Windows/x",
        "c:relative",
        "\\\\server\\share\\x",
        "out\\report.md",
        "\\rooted",
        ".",
        "./",
        "a\x00b",
    ],
)
def test_escaping_artifact_paths_rejected(path: str) -> None:
    v = check_artifact_path(path)
    assert v is not None
    assert v.code == Codes.RESULT_ARTIFACT_PATH


def test_result_with_bad_artifact_rejected_without_opening(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*_a: object, **_k: object) -> None:
        raise AssertionError("path must never be opened")

    monkeypatch.setattr("builtins.open", boom)
    bad = result(artifacts=[Artifact(path="ok.md", sha256=H1), Artifact(path="/abs", sha256=H2)])
    with pytest.raises(IntegrityError) as exc:
        validate_result(bad, expected=PROD)
    assert exc.value.code == Codes.RESULT_ARTIFACT_PATH
    assert exc.value.violations[0].field == "artifacts[1].path"


# --- 1.6 producer -------------------------------------------------------------------


def test_check_producer_matching() -> None:
    assert check_producer(PROD, expected=Producer(id="echo", version="1.0.0"), field="p") is None


@pytest.mark.parametrize(
    "actual", [Producer(id="other", version="1.0.0"), Producer(id="echo", version="9.9.9")]
)
def test_check_producer_divergent(actual: Producer) -> None:
    v = check_producer(actual, expected=PROD, field="producer")
    assert v == Violation(code=Codes.PROTO_PRODUCER, detail=v.detail if v else "", field="producer")


def test_result_with_wrong_producer_rejected() -> None:
    with pytest.raises(IntegrityError) as exc:
        validate_result(result(), expected=Producer(id="echo", version="2.0.0"))
    assert exc.value.code == Codes.PROTO_PRODUCER


# --- 2.6 timestamps -------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [TS, "2026-01-01T00:00:00Z", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00.5+00:00"],
)
def test_utc_timestamps_accepted(value: str) -> None:
    assert check_timestamp(value, field="created_at") is None


@pytest.mark.parametrize(
    "value",
    ["", "t", "yesterday", "2026-13-01T00:00:00Z", "2026-01-01T00:00:00",
     "2026-01-01T00:00:00+02:00", "2026-01-01"],
)
def test_malformed_or_non_utc_timestamps_rejected(value: str) -> None:
    v = check_timestamp(value, field="created_at")
    assert v is not None
    assert v.code == Codes.PROTO_SCHEMA
    assert v.field == "created_at"


def test_result_with_malformed_timestamp_rejected() -> None:
    with pytest.raises(IntegrityError) as exc:
        validate_result(result(created_at="not-a-date"), expected=PROD)
    assert exc.value.code == Codes.PROTO_SCHEMA


# --- deterministic collection ---------------------------------------------------------


def test_all_violations_collected_in_deterministic_order() -> None:
    bad = result(
        producer=Producer(id="evil", version="1.0.0"),
        created_at="nope",
        evidence=[evidence("e1"), evidence("e1")],
        findings=[
            Finding(id="f1", title="t", evidence_ids=["missing"]),
            Finding(id="f1", title="t"),
        ],
        artifacts=[Artifact(path="../x", sha256=H1)],
    )
    with pytest.raises(IntegrityError) as first:
        validate_result(bad, expected=PROD)
    with pytest.raises(IntegrityError) as second:
        validate_result(bad, expected=PROD)
    expected_order = [
        Codes.PROTO_PRODUCER,
        Codes.PROTO_SCHEMA,
        Codes.RESULT_DUP_EVIDENCE,
        Codes.RESULT_DUP_FINDING,
        Codes.RESULT_DANGLING_EVIDENCE,
        Codes.RESULT_ARTIFACT_PATH,
    ]
    assert codes_of(first) == expected_order
    assert first.value.code == Codes.PROTO_PRODUCER
    assert first.value.violations == second.value.violations


# --- 1.7 context pack -----------------------------------------------------------------


def pack(**overrides: Any) -> ContextPack:
    base: dict[str, Any] = {
        "producer": Producer(id="theforge", version="0.1.0"),
        "created_at": TS,
        "status": "complete",
        "task_id": "t1",
        "provider_id": "echo",
        "root": "/ws",
        "files": [
            ContextFile(path="a.py", sha256=H1, bytes=10),
            ContextFile(path="src/b.py", sha256=H2, bytes=5),
        ],
        "budget_bytes": 100,
        "used_bytes": 15,
    }
    base.update(overrides)
    return ContextPack(**base)


def test_valid_context_pack_passes() -> None:
    validate_context_pack(pack())
    validate_context_pack(pack(files=[], used_bytes=0))
    validate_context_pack(pack(budget_bytes=15))


def test_context_pack_over_budget_rejected() -> None:
    with pytest.raises(IntegrityError) as exc:
        validate_context_pack(pack(budget_bytes=10))
    assert exc.value.code == Codes.CONTEXT_BYTES


def test_context_pack_used_bytes_mismatch_rejected() -> None:
    with pytest.raises(IntegrityError) as exc:
        validate_context_pack(pack(used_bytes=14))
    assert exc.value.code == Codes.CONTEXT_BYTES


@pytest.mark.parametrize("path", ["/etc/passwd", "../x", "C:/x", "a\\b"])
def test_context_pack_escaping_file_path_rejected(path: str) -> None:
    files = [ContextFile(path=path, sha256=H1, bytes=15)]
    with pytest.raises(IntegrityError) as exc:
        validate_context_pack(pack(files=files))
    assert exc.value.code == Codes.CONTEXT_PATH
    assert exc.value.violations[0].field == "files[0].path"


# --- 1.8 / 1.5 receipt ----------------------------------------------------------------


def receipt(**overrides: Any) -> ExecutionReceipt:
    base: dict[str, Any] = {
        "producer": Producer(id="theforge", version="0.1.0"),
        "created_at": TS,
        "status": "ok",
        "run_id": "r1",
        "forge_version": "0.1.0",
        "inputs": ReceiptInputs(task_sha256=H1, routing_sha256=H2, context_sha256=H1),
        "provider": ReceiptProvider(
            id="echo", version="1.0.0", trust="builtin", manifest_sha256=H2
        ),
        "result_sha256": H1,
        "started_at": TS,
        "finished_at": TS,
    }
    base.update(overrides)
    return ExecutionReceipt(**base)


def test_valid_success_receipt_passes() -> None:
    validate_receipt(receipt(), result_sha256=H1)
    validate_receipt(receipt(status="partial"), result_sha256=H1)


def test_failure_receipt_without_result_hash_passes() -> None:
    failed = receipt(
        status="provider_failure",
        result_sha256=None,
        error=ErrorInfo(code=Codes.PROTO_EXIT, detail="exit 1"),
    )
    validate_receipt(failed, result_sha256=None)


def test_success_receipt_without_result_hash_rejected() -> None:
    with pytest.raises(IntegrityError) as exc:
        validate_receipt(receipt(result_sha256=None), result_sha256=H1)
    assert exc.value.code == Codes.RECEIPT_INVALID


def test_success_receipt_with_no_persisted_result_rejected() -> None:
    with pytest.raises(IntegrityError) as exc:
        validate_receipt(receipt(), result_sha256=None)
    assert exc.value.code == Codes.RECEIPT_INVALID


def test_success_receipt_with_mismatched_hash_rejected() -> None:
    with pytest.raises(IntegrityError) as exc:
        validate_receipt(receipt(), result_sha256=H2)
    assert exc.value.code == Codes.RECEIPT_INVALID
    assert exc.value.violations[0].field == "result_sha256"


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"inputs": ReceiptInputs(task_sha256="A" * 64)}, "inputs.task_sha256"),
        ({"inputs": ReceiptInputs(task_sha256=H1, routing_sha256="abc")}, "inputs.routing_sha256"),
        ({"inputs": ReceiptInputs(task_sha256=H1, context_sha256="h")}, "inputs.context_sha256"),
        ({"inputs": ReceiptInputs(task_sha256=H1, risk_sha256="g" * 64)}, "inputs.risk_sha256"),
        (
            {"provider": ReceiptProvider(id="e", version="1", trust="local", manifest_sha256="h")},
            "provider.manifest_sha256",
        ),
    ],
)
def test_receipt_malformed_hash_rejected(overrides: dict[str, Any], field: str) -> None:
    with pytest.raises(IntegrityError) as exc:
        validate_receipt(receipt(**overrides), result_sha256=H1)
    assert exc.value.code == Codes.RECEIPT_INVALID
    assert exc.value.violations[0].field == field


def test_receipt_malformed_result_hash_rejected() -> None:
    bad = "F" * 64
    with pytest.raises(IntegrityError) as exc:
        validate_receipt(receipt(result_sha256=bad), result_sha256=bad)
    assert exc.value.code == Codes.RECEIPT_INVALID
    assert exc.value.violations[0].field == "result_sha256"


@pytest.mark.parametrize("field", ["created_at", "started_at", "finished_at"])
def test_receipt_malformed_timestamp_rejected(field: str) -> None:
    with pytest.raises(IntegrityError) as exc:
        validate_receipt(receipt(**{field: "t"}), result_sha256=H1)
    assert exc.value.code == Codes.RECEIPT_INVALID
    assert exc.value.violations[0].field == field
