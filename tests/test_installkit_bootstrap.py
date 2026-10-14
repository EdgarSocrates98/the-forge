"""Regression tests for the canonical installkit bootstrap
(``scripts/installkit/forge_bootstrap.py``) interpreter specifier checks.

Two-component bounds like ``>=3.12`` previously collapsed to ``(0, 0, 0)``
because ``_semver_tuple`` only parsed three-part versions — making every
interpreter satisfy any floor and no interpreter satisfy any ceiling.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP_PATH = ROOT / "scripts" / "installkit" / "forge_bootstrap.py"

spec = importlib.util.spec_from_file_location("forge_bootstrap", BOOTSTRAP_PATH)
fb = importlib.util.module_from_spec(spec)
sys.modules["forge_bootstrap"] = fb
spec.loader.exec_module(fb)


def test_semver_tuple_pads_two_component():
    assert fb._semver_tuple("3.12") == (3, 12, 0)
    assert fb._semver_tuple("3") == (3, 0, 0)
    assert fb._semver_tuple("3.12.5") == (3, 12, 5)


def test_semver_tuple_unparseable_falls_back_zero():
    assert fb._semver_tuple("abc") == (0, 0, 0)


def test_satisfies_floor_accepts_newer_python():
    # 3.13/3.14+ must not be refused by an open floor (>=3.12).
    assert fb._satisfies("3.14.6", ">=3.12")
    assert fb._satisfies("3.13.1", ">=3.12")
    assert fb._satisfies("3.12.0", ">=3.12")


def test_satisfies_floor_refuses_older_python():
    assert not fb._satisfies("3.11.9", ">=3.12")
    assert not fb._satisfies("3.9.9", ">=3.10")


def test_satisfies_ceiling_still_works():
    assert fb._satisfies("3.14.6", ">=3.12,<3.15")
    assert not fb._satisfies("3.15.0", ">=3.12,<3.15")
    # the historical api-forge pin is only satisfiable by 3.12.x itself
    assert fb._satisfies("3.12.13", ">=3.12,<3.13")
    assert not fb._satisfies("3.13.0", ">=3.12,<3.13")


def test_environment_contract_is_account_scoped_and_shell_safe(tmp_path):
    cfg = {"forge_id": "spark-forge-aws", "cli": "sparkforge-aws"}
    venv = tmp_path / "install" / ".venv"
    contract = fb.environment_contract(cfg, tmp_path / "checkout", tmp_path / "install", venv, None)

    assert contract["schema"] == "forge/InstallEnvironment/v1"
    assert contract["scope"] == "user"
    assert contract["prefix"] == "SPARK_FORGE_AWS"
    assert contract["variables"]["SPARK_FORGE_AWS_HOME"].endswith("checkout")
    venv_value = contract["variables"]["SPARK_FORGE_AWS_VENV"].replace("\\", "/")
    cli_value = contract["variables"]["SPARK_FORGE_AWS_CLI"].replace("\\", "/")
    assert venv_value.endswith("install/.venv")
    assert cli_value.endswith(
        "install/.venv/Scripts/sparkforge-aws.exe"
    ) or cli_value.endswith(
        "install/.venv/bin/sparkforge-aws"
    )


def test_env_prefix_normalizes_hyphenated_forge_ids():
    assert fb.env_prefix("the-forge") == "THE_FORGE"
    assert fb.env_prefix("forge.doctor-api") == "FORGE_DOCTOR_API"


def test_posix_environment_file_is_idempotent(tmp_path, monkeypatch):
    env_file = tmp_path / "config" / "forjas" / "env.sh"
    rc_file = tmp_path / ".profile"
    monkeypatch.setattr(fb, "_posix_env_paths", lambda: (env_file, rc_file))
    values = {"SPARK_FORGE_AWS_HOME": str(tmp_path / "checkout")}

    fb._persist_posix(values, None)
    fb._persist_posix(values, None)

    rendered = env_file.read_text(encoding="utf-8")
    assert rendered.count("# >>> forjas account environment >>>") == 1
    assert rendered.count("SPARK_FORGE_AWS_HOME") == 1
    assert rc_file.read_text(encoding="utf-8").count("forjas-account-environment") == 1


def test_detects_git_bash_native_windows(monkeypatch):
    monkeypatch.setattr(fb.os, "name", "nt")
    monkeypatch.setenv("MSYSTEM", "UCRT64")
    monkeypatch.delenv("OSTYPE", raising=False)
    assert fb._is_git_bash()


def test_git_bash_persistence_writes_registry_and_shell_init(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(fb.os, "name", "nt")
    monkeypatch.setattr(fb, "_is_git_bash", lambda: True)
    monkeypatch.setattr(
        fb,
        "_persist_windows",
        lambda values, aliases, shim: calls.append(("windows", values, aliases, shim)),
    )
    monkeypatch.setattr(
        fb,
        "_persist_posix",
        lambda values, shim, shell_shim=None: calls.append(
            ("git-bash", values, shim, shell_shim)
        ) or str(tmp_path / "env.sh"),
    )
    env = {
        "variables": {"FORGE_TEST_HOME": str(tmp_path)},
        "windows_aliases": {"FORGE-TEST-HOME": str(tmp_path)},
    }

    out = fb.persist_environment(env, tmp_path / "bin" / "forge-test", lambda _: None)

    assert [call[0] for call in calls] == ["windows", "git-bash"]
    assert out["persistence"] == "HKCU\\Environment + Git Bash shell-init"
    assert out["shell"] == "git-bash"
    assert out["shell_init"].endswith("env.sh")


def test_registry_has_value_uses_winreg_function(monkeypatch):
    calls = []

    def query_value(key, name):
        calls.append((key, name))
        return "value", 1

    monkeypatch.setitem(sys.modules, "winreg", types.SimpleNamespace(QueryValueEx=query_value))
    key = object()
    assert fb._registry_has_value(key, "Path")
    assert calls == [(key, "Path")]

    def missing(_key, _name):
        raise FileNotFoundError

    monkeypatch.setitem(sys.modules, "winreg", types.SimpleNamespace(QueryValueEx=missing))
    assert not fb._registry_has_value(key, "Missing")
