"""``theforge install`` through the real CLI in a subprocess (ADR-0058)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def cli(root: Path, *args: str, home: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    if home is not None:
        env["FORGE_HOME_OVERRIDE"] = str(home)
    return subprocess.run(
        [sys.executable, "-m", "theforge", *args, "--root", str(root)],
        capture_output=True, text=True, encoding="utf-8",
        timeout=120, env=env,
    )


@pytest.fixture()
def target(tmp_path: Path) -> Path:
    d = tmp_path / "consumer"
    d.mkdir()
    return d


def test_install_apply_help(target: Path) -> None:
    proc = cli(target, "install", "apply", "--help")
    assert proc.returncode == 0
    assert "--scope" in proc.stdout and "--profile" in proc.stdout


def test_apply_without_yes_refuses(target: Path) -> None:
    proc = cli(target, "install", "apply", "--json")
    assert proc.returncode == 4
    doc = json.loads(proc.stdout)
    assert doc["error"]["kind"] == "FORGE-INSTALL-PLAN-NOT-APPROVED"


def test_apply_status_uninstall_roundtrip(target: Path) -> None:
    proc = cli(target, "install", "apply", "--yes")
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "completed" in proc.stdout

    proc = cli(target, "install", "status", "--json")
    assert json.loads(proc.stdout)["status"] == "healthy"

    proc = cli(target, "install", "doctor", "--json")
    assert json.loads(proc.stdout)["schema"] == "forge/InstallationHealth/v1"

    proc = cli(target, "install", "uninstall")
    assert proc.returncode == 0
    assert not (target / ".agents" / "skills").exists()


def test_installations_list(target: Path, tmp_path: Path) -> None:
    proc = cli(target, "installations", "list", "--json", home=tmp_path / "h")
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["installations"] == []


def test_auto_dry_run(target: Path, tmp_path: Path) -> None:
    home = tmp_path / "home"
    (home / ".forge" / "installations").mkdir(parents=True)
    (home / ".forge" / "installations" / "the-forge.json").write_text(
        '{"forge_id": "the-forge", "cli": {"name": "theforge"}}', "utf-8")
    proc = cli(target, "install", "auto", "--dry-run", home=home)
    assert proc.returncode == 0
    assert "planned" in proc.stdout


def test_mcp_verify_not_applicable(target: Path) -> None:
    proc = cli(target, "install", "mcp-verify", "--json")
    doc = json.loads(proc.stdout)
    assert doc["status"] in ("NOT_APPLICABLE", "UNVERIFIED")
