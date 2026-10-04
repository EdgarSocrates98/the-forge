"""Higiene da raiz do repositório (agentic-maintainability, requisito 6).

Toda entrada da raiz precisa ter nome no padrão do projeto. Arquivos criados
por redirecionamento acidental de shell (``tuple[str``, ``dict[str``, ``(3``)
caem fora do padrão e falham o gate offline, identificando a entrada.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROOT_NAME = re.compile(r"^[A-Za-z0-9._-]+$")


def _bad_root_entries(root: Path) -> list[str]:
    return sorted(entry.name for entry in root.iterdir() if not ROOT_NAME.match(entry.name))


def test_repository_root_entries_follow_the_naming_pattern() -> None:
    bad = _bad_root_entries(REPO)
    assert not bad, f"entradas da raiz fora do padrão {ROOT_NAME.pattern}: {bad}"


def test_check_flags_entries_left_by_shell_redirection(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("ok", encoding="utf-8")
    (tmp_path / ".github").mkdir()
    for name in ("tuple[str", "dict[str", "(3"):
        (tmp_path / name).write_text("", encoding="utf-8")

    assert _bad_root_entries(tmp_path) == ["(3", "dict[str", "tuple[str"]


def test_check_accepts_project_style_names(tmp_path: Path) -> None:
    for name in ("pyproject.toml", ".gitignore", "AGENTS.md", "real-provider_v1.json"):
        (tmp_path / name).write_text("", encoding="utf-8")

    assert _bad_root_entries(tmp_path) == []
