"""Regression: stray forge.json in an ancestor must not mark a project root."""

import shutil
import tempfile
from pathlib import Path

import pytest


@pytest.fixture()
def isolated_root():
    root = Path(tempfile.mkdtemp())
    yield root
    shutil.rmtree(root, ignore_errors=True)


def test_stray_forge_json_ancestor_is_not_a_root(isolated_root: Path) -> None:
    from theforge.ui import wizard

    (isolated_root / "forge.json").write_text("{}")
    inner = isolated_root / "a" / "b"
    inner.mkdir(parents=True)
    assert not wizard._has_vcs_root(inner)


def test_forge_json_with_pyproject_is_a_root(isolated_root: Path) -> None:
    from theforge.ui import wizard

    (isolated_root / "forge.json").write_text("{}")
    (isolated_root / "pyproject.toml").write_text("[project]\nname='x'\n")
    inner = isolated_root / "a" / "b"
    inner.mkdir(parents=True)
    assert wizard._has_vcs_root(inner)


def test_git_marker_remains_a_root(isolated_root: Path) -> None:
    from theforge.ui import wizard

    (isolated_root / ".git").mkdir()
    inner = isolated_root / "a" / "b"
    inner.mkdir(parents=True)
    assert wizard._has_vcs_root(inner)
