"""Exercise every published CLI command's help surface across the Forge train.

This is intentionally a non-mutating contract probe.  It reads generated
command inventories where available and runs each leaf as ``... --help`` in a
real subprocess.  Help is a useful boundary test for required positional
arguments, parser wiring and import-time regressions without applying an
installation, changing a workspace or invoking a provider.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from time import monotonic

ROOT = Path(__file__).resolve().parents[1]
REPOS_ROOT = ROOT.parent


@dataclass(frozen=True)
class Case:
    repo: str
    command: tuple[str, ...]
    inventory: str | None = None


CASES = (
    Case("api-forge", ("uv", "run", "apiforge"), "docs/reference/commands.generated.json"),
    Case("code-atlas-forge", ("uv", "run", "code-atlas")),
    Case("data-sentinel-forge", ("uv", "run", "data-sentinel")),
    Case("forge-agent-bridge", ("uv", "run", "forge-bridge")),
    Case("forge-cli", ("node", "dist/index.js")),
    Case(
        "forge-doctor-api",
        ("uv", "run", "forge-doctor-api"),
        "docs/reference/commands.generated.json",
    ),
    Case(
        "forge-doctor-data",
        ("uv", "run", "forge-doctor-data"),
        "docs/reference/commands.generated.json",
    ),
    Case("forge-lens", ("uv", "run", "forge-lens")),
    Case("forge-portal", ("node", "tools/portal-cli.mjs")),
    Case(
        "platform-forge",
        ("uv", "run", "platformforge"),
        "docs/reference/commands.generated.json",
    ),
    Case("product-forge", ("uv", "run", "productforge")),
    Case(
        "spark-forge-aws",
        ("uv", "run", "sparkforge-aws"),
        "docs/reference/commands.generated.json",
    ),
    Case(
        "spark-forge-azure",
        ("uv", "run", "sparkforge-azure"),
        "docs/reference/commands.generated.json",
    ),
    Case(
        "the-forge",
        ("uv", "run", "theforge"),
        "docs/reference/commands.generated.json",
    ),
)


def _commands(case: Case) -> list[tuple[str, ...]]:
    if not case.inventory:
        return [()]
    data = json.loads((REPOS_ROOT / case.repo / case.inventory).read_text(encoding="utf-8"))
    return [tuple(str(row["path"]).split()) for row in data["commands"] if not row.get("group")]


def _run(case: Case, path: tuple[str, ...], timeout: float) -> dict[str, object]:
    argv = [*case.command, *path, "--help"]
    started = monotonic()
    try:
        result = subprocess.run(
            argv,
            cwd=REPOS_ROOT / case.repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        return {
            "repo": case.repo,
            "command": " ".join(argv),
            "path": " ".join(path),
            "exit_code": result.returncode,
            "seconds": round(monotonic() - started, 3),
            "output": (result.stdout or result.stderr)[:500],
            "status": "PASS" if result.returncode == 0 else "FAIL",
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "repo": case.repo,
            "command": " ".join(argv),
            "path": " ".join(path),
            "exit_code": None,
            "seconds": round(monotonic() - started, 3),
            "output": str(exc)[:500],
            "status": "TIMEOUT",
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="audit/cli-command-help-matrix-current.json")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    jobs = [(case, path) for case in CASES for path in _commands(case)]
    results: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [pool.submit(_run, case, path, args.timeout) for case, path in jobs]
        for future in as_completed(futures):
            results.append(future.result())
    results.sort(key=lambda row: (str(row["repo"]), str(row["path"])))
    failures = [row for row in results if row["status"] != "PASS"]
    report = {
        "schema": "forge/cli-command-help-matrix/v1",
        "repository_count": len(CASES),
        "command_count": len(results),
        "failure_count": len(failures),
        "status": "PASS" if not failures else "FAIL",
        "results": results,
    }
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {
        key: report[key]
        for key in ("repository_count", "command_count", "failure_count", "status")
    }
    print(json.dumps(summary, indent=2))
    if failures:
        for row in failures[:20]:
            print(f"FAIL {row['repo']}: {row['path']} ({row['status']})")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
