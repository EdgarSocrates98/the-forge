"""Spark Forge adapter (real-provider-integration 4.1-4.4): manifest derived from the recorded
native tool surface, the capability table, describe and health with and without ``--replay``,
the replay layout, the snapshot re-recording, and the translation of real recorded execute
outputs and native errors (plus the execute recording helper), and execute with the replay
backend and the live backend (over a stand-in ``sparkforge`` package).

The dev interpreter does not have the Spark Forge installed: describe there must be refused
with an actionable reason, and every manifest check runs in replay (``environment.json`` stands
in for the import check, the packaged ``native_catalog.json`` is the tool surface).
"""

import hashlib
import importlib.metadata
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

import pytest
from theforge_sparkforge import SUPPORTED_SPECIALIST, backend, catalog, record
from theforge_sparkforge._shell import (
    Reply,
    ResultDraft,
    StagedInput,
    finalize,
    select_inputs,
    stage_context,
)

from theforge.contracts import (
    PROTOCOL_V1,
    ExecutionResult,
    ForgeManifest,
    HealthReport,
    Producer,
    Response,
    from_dict,
)
from theforge.contracts.integrity import validate_manifest_limits, validate_result
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
    assert (response.producer.id, response.producer.version) == ("spark-forge", "0.3.0")
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
    assert manifest.version == "0.3.0"
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


def test_python_sources_are_claimed_only_where_an_action_reads_them() -> None:
    # The cross-forge proof task must route to exactly one best Spark capability.
    for spec in catalog.CAPABILITIES:
        if spec.id == "pyspark.static-analysis":
            assert spec.signals.file_globs == ("*.py",)
            assert spec.signals.dependencies == ("pyspark",)
            continue
        # *.py only where an action reads Python sources (the core stages only files matching
        # file_globs); a lone file signal stays below the router minimum.
        if "*.py" in spec.signals.file_globs:
            assert any("*.py" in binding.globs for binding in spec.bindings.values()), spec.id
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


# --- execute translation over real recordings (4.3) ---------------------------------------

WORKSPACE = REPO / "tests" / "fixtures" / "workspaces" / "spark"
CAPABILITY, ACTION = "pyspark.static-analysis", "pyspark"
ANALYZE_TOOL, JUDGE_TOOL = "sparkforge_analyze_pyspark", "sparkforge_judge"
OUTPUT_RECORDING = DEFAULT / f"{CAPABILITY}.{ACTION}.json"
ERROR_SCENARIO = SCENARIOS / "native-error"
ERROR_RECORDING = ERROR_SCENARIO / f"{CAPABILITY}.{ACTION}.error.json"
PRODUCER = {"id": "spark-forge", "version": "0.3.0"}
# Machine-specific fragments a portable recording never contains: a drive path (raw or JSON-
# escaped; a URL scheme is followed by a second slash), a user directory, a temp directory.
MACHINE_PATH = re.compile(r"(?<![A-Za-z])[A-Za-z]:(?:\\|/(?!/))|/Users/|/home/|AppData|/tmp/",
                          re.IGNORECASE)


def _recorded() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(OUTPUT_RECORDING.read_text(encoding="utf-8"))
    return data


def _context(root: Path, paths: list[str]) -> dict[str, Any]:
    files = []
    for rel in paths:
        data = (root / rel).read_bytes()
        files.append({"path": rel, "sha256": hashlib.sha256(data).hexdigest(),
                      "bytes": len(data)})
    return {"context": {"root": str(root.resolve()), "files": files}}


def _staged(tmp_path: Path) -> StagedInput:
    payload = _context(WORKSPACE, ["jobs/orders_job.py", "requirements.txt"])
    return stage_context(payload, tmp_path)


def _translate(recorded: dict[str, Any], stage: StagedInput) -> Any:
    from theforge_sparkforge import translate

    return translate.translate_recording(recorded, stage)


def _validated(draft: Any, cwd: Path) -> ExecutionResult:
    assert isinstance(draft, ResultDraft), draft
    reply = finalize(draft, cwd)
    assert reply.status in ("ok", "partial"), reply.error
    result = from_dict(ExecutionResult, reply.payload, "$.payload")
    validate_result(result, expected=Producer(**PRODUCER))
    return result


