"""Run the safe, read-only entry-point smoke for the 14-repository train.

This gate proves that each installed CLI can be discovered and explain itself.
It deliberately runs only ``--version`` and ``--help``: no wizard, install,
provider, workspace, or cloud action is invoked. Child processes receive a
scrubbed environment so the smoke cannot accidentally use ambient credentials.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent


@dataclass(frozen=True)
class Case:
    repo: str
    executable: str
    args: tuple[str, ...]


CASES: tuple[Case, ...] = (
    Case("api-forge", "uv", ("run", "apiforge")),
    Case("code-atlas-forge", "uv", ("run", "code-atlas")),
    Case("data-sentinel-forge", "uv", ("run", "data-sentinel")),
    Case("forge-agent-bridge", "uv", ("run", "forge-bridge")),
    Case("forge-cli", "node", ("dist/index.js",)),
    Case("forge-doctor-api", "uv", ("run", "forge-doctor-api")),
    Case("forge-doctor-data", "uv", ("run", "forge-doctor-data")),
    Case("forge-lens", "uv", ("run", "forge-lens")),
    Case("forge-portal", "node", ("tools/portal-cli.mjs",)),
    Case("platform-forge", "uv", ("run", "platformforge")),
    Case("product-forge", "uv", ("run", "productforge")),
    Case("spark-forge-aws", "uv", ("run", "sparkforge-aws")),
    Case("spark-forge-azure", "uv", ("run", "sparkforge-azure")),
    Case("the-forge", "uv", ("run", "theforge")),
)

FLAGS = ("--version", "--help")
SECRET_MARKERS = (
    "ACCESS_KEY",
    "API_KEY",
    "PASSWORD",
    "PRIVATE_KEY",
    "SECRET",
    "TOKEN",
)


def scrubbed_environment() -> dict[str, str]:
    """Preserve toolchain settings while excluding ambient secret material."""
    return {
        key: value
        for key, value in os.environ.items()
        if not any(marker in key.upper() for marker in SECRET_MARKERS)
        and key.upper() not in {"AWS_PROFILE", "AWS_CONFIG_FILE", "AZURE_CONFIG_DIR"}
    }


def _first_line(stdout: str, stderr: str) -> str:
    for line in (stdout + "\n" + stderr).splitlines():
        value = line.strip()
        if value:
            return value[:200]
    return ""


def run_case(case: Case, flag: str, timeout_s: float, env: dict[str, str]) -> dict[str, Any]:
    command = [case.executable, *case.args, flag]
    cwd = WORKSPACE / case.repo
    row: dict[str, Any] = {
        "repo": case.repo,
        "command": " ".join(command),
        "flag": flag,
        "cwd": str(cwd),
    }
    if not cwd.is_dir():
        row.update({"status": "FAIL", "reason": "repository missing"})
        return row
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
            check=False,
        )
    except FileNotFoundError as exc:
        row.update({"status": "FAIL", "reason": f"executable unavailable: {exc.filename}"})
        return row
    except subprocess.TimeoutExpired:
        row.update({"status": "FAIL", "reason": f"timeout after {timeout_s:g}s"})
        return row
    output = _first_line(completed.stdout, completed.stderr)
    row.update(
        {
            "status": "PASS" if completed.returncode == 0 and output else "FAIL",
            "exit_code": completed.returncode,
            "output": output,
        }
    )
    if completed.returncode != 0:
        row["reason"] = "non-zero exit code"
    elif not output:
        row["reason"] = "empty output"
    return row


def collect(timeout_s: float = 30.0) -> dict[str, Any]:
    env = scrubbed_environment()
    checks = [run_case(case, flag, timeout_s, env) for case in CASES for flag in FLAGS]
    return {
        "schema": "forge/cli-runtime-smoke/v1",
        "repository_count": len(CASES),
        "check_count": len(checks),
        "checks": checks,
        "status": "PASS" if all(row["status"] == "PASS" for row in checks) else "FAIL",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--timeout", type=float, default=30.0, help="per-command timeout in seconds"
    )
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    result = collect(args.timeout)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
