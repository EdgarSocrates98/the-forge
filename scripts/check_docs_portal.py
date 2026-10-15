"""Docs-portal gate (cyc10-02, §10.5/§10.7).

- all 18 §10.5 sections are covered in docs/portal/README.md;
- every relative link inside docs/portal/ resolves to a real file;
- every ``github.com/EdgarSocrates98/<repo>/blob/main/<path>`` link maps
  to a real file in the sibling checkout ``../<repo>/<path>`` — the
  program runs with all 9 repos side by side, so links stay honest;
- §10.6 positioning statement is present verbatim.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PORTAL = REPO / "docs" / "portal"
REPOS_ROOT = REPO.parent

SECTIONS_18 = [
    "Introdução",
    "Arquitetura",
    "Catálogo de Forjas",
    "Comparativo de capacidades",
    "Instalação",
    "Host setup",
    "Skills",
    "Agents",
    "MCP",
    "CLI",
    "Portal",
    "Graph Studio",
    "Forge Lab",
    "Contratos",
    "Troubleshooting",
    "FAQ",
    "Exemplos",
    "Contribuição",
]

POSITIONING = "ecossistema modular de ferramentas de engenharia agentic"

REL_LINK = re.compile(r"\]\((?!https?://|#)([^)]+)\)")
GH_LINK = re.compile(r"https://github\.com/EdgarSocrates98/([A-Za-z0-9_-]+)/blob/main/([^)\s]+)")


def main() -> int:
    fails: list[str] = []
    readme = PORTAL / "README.md"
    if not readme.is_file():
        print("docs/portal/README.md missing")
        return 1
    text = readme.read_text(encoding="utf-8")

    if POSITIONING not in text:
        fails.append("§10.6 positioning statement absent from portal landing")
    for sec in SECTIONS_18:
        if sec not in text:
            fails.append(f"§10.5 section '{sec}' absent from portal index")

    for f in PORTAL.rglob("*.md"):
        body = f.read_text(encoding="utf-8")
        for link in REL_LINK.findall(body):
            target = (f.parent / link.split("#")[0]).resolve()
            if link.split("#")[0] and not target.exists():
                fails.append(f"{f.relative_to(REPO)}: broken link '{link}'")
        for repo, path in GH_LINK.findall(body):
            if not (REPOS_ROOT / repo / path).exists():
                fails.append(
                    f"{f.relative_to(REPO)}: cross-repo link {repo}/{path} "
                    "has no file in the sibling checkout"
                )

    if fails:
        for x in fails:
            print(f"FAIL {x}")
        return 1
    print("docs portal: 18 sections, positioning verbatim, all links resolve")
    return 0


if __name__ == "__main__":
    sys.exit(main())
