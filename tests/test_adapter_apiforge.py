"""API Forge adapter (real-provider-integration 5.1): manifest from the recorded public matrix.

The adapter derives its ``describe`` from ``native_matrix.json`` (a snapshot of the API Forge
public capability matrix): only ``supported``/``heuristic``, ``read_only`` records mapped to
an offline verb are exposed, with the native id and state; every other record is a
limitation with its reason. Without ``--replay`` the describe refuses when the interpreter is
not Python 3.12 or ``apiforge`` is not importable; with ``--replay <dir>`` those checks read
the scenario's ``environment.json`` instead. The core's own contract code validates what the
adapter answers (``from_dict``, ``validate_taxonomy``, ``validate_manifest_limits``).
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
from theforge_apiforge import _shell, backend, catalog, health, record

from theforge.contracts import (
    PROTOCOL_V1,
    ErrorInfo,
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
from theforge.contracts.types import is_catch_all_glob

REPO = Path(__file__).parents[1]
PACKAGE = REPO / "adapters" / "apiforge" / "src" / "theforge_apiforge"
NATIVE = REPO / "tests" / "fixtures" / "native" / "apiforge"
DEFAULT = NATIVE / "default"
SCENARIOS = NATIVE / "scenarios"
WORKSPACE = REPO / "tests" / "fixtures" / "workspaces" / "api"
EXPOSED = ["api.analyze", "api.change-control"]
ON_312 = sys.version_info[:2] == (3, 12)


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
            [sys.executable, "-m", "theforge_apiforge", *options, op],
            input=request,
            capture_output=True,
            timeout=60,
            cwd=cwd,
        )
    assert out.returncode == 0, out.stderr
    data = json.loads(out.stdout)
    response = from_dict(Response, data)
    assert response.op == op and response.request_id == f"req-{op}"
    assert (response.producer.id, response.producer.version) == ("api-forge", "0.3.0")
    return response, data


def _describe(replay: Path | None = DEFAULT) -> tuple[Response, dict[str, Any]]:
    return _call("describe", () if replay is None else ("--replay", str(replay)))


def _snapshot() -> dict[str, Any]:
    data: dict[str, Any] = json.loads((PACKAGE / "native_matrix.json").read_text("utf-8"))
    return data


# --- describe in replay ---------------------------------------------------------------------


def test_replay_describe_exposes_analyze_and_change_control() -> None:
    response, raw = _describe()
    assert response.status == "ok", response.error
    manifest = from_dict(ForgeManifest, response.payload)
    assert manifest.id == "api-forge" and manifest.version == "0.3.0"
    assert manifest.protocols == [PROTOCOL_V1]
    assert set(manifest.ops) >= {"describe", "health", "execute"}
    assert [c.id for c in manifest.capabilities] == EXPOSED
    assert manifest.execution.local and manifest.execution.offline
    assert not manifest.execution.requires_network
    assert validate_taxonomy(manifest) == ()
    assert validate_manifest_limits(manifest) == ()
    analyze = manifest.capability("api.analyze")
    change = manifest.capability("api.change-control")
    assert analyze is not None and analyze.actions == ["analyze"]
    assert analyze.default_action == "analyze"
    assert change is not None and change.actions == ["run"] and change.default_action == "run"
    native = {r["capability_id"]: r for r in _snapshot()["capabilities"]}
    for capability in manifest.capabilities:
        assert capability.state == native[capability.id]["state"]  # native state preserved
        assert capability.operation_class == "read_only"
        assert capability.description
        assert capability.signals.keywords and capability.signals.file_globs
    # context-intelligence-v2 field: checked on the RAW payload (ForgeManifest may lack it).
    assert raw["payload"]["context_revalidation"] == "hash"


def test_replay_describe_lists_every_other_record_with_reason() -> None:
    response, _ = _describe()
    assert response.status == "ok"
    manifest = from_dict(ForgeManifest, response.payload)
    records = _snapshot()["capabilities"]
    excluded = [r for r in records if r["capability_id"] not in EXPOSED]
    assert len(excluded) == len(records) - len(EXPOSED) > 0
    for item in excluded:
        prefix = f"capability '{item['capability_id']}' ({item['state']}) not exposed: "
        notes = [n for n in manifest.limitations if n.startswith(prefix)]
        assert len(notes) == 1, (item["capability_id"], manifest.limitations)
        assert len(notes[0]) > len(prefix)  # a reason follows
    reasons = {
        n.split(" not exposed: ", 1)[0]: n.split(" not exposed: ", 1)[1]
        for n in manifest.limitations
        if " not exposed: " in n
    }
    assert "--phase" in reasons["capability 'api.next-step' (supported)"]
    assert "network" in reasons["capability 'integration.health' (supported)"]
    assert "unresolved" in reasons["capability 'git.plan' (unresolved)"]
    assert "local_reversible" in reasons["capability 'git.plan' (unresolved)"]
    assert "external_mutation" in reasons["capability 'external.apply' (unsupported)"]
    assert "tests/fixtures" in reasons["capability 'database.verify-runtime' (supported)"]
    assert "offline verb" in reasons["capability 'cloud.inspect' (heuristic)"]


def test_describe_flags_a_hand_built_snapshot() -> None:
    """A matrix marked ``hand-built`` is flagged provisional in the manifest
    limitations; the packaged matrix is recorded against API Forge main."""
    snapshot = _snapshot()
    assert snapshot["provenance"] == "recorded"
    hand_built = catalog.manifest_payload(
        {**snapshot, "provenance": "hand-built"}, provider_id="api-forge", version="0.3.0"
    )
    assert any("hand-built" in n and "0.1.0" in n for n in hand_built["limitations"])


def test_describe_is_deterministic() -> None:
    first = _describe()[1]["payload"]
    second = _describe()[1]["payload"]
    assert first == second


@pytest.mark.parametrize(
    ("scenario", "expected"),
    [
        ("python-3.11", "Python 3.12"),
        ("apiforge-missing", "apiforge is not importable"),
    ],
)
def test_replay_environment_replaces_the_live_checks(scenario: str, expected: str) -> None:
    response, _ = _describe(SCENARIOS / scenario)
    assert response.status == "refused"
    assert response.error is not None
    assert response.error.code == "APIFORGE-ADAPTER-UNAVAILABLE"
    assert expected in response.error.detail
    assert "environment.json" in response.error.detail
    assert response.error.unlock


def test_replay_without_environment_is_a_missing_recording(tmp_path: Path) -> None:
    response, _ = _describe(tmp_path)
    assert response.status == "error"
    assert response.error is not None
    assert response.error.code == "ADAPTER-REPLAY-MISSING"
    assert "environment.json" in response.error.detail


def test_replay_environment_must_be_an_object(tmp_path: Path) -> None:
    (tmp_path / "environment.json").write_text('["3.12"]', encoding="utf-8")
    response, _ = _describe(tmp_path)
    assert response.status == "error"
    assert response.error is not None and response.error.code == "ADAPTER-REPLAY-INVALID"


@pytest.mark.skipif(ON_312, reason="this environment runs Python 3.12")
def test_describe_without_replay_refuses_citing_python_312() -> None:
    response, _ = _describe(None)
    assert response.status == "refused"
    assert response.error is not None
    assert response.error.code == "APIFORGE-ADAPTER-UNAVAILABLE"
    assert "API Forge requires Python 3.12" in response.error.detail
    assert f"{sys.version_info[0]}.{sys.version_info[1]}" in response.error.detail
    assert response.error.unlock


@pytest.mark.skipif(ON_312, reason="this environment runs Python 3.12")
def test_execute_without_replay_surfaces_the_describe_refusal() -> None:
    payload = {
        "task": {"intent": "x"},
        "capability": "api.analyze",
        "action": "analyze",
        "context": {"files": []},
    }
    response, _ = _call("execute", (), payload)
    assert response.status == "refused"
    assert response.error is not None
    assert response.error.code == "APIFORGE-ADAPTER-UNAVAILABLE"


def test_live_environment_checks() -> None:
    def present(name: str) -> object:
        return object()

    def absent(name: str) -> object:
        return None

    problem = backend.live_environment_problem((3, 11), "/py311", present)
    assert problem is not None and "Python 3.12" in problem and "3.11" in problem
    assert "/py311" in problem
    problem = backend.live_environment_problem((3, 12), "/py312", absent)
    assert problem is not None and "apiforge is not importable" in problem
    assert backend.live_environment_problem((3, 12), "/py312", present) is None


# --- catalog --------------------------------------------------------------------------------


def _record(
    capability_id: str, state: str = "supported", risk: str = "read_only"
) -> dict[str, Any]:
    return {"capability_id": capability_id, "state": state, "risk": risk, "limitations": []}


def test_eligibility_rules() -> None:
    assert catalog.eligible(_record("api.analyze")) == (True, "")
    assert catalog.eligible(_record("api.analyze", "heuristic"))[0]
    for state in ("unresolved", "unsupported", "planned"):
        ok, reason = catalog.eligible(_record("api.analyze", state))
        assert not ok and state in reason
    ok, reason = catalog.eligible(_record("api.analyze", risk="external_mutation"))
    assert not ok and "external_mutation" in reason
    ok, reason = catalog.eligible(_record("api.unknown-verb"))
    assert not ok and "offline verb" in reason


def test_heuristic_record_keeps_its_native_state() -> None:
    snapshot = {
        **_snapshot(),
        "capabilities": [_record("api.analyze", "heuristic"), _record("api.change-control")],
    }
    payload = catalog.manifest_payload(snapshot, provider_id="api-forge", version="0.1.0")
    manifest = from_dict(ForgeManifest, payload)
    assert [(c.id, c.state) for c in manifest.capabilities] == [
        ("api.analyze", "heuristic"),
        ("api.change-control", "supported"),
    ]


def test_snapshot_shape_and_order() -> None:
    snapshot = _snapshot()
    assert snapshot["specialist_version"] == "0.1.0"
    assert snapshot["recorded_at"]
    records = snapshot["capabilities"]
    ids = [r["capability_id"] for r in records]
    assert ids == sorted(ids) and len(ids) == len(set(ids))
    for item in records:
        assert set(item) == {"capability_id", "state", "risk", "limitations"}
        assert item["limitations"] == sorted(set(item["limitations"]))
    assert {"api.analyze", "api.change-control"} <= set(ids)
    raw = (PACKAGE / "native_matrix.json").read_bytes()
    assert b"\r\n" not in raw and raw.endswith(b"\n")
    assert raw == record.encode_snapshot(snapshot)  # canonical encoding


def test_every_verb_map_entry_passes_the_taxonomy_even_heuristic() -> None:
    snapshot = {**_snapshot(), "capabilities": [_record(cid) for cid in sorted(catalog.VERB_MAP)]}
    manifest = from_dict(
        ForgeManifest, catalog.manifest_payload(snapshot, provider_id="api-forge", version="0.1.0")
    )
    assert [c.id for c in manifest.capabilities] == sorted(catalog.VERB_MAP)
    assert validate_taxonomy(manifest) == ()
    assert validate_manifest_limits(manifest) == ()


NOT_INPUTS = [
    "README.md",
    "docs/guide.md",
    "app/notes.md",
    "CHANGELOG.MD",
    "x",
    "a.txt",
    "Makefile",
    ".env",
    "data.bin",
    "openapi.md",
    "change-bundle.md",
]


def test_no_input_pattern_accepts_markdown_or_any_file() -> None:
    for capability_id, spec in catalog.VERB_MAP.items():
        assert spec.inputs, capability_id
        globs = [g for item in spec.inputs for g in item.globs]
        for glob in [*globs, *spec.signals.file_globs]:
            assert not is_catch_all_glob(glob), (capability_id, glob)
            for path in NOT_INPUTS:
                assert not _shell.select_inputs(
                    _shell.StagedInput(root=Path("."), files={path: "0" * 64}), {"probe": [glob]}
                )["probe"], (capability_id, glob, path)


def test_input_globs_select_the_example_workspace() -> None:
    files = {
        p.relative_to(WORKSPACE).as_posix(): "0" * 64
        for p in sorted(WORKSPACE.rglob("*"))
        if p.is_file()
    }
    stage = _shell.StagedInput(root=WORKSPACE, files=files)
    analyze = catalog.VERB_MAP["api.analyze"]
    selected = _shell.select_inputs(stage, {i.name: i.globs for i in analyze.inputs})
    assert selected["contract"] == ["openapi.yaml"]
    assert "app/main.py" in selected["project"]
    change = catalog.VERB_MAP["api.change-control"]
    selected = _shell.select_inputs(stage, {i.name: i.globs for i in change.inputs})
    assert selected["bundle"] == ["change-bundle.json"]


def test_verb_map_matches_the_design() -> None:
    analyze = catalog.VERB_MAP["api.analyze"]
    assert analyze.argv[0] == "analyze" and "--detail-level" in analyze.argv
    assert [i.flag for i in analyze.inputs] == ["--contract", "--project"]
    assert analyze.actions == ("analyze",)
    assert analyze.output_dir == "case"
    change = catalog.VERB_MAP["api.change-control"]
    assert change.argv[:2] == ("change-control", "run")
    assert [i.flag for i in change.inputs] == ["--bundle"]
    assert change.actions == ("run",)
    assert change.output_dir == "change-control"
    for spec in catalog.VERB_MAP.values():
        assert "--fail-on" not in spec.argv
        assert not Path(spec.output_dir).is_absolute() and ".." not in spec.output_dir


# --- replay layout --------------------------------------------------------------------------


def test_default_scenario_layout() -> None:
    environment = json.loads((DEFAULT / "environment.json").read_text("utf-8"))
    assert environment["python"].startswith("3.12")
    assert environment["specialist_version"] == "0.1.0"
    assert environment["provenance"] == "recorded"
    for scenario in SCENARIOS.iterdir():
        assert (scenario / "environment.json").is_file(), scenario  # complete scenarios


def test_replay_error_recording_prevails(tmp_path: Path) -> None:
    replay = backend.ReplayBackend(tmp_path)
    assert replay.expected("api.analyze", "analyze") == "api.analyze.analyze.json"
    assert replay.recording("api.analyze", "analyze") is None
    native = tmp_path / "api.analyze.analyze.json"
    native.write_text("{}", encoding="utf-8")
    assert replay.recording("api.analyze", "analyze") == ("native", native)
    error = tmp_path / "api.analyze.analyze.error.json"
    error.write_text('{"exit_code": 2, "stderr": "AF-X: y"}', encoding="utf-8")
    assert replay.recording("api.analyze", "analyze") == ("error", error)
    native.unlink()
    assert replay.recording("api.analyze", "analyze") == ("error", error)


# --- record ---------------------------------------------------------------------------------


class _FakeRecord:
    def __init__(self, capability_id: str, state: str, risk: str, limitations: tuple[str, ...]):
        self.capability_id = capability_id
        self.state = state
        self.risk = risk
        self.limitations = limitations
        self.verifier = "ignored"


def test_record_builds_a_deterministic_snapshot() -> None:
    records = [
        _FakeRecord("b.two", "heuristic", "read_only", ("z", "a", "z")),
        _FakeRecord("a.one", "supported", "read_only", ()),
    ]
    first = record.build_snapshot(
        records, specialist_version="0.1.0", recorded_at="2026-10-03T00:00:00Z"
    )
    second = record.build_snapshot(
        list(reversed(records)), specialist_version="0.1.0", recorded_at="2026-10-03T00:00:00Z"
    )
    assert record.encode_snapshot(first) == record.encode_snapshot(second)
    assert first["provenance"] == "recorded"
    assert [r["capability_id"] for r in first["capabilities"]] == ["a.one", "b.two"]
    assert first["capabilities"][1] == {
        "capability_id": "b.two",
        "state": "heuristic",
        "risk": "read_only",
        "limitations": ["a", "z"],
    }
    later = record.build_snapshot(
        records, specialist_version="0.1.0", recorded_at="2026-10-04T00:00:00Z"
    )
    assert {k: v for k, v in later.items() if k != "recorded_at"} == {
        k: v for k, v in first.items() if k != "recorded_at"
    }
    encoded = record.encode_snapshot(first)
    assert encoded.endswith(b"\n") and b"\r" not in encoded
    assert json.loads(encoded) == first


def test_record_check_classifies_drift() -> None:
    base = {
        "specialist_version": "1.0",
        "capabilities": [
            {
                "capability_id": "a.one",
                "state": "supported",
                "risk": "read_only",
                "limitations": [],
            },
            {
                "capability_id": "b.two",
                "state": "supported",
                "risk": "read_only",
                "limitations": [],
            },
        ],
    }
    assert record.classify_drift(base, base) == ("none", [])
    added = {
        **base,
        "capabilities": [
            *base["capabilities"],
            {
                "capability_id": "c.new",
                "state": "supported",
                "risk": "read_only",
                "limitations": [],
            },
        ],
    }
    status, lines = record.classify_drift(base, added)
    assert status == "additive" and lines == ["capability added: c.new"]
    status, lines = record.classify_drift(base, {**base, "capabilities": base["capabilities"][:1]})
    assert status == "breaking" and lines == ["capability removed: b.two"]
    changed = {
        **base,
        "capabilities": [
            base["capabilities"][0],
            {**base["capabilities"][1], "state": "unsupported"},
        ],
    }
    status, lines = record.classify_drift(base, changed)
    assert status == "breaking" and lines[0].startswith("capability changed: b.two")
    status, lines = record.classify_drift(base, {**base, "specialist_version": "2.0"})
    assert status == "additive" and "specialist version 1.0 -> 2.0" in lines


@pytest.mark.skipif(ON_312, reason="this environment runs Python 3.12")
def test_record_refuses_outside_python_312(tmp_path: Path) -> None:
    out = subprocess.run(
        [sys.executable, "-m", "theforge_apiforge.record", "--out", str(tmp_path / "m.json")],
        capture_output=True,
        timeout=60,
        cwd=tmp_path,
    )
    assert out.returncode != 0
    assert b"Python 3.12" in out.stderr
    assert not (tmp_path / "m.json").exists()


# --- snapshot validation --------------------------------------------------------------------


def _valid_snapshot() -> dict[str, Any]:
    return {
        "specialist_version": "0.1.0",
        "recorded_at": "2026-10-03T00:00:00Z",
        "provenance": "recorded",
        "capabilities": [_record("api.analyze")],
    }


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"{not json", "unreadable"),
        (b"\xff\xfe", "unreadable"),
        (b"[]", "expected an object"),
        (json.dumps({**_valid_snapshot(), "provenance": ""}).encode(), "provenance"),
        (
            json.dumps({k: v for k, v in _valid_snapshot().items() if k != "provenance"}).encode(),
            "provenance",
        ),
        (json.dumps({**_valid_snapshot(), "capabilities": {}}).encode(), "capabilities"),
        (json.dumps({**_valid_snapshot(), "capabilities": ["x"]}).encode(), "capabilities[0]"),
        (
            json.dumps(
                {
                    **_valid_snapshot(),
                    "capabilities": [
                        {"capability_id": "api.analyze", "state": "", "risk": "read_only"}
                    ],
                }
            ).encode(),
            "capabilities[0].state",
        ),
        (
            json.dumps(
                {
                    **_valid_snapshot(),
                    "capabilities": [{**_record("api.analyze"), "limitations": [1]}],
                }
            ).encode(),
            "limitations",
        ),
        (
            json.dumps(
                {
                    **_valid_snapshot(),
                    "capabilities": [_record("api.analyze"), _record("api.analyze")],
                }
            ).encode(),
            "duplicate capability_id",
        ),
    ],
)
def test_load_snapshot_rejects_corrupt_files(tmp_path: Path, content: bytes, message: str) -> None:
    path = tmp_path / "native_matrix.json"
    path.write_bytes(content)
    with pytest.raises(catalog.SnapshotError, match=re.escape(message)):
        catalog.load_snapshot(path)


def test_load_snapshot_missing_file(tmp_path: Path) -> None:
    with pytest.raises(catalog.SnapshotError, match="unreadable"):
        catalog.load_snapshot(tmp_path / "absent.json")


def test_corrupt_snapshot_makes_describe_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "native_matrix.json"
    path.write_bytes(
        json.dumps(
            {**_valid_snapshot(), "capabilities": [_record("api.analyze"), _record("api.analyze")]}
        ).encode()
    )
    entry = importlib.import_module("theforge_apiforge.__main__")
    monkeypatch.setattr(entry, "load_snapshot", lambda: catalog.load_snapshot(path))
    handler = entry.describe(_shell.AdapterOptions(replay=DEFAULT))
    reply = handler(
        _shell.Request(op="describe", request_id="r", protocol=PROTOCOL_V1, payload={}), tmp_path
    )
    assert reply.status == "error"
    assert reply.error is not None
    assert reply.error["code"] == "APIFORGE-ADAPTER-SNAPSHOT-INVALID"
    assert "duplicate capability_id" in reply.error["detail"]
    assert reply.error["unlock"]


# --- health ---------------------------------------------------------------------------------

CHECKS = ["python", "import", "version", "cli"]


def _health(options: tuple[str, ...] = ("--replay", str(DEFAULT))) -> tuple[Response, HealthReport]:
    response, _ = _call("health", options)
    assert response.status == "ok", response.error
    return response, from_dict(HealthReport, response.payload, "$.payload")


def _checks(report: HealthReport) -> dict[str, HealthCheck]:
    return {check.name: check for check in report.checks}


def test_replay_default_health_is_ok_from_local_checks() -> None:
    recording = json.loads((DEFAULT / "health.json").read_text("utf-8"))
    assert recording["provenance"] == "recorded"  # seen in the real API Forge interpreter
    assert recording["cli"] is True
    _, report = _health()
    checks = _checks(report)
    assert list(checks) == CHECKS
    assert checks["python"].ok and "3.12" in checks["python"].detail
    assert checks["import"].ok
    assert checks["version"].ok and "0.1.0" in checks["version"].detail
    assert checks["cli"].ok and "apiforge.cli" in checks["cli"].detail
    assert report.status == "ok"


def test_replay_health_without_the_cli_entry_point_is_unavailable() -> None:
    directory = SCENARIOS / "cli-missing"
    recording = json.loads((directory / "health.json").read_text("utf-8"))
    assert recording["cli"] is False
    _, report = _health(("--replay", str(directory)))
    assert report.status == "unavailable"
    failing = [check for check in report.checks if not check.ok]
    assert [check.name for check in failing] == ["cli"]
    assert "apiforge.cli" in failing[0].detail and "reinstall" in failing[0].detail


@pytest.mark.parametrize(
    ("scenario", "name", "expected"),
    [
        ("python-3.11", "python", "API Forge requires Python 3.12"),
        ("apiforge-missing", "import", "apiforge is not importable"),
    ],
)
def test_replay_health_unavailable_with_the_interpreter_or_import_reason(
    scenario: str, name: str, expected: str
) -> None:
    _, report = _health(("--replay", str(SCENARIOS / scenario)))
    assert report.status == "unavailable"
    failing = [check for check in report.checks if not check.ok]
    assert [check.name for check in failing] == [name]
    assert expected in failing[0].detail
    assert "cli" not in _checks(report)  # nothing else is probed without the API Forge


@pytest.mark.parametrize(
    ("assumed", "expected"),
    [("9.9.9", "degraded"), ("0.0.9", "degraded"), ("0.2.0", "degraded"), ("0.1.7", "ok")],
)
def test_health_accepts_the_assumed_specialist_version(assumed: str, expected: str) -> None:
    _, report = _health(("--assume-specialist-version", assumed, "--replay", str(DEFAULT)))
    assert report.status == expected
    version = _checks(report)["version"]
    assert version.ok is (expected == "ok")
    assert assumed in version.detail and "--assume-specialist-version" in version.detail
    if expected == "degraded":
        assert f"found {assumed}, supported >=0.1.0,<0.2.0" in version.detail


def test_unparseable_specialist_version_is_degraded() -> None:
    _, report = _health(("--assume-specialist-version", "banana", "--replay", str(DEFAULT)))
    assert report.status == "degraded"
    assert "found banana, supported >=0.1.0,<0.2.0" in _checks(report)["version"].detail


def test_out_of_window_version_keeps_a_missing_cli_unavailable() -> None:
    _, report = _health(
        ("--assume-specialist-version", "9.9.9", "--replay", str(SCENARIOS / "cli-missing"))
    )
    assert report.status == "unavailable"
    assert not _checks(report)["version"].ok and not _checks(report)["cli"].ok


def test_unavailable_health_reaches_the_core_with_its_reason() -> None:
    # The core reports an unavailable provider with the details of its failing checks.
    _, report = _health(("--replay", str(SCENARIOS / "cli-missing")))
    failing = "; ".join(c.detail or c.name for c in report.checks if not c.ok)
    assert "apiforge.cli" in failing


def test_replay_health_without_recording_is_missing(tmp_path: Path) -> None:
    (tmp_path / "environment.json").write_text(
        '{"python": "3.12.13", "specialist_version": "0.1.0"}', encoding="utf-8"
    )
    response, _ = _call("health", ("--replay", str(tmp_path)))
    assert response.status == "error"
    assert response.error is not None
    assert response.error.code == "ADAPTER-REPLAY-MISSING"
    assert "health.json" in response.error.detail


@pytest.mark.parametrize(
    "content",
    [
        '["ready"]',
        '{"cli": "true"}',
        '{"cli": 1}',
        "{}",
        '{"exit_code": 0, "doctor": {}}',
        "not json",
    ],
)
def test_replay_health_rejects_malformed_recordings(tmp_path: Path, content: str) -> None:
    (tmp_path / "environment.json").write_text(
        '{"python": "3.12.13", "specialist_version": "0.1.0"}', encoding="utf-8"
    )
    (tmp_path / "health.json").write_text(content, encoding="utf-8")
    response, _ = _call("health", ("--replay", str(tmp_path)))
    assert response.status == "error"
    assert response.error is not None and response.error.code == "ADAPTER-REPLAY-INVALID"
    assert "health.json" in response.error.detail


def test_health_scenarios_are_complete() -> None:
    assert (DEFAULT / "health.json").is_file()
    directory = SCENARIOS / "cli-missing"
    assert (directory / "environment.json").is_file()
    environment = json.loads((directory / "environment.json").read_text("utf-8"))
    assert environment["python"].startswith("3.12") and environment["specialist_version"]
    for path in NATIVE.rglob("health.json"):
        recording = json.loads(path.read_text("utf-8"))
        assert isinstance(recording["cli"], bool), path
        assert "doctor" not in recording, path  # health never runs the native doctor
        assert recording["provenance"] in {"recorded", "derived"}, path
        if recording["provenance"] == "derived":
            assert recording["derived_from"] == "default/health.json"
            assert recording["derivation"]
        text = path.read_text("utf-8")
        # Recordings never carry the recording machine's paths.
        assert "edgar" not in text.lower() and ".venvs" not in text, path
    assert not list(SCENARIOS.glob("doctor-*"))


@pytest.mark.skipif(ON_312, reason="this environment runs Python 3.12")
def test_live_health_outside_python_312_is_unavailable() -> None:
    _, report = _health(())
    assert report.status == "unavailable"
    python = _checks(report)["python"]
    assert not python.ok and "API Forge requires Python 3.12" in python.detail


# --- health units ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("0.1.0", True),
        ("0.1.99", True),
        ("0.2.0", False),
        ("0.0.9", False),
        ("1.0.0", False),
        ("0.1", None),
        ("v0.1.0", None),
        ("0.1.0rc1", None),
        ("", None),
        ("x.y.z", None),
    ],
)
def test_version_window(version: str, expected: bool | None) -> None:
    assert health.in_window(version, ">=0.1.0,<0.2.0") is expected


def test_version_window_operators() -> None:
    assert health.in_window("1.2.3", "==1.2.3") is True
    assert health.in_window("1.2.3", ">1.2.3") is False
    assert health.in_window("1.2.3", "<=1.2.3") is True
    with pytest.raises(ValueError):
        health.in_window("1.2.3", "~=1.2")


def test_cli_entry_point_is_looked_up_by_spec(monkeypatch: pytest.MonkeyPatch) -> None:
    looked_up: list[str] = []

    def find_spec(name: str) -> object:
        looked_up.append(name)
        return object() if name == "apiforge.cli" else None

    monkeypatch.setattr(health.importlib.util, "find_spec", find_spec)
    assert health.cli_found() is True
    assert looked_up == ["apiforge.cli"]  # found by spec, never imported


@pytest.mark.parametrize("outcome", [None, ImportError("broken parent"), ValueError("spec")])
def test_cli_entry_point_missing_or_broken_is_not_found(
    monkeypatch: pytest.MonkeyPatch, outcome: object
) -> None:
    def find_spec(name: str) -> object:
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(health.importlib.util, "find_spec", find_spec)
    assert health.cli_found() is False


@pytest.mark.parametrize(
    ("cli", "status", "ok"), [(True, "ok", True), (False, "unavailable", False)]
)
def test_live_health_reports_the_cli_and_never_runs_a_native_process(
    monkeypatch: pytest.MonkeyPatch, cli: bool, status: str, ok: bool
) -> None:
    # Importing the native CLI costs seconds (3-17 s measured): health stays far below the
    # core's 10 s budget because it never spawns the API Forge (no doctor, no CLI).
    def spawn(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("health must not run a native process")

    monkeypatch.setattr(_shell, "run_native", spawn)
    monkeypatch.setattr(subprocess, "Popen", spawn)
    monkeypatch.setattr(
        health,
        "_live_environment",
        lambda: (
            [
                {"name": "python", "ok": True, "detail": "Python 3.12"},
                {"name": "import", "ok": True, "detail": "apiforge 0.1.0 importable"},
            ],
            "0.1.0",
        ),
    )
    monkeypatch.setattr(health, "cli_found", lambda: cli)
    reply = health.health_reply(_shell.AdapterOptions())
    assert reply.status == "ok"
    assert reply.payload is not None and reply.payload["status"] == status
    checks = {check["name"]: check for check in reply.payload["checks"]}
    assert list(checks) == CHECKS
    assert checks["cli"]["ok"] is ok and "apiforge.cli" in checks["cli"]["detail"]


def test_health_module_no_longer_carries_the_doctor() -> None:
    for name in ("run_doctor", "doctor_check", "DOCTOR_TIMEOUT", "IGNORED_CAPABILITIES"):
        assert not hasattr(health, name), name


# --- translation of cases and native errors (5.3) -------------------------------------------

PRODUCER = Producer(id="api-forge", version="0.3.0")
ANALYZE_RECORDING = DEFAULT / "api.analyze.analyze.json"
WORKSPACE_FILES = [
    "openapi.yaml",
    "app/__init__.py",
    "app/main.py",
    "requirements.txt",
    "change-bundle.json",
]
# Machine-specific fragments a portable recording never contains: a drive path (raw or JSON-
# escaped), a user directory, a temp directory.
MACHINE_PATH = re.compile(
    r"(?<![A-Za-z])[A-Za-z]:(?:\\|/(?!/))|/Users/|/home/|AppData|/tmp/", re.IGNORECASE
)


def _translate_module() -> Any:
    return importlib.import_module("theforge_apiforge.translate")


def _analyze_recording() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(ANALYZE_RECORDING.read_text(encoding="utf-8"))
    return data


def _stage(cwd: Path, paths: list[str] | None = None) -> _shell.StagedInput:
    files = []
    for rel in WORKSPACE_FILES if paths is None else paths:
        data = (WORKSPACE / rel).read_bytes()
        files.append({"path": rel, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
    payload = {"context": {"root": str(WORKSPACE.resolve()), "files": files}}
    return _shell.stage_context(payload, cwd)


def _write_case(cwd: Path, recording: dict[str, Any]) -> None:
    """Materialize the recorded case files as the API Forge writes them (sorted, indent 2)."""
    case = cwd / recording["case_dir"]
    case.mkdir(parents=True, exist_ok=True)
    for name, document in recording["case_files"].items():
        text = json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        (case / name).write_bytes(text.encode("utf-8"))


def _translated(
    cwd: Path, recording: dict[str, Any] | None = None, state: str = "supported"
) -> tuple[Any, _shell.StagedInput]:
    recording = _analyze_recording() if recording is None else recording
    stage = _stage(cwd)
    _write_case(cwd, recording)
    translate = _translate_module()
    case = translate.read_case(cwd, recording["case_dir"])
    return translate.translate_case(case, stage, state=state), stage


def _validated(draft: Any, cwd: Path) -> ExecutionResult:
    assert isinstance(draft, _shell.ResultDraft), draft
    reply = _shell.finalize(draft, cwd)
    assert reply.status in ("ok", "partial"), reply.error
    result = from_dict(ExecutionResult, reply.payload, "$.payload")
    validate_result(result, expected=PRODUCER)
    return result


def test_analyze_recording_is_a_recorded_case_of_the_example_workspace() -> None:
    recording = _analyze_recording()
    assert recording["provenance"] == "recorded" and recording["assembled_from"]
    assert recording["exit_code"] == 0
    assert recording["argv"][:1] == ["analyze"] and "--fail-on" not in recording["argv"]
    assert recording["case_dir"] == catalog.VERB_MAP["api.analyze"].output_dir
    assert {"case.json", "findings.json", "facts.json"} <= set(recording["case_files"])
    raw = ANALYZE_RECORDING.read_bytes()
    assert b"\r" not in raw and MACHINE_PATH.search(raw.decode("utf-8")) is None
    # Deterministic: the file is its own canonical serialization.
    assert (
        raw.decode("utf-8")
        == json.dumps(recording, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    )


def test_translated_case_passes_core_integrity_with_native_ids(tmp_path: Path) -> None:
    draft, _ = _translated(tmp_path)
    result = _validated(draft, tmp_path)
    recording = _analyze_recording()
    native_facts = [fact["fact_id"] for fact in recording["case_files"]["facts.json"]["facts"]]
    native_findings = recording["case_files"]["findings.json"]["findings"]
    assert [item.id for item in result.evidence] == native_facts
    assert [item.id for item in result.findings] == [f["finding_id"] for f in native_findings]
    finding = result.findings[0]
    assert finding.title == "AF-CODE-002: Code route missing from contract"
    assert finding.severity == "medium"
    assert finding.evidence_ids == native_findings[0]["evidence"]
    assert all(item.epistemic == "observed" for item in result.evidence)
    route = next(item for item in result.evidence if item.id == finding.evidence_ids[0])
    assert route.subject == "code.route"
    assert route.claim == 'code.route: method="delete", path="/orders/{order_id}"'
    assert route.location is not None
    assert (route.location.path, route.location.line) == ("app/main.py", 18)


def test_evidence_hash_is_null_or_the_verified_sha256_of_the_located_file(tmp_path: Path) -> None:
    draft, stage = _translated(tmp_path)
    result = _validated(draft, tmp_path)
    paths = set()
    for item in result.evidence:
        assert item.location is not None
        paths.add(item.location.path)
        if item.hash is not None:
            expected = hashlib.sha256((WORKSPACE / item.location.path).read_bytes()).hexdigest()
            assert item.hash == expected == stage.files[item.location.path]
    # Code facts are relative to --project, the contract fact to the native cwd (stage/...):
    # both land on the workspace path with their verified hash.
    assert paths == {"app/main.py", "openapi.yaml"}
    assert all(item.hash is not None for item in result.evidence)


def test_divergent_native_sha256_becomes_null(tmp_path: Path) -> None:
    recording = _analyze_recording()
    facts = recording["case_files"]["facts.json"]["facts"]
    facts[0]["source"]["sha256"] = "0" * 64  # other content
    facts[1]["source"]["sha256"] = "sha256:" + facts[1]["source"]["sha256"]  # prefixed, equal
    facts[2]["source"]["sha256"] = facts[2]["source"]["sha256"].upper()  # malformed
    draft, stage = _translated(tmp_path, recording)
    result = _validated(draft, tmp_path)
    by_id = {item.id: item for item in result.evidence}
    assert by_id[facts[0]["fact_id"]].hash is None
    assert by_id[facts[1]["fact_id"]].hash == stage.files["app/main.py"]
    assert by_id[facts[2]["fact_id"]].hash is None


def test_unstaged_or_outside_locations_have_no_hash(tmp_path: Path) -> None:
    recording = _analyze_recording()
    facts = recording["case_files"]["facts.json"]["facts"]
    facts[0]["source"]["path"] = "../../etc/passwd"
    stage = _stage(tmp_path, ["openapi.yaml"])  # app/main.py not staged
    _write_case(tmp_path, recording)
    translate = _translate_module()
    draft = translate.translate_case(translate.read_case(tmp_path, "case"), stage)
    result = _validated(draft, tmp_path)
    by_id = {item.id: item for item in result.evidence}
    outside = by_id[facts[0]["fact_id"]]
    assert outside.location is None and outside.hash is None
    assert any(
        facts[0]["fact_id"] in note and "outside the workspace" in note
        for note in result.limitations
    )
    unstaged = by_id[facts[1]["fact_id"]]
    assert unstaged.location is not None and unstaged.location.path == "app/main.py"
    assert unstaged.hash is None


def test_not_applicable_findings_are_omitted_and_counted(tmp_path: Path) -> None:
    recording = _analyze_recording()
    findings = recording["case_files"]["findings.json"]["findings"]
    base = findings[0]
    findings.extend(
        [{**base, "finding_id": f"finding:na{n}", "status": "not_applicable"} for n in range(2)]
    )
    findings.append(
        {**base, "finding_id": "finding:unresolved", "status": "unresolved", "severity": "high"}
    )
    draft, _ = _translated(tmp_path, recording)
    result = _validated(draft, tmp_path)
    assert [item.id for item in result.findings] == [base["finding_id"], "finding:unresolved"]
    assert "2 native finding(s) with status not_applicable omitted" in result.limitations


def test_dangling_fact_reference_is_dropped_not_invented(tmp_path: Path) -> None:
    recording = _analyze_recording()
    finding = recording["case_files"]["findings.json"]["findings"][0]
    finding["evidence"] = [*finding["evidence"], "fact:missing"]
    finding["severity"] = "urgent"
    draft, _ = _translated(tmp_path, recording)
    result = _validated(draft, tmp_path)
    assert result.findings[0].evidence_ids == finding["evidence"][:1]
    assert "fact:missing" not in {item.id for item in result.evidence}
    assert result.findings[0].severity == "info"
    assert any("fact:missing" in note and "dropped" in note for note in result.limitations)
    assert any("unknown native severity" in note for note in result.limitations)


def test_heuristic_capability_evidence_is_inferred(tmp_path: Path) -> None:
    draft, _ = _translated(tmp_path, state="heuristic")
    result = _validated(draft, tmp_path)
    assert {item.epistemic for item in result.evidence} == {"inferred"}


def test_case_files_are_artifacts_with_their_sha256(tmp_path: Path) -> None:
    draft, _ = _translated(tmp_path)
    result = _validated(draft, tmp_path)
    names = sorted(_analyze_recording()["case_files"])
    assert [item.path for item in result.artifacts] == [f"case/{name}" for name in names]
    for item in result.artifacts:
        assert item.sha256 == hashlib.sha256((tmp_path / item.path).read_bytes()).hexdigest()
    # The case files are written byte for byte as the API Forge writes them: the native
    # manifest's hashes match the attached files (case.json cannot hash itself).
    manifest = _analyze_recording()["case_files"]["case.json"]["artifacts"]
    attached = {item.path: item.sha256 for item in result.artifacts}
    assert all(attached[f"case/{entry['path']}"] == entry["sha256"] for entry in manifest.values())


def test_case_links_are_never_followed_or_attached(tmp_path: Path) -> None:
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    _write_case(tmp_path, _analyze_recording())
    try:
        (tmp_path / "case" / "linked.json").symlink_to(outside)
    except OSError:
        pytest.skip("symlinks are not available to this user")
    case = _translate_module().read_case(tmp_path, "case")
    assert "case/linked.json" not in [item["path"] for item in case.artifacts]
    assert "linked.json" not in case.documents
    assert any("case/linked.json" in note for note in case.limitations)


@pytest.mark.parametrize("missing", ["findings.json", "facts.json"])
def test_case_without_findings_or_facts_is_a_native_invalid_error(
    tmp_path: Path, missing: str
) -> None:
    recording = _analyze_recording()
    del recording["case_files"][missing]
    draft, _ = _translated(tmp_path, recording)
    assert isinstance(draft, _shell.Reply) and draft.status == "error"
    assert draft.error is not None and draft.error["code"] == "APIFORGE-ADAPTER-NATIVE-INVALID"
    assert missing in draft.error["detail"]


def test_missing_case_directory_is_a_native_invalid_error(tmp_path: Path) -> None:
    translate = _translate_module()
    draft = translate.translate_case(translate.read_case(tmp_path, "case"), _stage(tmp_path))
    assert isinstance(draft, _shell.Reply) and draft.error is not None
    assert draft.error["code"] == "APIFORGE-ADAPTER-NATIVE-INVALID"


def _error_recording(scenario: str) -> dict[str, Any]:
    path = SCENARIOS / scenario / "api.analyze.analyze.error.json"
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    assert data["provenance"] == "hand-built" and data["assembled_from"]
    assert b"\r" not in path.read_bytes()
    assert MACHINE_PATH.search(path.read_text(encoding="utf-8")) is None
    return data


def test_recorded_refusal_keeps_the_af_code_field_and_unlock() -> None:
    recording = _error_recording("analyze-refused")
    assert recording["exit_code"] == 2
    reply = _translate_module().native_failure(recording["exit_code"], recording["stderr"])
    assert reply.status == "refused"
    error = from_dict(ErrorInfo, reply.error, "$.error")
    assert error.code == "AF-OPENAPI-UNSUPPORTED-VERSION"
    assert error.detail == "openapi.yaml: openapi must be 3.1.x, got None"
    assert error.field == "unknown"
    assert error.unlock == "inspect the documented contract and rerun the verifier"


def test_recorded_exit_3_is_an_error_with_the_af_code_intact() -> None:
    recording = _error_recording("analyze-error")
    assert recording["exit_code"] == 3
    reply = _translate_module().native_failure(recording["exit_code"], recording["stderr"])
    assert reply.status == "error"
    error = from_dict(ErrorInfo, reply.error, "$.error")
    assert (error.code, error.detail) == ("AF-CASE-INVALID", "case/case.json")
    assert (error.field, error.unlock) == (
        "unknown",
        "inspect the documented contract and rerun the verifier",
    )


def test_error_scenarios_are_complete() -> None:
    for scenario in ("analyze-refused", "analyze-error"):
        directory = SCENARIOS / scenario
        assert (directory / "environment.json").is_file()
        assert (directory / "health.json").is_file()
        assert not (directory / "api.analyze.analyze.json").exists()


@pytest.mark.parametrize(
    ("exit_code", "stderr", "status", "code", "field", "unlock"),
    [
        (
            2,
            "AF-INPUT-NOT-FOUND: stage/x.yaml (field=analysis input; unlock=correct the input)",
            "refused",
            "AF-INPUT-NOT-FOUND",
            "analysis input",
            "correct the input",
        ),
        (
            2,
            "AF-CLI-INTERNAL: boom (field=unknown; unlock=report it)",
            "error",
            "AF-CLI-INTERNAL",
            "unknown",
            "report it",
        ),
        (
            3,
            "AF-CASE-MANIFEST-MISSING: case/case.json (field=unknown; unlock=rerun)",
            "error",
            "AF-CASE-MANIFEST-MISSING",
            "unknown",
            "rerun",
        ),
        (1, "AF-CHANGE-X: odd exit (field=f; unlock=u)", "error", "AF-CHANGE-X", "f", "u"),
        # Other output before the AF-* line and an unlock with parentheses.
        (
            2,
            "warning: something\nAF-ROUTING-NO-FINDINGS: nothing to review (field=bundle; "
            "unlock=add findings (see docs))\n",
            "refused",
            "AF-ROUTING-NO-FINDINGS",
            "bundle",
            "add findings (see docs)",
        ),
        (2, "AF-BARE-CODE: only a detail", "refused", "AF-BARE-CODE", None, None),
    ],
)
def test_af_lines_map_to_refusal_or_error(
    exit_code: int, stderr: str, status: str, code: str, field: str | None, unlock: str | None
) -> None:
    reply = _translate_module().native_failure(exit_code, stderr)
    assert reply.status == status
    assert reply.error is not None
    assert (reply.error["code"], reply.error["field"], reply.error["unlock"]) == (
        code,
        field,
        unlock,
    )


def test_af_detail_with_parentheses_is_kept_whole() -> None:
    reply = _translate_module().native_failure(
        2, "AF-ROUTING-NO-FINDINGS: nothing (yet) to review (field=bundle; unlock=u)"
    )
    assert reply.error is not None and reply.error["detail"] == "nothing (yet) to review"


@pytest.mark.parametrize(
    "stderr",
    [
        "",
        "Traceback (most recent call last):\n  boom\n",
        "af-lowercase: not a code",
        pytest.param("x" * 2000, id="long-stderr"),
    ],
)
def test_unrecognized_failure_is_a_structured_error_with_the_stderr_tail(stderr: str) -> None:
    reply = _translate_module().native_failure(3, stderr)
    assert reply.status == "error" and reply.error is not None
    error = from_dict(ErrorInfo, reply.error, "$.error")
    assert error.code == "APIFORGE-ADAPTER-NATIVE-FAILURE"
    assert "exited with code 3" in error.detail
    tail = stderr.strip()
    if tail:
        assert tail[-100:] in error.detail
    assert len(error.detail) <= 600


def test_multi_line_af_message_keeps_field_and_unlock() -> None:
    reply = _translate_module().native_failure(
        2, "warning: x\nAF-X: line1\ncontinued (field=f; unlock=u)\n"
    )
    assert reply.status == "refused" and reply.error is not None
    assert (reply.error["code"], reply.error["field"], reply.error["unlock"]) == ("AF-X", "f", "u")
    assert reply.error["detail"] == "line1\ncontinued"


def test_recognized_af_detail_is_bounded() -> None:
    reply = _translate_module().native_failure(
        2, "AF-LONG: " + "d" * 5000 + " (field=f; unlock=" + "u" * 5000 + ")"
    )
    assert reply.error is not None and reply.error["code"] == "AF-LONG"
    assert len(reply.error["detail"]) <= 500 and reply.error["detail"].startswith("ddd")
    assert len(reply.error["unlock"]) <= 500 and reply.error["field"] == "f"


# --- execute (5.4) --------------------------------------------------------------------------

CHANGE_RECORDING = DEFAULT / "api.change-control.run.json"
ACTIONS = {"api.analyze": "analyze", "api.change-control": "run"}


def _context(paths: list[str] | None = None, root: Path = WORKSPACE) -> dict[str, Any]:
    files = []
    for rel in WORKSPACE_FILES if paths is None else paths:
        data = (root / rel).read_bytes()
        files.append({"path": rel, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
    return {"root": str(root.resolve()), "files": files}


def _execute_payload(
    capability: str, paths: list[str] | None = None, root: Path = WORKSPACE
) -> dict[str, Any]:
    return {
        "task": {"intent": "review the orders API", "budget_profile": "economy"},
        "capability": capability,
        "action": ACTIONS[capability],
        "context": _context(paths, root),
    }


def _execute(
    cwd: Path, payload: dict[str, Any], replay: Path | None = DEFAULT
) -> tuple[Response, dict[str, Any]]:
    """Run ``execute`` as the core does, in ``cwd`` (never the repository)."""
    cwd.mkdir(parents=True, exist_ok=True)
    request = json.dumps(
        {
            "protocol": PROTOCOL_V1,
            "kind": "Request",
            "op": "execute",
            "request_id": "req-execute",
            "payload": payload,
        }
    ).encode()
    options = () if replay is None else ("--replay", str(replay))
    out = subprocess.run(
        [sys.executable, "-m", "theforge_apiforge", *options, "execute"],
        input=request,
        capture_output=True,
        timeout=120,
        cwd=cwd,
    )
    assert out.returncode == 0, out.stderr
    data = json.loads(out.stdout)
    response = from_dict(Response, data)
    assert response.op == "execute" and response.request_id == "req-execute"
    return response, data


def _listing(cwd: Path) -> list[str]:
    return sorted(p.relative_to(cwd).as_posix() for p in cwd.rglob("*") if p.is_file())


def _result(response: Response, data: dict[str, Any], cwd: Path) -> ExecutionResult:
    assert response.status in ("ok", "partial"), response.error
    result = from_dict(ExecutionResult, data["payload"], "$.payload")
    validate_result(result, expected=PRODUCER)
    # The cwd ends with exactly the declared artifacts, each with its sha256.
    assert _listing(cwd) == sorted(item.path for item in result.artifacts)
    assert sorted(p.name for p in cwd.iterdir() if p.is_dir()) == sorted(
        {item.path.split("/")[0] for item in result.artifacts if "/" in item.path}
    )
    for item in result.artifacts:
        assert item.sha256 == hashlib.sha256((cwd / item.path).read_bytes()).hexdigest()
    return result


def _change_recording() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(CHANGE_RECORDING.read_text(encoding="utf-8"))
    return data


def test_change_control_recording_is_a_provisional_live_shaped_case() -> None:
    recording = _change_recording()
    assert recording["provenance"] == "hand-built" and recording["assembled_from"]
    assert recording["exit_code"] == 0 and recording["native_cwd"] == "stage"
    assert recording["argv"][:2] == ["change-control", "run"]
    assert "--fail-on" not in recording["argv"]
    assert recording["case_dir"] == catalog.VERB_MAP["api.change-control"].output_dir
    assert {"case/case.json", "case/findings.json", "case/facts.json"} <= set(
        recording["case_files"]
    )
    raw = CHANGE_RECORDING.read_bytes()
    assert b"\r" not in raw and MACHINE_PATH.search(raw.decode("utf-8")) is None
    assert (
        raw.decode("utf-8")
        == json.dumps(recording, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    )


def test_internal_error_scenario_has_no_af_line() -> None:
    recording = _error_recording("analyze-internal")
    assert recording["exit_code"] not in (0, 2)
    assert re.search(r"^AF-", recording["stderr"], re.MULTILINE) is None
    directory = SCENARIOS / "analyze-internal"
    assert (directory / "environment.json").is_file() and (directory / "health.json").is_file()


def test_replay_execute_analyze_is_ok_with_native_ids(tmp_path: Path) -> None:
    cwd = tmp_path / "work"
    response, data = _execute(cwd, _execute_payload("api.analyze"))
    assert response.status == "ok"
    result = _result(response, data, cwd)
    recording = _analyze_recording()
    assert [item.id for item in result.evidence] == [
        fact["fact_id"] for fact in recording["case_files"]["facts.json"]["facts"]
    ]
    assert [item.id for item in result.findings] == [
        f["finding_id"] for f in recording["case_files"]["findings.json"]["findings"]
    ]
    assert [item.path for item in result.artifacts] == sorted(
        f"case/{name}" for name in recording["case_files"]
    )
    assert all(item.hash is not None for item in result.evidence)
    # Replay writes the case files with the native serializer: the case manifest hashes hold.
    manifest = recording["case_files"]["case.json"]["artifacts"]
    attached = {item.path: item.sha256 for item in result.artifacts}
    assert all(attached[f"case/{entry['path']}"] == entry["sha256"] for entry in manifest.values())


def test_replay_execute_change_control_is_ok_with_native_ids(tmp_path: Path) -> None:
    cwd = tmp_path / "work"
    response, data = _execute(cwd, _execute_payload("api.change-control"))
    assert response.status == "ok"
    result = _result(response, data, cwd)
    files = _change_recording()["case_files"]
    native_facts = [fact["fact_id"] for fact in files["case/facts.json"]["facts"]]
    assert [item.id for item in result.evidence] == native_facts
    assert [item.id for item in result.findings] == [
        f["finding_id"] for f in files["case/findings.json"]["findings"]
    ]
    assert result.findings[0].title.startswith("AF-CODE-002: ")
    # Code facts are relative to the bundle's project (app), the contract fact to the staged
    # workspace root (the native cwd): both land on workspace paths with verified hashes.
    assert {item.location.path for item in result.evidence if item.location} == {
        "app/main.py",
        "openapi.yaml",
    }
    for item in result.evidence:
        assert item.location is not None
        assert (
            item.hash == hashlib.sha256((WORKSPACE / item.location.path).read_bytes()).hexdigest()
        )
    assert [item.path for item in result.artifacts] == sorted(
        f"change-control/{name}" for name in files
    )
    assert (cwd / "change-control" / "graph" / "nodes.jsonl").read_text(encoding="utf-8") == files[
        "graph/nodes.jsonl"
    ]


@pytest.mark.parametrize(
    ("scenario", "status", "code"),
    [
        ("analyze-refused", "refused", "AF-OPENAPI-UNSUPPORTED-VERSION"),
        ("analyze-error", "error", "AF-CASE-INVALID"),
        ("analyze-internal", "error", "APIFORGE-ADAPTER-NATIVE-FAILURE"),
    ],
)
def test_replay_execute_native_failures(
    tmp_path: Path, scenario: str, status: str, code: str
) -> None:
    cwd = tmp_path / "work"
    response, _ = _execute(cwd, _execute_payload("api.analyze"), SCENARIOS / scenario)
    assert response.status == status
    assert response.error is not None and response.error.code == code
    if scenario == "analyze-internal":
        assert "RuntimeError: unexpected extractor state" in response.error.detail
    assert _listing(cwd) == [] and list(cwd.iterdir()) == []


def test_replay_execute_unrecorded_action_is_missing(tmp_path: Path) -> None:
    cwd = tmp_path / "work"
    response, _ = _execute(
        cwd, _execute_payload("api.change-control"), SCENARIOS / "analyze-refused"
    )
    assert response.status == "error" and response.error is not None
    assert response.error.code == "ADAPTER-REPLAY-MISSING"
    assert "api.change-control.run.json" in response.error.detail
    assert list(cwd.iterdir()) == []


@pytest.mark.parametrize("capability", EXPOSED)
def test_execute_without_compatible_input_is_partial_without_recording(
    tmp_path: Path, capability: str
) -> None:
    replay = tmp_path / "replay"  # environment only: no recording is consulted
    replay.mkdir()
    (replay / "environment.json").write_bytes((DEFAULT / "environment.json").read_bytes())
    cwd = tmp_path / "work"
    response, data = _execute(cwd, _execute_payload(capability, ["requirements.txt"]), replay)
    assert response.status == "partial"
    result = _result(response, data, cwd)
    assert list(result.findings) == []
    assert any(note.startswith("no input: expected") for note in result.limitations)


def _large_scenario(directory: Path) -> int:
    """A large-output scenario derived from the default analyze recording (never versioned:
    it is above the 4 MiB inline limit)."""
    directory.mkdir()
    for name in ("environment.json", "health.json"):
        (directory / name).write_bytes((DEFAULT / name).read_bytes())
    recording = _analyze_recording()
    recording["provenance"] = "derived"
    findings = recording["case_files"]["findings.json"]["findings"]
    base = findings[0]
    count = 3000
    findings[:] = [
        {**base, "finding_id": f"finding:{n:06d}", "title": f"{n} " + "t" * 1500}
        for n in range(count)
    ]
    (directory / "api.analyze.analyze.json").write_text(json.dumps(recording), encoding="utf-8")
    return count


def test_replay_execute_large_output_is_partial_with_artifact(tmp_path: Path) -> None:
    total = _large_scenario(tmp_path / "large")
    cwd = tmp_path / "work"
    response, data = _execute(cwd, _execute_payload("api.analyze"), tmp_path / "large")
    assert response.status == "partial"
    result = _result(response, data, cwd)
    assert 0 < len(result.findings) < total
    assert _shell.SPILL_PATH in [item.path for item in result.artifacts]
    assert any(note.startswith("output truncated:") for note in result.limitations)
    assert _shell.inline_size(data["payload"]) <= _shell.INLINE_LIMIT


def test_bundle_paths_outside_the_workspace_are_refused(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    for rel in WORKSPACE_FILES:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes((WORKSPACE / rel).read_bytes())
    bundle = json.loads((WORKSPACE / "change-bundle.json").read_text(encoding="utf-8"))
    bundle["contract"] = "../outside/openapi.yaml"
    (root / "change-bundle.json").write_text(json.dumps(bundle), encoding="utf-8")
    cwd = tmp_path / "work"
    response, _ = _execute(cwd, _execute_payload("api.change-control", root=root))
    assert response.status == "refused" and response.error is not None
    assert response.error.code == "APIFORGE-ADAPTER-INPUT-OUTSIDE"
    assert response.error.field == "bundle.contract"
    assert list(cwd.iterdir()) == []


# --- live backend, offline: the native process executor is a fake --------------------------


class _FakeNative:
    """Stands in for ``run_native``: records the call and leaves what the verb would."""

    def __init__(self, recording: dict[str, Any] | None, returncode: int = 0, stderr: bytes = b""):
        self.recording = recording
        self.returncode = returncode
        self.stderr = stderr
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self, argv: list[str], *, cwd: Path, env: dict[str, str], timeout: float
    ) -> _shell.NativeOutcome:
        self.calls.append(
            {"argv": list(argv), "cwd": Path(cwd), "env": dict(env), "timeout": timeout}
        )
        # What the API Forge leaves in its cwd whatever the verb: economy ledger and cache.
        (Path(cwd) / ".apiforge" / "cache").mkdir(parents=True, exist_ok=True)
        (Path(cwd) / ".apiforge" / "economy.jsonl").write_text("{}\n", encoding="utf-8")
        if self.recording is not None and self.returncode == 0:
            out = Path(argv[argv.index("--out-dir") + 1])
            out = out if out.is_absolute() else Path(cwd) / out
            for name, document in self.recording["case_files"].items():
                target = out / name
                target.parent.mkdir(parents=True, exist_ok=True)
                text = (
                    document
                    if isinstance(document, str)
                    else json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
                )
                target.write_bytes(text.encode("utf-8"))
        return _shell.NativeOutcome(returncode=self.returncode, stdout=b"{}", stderr=self.stderr)


def _live_respond(
    cwd: Path, payload: dict[str, Any], fake: _FakeNative
) -> tuple[Response, dict[str, Any]]:
    """``respond`` in process with the live execute backend and the fake executor; describe
    answers from the default replay environment (this interpreter has no API Forge)."""
    main = importlib.import_module("theforge_apiforge.__main__")
    execute = importlib.import_module("theforge_apiforge.execute")
    handlers = {
        "describe": lambda options: main.describe(_shell.AdapterOptions(replay=DEFAULT)),
        "health": main.health,
        "execute": lambda options: execute.handler(options, run=fake),
    }
    cwd.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(
        {
            "protocol": PROTOCOL_V1,
            "kind": "Request",
            "op": "execute",
            "request_id": "req-live",
            "payload": payload,
        }
    ).encode()
    body = _shell.respond(
        ["execute"], raw, provider_id="api-forge", version="0.1.0", handlers=handlers, cwd=cwd
    )
    data = json.loads(body)
    return from_dict(Response, data), data


def _inside(path: Path, root: Path) -> bool:
    return path.resolve().is_relative_to(root.resolve())


@pytest.mark.parametrize(
    ("capability", "recording"),
    [("api.analyze", ANALYZE_RECORDING), ("api.change-control", CHANGE_RECORDING)],
)
def test_live_verb_keeps_every_output_under_the_run_cwd(
    tmp_path: Path, capability: str, recording: Path
) -> None:
    cwd = tmp_path / "work"
    fake = _FakeNative(json.loads(recording.read_text(encoding="utf-8")))
    response, data = _live_respond(cwd, _execute_payload(capability), fake)
    assert response.status == "ok", response.error
    result = _result(response, data, cwd)
    assert len(fake.calls) == 1
    call = fake.calls[0]
    argv, native_cwd = call["argv"], call["cwd"]
    spec = catalog.VERB_MAP[capability]
    # Same interpreter, public CLI, mapped verb, no failure threshold.
    assert argv[:3] == [sys.executable, "-c", "from apiforge.cli import app; app()"]
    flags = [index for index, token in enumerate(spec.argv) if token.startswith("--")]
    verb = list(spec.argv[: flags[0] if flags else len(spec.argv)])
    assert argv[3 : 3 + len(verb)] == verb
    for index in flags:  # the verb's fixed flags are kept with their values
        position = argv.index(spec.argv[index])
        assert argv[position + 1] == spec.argv[index + 1]
    assert not any(token.startswith("--fail-on") for token in argv)
    # Native cwd under the run cwd, cache off, nothing else added to the environment.
    assert _inside(native_cwd, cwd)
    assert call["env"] == {"APIFORGE_CACHE": "off"}
    assert call["timeout"] == pytest.approx(60.0 * 0.85)
    # Output dir under the run cwd and outside every input; inputs come from stage/.
    out = Path(argv[argv.index("--out-dir") + 1])
    out = out if out.is_absolute() else native_cwd / out
    assert _inside(out, cwd) and not _inside(out, cwd / "stage")
    assert ".." not in Path(argv[argv.index("--out-dir") + 1]).parts
    for flag in ("--contract", "--project", "--bundle"):
        if flag in argv:
            value = Path(argv[argv.index(flag) + 1])
            value = value if value.is_absolute() else native_cwd / value
            assert _inside(value, cwd / "stage"), (flag, value)
            assert not _inside(out, value) and not _inside(value, out)
    # .apiforge/ (ledger, cache) and stage/ are gone: only the case files remain.
    assert not (cwd / ".apiforge").exists() and not (cwd / "stage").exists()
    assert result.artifacts and all(
        item.path.startswith(spec.output_dir + "/") for item in result.artifacts
    )


def test_live_native_failure_decodes_stderr_leniently(tmp_path: Path) -> None:
    cwd = tmp_path / "work"
    fake = _FakeNative(
        None,
        returncode=2,
        stderr=b"\xff\xfe noise\nAF-INPUT-NOT-FOUND: stage/x (field=f; unlock=u)\n",
    )
    response, _ = _live_respond(cwd, _execute_payload("api.analyze"), fake)
    assert response.status == "refused" and response.error is not None
    assert response.error.code == "AF-INPUT-NOT-FOUND"
    assert list(cwd.iterdir()) == []


def test_live_verb_is_not_called_without_input(tmp_path: Path) -> None:
    fake = _FakeNative(None)
    response, _ = _live_respond(
        tmp_path / "work", _execute_payload("api.analyze", ["requirements.txt"]), fake
    )
    assert response.status == "partial" and fake.calls == []


class _AbsolutePaths(_FakeNative):
    """Like the API Forge change-control run: some outputs embed absolute run-dir paths."""

    def __call__(
        self, argv: list[str], *, cwd: Path, env: dict[str, str], timeout: float
    ) -> _shell.NativeOutcome:
        outcome = super().__call__(argv, cwd=cwd, env=env, timeout=timeout)
        out = Path(argv[argv.index("--out-dir") + 1])
        case = out / "case" / "case.json"
        brief = {
            "proof": [str(case), case.as_posix(), str(out)],
            "cwd": str(Path(cwd)),
            "verifier": f"apiforge verify --run-dir {out}",
        }
        (out / "brief.json").write_text(
            json.dumps(brief, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (out / "notes.txt").write_text(f"run dir {out}\n", encoding="utf-8")
        # A file a native manifest hashes is never rewritten.
        hashed = out / "hashed.txt"
        hashed.write_text(f"pinned {out}\n", encoding="utf-8")
        digest = hashlib.sha256(hashed.read_bytes()).hexdigest()
        (out / "manifest.json").write_text(
            json.dumps({"hashed.txt": digest}) + "\n", encoding="utf-8"
        )
        return outcome


def test_live_absolute_run_paths_become_relative_in_artifacts(tmp_path: Path) -> None:
    cwd = tmp_path / "work"
    fake = _AbsolutePaths(_change_recording())
    response, data = _live_respond(cwd, _execute_payload("api.change-control"), fake)
    assert response.status == "ok", response.error
    result = _result(response, data, cwd)  # sha256 of every artifact == bytes on disk
    run = str(cwd.resolve())
    for item in result.artifacts:
        if item.path == "change-control/hashed.txt":
            continue
        text = (cwd / item.path).read_text(encoding="utf-8")
        for form in (run, run.replace("\\", "\\\\"), cwd.resolve().as_posix()):
            assert form not in text, item.path
    brief = json.loads((cwd / "change-control" / "brief.json").read_text(encoding="utf-8"))
    assert brief["proof"] == ["change-control/case/case.json"] * 2 + ["change-control"]
    assert brief["cwd"] == "stage"
    assert brief["verifier"] == "apiforge verify --run-dir change-control"
    assert (cwd / "change-control" / "notes.txt").read_text(
        encoding="utf-8"
    ) == "run dir change-control\n"
    assert run in (cwd / "change-control" / "hashed.txt").read_text(encoding="utf-8")
    assert any(
        "change-control/hashed.txt" in note and "absolute" in note for note in result.limitations
    )


def _replay_with_case_files(directory: Path, files: dict[str, Any]) -> None:
    directory.mkdir()
    (directory / "environment.json").write_bytes((DEFAULT / "environment.json").read_bytes())
    recording = _analyze_recording()
    recording["case_files"] = {**recording["case_files"], **files}
    (directory / "api.analyze.analyze.json").write_text(json.dumps(recording), encoding="utf-8")


@pytest.mark.parametrize(
    "key",
    [
        "../x.json",
        "case/../../x.json",
        "/abs.json",
        "C:/x.json",
        "C:x.json",
        "a\\..\\..\\x.json",
        "\\\\srv\\s\\x.json",
    ],
)
def test_replay_rejects_case_file_keys_outside_the_case(tmp_path: Path, key: str) -> None:
    _replay_with_case_files(tmp_path / "replay", {key: {"x": 1}})
    cwd = tmp_path / "work"
    response, _ = _execute(cwd, _execute_payload("api.analyze"), tmp_path / "replay")
    assert response.status == "error" and response.error is not None
    assert response.error.code == "ADAPTER-REPLAY-INVALID"
    assert list(cwd.iterdir()) == []
    assert sorted(p.name for p in tmp_path.iterdir()) == ["replay", "work"]


@pytest.mark.parametrize(
    "files",
    [{"a": "x", "a/b.json": {}}, {"x.json": {}, "./x.json": {}}, {"D/b.json": {}, "d": "x"}],
)
def test_replay_rejects_conflicting_case_file_keys(tmp_path: Path, files: dict[str, Any]) -> None:
    _replay_with_case_files(tmp_path / "replay", files)
    cwd = tmp_path / "work"
    response, _ = _execute(cwd, _execute_payload("api.analyze"), tmp_path / "replay")
    assert response.status == "error" and response.error is not None
    assert response.error.code == "ADAPTER-REPLAY-INVALID"
    assert list(cwd.iterdir()) == []


# --- true semantic handoff (Cycle 2.1 Wave F) ----------------------------------------------

from theforge_apiforge import execute as _exec_mod  # noqa: E402
from theforge_apiforge import handoff as upstream  # noqa: E402

HANDOFF_ITEMS = [
    {
        "kind": "evidence",
        "id": "f_2d3af1",
        "origin": {
            "plan_run": "plan-1",
            "node": "n1",
            "run_id": "run-n1",
            "provider": {"id": "spark-forge-aws", "version": "0.1.0"},
        },
        "epistemic": "inferred",
        "subject": "pyspark.dataframe",
        "claim": "etl.py reads orders.csv",
        "location": {"path": "data-pipeline/jobs/etl.py", "line": 12},
    },
    {
        "kind": "finding",
        "id": "f_99aa",
        "origin": {
            "plan_run": "plan-1",
            "node": "n1",
            "run_id": "run-n1",
            "provider": {"id": "spark-forge-aws", "version": "0.1.0"},
        },
        "severity": "medium",
        "claim": "no schema validation on the output frame",
    },
    {
        "kind": "decision",
        "id": "outcome",
        "origin": {
            "plan_run": "plan-1",
            "node": "n1",
            "run_id": "run-n1",
            "provider": {"id": "spark-forge-aws", "version": "0.1.0"},
        },
        "epistemic": "observed",
        "claim": "n1 ok: 2 facts, 1 finding",
    },
]


def _handoff_payload(items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "schema": "theforge/Handoff/v1",
        "plan_run": "plan-1",
        "target_node": "n2",
        "items": HANDOFF_ITEMS if items is None else items,
    }


def test_manifest_declares_accepts_handoff_only_where_consumption_exists() -> None:
    manifest = from_dict(ForgeManifest, _describe()[0].payload)
    analyze = manifest.capability("api.analyze")
    change = manifest.capability("api.change-control")
    assert analyze is not None and analyze.accepts_handoff
    assert change is not None and not change.accepts_handoff


def test_translate_handoff_maps_items_with_their_provenance() -> None:
    document, notes = upstream.translate_handoff(_handoff_payload())
    assert notes == []
    assert document["schema"] == upstream.UPSTREAM_SCHEMA
    facts = document["facts"]
    assert [f["kind"] for f in facts] == [
        "upstream.evidence",
        "upstream.finding",
        "upstream.decision",
    ]
    first = facts[0]
    assert first["fact_id"].startswith("upstream:")
    assert first["source"]["extractor"] == upstream.UPSTREAM_EXTRACTOR
    provenance = first["attrs"]["upstream"]
    assert (
        provenance["provider"],
        provenance["run_id"],
        provenance["node"],
        provenance["item"],
        provenance["plan_run"],
    ) == ("spark-forge-aws", "run-n1", "n1", "f_2d3af1", "plan-1")
    assert provenance["epistemic"] == "inferred"  # verbatim, never upgraded
    assert provenance["claim"] == "etl.py reads orders.csv"
    assert provenance["location"] == {"path": "data-pipeline/jobs/etl.py", "line": 12}
    assert facts[1]["measures"]["severity"] == "medium"
    assert facts[2]["attrs"]["upstream"]["epistemic"] == "observed"


def test_translate_handoff_is_deterministic() -> None:
    assert (
        upstream.translate_handoff(_handoff_payload())[0]
        == upstream.translate_handoff(_handoff_payload())[0]
    )


def test_translate_handoff_skips_malformed_items_with_a_limitation() -> None:
    document, notes = upstream.translate_handoff(
        _handoff_payload([*HANDOFF_ITEMS, {"kind": "evidence"}, "junk"])
    )
    assert len(document["facts"]) == len(HANDOFF_ITEMS)
    assert any("2 handoff item(s) malformed" in note for note in notes)


def test_translate_handoff_bounds_items_and_bytes() -> None:
    many = [
        dict(item, id=f"e{i}", claim=f"claim {i}") for i in range(50) for item in HANDOFF_ITEMS[:1]
    ]
    document, notes = upstream.translate_handoff(_handoff_payload(many))
    assert len(document["facts"]) == upstream.MAX_UPSTREAM_ITEMS
    assert any("truncated to 32" in note for note in notes)
    big = [dict(HANDOFF_ITEMS[0], id=f"e{i}", claim="c" * 4000) for i in range(20)]
    document, notes = upstream.translate_handoff(_handoff_payload(big))
    encoded = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    assert len(encoded) <= upstream.MAX_UPSTREAM_BYTES
    assert any("bytes" in note for note in notes)


def _upstream_fact() -> dict[str, Any]:
    """The fact the intake persists for the first handoff item (as the specialist wrote it)."""
    document, _ = upstream.translate_handoff(_handoff_payload())
    return document["facts"][0]


def test_upstream_facts_translate_to_derived_evidence(tmp_path: Path) -> None:
    from theforge_apiforge import translate

    recording = _analyze_recording()
    facts = recording["case_files"]["facts.json"]["facts"]
    facts.append(_upstream_fact())
    stage = _shell.StagedInput(root=tmp_path, files={})
    cwd = tmp_path
    out = cwd / "case"
    out.mkdir()
    for name, document in recording["case_files"].items():
        (out / name).write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    native_case = translate.read_case(cwd, "case")
    draft = translate.translate_case(native_case, stage, state="supported")
    assert not isinstance(draft, _shell.Reply)
    derived = [e for e in draft.evidence if e.get("derived_from")]
    assert len(derived) == 1
    entry = derived[0]
    assert entry["id"].startswith("upstream:")
    assert entry["epistemic"] == "inferred"  # the handoff item's status, verbatim
    assert entry["subject"] == "pyspark.dataframe"
    assert entry["claim"] == "etl.py reads orders.csv"
    assert entry["derived_from"] == {
        "provider": "spark-forge-aws",
        "run_id": "run-n1",
        "node": "n1",
        "plan_run": "plan-1",
        "item": "f_2d3af1",
    }
    assert entry["location"] == {"path": "data-pipeline/jobs/etl.py", "line": 12}
    native = [e for e in draft.evidence if not e.get("derived_from")]
    assert native and all(e["epistemic"] == "observed" for e in native)


def test_upstream_fact_without_provenance_is_skipped_not_invented(tmp_path: Path) -> None:
    recording = _analyze_recording()
    facts = recording["case_files"]["facts.json"]["facts"]
    broken = _upstream_fact()
    broken["attrs"] = {}  # no provenance: must not become an evidence orphan
    facts.append(broken)
    cwd = tmp_path
    out = cwd / "case"
    out.mkdir()
    for name, document in recording["case_files"].items():
        (out / name).write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    from theforge_apiforge import translate

    draft = translate.translate_case(
        translate.read_case(cwd, "case"), _shell.StagedInput(root=cwd, files={})
    )
    assert not isinstance(draft, _shell.Reply)
    assert not [e for e in draft.evidence if str(e["id"]).startswith("upstream:")]
    assert any("no provenance map" in note for note in draft.limitations)


def test_live_execute_feeds_the_handoff_to_the_native_verb(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recording = _analyze_recording()
    recording["case_files"]["facts.json"]["facts"].append(_upstream_fact())
    fake = _FakeNative(recording)
    monkeypatch.setattr(_exec_mod, "_upstream_supported", lambda: True)
    payload = {**_execute_payload("api.analyze"), "handoff": _handoff_payload()}
    cwd = tmp_path / "work"
    response, data = _live_respond(cwd, payload, fake)
    assert response.status == "ok", response.error
    (call,) = fake.calls
    argv = call["argv"]
    assert argv[-2:] == ["--upstream", upstream.UPSTREAM_FILE]
    # The intake file was written under the native cwd and is gone after cleanup.
    assert not (cwd / upstream.UPSTREAM_FILE).exists()
    result = _result(response, data, cwd)
    derived = [e for e in result.evidence if e.derived_from is not None]
    assert len(derived) == 1 and derived[0].derived_from is not None
    assert derived[0].derived_from.provider == "spark-forge-aws"
    assert derived[0].derived_from.run_id == "run-n1"
    assert derived[0].derived_from.node == "n1"
    assert derived[0].derived_from.item == "f_2d3af1"


def test_live_execute_without_intake_records_the_limitation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeNative(_analyze_recording())
    monkeypatch.setattr(_exec_mod, "_upstream_supported", lambda: False)
    payload = {**_execute_payload("api.analyze"), "handoff": _handoff_payload()}
    response, data = _live_respond(tmp_path / "work", payload, fake)
    assert response.status == "ok", response.error
    (call,) = fake.calls
    assert "--upstream" not in call["argv"]
    result = _result(response, data, tmp_path / "work")
    assert any("handoff delivered but not consumed" in note for note in result.limitations)


def test_live_execute_without_handoff_never_writes_the_intake(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeNative(_analyze_recording())
    monkeypatch.setattr(_exec_mod, "_upstream_supported", lambda: True)
    response, _ = _live_respond(tmp_path / "work", _execute_payload("api.analyze"), fake)
    assert response.status == "ok", response.error
    (call,) = fake.calls
    assert "--upstream" not in call["argv"]


def test_replay_execute_replays_the_current_handoff(tmp_path: Path) -> None:
    """In replay the upstream facts come from THIS request's handoff (the translation is
    adapter-deterministic): the recorded provenance never leaks into a new run."""
    cwd = tmp_path / "work"
    payload = {**_execute_payload("api.analyze"), "handoff": _handoff_payload()}
    response, data = _execute(cwd, payload, SCENARIOS / "cross")
    assert response.status == "ok", response.error
    result = _result(response, data, cwd)
    derived = [e for e in result.evidence if e.derived_from is not None]
    assert {e.derived_from.item for e in derived if e.derived_from is not None} == {
        item["id"] for item in HANDOFF_ITEMS
    }
    assert all(e.derived_from is not None and e.derived_from.run_id == "run-n1" for e in derived)
    facts = json.loads((cwd / "case" / "facts.json").read_text(encoding="utf-8"))
    upstream_facts = [
        f for f in facts["facts"] if f["source"].get("extractor") == "theforge/handoff"
    ]
    assert [f["attrs"]["upstream"]["run_id"] for f in upstream_facts] == ["run-n1"] * len(
        HANDOFF_ITEMS
    )


def test_replay_execute_without_handoff_drops_recorded_upstream(tmp_path: Path) -> None:
    """The cross recording embeds upstream facts; replayed without a handoff they are
    dropped — in that run the verb saw no ``--upstream`` intake."""
    cwd = tmp_path / "work"
    response, data = _execute(cwd, _execute_payload("api.analyze"), SCENARIOS / "cross")
    assert response.status == "ok", response.error
    result = _result(response, data, cwd)
    assert [e for e in result.evidence if e.derived_from is not None] == []
    facts = json.loads((cwd / "case" / "facts.json").read_text(encoding="utf-8"))
    assert not [f for f in facts["facts"] if f["source"].get("extractor") == "theforge/handoff"]


def test_execute_carries_the_native_case_receipt(tmp_path: Path) -> None:
    """Phase 37 nested receipt: the result points at the provider's own run record —
    ``case_id`` verbatim plus the sha256 of the manifest file it wrote (already an
    artifact of the run). Never the contents."""
    cwd = tmp_path / "work"
    response, data = _execute(cwd, _execute_payload("api.analyze"), SCENARIOS / "cross")
    assert response.status == "ok", response.error
    result = _result(response, data, cwd)
    assert result.provider_receipt is not None
    assert result.provider_receipt.ref == "case:cff8bff8a5345118"
    hashed = {a.path: a.sha256 for a in result.artifacts}
    assert result.provider_receipt.sha256 == hashed["case/case.json"]


# --- execute recorder (Cycle 2.1 Wave G) --------------------------------------

from theforge_apiforge import record_execute  # noqa: E402
from theforge_apiforge._shell import NativeOutcome  # noqa: E402

ANALYZE_ARGS = {"contract": "orders-api/openapi.yaml", "project": "orders-api"}


def _fake_native(case_files: dict[str, Any], *, rc: int = 0, stderr: bytes = b""):
    """A ``run`` stand-in: writes ``case_files`` under the verb's output dir, or fails."""

    def run(argv: list[str], *, cwd: Path, env: dict[str, str], timeout: float) -> NativeOutcome:
        if rc != 0:
            return NativeOutcome(returncode=rc, stdout=b"", stderr=stderr)
        out = cwd / "case"
        out.mkdir(parents=True, exist_ok=True)
        for name, document in case_files.items():
            path = out / name
            path.parent.mkdir(parents=True, exist_ok=True)
            if name.endswith(".json"):
                path.write_text(
                    json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
                )
            else:
                path.write_text(str(document), encoding="utf-8")
        return NativeOutcome(returncode=0, stdout=b'{"status": "ok"}', stderr=b"")

    return run


