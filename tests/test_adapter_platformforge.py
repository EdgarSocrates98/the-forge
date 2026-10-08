"""Platform Forge adapter: handoff over the public boundary.

The adapter derives ``describe`` from ``native_surface.json`` (a snapshot of the
specialist's public seams plus its own capability-manifest/v3 declaration): a capability
is exposed only when the seam it drives is recorded present. Live, the interpreter must
be Python >= 3.10 with ``platformforge`` importable; with ``--replay <dir>`` the
scenario's ``environment.json`` answers instead and recordings replace the bridge runs.
The exposed capabilities are the offline, read-only analyzers (``iac``, ``plan``,
``state``, ``k8s``, ``secrets``, ``gha``, ``gitops``, ``catalog``) plus
``platform.manifest`` — mutating executors are never claimed.
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
from theforge_platformforge import _shell, catalog, health, record

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
PACKAGE = REPO / "adapters" / "platformforge" / "src" / "theforge_platformforge"
NATIVE = REPO / "tests" / "fixtures" / "native" / "platformforge"
DEFAULT = NATIVE / "default"
SCENARIOS = NATIVE / "scenarios"
WORKSPACES = REPO / "tests" / "fixtures" / "workspaces" / "platform"
EXPOSED = [
    "catalog.analyze",
    "gha.analyze",
    "gitops.analyze",
    "iac.analyze",
    "iac.plan-review",
    "iac.state",
    "k8s.analyze",
    "platform.manifest",
    "secrets.scan",
]
CHECKS = ["python", "import", "version", "boundary"]
ON_310_PLUS = sys.version_info[:2] >= (3, 10)
HAS_SPECIALIST = importlib.util.find_spec("platformforge") is not None


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
            [sys.executable, "-m", "theforge_platformforge", *options, op],
            input=request,
            capture_output=True,
            timeout=120,
            cwd=cwd,
        )
    assert out.returncode == 0, out.stderr
    data = json.loads(out.stdout)
    response = from_dict(Response, data)
    assert response.op == op and response.request_id == f"req-{op}"
    assert (response.producer.id, response.producer.version) == ("platform-forge", "0.1.0")
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
    workspace: Path | None = None,
    extra: dict[str, Any] | None = None,
) -> tuple[Response, dict[str, Any], Path]:
    """Execute in a cwd that persists past the call so artifacts can be inspected."""
    if context is None and workspace is not None:
        context = _workspace_context(workspace)
    payload = {
        "task": {"intent": "x", "budget_profile": "economy"},
        "capability": capability,
        "action": action,
        "context": context if context is not None else {"root": "", "files": []},
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
        [sys.executable, "-m", "theforge_platformforge", "--replay", str(replay), "execute"],
        input=request,
        capture_output=True,
        timeout=120,
        cwd=cwd,
    )
    assert out.returncode == 0, out.stderr
    data = json.loads(out.stdout)
    response = from_dict(Response, data)
    return response, data, cwd


# --- describe -------------------------------------------------------------------------------


def test_replay_describe_manifest() -> None:
    response, raw = _describe()
    assert response.status == "ok", response.error
    manifest = from_dict(ForgeManifest, response.payload)
    assert manifest.id == "platform-forge" and manifest.version == "0.1.0"
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
    iac = manifest.capability("iac.analyze")
    manifest_cap = manifest.capability("platform.manifest")
    assert iac is not None and iac.actions == ["analyze"]
    assert iac.relations.produces == [catalog.IAC_FACTS]
    assert manifest_cap is not None and manifest_cap.actions == ["report"]
    assert manifest_cap.relations.produces == [catalog.MANIFEST_DOC]
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
        provider_id="platform-forge",
        version="0.1.0",
    )
    assert any("hand-built" in n for n in payload["limitations"])


def test_seam_absent_becomes_a_limitation_not_a_capability() -> None:
    snapshot = _snapshot()
    for seam in snapshot["seams"]:
        seam["present"] = seam["name"] != catalog.SEAM_IAC_ANALYZE
    payload = catalog.manifest_payload(snapshot, provider_id="platform-forge", version="0.1.0")
    manifest = from_dict(ForgeManifest, payload)
    assert manifest.capability("iac.analyze") is None
    assert manifest.capability("k8s.analyze") is not None
    assert any("iac.analyze" in n and catalog.SEAM_IAC_ANALYZE in n for n in manifest.limitations)


def test_replay_environment_replaces_the_live_checks() -> None:
    response, _ = _describe(SCENARIOS / "specialist-missing")
    assert response.status == "refused"
    assert response.error is not None
    assert response.error.code == "PLATFORMFORGE-ADAPTER-UNAVAILABLE"
    assert "platformforge is not importable" in response.error.detail
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
    assert response.error.code == "PLATFORMFORGE-ADAPTER-UNAVAILABLE"
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
        catalog.SEAM_IAC_ANALYZE,
        catalog.SEAM_K8S,
        catalog.SEAM_SECRETS,
        catalog.SEAM_MANIFEST,
    } <= set(names)
    # The specialist's own manifest declaration is recorded verbatim (surface evidence).
    assert snapshot["manifest_schema"] == "platformforge/capability-manifest/v3"
    assert "change-intent" in snapshot["cross_forge_accepts"]
    assert "iac" in snapshot["domains"] and "k8s" in snapshot["domains"]
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
    dropped = {**snapshot, "tools": []}
    status, lines = record.classify_drift(snapshot, dropped)
    assert status == "breaking" and any("tool removed:" in line for line in lines)
    shrunk = {**snapshot, "cross_forge_accepts": []}
    status, lines = record.classify_drift(snapshot, shrunk)
    assert status == "breaking" and any("cross-forge accept" in line for line in lines)
    schema_changed = {**snapshot, "manifest_schema": "platformforge/capability-manifest/v4"}
    status, lines = record.classify_drift(snapshot, schema_changed)
    assert status == "breaking" and any("manifest schema" in line for line in lines)
    versioned = {**snapshot, "specialist_version": "9.9.9"}
    status, lines = record.classify_drift(snapshot, versioned)
    assert status == "additive" and any("specialist version" in line for line in lines)


def _valid_snapshot() -> dict[str, Any]:
    return {
        "specialist_version": "0.1.0",
        "recorded_at": "2026-10-08T00:00:00Z",
        "provenance": "recorded",
        "manifest_schema": "platformforge/capability-manifest/v3",
        "tools": ["platformforge_analyze"],
        "domains": ["iac"],
        "cross_forge_accepts": ["change-intent"],
        "seams": [
            {
                "name": "iac_analyze",
                "module": "platformforge.iac.terraform",
                "callable": "analyze_hcl",
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
    entry = importlib.import_module("theforge_platformforge.__main__")
    monkeypatch.setattr(entry, "load_snapshot", lambda: catalog.load_snapshot(path))
    handler = entry.describe(_shell.AdapterOptions(replay=DEFAULT))
    reply = handler(
        _shell.Request(op="describe", request_id="r", protocol=PROTOCOL_V1, payload={}), tmp_path
    )
    assert reply.status == "error"
    assert reply.error is not None
    assert reply.error["code"] == "PLATFORMFORGE-ADAPTER-SNAPSHOT-INVALID"
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
    assert checks["boundary"].ok and "platformforge.forge.manifest" in checks["boundary"].detail
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
    assert not checks["boundary"].ok and "platformforge" in checks["boundary"].detail


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


PRODUCER = Producer(id="platform-forge", version="0.1.0")


def _result(response: Response, *, expect_ok: bool = True) -> ExecutionResult:
    if expect_ok:
        assert response.status == "ok", response.error
    result = from_dict(ExecutionResult, response.payload, "$.payload")
    validate_result(result, expected=PRODUCER)
    return result


def test_replay_iac_analyze_translates_the_fact_document() -> None:
    response, _, cwd = _execute("iac.analyze", "analyze", workspace=WORKSPACES / "iac")
    result = _result(response)
    assert result.status == "ok"
    assert any("facts:" in ev.claim for ev in result.evidence)
    assert [a.path for a in result.artifacts] == ["native/iac-facts.json"]
    artifact = cwd / "native" / "iac-facts.json"
    assert artifact.is_file()
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == result.artifacts[0].sha256
    document = json.loads(artifact.read_text("utf-8"))
    assert isinstance(document["facts"], list) and document["facts"]


def test_replay_plan_review_uses_the_file_seam() -> None:
    response, _, cwd = _execute("iac.plan-review", "analyze", workspace=WORKSPACES / "plan")
    result = _result(response)
    assert result.status == "ok"
    document = json.loads((cwd / "native" / "plan-review.json").read_text("utf-8"))
    assert document["counts"]["facts"] == 2


def test_replay_state_analyze_uses_the_file_seam() -> None:
    response, _, _ = _execute("iac.state", "analyze", workspace=WORKSPACES / "state")
    result = _result(response)
    assert result.status == "ok"


def test_replay_k8s_analyze() -> None:
    response, _, cwd = _execute("k8s.analyze", "analyze", workspace=WORKSPACES / "k8s")
    result = _result(response)
    assert result.status == "ok"
    document = json.loads((cwd / "native" / "k8s-facts.json").read_text("utf-8"))
    assert document["counts"]["facts"] == 3


def test_replay_secrets_scan_redacts_values() -> None:
    response, raw, cwd = _execute("secrets.scan", "scan", workspace=WORKSPACES / "secrets")
    result = _result(response)
    assert result.status == "ok"
    document = json.loads((cwd / "native" / "secrets-report.json").read_text("utf-8"))
    # The specialist's own contract: labels and line numbers, never values.
    assert "values never emitted" in document["note"]
    blob = json.dumps(raw["payload"])
    assert "AKIAIOSFODNN7EXAMPLE" not in blob and "sup3r-s3cret-eval-value" not in blob


def test_replay_gha_and_gitops_and_catalog() -> None:
    for capability, workspace, artifact in (
        ("gha.analyze", WORKSPACES / "gha", "native/gha-facts.json"),
        ("gitops.analyze", WORKSPACES / "gitops", "native/gitops-facts.json"),
        ("catalog.analyze", WORKSPACES / "catalog", "native/catalog-facts.json"),
    ):
        response, _, cwd = _execute(capability, "analyze", workspace=workspace)
        result = _result(response)
        assert result.status == "ok", capability
        assert (cwd / artifact).is_file(), capability


def test_replay_forge_manifest_reports_the_declared_surface() -> None:
    response, _, cwd = _execute("platform.manifest", "report")
    result = _result(response)
    assert result.status == "ok"
    document = json.loads((cwd / "native" / "capability-manifest.json").read_text("utf-8"))
    assert document["manifest"] == "platformforge/capability-manifest/v3"
    # The recorded cross-forge contract surfaces as observed evidence.
    assert any("cross_forge.accepts" in ev.claim for ev in result.evidence)
    assert any("change-intent" in ev.claim for ev in result.evidence)


def test_replay_execute_emits_no_machine_paths() -> None:
    response, raw, _ = _execute("iac.analyze", "analyze", workspace=WORKSPACES / "iac")
    _result(response)
    blob = json.dumps(raw["payload"])
    assert str(WORKSPACES) not in blob and "C:\\" not in blob and "\\Users\\" not in blob


def test_replay_error_recording_is_a_structured_failure() -> None:
    response, _, _ = _execute(
        "iac.analyze",
        "analyze",
        SCENARIOS / "native-error",
        workspace=WORKSPACES / "iac",
    )
    assert response.status == "error"
    assert response.error is not None
    assert response.error.code == "PF-NATIVE-FAILURE"
    assert "simulated specialist failure" in response.error.detail


def test_replay_error_recording_exit_2_is_a_refusal() -> None:
    response, _, _ = _execute(
        "secrets.scan",
        "scan",
        SCENARIOS / "native-error",
        workspace=WORKSPACES / "secrets",
    )
    assert response.status == "refused"
    assert response.error is not None
    assert response.error.code == "PF-REQUEST-INVALID"


def test_replay_without_a_recording_is_missing(tmp_path: Path) -> None:
    (tmp_path / "environment.json").write_text(
        json.dumps({"python": "3.11.15", "specialist_version": "0.1.0"}), encoding="utf-8"
    )
    (tmp_path / "health.json").write_text('{"boundary": true}', encoding="utf-8")
    response, _, _ = _execute("iac.analyze", "analyze", tmp_path, workspace=WORKSPACES / "iac")
    assert response.status == "error"
    assert response.error is not None
    assert response.error.code == "ADAPTER-REPLAY-MISSING"
    assert "iac.analyze.analyze.json" in response.error.detail


def test_iac_analyze_with_no_input_is_partial() -> None:
    source = Path(tempfile.mkdtemp())
    response, _, _ = _execute("iac.analyze", "analyze", context={"root": str(source), "files": []})
    result = _result(response, expect_ok=False)
    assert result.status == "partial"
    assert any("no input" in lim for lim in result.limitations)


def test_forged_provider_claims_in_the_document_stay_data(tmp_path: Path) -> None:
    """A recorded document claiming another producer is never elevated — the
    adapter's own identity attributes every emitted item; forged fields only
    survive verbatim inside the stored artifact."""
    import shutil

    scenario = tmp_path / "forged"
    shutil.copytree(DEFAULT, scenario)
    recording = scenario / "iac.analyze.analyze.json"
    document = json.loads(recording.read_text("utf-8"))
    document["provenance"] = {"provider": {"id": "evil-forge", "version": "9.9.9"}}
    recording.write_text(json.dumps(document), encoding="utf-8")

    response, data, cwd = _execute(
        "iac.analyze", "analyze", replay=scenario, workspace=WORKSPACES / "iac"
    )
    result = _result(response)
    assert response.producer.id == "platform-forge"
    assert result.status == "ok" and result.producer.id == "platform-forge"
    ids = {item.producer.id for item in result.evidence}
    assert ids == {"platform-forge"}
    stored = json.loads((cwd / "native" / "iac-facts.json").read_text("utf-8"))
    assert stored["provenance"]["provider"]["id"] == "evil-forge"


# --- live specialist (only when the interpreter has platformforge) ---------------------------


@pytest.mark.skipif(
    not (ON_310_PLUS and HAS_SPECIALIST),
    reason="platformforge is not importable in this interpreter",
)
def test_live_describe_matches_the_recorded_surface() -> None:
    response, raw = _describe(None)
    assert response.status == "ok", response.error
    assert raw["payload"]["native_surface_fingerprint"] == catalog.native_fingerprint(_snapshot())
