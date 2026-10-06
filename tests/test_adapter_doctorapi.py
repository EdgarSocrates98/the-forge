"""Forge Doctor API adapter (cycle 3.1, phases 11-12): the spec-070 boundary as a provider.

The adapter derives ``describe`` from ``native_surface.json`` (a snapshot of the specialist's
public seams): a capability is exposed only when the seam it drives is recorded present.
Live, the interpreter must be Python >= 3.11 with ``forge_doctor_api`` importable; with
``--replay <dir>`` the scenario's ``environment.json`` answers instead and recordings replace
the bridge runs. ``api.diagnose`` drives ``DoctorBoundary`` (``handle`` + ``endpoint_dict``)
into a bounded ``ApiHandoffBundle`` v2 plus the ``ForgeHandoff`` envelope; ``api.verify``
strict-parses a staged document and recomputes ``body_sha256`` for v2 bundles. Both translate
into the Evidence Bus without the core knowing anything about API internals.
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
from theforge_doctorapi import _shell, catalog, health

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
PACKAGE = REPO / "adapters" / "doctorapi" / "src" / "theforge_doctorapi"
NATIVE = REPO / "tests" / "fixtures" / "native" / "doctorapi"
DEFAULT = NATIVE / "default"
SCENARIOS = NATIVE / "scenarios"
WORKSPACE = REPO / "tests" / "fixtures" / "workspaces" / "cross" / "orders-api"
EXPOSED = ["api.diagnose", "api.verify"]
CHECKS = ["python", "import", "version", "boundary"]
ON_311_PLUS = sys.version_info[:2] >= (3, 11)
HAS_SPECIALIST = importlib.util.find_spec("forge_doctor_api") is not None


def _call(op: str, options: tuple[str, ...] = (), payload: dict[str, Any] | None = None
          ) -> tuple[Response, dict[str, Any]]:
    request = json.dumps({"protocol": PROTOCOL_V1, "kind": "Request", "op": op,
                          "request_id": f"req-{op}", "payload": payload or {}}).encode()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as cwd:  # never the repo
        out = subprocess.run([sys.executable, "-m", "theforge_doctorapi", *options, op],
                             input=request, capture_output=True, timeout=120, cwd=cwd)
    assert out.returncode == 0, out.stderr
    data = json.loads(out.stdout)
    response = from_dict(Response, data)
    assert response.op == op and response.request_id == f"req-{op}"
    assert (response.producer.id, response.producer.version) == ("forge-doctor-api",
                                                                 "0.2.0")
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
    out = subprocess.run([sys.executable, "-m", "theforge_doctorapi",
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
    assert manifest.id == "forge-doctor-api" and manifest.version == "0.2.0"
    assert manifest.protocols == [PROTOCOL_V1]
    assert set(manifest.ops) >= {"describe", "health", "execute"}
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
    diagnose = manifest.capability("api.diagnose")
    verify = manifest.capability("api.verify")
    assert diagnose is not None and diagnose.actions == ["analyze"]
    assert verify is not None and verify.actions == ["verify"]
    # Wave B surface fields on the raw payload.
    assert raw["payload"]["context_revalidation"] == "hash"
    assert raw["payload"]["adapter_version"] == "0.2.0"
    fingerprint = raw["payload"]["native_surface_fingerprint"]
    assert fingerprint == catalog.native_fingerprint(_snapshot())


def test_describe_is_deterministic() -> None:
    assert _describe()[1]["payload"] == _describe()[1]["payload"]


def test_describe_flags_a_hand_built_snapshot() -> None:
    snapshot = _snapshot()
    assert snapshot["provenance"] == "recorded"
    payload = catalog.manifest_payload({**snapshot, "provenance": "hand-built"},
                                       provider_id="forge-doctor-api", version="0.2.0")
    assert any("hand-built" in n for n in payload["limitations"])


def test_seam_absent_becomes_a_limitation_not_a_capability() -> None:
    snapshot = _snapshot()
    for seam in snapshot["seams"]:
        seam["present"] = seam["name"] != catalog.SEAM_DIAGNOSE
    payload = catalog.manifest_payload(snapshot, provider_id="forge-doctor-api",
                                       version="0.2.0")
    manifest = from_dict(ForgeManifest, payload)
    assert manifest.capability("api.diagnose") is None
    assert manifest.capability("api.verify") is not None
    assert any("api.diagnose" in n and catalog.SEAM_DIAGNOSE in n
               for n in manifest.limitations)


def test_replay_environment_replaces_the_live_checks() -> None:
    response, _ = _describe(SCENARIOS / "specialist-missing")
    assert response.status == "refused"
    assert response.error is not None
    assert response.error.code == "DOCTORAPI-ADAPTER-UNAVAILABLE"
    assert "forge_doctor_api is not importable" in response.error.detail
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
    assert response.error.code == "DOCTORAPI-ADAPTER-UNAVAILABLE"
    assert response.error.unlock


# --- catalog / snapshot ---------------------------------------------------------------------


def test_snapshot_shape_and_canonical_encoding() -> None:
    snapshot = _snapshot()
    assert snapshot["specialist_version"] == "0.2.0"
    assert snapshot["provenance"] == "recorded"
    assert snapshot["recorded_at"]
    assert snapshot["protocol_version"] == 2
    names = [seam["name"] for seam in snapshot["seams"]]
    assert len(names) == len(set(names))
    assert {catalog.SEAM_DIAGNOSE, catalog.SEAM_VERIFY} <= set(names)
    raw = (PACKAGE / "native_surface.json").read_bytes()
    assert b"\r\n" not in raw and raw.endswith(b"\n")


def test_native_fingerprint_ignores_recorded_at() -> None:
    snapshot = _snapshot()
    later = {**snapshot, "recorded_at": "2999-01-01T00:00:00Z"}
    assert catalog.native_fingerprint(later) == catalog.native_fingerprint(snapshot)
    different = {**snapshot, "seams": []}
    assert catalog.native_fingerprint(different) != catalog.native_fingerprint(snapshot)


def _valid_snapshot() -> dict[str, Any]:
    return {"specialist_version": "0.2.0", "recorded_at": "2026-10-03T00:00:00Z",
            "provenance": "recorded", "protocol_version": 2,
            "seams": [{"name": "doctor_boundary",
                       "module": "forge_doctor_api.handoff.boundary",
                       "callable": "DoctorBoundary", "present": True}]}


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
    (json.dumps({**_valid_snapshot(), "seams": [
        _valid_snapshot()["seams"][0], _valid_snapshot()["seams"][0]]}).encode(),
     "duplicate seam"),
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
    entry = importlib.import_module("theforge_doctorapi.__main__")
    monkeypatch.setattr(entry, "load_snapshot", lambda: catalog.load_snapshot(path))
    handler = entry.describe(_shell.AdapterOptions(replay=DEFAULT))
    reply = handler(_shell.Request(op="describe", request_id="r", protocol=PROTOCOL_V1,
                                   payload={}), tmp_path)
    assert reply.status == "error"
    assert reply.error is not None
    assert reply.error["code"] == "DOCTORAPI-ADAPTER-SNAPSHOT-INVALID"
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
    assert checks["import"].ok and "0.2.0" in checks["import"].detail
    assert checks["version"].ok
    assert checks["boundary"].ok and "forge_doctor_api.handoff.boundary" in \
        checks["boundary"].detail
    assert report.status == "ok"


def test_replay_health_version_skew_is_degraded() -> None:
    _, report = _health(("--replay", str(SCENARIOS / "version-skew")))
    checks = _checks(report)
    assert report.status == "degraded"
    assert not checks["version"].ok and "0.9.9" in checks["version"].detail
    assert checks["boundary"].ok


def test_replay_health_without_the_boundary_is_unavailable() -> None:
    _, report = _health(("--replay", str(SCENARIOS / "boundary-missing")))
    checks = _checks(report)
    assert report.status == "unavailable"
    assert not checks["boundary"].ok and "forge_doctor_api" in checks["boundary"].detail


def test_replay_health_without_the_specialist_is_unavailable() -> None:
    _, report = _health(("--replay", str(SCENARIOS / "specialist-missing")))
    report_checks = _checks(report)
    assert report.status == "unavailable"
    assert not report_checks["import"].ok
    assert "version" not in report_checks and "boundary" not in report_checks


def test_assume_specialist_version_overrides_the_probe() -> None:
    _, report = _health(("--replay", str(SCENARIOS / "version-skew"),
                         "--assume-specialist-version", "0.2.1"))
    checks = _checks(report)
    assert report.status == "ok"
    assert checks["version"].ok and "0.2.1" in checks["version"].detail
    assert "assumed" in checks["version"].detail


def test_in_window_plain_semver() -> None:
    window = ">=0.2.0,<0.3.0"
    assert health.in_window("0.2.0", window) is True
    assert health.in_window("0.2.9", window) is True
    assert health.in_window("0.3.0", window) is False
    assert health.in_window("0.1.0", window) is False
    assert health.in_window("banana", window) is None


# --- execute (replay) -----------------------------------------------------------------------


PRODUCER = Producer(id="forge-doctor-api", version="0.2.0")


def _result(response: Response, *, expect_ok: bool = True) -> ExecutionResult:
    if expect_ok:
        assert response.status == "ok", response.error
    result = from_dict(ExecutionResult, response.payload, "$.payload")
    validate_result(result, expected=PRODUCER)
    return result


def test_replay_diagnose_translates_the_bundle() -> None:
    response, _, cwd = _execute("api.diagnose", "analyze")
    result = _result(response)
    assert result.status == "ok"
    assert result.findings, "the recorded diagnose carries findings"
    assert result.evidence
    evidence_ids = {ev.id for ev in result.evidence}
    for finding in result.findings:
        assert finding.evidence_ids and set(finding.evidence_ids) <= evidence_ids
        assert finding.severity in ("info", "low", "medium", "high", "critical")
    # The bridge document is the declared artifact; its hash is verified content.
    assert [a.path for a in result.artifacts] == ["native/handoff.json"]
    artifact = cwd / "native" / "handoff.json"
    assert artifact.is_file()
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == result.artifacts[0].sha256
    document = json.loads(artifact.read_text("utf-8"))
    assert document["bundle"]["handoff_version"] == 2
    assert document["handoff"]["handoff_id"] == document["bundle"]["handoff_id"]


def test_replay_diagnose_preserves_unknowns_and_emits_no_machine_paths() -> None:
    response, raw, _ = _execute("api.diagnose", "analyze")
    result = _result(response)
    assert result.unknowns, "UNKNOWN-confidence findings carry explicit unknowns"
    assert all(isinstance(u, str) and u for u in result.unknowns)
    assert any("resolve:" in u for u in result.unknowns)
    blob = json.dumps(raw["payload"])
    assert str(WORKSPACE) not in blob and "C:\\" not in blob and "\\Users\\" not in blob


def test_replay_diagnose_maps_envelope_and_manifest_evidence() -> None:
    response, _, _ = _execute("api.diagnose", "analyze")
    result = _result(response)
    subjects = {ev.subject for ev in result.evidence}
    ids = {ev.id for ev in result.evidence}
    assert "handoff-envelope" in ids or "handoff" in subjects
    # Evidence.hash binds only to ContextPack content; artifact provenance lives in
    # artifacts[] and in the claim text, so the envelope evidence hash stays null.
    envelope = [ev for ev in result.evidence if ev.id == "handoff-envelope"]
    assert envelope and envelope[0].hash is None and envelope[0].location is None
    assert "native/handoff.json" in envelope[0].claim
    assert result.artifacts and result.artifacts[0].sha256


def test_replay_verify_reports_integrity_of_the_staged_bundle() -> None:
    document = json.loads((DEFAULT / "api.diagnose.analyze.json").read_text("utf-8"))
    blob = json.dumps(document["bundle"], sort_keys=True).encode()
    digest = hashlib.sha256(blob).hexdigest()
    source = Path(tempfile.mkdtemp())
    response, _, cwd = _execute("api.verify", "verify",
                               context=_context_of(source, "bundle.json", blob))
    result = _result(response)
    assert result.status == "ok"
    verdict = [ev for ev in result.evidence
               if "integrity" in ev.claim or "valid" in ev.claim or ev.hash == digest]
    assert verdict
    assert (cwd / "native" / "handoff.json").is_file()


def test_replay_verify_needs_a_staged_payload() -> None:
    source = Path(tempfile.mkdtemp())
    response, _, _ = _execute("api.verify", "verify",
                             context=_context_of(source, "readme.md", b"hello"))
    result = _result(response, expect_ok=False)
    assert result.status == "partial"


def test_replay_error_recording_is_a_structured_failure() -> None:
    response, _, _ = _execute("api.diagnose", "analyze", SCENARIOS / "native-error")
    assert response.status == "error"
    assert response.error is not None
    assert response.error.code == "FDA-NATIVE-FAILURE"
    assert "simulated specialist failure" in response.error.detail


def test_replay_without_a_recording_is_missing(tmp_path: Path) -> None:
    (tmp_path / "environment.json").write_text(
        json.dumps({"python": "3.11.15", "specialist_version": "0.2.0"}),
        encoding="utf-8")
    (tmp_path / "health.json").write_text('{"boundary": true}', encoding="utf-8")
    response, _, _ = _execute("api.diagnose", "analyze", tmp_path)
    assert response.status == "error"
    assert response.error is not None
    assert response.error.code == "ADAPTER-REPLAY-MISSING"
    assert "api.diagnose.analyze.json" in response.error.detail


def test_diagnose_with_no_input_is_partial() -> None:
    response, _, _ = _execute("api.diagnose", "analyze",
                             context={"root": str(WORKSPACE), "files": []})
    result = _result(response, expect_ok=False)
    assert result.status == "partial"
