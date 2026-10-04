"""Spark Forge adapter (real-provider-integration 4.1, 4.2): manifest derived from the recorded
native tool surface, the capability table, describe and health with and without ``--replay``,
the replay layout and the snapshot re-recording.

The dev interpreter does not have the Spark Forge installed: describe there must be refused
with an actionable reason, and every manifest check runs in replay (``environment.json`` stands
in for the import check, the packaged ``native_catalog.json`` is the tool surface).
"""

import importlib.metadata
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest
from theforge_sparkforge import SUPPORTED_SPECIALIST, backend, catalog, record
from theforge_sparkforge._shell import StagedInput, select_inputs

from theforge.contracts import (
    PROTOCOL_V1,
    ForgeManifest,
    HealthReport,
    Response,
    from_dict,
)
from theforge.contracts.integrity import validate_manifest_limits
from theforge.contracts.taxonomy import validate_taxonomy
from theforge.contracts.types import is_catch_all_glob

REPO = Path(__file__).parents[1]
PACKAGE = REPO / "adapters" / "sparkforge" / "src" / "theforge_sparkforge"
SNAPSHOT = PACKAGE / "native_catalog.json"
NATIVE = REPO / "tests" / "fixtures" / "native" / "sparkforge"
DEFAULT = NATIVE / "default"
SCENARIOS = NATIVE / "scenarios"

# The exposed catalog recorded from sparkforge-aws 0.5.0 (capability -> actions, in order).
EXPECTED_EXPOSED = {
    "pyspark.static-analysis": ["pyspark", "graph"],
    "spark.runtime-analysis": ["event-log", "sql-metrics", "plan"],
    "streaming.analysis": ["schema-registry", "streaming-integrations"],
    "glue.analysis": ["glue-resource-link"],
    "emr.analysis": ["emr-cluster", "emr-serverless", "emr-eks"],
    "athena.analysis": ["sql", "athena-workgroup"],
    "iceberg.analysis": ["iceberg"],
    "parquet.footer-analysis": ["parquet-footer"],
    "terraform.analysis": ["terraform"],
    "orchestration.analysis": ["step-functions", "airflow-dag"],
    "data-quality.analysis": ["data-quality"],
    "lakeformation.access-analysis": ["lakeformation-grants", "iam-access"],
    "cloudwatch.analysis": ["cloudwatch", "cloudwatch-logs"],
    "platform.graph-analysis": ["dbt-artifacts", "consumers"],
    "finops.performance-analysis": ["workload"],
}
# Files no action input may accept: the conformance's notes.md and generic names.
GENERIC_FILES = ["notes.md", "README.md", "docs/guide/intro.md", "x", "a.b", "notes.txt",
                 "data.json", "config.yaml", "settings.yml", "events.jsonl", "Makefile",
                 ".sparkforge/notes.md", "artifacts/readme.md"]


def _request(op: str, payload: dict[str, Any] | None = None) -> bytes:
    return json.dumps({"protocol": PROTOCOL_V1, "kind": "Request", "op": op,
                       "request_id": f"req-{op}", "payload": payload or {}}).encode()


def _call(op: str, *options: str, payload: dict[str, Any] | None = None) -> Response:
    argv = [sys.executable, "-m", "theforge_sparkforge", *options, op]
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as cwd:  # never the repo
        out = subprocess.run(argv, input=_request(op, payload), capture_output=True,
                             timeout=60, cwd=cwd)
    assert out.returncode == 0, out.stderr
    response = from_dict(Response, json.loads(out.stdout))
    assert (response.producer.id, response.producer.version) == ("spark-forge", "0.1.0")
    assert response.request_id == f"req-{op}"
    return response


def _describe_replay(directory: Path = DEFAULT) -> Response:
    return _call("describe", "--replay", str(directory))


@pytest.fixture(scope="module")
def replay_describe() -> Response:
    response = _describe_replay()
    assert response.status == "ok", response.error
    return response


