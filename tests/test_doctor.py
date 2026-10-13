import os
from pathlib import Path

from helpers import SPARK_ENTRY, make_workspace, write_providers
from theforge.environment import detect_host, run_doctor
from theforge.registry import Registry, user_cache_dir


def test_detect_host() -> None:
    assert detect_host({"CLAUDECODE": "1"}) == "claude-code"
    assert detect_host({"CODEX_HOME": "x"}) == "codex"
    assert detect_host({"CI": "true"}) == "ci"
    assert detect_host({}) == "terminal"


def test_doctor_uninitialized(tmp_path: Path) -> None:
    report = run_doctor(tmp_path, Registry(None), env={})
    checks = {c["name"]: c for c in report["checks"]}
    assert checks["python"]["status"] == "ok"
    assert checks["workspace"]["status"] == "warn"
    assert checks["provider:echo-forge"]["status"] == "ok"
    assert checks["host"]["detail"] == "terminal"
    assert report["healthy"] is True


def test_doctor_missing_provider_warns(tmp_path: Path) -> None:
    make_workspace(
        tmp_path,
        [{"id": "ghost-forge", "argv": ["definitely-not-a-real-forge-binary"], "trust": "local"}],
    )
    report = run_doctor(tmp_path, Registry(tmp_path / ".forge"), env={})
    checks = {c["name"]: c for c in report["checks"]}
    assert checks["workspace"]["status"] == "ok"
    assert checks["provider:ghost-forge"]["status"] == "warn"
    assert "FORGE-PROVIDER-NOT-READY" in checks["provider:ghost-forge"]["detail"]
    assert report["healthy"] is True


def test_doctor_is_read_only(tmp_path: Path) -> None:
    forge = make_workspace(tmp_path, [SPARK_ENTRY])
    report = run_doctor(tmp_path, Registry(forge), env={})
    checks = {c["name"]: c for c in report["checks"]}
    assert checks["provider:fixture-spark"]["status"] == "ok"
    assert not (forge / "registry").exists()
    assert not list((user_cache_dir() / "registry").glob("*.json"))


def test_doctor_reports_registry_errors(tmp_path: Path) -> None:
    forge = make_workspace(tmp_path, [])
    config = Path(os.environ["THEFORGE_CONFIG_DIR"])
    config.mkdir(parents=True, exist_ok=True)
    (config / "providers.toml").write_text("[[providers]\n", encoding="utf-8")
    report = run_doctor(tmp_path, Registry(forge), env={})
    checks = {c["name"]: c for c in report["checks"]}
    assert checks["providers"]["status"] == "fail"
    assert report["healthy"] is False


def test_doctor_surfaces_registry_warnings(tmp_path: Path) -> None:
    forge = make_workspace(tmp_path, [])
    write_providers(forge, [{**SPARK_ENTRY, "trust": "trusted"}], scope="project")
    report = run_doctor(tmp_path, Registry(forge), env={})
    warns = [c for c in report["checks"] if c["name"] == "registry"]
    assert warns and warns[0]["status"] == "warn"
    assert "fixture-spark" in warns[0]["detail"]


def test_doctor_validates_account_environment_when_published(tmp_path: Path) -> None:
    install = tmp_path / "install"
    venv = install / ".venv"
    checkout = tmp_path / "checkout"
    install.mkdir()
    venv.mkdir()
    checkout.mkdir()
    python = venv / "python.exe"
    cli = venv / "sparkforge-aws.exe"
    python.write_text("", encoding="utf-8")
    cli.write_text("", encoding="utf-8")
    env = {
        "SPARK_FORGE_AWS_HOME": str(checkout),
        "SPARK_FORGE_AWS_INSTALL_ROOT": str(install),
        "SPARK_FORGE_AWS_VENV": str(venv),
        "SPARK_FORGE_AWS_PYTHON": str(python),
        "SPARK_FORGE_AWS_CLI": str(cli),
    }

    report = run_doctor(tmp_path, Registry(None), env=env)

    checks = {c["name"]: c for c in report["checks"]}
    assert checks["account-environment"]["status"] == "ok"
    assert report["account_environment"][0]["state"] == "ready"


def test_doctor_marks_invalid_account_environment_as_failure(tmp_path: Path) -> None:
    report = run_doctor(
        tmp_path,
        Registry(None),
        env={"SPARK_FORGE_AWS_HOME": str(tmp_path / "gone")},
    )

    checks = {c["name"]: c for c in report["checks"]}
    assert checks["account-environment"]["status"] == "fail"
    assert report["healthy"] is False


def test_doctor_ignores_unrelated_tool_environment_variables(tmp_path: Path) -> None:
    report = run_doctor(
        tmp_path,
        Registry(None),
        env={"M2_HOME": str(tmp_path), "PYENV_HOME": str(tmp_path / "missing")},
    )

    assert report["account_environment"] == []
    assert report["healthy"] is True
