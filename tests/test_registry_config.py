import sys
from pathlib import Path

import pytest

from theforge.errors import UsageError
from theforge.registry.config import builtin_entries, resolve_entries, user_config_dir


def test_builtin_echo_entry() -> None:
    entry = builtin_entries()[0]
    assert entry.id == "echo-forge" and entry.trust == "builtin"
    assert entry.argv[0] == sys.executable


def _project(tmp_path: Path, body: str) -> Path:
    forge = tmp_path / ".forge"
    (forge / "config").mkdir(parents=True)
    (forge / "config" / "providers.toml").write_text(body, encoding="utf-8")
    return forge


def _user(tmp_path: Path, body: str) -> Path:
    user = tmp_path / "user"
    user.mkdir()
    (user / "providers.toml").write_text(body, encoding="utf-8")
    return user


def test_project_trust_ignored_with_warning(tmp_path: Path) -> None:
    forge = _project(tmp_path, '[[providers]]\nid = "x-forge"\nargv = ["x"]\ntrust = "trusted"\n')
    warnings: list[str] = []
    entries = {e.id: e for e in resolve_entries(forge, tmp_path / "none", warnings)}
    assert entries["x-forge"].trust == "unverified" and entries["x-forge"].source == "project"
    assert len(warnings) == 1 and "x-forge" in warnings[0] and "ignored" in warnings[0]


def test_project_without_trust_unverified_and_expands_python(tmp_path: Path) -> None:
    forge = _project(tmp_path, '[[providers]]\nid = "x-forge"\nargv = ["{python}", "x.py"]\n')
    warnings: list[str] = []
    entries = {e.id: e for e in resolve_entries(forge, tmp_path / "none", warnings)}
    assert entries["x-forge"].trust == "unverified"
    assert entries["x-forge"].argv == [sys.executable, "x.py"]
    assert warnings == [] and "echo-forge" in entries


def test_user_trust_kept_and_wins_over_project(tmp_path: Path) -> None:
    user = _user(tmp_path, '[[providers]]\nid = "x-forge"\nargv = ["u"]\ntrust = "trusted"\n')
    forge = _project(tmp_path, '[[providers]]\nid = "x-forge"\nargv = ["p"]\n')
    warnings: list[str] = []
    entries = {e.id: e for e in resolve_entries(forge, user, warnings)}
    assert entries["x-forge"].source == "user" and entries["x-forge"].trust == "trusted"
    assert entries["x-forge"].argv == ["u"]
    assert any("already defined in user providers.toml" in w and "x-forge" in w for w in warnings)


def test_builtin_id_reserved_in_user_and_project(tmp_path: Path) -> None:
    body = '[[providers]]\nid = "echo-forge"\nargv = ["x"]\n'
    with pytest.raises(UsageError, match="reserved"):
        resolve_entries(None, _user(tmp_path, body))
    with pytest.raises(UsageError, match="reserved"):
        resolve_entries(_project(tmp_path, body), tmp_path / "none")


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