def _items(recorded: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = recorded["output"]["items"]
    return items


def test_default_recording_holds_tool_output_and_chained_judge() -> None:
    recorded = _recorded()
    assert set(recorded) == {"tool", "arguments", "output", "judge"}
    assert recorded["tool"] == ANALYZE_TOOL
    assert recorded["judge"]["tool"] == JUDGE_TOOL
    assert _items(recorded) and recorded["judge"]["output"]["items"]
    assert recorded["output"]["next_cursor"] is None
    assert recorded["judge"]["output"]["next_cursor"] is None
    # File arguments are relative to the staged workspace, never machine paths.
    assert recorded["arguments"]["path"] == "jobs"


@pytest.mark.parametrize("path", [*sorted(DEFAULT.glob(f"{CAPABILITY}.*.json")),
                                  ERROR_RECORDING], ids=lambda path: path.name)
def test_execute_recordings_are_canonical_lf_and_portable(path: Path) -> None:
    text = path.read_bytes().decode("utf-8")
    assert "\r" not in text
    assert record.render(json.loads(text)) == text
    assert MACHINE_PATH.search(text) is None, (path.name, MACHINE_PATH.search(text))


def test_recorded_output_translates_to_a_result_that_passes_core_integrity(
        tmp_path: Path) -> None:
    recorded = _recorded()
    result = _validated(_translate(recorded, _staged(tmp_path)), tmp_path)
    assert result.status == "ok"
    assert [e.id for e in result.evidence] == [item["id"] for item in _items(recorded)]
    assert all(e.epistemic == "observed" for e in result.evidence)
    assert {e.subject for e in result.evidence} == {item["kind"] for item in _items(recorded)}
    assert all(len(e.claim) <= 500 for e in result.evidence)
    located = [e.location for e in result.evidence if e.location is not None]
    assert located and {loc.path for loc in located} == {"jobs/orders_job.py"}
    judged = recorded["judge"]["output"]["items"]
    assert [f.id for f in result.findings] == [f"{item['rule_id']}#1" for item in judged]
    assert [f.title for f in result.findings] == [f"{item['rule_id']}: {item['title']}"
                                                  for item in judged]
    severity = {"P0": "critical", "P1": "high", "P2": "medium", "P3": "low", "P4": "info"}
    assert [f.severity for f in result.findings] == [severity[item["severity"]]
                                                     for item in judged]
    assert [f.evidence_ids for f in result.findings] == [item["evidence"] for item in judged]


def test_every_evidence_hash_is_null_or_the_verified_sha256(tmp_path: Path) -> None:
    stage = _staged(tmp_path)
    result = _validated(_translate(_recorded(), stage), tmp_path)
    for evidence in result.evidence:
        path = evidence.location.path if evidence.location is not None else None
        assert evidence.hash is None or evidence.hash == stage.files[str(path)]


def test_native_hash_equal_to_the_staged_file_is_kept(tmp_path: Path) -> None:
    recorded = _recorded()
    native = next(iter(recorded["output"]["provenance"].values()))["artifact_sha256"]
    stage = StagedInput(root=tmp_path, files={"jobs/orders_job.py": native})
    result = _validated(_translate(recorded, stage), tmp_path)
    assert result.evidence and all(e.hash == native for e in result.evidence)


def test_divergent_artifact_sha256_becomes_null(tmp_path: Path) -> None:
    recorded = _recorded()
    verified = next(iter(recorded["output"]["provenance"].values()))["artifact_sha256"]
    for provenance in recorded["output"]["provenance"].values():
        provenance["artifact_sha256"] = "0" * 64
    stage = StagedInput(root=tmp_path, files={"jobs/orders_job.py": verified})
    result = _validated(_translate(recorded, stage), tmp_path)
    assert result.evidence and all(e.hash is None for e in result.evidence)


def test_file_not_staged_has_null_hash(tmp_path: Path) -> None:
    result = _validated(_translate(_recorded(), StagedInput(root=tmp_path)), tmp_path)
    assert result.evidence and all(e.hash is None for e in result.evidence)


def test_full_and_summary_fact_shapes_translate_alike(tmp_path: Path) -> None:
    recorded = _recorded()
    provenance = recorded["output"]["provenance"]
    native = next(iter(provenance.values()))["artifact_sha256"]
    stage = StagedInput(root=tmp_path, files={"jobs/orders_job.py": native})
    expected = _validated(_translate(recorded, stage), tmp_path).evidence
    full = json.loads(json.dumps(recorded))
    for item in _items(full):
        item["provenance"] = provenance[item.pop("provenance_ref")]
    del full["output"]["provenance"]
    summary = json.loads(json.dumps(recorded))
    for item in _items(summary):
        subject = item.pop("subject")
        item["at"] = f"{subject['file']}:{subject['line']}"
        if subject.get("symbol"):
            item["symbol"] = subject["symbol"]
    for variant in (full, summary):
        evidence = _validated(_translate(variant, stage), tmp_path).evidence
        assert [(e.id, e.location, e.hash, e.claim) for e in evidence] == [
            (e.id, e.location, e.hash, e.claim) for e in expected]


def test_location_is_remapped_to_the_workspace(tmp_path: Path) -> None:
    from theforge_sparkforge import translate

    stage = StagedInput(root=tmp_path, files={"jobs/orders_job.py": "a" * 64})
    assert translate.workspace_path("orders_job.py", "jobs", stage) == "jobs/orders_job.py"
    assert translate.workspace_path("jobs/orders_job.py", "", stage) == "jobs/orders_job.py"
    assert translate.workspace_path("../secret.py", "", stage) is None
    assert translate.workspace_path("", "", stage) is None
    inside = (tmp_path / "jobs" / "orders_job.py").resolve()
    assert translate.workspace_path(str(inside), "", stage) == "jobs/orders_job.py"
    assert translate.workspace_path(str(tmp_path.parent.resolve() / "x.py"), "", stage) is None


def test_unmappable_location_has_no_location_nor_hash(tmp_path: Path) -> None:
    recorded = _recorded()
    _items(recorded)[0]["subject"]["file"] = "../../outside.py"
    result = _validated(_translate(recorded, _staged(tmp_path)), tmp_path)
    first = result.evidence[0]
    assert first.location is None and first.hash is None
    assert any(first.id in note and "outside the workspace" in note
               for note in result.limitations)


@pytest.mark.parametrize("which", ["output", "judge"])
def test_remaining_pagination_becomes_a_partial_limitation(tmp_path: Path, which: str) -> None:
    recorded = _recorded()
    page = recorded["output"] if which == "output" else recorded["judge"]["output"]
    tool = ANALYZE_TOOL if which == "output" else JUDGE_TOOL
    total = page["total_count"]
    page["next_cursor"] = str(page["returned_count"])
    page["total_count"] = total + 7
    result = _validated(_translate(recorded, _staged(tmp_path)), tmp_path)
    assert result.status == "partial"
    assert (f"paginated: {tool} returned {page['returned_count']} of {total + 7} items"
            in result.limitations)


def test_reference_to_an_absent_fact_is_dropped_with_a_limitation(tmp_path: Path) -> None:
    recorded = _recorded()
    first = recorded["judge"]["output"]["items"][0]
    first["evidence"] = [*first["evidence"], "f_absent"]
    result = _validated(_translate(recorded, _staged(tmp_path)), tmp_path)
    assert "f_absent" not in result.findings[0].evidence_ids
    assert any("f_absent" in note for note in result.limitations)


def test_repeated_rule_ids_are_numbered_in_native_order(tmp_path: Path) -> None:
    recorded = _recorded()
    judged = recorded["judge"]["output"]["items"]
    judged.append(json.loads(json.dumps(judged[0])))
    result = _validated(_translate(recorded, _staged(tmp_path)), tmp_path)
    rule = judged[0]["rule_id"]
    assert [f.id for f in result.findings if f.id.startswith(rule)] == [f"{rule}#1",
                                                                       f"{rule}#2"]


@pytest.mark.parametrize(("native", "expected"), [("P0", "critical"), ("P1", "high"),
                                                  ("P2", "medium"), ("P3", "low"),
                                                  ("P4", "info")])
def test_native_severity_map(native: str, expected: str) -> None:
    from theforge_sparkforge import translate

    assert translate.SEVERITY[native] == expected


def test_stage_limitations_are_carried_into_the_result(tmp_path: Path) -> None:
    stage = StagedInput(root=tmp_path,
                        limitations=("context file 'x.py' skipped: file not found",))
    result = _validated(_translate(_recorded(), stage), tmp_path)
    assert stage.limitations[0] in result.limitations


def _refusal(reply: Any) -> Response:
    assert isinstance(reply, Reply), reply
    return from_dict(Response, {"request_id": "r", "op": "execute", "producer": PRODUCER,
                                "status": reply.status, "error": reply.error,
                                "limitations": reply.limitations})


def test_recorded_native_error_becomes_a_sparkforge_refusal() -> None:
    from theforge_sparkforge import translate

    native = json.loads(ERROR_RECORDING.read_text(encoding="utf-8"))
    assert set(native) >= {"error", "exit_code"}
    response = _refusal(translate.spark_error(native))
    assert response.status == "refused" and response.error is not None
    assert response.error.code.startswith("SPARKFORGE-")
    assert response.error.code == "SPARKFORGE-TOOL-ERROR"
    assert response.error.detail == native["error"]


def test_native_error_recording_is_replayed_through_translation(tmp_path: Path) -> None:
    from theforge_sparkforge import translate

    native = json.loads(ERROR_RECORDING.read_text(encoding="utf-8"))
    response = _refusal(translate.translate_spark(native, None, StagedInput(root=tmp_path),
                                                  tool=ANALYZE_TOOL))
    assert response.error is not None and response.error.code == "SPARKFORGE-TOOL-ERROR"


def test_typed_native_error_keeps_its_code_and_unlock() -> None:
    from theforge_sparkforge import translate

    native = {"error": "chamada recusada pela cadeia de autorizacao: approval",
              "exit_code": 2, "error_code": "UNAUTHORIZED", "required_approval": "write"}
    response = _refusal(translate.spark_error(native))
    assert response.status == "refused" and response.error is not None
    assert response.error.code == "SPARKFORGE-UNAUTHORIZED"
    assert response.error.detail == native["error"]
    assert response.error.unlock is not None and "write" in response.error.unlock


def test_untyped_native_failure_outside_the_refusal_exit_is_an_error() -> None:
    from theforge_sparkforge import translate

    response = _refusal(translate.spark_error({"error": "boom", "exit_code": 1}))
    assert response.status == "error" and response.error is not None
    assert response.error.code == "SPARKFORGE-TOOL-ERROR"


def test_judge_error_is_a_sparkforge_refusal(tmp_path: Path) -> None:
    from theforge_sparkforge import translate

    recorded = _recorded()
    judged = {"error": "facts[0] esta sem o campo obrigatorio 'subject'.", "exit_code": 2}
    response = _refusal(translate.translate_spark(recorded["output"], judged,
                                                  StagedInput(root=tmp_path),
                                                  tool=ANALYZE_TOOL))
    assert response.error is not None and response.error.code == "SPARKFORGE-TOOL-ERROR"
    assert response.error.detail == judged["error"]


def test_unknown_tool_is_a_structured_refusal() -> None:
    from theforge_sparkforge import translate

    response = _refusal(translate.unknown_tool("sparkforge_nope"))
    assert response.status == "refused" and response.error is not None
    assert response.error.code == "SPARKFORGE-TOOL-UNKNOWN"
    assert "sparkforge_nope" in response.error.detail


@pytest.mark.parametrize("native", [[], {"items": "x"}, {"total_count": 1}])
def test_malformed_native_output_is_a_structured_adapter_error(tmp_path: Path,
                                                               native: Any) -> None:
    from theforge_sparkforge import translate

    response = _refusal(translate.translate_spark(native, None, StagedInput(root=tmp_path),
                                                  tool=ANALYZE_TOOL))
    assert response.status == "error" and response.error is not None
    assert response.error.code == "SPARKFORGE-ADAPTER-NATIVE-INVALID"


def test_native_error_scenario_is_a_complete_replay_directory() -> None:
    assert (ERROR_SCENARIO / backend.ENVIRONMENT_FILE).is_file()
    assert (ERROR_SCENARIO / backend.HEALTH_FILE).is_file()
    found = backend.recording(ERROR_SCENARIO, CAPABILITY, ACTION)
    assert found == backend.Recording(kind="error", path=ERROR_RECORDING)


# --- execute recording helper (4.3, reused by 4.4) ----------------------------------------

Calls = list[tuple[str, dict[str, Any], Path]]


def _fake_call(responses: dict[str, Any], calls: Calls) -> Any:
    def call(name: str, arguments: dict[str, Any]) -> Any:
        cwd = Path.cwd()
        calls.append((name, dict(arguments), cwd))
        assert (cwd / "stage" / "jobs" / "orders_job.py").is_file()
        response = responses[name]
        return response(cwd) if callable(response) else response
    return call


_ACCEPTED = frozenset({"path", "kind", "limit", "cursor", "detail_level"})


def test_recording_helper_records_the_tool_output_and_the_chained_judge() -> None:
    from theforge_sparkforge import record_execute

    output = {"items": [{"id": "f_1", "kind": "pyspark.udf"}], "next_cursor": None}
    judged = {"items": [], "next_cursor": None}
    calls: Calls = []
    before = Path.cwd()
    name, data = record_execute.record_action(
        _fake_call({ANALYZE_TOOL: output, JUDGE_TOOL: judged}, calls),
        workspace=WORKSPACE, capability=CAPABILITY, action=ACTION,
        arguments={"path": "jobs"}, accepted=_ACCEPTED)
    assert Path.cwd() == before
    assert name == f"{CAPABILITY}.{ACTION}.json"
    assert data == {"tool": ANALYZE_TOOL,
                    "arguments": {"path": "jobs", "detail_level": "normal", "limit": 200},
                    "output": output,
                    "judge": {"tool": JUDGE_TOOL, "arguments": {"limit": 200},
                              "output": judged}}
    (tool, args, cwd), (judge, judge_args, _) = calls
    assert tool == ANALYZE_TOOL and args["path"] == "stage/jobs"
    assert judge == JUDGE_TOOL and judge_args == {"facts": output["items"], "limit": 200}
    assert not cwd.exists()  # the temporary copy is gone
    assert not (WORKSPACE / "stage").exists()


def test_recording_helper_writes_a_native_error_as_the_error_recording() -> None:
    from theforge_sparkforge import record_execute

    error = {"error": "Caminho nao encontrado para analise: stage/jobs/missing_job.py",
             "exit_code": 2}
    calls: Calls = []
    name, data = record_execute.record_action(
        _fake_call({ANALYZE_TOOL: error}, calls), workspace=WORKSPACE,
        capability=CAPABILITY, action=ACTION, arguments={"path": "jobs/missing_job.py"},
        accepted=_ACCEPTED)
    assert name == f"{CAPABILITY}.{ACTION}.error.json"
    assert data == error
    assert [call[0] for call in calls] == [ANALYZE_TOOL]  # no judge without facts


def test_recording_helper_refuses_a_recording_with_machine_paths() -> None:
    from theforge_sparkforge import record_execute

    def leaky(cwd: Path) -> dict[str, Any]:
        return {"items": [], "next_cursor": None, "root": str(cwd)}

    with pytest.raises(record_execute.RecordingError, match="machine path"):
        record_execute.record_action(
            _fake_call({ANALYZE_TOOL: leaky}, []), workspace=WORKSPACE,
            capability=CAPABILITY, action=ACTION, arguments={"path": "jobs"},
            accepted=_ACCEPTED)


def test_recording_helper_rejects_an_undeclared_action_or_escaping_argument() -> None:
    from theforge_sparkforge import record_execute

    call = _fake_call({}, [])
    with pytest.raises(record_execute.RecordingError, match="action"):
        record_execute.record_action(call, workspace=WORKSPACE, capability=CAPABILITY,
                                     action="nope", arguments={}, accepted=_ACCEPTED)
    with pytest.raises(record_execute.RecordingError, match="workspace-relative"):
        record_execute.record_action(call, workspace=WORKSPACE, capability=CAPABILITY,
                                     action=ACTION, arguments={"path": "../x"},
                                     accepted=_ACCEPTED)


def test_recording_helper_without_sparkforge_fails_and_writes_nothing(tmp_path: Path) -> None:
    if importlib.util.find_spec("sparkforge") is not None:
        pytest.skip("the Spark Forge is importable in this interpreter")
    out = subprocess.run([sys.executable, "-m", "theforge_sparkforge.record_execute",
                          "--workspace", str(WORKSPACE), "--capability", CAPABILITY,
                          "--action", ACTION, "--arg", "path=jobs", "--out", str(tmp_path)],
                         capture_output=True, timeout=60, cwd=tmp_path)
    assert out.returncode != 0
    assert b"sparkforge is not importable" in out.stderr
    assert list(tmp_path.iterdir()) == []


def test_recording_helper_rejects_a_missing_file_or_overlapping_workspace(
        tmp_path: Path) -> None:
    from theforge_sparkforge import record_execute

    check = record_execute.check_workspace
    with pytest.raises(record_execute.RecordingError, match="does not exist"):
        check(tmp_path / "missing")
    (tmp_path / "file.py").write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(record_execute.RecordingError, match="existing directory"):
        check(tmp_path / "file.py")
    workspace = tmp_path / "ws"
    (workspace / "out").mkdir(parents=True)
    for out in (workspace, workspace / "out", tmp_path):
        with pytest.raises(record_execute.RecordingError, match="overlap"):
            check(workspace, out)
    assert check(workspace, tmp_path / "elsewhere") == workspace.resolve()
    with pytest.raises(record_execute.RecordingError, match="does not exist"):
        record_execute.record_action(_fake_call({}, []), workspace=tmp_path / "missing",
                                     capability=CAPABILITY, action=ACTION,
                                     arguments={"path": "jobs"}, accepted=_ACCEPTED)


def test_recording_helper_never_copies_nor_follows_links(tmp_path: Path) -> None:
    from theforge_sparkforge import record_execute

    workspace = tmp_path / "ws"
    shutil.copytree(WORKSPACE, workspace)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.py").write_text("token = 1\n", encoding="utf-8")
    try:
        (workspace / "linked").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks are not available to this user")
    seen: list[bool] = []

    def call(name: str, arguments: dict[str, Any]) -> Any:
        seen.append((Path.cwd() / "stage" / "linked").exists())
        return {"items": [], "next_cursor": None}

    record_execute.record_action(call, workspace=workspace, capability=CAPABILITY,
                                 action=ACTION, arguments={"path": "jobs"},
                                 accepted=_ACCEPTED)
    assert seen == [False]
    with pytest.raises(record_execute.RecordingError, match="not a link"):
        record_execute.check_workspace(workspace / "linked")


# --- execute with the replay and live backends (4.4) --------------------------------------

WORKSPACE_FILES = ["jobs/orders_job.py", "requirements.txt"]
SPILL = "native/full-output.json"
RECORDED_ACTIONS = sorted(path.name[:-len(".json")].rsplit(".", 1)
                          for path in DEFAULT.glob("*.json")
                          if path.name not in (backend.ENVIRONMENT_FILE, backend.HEALTH_FILE))


def _execute(cwd: Path, *options: str, capability: str = CAPABILITY, action: str = ACTION,
             files: list[str] | None = None, root: Path = WORKSPACE,
             env: dict[str, str] | None = None,
             handoff: dict[str, Any] | None = None) -> Response:
    payload = {"task": {"intent": "analyze the spark job", "budget_profile": "balanced"},
               "capability": capability, "action": action,
               **_context(root, WORKSPACE_FILES if files is None else files)}
    if handoff is not None:
        payload["handoff"] = handoff
    argv = [sys.executable, "-m", "theforge_sparkforge", *options, "execute"]
    out = subprocess.run(argv, input=_request("execute", payload), capture_output=True,
                         timeout=180, cwd=cwd, env=env)
    assert out.returncode == 0, out.stderr
    response = from_dict(Response, json.loads(out.stdout))
    assert (response.producer.id, response.producer.version) == ("spark-forge", "0.3.0")
    return response


def _result(response: Response) -> ExecutionResult:
    assert response.status in ("ok", "partial"), response.error
    result = from_dict(ExecutionResult, response.payload, "$.payload")
    validate_result(result, expected=Producer(**PRODUCER))
    return result


def _left_in(cwd: Path) -> set[str]:
    """Every file and directory left in ``cwd`` (relative POSIX paths)."""
    return {path.relative_to(cwd).as_posix() for path in cwd.rglob("*")}


def _assert_only_artifacts(cwd: Path, response: Response) -> None:
    artifacts = ({item["path"] for item in response.payload.get("artifacts") or []}
                 if response.status in ("ok", "partial") else set())
    parents = {parent.as_posix() for path in artifacts
               for parent in PurePosixPath(path).parents if parent.as_posix() != "."}
    assert _left_in(cwd) == artifacts | parents


def _replay_scenario(tmp_path: Path, *recordings: Path) -> Path:
    """A replay directory with the default environment and health and only ``recordings``."""
    scenario = tmp_path / "scenario"
    scenario.mkdir()
    for name in (backend.ENVIRONMENT_FILE, backend.HEALTH_FILE):
        shutil.copyfile(DEFAULT / name, scenario / name)
    for path in recordings:
        shutil.copyfile(path, scenario / path.name)
    return scenario


def _run_dir(tmp_path: Path) -> Path:
    cwd = tmp_path / "work"
    cwd.mkdir()
    return cwd


def test_the_default_scenario_records_the_actions_exercised_over_the_spark_workspace() -> None:
    assert [CAPABILITY, ACTION] in RECORDED_ACTIONS
    assert [CAPABILITY, "graph"] in RECORDED_ACTIONS


@pytest.mark.parametrize(("capability", "action"), RECORDED_ACTIONS)
def test_every_recorded_action_replays_to_a_result_that_passes_core_integrity(
        tmp_path: Path, capability: str, action: str) -> None:
    cwd = _run_dir(tmp_path)
    response = _execute(cwd, "--replay", str(DEFAULT), capability=capability, action=action)
    result = _result(response)
    recorded = json.loads((DEFAULT / f"{capability}.{action}.json").read_text("utf-8"))
    assert [e.id for e in result.evidence] == [item["id"] for item in _items(recorded)]
    assert len(result.findings) == len(recorded["judge"]["output"]["items"])
    _assert_only_artifacts(cwd, response)
    assert _left_in(cwd) == set()


def test_replay_of_an_unrecorded_action_is_replay_missing_naming_the_file(
        tmp_path: Path) -> None:
    cwd = _run_dir(tmp_path)
    response = _execute(cwd, "--replay", str(_replay_scenario(tmp_path)))
    assert response.status == "error" and response.error is not None
    assert response.error.code == "ADAPTER-REPLAY-MISSING"
    assert f"{CAPABILITY}.{ACTION}.json" in response.error.detail
    assert _left_in(cwd) == set()


def test_execute_without_compatible_input_is_partial_without_reading_recordings(
        tmp_path: Path) -> None:
    scenario = _replay_scenario(tmp_path)
    # A recording that would be an error if it were read.
    (scenario / f"{CAPABILITY}.{ACTION}.json").write_text("not json", encoding="utf-8")
    cwd = _run_dir(tmp_path)
    response = _execute(cwd, "--replay", str(scenario), files=["requirements.txt"])
    result = _result(response)
    assert result.status == "partial"
    assert not result.findings and not result.evidence
    assert any(note.startswith("no input: expected *.py") for note in result.limitations)
    assert result.unknowns == ["input:path"]
    assert _left_in(cwd) == set()


def test_replayed_native_error_is_a_sparkforge_refusal_with_workspace_paths(
        tmp_path: Path) -> None:
    cwd = _run_dir(tmp_path)
    response = _execute(cwd, "--replay", str(ERROR_SCENARIO))
    assert response.status == "refused" and response.error is not None
    assert response.error.code == "SPARKFORGE-TOOL-ERROR"
    assert "jobs/missing_job.py" in response.error.detail
    assert "stage/" not in response.error.detail
    assert _left_in(cwd) == set()


@pytest.mark.parametrize("content", ["not json", "[]", '{"tool": "sparkforge_analyze_graph", '
                                     '"arguments": {}, "output": {"items": []}, "judge": null}'])
def test_unusable_replay_recording_is_replay_invalid(tmp_path: Path, content: str) -> None:
    scenario = _replay_scenario(tmp_path)
    (scenario / f"{CAPABILITY}.{ACTION}.json").write_text(content, encoding="utf-8")
    cwd = _run_dir(tmp_path)
    response = _execute(cwd, "--replay", str(scenario))
    assert response.status == "error" and response.error is not None
    assert response.error.code == "ADAPTER-REPLAY-INVALID"
    assert _left_in(cwd) == set()


COPIES = 1000


def _large_recording() -> dict[str, Any]:
    """The real recording widened past the inline limit (derived in the test, never
    versioned): every fact and finding repeated with fresh ids."""
    recorded = _recorded()
    facts, judged = _items(recorded), recorded["judge"]["output"]["items"]
    many_facts: list[dict[str, Any]] = []
    many_findings: list[dict[str, Any]] = []
    for copy in range(COPIES):
        renamed = {item["id"]: f"{item['id']}_{copy}" for item in facts}
        many_facts.extend({**item, "id": renamed[item["id"]]} for item in facts)
        many_findings.extend({**item, "evidence": [renamed[ref] for ref in item["evidence"]]}
                             for item in judged)
    recorded["output"]["items"] = many_facts
    recorded["output"]["returned_count"] = recorded["output"]["total_count"] = len(many_facts)
    recorded["judge"]["output"]["items"] = many_findings
    recorded["provenance"] = (f"derived in the test from the default recording, "
                              f"widened {COPIES}x")
    return recorded


def test_large_replayed_output_is_partial_with_the_spill_artifact(tmp_path: Path) -> None:
    scenario = _replay_scenario(tmp_path)
    (scenario / f"{CAPABILITY}.{ACTION}.json").write_text(
        record.render(_large_recording()), encoding="utf-8")
    cwd = _run_dir(tmp_path)
    response = _execute(cwd, "--replay", str(scenario))
    result = _result(response)
    assert result.status == "partial"
    assert [a.path for a in result.artifacts] == [SPILL]
    spilled = (cwd / SPILL).read_bytes()
    assert hashlib.sha256(spilled).hexdigest() == result.artifacts[0].sha256
    assert any(note.startswith("output truncated:") for note in result.limitations)
    _assert_only_artifacts(cwd, response)


# Live backend over a stand-in ``sparkforge`` package (the real one runs in 7.2 and in the
# manual smoke): it records where and with what it was called, writes its ledger into the
# process cwd during the call and at exit, and answers with the real recording.
FAKE_TOOLS = '''\
import atexit
import json
import os
from pathlib import Path, PurePosixPath

RECORDING = json.loads(Path(os.environ["FAKE_SPARKFORGE_RECORDING"]).read_text("utf-8"))
MODE = os.environ.get("FAKE_SPARKFORGE_MODE", "ok")
TOOLS = {
    "sparkforge_analyze_pyspark": {"inputSchema": {"properties": {
        "path": {}, "kind": {}, "limit": {}, "cursor": {}, "detail_level": {},
        "upstream": {}}}},
    "sparkforge_analyze_graph": {"inputSchema": {"properties": {"path": {}, "limit": {}}}},
    "sparkforge_judge": {"inputSchema": {"properties": {"facts": {}, "limit": {}}}},
}


def _ledger():
    db = Path.cwd() / ".sparkforge" / "traces.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    db.write_text("ledger", encoding="utf-8")


atexit.register(_ledger)


def call_tool(name, arguments):
    probe = {"tool": name, "cwd": os.getcwd(), "facts": len(arguments.get("facts") or []),
             "arguments": {k: v for k, v in arguments.items() if k != "facts"}}
    with open(os.environ["FAKE_SPARKFORGE_PROBE"], "a", encoding="utf-8") as fh:
        fh.write(json.dumps(probe) + "\\n")
    if MODE == "unknown" or name not in TOOLS:
        raise KeyError(name)
    if MODE == "crash":
        raise RuntimeError("native crash")
    print("native chatter on stdout")
    if MODE == "noisy":
        import sys
        os.write(1, b"raw fd noise\\n")
        sys.__stdout__.write("dunder stdout noise\\n")
        sys.__stdout__.flush()
        atexit.register(print, "atexit noise on stdout")
    _ledger()
    if "path" in arguments:
        (Path(arguments["path"]) / ".sparkforge" / "cache").mkdir(parents=True, exist_ok=True)
    if MODE == "error":
        return {"error": "Caminho nao encontrado para analise: stage/jobs/x.py", "exit_code": 2}
    if name == "sparkforge_judge":
        return RECORDING["judge"]["output"]
    output = dict(RECORDING["output"])
    if MODE != "old" and arguments.get("upstream"):
        filters = dict(output.get("filters_applied") or {})
        filters["upstream"] = arguments["upstream"]
        output["filters_applied"] = filters
        items = list(output.get("items") or [])
        items.append({
            "id": "upstream:provider:data:item-1",
            "kind": "upstream.evidence",
            "subject": {"file": "jobs/x.py", "line": 4},
            "measures": {"subject": "provider.finding"},
            "attrs": {"upstream": {
                "provider": "doctor-data", "run_id": "run-1", "node": "observe",
                "item": "ev#1", "epistemic": "inferred",
                "claim": "dataframe churned"}},
            "provenance": {"extractor": "theforge/handoff"},
        })
        output["items"] = items
        output["total_count"] = output.get("total_count", len(items)) + 1
        output["returned_count"] = output.get("returned_count", len(items)) + 1
    return output
'''


def _fake_sparkforge(tmp_path: Path, mode: str = "ok") -> tuple[dict[str, str], Path]:
    fake = tmp_path / "fake"
    (fake / "sparkforge" / "adapters").mkdir(parents=True)
    (fake / "sparkforge" / "__init__.py").write_text('__version__ = "0.5.0"\n', "utf-8")
    (fake / "sparkforge" / "adapters" / "__init__.py").write_text("", "utf-8")
    (fake / "sparkforge" / "adapters" / "tools.py").write_text(FAKE_TOOLS, "utf-8")
    probe = tmp_path / "probe.jsonl"
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(fake), env.get("PYTHONPATH")]))
    env.update(FAKE_SPARKFORGE_RECORDING=str(OUTPUT_RECORDING),
               FAKE_SPARKFORGE_PROBE=str(probe), FAKE_SPARKFORGE_MODE=mode)
    return env, probe


