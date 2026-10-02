from pathlib import Path

from helpers import make_workspace

from theforge.environment import detect_host, run_doctor
from theforge.registry import Registry


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
    make_workspace(tmp_path, [{"id": "ghost-forge",
                               "argv": ["definitely-not-a-real-forge-binary"],
                               "trust": "local"}])
    report = run_doctor(tmp_path, Registry(tmp_path / ".forge"), env={})
    checks = {c["name"]: c for c in report["checks"]}
    assert checks["workspace"]["status"] == "ok"
    assert checks["provider:ghost-forge"]["status"] == "warn"
    assert "FORGE-PROVIDER-NOT-READY" in checks["provider:ghost-forge"]["detail"]
    assert report["healthy"] is True
