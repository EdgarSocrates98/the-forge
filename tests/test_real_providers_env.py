"""Environment contract of the real-Forge integration tests (real-provider-integration 7.1).

``tests/real_providers.py`` reads ``THEFORGE_REAL_{SPARKFORGE,APIFORGE,DOCTORDATA,DOCTORAPI}_
PYTHON`` and
``THEFORGE_REAL_PROVIDERS_REQUIRED`` and checks, in order: variable set, file exists,
``import <adapter>, <specialist>`` exits 0. A missing prerequisite skips with an explicit reason,
or fails when the run declares the real Forges required. Everything here runs on a simulated
environment and an injected import probe: no subprocess, no real Forge.
"""

import os
import subprocess
import tomllib
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

import real_providers as rp
from theforge.security.env import safe_env

ALL_VARS = (rp.SPARK_PYTHON_VAR, rp.API_PYTHON_VAR, rp.DOCTORDATA_PYTHON_VAR,
            rp.DOCTORAPI_PYTHON_VAR, rp.REQUIRED_VAR)


def _ok_probe(python: Path, modules: Sequence[str]) -> str | None:
    return None


def _failing_probe(python: Path, modules: Sequence[str]) -> str | None:
    return f"`import {', '.join(modules)}` exited 1: ModuleNotFoundError: No module named 'x'"


def _never_probe(python: Path, modules: Sequence[str]) -> str | None:
    raise AssertionError("the import probe must not run before the file check passes")


@pytest.fixture
def interpreter(tmp_path: Path) -> Path:
    path = tmp_path / "venv" / "Scripts" / "python.exe"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"")
    return path


# --- the contract itself ------------------------------------------------------------------

def test_contract_variable_names() -> None:
    assert rp.SPARK_PYTHON_VAR == "THEFORGE_REAL_SPARKFORGE_PYTHON"
    assert rp.API_PYTHON_VAR == "THEFORGE_REAL_APIFORGE_PYTHON"
    assert rp.DOCTORDATA_PYTHON_VAR == "THEFORGE_REAL_DOCTORDATA_PYTHON"
    assert rp.DOCTORAPI_PYTHON_VAR == "THEFORGE_REAL_DOCTORAPI_PYTHON"
    assert rp.REQUIRED_VAR == "THEFORGE_REAL_PROVIDERS_REQUIRED"
    assert rp.IMPORT_TIMEOUT == 60.0
    assert {name: (spec.provider_id, spec.variable, spec.adapter_module, spec.specialist_module)
            for name, spec in rp.FORGES.items()} == {
        "spark": ("spark-forge", rp.SPARK_PYTHON_VAR, "theforge_sparkforge",
                  "sparkforge_aws.adapters.tools"),
        "api": ("api-forge", rp.API_PYTHON_VAR, "theforge_apiforge", "apiforge"),
        "doctordata": ("forge-doctor-data", rp.DOCTORDATA_PYTHON_VAR,
                       "theforge_doctordata", "forge_doctor_data"),
        "doctorapi": ("forge-doctor-api", rp.DOCTORAPI_PYTHON_VAR,
                      "theforge_doctorapi", "forge_doctor_api"),
    }


def test_documented_in_real_providers_doc() -> None:
    doc = (Path(__file__).parents[1] / "docs" / "real-providers.md").read_text(encoding="utf-8")
    for variable in ALL_VARS:
        assert f"`{variable}`" in doc
    assert rp.missing_variable_reason("api") in doc


# --- check order and reasons --------------------------------------------------------------

@pytest.mark.parametrize("value", [None, "", "   "])
def test_missing_variable(value: str | None) -> None:
    environ = {} if value is None else {rp.API_PYTHON_VAR: value}
    with pytest.raises(rp.ForgeUnavailable) as info:
        rp.check_forge("api", environ, probe=_never_probe)
    assert info.value.reason == (
        "THEFORGE_REAL_APIFORGE_PYTHON not set (API Forge needs Python 3.12; "
        "see docs/real-providers.md)")


def test_missing_variable_spark_reason() -> None:
    with pytest.raises(rp.ForgeUnavailable) as info:
        rp.check_forge("spark", {}, probe=_never_probe)
    assert info.value.reason.startswith("THEFORGE_REAL_SPARKFORGE_PYTHON not set (")
    assert "docs/real-providers.md" in info.value.reason


def test_nonexistent_file(tmp_path: Path) -> None:
    missing = tmp_path / "nope" / "python.exe"
    environ = {rp.SPARK_PYTHON_VAR: str(missing)}
    with pytest.raises(rp.ForgeUnavailable) as info:
        rp.check_forge("spark", environ, probe=_never_probe)
    assert info.value.reason.startswith("THEFORGE_REAL_SPARKFORGE_PYTHON=")
    assert str(missing) in info.value.reason and "does not exist" in info.value.reason


