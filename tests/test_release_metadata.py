"""Release metadata must not drift across package and documentation surfaces."""

import re
import tomllib
from pathlib import Path

import theforge

ROOT = Path(__file__).parents[1]


def test_release_version_is_consistent() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = pyproject["project"]["version"]
    assert version == theforge.__version__
    assert version == "0.4.0"

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"on `{version}`" in readme
    assert f"### {version} — Cycle 5.1" in changelog


def test_cycle_41_is_not_falsely_marked_closed_while_remote_validation_is_blocked() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    report = (ROOT / "docs" / "reports" / "cycle-4.1.md").read_text(encoding="utf-8")
    # §56: the precise taxonomy is CLOSED_LOCALLY + REMOTE_VALIDATION_BLOCKED —
    # a bare COMPLETE/CLOSED would be an overclaim while remote CI is blocked.
    assert re.search(r"Cycle 4\.1: CLOSED_LOCALLY / REMOTE_VALIDATION_BLOCKED", readme)
    assert not re.search(r"Cycle 4\.1: (COMPLETE|CLOSED)\b(?!_LOCALLY)", readme)
    assert "REMOTE_VALIDATION_BLOCKED" in report