@pytest.fixture(scope="module")
def manifest(replay_describe: Response) -> ForgeManifest:
    return from_dict(ForgeManifest, replay_describe.payload, "$.payload")


@pytest.fixture(scope="module")
def snapshot() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    return data


# --- describe in replay -------------------------------------------------------------------

def test_replay_describe_manifest_passes_taxonomy_and_limits(manifest: ForgeManifest) -> None:
    assert manifest.id == "spark-forge"
    assert manifest.version == "0.1.0"
    assert manifest.protocols == ["forge/v1"]
    assert set(manifest.ops) == {"describe", "health", "execute"}
    assert manifest.domains == ["data-engineering"]
    assert manifest.execution.local and manifest.execution.offline
    assert not manifest.execution.requires_network
    assert manifest.capabilities
    assert validate_taxonomy(manifest) == ()
    assert validate_manifest_limits(manifest) == ()
    for cap in manifest.capabilities:
        assert cap.state == "supported"
        assert cap.operation_class == "read_only"
        assert cap.default_action == cap.actions[0]
        assert cap.description


def test_replay_describe_declares_the_recorded_catalog(manifest: ForgeManifest) -> None:
    exposed = {cap.id: cap.actions for cap in manifest.capabilities}
    assert exposed == EXPECTED_EXPOSED
    assert list(exposed) == list(EXPECTED_EXPOSED)  # catalog order


def test_replay_describe_declares_hash_revalidation(replay_describe: Response) -> None:
    # Raw payload: the parsed ForgeManifest lacks the optional field until
    # context-intelligence-v2 lands; cores without it ignore it (forward-compat of forge/v1).
    assert replay_describe.payload["context_revalidation"] == "hash"


def test_no_aws_or_write_tool_is_declared(manifest: ForgeManifest,
                                          snapshot: dict[str, Any]) -> None:
    for cap in manifest.capabilities:
        for action in cap.actions:
            tool = catalog.tool_for(cap.id, action)
            assert tool is not None, (cap.id, action)
            annotations = snapshot["tools"][tool]["annotations"]
            assert annotations["readOnlyHint"] is True, tool
            assert annotations["openWorldHint"] is False, tool
            assert "collect" not in tool and tool != "sparkforge_doctor"


def test_every_declared_action_fills_the_required_native_arguments(
        manifest: ForgeManifest, snapshot: dict[str, Any]) -> None:
    for cap in manifest.capabilities:
        spec = catalog.spec(cap.id)
        assert spec is not None
        for action in cap.actions:
            tool = catalog.tool_for(cap.id, action)
            assert tool is not None
            binding = spec.bindings[tool]
            assert set(snapshot["tools"][tool]["required"]) <= {binding.arg}


def test_exclusions_are_listed_in_limitations(manifest: ForgeManifest,
                                              snapshot: dict[str, Any]) -> None:
    declared = {catalog.tool_for(cap.id, action)
                for cap in manifest.capabilities for action in cap.actions}
    text = "\n".join(manifest.limitations)
    for tool in sorted(set(snapshot["tools"]) - declared):
        assert tool in text, f"{tool} is neither declared nor listed in limitations"
    collectors = [line for line in manifest.limitations if "sparkforge_collect_glue_job," in line]
    assert len(collectors) == 1 and "AWS" in collectors[0]
    writers = [line for line in manifest.limitations if "sparkforge_case_open" in line]
    assert len(writers) == 1 and "write" in writers[0]
    assert any("sparkforge_doctor" in line and "credential" in line
               for line in manifest.limitations)
    assert any("'migration.assessment'" in line and "not exposed" in line
               for line in manifest.limitations)
    assert any("sparkforge_analyze_call_graph" in line and "facts" in line
               for line in manifest.limitations)
    assert any("0.5.0" in line and "native_catalog.json" in line
               for line in manifest.limitations)


