"""Integration conformance against the real Forges (real-provider-integration 7.2).

Marker ``real_provider`` (excluded from the default selection): ``python -m pytest -m
real_provider``. Each Forge runs only when the environment contract of ``real_providers.py``
(``THEFORGE_REAL_{SPARKFORGE,APIFORGE}_PYTHON``) names an interpreter with the adapter and the
specialist; otherwise its tests skip with the reason, or fail when
``THEFORGE_REAL_PROVIDERS_REQUIRED=1``. See ``docs/real-providers.md``.

The real adapter is registered in the test's isolated user ``providers.toml`` (``id``/``argv``/
``trust`` only) and everything goes through the core: ``Registry`` (describe), ``check_health``
and ``Forger.ask`` with the ``RunStore`` and the receipt. Covered per Forge: describe (ready,
SemVer, offline, taxonomy), health without credentials, execute of an exposed capability on the
example workspace (integrity, native ids, native state contained in the run, ``work/`` reduced
to the artifacts, evidence hashes equal to the ContextPack), absence (missing interpreter,
interpreter without the specialist), version skew, and drift (recorded snapshot vs. live
surface; live native output vs. the replay recording of the same action).

The core's ``check_health`` keeps only the status, so the version-skew and degraded-health
details are read from the adapter's own health reply (implementation note 4.2).
"""

import importlib.util
import json
import re
import secrets
import shutil
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import pytest

import real_providers as rp
from theforge.contracts import (
    ContextPack,
    ExecutionReceipt,
    ExecutionResult,
    HealthReport,
    Producer,
    from_dict,
)
from theforge.contracts.codes import Codes
from theforge.contracts.integrity import (
    validate_context_pack,
    validate_receipt,
    validate_result,
)
from theforge.contracts.semver import parse_semver
from theforge.contracts.taxonomy import validate_taxonomy
from theforge.forger import AskOutcome, AskRequest, Forger
from theforge.protocol import SubprocessTransport
from theforge.registry import Registry, RegistryRecord, check_health
from theforge.registry.registry import provider_cwd
from theforge.runs import RunStore
from theforge.security.env import is_credential_name, safe_env
from theforge.state import init_workspace

REPO = Path(__file__).parents[1]
FIXTURES = REPO / "tests" / "fixtures"
ADAPTERS = REPO / "adapters"
# Native state directories / files the specialists write into their cwd.
NATIVE_STATE = {".sparkforge", ".apiforge", "traces.db", "stage"}
# Credential-shaped variables set in the test process: none may reach a provider.
# Values are random per session (never literals), so a leak check cannot match by accident.
CREDENTIALS = {name: f"theforge-sentinel-{secrets.token_hex(8)}"
               for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "GITHUB_TOKEN",
                            "OPENAI_API_KEY")}
NATIVE_TIMEOUT = 300.0
HEALTH_TIMEOUT = 60.0


@dataclass(frozen=True)
class Case:
    name: str
    workspace: Path
    capability: str
    action: str
    supported: str
    snapshot: Path

    @property
    def recording(self) -> Path:
        return FIXTURES / "native" / self.native / "default" / (
            f"{self.capability}.{self.action}.json")

    @property
    def native(self) -> str:
        return rp.FORGES[self.name].adapter_module.removeprefix("theforge_")

    @property
    def spec(self) -> rp.ForgeSpec:
        return rp.FORGES[self.name]

    @property
    def unavailable_code(self) -> str:
        return f"{self.spec.provider_id.replace('-', '').upper()}-ADAPTER-UNAVAILABLE"


CASES = {
    "spark": Case("spark", FIXTURES / "workspaces" / "spark", "pyspark.static-analysis",
                  "pyspark", ">=0.5.0,<0.6.0",
                  ADAPTERS / "sparkforge" / "src" / "theforge_sparkforge"
                  / "native_catalog.json"),
    "api": Case("api", FIXTURES / "workspaces" / "api", "api.analyze", "analyze",
                ">=0.1.0,<0.2.0",
                ADAPTERS / "apiforge" / "src" / "theforge_apiforge" / "native_matrix.json"),
}


@pytest.fixture(params=sorted(CASES))
def case(request: pytest.FixtureRequest) -> Case:
    return CASES[str(request.param)]


@pytest.fixture
def forge(case: Case) -> rp.RealForge:
    return rp.require_forge(case.name)


@pytest.fixture
def credentials(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, str]]:
    for name, value in CREDENTIALS.items():
        monkeypatch.setenv(name, value)
    yield CREDENTIALS


# --- helpers ------------------------------------------------------------------------------