def _probes(probe: Path) -> list[dict[str, Any]]:
    if not probe.exists():
        return []
    return [json.loads(line) for line in probe.read_text("utf-8").splitlines()]


def test_live_execute_calls_the_tool_and_judge_with_repository_and_state_under_the_cwd(
        tmp_path: Path) -> None:
    env, probe = _fake_sparkforge(tmp_path)
    cwd = _run_dir(tmp_path)
    response = _execute(cwd, env=env)
    result = _result(response)
    recorded = _recorded()
    assert result.status == "ok"
    assert [e.id for e in result.evidence] == [item["id"] for item in _items(recorded)]
    assert len(result.findings) == len(recorded["judge"]["output"]["items"])
    tool_call, judge_call = _probes(probe)
    assert tool_call["tool"] == ANALYZE_TOOL
    assert tool_call["arguments"] == {"path": "stage/jobs", "detail_level": "normal",
                                      "limit": 200}
    assert judge_call["tool"] == JUDGE_TOOL
    assert judge_call["arguments"] == {"limit": 200}
    assert judge_call["facts"] == len(_items(recorded))
    for call in (tool_call, judge_call):
        # The native state (.sparkforge/ ledger, cache) goes to the process cwd: the run cwd.
        assert Path(call["cwd"]).resolve() == cwd.resolve()
    repository = (cwd / tool_call["arguments"]["path"]).resolve()
    assert repository.is_relative_to((cwd / "stage").resolve())
    # stage/, the native ledger written at exit and the repository cache are gone.
    assert _left_in(cwd) == set()
    assert not (WORKSPACE / ".sparkforge").exists()