def _recorded(case_files: dict[str, Any], **kwargs: Any) -> tuple[str, dict[str, Any]]:
    return record_execute.record_action(
        workspace=WORKSPACE,
        capability="api.analyze",
        action="analyze",
        arguments=ANALYZE_ARGS,
        run=_fake_native(case_files),
        **kwargs,
    )


def test_record_execute_produces_a_replayable_recording(tmp_path: Path) -> None:
    """live -> record -> replay -> semantic equivalence (the recording's case replays
    into the same evidence/findings as the live output it captured)."""
    case_files = _analyze_recording()["case_files"]
    name, data = _recorded(case_files)
    assert name == "api.analyze.analyze.json"
    assert data["exit_code"] == 0 and data["provenance"] == "recorded"
    assert data["case_dir"] == "case" and data["native_cwd"] == "."
    assert data["argv"] == [
        "analyze",
        "--contract",
        "stage/orders-api/openapi.yaml",
        "--project",
        "stage",
        "--out-dir",
        "case",
        "--detail-level",
        "summary",
    ]
    assert data["case_files"].keys() == case_files.keys()
    scenario = tmp_path / "scenario"
    scenario.mkdir()
    (scenario / "environment.json").write_bytes((DEFAULT / "environment.json").read_bytes())
    (scenario / "health.json").write_bytes((DEFAULT / "health.json").read_bytes())
    (scenario / name).write_text(json.dumps(data), encoding="utf-8")
    cwd_a, cwd_b = tmp_path / "a", tmp_path / "b"
    live_like, data_a = _execute(cwd_a, _execute_payload("api.analyze"), scenario)
    replayed, data_b = _execute(cwd_b, _execute_payload("api.analyze"), DEFAULT)
    assert live_like.status == replayed.status == "ok"
    result_a = from_dict(ExecutionResult, data_a["payload"], "$.payload")
    result_b = from_dict(ExecutionResult, data_b["payload"], "$.payload")
    assert result_a.evidence == result_b.evidence
    assert result_a.findings == result_b.findings
    assert {a.path for a in result_a.artifacts} == {a.path for a in result_b.artifacts}


