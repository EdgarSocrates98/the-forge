"""Offline lab helpers stay compatible with dynamic Python version metadata."""

from pathlib import Path

from scripts.lab.theforge_lab import _declared_version


def test_declared_version_reads_hatch_path_without_importing_provider(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "fixture"
dynamic = ["version"]

[tool.hatch.version]
path = "src/fixture/__init__.py"
""".lstrip(),
        encoding="utf-8",
    )
    package = tmp_path / "src" / "fixture"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text('__version__ = "1.2.3"\n', encoding="utf-8")

    assert _declared_version(tmp_path, "fixture") == "1.2.3"


def test_declared_version_reads_setuptools_attr_without_importing_provider(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "fixture"
dynamic = ["version"]

[tool.setuptools.dynamic.version]
attr = "fixture.__version__"
""".lstrip(),
        encoding="utf-8",
    )
    package = tmp_path / "src" / "fixture"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text('__version__ = "2.3.4"\n', encoding="utf-8")

    assert _declared_version(tmp_path, "fixture") == "2.3.4"