def test_directory_is_not_an_interpreter(tmp_path: Path) -> None:
    (tmp_path / "python3").mkdir()
    environ = {rp.SPARK_PYTHON_VAR: str(tmp_path / "python3")}
    with pytest.raises(rp.ForgeUnavailable) as info:
        rp.check_forge("spark", environ, probe=_never_probe)
    assert "is not a file" in info.value.reason


def test_relative_path_rejected(interpreter: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(interpreter.parent)
    environ = {rp.SPARK_PYTHON_VAR: interpreter.name}
    with pytest.raises(rp.ForgeUnavailable) as info:
        rp.check_forge("spark", environ, probe=_never_probe)
    assert "absolute path" in info.value.reason


@pytest.mark.parametrize("name", ["sh", "python.bat", "pythonw.exe", "python2", "evil.exe"])
def test_non_python_file_rejected(tmp_path: Path, name: str) -> None:
    path = tmp_path / name
    path.write_bytes(b"")
    with pytest.raises(rp.ForgeUnavailable) as info:
        rp.check_forge("spark", {rp.SPARK_PYTHON_VAR: str(path)}, probe=_never_probe)
    assert "does not name a Python interpreter" in info.value.reason


@pytest.mark.parametrize("name", ["python", "python3", "python3.12", "Python.exe",
                                  "python3.11.exe"])
def test_python_names_accepted(tmp_path: Path, name: str) -> None:
    path = tmp_path / name
    path.write_bytes(b"")
    assert rp.check_forge("spark", {rp.SPARK_PYTHON_VAR: str(path)}, probe=_ok_probe).python == path


def test_path_normalized_once(interpreter: Path) -> None:
    raw = str(interpreter.parent / ".." / interpreter.parent.name / interpreter.name)
    forge = rp.check_forge("spark", {rp.SPARK_PYTHON_VAR: raw}, probe=_ok_probe)
    assert forge.python == interpreter and ".." not in forge.python.parts


def test_import_failure(interpreter: Path) -> None:
    seen: list[tuple[Path, tuple[str, ...]]] = []

    def probe(python: Path, modules: Sequence[str]) -> str | None:
        seen.append((python, tuple(modules)))
        return _failing_probe(python, modules)

    with pytest.raises(rp.ForgeUnavailable) as info:
        rp.check_forge("api", {rp.API_PYTHON_VAR: str(interpreter)}, probe=probe)
    assert seen == [(interpreter, ("theforge_apiforge", "apiforge"))]
    reason = info.value.reason
    assert reason.startswith(f"API Forge not importable with {interpreter}: ")
    assert "ModuleNotFoundError" in reason and rp.API_PYTHON_VAR in reason


def test_all_prerequisites_met(interpreter: Path) -> None:
    forge = rp.check_forge("spark", {rp.SPARK_PYTHON_VAR: str(interpreter)}, probe=_ok_probe)
    assert forge == rp.RealForge("spark-forge", interpreter, "theforge_sparkforge",
                                 "sparkforge_aws.adapters.tools")
    assert forge.argv() == [str(interpreter), "-m", "theforge_sparkforge"]
    assert forge.argv("--assume-specialist-version", "9.9.9")[-2:] == [
        "--assume-specialist-version", "9.9.9"]


def test_unknown_forge() -> None:
    with pytest.raises(KeyError):
        rp.check_forge("glue", {}, probe=_never_probe)


# --- skip vs fail -------------------------------------------------------------------------

@pytest.mark.parametrize("required", [None, "", "0", "true", "yes"])
def test_skips_with_reason_when_not_required(required: str | None) -> None:
    environ = {} if required is None else {rp.REQUIRED_VAR: required}
    with pytest.raises(pytest.skip.Exception) as info:
        rp.require_forge("api", environ, probe=_never_probe)
    assert str(info.value.msg) == rp.missing_variable_reason("api")


def test_fails_with_reason_when_required(interpreter: Path) -> None:
    cases: list[tuple[dict[str, str], str]] = [
        ({}, "not set"),
        ({rp.API_PYTHON_VAR: str(interpreter.parent / "missing" / "python.exe")}, "does not exist"),
        ({rp.API_PYTHON_VAR: str(interpreter)}, "not importable"),
    ]
    for environ, fragment in cases:
        environ[rp.REQUIRED_VAR] = "1"
        with pytest.raises(pytest.fail.Exception) as info:
            rp.require_forge("api", environ, probe=_failing_probe)
        assert fragment in str(info.value.msg)
        assert str(info.value.msg).startswith(f"{rp.REQUIRED_VAR}=1: ")


def test_required_mode_passes_when_ready(interpreter: Path) -> None:
    environ = {rp.SPARK_PYTHON_VAR: str(interpreter), rp.REQUIRED_VAR: "1"}
    assert rp.require_forge("spark", environ, probe=_ok_probe).python == interpreter


def test_reads_process_environment_by_default(
        interpreter: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in ALL_VARS:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv(rp.SPARK_PYTHON_VAR, str(interpreter))
    assert rp.require_forge("spark", probe=_ok_probe).python == interpreter
    with pytest.raises(pytest.skip.Exception):
        rp.require_forge("api", probe=_ok_probe)
    monkeypatch.setenv(rp.REQUIRED_VAR, "1")
    with pytest.raises(pytest.fail.Exception):
        rp.require_forge("api", probe=_ok_probe)


# --- the default import probe -------------------------------------------------------------

def _fake_run(result: Any) -> Any:
    calls: list[dict[str, Any]] = []

    def run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append({"argv": argv, **kwargs})
        if isinstance(result, BaseException):
            raise result
        return subprocess.CompletedProcess(argv, result[0], "", result[1])

    run.calls = calls  # type: ignore[attr-defined]
    return run


def test_probe_ok_runs_import_without_credentials(
        interpreter: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "s3cr3t")
    monkeypatch.setenv(rp.SPARK_PYTHON_VAR, str(interpreter))
    run = _fake_run((0, ""))
    assert rp.probe_imports(interpreter, ["theforge_sparkforge", "sparkforge.adapters.tools"],
                            run=run) is None
    (call,) = run.calls
    assert call["argv"] == [str(interpreter), "-c",
                            "import theforge_sparkforge, sparkforge.adapters.tools"]
    assert call["timeout"] == rp.IMPORT_TIMEOUT
    assert "AWS_SECRET_ACCESS_KEY" not in call["env"]
    assert not any(key.startswith("THEFORGE_REAL_") for key in call["env"])


def test_probe_reports_last_stderr_line(interpreter: Path) -> None:
    stderr = ("Traceback (most recent call last):\n  ...\n"
              "ModuleNotFoundError: No module named 'apiforge'\n")
    reason = rp.probe_imports(interpreter, ["theforge_apiforge", "apiforge"],
                              run=_fake_run((1, stderr)))
    assert reason == ("`import theforge_apiforge, apiforge` exited 1: "
                      "ModuleNotFoundError: No module named 'apiforge'")


def test_probe_timeout(interpreter: Path) -> None:
    reason = rp.probe_imports(interpreter, ["apiforge"],
                              run=_fake_run(subprocess.TimeoutExpired("python", 60)))
    assert reason == "`import apiforge` did not finish in 60 s"


def test_probe_spawn_error(interpreter: Path) -> None:
    reason = rp.probe_imports(interpreter, ["apiforge"],
                              run=_fake_run(PermissionError(13, "Access is denied")))
    assert reason is not None and reason.startswith("`import apiforge` could not start: ")
    assert "Access is denied" in reason


# --- registration in the isolated user providers.toml -------------------------------------

def test_register_writes_isolated_user_providers_toml(
        interpreter: Path, user_config_dir: Path) -> None:
    spark = rp.RealForge("spark-forge", interpreter, "theforge_sparkforge",
                         "sparkforge_aws.adapters.tools")
    api = rp.RealForge("api-forge", interpreter, "theforge_apiforge", "apiforge")
    entries = rp.register(user_config_dir, spark.entry(),
                          api.entry("--assume-specialist-version", "9.9.9"))

    path = user_config_dir / "providers.toml"
    text = path.read_text(encoding="utf-8")
    providers = tomllib.loads(text)["providers"]
    assert providers == entries
    assert providers == [
        {"id": "spark-forge", "argv": [str(interpreter), "-m", "theforge_sparkforge"],
         "trust": "trusted"},
        {"id": "api-forge", "argv": [str(interpreter), "-m", "theforge_apiforge",
                                     "--assume-specialist-version", "9.9.9"],
         "trust": "trusted"},
    ]
    # Nothing of the contract is handed to the provider: no env table, no variable names.
    assert all(set(entry) == {"id", "argv", "trust"} for entry in providers)
    assert "THEFORGE_REAL_" not in text


def test_register_trust_override(interpreter: Path, user_config_dir: Path) -> None:
    forge = rp.RealForge("api-forge", interpreter, "theforge_apiforge", "apiforge")
    (entry,) = rp.register(user_config_dir, forge.entry(trust="local"))
    assert entry["trust"] == "local"


def test_contract_variables_never_reach_provider_env() -> None:
    source = {**{variable: "x" for variable in ALL_VARS}, "PATH": os.environ.get("PATH", "")}
    env = safe_env(source)
    assert not any(variable in env for variable in ALL_VARS)
