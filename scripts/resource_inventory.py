#!/usr/bin/env python3
"""ONDA 4 — real resource inventory across all 15 repos.

Scans each checkout directly (no manifest dependency) and emits per-repo,
per-kind counts with location, packaging status and availability evidence.
Repos without a forge.agentic.json (forge-cli, forge-portal) are inventoried
honestly under their own conventions — never reported as "None".

Kinds: skill, agent, knowledge, rule, contract, eval, example, fixture,
command, config, protocol.

Usage: python scripts/resource_inventory.py --root <workspace> [--write]
"""
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPOS = [
    "the-forge", "forge-cli", "forge-portal", "forge-agent-bridge",
    "spark-forge-aws", "spark-forge-azure", "api-forge", "platform-forge",
    "product-forge", "code-atlas-forge", "forge-lens", "data-sentinel-forge",
    "api-sentinel-forge", "forge-doctor-api", "forge-doctor-data",
]

# kind -> candidate dirs (glob-aware; first match wins per kind)
KIND_DIRS: dict[str, tuple[str, ...]] = {
    "skill":    ("skills", ".claude/skills", ".agents/skills", ".devin/skills"),
    "agent":    ("agents", ".claude/agents", ".agents/agents",
                 "src/*/installation/assets/agents"),
    "knowledge": ("knowledge", "docs/knowledge"),
    "rule":     ("rules", "rules/catalog", "src/*/rules", "src/*/rules/catalog"),
    "contract": ("contracts", "schemas", "contracts/v1", "src/*/contracts"),
    "eval":     ("evals", "evaluation"),
    "example":  ("examples",),
    "fixture":  ("fixtures", "tests/fixtures", "lab/fixtures"),
    "protocol": ("protocols",),
}

SKIP_DIRS = {"__pycache__", ".pytest_cache", "node_modules", ".git", "dist",
             ".venv", "site-packages", ".next", "coverage", "htmlcov"}
TEXT_EXTS = {".md", ".yaml", ".yml", ".json", ".py", ".txt", ".toml",
             ".ts", ".tsx"}


def _dirs(root: Path, kind: str) -> list[Path]:
    out: list[Path] = []
    for rel in KIND_DIRS.get(kind, ()):
        bases = sorted(root.glob(rel)) if "*" in rel else [root / rel]
        for b in bases:
            if b.is_dir():
                out.append(b)
    return out


def _count_files(base: Path) -> int:
    n = 0
    for p in base.rglob("*"):
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.suffix.lower() in TEXT_EXTS or not p.suffix:
            n += 1
    return n


def _top_level_units(base: Path, kind: str) -> int:
    """Collection-kind resources count top-level units (one per skill dir,
    one per fixture file) not every nested file."""
    if kind in ("skill", "agent"):
        # one resource per immediate subdirectory or top-level .md file
        units = 0
        for p in sorted(base.iterdir()):
            if (p.is_dir() and p.name not in SKIP_DIRS) or (
                    p.is_file() and p.suffix.lower() in TEXT_EXTS):
                units += 1
        return units
    return _count_files(base)


def _commands(root: Path, repo: str) -> dict[str, Any]:
    """Declared CLI entrypoints / npm bins / console scripts."""
    out: dict[str, Any] = {"console_scripts": [], "npm_bins": []}
    pj = root / "pyproject.toml"
    if pj.exists():
        import tomllib
        try:
            data = tomllib.loads(pj.read_text(encoding="utf-8"))
            scripts = (data.get("project") or {}).get("scripts") or {}
            out["console_scripts"] = sorted(scripts)
        except Exception:  # noqa: BLE001
            pass
    pkg = root / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
            bin_ = data.get("bin") or {}
            if isinstance(bin_, dict):
                out["npm_bins"] = sorted(bin_)
            elif isinstance(bin_, str):
                out["npm_bins"] = [data.get("name", "?")]
        except Exception:  # noqa: BLE001
            pass
    return out


