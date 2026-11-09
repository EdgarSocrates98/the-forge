"""Build and install the Python Forge wheels in isolated environments.

This is a distribution gate, not a replacement for each project's test suite.
Every project is built from its checkout, installed into a fresh virtualenv,
and exercised through its published CLI entry point without requiring flags.
The runner is intentionally dependency-light and works on Windows and POSIX
hosts as long as ``uv`` is available on PATH.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent

PROJECTS: tuple[tuple[str, str], ...] = (
    ("api-forge", "apiforge"),
    ("code-atlas-forge", "code-atlas"),
    ("data-sentinel-forge", "data-sentinel"),
    ("forge-agent-bridge", "forge-bridge"),
    ("forge-doctor-api", "forge-doctor-api"),
    ("forge-doctor-data", "forge-doctor-data"),
    ("forge-lens", "forge-lens"),
    ("platform-forge", "platformforge"),
    ("product-forge", "productforge"),
    ("spark-forge-aws", "sparkforge-aws"),
    ("spark-forge-azure", "sparkforge-azure"),
    ("the-forge", "theforge"),
)


def _run(command: list[str], *, cwd: Path, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def _tail(result: subprocess.CompletedProcess[str]) -> str:
    output = (result.stdout + "\n" + result.stderr).strip()
    return output[-2000:]


def _python_path(venv: Path) -> Path:
    relative = Path("Scripts") / "python.exe" if os.name == "nt" else Path("bin") / "python"
    return venv / relative


def _entrypoint(venv: Path, cli: str) -> Path:
    suffix = ".exe" if os.name == "nt" else ""
    directory = "Scripts" if os.name == "nt" else "bin"
    return venv / directory / f"{cli}{suffix}"


def _project_result(repo: str, cli: str) -> dict[str, Any]:
    return {
        "repo": repo,
        "cli": cli,
        "build": "NOT_RUN",
        "install": "NOT_RUN",
        "cli_help": "NOT_RUN",
        "wheel": None,
        "error": None,
    }


def run(workspace: Path, work_root: Path) -> dict[str, Any]:
    if shutil.which("uv") is None:
        raise RuntimeError("uv is required on PATH")

    results: list[dict[str, Any]] = []
    for repo_name, cli in PROJECTS:
        repo = workspace / repo_name
        result = _project_result(repo_name, cli)
        results.append(result)
        if not repo.is_dir():
            result["error"] = "repository missing"
            continue

        output_dir = work_root / "wheels" / repo_name
        venv = work_root / "venvs" / repo_name
        output_dir.mkdir(parents=True, exist_ok=True)
        build = _run(
            ["uv", "build", "--wheel", "--sdist", "--out-dir", str(output_dir)],
            cwd=repo,
        )
        if build.returncode:
            result["build"] = "FAIL"
            result["error"] = f"wheel build failed: {_tail(build)}"
            continue
        result["build"] = "PASS"

        wheels = sorted(output_dir.glob("*.whl"))
        if not wheels:
            result["error"] = "wheel missing after successful build"
            continue
        wheel = wheels[0]
        result["wheel"] = wheel.name

        venv_result = _run(["uv", "venv", str(venv)], cwd=workspace)
        if venv_result.returncode:
            result["error"] = f"venv creation failed: {_tail(venv_result)}"
            continue
        python = _python_path(venv)
        install = _run(["uv", "pip", "install", "--python", str(python), str(wheel)], cwd=workspace)
        if install.returncode:
            result["install"] = "FAIL"
            result["error"] = f"wheel install failed: {_tail(install)}"
            continue
        result["install"] = "PASS"

        entrypoint = _entrypoint(venv, cli)
        if not entrypoint.is_file():
            result["cli_help"] = "FAIL"
            result["error"] = f"published CLI entry point missing: {entrypoint.name}"
            continue
        help_result = _run([str(entrypoint), "--help"], cwd=workspace)
        result["cli_help"] = "PASS" if help_result.returncode == 0 else "FAIL"
        if help_result.returncode:
            result["error"] = f"CLI --help failed: {_tail(help_result)}"

    return {
        "schema": "forge/installed-wheel-matrix/v1",
        "platform": platform.platform(),
        "python": platform.python_version(),
        "project_count": len(results),
        "projects": results,
        "status": "PASS"
        if all(
            row["build"] == "PASS" and row["install"] == "PASS" and row["cli_help"] == "PASS"
            for row in results
        )
        else "FAIL",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repos-root", type=Path, default=WORKSPACE)
    parser.add_argument("--work-root", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    if args.work_root:
        args.work_root.mkdir(parents=True, exist_ok=True)
        receipt = run(args.repos_root.resolve(), args.work_root.resolve())
    else:
        with tempfile.TemporaryDirectory(prefix="forge-wheel-matrix-") as directory:
            receipt = run(args.repos_root.resolve(), Path(directory))

    text = json.dumps(receipt, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
