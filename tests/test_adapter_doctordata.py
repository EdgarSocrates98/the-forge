"""Forge Doctor Data adapter (cycle 3.1, phases 9-10): handoff over the public boundary.

The adapter derives ``describe`` from ``native_surface.json`` (a snapshot of the specialist's
public seams): a capability is exposed only when the seam it drives is recorded present.
Live, the interpreter must be Python >= 3.11 with ``forge_doctor_data`` importable; with
``--replay <dir>`` the scenario's ``environment.json`` answers instead and recordings replace
the bridge runs. ``data.scan`` drives ``accept_request`` (a ``forge-contracts/1``
HandoffBundle) and ``data.verify`` drives ``check_conformance``; both translate into the
Evidence Bus without the core knowing anything about data platforms.
"""

import hashlib
import importlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest
from theforge_doctordata import _shell, catalog, health, record

from theforge.contracts import (
    PROTOCOL_V1,
    ExecutionResult,
    ForgeManifest,
    HealthCheck,
    HealthReport,
    Producer,
    Response,
    from_dict,
)
from theforge.contracts.integrity import validate_manifest_limits, validate_result
from theforge.contracts.taxonomy import validate_taxonomy

REPO = Path(__file__).parents[1]
PACKAGE = REPO / "adapters" / "doctordata" / "src" / "theforge_doctordata"
NATIVE = REPO / "tests" / "fixtures" / "native" / "doctordata"
DEFAULT = NATIVE / "default"
SCENARIOS = NATIVE / "scenarios"
WORKSPACE = REPO / "tests" / "fixtures" / "workspaces" / "data" / "shop"
EXPOSED = ["data.scan", "data.verify"]
CHECKS = ["python", "import", "version", "boundary"]
ON_311_PLUS = sys.version_info[:2] >= (3, 11)
HAS_SPECIALIST = importlib.util.find_spec("forge_doctor_data") is not None


def _call(op: str, options: tuple[str, ...] = (), payload: dict[str, Any] | None = None
          ) -> tuple[Response, dict[str, Any]]:
    request = json.dumps({"protocol": PROTOCOL_V1, "kind": "Request", "op": op,
                          "request_id": f"req-{op}", "payload": payload or {}}).encode()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as cwd:  # never the repo
        out = subprocess.run([sys.executable, "-m", "theforge_doctordata", *options, op],
                             input=request, capture_output=True, timeout=120, cwd=cwd)
    assert out.returncode == 0, out.stderr
    data = json.loads(out.stdout)
    response = from_dict(Response, data)
    assert response.op == op and response.request_id == f"req-{op}"
    assert (response.producer.id, response.producer.version) == ("forge-doctor-data",
                                                                 "0.3.0")
    return response, data


def _describe(replay: Path | None = DEFAULT) -> tuple[Response, dict[str, Any]]:
    return _call("describe", () if replay is None else ("--replay", str(replay)))


def _snapshot() -> dict[str, Any]:
    return json.loads((PACKAGE / "native_surface.json").read_text("utf-8"))