def test_every_recorded_tool_has_a_classification(snapshot: dict[str, Any]) -> None:
    # A tool the catalog does not know falls back to an explicit "unmapped" limitation; with
    # the recorded surface that never happens (a new native tool surfaces here first).
    exposure = catalog.derive(snapshot)
    assert not [line for line in exposure.limitations if catalog.UNMAPPED_REASON in line]


# --- action inputs ------------------------------------------------------------------------

def _all_bindings() -> list[tuple[str, str, catalog.ArgBinding]]:
    return [(spec.id, tool, binding) for spec in catalog.CAPABILITIES
            for tool, binding in spec.bindings.items()]


def test_bindings_exist_and_name_only_catalogued_tools() -> None:
    assert _all_bindings()
    for spec in catalog.CAPABILITIES:
        tools = {tool for _, tool in spec.actions}
        assert set(spec.bindings) <= tools, spec.id


@pytest.mark.parametrize(("capability", "tool", "binding"), _all_bindings(),
                         ids=[f"{cap}:{tool}" for cap, tool, _ in _all_bindings()])
def test_no_action_input_accepts_markdown_or_any_file(capability: str, tool: str,
                                                      binding: catalog.ArgBinding) -> None:
    assert binding.globs
    for glob in binding.globs:
        assert not is_catch_all_glob(glob), glob
        assert "md" not in glob.lower().rsplit(".", 1)[-1], glob
    stage = StagedInput(root=Path("stage"), files={path: "0" * 64 for path in GENERIC_FILES})
    assert select_inputs(stage, {binding.arg: binding.globs}) == {binding.arg: []}


def test_capability_signals_have_no_catch_all_glob() -> None:
    for spec in catalog.CAPABILITIES:
        for glob in spec.signals.file_globs:
            assert not is_catch_all_glob(glob), (spec.id, glob)
            assert not glob.lower().endswith(".md"), (spec.id, glob)


def test_only_pyspark_static_analysis_claims_python_sources() -> None:
    # The cross-forge proof task must route to exactly one best Spark capability.
    for spec in catalog.CAPABILITIES:
        if spec.id == "pyspark.static-analysis":
            assert spec.signals.file_globs == ("*.py",)
            assert spec.signals.dependencies == ("pyspark",)
            continue
        assert "*.py" not in spec.signals.file_globs, spec.id
        assert "pyspark" not in spec.signals.dependencies, spec.id
        assert not {"spark", "pyspark", "pipeline", "api", "dados"} & set(spec.signals.keywords)


# --- eligibility (synthetic snapshots) ----------------------------------------------------

def _patched(snapshot: dict[str, Any], tool: str, **annotations: Any) -> dict[str, Any]:
    data = json.loads(json.dumps(snapshot))
    data["tools"][tool]["annotations"].update(annotations)
    return data


def _actions(exposure: catalog.Exposure) -> dict[str, list[str]]:
    return {cap["id"]: cap["actions"] for cap in exposure.capabilities}


def test_open_world_or_writing_tools_are_never_declared(snapshot: dict[str, Any]) -> None:
    open_world = catalog.derive(_patched(snapshot, "sparkforge_analyze_graph",
                                         openWorldHint=True))
    assert _actions(open_world)["pyspark.static-analysis"] == ["pyspark"]
    assert any("sparkforge_analyze_graph" in line and "openWorldHint" in line
               for line in open_world.limitations)
    writer = catalog.derive(_patched(snapshot, "sparkforge_analyze_graph", readOnlyHint=False))
    assert _actions(writer)["pyspark.static-analysis"] == ["pyspark"]
    assert any("sparkforge_analyze_graph" in line and "readOnlyHint" in line
               for line in writer.limitations)
    unknown = catalog.derive(_patched(snapshot, "sparkforge_analyze_graph",
                                      openWorldHint=None))
    assert _actions(unknown)["pyspark.static-analysis"] == ["pyspark"]


