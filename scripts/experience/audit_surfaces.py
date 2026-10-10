#!/usr/bin/env python3
"""Inventário real das superfícies das sete Forjas (FASE 0, §0.1/§0.5).

Lê APENAS o filesystem dos repositórios — nenhum pacote é importado, nenhuma
rede é tocada. O resultado é a matriz de aceite por Forja que a Fase 0
congela: o que existe, o que falta e o que precisa de verificação de
comportamento (não de existência de arquivo — §7).

Uso:

    python scripts/experience/audit_surfaces.py [--root E:\\projetos\\FORJAS]
        [--out docs/experience/audit-fase0.json]

A matriz publicada distingue `present` (arquivo/estrutura existe) de
`verified` (comportamento observado). Este script só emite `present`/
`absent`; a promoção a `verified` exige evidência de execução, registrada
à mão na coluna homônima do relatório — nunca inferida.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from datetime import UTC, datetime
from pathlib import Path

FORGES = (
    "the-forge",
    "api-forge",
    "spark-forge-aws",
    "spark-forge-azure",
    "platform-forge",
    "forge-doctor-data",
    "forge-doctor-api",
)

# Fonte canônica de skills por repo — declarada, não inferida: a convenção
# varia (AWS/Azure renderizam de skills/; api-forge de .github/skills;
# platform-forge mantém .devin/skills como fonte; the-forge edita os três
# hosts por igual conforme AGENTS.md; doctors não têm skills ainda).
SKILL_SOURCE = {
    "the-forge": [".agents/skills", ".claude/skills", ".devin/skills"],
    "api-forge": [".github/skills"],
    "spark-forge-aws": ["skills"],
    "spark-forge-azure": ["skills"],
    "platform-forge": [".devin/skills"],
    "forge-doctor-data": [],
    "forge-doctor-api": [],
}

PKG_DIRS = {
    "the-forge": "src/theforge",
    "api-forge": "src/apiforge",
    "spark-forge-aws": "sparkforge_aws",
    "spark-forge-azure": "sparkforge_azure",
    "platform-forge": "platformforge",
    "forge-doctor-data": "src/forge_doctor_data",
    "forge-doctor-api": "src/forge_doctor_api",
}


def _count_md(root: Path, pattern: str) -> int:
    return sum(1 for p in root.glob(pattern) if p.is_file())


def _count_skill_dirs(root: Path) -> int:
    skills = root / "skills"
    if not skills.is_dir():
        return 0
    return sum(1 for p in skills.iterdir() if (p / "SKILL.md").is_file())


def _count_mirror_skills(root: Path) -> int:
    if not root.is_dir():
        return 0
    return sum(1 for p in root.iterdir() if (p / "SKILL.md").is_file())


def _pyproject(root: Path) -> dict:
    pp = root / "pyproject.toml"
    if not pp.is_file():
        return {}
    return tomllib.loads(pp.read_text(encoding="utf-8"))


def _cli_groups(root: Path) -> int | None:
    """Grupos de 1º nível curados em command-rationale.json (fonte de verdade)."""
    cr = root / "docs" / "reference" / "command-rationale.json"
    if cr.is_file():
        data = json.loads(cr.read_text(encoding="utf-8"))
        groups = data.get("groups") or data
        if isinstance(groups, dict):
            return sum(1 for k in groups if isinstance(k, str) and " " not in k)
    return None


def _presence(root: Path, rel: str) -> bool:
    return (root / rel).exists()


def _find_pkg(root: Path, forge: str) -> Path:
    return root / PKG_DIRS[forge]


def _grep_count(root: Path, pattern: str, glob: str = "**/*.py") -> int:
    rx = re.compile(pattern)
    n = 0
    pkg_hint = root
    for p in pkg_hint.glob(glob):
        if not p.is_file() or ".venv" in p.parts or "__pycache__" in p.parts:
            continue
        try:
            if rx.search(p.read_text(encoding="utf-8", errors="replace")):
                n += 1
        except OSError:
            continue
    return n


def audit_forge(root: Path, forge: str) -> dict:
    pkg = _find_pkg(root, forge)
    py = _pyproject(root)
    project = py.get("project", {})
    scripts = sorted((project.get("scripts") or {}).keys())
    groups = _cli_groups(root)

    surface_lock = root / "docs" / "surface.lock.json"
    mcp_tools = None
    if surface_lock.is_file():
        mcp_tools = (
            json.loads(surface_lock.read_text(encoding="utf-8"))
            .get("tools", {})
            .get("tool_count")
        )

    mirrors = {
        ".claude/agents": _count_md(root / ".claude" / "agents", "*.md"),
        ".claude/skills": _count_mirror_skills(root / ".claude" / "skills"),
        ".agents/agents": _count_md(root / ".agents" / "agents", "*.md"),
        ".agents/skills": _count_mirror_skills(root / ".agents" / "skills"),
        ".devin/agents": _count_md(root / ".devin" / "agents", "*.md"),
        ".devin/skills": _count_mirror_skills(root / ".devin" / "skills"),
        ".codex/agents": _count_md(root / ".codex" / "agents", "*.toml"),
        ".github/skills": _count_mirror_skills(root / ".github" / "skills"),
        ".github/agents": _count_md(root / ".github" / "agents", "*.md")
        + _count_md(root / ".github" / "agents", "*.agent.md"),
    }

    ui_files = [p.name for p in (pkg / "ui").glob("*.py")] if (pkg / "ui").is_dir() else []
    rationale = root / "docs" / "reference" / "command-rationale.json"
    install_groups = []
    if rationale.is_file():
        data = json.loads(rationale.read_text(encoding="utf-8"))
        groups_map = data.get("groups") if isinstance(data, dict) else data
        if isinstance(groups_map, dict):
            install_groups = sorted(
                k
                for k in groups_map
                if k.startswith("install")
                or k.split(" ")[0] in ("install", "setup", "uninstall", "doctor", "status")
            )

    return {
        "forge_id": forge,
        "version": project.get("version"),
        "requires_python": project.get("requires-python"),
        "console_scripts": scripts,
        "cli_groups_curated": groups,
        "install_related_groups": install_groups,
        "surfaces": {
            "tui": {"present": bool(ui_files), "files": sorted(ui_files)},
            "mcp": {
                "present": _presence(root, str(Path(PKG_DIRS[forge]) / "mcp"))
                or _presence(root, str(Path(PKG_DIRS[forge]) / "integrations" / "mcp_server.py"))
                or _presence(root, str(Path(PKG_DIRS[forge]) / "handoff" / "mcp_server.py"))
                or _presence(root, str(Path(PKG_DIRS[forge]) / "cli" / "cmd_mcp.py")),
                "tools_locked": mcp_tools,
            },
            "install": {
                "present": bool(install_groups)
                or _presence(root, str(Path(PKG_DIRS[forge]) / "install")),
                "groups": install_groups,
            },
            "graph": {
                "present": _grep_count(pkg, r"graphview|graph_studio|GraphStudio|graph_view") > 0
                or _presence(root, "graph-studio")
                or _presence(root, "ui/graph"),
            },
            "docs": {
                "readme": _presence(root, "README.md"),
                "index": _presence(root, "docs/INDEX.md"),
                "learn_tree": (
                    _count_md(root / "docs" / "learn", "**/*.md")
                    if (root / "docs" / "learn").is_dir()
                    else 0
                ),
                "hub": _presence(root, "docs/hub"),
                "commands_reference": _presence(root, "docs/reference/commands.md"),
                "command_rationale": rationale.is_file(),
            },
        },
        "agentic": {
            "agents_canonical": _count_md(root / "agents", "**/*.md")
            + _count_md(root / "agentic" / "agents", "*.toml"),
            "skill_source": SKILL_SOURCE.get(forge, []),
            "skills_canonical": max(
                (_count_mirror_skills(root / src) for src in SKILL_SOURCE.get(forge, [])),
                default=0,
            )
            or _count_skill_dirs(root),
            "mirrors": mirrors,
            "agentic_surfaces_total": sum(mirrors.values()),
        },
        "contracts": {
            "schemas_dir": (
                _count_md(root / "schemas", "*.json")
                if (root / "schemas").is_dir()
                else 0
            ),
            "surface_lock": surface_lock.is_file(),
            "capability_manifest": _presence(root, "agents/CAPABILITY.json")
            or _presence(root, "docs/CAPABILITY.json")
            or _presence(root, "manifest.json"),
            "receipt_artifacts": [
                str(p.relative_to(root))
                for p in root.glob("**/VALIDATION-RECEIPT.json")
                if ".venv" not in p.parts
            ][:5],
        },
        "knowledge_docs": (
            _count_md(root / "knowledge", "**/*.md")
            if (root / "knowledge").is_dir()
            else 0
        ),
        "test_files": (
            _count_md(root / "tests", "**/test_*.py")
            if (root / "tests").is_dir()
            else 0
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[3]))
    ap.add_argument("--out", default="docs/experience/audit-fase0.json")
    args = ap.parse_args()

    root = Path(args.root)
    report = {
        "schema": "forge/ExperienceAudit/v1",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "generator": "scripts/experience/audit_surfaces.py",
        "note": "presence != verified — ver contrato de paridade (§7)",
        "forges": {},
    }
    for forge in FORGES:
        forge_root = root / forge
        if not forge_root.is_dir():
            report["forges"][forge] = {"error": "repo ausente"}
            continue
        report["forges"][forge] = audit_forge(forge_root, forge)

    out = Path(args.out)
    if not out.is_absolute():
        out = root / "the-forge" / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out}")

    for forge, data in report["forges"].items():
        if "error" in data:
            print(f"{forge:20} {data['error']}")
            continue
        s, a = data["surfaces"], data["agentic"]
        print(
            f"{forge:20} v{data['version']:<8} scripts={len(data['console_scripts'])} "
            f"tui={'Y' if s['tui']['present'] else '-'} "
            f"mcp={s['mcp']['tools_locked'] or ('Y' if s['mcp']['present'] else '-')} "
            f"install={'Y' if s['install']['present'] else '-'} "
            f"graph={'Y' if s['graph']['present'] else '-'} "
            f"agents={a['agents_canonical']} skills={a['skills_canonical']} "
            f"mirrors={a['agentic_surfaces_total']} tests={data['test_files']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
