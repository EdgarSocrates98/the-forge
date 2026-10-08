"""Spark Forge Azure adapter: handoff over the public boundary.

The adapter derives ``describe`` from ``native_surface.json`` (a snapshot of the
specialist's public seams): a capability is exposed only when the seam it drives is
recorded present. Live, the interpreter must be Python >= 3.10 with ``sparkforge_azure``
importable; with ``--replay <dir>`` the scenario's ``environment.json`` answers instead
and recordings replace the bridge runs. ``sdd.check``/``sdd.status`` drive the SDD gate
over a staged ``docs/sdd`` tree; ``azure.access-diagnose``/``fabric.access-diagnose`` run
the offline access pipelines over a staged case bundle; ``azure.doctor`` runs the
specialist's own environment report.
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
from theforge_sparkforge_azure import _shell, catalog, health, record

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
PACKAGE = REPO / "adapters" / "sparkforge_azure" / "src" / "theforge_sparkforge_azure"
NATIVE = REPO / "tests" / "fixtures" / "native" / "sparkforge_azure"
DEFAULT = NATIVE / "default"
SCENARIOS = NATIVE / "scenarios"
WORKSPACES = REPO / "tests" / "fixtures" / "workspaces" / "azure"
SDD_LIMPO = WORKSPACES / "sdd-limpo"
ACCESS_CASE = WORKSPACES / "access-case"
FABRIC_CASE = WORKSPACES / "fabric-case"
EXPOSED = [
    "azure.access-diagnose",
    "azure.doctor",
    "fabric.access-diagnose",
    "sdd.check",
    "sdd.status",
]
CHECKS = ["python", "import", "version", "boundary"]
ON_310_PLUS = sys.version_info[:2] >= (3, 10)
HAS_SPECIALIST = importlib.util.find_spec("sparkforge_azure") is not None


def _call(
    op: str, options: tuple[str, ...] = (), payload: dict[str, Any] | None = None
) -> tuple[Response, dict[str, Any]]:
    request = json.dumps(
        {
            "protocol": PROTOCOL_V1,
            "kind": "Request",
            "op": op,
            "request_id": f"req-{op}",
            "payload": payload or {},
        }
    ).encode()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as cwd:  # never the repo
        out = subprocess.run(
            [sys.executable, "-m", "theforge_sparkforge_azure", *options, op],
            input=request,
            capture_output=True,
            timeout=120,
            cwd=cwd,
        )
    assert out.returncode == 0, out.stderr
    data = json.loads(out.stdout)
    response = from_dict(Response, data)
    assert response.op == op and response.request_id == f"req-{op}"
    assert (response.producer.id, response.producer.version) == ("spark-forge-azure", "0.1.0")
    return response, data


def _describe(replay: Path | None = DEFAULT) -> tuple[Response, dict[str, Any]]:
    return _call("describe", () if replay is None else ("--replay", str(replay)))


def _snapshot() -> dict[str, Any]:
    return json.loads((PACKAGE / "native_surface.json").read_text("utf-8"))


def _workspace_context(root: Path) -> dict[str, Any]:
    files = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            blob = path.read_bytes()
            files.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "sha256": hashlib.sha256(blob).hexdigest(),
                    "bytes": len(blob),
                }
            )
    return {"root": str(root), "files": files}


def _execute(
    capability: str,
    action: str,
    replay: Path = DEFAULT,
    context: dict[str, Any] | None = None,
    workspace: Path = SDD_LIMPO,
    extra: dict[str, Any] | None = None,
) -> tuple[Response, dict[str, Any], Path]:
    """Execute in a cwd that persists past the call so artifacts can be inspected."""
    payload = {
        "task": {"intent": "x", "budget_profile": "economy"},
        "capability": capability,
        "action": action,
        "context": context if context is not None else _workspace_context(workspace),
    }
    payload.update(extra or {})
    request = json.dumps(
        {
            "protocol": PROTOCOL_V1,
            "kind": "Request",
            "op": "execute",
            "request_id": "req-execute",
            "payload": payload,
        }
    ).encode()
    cwd = Path(tempfile.mkdtemp())
    out = subprocess.run(
        [sys.executable, "-m", "theforge_sparkforge_azure", "--replay", str(replay), "execute"],
        input=request,
        capture_output=True,
        timeout=120,
        cwd=cwd,
    )
    assert out.returncode == 0, out.stderr
    data = json.loads(out.stdout)
    response = from_dict(Response, data)
    return response, data, cwd


def _context_of(root: Path, name: str, blob: bytes) -> dict[str, Any]:
    """A ContextPack-shaped context for one real file under ``root``."""
    (root / name).parent.mkdir(parents=True, exist_ok=True)
    (root / name).write_bytes(blob)
    return {
        "root": str(root),
        "files": [{"path": name, "sha256": hashlib.sha256(blob).hexdigest(), "bytes": len(blob)}],
    }


# --- describe -------------------------------------------------------------------------------


def test_replay_describe_manifest() -> None:
    response, raw = _describe()
    assert response.status == "ok", response.error
    manifest = from_dict(ForgeManifest, response.payload)
    assert manifest.id == "spark-forge-azure" and manifest.version == "0.1.0"
    assert manifest.protocols == [PROTOCOL_V1]
    assert set(manifest.ops) == {"describe", "health", "execute"}
    assert [c.id for c in manifest.capabilities] == EXPOSED
    assert manifest.execution.local and manifest.execution.offline
    assert not manifest.execution.requires_network
    assert validate_taxonomy(manifest) == ()
    assert validate_manifest_limits(manifest) == ()
    for capability in manifest.capabilities:
        assert capability.state == "supported"
        assert capability.operation_class == "read_only"
        assert capability.description
    check = manifest.capability("sdd.check")
    diagnose = manifest.capability("azure.access-diagnose")
    doctor = manifest.capability("azure.doctor")
    assert check is not None and check.actions == ["check"]
    assert check.relations.produces == [catalog.SDD_REPORT]
    assert diagnose is not None and diagnose.actions == ["analyze"]
    assert diagnose.relations.produces == [catalog.ACCESS_DIAGNOSIS]
    assert doctor is not None and doctor.actions == ["report"]
    # The manifest surfaces the recorded Azure domain vocabulary, not AWS aliases:
    # no signal keyword may name AWS-native services as if they were equivalent.
    assert "azure" in manifest.domains
    for capability in manifest.capabilities:
        for keyword in capability.signals.keywords:
            assert "aws" not in keyword.lower()
            assert "boto" not in keyword.lower()
            assert keyword.lower() != "s3"
    assert raw["payload"]["context_revalidation"] == "hash"
    assert raw["payload"]["adapter_version"] == "0.1.0"
    fingerprint = raw["payload"]["native_surface_fingerprint"]
    assert fingerprint == catalog.native_fingerprint(_snapshot())


def test_describe_is_deterministic() -> None:
    assert _describe()[1]["payload"] == _describe()[1]["payload"]


def test_describe_flags_a_hand_built_snapshot() -> None:
    snapshot = _snapshot()
    assert snapshot["provenance"] == "recorded"
    payload = catalog.manifest_payload(
        {**snapshot, "provenance": "hand-built"},
        provider_id="spark-forge-azure",
        version="0.1.0",
    )
    assert any("hand-built" in n for n in payload["limitations"])


def test_seam_absent_becomes_a_limitation_not_a_capability() -> None:
    snapshot = _snapshot()
    for seam in snapshot["seams"]:
        seam["present"] = seam["name"] != catalog.SEAM_SDD_CHECK
    payload = catalog.manifest_payload(snapshot, provider_id="spark-forge-azure", version="0.1.0")
    manifest = from_dict(ForgeManifest, payload)
    assert manifest.capability("sdd.check") is None
    assert manifest.capability("sdd.status") is not None
    assert any("sdd.check" in n and catalog.SEAM_SDD_CHECK in n for n in manifest.limitations)


@pytest.mark.parametrize("scenario", ["specialist-missing"])
def test_replay_environment_replaces_the_live_checks(scenario: str) -> None:
    response, _ = _describe(SCENARIOS / scenario)
    assert response.status == "refused"
    assert response.error is not None
    assert response.error.code == "SPARKFORGE_AZURE-ADAPTER-UNAVAILABLE"
    assert "sparkforge_azure is not importable" in response.error.detail
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


@pytest.mark.skipif(
    ON_310_PLUS and HAS_SPECIALIST, reason="the specialist is usable in this interpreter"
)
def test_describe_without_replay_refuses_when_the_specialist_is_absent() -> None:
    response, _ = _describe(None)
    assert response.status == "refused"
    assert response.error is not None
    assert response.error.code == "SPARKFORGE_AZURE-ADAPTER-UNAVAILABLE"
    assert response.error.unlock


# --- catalog / snapshot ---------------------------------------------------------------------


def test_snapshot_shape_and_canonical_encoding() -> None:
    snapshot = _snapshot()
    assert snapshot["specialist_version"] == "0.1.0"
    assert snapshot["provenance"] == "recorded"
    assert snapshot["recorded_at"]
    names = [seam["name"] for seam in snapshot["seams"]]
    assert len(names) == len(set(names))
    assert {
        catalog.SEAM_SDD_CHECK,
        catalog.SEAM_SDD_STATUS,
        catalog.SEAM_ACCESS_DIAGNOSE,
        catalog.SEAM_FABRIC_DIAGNOSE,
        catalog.SEAM_DOCTOR,
    } <= set(names)
    # The recorded surface carries the real Azure domain vocabulary of the specialist.
    domains = set(snapshot["specialist_domains"])
    assert "fabric" in domains and "unity-catalog" in domains and "adls" in domains
    assert "glue" not in domains and "s3" not in domains  # no AWS aliasing
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
    added = {
        **snapshot,
        "seams": [
            *snapshot["seams"],
            {"name": "new_seam", "module": "m", "callable": "c", "present": True},
        ],
    }
    status, lines = record.classify_drift(snapshot, added)
    assert status == "additive" and "seam added: new_seam" in lines
    missing = {**snapshot, "seams": snapshot["seams"][1:]}
    status, lines = record.classify_drift(snapshot, missing)
    assert status == "breaking" and lines[0].startswith("seam removed:")
    changed = json.loads(json.dumps(snapshot))
    changed["seams"][0]["parameters"] = ["other"]
    status, lines = record.classify_drift(snapshot, changed)
    assert status == "breaking" and any("seam changed:" in line for line in lines)
    dropped = {**snapshot, "tools": []}
    status, lines = record.classify_drift(snapshot, dropped)
    assert status == "breaking" and any("tool removed:" in line for line in lines)
    shrunk = {**snapshot, "specialist_domains": snapshot["specialist_domains"][1:]}
    status, lines = record.classify_drift(snapshot, shrunk)
    assert status == "breaking" and any("domain removed:" in line for line in lines)
    versioned = {**snapshot, "specialist_version": "9.9.9"}
    status, lines = record.classify_drift(snapshot, versioned)
    assert status == "additive" and any("specialist version" in line for line in lines)


def _valid_snapshot() -> dict[str, Any]:
    return {
        "specialist_version": "0.1.0",
        "recorded_at": "2026-10-08T00:00:00Z",
        "provenance": "recorded",
        "tools": ["sparkforge_sdd_check"],
        "specialist_domains": ["fabric"],
        "seams": [
            {
                "name": "sdd_check",
                "module": "sparkforge_azure.sdd.checks",
                "callable": "check",
                "present": True,
            }
        ],
    }


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"{not json", "unreadable"),
        (b"\xff\xfe", "unreadable"),
        (b"[]", "expected an object"),
        (
            json.dumps({k: v for k, v in _valid_snapshot().items() if k != "provenance"}).encode(),
            "provenance",
        ),
        (json.dumps({**_valid_snapshot(), "seams": {}}).encode(), "seams"),
        (json.dumps({**_valid_snapshot(), "seams": ["x"]}).encode(), "seams[0]"),
        (
            json.dumps(
                {
                    **_valid_snapshot(),
                    "seams": [{"name": "a", "module": "m", "callable": "c", "present": "yes"}],
                }
            ).encode(),
            "present",
        ),
    ],
)
def test_load_snapshot_rejects_corrupt_files(tmp_path: Path, content: bytes, message: str) -> None:
    path = tmp_path / "native_surface.json"
    path.write_bytes(content)
    with pytest.raises(catalog.SnapshotError, match=re.escape(message)):
        catalog.load_snapshot(path)


def test_corrupt_snapshot_makes_describe_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "native_surface.json"
    path.write_bytes(json.dumps({**_valid_snapshot(), "seams": {}}).encode())
    entry = importlib.import_module("theforge_sparkforge_azure.__main__")
    monkeypatch.setattr(entry, "load_snapshot", lambda: catalog.load_snapshot(path))
    handler = entry.describe(_shell.AdapterOptions(replay=DEFAULT))
    reply = handler(
        _shell.Request(op="describe", request_id="r", protocol=PROTOCOL_V1, payload={}), tmp_path
    )
    assert reply.status == "error"
    assert reply.error is not None
    assert reply.error["code"] == "SPARKFORGE_AZURE-ADAPTER-SNAPSHOT-INVALID"
    assert reply.error["unlock"]


# --- health ---------------------------------------------------------------------------------


def _health(options: tuple[str, ...] = ("--replay", str(DEFAULT))) -> tuple[Response, HealthReport]:
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
    assert checks["import"].ok and "0.1.0" in checks["import"].detail
    assert checks["version"].ok
    assert checks["boundary"].ok and "sparkforge_azure.adapters.tools" in checks["boundary"].detail
    assert report.status == "ok"


def test_replay_health_version_skew_is_degraded() -> None:
    _, report = _health(("--replay", str(SCENARIOS / "version-skew")))
    checks = _checks(report)
    assert report.status == "degraded"
    assert not checks["version"].ok and "9.9.0" in checks["version"].detail
    assert checks["boundary"].ok


def test_replay_health_without_the_boundary_is_unavailable() -> None:
    _, report = _health(("--replay", str(SCENARIOS / "boundary-missing")))
    checks = _checks(report)
    assert report.status == "unavailable"
    assert not checks["boundary"].ok and "sparkforge_azure" in checks["boundary"].detail


def test_replay_health_without_the_specialist_is_unavailable() -> None:
    _, report = _health(("--replay", str(SCENARIOS / "specialist-missing")))
    report_checks = _checks(report)
    assert report.status == "unavailable"
    assert not report_checks["import"].ok
    assert "version" not in report_checks and "boundary" not in report_checks


def test_assume_specialist_version_overrides_the_probe() -> None:
    _, report = _health(
        ("--replay", str(SCENARIOS / "version-skew"), "--assume-specialist-version", "0.1.5")
    )
    checks = _checks(report)
    assert report.status == "ok"
    assert checks["version"].ok and "0.1.5" in checks["version"].detail
    assert "assumed" in checks["version"].detail


def test_in_window_parses_release_candidates() -> None:
    window = ">=0.1.0,<0.2.0"
    assert health.in_window("0.1.0", window) is True
    assert health.in_window("0.1.9", window) is True
    assert health.in_window("0.2.0", window) is False
    assert health.in_window("not.a.version", window) is None
    with pytest.raises(ValueError):
        health.in_window("0.1.0", ">=banana")


# --- execute (replay) -----------------------------------------------------------------------


PRODUCER = Producer(id="spark-forge-azure", version="0.1.0")


def _result(response: Response, *, expect_ok: bool = True) -> ExecutionResult:
    if expect_ok:
        assert response.status == "ok", response.error
    result = from_dict(ExecutionResult, response.payload, "$.payload")
    validate_result(result, expected=PRODUCER)
    return result


def test_replay_sdd_check_translates_the_gate_verdict() -> None:
    response, _, cwd = _execute("sdd.check", "check")
    result = _result(response)
    assert result.status == "ok"
    # The complete fixture passes the gate: ok=true recorded as observed evidence.
    assert any("ok=True" in ev.claim for ev in result.evidence)
    assert [a.path for a in result.artifacts] == ["native/sdd-check.json"]
    artifact = cwd / "native" / "sdd-check.json"
    assert artifact.is_file()
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == result.artifacts[0].sha256
    document = json.loads(artifact.read_text("utf-8"))
    assert document["ok"] is True and document["features"] == ["EXPORTACAO"]


def test_replay_sdd_status_reports_the_phase() -> None:
    response, _, cwd = _execute("sdd.status", "status")
    result = _result(response)
    assert result.status == "ok"
    assert [a.path for a in result.artifacts] == ["native/sdd-status.json"]
    document = json.loads((cwd / "native" / "sdd-status.json").read_text("utf-8"))
    assert document["features"][0]["phase"] == "ship"


def test_replay_access_diagnose_translates_the_case() -> None:
    response, _, cwd = _execute("azure.access-diagnose", "analyze", workspace=ACCESS_CASE)
    result = _result(response)
    assert result.status == "ok"
    assert result.evidence
    assert [a.path for a in result.artifacts] == ["native/access-diagnosis.json"]
    artifact = cwd / "native" / "access-diagnosis.json"
    assert artifact.is_file()
    document = json.loads(artifact.read_text("utf-8"))
    # The real pipeline document is preserved verbatim under the artifact hash.
    assert "diagnosis" in document or "access_graph" in document or "findings" in document


def test_replay_fabric_diagnose_translates_the_case() -> None:
    response, _, cwd = _execute("fabric.access-diagnose", "analyze", workspace=FABRIC_CASE)
    result = _result(response)
    assert result.status == "ok"
    assert [a.path for a in result.artifacts] == ["native/fabric-diagnosis.json"]
    document = json.loads((cwd / "native" / "fabric-diagnosis.json").read_text("utf-8"))
    assert document["case"] == "fabric_bench"


def test_replay_doctor_needs_no_input() -> None:
    response, _, cwd = _execute(
        "azure.doctor", "report", context={"root": str(SDD_LIMPO), "files": []}
    )
    result = _result(response)
    assert result.status == "ok"
    assert any("checks ok" in ev.claim for ev in result.evidence)
    assert (cwd / "native" / "doctor.json").is_file()


def test_replay_execute_emits_no_machine_paths() -> None:
    response, raw, _ = _execute("sdd.check", "check")
    _result(response)
    blob = json.dumps(raw["payload"])
    assert str(SDD_LIMPO) not in blob and "C:\\" not in blob and "\\Users\\" not in blob


def test_replay_error_recording_is_a_structured_failure() -> None:
    response, _, _ = _execute("sdd.check", "check", SCENARIOS / "native-error")
    assert response.status == "error"
    assert response.error is not None
    assert response.error.code == "SFA-NATIVE-FAILURE"
    assert "simulated specialist failure" in response.error.detail


def test_replay_error_recording_exit_2_is_a_refusal() -> None:
    response, _, _ = _execute(
        "azure.access-diagnose",
        "analyze",
        SCENARIOS / "native-error",
        workspace=ACCESS_CASE,
    )
    assert response.status == "refused"
    assert response.error is not None
    assert response.error.code == "SFA-REQUEST-INVALID"
    assert "case.yaml" in response.error.detail


def test_replay_without_a_recording_is_missing(tmp_path: Path) -> None:
    (tmp_path / "environment.json").write_text(
        json.dumps({"python": "3.11.15", "specialist_version": "0.1.0"}), encoding="utf-8"
    )
    (tmp_path / "health.json").write_text('{"boundary": true}', encoding="utf-8")
    response, _, _ = _execute("sdd.check", "check", tmp_path)
    assert response.status == "error"
    assert response.error is not None
    assert response.error.code == "ADAPTER-REPLAY-MISSING"
    assert "sdd.check.check.json" in response.error.detail


def test_sdd_check_with_no_input_is_partial() -> None:
    response, _, _ = _execute("sdd.check", "check", context={"root": str(SDD_LIMPO), "files": []})
    result = _result(response, expect_ok=False)
    assert result.status == "partial"
    assert any("no input" in lim for lim in result.limitations)


def test_diagnose_with_no_input_is_partial() -> None:
    response, _, _ = _execute(
        "azure.access-diagnose",
        "analyze",
        context={"root": str(ACCESS_CASE), "files": []},
    )
    result = _result(response, expect_ok=False)
    assert result.status == "partial"


def test_a_malformed_profile_is_refused() -> None:
    response, _, _ = _execute(
        "azure.access-diagnose",
        "analyze",
        workspace=ACCESS_CASE,
        extra={"options": {"profile": "brutal"}},
    )
    assert response.status == "refused"
    assert response.error is not None
    assert response.error.code == "SFA-REQUEST-INVALID"
    assert response.error.field == "options.profile"


def test_forged_provider_claims_in_the_document_stay_data(tmp_path: Path) -> None:
    """A recorded document claiming another producer is never elevated — the
    adapter's own identity attributes every emitted item; forged fields only
    survive verbatim inside the stored artifact."""
    import shutil

    scenario = tmp_path / "forged"
    shutil.copytree(DEFAULT, scenario)
    recording = scenario / "sdd.check.check.json"
    document = json.loads(recording.read_text("utf-8"))
    document["provenance"] = {"provider": {"id": "evil-forge", "version": "9.9.9"}}
    recording.write_text(json.dumps(document), encoding="utf-8")

    response, data, cwd = _execute("sdd.check", "check", replay=scenario)
    result = _result(response)
    assert response.producer.id == "spark-forge-azure"
    assert result.status == "ok" and result.producer.id == "spark-forge-azure"
    ids = {item.producer.id for item in result.evidence if item.producer is not None}
    assert ids <= {"spark-forge-azure"}
    stored = json.loads((cwd / "native" / "sdd-check.json").read_text("utf-8"))
    assert stored["provenance"]["provider"]["id"] == "evil-forge"


# --- live specialist (only when the interpreter has sparkforge_azure) ------------------------


@pytest.mark.skipif(
    not (ON_310_PLUS and HAS_SPECIALIST),
    reason="sparkforge_azure is not importable in this interpreter",
)
def test_live_describe_matches_the_recorded_surface() -> None:
    response, raw = _describe(None)
    assert response.status == "ok", response.error
    assert raw["payload"]["native_surface_fingerprint"] == catalog.native_fingerprint(_snapshot())