def _workspace_context() -> dict[str, Any]:
    files = []
    for path in sorted(WORKSPACE.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            blob = path.read_bytes()
            files.append({"path": path.relative_to(WORKSPACE).as_posix(),
                          "sha256": hashlib.sha256(blob).hexdigest(),
                          "bytes": len(blob)})
    return {"root": str(WORKSPACE), "files": files}


def _execute(capability: str, action: str, replay: Path = DEFAULT,
             context: dict[str, Any] | None = None,
             extra: dict[str, Any] | None = None
             ) -> tuple[Response, dict[str, Any], Path]:
    """Execute in a cwd that persists past the call so artifacts can be inspected."""
    payload = {"task": {"intent": "x", "budget_profile": "economy"},
               "capability": capability, "action": action,
               "context": context if context is not None else _workspace_context()}
    payload.update(extra or {})
    request = json.dumps({"protocol": PROTOCOL_V1, "kind": "Request", "op": "execute",
                          "request_id": "req-execute", "payload": payload}).encode()
    cwd = Path(tempfile.mkdtemp())
    out = subprocess.run([sys.executable, "-m", "theforge_doctordata",
                          "--replay", str(replay), "execute"],
                         input=request, capture_output=True, timeout=120, cwd=cwd)
    assert out.returncode == 0, out.stderr
    data = json.loads(out.stdout)
    response = from_dict(Response, data)
    return response, data, cwd


def _context_of(root: Path, name: str, blob: bytes) -> dict[str, Any]:
    """A ContextPack-shaped context for one real file under ``root``."""
    (root / name).write_bytes(blob)
    return {"root": str(root),
            "files": [{"path": name, "sha256": hashlib.sha256(blob).hexdigest(),
                       "bytes": len(blob)}]}


# --- describe -------------------------------------------------------------------------------


def test_replay_describe_manifest() -> None:
    response, raw = _describe()
    assert response.status == "ok", response.error
    manifest = from_dict(ForgeManifest, response.payload)
    assert manifest.id == "forge-doctor-data" and manifest.version == "0.3.0"
    assert manifest.protocols == [PROTOCOL_V1]
    assert set(manifest.ops) == {"describe", "health", "execute", "verify"}
    assert [c.id for c in manifest.capabilities] == EXPOSED
    assert manifest.execution.local and manifest.execution.offline
    assert not manifest.execution.requires_network
    assert validate_taxonomy(manifest) == ()
    assert validate_manifest_limits(manifest) == ()
    for capability in manifest.capabilities:
        assert capability.state == "supported"
        assert capability.operation_class == "read_only"
        assert capability.description
        assert capability.signals.keywords and capability.signals.file_globs
    scan = manifest.capability("data.scan")
    verify = manifest.capability("data.verify")
    assert scan is not None and scan.actions == ["analyze"]
    assert scan.default_action == "analyze"
    # The scan emits the diagnostic artifact type a consumer can declare (wave E).
    assert scan.relations.produces == ["data.diagnostic-evidence"]
    assert verify is not None and verify.actions == ["verify"]
    # The Doctor audits sibling engineer runs through the ``verify`` op.
    assert verify.relations.can_verify == list(catalog.VERIFIES)
    assert all(ref.startswith("spark-forge/") for ref in verify.relations.can_verify)
    # Wave B surface fields on the raw payload.
    assert raw["payload"]["context_revalidation"] == "hash"
    assert raw["payload"]["adapter_version"] == "0.3.0"
    fingerprint = raw["payload"]["native_surface_fingerprint"]
    assert fingerprint == catalog.native_fingerprint(_snapshot())


def test_describe_is_deterministic() -> None:
    assert _describe()[1]["payload"] == _describe()[1]["payload"]


def test_describe_flags_a_hand_built_snapshot() -> None:
    snapshot = _snapshot()
    assert snapshot["provenance"] == "recorded"
    payload = catalog.manifest_payload({**snapshot, "provenance": "hand-built"},
                                       provider_id="forge-doctor-data", version="0.3.0")
    assert any("hand-built" in n for n in payload["limitations"])


def test_seam_absent_becomes_a_limitation_not_a_capability() -> None:
    snapshot = _snapshot()
    for seam in snapshot["seams"]:
        seam["present"] = seam["name"] != catalog.SEAM_SCAN
    payload = catalog.manifest_payload(snapshot, provider_id="forge-doctor-data",
                                       version="0.3.0")
    manifest = from_dict(ForgeManifest, payload)
    assert manifest.capability("data.scan") is None
    assert manifest.capability("data.verify") is not None
    assert any("data.scan" in n and catalog.SEAM_SCAN in n
               for n in manifest.limitations)


@pytest.mark.parametrize("scenario", ["specialist-missing"])
def test_replay_environment_replaces_the_live_checks(scenario: str) -> None:
    response, _ = _describe(SCENARIOS / scenario)
    assert response.status == "refused"
    assert response.error is not None
    assert response.error.code == "DOCTORDATA-ADAPTER-UNAVAILABLE"
    assert "forge_doctor_data is not importable" in response.error.detail
    assert "environment.json" in response.error.detail
    assert response.error.unlock


def test_replay_without_environment_is_a_missing_recording(tmp_path: Path) -> None:
    response, _ = _describe(tmp_path)
    assert response.status == "error"
    assert response.error is not None
    assert response.error.code == "ADAPTER-REPLAY-MISSING"
    assert "environment.json" in response.error.detail


def test_replay_environment_must_be_an_object(tmp_path: Path) -> None:
    (tmp_path / "environment.json").write_text('["3.11"]', encoding="utf-8")
    response, _ = _describe(tmp_path)
    assert response.status == "error"
    assert response.error is not None
    assert response.error.code == "ADAPTER-REPLAY-INVALID"


@pytest.mark.skipif(ON_311_PLUS and HAS_SPECIALIST,
                    reason="the specialist is usable in this interpreter")
def test_describe_without_replay_refuses_when_the_specialist_is_absent() -> None:
    response, _ = _describe(None)
    assert response.status == "refused"
    assert response.error is not None
    assert response.error.code == "DOCTORDATA-ADAPTER-UNAVAILABLE"
    assert response.error.unlock


# --- catalog / snapshot ---------------------------------------------------------------------


def test_snapshot_shape_and_canonical_encoding() -> None:
    snapshot = _snapshot()
    assert snapshot["specialist_version"] == "1.0.0rc1"
    assert snapshot["provenance"] == "recorded"
    assert snapshot["recorded_at"]
    names = [seam["name"] for seam in snapshot["seams"]]
    assert len(names) == len(set(names))
    assert {catalog.SEAM_SCAN, catalog.SEAM_CONFORMANCE} <= set(names)
    raw = (PACKAGE / "native_surface.json").read_bytes()
    assert b"\r\n" not in raw and raw.endswith(b"\n")


def test_native_fingerprint_ignores_recorded_at() -> None:
    snapshot = _snapshot()
    later = {**snapshot, "recorded_at": "2999-01-01T00:00:00Z"}
    assert catalog.native_fingerprint(later) == catalog.native_fingerprint(snapshot)
    different = {**snapshot, "seams": []}
    assert catalog.native_fingerprint(different) != catalog.native_fingerprint(snapshot)


def test_record_check_classifies_drift() -> None:
    snapshot = _snapshot()
    assert record.classify_drift(snapshot, snapshot) == ("none", [])
    added = {**snapshot, "seams": [*snapshot["seams"], {
        "name": "new_seam", "module": "m", "callable": "c", "present": True,
        "parameters": []}]}
    status, lines = record.classify_drift(snapshot, added)
    assert status == "additive" and lines == ["seam added: new_seam"]
    missing = {**snapshot, "seams": snapshot["seams"][1:]}
    status, lines = record.classify_drift(snapshot, missing)
    assert status == "breaking" and lines[0].startswith("seam removed:")
    dropped = {**snapshot, "request_kinds": []}
    status, lines = record.classify_drift(snapshot, dropped)
    assert status == "breaking" and "request kind removed: scan" in lines
    bumped = {**snapshot, "contract_version": "forge-contracts/2"}
    status, lines = record.classify_drift(snapshot, bumped)
    assert status == "breaking" and any("contract_version" in line for line in lines)
    versioned = {**snapshot, "specialist_version": "9.9.9"}
    status, lines = record.classify_drift(snapshot, versioned)
    assert status == "additive" and any("specialist version" in line for line in lines)


def _valid_snapshot() -> dict[str, Any]:
    return {"specialist_version": "1.0.0rc1", "recorded_at": "2026-10-03T00:00:00Z",
            "provenance": "recorded", "contract_version": "forge-contracts/1",
            "seams": [{"name": "accept_request",
                       "module": "forge_doctor_data.core.forger",
                       "callable": "accept_request", "present": True}]}


@pytest.mark.parametrize(("content", "message"), [
    (b"{not json", "unreadable"),
    (b"\xff\xfe", "unreadable"),
    (b"[]", "expected an object"),
    (json.dumps({k: v for k, v in _valid_snapshot().items()
                 if k != "provenance"}).encode(), "provenance"),
    (json.dumps({**_valid_snapshot(), "seams": {}}).encode(), "seams"),
    (json.dumps({**_valid_snapshot(), "seams": ["x"]}).encode(), "seams[0]"),
    (json.dumps({**_valid_snapshot(), "seams": [
        {"name": "a", "module": "m", "callable": "c", "present": "yes"}]}).encode(),
     "present"),
])
def test_load_snapshot_rejects_corrupt_files(tmp_path: Path, content: bytes,
                                             message: str) -> None:
    path = tmp_path / "native_surface.json"
    path.write_bytes(content)
    with pytest.raises(catalog.SnapshotError, match=re.escape(message)):
        catalog.load_snapshot(path)


def test_corrupt_snapshot_makes_describe_an_error(tmp_path: Path,
                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "native_surface.json"
    path.write_bytes(json.dumps({**_valid_snapshot(), "seams": {}}).encode())
    entry = importlib.import_module("theforge_doctordata.__main__")
    monkeypatch.setattr(entry, "load_snapshot", lambda: catalog.load_snapshot(path))
    handler = entry.describe(_shell.AdapterOptions(replay=DEFAULT))
    reply = handler(_shell.Request(op="describe", request_id="r", protocol=PROTOCOL_V1,
                                   payload={}), tmp_path)
    assert reply.status == "error"
    assert reply.error is not None
    assert reply.error["code"] == "DOCTORDATA-ADAPTER-SNAPSHOT-INVALID"
    assert reply.error["unlock"]


# --- health ---------------------------------------------------------------------------------


def _health(options: tuple[str, ...] = ("--replay", str(DEFAULT))
            ) -> tuple[Response, HealthReport]:
    response, _ = _call("health", options)
    assert response.status == "ok", response.error
    return response, from_dict(HealthReport, response.payload, "$.payload")


def _checks(report: HealthReport) -> dict[str, HealthCheck]:
    return {check.name: check for check in report.checks}


def test_replay_default_health_is_ok() -> None:
    _, report = _health()
    checks = _checks(report)
    assert list(checks) == CHECKS
    assert checks["python"].ok and "3.11" in checks["python"].detail
    assert checks["import"].ok and "1.0.0rc1" in checks["import"].detail
    assert checks["version"].ok
    assert checks["boundary"].ok and "forge_doctor_data.core.forger" in \
        checks["boundary"].detail
    assert report.status == "ok"


def test_replay_health_version_skew_is_degraded() -> None:
    _, report = _health(("--replay", str(SCENARIOS / "version-skew")))
    checks = _checks(report)
    assert report.status == "degraded"
    assert not checks["version"].ok and "2.4.0" in checks["version"].detail
    assert checks["boundary"].ok


def test_replay_health_without_the_boundary_is_unavailable() -> None:
    _, report = _health(("--replay", str(SCENARIOS / "boundary-missing")))
    checks = _checks(report)
    assert report.status == "unavailable"
    assert not checks["boundary"].ok and "forge_doctor_data" in checks["boundary"].detail


def test_replay_health_without_the_specialist_is_unavailable() -> None:
    _, report = _health(("--replay", str(SCENARIOS / "specialist-missing")))
    report_checks = _checks(report)
    assert report.status == "unavailable"
    assert not report_checks["import"].ok
    assert "version" not in report_checks and "boundary" not in report_checks


def test_assume_specialist_version_overrides_the_probe() -> None:
    _, report = _health(("--replay", str(SCENARIOS / "version-skew"),
                         "--assume-specialist-version", "1.2.3"))
    checks = _checks(report)
    assert report.status == "ok"
    assert checks["version"].ok and "1.2.3" in checks["version"].detail
    assert "assumed" in checks["version"].detail


def test_in_window_parses_release_candidates() -> None:
    window = ">=1.0.0rc1,<2.0.0"
    assert health.in_window("1.0.0rc1", window) is True
    assert health.in_window("1.0.0", window) is True
    assert health.in_window("1.5.2", window) is True
    assert health.in_window("0.9.9", window) is False
    assert health.in_window("1.0.0rc0", window) is False  # rc0 < rc1
    assert health.in_window("2.0.0", window) is False
    assert health.in_window("not.a.version", window) is None
    with pytest.raises(ValueError):
        health.in_window("1.0.0", ">=banana")


# --- execute (replay) -----------------------------------------------------------------------


PRODUCER = Producer(id="forge-doctor-data", version="0.3.0")


def _result(response: Response, *, expect_ok: bool = True) -> ExecutionResult:
    if expect_ok:
        assert response.status == "ok", response.error
    result = from_dict(ExecutionResult, response.payload, "$.payload")
    validate_result(result, expected=PRODUCER)
    return result


def test_replay_scan_translates_the_handoff_bundle() -> None:
    response, _, cwd = _execute("data.scan", "analyze")
    result = _result(response)
    assert result.status == "ok"
    assert result.findings, "the recorded scan carries findings"
    assert result.evidence
    finding_ids = {finding.id for finding in result.findings}
    for finding in result.findings:
        assert finding.evidence_ids and set(finding.evidence_ids) <= {
            ev.id for ev in result.evidence}
        assert finding.severity in ("info", "low", "medium", "high", "critical")
    assert finding_ids != {""}
    # The handoff document is the declared artifact; its hash is verified content.
    assert [a.path for a in result.artifacts] == ["native/handoff.json"]
    artifact = cwd / "native" / "handoff.json"
    assert artifact.is_file()
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == result.artifacts[0].sha256
    bundle = json.loads(artifact.read_text("utf-8"))
    assert bundle["contract_version"] == "forge-contracts/1"
    assert isinstance(bundle["findings"], list) and bundle["findings"]


def test_replay_scan_preserves_unknowns_and_emits_no_machine_paths() -> None:
    response, raw, _ = _execute("data.scan", "analyze")
    result = _result(response)
    assert result.unknowns, "unknown capabilities are explicit, not dropped"
    assert all(isinstance(u, str) and u for u in result.unknowns)
    blob = json.dumps(raw["payload"])
    assert str(WORKSPACE) not in blob and "C:\\" not in blob and "\\Users\\" not in blob


def test_replay_verify_reports_conformance_of_the_staged_payload() -> None:
    bundle = json.loads((DEFAULT / "data.scan.analyze.json").read_text("utf-8"))
    blob = json.dumps(bundle, sort_keys=True).encode()
    digest = hashlib.sha256(blob).hexdigest()
    source = Path(tempfile.mkdtemp())
    response, _, cwd = _execute("data.verify", "verify",
                               context=_context_of(source, "bundle.json", blob))
    result = _result(response)
    assert result.status == "ok"
    verdict_evidence = [ev for ev in result.evidence if "conformance" in ev.id
                        or "conformance" in ev.subject]
    assert verdict_evidence
    # The evidence hash binds to the verified staged payload, not the verdict artifact.
    assert any(ev.hash == digest for ev in verdict_evidence)
    assert (cwd / "native" / "handoff.json").is_file()


def test_replay_verify_needs_a_staged_payload() -> None:
    source = Path(tempfile.mkdtemp())
    response, _, _ = _execute("data.verify", "verify",
                             context=_context_of(source, "readme.md", b"hello"))
    result = _result(response, expect_ok=False)
    assert result.status == "partial"


def test_replay_error_recording_is_a_structured_failure() -> None:
    response, _, _ = _execute("data.scan", "analyze", SCENARIOS / "native-error")
    assert response.status == "error"
    assert response.error is not None
    assert response.error.code == "FDD-NATIVE-FAILURE"
    assert "simulated specialist failure" in response.error.detail


def test_replay_without_a_recording_is_missing(tmp_path: Path) -> None:
    (tmp_path / "environment.json").write_text(
        json.dumps({"python": "3.11.15", "specialist_version": "1.0.0rc1"}),
        encoding="utf-8")
    (tmp_path / "health.json").write_text('{"boundary": true}', encoding="utf-8")
    response, _, _ = _execute("data.scan", "analyze", tmp_path)
    assert response.status == "error"
    assert response.error is not None
    assert response.error.code == "ADAPTER-REPLAY-MISSING"
    assert "data.scan.analyze.json" in response.error.detail


def test_scan_with_no_input_is_partial() -> None:
    response, _, _ = _execute("data.scan", "analyze",
                             context={"root": str(WORKSPACE), "files": []})
    result = _result(response, expect_ok=False)
    assert result.status == "partial"


def test_bounded_options_are_refused_when_malformed() -> None:
    response, _, _ = _execute("data.scan", "analyze",
                             extra={"options": {"bounded": {"findings": -1}}})
    assert response.status == "refused"
    assert response.error is not None
    assert response.error.field == "options.bounded"


# --- verify op (cycle 3.1 wave E): independent verification ----------------------------------

SHA = "a" * 64


def _verify_payload(result: dict[str, Any], handoff: dict[str, Any] | None = None
                    ) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "task": {"schema": "theforge/TaskSpec/v1", "id": "t1", "intent": "x",
                 "targets": []},
        "capability": "pyspark.static-analysis", "action": "pyspark",
        "run_id": "run-1", "result": result}
    if handoff is not None:
        payload["handoff"] = handoff
    return payload


def _clean_result(**over: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema": "theforge/ExecutionResult/v1",
        "producer": {"id": "spark-forge", "version": "0.2.0"},
        "capability": "pyspark.static-analysis", "action": "pyspark",
        "status": "ok",
        "evidence": [{"id": "e1", "epistemic": "observed",
                      "subject": "job", "claim": "saw it",
                      "producer": {"id": "spark-forge", "version": "0.2.0"}}],
        "findings": [{"id": "f1", "title": "t", "severity": "low",
                      "evidence_ids": ["e1"]}],
        "artifacts": [], "limitations": [], "unknowns": [], "assumptions": []}
    result.update(over)
    return result


def _verify(payload: dict[str, Any], replay: Path = DEFAULT
            ) -> tuple[Response, dict[str, Any]]:
    return _call("verify", ("--replay", str(replay)), payload)


def test_verify_op_passes_a_coherent_result() -> None:
    response, _ = _verify(_verify_payload(_clean_result()))
    assert response.status == "ok", response.error
    verdict = response.payload
    assert verdict["status"] == "passed"
    assert verdict["details"] == ["result-coherence: passed"]
    assert verdict["basis"] == ["forge-doctor-data/coherence-audit"]


def test_verify_op_fails_a_finding_without_evidence() -> None:
    result = _clean_result(findings=[{"id": "f1", "title": "t", "severity": "low"}])
    response, _ = _verify(_verify_payload(result))
    assert response.status == "ok"
    assert response.payload["status"] == "failed"
    assert any("f1" in detail and "evidence" in detail
               for detail in response.payload["details"])


def test_verify_op_fails_an_unverifiable_evidence_hash() -> None:
    evidence = [{"id": "e1", "epistemic": "observed", "subject": "s",
                 "claim": "c", "hash": SHA}]
    response, _ = _verify(_verify_payload(_clean_result(evidence=evidence)))
    assert response.payload["status"] == "failed"
    assert any("hash without location" in detail
               for detail in response.payload["details"])


def test_verify_op_fails_a_dangling_evidence_ref() -> None:
    result = _clean_result(
        findings=[{"id": "f1", "title": "t", "severity": "low",
                   "evidence_ids": ["ghost"]}])
    response, _ = _verify(_verify_payload(result))
    assert response.payload["status"] == "failed"
    assert any("ghost" in detail for detail in response.payload["details"])


def _handoff(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"schema": "theforge/Handoff/v1",
            "producer": {"id": "theforge", "version": "0.2.0"},
            "created_at": "2026-01-01T00:00:00Z", "plan_run": "p1",
            "target_node": "n2", "items": items}


def _item(**over: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "kind": "evidence", "id": "e1",
        "origin": {"plan_run": "p1", "node": "n1", "run_id": "r1",
                   "provider": {"id": "forge-doctor-data", "version": "0.3.0"}},
        "epistemic": "observed", "subject": "s", "claim": "c"}
    item.update(over)
    return item


def test_verify_op_audits_the_consumed_handoff() -> None:
    handoff = _handoff([
        _item(),
        _item(kind="artifact", id="out.json", hash=SHA, epistemic=None),
    ])
    response, _ = _verify(_verify_payload(_clean_result(), handoff))
    assert response.payload["status"] == "passed"
    assert response.payload["details"] == ["result-coherence: passed",
                                           "handoff-coherence: passed"]


def test_verify_op_fails_a_handoff_artifact_without_hash() -> None:
    handoff = _handoff([_item(kind="artifact", id="out.json", epistemic=None)])
    response, _ = _verify(_verify_payload(_clean_result(), handoff))
    assert response.payload["status"] == "failed"
    assert any("hash is required" in detail
               for detail in response.payload["details"])


def test_verify_op_fails_handoff_evidence_without_epistemic() -> None:
    item = _item()
    del item["epistemic"]
    response, _ = _verify(_verify_payload(_clean_result(), _handoff([item])))
    assert response.payload["status"] == "failed"
    assert any("epistemic is required" in detail
               for detail in response.payload["details"])


def test_verify_op_never_upgrades_epistemic() -> None:
    """The verdict describes the verification, never the claim's truth."""
    result = _clean_result()  # observed evidence
    response, _ = _verify(_verify_payload(result))
    assert response.payload["status"] == "passed"
    # no epistemic field exists on a verdict — the producer's claims stand
    assert "epistemic" not in response.payload


def test_verify_op_rejects_a_non_object_payload() -> None:
    # A scalar payload fails at request parsing, before the handler runs.
    response, _ = _verify("nope")
    assert response.status == "error"
    assert response.error is not None
    assert response.error.code == "ADAPTER-REQUEST-INVALID"


@pytest.mark.parametrize("payload", [
    {"result": "nope"},
    {"task": {}, "capability": "x", "action": "y", "run_id": "r"},
])
def test_verify_op_refuses_a_malformed_payload(payload: Any) -> None:
    response, _ = _verify(payload)
    assert response.status == "refused"
    assert response.error is not None
    assert response.error.code == "ADAPTER-REQUEST-INVALID"


def test_verify_op_refuses_without_the_specialist() -> None:
    response, _ = _verify(_verify_payload(_clean_result()),
                          SCENARIOS / "specialist-missing")
    assert response.status == "refused"
    assert response.error is not None
    assert response.error.code == "DOCTORDATA-ADAPTER-UNAVAILABLE"