def test_live_execute_without_compatible_input_never_calls_the_specialist(
        tmp_path: Path) -> None:
    env, probe = _fake_sparkforge(tmp_path)
    cwd = _run_dir(tmp_path)
    result = _result(_execute(cwd, env=env, files=["requirements.txt"]))
    assert result.status == "partial" and result.unknowns == ["input:path"]
    assert _probes(probe) == []
    assert _left_in(cwd) == set()


@pytest.mark.parametrize(("mode", "status", "code"), [
    ("error", "refused", "SPARKFORGE-TOOL-ERROR"),
    ("unknown", "refused", "SPARKFORGE-TOOL-UNKNOWN"),
    ("crash", "error", "SPARKFORGE-ADAPTER-NATIVE-FAILED"),
])
def test_live_native_failures_are_structured_and_leave_nothing(
        tmp_path: Path, mode: str, status: str, code: str) -> None:
    env, _ = _fake_sparkforge(tmp_path, mode)
    cwd = _run_dir(tmp_path)
    response = _execute(cwd, env=env)
    assert response.status == status and response.error is not None
    assert response.error.code == code
    assert "stage/" not in response.error.detail
    assert _left_in(cwd) == set()


@pytest.mark.parametrize("path", ["../x.py", "/etc/x.py", "C:/x.py", r"jobs\x.py", "",
                                  "a/../../x"])