def test_missing_tool_or_unfillable_argument_is_not_declared(snapshot: dict[str, Any]) -> None:
    data = json.loads(json.dumps(snapshot))
    del data["tools"]["sparkforge_analyze_iceberg"]
    data["tools"]["sparkforge_analyze_parquet_footer"]["required"] = ["path", "table"]
    exposure = catalog.derive(data)
    actions = _actions(exposure)
    assert "iceberg.analysis" not in actions
    assert "parquet.footer-analysis" not in actions
    text = "\n".join(exposure.limitations)
    assert "sparkforge_analyze_iceberg" in text and "not in the recorded" in text
    assert "'table'" in text
    assert "capability 'iceberg.analysis' not exposed" in text


# --- describe without the specialist ------------------------------------------------------

def test_describe_without_sparkforge_is_refused_with_actionable_reason() -> None:
    if importlib.util.find_spec("sparkforge") is not None:
        pytest.skip("the Spark Forge is importable in this interpreter")
    response = _call("describe")
    assert response.status == "refused"
    assert response.error is not None
    assert response.error.code == "SPARKFORGE-ADAPTER-UNAVAILABLE"
    assert "sparkforge is not importable" in response.error.detail
    assert f"Python {sys.version_info.major}.{sys.version_info.minor}" in response.error.detail
    assert "sparkforge-aws >=0.5,<0.6" in response.error.detail
    assert response.error.unlock


def test_execute_without_sparkforge_surfaces_the_describe_refusal() -> None:
    if importlib.util.find_spec("sparkforge") is not None:
        pytest.skip("the Spark Forge is importable in this interpreter")
    response = _call("execute", payload={"task": {"intent": "x"},
                                         "capability": "pyspark.static-analysis",
                                         "action": "pyspark", "context": {"files": []}})
    assert response.status == "refused"
    assert response.error is not None and response.error.code == "SPARKFORGE-ADAPTER-UNAVAILABLE"


def test_replay_environment_replaces_the_import_check() -> None:
    response = _describe_replay(SCENARIOS / "specialist-missing")
    assert response.status == "refused"
    assert response.error is not None
    assert response.error.code == "SPARKFORGE-ADAPTER-UNAVAILABLE"
    assert "recorded" in response.error.detail and "3.11" in response.error.detail


def test_replay_without_environment_is_a_structured_error(tmp_path: Path) -> None:
    response = _describe_replay(tmp_path)
    assert response.status == "error"
    assert response.error is not None
    assert response.error.code == "ADAPTER-REPLAY-MISSING"
    assert "environment.json" in response.error.detail


@pytest.mark.parametrize("content", ["not json", "[]", '{"python": 3}',
                                     '{"python": "3.11.15"}'])
def test_replay_with_malformed_environment_is_a_structured_error(tmp_path: Path,
                                                                 content: str) -> None:
    (tmp_path / "environment.json").write_text(content, encoding="utf-8")
    response = _describe_replay(tmp_path)
    assert response.status == "error"
    assert response.error is not None and response.error.code == "ADAPTER-REPLAY-INVALID"


# --- replay layout ------------------------------------------------------------------------

def test_default_scenario_records_a_supported_environment() -> None:
    environment = json.loads((DEFAULT / "environment.json").read_text(encoding="utf-8"))
    assert set(environment) == {"python", "specialist_version"}
    assert environment["python"].startswith("3.11.")
    assert environment["specialist_version"] == "0.5.0"
    assert SUPPORTED_SPECIALIST == ">=0.5.0,<0.6.0"
    loaded = backend.load_environment(DEFAULT)
    assert isinstance(loaded, backend.Environment)
    assert loaded.specialist_version == "0.5.0"