def test_record_execute_never_modifies_the_workspace(tmp_path: Path) -> None:
    before = {
        p.relative_to(WORKSPACE).as_posix(): hashlib.sha256(p.read_bytes()).digest()
        for p in sorted(WORKSPACE.rglob("*"))
        if p.is_file()
    }
    _recorded(_analyze_recording()["case_files"])
    after = {
        p.relative_to(WORKSPACE).as_posix(): hashlib.sha256(p.read_bytes()).digest()
        for p in sorted(WORKSPACE.rglob("*"))
        if p.is_file()
    }
    assert after == before


def test_record_execute_refuses_a_recording_with_machine_paths(tmp_path: Path) -> None:
    with pytest.raises(record_execute.RecordingError, match="machine path"):
        _recorded({"facts.json": {"facts": []}, "note.txt": f"workspace at {WORKSPACE}"})


def test_record_execute_records_native_failures_as_error_files(tmp_path: Path) -> None:
    name, data = record_execute.record_action(
        workspace=WORKSPACE,
        capability="api.analyze",
        action="analyze",
        arguments=ANALYZE_ARGS,
        run=_fake_native({}, rc=34, stderr=b"AF-X: broken"),
    )
    assert name == "api.analyze.analyze.error.json"
    assert data == {"exit_code": 34, "stderr": "AF-X: broken"}