def test_native_call_refuses_file_arguments_outside_the_stage(tmp_path: Path,
                                                              path: str) -> None:
    from theforge_sparkforge import native_call

    with pytest.raises(native_call.CallError):
        native_call.staged_path(path, tmp_path)


def test_native_call_maps_stage_relative_paths(tmp_path: Path) -> None:
    from theforge_sparkforge import native_call

    assert native_call.staged_path(".", tmp_path) == "stage"
    assert native_call.staged_path("jobs", tmp_path) == "stage/jobs"
    assert native_call.staged_path("./jobs/x.py", tmp_path) == "stage/jobs/x.py"


def test_native_call_cli_refuses_an_escaping_file_before_importing_the_specialist(
        tmp_path: Path) -> None:
    out = subprocess.run([sys.executable, "-m", "theforge_sparkforge.native_call",
                          "--tool", ANALYZE_TOOL, "--file", "path=../outside"],
                         capture_output=True, timeout=60, cwd=tmp_path)
    assert out.returncode == 2
    assert b"must be a path relative to stage/" in out.stderr
    assert out.stdout == b""


@pytest.mark.parametrize(("matches", "expected"), [
    (["jobs/a.py"], "jobs"), (["jobs/a.py", "jobs/sub/b.py"], "jobs"),
    (["a.py", "jobs/b.py"], "."), (["x/a.py", "y/b.py"], "."),
])
def test_directory_binding_takes_the_deepest_common_staged_directory(
        matches: list[str], expected: str) -> None:
    from theforge_sparkforge import execute

    binding = catalog.ArgBinding(arg="path", globs=("*.py",), directory=True)
    assert execute.bound_files(binding, matches) == ({"path": expected}, [])