def _workspace(tmp_path: Path, case: Case, config_dir: Path,
               *entries: dict[str, Any]) -> Path:
    """A copy of the example workspace with ``entries`` in the isolated user providers.toml."""
    root = tmp_path / "ws"
    shutil.copytree(case.workspace, root)
    init_workspace(root)
    rp.register(config_dir, *entries)
    return root


def _record(root: Path, provider_id: str) -> RegistryRecord:
    return Registry(root / ".forge").get(provider_id)


def _ask(root: Path, case: Case) -> tuple[AskOutcome, RunStore]:
    forge_dir = root / ".forge"
    store = RunStore(forge_dir)
    outcome = Forger(root, Registry(forge_dir), store).ask(AskRequest(
        intent="analyze this workspace", capability=case.capability, action=case.action))
    return outcome, store


def _raw_health(argv: list[str]) -> tuple[HealthReport, str]:
    """The adapter's own health reply (the core's ``check_health`` keeps only the status)."""
    with provider_cwd() as cwd:
        response = SubprocessTransport(argv).call("health", {}, timeout=HEALTH_TIMEOUT,
                                                  cwd=Path(cwd))
    assert response.status == "ok", response.error
    report = from_dict(HealthReport, response.payload, "$.payload")
    return report, json.dumps(response.payload)


def _run_native(argv: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """A command in a specialist interpreter with the core's credential-free environment."""
    proc = subprocess.run(argv, cwd=cwd, env=safe_env(), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=NATIVE_TIMEOUT,
                          stdin=subprocess.DEVNULL, check=False)
    assert proc.returncode == 0, (argv, proc.stdout, proc.stderr)
    return proc


def _left_in(directory: Path) -> set[str]:
    return {path.relative_to(directory).as_posix() for path in directory.rglob("*")}


_HEX_TAIL = re.compile(r"(?P<prefix>.*?)(?P<hex>[0-9a-f]{6,})")


def id_shape(value: str) -> str:
    """The format of a native id: its prefix and the length of its hex tail
    (``f_2d3af1`` -> ``f_<hex6>``, ``fact:4019d1fcb4d4726e`` -> ``fact:<hex16>``)."""
    match = _HEX_TAIL.fullmatch(value)
    if match is None:
        return re.sub(r"\d", "9", value)
    return f"{match['prefix']}<hex{len(match['hex'])}>"


ID_KEYS = {"id", "fact_id", "finding_id", "case_id"}


def id_shapes(document: Any) -> set[str]:
    """``key=shape`` of every native id in ``document`` (id fields and evidence references)."""
    shapes: set[str] = set()
    if isinstance(document, dict):
        for key, value in document.items():
            if key in ID_KEYS and isinstance(value, str):
                shapes.add(f"{key}={id_shape(value)}")
            elif key == "evidence" and isinstance(value, list):
                shapes |= {f"evidence={id_shape(v)}" for v in value if isinstance(v, str)}
            else:
                shapes |= id_shapes(value)
    elif isinstance(document, list):
        for item in document:
            shapes |= id_shapes(item)
    return shapes


def _recorded_evidence_shapes(case: Case) -> set[str]:
    """The id format of the facts (the evidence) in the replay recording of the action."""
    recording = json.loads(case.recording.read_text(encoding="utf-8"))
    if case.name == "spark":
        facts = recording["output"]["items"]
        return {id_shape(item["id"]) for item in facts}
    facts = recording["case_files"]["facts.json"]["facts"]
    return {id_shape(item["fact_id"]) for item in facts}


def _hashed_evidence_drift(pack: dict[str, Any], result: ExecutionResult) -> list[str]:
    items: dict[str, set[str]] = {}
    for item in pack["files"]:
        items.setdefault(item["path"], set()).add(item["sha256"])
    return sorted(f"{e.id}: {e.location.path if e.location else None} hash {e.hash}"
                  for e in result.evidence
                  if e.hash is not None
                  and (e.location is None or e.hash not in items.get(e.location.path, set())))


def _native_state_left(root: Path) -> list[str]:
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*")
                  if path.name in NATIVE_STATE)


# --- describe -----------------------------------------------------------------------------