def test_record_execute_feeds_the_handoff_through_the_intake(tmp_path: Path) -> None:
    handoff_file = tmp_path / "handoff.json"
    handoff_file.write_text(json.dumps(_handoff_payload()), encoding="utf-8")
    name, data = _recorded(_analyze_recording()["case_files"], handoff=handoff_file)
    assert name == "api.analyze.analyze.json"
    assert data["argv"][-2:] == ["--upstream", "upstream-facts.json"]


def test_record_execute_rejects_an_intake_less_capability(tmp_path: Path) -> None:
    handoff_file = tmp_path / "handoff.json"
    handoff_file.write_text(json.dumps(_handoff_payload()), encoding="utf-8")
    with pytest.raises(record_execute.RecordingError, match="no upstream intake"):
        record_execute.record_action(
            workspace=WORKSPACE,
            capability="api.change-control",
            action="run",
            arguments={"bundle": "change-bundle.json"},
            handoff=handoff_file,
            run=_fake_native({}),
        )


@pytest.mark.parametrize(
    "kwargs, match",
    [
        ({"arguments": {"bogus": "x"}}, "unknown input"),
        ({"arguments": {"contract": "orders-api/openapi.yaml"}}, "missing input"),
        ({"arguments": {**ANALYZE_ARGS, "project": "../outside"}}, "workspace-relative"),
        ({"capability": "api.bogus"}, "not in the verb table"),
    ],
)
def test_record_execute_validates_its_inputs(
    tmp_path: Path, kwargs: dict[str, Any], match: str
) -> None:
    base = {
        "workspace": WORKSPACE,
        "capability": "api.analyze",
        "action": "analyze",
        "arguments": ANALYZE_ARGS,
        "run": _fake_native({}),
    }
    with pytest.raises(record_execute.RecordingError, match=match):
        record_execute.record_action(**{**base, **kwargs})