def test_every_scenario_is_a_complete_directory() -> None:
    assert SCENARIOS.is_dir()
    for scenario in sorted(SCENARIOS.iterdir()):
        assert scenario.is_dir(), scenario
        assert (scenario / backend.ENVIRONMENT_FILE).is_file(), scenario
        assert (scenario / backend.HEALTH_FILE).is_file(), scenario


def test_replay_recording_prefers_the_error_recording(tmp_path: Path) -> None:
    cap, action = "pyspark.static-analysis", "pyspark"
    assert backend.recording(tmp_path, cap, action) is None
    output = tmp_path / f"{cap}.{action}.json"
    output.write_text("{}", encoding="utf-8")
    found = backend.recording(tmp_path, cap, action)
    assert found == backend.Recording(kind="output", path=output)
    error = tmp_path / f"{cap}.{action}.error.json"
    error.write_text("{}", encoding="utf-8")
    assert backend.recording(tmp_path, cap, action) == backend.Recording(kind="error",
                                                                         path=error)
    assert backend.expected_recording(cap, action) == f"{cap}.{action}.json"


# --- snapshot -----------------------------------------------------------------------------

def test_recorded_snapshot_has_origin_version_and_tool_surface(snapshot: dict[str, Any]) -> None:
    assert set(snapshot) == {"specialist_version", "recorded_at", "tools"}
    assert snapshot["specialist_version"] == "0.5.0"
    assert len(snapshot["recorded_at"]) == 10  # YYYY-MM-DD (UTC)
    assert len(snapshot["tools"]) == 136
    for name, entry in snapshot["tools"].items():
        assert name.startswith("sparkforge_")
        assert set(entry) == {"annotations", "required"}
        assert isinstance(entry["annotations"]["readOnlyHint"], bool)
        assert isinstance(entry["annotations"]["openWorldHint"], bool)
        assert entry["required"] == sorted(entry["required"])


def test_recorded_snapshot_is_in_canonical_form() -> None:
    text = SNAPSHOT.read_bytes().decode("utf-8")
    assert "\r" not in text
    assert record.render(json.loads(text)) == text


def _tools(order: list[str]) -> dict[str, Any]:
    base = {
        "sparkforge_b": {"description": "b", "annotations": {"title": "B",
                                                             "readOnlyHint": True,
                                                             "openWorldHint": False},
                         "inputSchema": {"required": ["path", "kind"]}},
        "sparkforge_a": {"annotations": {"openWorldHint": True, "readOnlyHint": False},
                         "inputSchema": {"type": "object"}},
    }
    return {name: base[name] for name in order}


def test_snapshot_rerecording_is_deterministic() -> None:
    first = record.build_snapshot(_tools(["sparkforge_b", "sparkforge_a"]), "0.5.0",
                                  today="2026-10-03")
    second = record.build_snapshot(_tools(["sparkforge_a", "sparkforge_b"]), "0.5.0",
                                   today="2026-10-04", previous=first)
    assert record.render(first) == record.render(second)  # same surface keeps recorded_at
    assert first["tools"]["sparkforge_b"] == {
        "annotations": {"openWorldHint": False, "readOnlyHint": True, "title": "B"},
        "required": ["kind", "path"]}
    assert first["tools"]["sparkforge_a"]["required"] == []
    changed = record.build_snapshot(_tools(["sparkforge_a"]), "0.5.1", today="2026-10-05",
                                    previous=first)
    assert changed["recorded_at"] == "2026-10-05"
    assert changed["specialist_version"] == "0.5.1"
    rendered = record.render(first)
    assert rendered.endswith("\n") and list(json.loads(rendered)) == sorted(first)


def test_record_without_sparkforge_fails_with_reason_and_writes_nothing(tmp_path: Path) -> None:
    if importlib.util.find_spec("sparkforge") is not None:
        pytest.skip("the Spark Forge is importable in this interpreter")
    target = tmp_path / "native_catalog.json"
    out = subprocess.run([sys.executable, "-m", "theforge_sparkforge.record",
                          "--output", str(target)], capture_output=True, timeout=60,
                         cwd=tmp_path)
    assert out.returncode != 0
    assert b"sparkforge is not importable" in out.stderr
    assert not target.exists()