def test_describe_is_ready_semver_offline_and_on_the_taxonomy(
        tmp_path: Path, user_config_dir: Path, case: Case, forge: rp.RealForge) -> None:
    root = _workspace(tmp_path, case, user_config_dir, forge.entry())
    record = _record(root, forge.provider_id)
    assert record.state == "ready", record.error
    assert record.routable()
    manifest = record.manifest
    assert manifest is not None and manifest.id == forge.provider_id
    assert parse_semver(manifest.version) is not None, manifest.version
    assert manifest.capabilities
    # No network or credential capability: offline execution, read-only operations only.
    assert manifest.execution.offline and not manifest.execution.requires_network
    assert manifest.execution.local
    assert {c.operation_class for c in manifest.capabilities} == {"read_only"}
    assert {c.state for c in manifest.capabilities} <= {"supported", "heuristic"}
    assert validate_taxonomy(manifest) == ()
    exposed = manifest.capability(case.capability)
    assert exposed is not None and case.action in exposed.actions


def _live_snapshot(case: Case, forge: rp.RealForge, directory: Path) -> dict[str, Any]:
    """The snapshot re-recorded from the live specialist into ``directory`` (never into the
    packaged file): the adapter's own ``record`` module in the specialist interpreter."""
    directory.mkdir(parents=True)
    target = directory / case.snapshot.name
    if case.name == "spark":
        argv = [str(forge.python), "-m", "theforge_sparkforge.record", "--output", str(target)]
    else:
        argv = [str(forge.python), "-m", "theforge_apiforge.record", "--out", str(target),
                "--recorded-at", "live"]
    _run_native(argv, directory)
    data: dict[str, Any] = json.loads(target.read_text(encoding="utf-8"))
    return data


def _surface(snapshot: dict[str, Any]) -> dict[str, Any]:
    """The recorded surface, without the recording metadata (date, provenance)."""
    return {key: value for key, value in snapshot.items()
            if key not in ("recorded_at", "provenance")}


def _surface_diff(recorded: dict[str, Any], live: dict[str, Any]) -> list[str]:
    diff: list[str] = []
    if recorded.get("specialist_version") != live.get("specialist_version"):
        diff.append(f"specialist_version {recorded.get('specialist_version')!r} -> "
                    f"{live.get('specialist_version')!r}")
    if "tools" in recorded or "tools" in live:
        old, new = recorded.get("tools", {}), live.get("tools", {})
    else:
        old = {c["capability_id"]: c for c in recorded.get("capabilities", [])}
        new = {c["capability_id"]: c for c in live.get("capabilities", [])}
    for name in sorted(set(old) | set(new)):
        if name not in new:
            diff.append(f"removed {name}")
        elif name not in old:
            diff.append(f"added {name}: {new[name]}")
        elif old[name] != new[name]:
            diff.append(f"changed {name}: {old[name]} -> {new[name]}")
    return diff


def test_recorded_snapshot_equals_the_live_surface(
        tmp_path: Path, case: Case, forge: rp.RealForge) -> None:
    """Drift: the packaged snapshot describe uses is the live specialist's surface."""
    recorded = json.loads(case.snapshot.read_text(encoding="utf-8"))
    live = _live_snapshot(case, forge, tmp_path / "live")
    diff = _surface_diff(recorded, live)
    assert _surface(recorded) == _surface(live), (
        f"{case.snapshot.name} drifted from the live {case.spec.label} "
        f"(re-record it, see docs/real-providers.md): " + "; ".join(diff))


# --- health -------------------------------------------------------------------------------

def test_health_is_ok_or_degraded_with_reason_and_without_credentials(
        tmp_path: Path, user_config_dir: Path, case: Case, forge: rp.RealForge,
        credentials: dict[str, str]) -> None:
    root = _workspace(tmp_path, case, user_config_dir, forge.entry())
    record = _record(root, forge.provider_id)
    assert record.state == "ready", record.error
    outcome = check_health(record, timeout=HEALTH_TIMEOUT)
    assert outcome.status in ("ok", "degraded"), outcome.error
    # A second, independent probe (for the reason the core drops): its status may differ
    # from the first one (e.g. the API Forge doctor finishing on one side of its time cap).
    report, raw = _raw_health(forge.argv())
    assert report.status in ("ok", "degraded"), report
    if report.status == "degraded":
        assert [c.detail for c in report.checks if not c.ok and c.detail], report
    # The core never hands credentials to a provider: none of the variables set here.
    assert not [name for name in safe_env() if is_credential_name(name)]
    assert not [value for value in credentials.values() if value in raw], raw


# --- execute ------------------------------------------------------------------------------

