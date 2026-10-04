"""API Forge adapter (real-provider-integration 5.1): manifest from the recorded public matrix.

The adapter derives its ``describe`` from ``native_matrix.json`` (a snapshot of the API Forge
public capability matrix): only ``supported``/``heuristic``, ``read_only`` records mapped to
an offline verb are exposed, with the native id and state; every other record is a
limitation with its reason. Without ``--replay`` the describe refuses when the interpreter is
not Python 3.12 or ``apiforge`` is not importable; with ``--replay <dir>`` those checks read
the scenario's ``environment.json`` instead. The core's own contract code validates what the
adapter answers (``from_dict``, ``validate_taxonomy``, ``validate_manifest_limits``).
"""

import importlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest
from theforge_apiforge import _shell, backend, catalog, record

from theforge.contracts import PROTOCOL_V1, ForgeManifest, Response, from_dict
from theforge.contracts.integrity import validate_manifest_limits
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


def _call(op: str, options: tuple[str, ...] = (), payload: dict[str, Any] | None = None
          ) -> tuple[Response, dict[str, Any]]:
    request = json.dumps({"protocol": PROTOCOL_V1, "kind": "Request", "op": op,
                          "request_id": f"req-{op}", "payload": payload or {}}).encode()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as cwd:  # never the repo
        out = subprocess.run([sys.executable, "-m", "theforge_apiforge", *options, op],
                             input=request, capture_output=True, timeout=60, cwd=cwd)
    assert out.returncode == 0, out.stderr
    data = json.loads(out.stdout)
    response = from_dict(Response, data)
    assert response.op == op and response.request_id == f"req-{op}"
    assert (response.producer.id, response.producer.version) == ("api-forge", "0.1.0")
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
    assert manifest.id == "api-forge" and manifest.version == "0.1.0"
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
    reasons = {n.split(" not exposed: ", 1)[0]: n.split(" not exposed: ", 1)[1]
               for n in manifest.limitations if " not exposed: " in n}
    assert "--phase" in reasons["capability 'api.next-step' (supported)"]
    assert "network" in reasons["capability 'integration.health' (supported)"]
    assert "unresolved" in reasons["capability 'git.plan' (unresolved)"]
    assert "local_reversible" in reasons["capability 'git.plan' (unresolved)"]
    assert "external_mutation" in reasons["capability 'external.apply' (unsupported)"]
    assert "tests/fixtures" in reasons["capability 'database.verify-runtime' (supported)"]
    assert "offline verb" in reasons["capability 'cloud.inspect' (heuristic)"]


def test_replay_describe_flags_a_hand_built_snapshot() -> None:
    snapshot = _snapshot()
    assert snapshot["provenance"] == "hand-built"
    response, _ = _describe()
    manifest = from_dict(ForgeManifest, response.payload)
    assert any("hand-built" in n and "0.1.0" in n for n in manifest.limitations)


def test_describe_is_deterministic() -> None:
    first = _describe()[1]["payload"]
    second = _describe()[1]["payload"]
    assert first == second


@pytest.mark.parametrize(("scenario", "expected"), [
    ("python-3.11", "Python 3.12"),
    ("apiforge-missing", "apiforge is not importable"),
])
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
    payload = {"task": {"intent": "x"}, "capability": "api.analyze", "action": "analyze",
               "context": {"files": []}}
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

