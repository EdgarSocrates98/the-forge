#!/usr/bin/env python3
"""Exercise every first-party install.ps1/install.sh in safe dry-run mode."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPOSITORIES = (
    "the-forge",
    "spark-forge-aws",
    "spark-forge-azure",
    "api-forge",
    "platform-forge",
    "forge-doctor-api",
    "forge-doctor-data",
)


def args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worktree-root", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, default=Path("audit/artifacts/installers"))
    parser.add_argument("--output", type=Path, default=Path("audit/reports/installer-matrix.json"))
    parser.add_argument("--timeout", type=float, default=120.0)
    return parser.parse_args()


def win_path(path: Path) -> str:
    return str(path.resolve())


def bash_path(path: Path) -> str:
    value = win_path(path).replace("\\", "/")
    if len(value) >= 2 and value[1] == ":":
        value = "/" + value[0].lower() + value[2:]
    return value


def git_bash() -> str | None:
    candidates = [
        os.environ.get("GIT_BASH"),
        r"C:\Program Files\Git\bin\bash.exe",
        shutil.which("bash.exe"),
    ]
    for item in candidates:
        if item and Path(item).is_file() and "system32" not in item.lower():
            return item
    return None


def native_bash() -> str | None:
    if os.name != "posix":
        return None
    return shutil.which("bash")


def run_case(
    *,
    repo: str,
    shell: str,
    script: Path,
    command: list[str] | None,
    target: Path,
    artifact_dir: Path,
    timeout: float,
) -> dict[str, Any]:
    case_id = f"{repo}-{shell}"
    case_dir = artifact_dir / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = case_dir / "stdout.txt"
    stderr_path = case_dir / "stderr.txt"
    started = time.perf_counter()
    result: dict[str, Any] = {
        "id": case_id,
        "repo": repo,
        "shell": shell,
        "script": str(script),
        "status": "BLOCKED",
        "command": command,
        "cwd": str(script.parent),
        "exit_code": None,
        "duration_seconds": None,
        "stdout_artifact": str(stdout_path),
        "stderr_artifact": str(stderr_path),
        "reason": None,
    }
    if command is None:
        result["reason"] = "runtime unavailable"
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.write_text("runtime unavailable\n", encoding="utf-8")
        return result
    env = os.environ.copy()
    env["NO_COLOR"] = "1"
    env["PYTHONNOUSERSITE"] = "1"
    try:
        completed = subprocess.run(
            command,
            cwd=script.parent,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        result["exit_code"] = completed.returncode
        result["status"] = "PASS" if completed.returncode == 0 else "FAIL"
        stdout_path.write_text(completed.stdout, encoding="utf-8")
        stderr_path.write_text(completed.stderr, encoding="utf-8")
    except subprocess.TimeoutExpired as exc:
        result["status"] = "BLOCKED"
        result["reason"] = f"timeout after {timeout:.1f}s"
        stdout_path.write_text(str(exc.stdout or ""), encoding="utf-8")
        stderr_path.write_text(str(exc.stderr or ""), encoding="utf-8")
    except OSError as exc:
        result["status"] = "BLOCKED"
        result["reason"] = str(exc)
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.write_text(str(exc), encoding="utf-8")
    result["duration_seconds"] = round(time.perf_counter() - started, 3)
    return result


def main() -> int:
    parsed = args()
    worktree_root = parsed.worktree_root.resolve()
    runtime_root = parsed.runtime_root.resolve()
    artifact_dir = parsed.artifact_dir.resolve()
    output = parsed.output.resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    cases: list[dict[str, Any]] = []
    if os.name == "posix":
        powershells = [("powershell-5.1", None)]
        if shutil.which("pwsh"):
            powershells.append(("powershell-7", shutil.which("pwsh")))
    else:
        powershells = [("powershell-5.1", shutil.which("powershell.exe"))]
        if shutil.which("pwsh.exe"):
            powershells.append(("powershell-7", shutil.which("pwsh.exe")))
    bash = git_bash()
    linux = native_bash()
    for repo in REPOSITORIES:
        source = worktree_root / repo
        target_base = artifact_dir / "targets" / repo
        python = runtime_root / repo / ".venv" / "Scripts" / "python.exe"
        posix_python = runtime_root / repo / ".venv" / "bin" / "python"
        if not posix_python.is_file():
            posix_python = Path(sys.executable)
        if os.name == "posix":
            python = posix_python
        for shell, executable in powershells:
            script = source / "install.ps1"
            command = (
                [
                    executable,
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    win_path(script),
                    "--dry-run",
                    "--install-dir",
                    win_path(target_base / shell),
                    "--python",
                    win_path(python),
                    "--quiet",
                ]
                if executable and script.is_file()
                else None
            )
            cases.append(
                run_case(
                    repo=repo,
                    shell=shell,
                    script=script,
                    command=command,
                    target=target_base / shell,
                    artifact_dir=artifact_dir,
                    timeout=parsed.timeout,
                )
            )
        script = source / "install.sh"
        if bash and script.is_file():
            command = [
                bash,
                bash_path(script),
                "--dry-run",
                "--install-dir",
                win_path(target_base / "git-bash"),
                "--python",
                win_path(python),
                "--quiet",
            ]
        else:
            command = None
        cases.append(
            run_case(
                repo=repo,
                shell="git-bash",
                script=script,
                command=command,
                target=target_base / "git-bash",
                artifact_dir=artifact_dir,
                timeout=parsed.timeout,
            )
        )
        if linux and script.is_file():
            linux_command = [
                linux,
                str(script),
                "--dry-run",
                "--install-dir",
                str(target_base / "linux-bash"),
                "--python",
                str(posix_python),
                "--quiet",
            ]
        else:
            linux_command = None
        cases.append(
            run_case(
                repo=repo,
                shell="linux-bash",
                script=script,
                command=linux_command,
                target=target_base / "linux-bash",
                artifact_dir=artifact_dir,
                timeout=parsed.timeout,
            )
        )
    payload = {
        "schema": "forge/installer-matrix/v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "platform": platform.platform(),
        "mode": "dry-run; no HKCU, PATH, shell profile or source checkout mutation",
        "results": cases,
        "counts": {
            state: sum(1 for case in cases if case["status"] == state)
            for state in ("PASS", "FAIL", "BLOCKED")
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for case in cases:
        print(f"{case['status']:8} {case['id']} ({case['duration_seconds'] or 0}s)")
    return 1 if payload["counts"]["FAIL"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