def test_file_binding_takes_the_first_match_and_notes_the_rest() -> None:
    from theforge_sparkforge import execute

    binding = catalog.ArgBinding(arg="path", globs=("*.jsonl",))
    files, notes = execute.bound_files(binding, ["a.jsonl", "b.jsonl"])
    assert files == {"path": "a.jsonl"}
    assert notes == ["path: 2 staged files match; analyzed a.jsonl only"]


def test_live_native_writes_to_the_stdout_fd_never_corrupt_the_answer(tmp_path: Path) -> None:
    env, _ = _fake_sparkforge(tmp_path, "noisy")
    cwd = _run_dir(tmp_path)
    result = _result(_execute(cwd, env=env))
    assert result.status == "ok"
    assert [e.id for e in result.evidence] == [item["id"] for item in _items(_recorded())]
    assert _left_in(cwd) == set()


# --- handoff intake (upstream-facts) ------------------------------------------------------

HANDOFF_ORIGIN = {"plan_run": "plan-1", "node": "observe", "run_id": "run-1",
                  "provider": {"id": "doctor-data", "version": "1.0.0rc1"}}


def _handoff(*items: Any) -> dict[str, Any]:
    return {"schema": "theforge/Handoff/v1",
            "producer": {"id": "theforge", "version": "0.4.0"},
            "created_at": "2026-01-01T00:00:00Z", "plan_run": "plan-1",
            "target_node": "engineer", "items": list(items)}