def test_execute_through_the_core_ends_with_an_intact_contained_result(
        tmp_path: Path, user_config_dir: Path, case: Case, forge: rp.RealForge,
        credentials: dict[str, str]) -> None:
    root = _workspace(tmp_path, case, user_config_dir, forge.entry())
    outcome, store = _ask(root, case)
    assert outcome.status in ("ok", "partial"), outcome.error
    receipt = store.read(outcome.run_id, "receipt")
    assert receipt["status"] == outcome.status and receipt["error"] is None
    assert receipt["provider"]["id"] == forge.provider_id
    result = outcome.result
    assert result is not None and result.evidence, result
    assert not any(note.startswith("no input") for note in result.limitations), result

    # Intact: the persisted result and receipt pass the core's integrity checks.
    record = _record(root, forge.provider_id)
    assert record.manifest is not None
    persisted = from_dict(ExecutionResult, store.read(outcome.run_id, "result"), "$")
    validate_result(persisted, expected=Producer(id=forge.provider_id,
                                                 version=record.manifest.version))
    validate_receipt(from_dict(ExecutionReceipt, receipt, "$"),
                     result_sha256=store.persisted_sha256(outcome.run_id, "result"))
    pack = store.read(outcome.run_id, "context")
    validate_context_pack(from_dict(ContextPack, pack, "$"))

    # Native ids: evidence ids keep the specialist's fact ids (same format as recorded).
    shapes = _recorded_evidence_shapes(case)
    assert {id_shape(e.id) for e in result.evidence} <= shapes, (shapes, result.evidence)
    work = store.work_dir(outcome.run_id)
    if case.name == "api":
        facts = [a.path for a in result.artifacts if PurePosixPath(a.path).name == "facts.json"]
        assert len(facts) == 1, result.artifacts
        native = json.loads((work / facts[0]).read_text(encoding="utf-8"))
        assert {e.id for e in result.evidence} <= {f["fact_id"] for f in native["facts"]}

    # Native state stays in the run: nothing native in the workspace, and the run's work/
    # holds exactly the declared artifacts (and their parent directories).
    assert _native_state_left(root) == []
    paths = {a.path for a in result.artifacts}
    parents = {parent.as_posix() for path in paths for parent in PurePosixPath(path).parents
               if parent.as_posix() != "."}
    assert _left_in(work) == paths | parents

    # Every non-null evidence hash is the sha256 of the ContextPack item of the same path.
    assert [e for e in result.evidence if e.hash is not None], result.evidence
    assert _hashed_evidence_drift(pack, result) == []

    # No credential reached the provider: none of the sentinels is in what it wrote.
    written = json.dumps(store.read(outcome.run_id, "result")) + "".join(
        (work / a.path).read_text(encoding="utf-8", errors="replace")
        for a in result.artifacts)
    assert not [value for value in credentials.values() if value in written]


def _live_spark_output(case: Case, forge: rp.RealForge, tmp_path: Path) -> dict[str, Any]:
    """The live native output of the action, recorded in the replay layout by the adapter's
    execute recorder (on a copy of the example workspace, in a scratch directory)."""
    recording = json.loads(case.recording.read_text(encoding="utf-8"))
    workspace = tmp_path / "spark-ws"
    shutil.copytree(case.workspace, workspace)
    out = tmp_path / "live"
    argv = [str(forge.python), "-m", "theforge_sparkforge.record_execute",
            "--workspace", str(workspace), "--capability", case.capability,
            "--action", case.action, "--out", str(out)]
    argv += [f"--arg={name}={value}" for name, value in recording["arguments"].items()
             if name not in ("detail_level", "limit")]
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    _run_native(argv, scratch)
    live: dict[str, Any] = json.loads((out / case.recording.name).read_text(encoding="utf-8"))
    assert _left_in(scratch) == set()
    return live


def _live_api_case(tmp_path: Path, user_config_dir: Path, case: Case,
                   forge: rp.RealForge) -> dict[str, Any]:
    """The live native case files of the action (the declared artifacts of a core run)."""
    root = _workspace(tmp_path, case, user_config_dir, forge.entry())
    outcome, store = _ask(root, case)
    assert outcome.status in ("ok", "partial"), outcome.error
    assert outcome.result is not None
    work = store.work_dir(outcome.run_id)
    files: dict[str, Any] = {}
    for artifact in outcome.result.artifacts:
        path = PurePosixPath(artifact.path)
        if path.parts[0] == "case" and path.suffix == ".json":
            files[path.relative_to("case").as_posix()] = json.loads(
                (work / artifact.path).read_text(encoding="utf-8"))
    return files


def _top_keys(document: Any) -> list[str]:
    return sorted(document) if isinstance(document, dict) else [type(document).__name__]


