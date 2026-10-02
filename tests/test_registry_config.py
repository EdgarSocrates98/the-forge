import sys
from pathlib import Path

import pytest

from theforge.errors import UsageError
from theforge.registry.config import builtin_entries, resolve_entries, user_config_dir


def test_builtin_echo_entry() -> None:
    entry = builtin_entries()[0]
    assert entry.id == "echo-forge" and entry.trust == "builtin"
    assert entry.argv[0] == sys.executable


def test_project_overrides_user_and_expands_python(tmp_path: Path) -> None:
    user = tmp_path / "user"
    user.mkdir()
    forge = tmp_path / ".forge"
    (forge / "config").mkdir(parents=True)
    (user / "providers.toml").write_text(
        '[[providers]]\nid = "x-forge"\nargv = ["x"]\ntrust = "trusted"\n', encoding="utf-8")
    (forge / "config" / "providers.toml").write_text(
        '[[providers]]\nid = "x-forge"\nargv = ["{python}", "x.py"]\n', encoding="utf-8")
    entries = {e.id: e for e in resolve_entries(forge, user)}
    assert entries["x-forge"].source == "project"
    assert entries["x-forge"].trust == "unverified"
    assert entries["x-forge"].argv == [sys.executable, "x.py"]
    assert "echo-forge" in entries


def _project(tmp_path: Path, body: str) -> Path:
    forge = tmp_path / ".forge"
    (forge / "config").mkdir(parents=True)
    (forge / "config" / "providers.toml").write_text(body, encoding="utf-8")
    return forge


def test_builtin_trust_is_reserved(tmp_path: Path) -> None:
    forge = _project(tmp_path, '[[providers]]\nid = "x"\nargv = ["x"]\ntrust = "builtin"\n')
    with pytest.raises(UsageError, match="reserved"):
        resolve_entries(forge, tmp_path / "none")


def test_empty_argv_rejected(tmp_path: Path) -> None:
    forge = _project(tmp_path, '[[providers]]\nid = "x"\nargv = []\n')
    with pytest.raises(UsageError, match="argv"):
        resolve_entries(forge, tmp_path / "none")


def test_malformed_toml(tmp_path: Path) -> None:
    forge = _project(tmp_path, "[[providers]\n")
    with pytest.raises(UsageError, match="cannot read"):
        resolve_entries(forge, tmp_path / "none")


def test_user_config_dir_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("THEFORGE_CONFIG_DIR", str(tmp_path))
    assert user_config_dir() == tmp_path
