"""Spark Forge adapter (real-provider-integration 4.1): manifest derived from the recorded
native tool surface, the capability table, describe with and without ``--replay``, the replay
layout and the snapshot re-recording.

The dev interpreter does not have the Spark Forge installed: describe there must be refused
with an actionable reason, and every manifest check runs in replay (``environment.json`` stands
in for the import check, the packaged ``native_catalog.json`` is the tool surface).
"""

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

from theforge.contracts import PROTOCOL_V1, ForgeManifest, Response, from_dict
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