def test_live_native_output_has_the_recorded_keys_and_id_formats(
        tmp_path: Path, user_config_dir: Path, case: Case, forge: rp.RealForge) -> None:
    """Execute drift: the live native output of the exercised action has the same top-level
    keys and the same id formats as the replay recording of the same action."""
    recording = json.loads(case.recording.read_text(encoding="utf-8"))
    if case.name == "spark":
        live = _live_spark_output(case, forge, tmp_path)
        pairs = {
            "recording": (recording, live),
            "output": (recording["output"], live["output"]),
            "judge": (recording["judge"], live["judge"]),
            "judge.output": (recording["judge"]["output"], live["judge"]["output"]),
        }
        assert live["tool"] == recording["tool"]
        assert live["arguments"] == recording["arguments"]
    else:
        live_files = _live_api_case(tmp_path, user_config_dir, case, forge)
        recorded_files = recording["case_files"]
        assert sorted(live_files) == sorted(recorded_files)
        pairs = {name: (recorded_files[name], live_files[name]) for name in recorded_files}
    drift = {name: (_top_keys(old), _top_keys(new)) for name, (old, new) in pairs.items()
             if _top_keys(old) != _top_keys(new)}
    assert drift == {}, f"{case.recording.name}: top-level keys drifted {drift}"
    id_drift = {name: (sorted(id_shapes(old)), sorted(id_shapes(new)))
                for name, (old, new) in pairs.items() if id_shapes(old) != id_shapes(new)}
    assert id_drift == {}, f"{case.recording.name}: id formats drifted {id_drift}"


# --- absence and version skew -------------------------------------------------------------

def test_missing_interpreter_is_unreachable_with_spawn_code_and_path(
        tmp_path: Path, user_config_dir: Path, case: Case) -> None:
    missing = tmp_path / "no-such-venv" / ("python.exe" if sys.platform == "win32"
                                           else "python")
    spec = case.spec
    entry = {"id": spec.provider_id, "argv": [str(missing), "-m", spec.adapter_module],
             "trust": "trusted"}
    root = _workspace(tmp_path, case, user_config_dir, entry)
    record = _record(root, spec.provider_id)
    assert record.state == "unreachable" and not record.routable()
    assert record.error is not None
    assert record.error.startswith(f"{Codes.PROTO_SPAWN}: "), record.error
    # The transport names the interpreter it could not start (as a Python literal).
    assert str(missing) in record.error or repr(str(missing)) in record.error


def test_interpreter_without_the_specialist_is_invalid_with_reason(
        tmp_path: Path, user_config_dir: Path, case: Case) -> None:
    """The test's own interpreter has the adapter (development install) but not the
    specialist: describe is refused and the registry keeps the adapter's code and reason."""
    spec = case.spec
    if importlib.util.find_spec(spec.specialist_module.split(".")[0]) is not None:
        pytest.skip(f"{spec.label} is installed in {sys.executable}")
    if importlib.util.find_spec(spec.adapter_module) is not None:
        argv = [sys.executable, "-m", spec.adapter_module]
    else:
        # The scheduled workflow installs the adapters only in the specialist venvs: run the
        # adapter from its source tree (stdlib-only) instead of skipping in required mode.
        src = str(ADAPTERS / case.native / "src")
        argv = [sys.executable, "-c",
                f"import runpy, sys; sys.path.insert(0, {src!r}); "
                f"runpy.run_module({spec.adapter_module!r}, run_name='__main__', "
                f"alter_sys=True)"]
    entry = {"id": spec.provider_id, "argv": argv, "trust": "trusted"}
    root = _workspace(tmp_path, case, user_config_dir, entry)
    record = _record(root, spec.provider_id)
    assert record.state == "invalid" and record.manifest is None and not record.routable()
    assert record.error is not None
    assert record.error.startswith(f"describe refused {case.unavailable_code}: "), record.error
    reason = record.error.split(": ", 1)[1]
    assert sys.executable in reason
    assert f"{sys.version_info.major}.{sys.version_info.minor}" in reason


def test_assumed_version_outside_the_window_is_degraded_with_version_and_window(
        tmp_path: Path, user_config_dir: Path, case: Case, forge: rp.RealForge) -> None:
    options = ("--assume-specialist-version", "9.9.9")
    root = _workspace(tmp_path, case, user_config_dir, forge.entry(*options))
    record = _record(root, forge.provider_id)
    assert record.state == "ready", record.error  # describe does not depend on the version
    outcome = check_health(record, timeout=HEALTH_TIMEOUT)
    assert outcome.status == "degraded" and outcome.error is None
    report, _ = _raw_health(forge.argv(*options))
    assert report.status == "degraded"
    failing = [check.detail or "" for check in report.checks if not check.ok]
    assert any(f"found 9.9.9, supported {case.supported}" in detail for detail in failing), \
        report
