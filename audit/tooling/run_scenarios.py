#!/usr/bin/env python3
"""Run small, deterministic ecosystem scenarios and record evidence.

The runner is stdlib-only by design. It never invokes a shell, never mutates
the source repositories, and redacts common secret-shaped output before
persisting evidence.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,100}$")
SECRET_LINE = re.compile(
    r"(?i)(\b(?:api[_-]?key|access[_-]?token|secret|password|passwd)\b\s*[:=]\s*)([^\s,;]+)"
)


def redact(value: str) -> str:
    return SECRET_LINE.sub(r"\1<redacted>", value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario-file", type=Path, default=Path("audit/scenarios/ecosystem.json")
    )
    parser.add_argument("--repo-root", type=Path, help="central repository root")
    parser.add_argument(
        "--worktree-root", type=Path, help="directory containing one checkout per repository"
    )
    parser.add_argument("--runtime-root", type=Path, help="directory containing runtime venvs")
    parser.add_argument("--artifact-dir", type=Path, default=Path("audit/artifacts/scenarios"))
    parser.add_argument("--output", type=Path, default=Path("audit/reports/evidence-index.json"))
    parser.add_argument("--timeout", type=float, default=180.0)
    return parser.parse_args()


def repo_path(repo: str, central: Path, worktrees: Path | None, runtimes: Path | None) -> Path:
    if worktrees:
        candidate = (worktrees / repo).resolve()
    elif repo == central.name:
        candidate = central
    elif runtimes:
        candidate = (runtimes / repo).resolve()
    else:
        candidate = (central.parent / repo).resolve()
    if not candidate.is_dir():
        raise FileNotFoundError(f"repository checkout not found: {candidate}")
    return candidate


def runtime_python(repo: str, runtimes: Path | None) -> Path:
    candidates: list[Path] = []
    if runtimes:
        root = runtimes / repo
        candidates.extend(
            (root / ".venv" / "Scripts" / "python.exe", root / ".venv" / "bin" / "python")
        )
    candidates.append(Path(sys.executable))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"python runtime not found for {repo}")


def runtime_entrypoint(repo: str, entrypoint: str, runtimes: Path | None) -> Path:
    if not runtimes:
        raise FileNotFoundError(f"runtime root required for CLI scenario {repo}")
    root = runtimes / repo / ".venv"
    candidates = [root / "Scripts" / f"{entrypoint}.exe", root / "bin" / entrypoint]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"entrypoint not found: {entrypoint} ({repo})")


def git_sha(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def expand(value: str, *, root: Path, artifact_dir: Path) -> str:
    return value.replace("{repo_root}", str(root)).replace("{artifact_dir}", str(artifact_dir))


def build_command(
    spec: dict[str, Any], root: Path, artifact_dir: Path, runtimes: Path | None
) -> list[str]:
    repo = str(spec["repo"])
    args = [expand(str(arg), root=root, artifact_dir=artifact_dir) for arg in spec.get("args", [])]
    kind = spec.get("kind")
    if kind == "cli":
        return [str(runtime_entrypoint(repo, str(spec["entrypoint"]), runtimes)), *args]
    if kind == "bootstrap":
        return [str(runtime_python(repo, runtimes)), str(root / str(spec["entrypoint"])), *args]
    raise ValueError(f"unsupported scenario kind: {kind}")


def run_one(
    spec: dict[str, Any],
    *,
    central: Path,
    worktrees: Path | None,
    runtimes: Path | None,
    artifact_dir: Path,
    default_timeout: float,
) -> dict[str, Any]:
    scenario_id = str(spec.get("id", ""))
    if not SAFE_ID.fullmatch(scenario_id):
        raise ValueError(f"invalid scenario id: {scenario_id!r}")
    root = repo_path(str(spec["repo"]), central, worktrees, runtimes)
    scenario_artifact = artifact_dir / scenario_id
    scenario_artifact.mkdir(parents=True, exist_ok=True)
    stdout_path = scenario_artifact / "stdout.txt"
    stderr_path = scenario_artifact / "stderr.txt"
    started = time.perf_counter()
    command: list[str] | None = None
    exit_code: int | None = None
    status = "FAIL"
    error: str | None = None
    stdout = ""
    stderr = ""
    try:
        command = build_command(spec, root, scenario_artifact, runtimes)
        env = os.environ.copy()
        src = root / "src"
        if src.is_dir():
            env["PYTHONPATH"] = str(src) + (
                os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
            )
        env["NO_COLOR"] = "1"
        env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
        env["PYTHONNOUSERSITE"] = "1"
        completed = subprocess.run(
            command,
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=float(spec.get("timeout", default_timeout)),
            check=False,
        )
        exit_code = completed.returncode
        stdout = redact(completed.stdout)
        stderr = redact(completed.stderr)
        status = "PASS" if exit_code == 0 else "FAIL"
    except subprocess.TimeoutExpired as exc:
        status = "BLOCKED"
        error = f"timeout after {float(spec.get('timeout', default_timeout)):.1f}s"
        stdout = redact((exc.stdout or "") if isinstance(exc.stdout, str) else "")
        stderr = redact((exc.stderr or "") if isinstance(exc.stderr, str) else "")
    except (OSError, ValueError) as exc:
        status = "BLOCKED"
        error = str(exc)
    duration = round(time.perf_counter() - started, 3)
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    return {
        "id": scenario_id,
        "repo": str(spec["repo"]),
        "status": status,
        "sha": git_sha(root),
        "command": command,
        "cwd": str(root),
        "exit_code": exit_code,
        "duration_seconds": duration,
        "stdout_artifact": str(stdout_path),
        "stderr_artifact": str(stderr_path),
        "stdout_preview": stdout[-2000:],
        "stderr_preview": stderr[-2000:],
        "error": error,
        "recorded_at": datetime.now(UTC).isoformat(),
    }


def main() -> int:
    args = parse_args()
    central = (args.repo_root or Path(__file__).resolve().parents[2]).resolve()
    scenario_file = (
        (central / args.scenario_file).resolve()
        if not args.scenario_file.is_absolute()
        else args.scenario_file.resolve()
    )
    worktrees = args.worktree_root.resolve() if args.worktree_root else None
    runtimes = args.runtime_root.resolve() if args.runtime_root else central.parent
    artifact_dir = (
        (central / args.artifact_dir).resolve()
        if not args.artifact_dir.is_absolute()
        else args.artifact_dir.resolve()
    )
    output = (
        (central / args.output).resolve()
        if not args.output.is_absolute()
        else args.output.resolve()
    )
    plan = json.loads(scenario_file.read_text(encoding="utf-8"))
    if plan.get("schema") != "forge/scenario-plan/v1":
        raise SystemExit(f"unsupported scenario schema: {plan.get('schema')!r}")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for spec in plan["scenarios"]:
        result = run_one(
            spec,
            central=central,
            worktrees=worktrees,
            runtimes=runtimes,
            artifact_dir=artifact_dir,
            default_timeout=args.timeout,
        )
        results.append(result)
        print(f"{result['status']:8} {result['id']} ({result['duration_seconds']}s)")
    payload = {
        "schema": "forge/evidence-index/v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "runner": {
            "path": str(Path(__file__).resolve()),
            "python": sys.version,
            "platform": platform.platform(),
            "sha": git_sha(central),
        },
        "results": results,
        "counts": {
            status: sum(1 for result in results if result["status"] == status)
            for status in ("PASS", "FAIL", "BLOCKED")
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0 if not any(result["status"] == "FAIL" for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