def _record(capability_id: str, state: str = "supported", risk: str = "read_only"
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
    snapshot = {**_snapshot(), "capabilities": [_record("api.analyze", "heuristic"),
                                                _record("api.change-control")]}
    payload = catalog.manifest_payload(snapshot, provider_id="api-forge", version="0.1.0")
    manifest = from_dict(ForgeManifest, payload)
    assert [(c.id, c.state) for c in manifest.capabilities] == [
        ("api.analyze", "heuristic"), ("api.change-control", "supported")]


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
    snapshot = {**_snapshot(),
                "capabilities": [_record(cid) for cid in sorted(catalog.VERB_MAP)]}
    manifest = from_dict(ForgeManifest, catalog.manifest_payload(
        snapshot, provider_id="api-forge", version="0.1.0"))
    assert [c.id for c in manifest.capabilities] == sorted(catalog.VERB_MAP)
    assert validate_taxonomy(manifest) == ()
    assert validate_manifest_limits(manifest) == ()


NOT_INPUTS = ["README.md", "docs/guide.md", "app/notes.md", "CHANGELOG.MD", "x", "a.txt",
              "Makefile", ".env", "data.bin", "openapi.md", "change-bundle.md"]


def test_no_input_pattern_accepts_markdown_or_any_file() -> None:
    for capability_id, spec in catalog.VERB_MAP.items():
        assert spec.inputs, capability_id
        globs = [g for item in spec.inputs for g in item.globs]
        for glob in [*globs, *spec.signals.file_globs]:
            assert not is_catch_all_glob(glob), (capability_id, glob)
            for path in NOT_INPUTS:
                assert not _shell.select_inputs(
                    _shell.StagedInput(root=Path("."), files={path: "0" * 64}),
                    {"probe": [glob]})["probe"], (capability_id, glob, path)


def test_input_globs_select_the_example_workspace() -> None:
    files = {p.relative_to(WORKSPACE).as_posix(): "0" * 64
             for p in sorted(WORKSPACE.rglob("*")) if p.is_file()}
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
    assert environment["provenance"] == "hand-built"
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
    records = [_FakeRecord("b.two", "heuristic", "read_only", ("z", "a", "z")),
               _FakeRecord("a.one", "supported", "read_only", ())]
    first = record.build_snapshot(records, specialist_version="0.1.0",
                                  recorded_at="2026-10-03T00:00:00Z")
    second = record.build_snapshot(list(reversed(records)), specialist_version="0.1.0",
                                   recorded_at="2026-10-03T00:00:00Z")
    assert record.encode_snapshot(first) == record.encode_snapshot(second)
    assert first["provenance"] == "recorded"
    assert [r["capability_id"] for r in first["capabilities"]] == ["a.one", "b.two"]
    assert first["capabilities"][1] == {"capability_id": "b.two", "state": "heuristic",
                                        "risk": "read_only", "limitations": ["a", "z"]}
    later = record.build_snapshot(records, specialist_version="0.1.0",
                                  recorded_at="2026-10-04T00:00:00Z")
    assert {k: v for k, v in later.items() if k != "recorded_at"} == {
        k: v for k, v in first.items() if k != "recorded_at"}
    encoded = record.encode_snapshot(first)
    assert encoded.endswith(b"\n") and b"\r" not in encoded
    assert json.loads(encoded) == first


@pytest.mark.skipif(ON_312, reason="this environment runs Python 3.12")
def test_record_refuses_outside_python_312(tmp_path: Path) -> None:
    out = subprocess.run([sys.executable, "-m", "theforge_apiforge.record",
                          "--out", str(tmp_path / "m.json")],
                         capture_output=True, timeout=60, cwd=tmp_path)
    assert out.returncode != 0
    assert b"Python 3.12" in out.stderr
    assert not (tmp_path / "m.json").exists()


# --- snapshot validation --------------------------------------------------------------------

def _valid_snapshot() -> dict[str, Any]:
    return {"specialist_version": "0.1.0", "recorded_at": "2026-10-03T00:00:00Z",
            "provenance": "recorded", "capabilities": [_record("api.analyze")]}


@pytest.mark.parametrize(("content", "message"), [
    (b"{not json", "unreadable"),
    (b"\xff\xfe", "unreadable"),
    (b"[]", "expected an object"),
    (json.dumps({**_valid_snapshot(), "provenance": ""}).encode(), "provenance"),
    (json.dumps({k: v for k, v in _valid_snapshot().items() if k != "provenance"}).encode(),
     "provenance"),
    (json.dumps({**_valid_snapshot(), "capabilities": {}}).encode(), "capabilities"),
    (json.dumps({**_valid_snapshot(), "capabilities": ["x"]}).encode(), "capabilities[0]"),
    (json.dumps({**_valid_snapshot(), "capabilities": [
        {"capability_id": "api.analyze", "state": "", "risk": "read_only"}]}).encode(),
     "capabilities[0].state"),
    (json.dumps({**_valid_snapshot(), "capabilities": [
        {**_record("api.analyze"), "limitations": [1]}]}).encode(), "limitations"),
    (json.dumps({**_valid_snapshot(), "capabilities": [
        _record("api.analyze"), _record("api.analyze")]}).encode(), "duplicate capability_id"),
])
def test_load_snapshot_rejects_corrupt_files(tmp_path: Path, content: bytes,
                                             message: str) -> None:
    path = tmp_path / "native_matrix.json"
    path.write_bytes(content)
    with pytest.raises(catalog.SnapshotError, match=re.escape(message)):
        catalog.load_snapshot(path)


def test_load_snapshot_missing_file(tmp_path: Path) -> None:
    with pytest.raises(catalog.SnapshotError, match="unreadable"):
        catalog.load_snapshot(tmp_path / "absent.json")


def test_corrupt_snapshot_makes_describe_an_error(tmp_path: Path,
                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "native_matrix.json"
    path.write_bytes(json.dumps({**_valid_snapshot(), "capabilities": [
        _record("api.analyze"), _record("api.analyze")]}).encode())
    entry = importlib.import_module("theforge_apiforge.__main__")
    monkeypatch.setattr(entry, "load_snapshot", lambda: catalog.load_snapshot(path))
    handler = entry.describe(_shell.AdapterOptions(replay=DEFAULT))
    reply = handler(_shell.Request(op="describe", request_id="r", protocol=PROTOCOL_V1,
                                   payload={}), tmp_path)
    assert reply.status == "error"
    assert reply.error is not None
    assert reply.error["code"] == "APIFORGE-ADAPTER-SNAPSHOT-INVALID"
    assert "duplicate capability_id" in reply.error["detail"]
    assert reply.error["unlock"]
