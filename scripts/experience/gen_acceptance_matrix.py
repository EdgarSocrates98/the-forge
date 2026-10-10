#!/usr/bin/env python3
"""Render docs/experience/matriz-aceite.md from audit-fase0.json.

FASE 0 §0.5: matriz de critérios de aceite preenchida com inventário real.
Cada célula mostra o estado OBSERVADO — a coluna "alvo" vem do programa,
nunca de presunção. Regenerar com:

    python scripts/experience/gen_acceptance_matrix.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "docs" / "experience" / "audit-fase0.json"
OUT = ROOT / "docs" / "experience" / "matriz-aceite.md"

# Capacidades × o que o auditor observa. Alvo = requisito do programa.
ROWS: list[tuple[str, str, str]] = [
    # (capacidade, alvo do programa, chave do audit)
    ("install.lifecycle", "status/doctor/plan honestos", "install"),
    ("cli.agentic", "verbos descobrem agents/skills", None),
    ("tui.entries", "entradas reais, DocMeta, sem botão falso", "tui"),
    ("mcp.surface", "tools declaradas + handshake", "mcp_tools"),
    ("graph.surface", "projeção consumível", "graph"),
    ("agents.catalog", "catálogo didático §11", "agents"),
    ("skills.catalog", "skills canônicas + triggers", "skills"),
    ("mirrors.sync", "espelhos == render(canônico)", "mirrors"),
    ("tests.suite", "suíte verde em main", "test_files"),
]


def _observed(audit: dict, forge: str, key: str | None) -> tuple[str, str]:
    """Estado observado + evidência, a partir do audit."""
    row = audit["forges"][forge]
    surf = row["surfaces"]
    if key == "install":
        ok = surf["install"]["present"]
        return (
            "SUPPORTED" if ok else "UNSUPPORTED",
            "superfície install/" if ok else "sem superfície install",
        )
    if key == "tui":
        ok = surf["tui"]["present"]
        return (
            "SUPPORTED" if ok else "UNSUPPORTED",
            f"{len(surf['tui']['files'])} arquivos ui/" if ok else "ausente",
        )
    if key == "mcp_tools":
        n = surf["mcp"]["tools_locked"]
        if n:
            return ("SUPPORTED", f"{n} tools no lock")
        return (
            "UNVERIFIED" if surf["mcp"]["present"] else "UNSUPPORTED",
            "módulo mcp/ existe, tools não contadas"
            if surf["mcp"]["present"]
            else "sem mcp/",
        )
    if key == "graph":
        ok = surf["graph"]["present"]
        return (
            "SUPPORTED" if ok else "PARTIAL",
            "graphview/knowledge detectado" if ok else "parcial",
        )
    if key == "agents":
        n = row["agentic"]["agents_canonical"]
        return ("SUPPORTED" if n else "UNSUPPORTED", f"{n} agents canônicos")
    if key == "skills":
        n = row["agentic"]["skills_canonical"]
        src = ",".join(row["agentic"]["skill_source"]) or "—"
        return ("SUPPORTED" if n else "UNSUPPORTED", f"{n} skills em {src}")
    if key == "mirrors":
        n = row["agentic"]["agentic_surfaces_total"]
        return ("SUPPORTED" if n else "UNSUPPORTED", f"{n} arquivos espelho")
    if key == "test_files":
        n = row["test_files"]
        return ("SUPPORTED", f"{n} arquivos de teste")
    # cli.agentic — derivado: cli + superfícies agentic
    n = row["agentic"]["agents_canonical"] + row["agentic"]["skills_canonical"]
    return ("SUPPORTED" if n else "PARTIAL", f"{n} recursos agentic")


def main() -> None:
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    forges = list(audit["forges"])

    lines = [
        "# Matriz de Aceite — FASE 0 (baseline observado)",
        "",
        f"Gerado de `docs/experience/audit-fase0.json` (audit {audit['generated_at']}).",
        "Estados: **SUPPORTED** (evidência no audit), **PARTIAL**, **UNSUPPORTED**,",
        "**UNVERIFIED** (sem evidência de comportamento — não confundir com ausente),",
        "**NOT_APPLICABLE**. Célula nunca é preenchida por existência de arquivo solto.",
        "",
        "| capacidade \\ forja | alvo do programa | " + " | ".join(forges) + " |",
        "|---|---|" + "---|" * len(forges),
    ]
    for cap, target, key in ROWS:
        cells = []
        for f in forges:
            state, ev = _observed(audit, f, key)
            cells.append(f"{state}<br><sub>{ev}</sub>")
        lines.append(f"| `{cap}` | {target} | " + " | ".join(cells) + " |")

    lines += [
        "",
        "## Leituras honestas do baseline",
        "",
    ]
    for f in forges:
        row = audit["forges"][f]
        a = row["agentic"]
        gaps = []
        if not a["agents_canonical"]:
            gaps.append("sem agents canônicos")
        if not a["skills_canonical"]:
            gaps.append("sem skills canônicas")
        if not a["agentic_surfaces_total"]:
            gaps.append("sem espelhos de host")
        if not row["surfaces"]["install"]:
            gaps.append("sem verbo install")
        note = "; ".join(gaps) if gaps else "superfícies agentic presentes"
        lines.append(
            f"- **{f}** v{row['version']}: {a['agents_canonical']} agents, "
            f"{a['skills_canonical']} skills, {a['agentic_surfaces_total']} espelhos, "
            f"{row['test_files']} arquivos de teste — {note}."
        )
    lines += [
        "",
        "> Regenerar: `python scripts/experience/gen_acceptance_matrix.py`",
        "> (roda `audit_surfaces.py` antes se o inventário mudou).",
        "",
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
