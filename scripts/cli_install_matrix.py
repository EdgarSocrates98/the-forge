"""Validate the ecosystem CLI/TUI/install contract.

This is intentionally a small, dependency-free structural gate.  It does not
pretend to replace real terminal tests; it catches drift such as a missing
wizard module, a route that only checks stdin, or a project silently omitted
from the 14-repository release train.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent

PROJECTS: tuple[dict[str, Any], ...] = (
    {
        "repo": "api-forge",
        "cli": "apiforge",
        "install": "apiforge.cli_install",
        "surface": "home+tui+wizard",
        "source": "src/apiforge/cli_install.py",
    },
    {
        "repo": "code-atlas-forge",
        "cli": "code-atlas",
        "install": "code_atlas.install.cli",
        "surface": "home+tui+wizard",
        "source": "src/code_atlas/cli.py",
    },
    {
        "repo": "data-sentinel-forge",
        "cli": "data-sentinel",
        "install": "data_sentinel.cli.install",
        "surface": "home+tui+wizard",
        "source": "src/data_sentinel/cli/install.py",
    },
    {
        "repo": "forge-agent-bridge",
        "cli": "forge-bridge",
        "install": "forge_agent_bridge.install.cli",
        "surface": "home+tui+wizard",
        "source": "src/forge_agent_bridge/cli.py",
    },
    {
        "repo": "forge-cli",
        "cli": "forge",
        "install": "@clack/prompts",
        "surface": "menu+tui+wizard",
        "source": "src/index.ts",
    },
    {
        "repo": "forge-doctor-api",
        "cli": "forge-doctor-api",
        "install": "forge_doctor_api.ui.wizard",
        "surface": "home+tui+wizard",
        "source": "src/forge_doctor_api/cli/install_cmd.py",
    },
    {
        "repo": "forge-doctor-data",
        "cli": "forge-doctor-data",
        "install": "forge_doctor_data.ui.wizard",
        "surface": "home+tui+wizard",
        "source": "src/forge_doctor_data/cli/install_cmd.py",
    },
    {
        "repo": "forge-lens",
        "cli": "forge-lens",
        "install": "forge_lens.install.guided",
        "surface": "home+tui+wizard",
        "source": "src/forge_lens/install/guided.py",
    },
    {
        "repo": "forge-portal",
        "cli": "web",
        "install": None,
        "surface": "web-only",
        "source": "portal",
    },
    {
        "repo": "platform-forge",
        "cli": "platformforge",
        "install": "platformforge.ui.wizard",
        "surface": "home+tui+wizard",
        "source": "platformforge/portable_cli.py",
    },
    {
        "repo": "product-forge",
        "cli": "productforge",
        "install": "product_forge.ui.wizard",
        "surface": "home+tui+wizard",
        "source": "src/product_forge/install/cli.py",
    },
    {
        "repo": "spark-forge-aws",
        "cli": "sparkforge-aws",
        "install": "sparkforge_aws.ui.wizard",
        "surface": "home+tui+wizard",
        "source": "sparkforge_aws/adapters/cli.py",
    },
    {
        "repo": "spark-forge-azure",
        "cli": "sparkforge-azure",
        "install": "sparkforge_azure.ui.wizard",
        "surface": "home+tui+wizard",
        "source": "sparkforge_azure/cli/cmd_install.py",
    },
    {
        "repo": "the-forge",
        "cli": "theforge",
        "install": "theforge.ui.wizard",
        "surface": "home+tui+wizard",
        "source": "src/theforge/cli/commands.py",
    },
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def _evidence(repo: Path, source: str) -> str:
    """Read only product source files relevant to CLI/install evidence."""
    paths = [repo / source]
    ignored = {"vendor", "node_modules", "portal", "assets", "tests", "fixtures", ".git"}
    bases = [
        repo / name
        for name in ("src", "theforge", "platformforge", "sparkforge_aws", "sparkforge_azure")
    ]
    for base in bases:
        if not base.is_dir():
            continue
        for current, directories, filenames in os.walk(base):
            directories[:] = [name for name in directories if name not in ignored]
            current_path = Path(current)
            for name in filenames:
                path = current_path / name
                rel_parts = set(path.relative_to(repo).parts)
                if name.endswith((".py", ".ts")) and (
                    {"ui", "cli", "install"}.intersection(rel_parts) or name == "index.ts"
                ):
                    paths.append(path)
    unique = {p for p in paths if p.is_file() and not ignored.intersection(p.parts)}
    return "\n".join(_read(path) for path in unique)


def collect() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for item in PROJECTS:
        repo = WORKSPACE / item["repo"]
        source = repo / item["source"]
        text = _evidence(repo, item["source"])
        row = {
            **item,
            "exists": repo.is_dir(),
            "source_exists": source.is_file(),
            "tty_both_streams": (
                ("stdin.isatty()" in text and "stdout.isatty()" in text)
                or ("process.stdin.isTTY" in text and "process.stdout.isTTY" in text)
            ),
            "visual_install": item["install"] is None
            or any(marker in text for marker in ("wizard", "run_guided_install", "@clack/prompts")),
            "json_or_pipeline": item["install"] is None
            or ("json" in text.lower() or "JSON" in text),
            "non_tty_guard": item["install"] is None
            or ("isatty" in text or "isTTY" in text or "isNonInteractive" in text),
            "home_tui": item["install"] is None
            or ("run_home" in text and "run_tui" in text),
        }
        if not row["exists"]:
            errors.append(f"{item['repo']}: repository missing")
        if not row["source_exists"] and item["install"] is not None:
            errors.append(f"{item['repo']}: source missing: {item['source']}")
        if item["install"] is not None:
            if not row["tty_both_streams"]:
                errors.append(f"{item['repo']}: no both-stream TTY evidence in {item['source']}")
            if not row["visual_install"]:
                errors.append(f"{item['repo']}: no visual install evidence")
            if not row["json_or_pipeline"]:
                errors.append(f"{item['repo']}: no JSON/pipeline evidence")
            if item["surface"] == "home+tui+wizard" and not row["home_tui"]:
                errors.append(f"{item['repo']}: no home/TUI evidence")
        rows.append(row)
    return {
        "schema": "forge/cli-tui-install-matrix/v1",
        "repository_count": len(rows),
        "projects": rows,
        "errors": errors,
        "status": "PASS" if not errors and len(rows) == 14 else "FAIL",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="validate and print the matrix")
    parser.parse_args()
    result = collect()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