def _handoff_item(**over: Any) -> dict[str, Any]:
    item: dict[str, Any] = {"kind": "evidence", "id": "ev#1",
                            "origin": dict(HANDOFF_ORIGIN), "epistemic": "inferred",
                            "subject": "pyspark.dataframe",
                            "claim": "the dataframe is rebuilt per batch",
                            "location": {"path": "jobs/orders_job.py", "line": 42}}
    item.update(over)
    return item


def test_translate_handoff_maps_each_item_to_a_foreign_fact() -> None:
    from theforge_sparkforge import handoff as upstream

    document, notes = upstream.translate_handoff(_handoff(_handoff_item()))
    assert notes == []
    assert document["schema"] == "sparkforge/upstream-facts/v1"
    (fact,) = document["facts"]
    assert fact["id"].startswith("upstream:")
    assert fact["kind"] == "upstream.evidence"
    assert fact["provenance"]["extractor"] == "theforge/handoff"
    assert "artifact" not in fact["provenance"]  # the intake stamps what it consumed
    map_ = fact["attrs"]["upstream"]
    assert map_["provider"] == "doctor-data" and map_["run_id"] == "run-1"
    assert map_["node"] == "observe" and map_["item"] == "ev#1"
    assert map_["plan_run"] == "plan-1"
    assert map_["epistemic"] == "inferred"  # verbatim, never upgraded
    assert map_["claim"] == "the dataframe is rebuilt per batch"
    assert fact["subject"] == {"file": "jobs/orders_job.py", "line": 42}