def _configs(root: Path) -> list[str]:
    names = []
    for cand in ("pyproject.toml", "package.json", "forge.json",
                 "forge.agentic.json", "manifest.json", "parity.yaml",
                 "uv.lock", "tsconfig.json", "angular.json", "workspace.yaml",
                 "CONTEXT.md"):
        if (root / cand).exists():
            names.append(cand)
    return names


def _packaged(root: Path, repo: str) -> dict[str, Any]:
    """What the distribution actually ships (wheel content claims)."""
    pj = root / "pyproject.toml"
    info: dict[str, Any] = {"dist": None, "src_layout": False}
    if pj.exists():
        import tomllib
        try:
            data = tomllib.loads(pj.read_text(encoding="utf-8"))
            info["dist"] = (data.get("project") or {}).get("name")
        except Exception:  # noqa: BLE001
            pass
        info["src_layout"] = (root / "src").is_dir()
    pkg = root / "package.json"
    if info["dist"] is None and pkg.exists():
        import contextlib
        with contextlib.suppress(Exception):
            info["dist"] = json.loads(
                pkg.read_text(encoding="utf-8")).get("name")
    return info


def inventory_repo(root: Path, repo: str) -> dict[str, Any]:
    d = root / repo
    entry: dict[str, Any] = {"repo": repo, "exists": d.is_dir()}
    if not d.is_dir():
        return entry
    entry["has_manifest"] = (d / "forge.agentic.json").exists() or any(
        d.glob("src/*/forge.agentic.json"))
    kinds: dict[str, dict[str, Any]] = {}
    for kind in KIND_DIRS:
        dirs = _dirs(d, kind)
        if not dirs:
            continue
        count = sum(_top_level_units(b, kind) for b in dirs)
        kinds[kind] = {"count": count,
                       "locations": [str(b.relative_to(d)) for b in dirs]}
    entry["resources"] = kinds
    entry["resource_total"] = sum(v["count"] for v in kinds.values())
    cmds = _commands(d, repo)
    entry["commands"] = cmds["console_scripts"] + cmds["npm_bins"]
    entry["config_files"] = _configs(d)
    pk = _packaged(d, repo)
    entry["dist_name"] = pk["dist"]
    entry["src_layout"] = pk["src_layout"]
    # integrity: manifest parse + sha of manifest when present
    man = d / "forge.agentic.json"
    if not man.exists():
        man = next(d.glob("src/*/forge.agentic.json"), None)  # type: ignore[assignment]
    if man and man.exists():
        import hashlib
        try:
            payload = json.loads(man.read_text(encoding="utf-8"))
            entry["manifest_sha256"] = hashlib.sha256(
                man.read_bytes()).hexdigest()
            entry["manifest_parses"] = True
            entry["manifest_id"] = payload.get("forge_id") or payload.get("id")
        except Exception:  # noqa: BLE001
            entry["manifest_parses"] = False
    return entry


def main() -> int:
    argv = sys.argv[1:]
    root = Path(argv[argv.index("--root") + 1]) if "--root" in argv else Path.cwd()
    out_dir = root / "audits" / "unified-platform"
    out_dir.mkdir(parents=True, exist_ok=True)

    inv = {r: inventory_repo(root, r) for r in REPOS}
    totals: dict[str, int] = {
        "repos": sum(1 for e in inv.values() if e.get("exists")),
        "with_manifest": sum(1 for e in inv.values()
                             if e.get("has_manifest")),
        "resources": sum(e.get("resource_total", 0) for e in inv.values()),
        "commands": sum(len(e.get("commands") or [])
                        for e in inv.values()),
    }
    report = {
        "kind": "forge/resource-inventory/1",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "workspace": str(root),
        "repos": inv,
        "totals": totals,
    }
    (out_dir / "resource-inventory.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    t = totals
    print(f"inventory: {t['repos']} repos, {t['with_manifest']} manifests, "
          f"{t['resources']} resources, {t['commands']} commands")
    for r, e in inv.items():
        print(f"  {r:24s} manifest={e.get('has_manifest')} "
              f"resources={e.get('resource_total', 0)} "
              f"cmds={len(e.get('commands') or [])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