@pytest.mark.parametrize("content", ["not json", "[]", '{"specialist_version": "0.5.0"}',
                                     '{"specialist_version": "0.5.0", "recorded_at": "x", '
                                     '"tools": {"t": {"annotations": {}, "required": [1]}}}'])
def test_corrupt_snapshot_is_a_structured_adapter_error(tmp_path: Path, content: str,
                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    from theforge_sparkforge import __main__ as entry
    from theforge_sparkforge._shell import AdapterOptions, Request

    corrupt = tmp_path / "native_catalog.json"
    corrupt.write_text(content, encoding="utf-8")
    assert isinstance(catalog.load_snapshot(corrupt), str)
    original = catalog.load_snapshot
    monkeypatch.setattr(catalog, "load_snapshot", lambda: original(corrupt))
    request = Request(op="describe", request_id="r", protocol=PROTOCOL_V1, payload={})
    reply = entry.HANDLERS["describe"](AdapterOptions(replay=DEFAULT))(request, tmp_path)
    assert reply.status == "error"
    assert reply.error is not None
    assert reply.error["code"] == "SPARKFORGE-ADAPTER-SNAPSHOT-INVALID"
    assert "native_catalog.json" in reply.error["detail"]


def test_benchmark_is_excluded_for_needing_two_states(snapshot: dict[str, Any]) -> None:
    lines = [line for line in catalog.derive(snapshot).limitations
             if "(sparkforge_benchmark)" in line]
    assert len(lines) == 1
    assert "two" in lines[0] and "before" in lines[0] and "after" in lines[0]


# --- health -------------------------------------------------------------------------------

HEALTH_CHECKS = {"interpreter", "dispatcher", "specialist-version", "snapshot"}


def _health(*options: str) -> HealthReport:
    response = _call("health", *options)
    assert response.status == "ok", response.error
    return from_dict(HealthReport, response.payload, "$.payload")


def _check(report: HealthReport, name: str) -> Any:
    found = [check for check in report.checks if check.name == name]
    assert len(found) == 1, report
    return found[0]


def _failing(report: HealthReport) -> str:
    return "; ".join(check.detail for check in report.checks if not check.ok)


def _scenario(tmp_path: Path, *, python: str = "3.11.15", version: str | None = "0.5.0",
              dispatcher: bool = True) -> Path:
    (tmp_path / "environment.json").write_text(
        json.dumps({"python": python, "specialist_version": version}), encoding="utf-8")
    (tmp_path / "health.json").write_text(
        json.dumps({"dispatcher": dispatcher, "specialist_version": version}), encoding="utf-8")
    return tmp_path


def test_replay_health_of_the_default_scenario_is_ok() -> None:
    report = _health("--replay", str(DEFAULT))
    assert report.status == "ok"
    assert {check.name for check in report.checks} == HEALTH_CHECKS
    assert all(check.ok for check in report.checks), report
    version = _check(report, "specialist-version")
    assert "0.5.0" in version.detail and SUPPORTED_SPECIALIST in version.detail


def test_replay_health_without_the_specialist_is_unavailable_with_reason() -> None:
    report = _health("--replay", str(SCENARIOS / "specialist-missing"))
    assert report.status == "unavailable"
    reason = _failing(report)
    assert "not importable" in reason and "3.11" in reason
    assert _check(report, "snapshot").ok


def test_replay_health_out_of_window_is_degraded_with_version_and_window() -> None:
    report = _health("--replay", str(SCENARIOS / "version-skew"))
    assert report.status == "degraded"
    version = _check(report, "specialist-version")
    assert not version.ok
    assert f"found 0.6.1, supported {SUPPORTED_SPECIALIST}" in version.detail
    assert all(check.ok for check in report.checks if check.name != "specialist-version")


def test_assumed_version_overrides_the_found_one_in_replay() -> None:
    skewed = _health("--replay", str(DEFAULT), "--assume-specialist-version", "9.9.9")
    assert skewed.status == "degraded"
    detail = _check(skewed, "specialist-version").detail
    assert f"found 9.9.9, supported {SUPPORTED_SPECIALIST}" in detail
    assert "assumed" in detail and "0.5.0" in detail
    fixed = _health("--replay", str(SCENARIOS / "version-skew"),
                    "--assume-specialist-version", "0.5.3")
    assert fixed.status == "ok", fixed


def test_assumed_version_does_not_hide_an_unavailable_specialist() -> None:
    report = _health("--replay", str(SCENARIOS / "specialist-missing"),
                     "--assume-specialist-version", "0.5.0")
    assert report.status == "unavailable"


def test_replay_health_with_an_old_interpreter_is_unavailable(tmp_path: Path) -> None:
    report = _health("--replay", str(_scenario(tmp_path, python="3.9.18")))
    assert report.status == "unavailable"
    assert not _check(report, "interpreter").ok
    assert "3.9.18" in _failing(report) and "3.10" in _failing(report)


def test_replay_health_without_the_dispatcher_is_unavailable(tmp_path: Path) -> None:
    report = _health("--replay", str(_scenario(tmp_path, dispatcher=False)))
    assert report.status == "unavailable"
    assert not _check(report, "dispatcher").ok
    assert "sparkforge.adapters.tools" in _failing(report)


def test_replay_health_without_health_recording_is_a_structured_error(tmp_path: Path) -> None:
    _scenario(tmp_path)
    (tmp_path / "health.json").unlink()
    response = _call("health", "--replay", str(tmp_path))
    assert response.status == "error"
    assert response.error is not None and response.error.code == "ADAPTER-REPLAY-MISSING"
    assert "health.json" in response.error.detail


@pytest.mark.parametrize("content", ["not json", "[]", '{"dispatcher": true}',
                                     '{"dispatcher": "yes", "specialist_version": "0.5.0"}',
                                     '{"dispatcher": true, "specialist_version": 5}'])
def test_replay_health_with_malformed_recording_is_a_structured_error(tmp_path: Path,
                                                                      content: str) -> None:
    _scenario(tmp_path)
    (tmp_path / "health.json").write_text(content, encoding="utf-8")
    response = _call("health", "--replay", str(tmp_path))
    assert response.status == "error"
    assert response.error is not None and response.error.code == "ADAPTER-REPLAY-INVALID"


def test_health_with_an_unreadable_snapshot_is_unavailable(tmp_path: Path,
                                                           monkeypatch: pytest.MonkeyPatch
                                                           ) -> None:
    from theforge_sparkforge import __main__ as entry
    from theforge_sparkforge._shell import AdapterOptions, Request

    monkeypatch.setattr(catalog, "load_snapshot", lambda: "native_catalog.json is unreadable")
    request = Request(op="health", request_id="r", protocol=PROTOCOL_V1, payload={})
    reply = entry.HANDLERS["health"](AdapterOptions(replay=DEFAULT))(request, tmp_path)
    assert reply.status == "ok"
    report = from_dict(HealthReport, reply.payload, "$.payload")
    assert report.status == "unavailable"
    assert not _check(report, "snapshot").ok
    assert "native_catalog.json" in _failing(report)


def test_live_health_without_sparkforge_is_unavailable_with_reason() -> None:
    if importlib.util.find_spec("sparkforge") is not None:
        pytest.skip("the Spark Forge is importable in this interpreter")
    report = _health()
    assert report.status == "unavailable"
    reason = _failing(report)
    assert "sparkforge" in reason and "not importable" in reason
    assert f"Python {sys.version_info.major}.{sys.version_info.minor}" in reason
    assert _check(report, "interpreter").ok and _check(report, "snapshot").ok


def test_live_health_never_imports_the_dispatcher(monkeypatch: pytest.MonkeyPatch) -> None:
    from theforge_sparkforge import health

    seen: list[str] = []

    def fake_find_spec(name: str) -> object:
        seen.append(name)
        return object()

    monkeypatch.setattr(health.importlib.util, "find_spec", fake_find_spec)
    monkeypatch.setattr(health, "_installed_version", lambda: "0.5.0")
    observation = health.observe_live()
    assert observation.dispatcher and observation.specialist_version == "0.5.0"
    assert "sparkforge.adapters.tools" in seen
    assert "sparkforge.adapters.tools" not in sys.modules


@pytest.mark.parametrize(("version", "inside"), [
    ("0.5.0", True), ("0.5.10", True), ("0.5.9", True), ("0.6.0", False), ("0.4.99", False),
    ("1.0.0", False), ("0.5", False), ("v0.5.0", False), ("0.5.0-rc1", False), ("", False)])
def test_supported_window_is_a_semver_range(version: str, inside: bool) -> None:
    from theforge_sparkforge import health

    assert health.in_window(version, SUPPORTED_SPECIALIST) is inside


def test_recorded_health_scenarios_are_in_canonical_form() -> None:
    for path in [DEFAULT / "health.json", *sorted(SCENARIOS.glob("*/health.json"))]:
        text = path.read_bytes().decode("utf-8")
        assert "\r" not in text, path
        assert record.render(json.loads(text)) == text, path
    default = json.loads((DEFAULT / "health.json").read_text(encoding="utf-8"))
    assert default == {"dispatcher": True, "specialist_version": "0.5.0"}


def test_record_writes_the_health_probes_of_this_interpreter() -> None:
    probes = record.health_probes()
    assert set(probes) == {"dispatcher", "specialist_version"}
    if importlib.util.find_spec("sparkforge") is None:
        assert probes == {"dispatcher": False, "specialist_version": None}


def test_live_interpreter_version_ignores_a_prerelease_suffix(
        monkeypatch: pytest.MonkeyPatch) -> None:
    import platform

    from theforge_sparkforge import health

    monkeypatch.setattr(platform, "python_version", lambda: "3.13.0rc1")
    observation = health.observe_live()
    assert observation.python == ".".join(str(part) for part in sys.version_info[:3])
    payload = health.report(observation, window=SUPPORTED_SPECIALIST, assumed=None,
                            snapshot_problem=None)
    report = from_dict(HealthReport, payload, "$.payload")
    assert _check(report, "interpreter").ok


class _BrokenSparkforge:
    @property
    def __version__(self) -> str:
        raise RuntimeError("broken __init__")


@pytest.mark.parametrize(("metadata", "expected"), [("0.5.2", "0.5.2"), (None, None)])
def test_broken_sparkforge_version_falls_back_to_metadata(
        monkeypatch: pytest.MonkeyPatch, metadata: str | None, expected: str | None) -> None:
    from theforge_sparkforge import health

    def fake_metadata(name: str) -> str:
        assert name == "sparkforge-aws"
        if metadata is None:
            raise importlib.metadata.PackageNotFoundError(name)
        return metadata

    monkeypatch.setitem(sys.modules, "sparkforge", _BrokenSparkforge())
    monkeypatch.setattr(health, "metadata_version", fake_metadata)
    assert health._installed_version() == expected
    observation = health.Observation(interpreter="x", python="3.11.15", dispatcher=True,
                                     specialist_version=health._installed_version())
    report = from_dict(HealthReport, health.report(
        observation, window=SUPPORTED_SPECIALIST, assumed=None, snapshot_problem=None))
    version = _check(report, "specialist-version")
    assert version.ok is (expected is not None)
    if expected is None:
        assert report.status == "degraded" and "no sparkforge version" in version.detail