def test_translate_handoff_is_deterministic_and_bounded() -> None:
    from theforge_sparkforge import handoff as upstream

    items = [_handoff_item(id=f"ev#{n}", claim=f"claim {n}") for n in range(130)]
    document, notes = upstream.translate_handoff(_handoff(*items))
    assert len(document["facts"]) == 128
    assert any("truncated to 128" in note for note in notes)
    again, _ = upstream.translate_handoff(_handoff(*items))
    assert again == document  # content-addressed ids: byte-identical rerun


def test_translate_handoff_skips_malformed_items_with_a_limitation() -> None:
    from theforge_sparkforge import handoff as upstream

    document, notes = upstream.translate_handoff(
        _handoff(_handoff_item(), {"kind": "evidence", "id": ""}, "not-a-mapping"))
    assert len(document["facts"]) == 1
    assert notes == ["2 handoff item(s) malformed: not translated"]


def test_manifest_declares_the_handoff_intake_on_static_analysis(
        manifest: ForgeManifest) -> None:
    static = next(c for c in manifest.capabilities if c.id == "pyspark.static-analysis")
    assert static.accepts_handoff is True
    assert list(static.relations.consumes) == ["data.diagnostic-evidence"]
    others = [c for c in manifest.capabilities if c.id != "pyspark.static-analysis"]
    assert all(not c.accepts_handoff for c in others)
    assert "handoff/v1" in manifest.features


def test_live_execute_feeds_the_handoff_to_the_native_intake(tmp_path: Path) -> None:
    env, probe = _fake_sparkforge(tmp_path)
    cwd = _run_dir(tmp_path)
    result = _result(_execute(cwd, env=env, handoff=_handoff(_handoff_item())))
    assert result.status == "ok"
    tool_call = _probes(probe)[0]
    assert tool_call["arguments"]["upstream"] == "stage/upstream-facts.json"
    foreign = [e for e in result.evidence if e.id.startswith("upstream:")]
    assert len(foreign) == 1
    entry = foreign[0]
    assert entry.epistemic == "inferred"  # the producer's status, verbatim
    assert entry.derived_from is not None
    assert entry.derived_from.provider == "doctor-data"
    assert entry.derived_from.run_id == "run-1" and entry.derived_from.item == "ev#1"
    assert not [n for n in result.limitations if "not consumed" in n]
    # The intake file is staged, never left behind.
    assert _left_in(cwd) == set()


def test_live_execute_reports_a_handoff_the_specialist_did_not_consume(
        tmp_path: Path) -> None:
    env, _ = _fake_sparkforge(tmp_path, "old")  # a Spark Forge without the intake ignores it
    cwd = _run_dir(tmp_path)
    result = _result(_execute(cwd, env=env, handoff=_handoff(_handoff_item())))
    assert any("handoff delivered but not consumed" in n and "upstream intake" in n
               for n in result.limitations)


def test_execute_without_handoff_never_writes_nor_passes_the_intake(
        tmp_path: Path) -> None:
    env, probe = _fake_sparkforge(tmp_path)
    cwd = _run_dir(tmp_path)
    result = _result(_execute(cwd, env=env))
    assert result.status == "ok"
    assert "upstream" not in _probes(probe)[0]["arguments"]
    assert not [n for n in result.limitations if "handoff" in n]
    assert _left_in(cwd) == set()


def test_execute_on_a_capability_without_intake_reports_the_handoff(
        tmp_path: Path) -> None:
    env, probe = _fake_sparkforge(tmp_path)
    cwd = _run_dir(tmp_path)
    result = _result(_execute(cwd, env=env, action="graph",
                              handoff=_handoff(_handoff_item())))
    assert result.status == "ok"
    assert any("handoff delivered but not consumed" in n and "'pyspark'" in n
               for n in result.limitations)
    assert "upstream" not in _probes(probe)[0]["arguments"]
    assert _left_in(cwd) == set()


def test_replay_with_a_handoff_reports_the_recording_did_not_consume_it(
        tmp_path: Path) -> None:
    scenario = _replay_scenario(tmp_path, OUTPUT_RECORDING)
    cwd = _run_dir(tmp_path)
    result = _result(_execute(cwd, "--replay", str(scenario),
                              handoff=_handoff(_handoff_item())))
    assert result.status == "ok"
    assert any("handoff delivered but not consumed" in n and "recorded run" in n
               for n in result.limitations)
    assert _left_in(cwd) == set()  # no intake file is ever written in replay


def test_recording_helper_feeds_a_handoff_through_the_native_intake(tmp_path: Path) -> None:
    from theforge_sparkforge import record_execute

    staged: list[Path] = []
    output = {"items": [], "next_cursor": None}

    def call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        staged.append(Path(arguments["upstream"]))
        return output

    name, data = record_execute.record_action(
        call, workspace=WORKSPACE, capability=CAPABILITY, action=ACTION,
        arguments={"path": "jobs"}, accepted=_ACCEPTED | {"upstream"},
        handoff=_handoff(_handoff_item()))
    assert name == f"{CAPABILITY}.{ACTION}.json"
    assert data["arguments"]["upstream"] == "upstream-facts.json"  # workspace-relative
    # The tool saw the staged document while it existed.
    assert staged == [Path("stage/upstream-facts.json")]


def test_recording_helper_refuses_a_handoff_on_a_capability_without_intake() -> None:
    from theforge_sparkforge import record_execute

    with pytest.raises(record_execute.RecordingError, match="upstream intake"):
        record_execute.record_action(_fake_call({}, []), workspace=WORKSPACE,
                                     capability="spark.runtime-analysis", action="plan",
                                     arguments={"path": "jobs"}, accepted=_ACCEPTED,
                                     handoff=_handoff(_handoff_item()))
