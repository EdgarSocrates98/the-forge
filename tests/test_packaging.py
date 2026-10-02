import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).parents[1]


def test_zero_runtime_dependencies() -> None:
    data = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"].get("dependencies", []) == []


@pytest.mark.slow
def test_fresh_install(tmp_path: Path) -> None:
    venv = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    bin_dir = venv / ("Scripts" if os.name == "nt" else "bin")
    python = bin_dir / ("python.exe" if os.name == "nt" else "python")
    subprocess.run([str(python), "-m", "pip", "install", "--quiet", str(REPO)], check=True)
    suffix = ".exe" if os.name == "nt" else ""
    assert (bin_dir / f"forge{suffix}").exists()
    workspace = tmp_path / "ws"
    workspace.mkdir()
    out = subprocess.run([str(bin_dir / f"theforge{suffix}"), "doctor", "--json",
                          "--root", str(workspace)], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    checks = {c["name"]: c for c in json.loads(out.stdout)["checks"]}
    assert checks["provider:echo-forge"]["status"] == "ok"
