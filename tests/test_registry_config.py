import os
import sys
from pathlib import Path

import pytest

from theforge.errors import UsageError
from theforge.registry.config import (
    ProviderEntry,
    builtin_entries,
    load_entries,
    resolve_entries,
    user_cache_dir,
    user_config_dir,
)
from theforge.registry.identity import ProviderFingerprint, fingerprint


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


# --- user cache dir (4.4/4.5) ---------------------------------------------------------------


def test_user_cache_dir_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("THEFORGE_CACHE_DIR", str(tmp_path / "c"))
    assert user_cache_dir() == tmp_path / "c"


def _no_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, platform: str) -> None:
    monkeypatch.delenv("THEFORGE_CACHE_DIR", raising=False)
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))


def test_user_cache_dir_windows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _no_override(monkeypatch, tmp_path, "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "lad"))
    assert user_cache_dir() == tmp_path / "lad" / "theforge" / "Cache"
    monkeypatch.delenv("LOCALAPPDATA")
    assert user_cache_dir() == tmp_path / "home" / "AppData" / "Local" / "theforge" / "Cache"


def test_user_cache_dir_darwin(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _no_override(monkeypatch, tmp_path, "darwin")
    assert user_cache_dir() == tmp_path / "home" / "Library" / "Caches" / "theforge"


def test_user_cache_dir_linux_xdg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _no_override(monkeypatch, tmp_path, "linux")
    xdg = tmp_path / "xdg"
    monkeypatch.setenv("XDG_CACHE_HOME", str(xdg))
    assert user_cache_dir() == xdg / "theforge"
    monkeypatch.setenv("XDG_CACHE_HOME", "relative/cache")
    assert user_cache_dir() == tmp_path / "home" / ".cache" / "theforge"
    monkeypatch.delenv("XDG_CACHE_HOME")
    assert user_cache_dir() == tmp_path / "home" / ".cache" / "theforge"


# --- relative argv resolution (5.4) ---------------------------------------------------------


def _write_toml(user: Path, argv_toml: str) -> Path:
    path = user / "providers.toml"
    path.write_text(f'[[providers]]\nid = "x-forge"\nargv = {argv_toml}\n', encoding="utf-8")
    return path


def test_relative_argv_script_resolved_against_config_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = tmp_path / "user"
    (user / "providers").mkdir(parents=True)
    script = user / "providers" / "forge.py"
    script.write_text("print('x')\n", encoding="utf-8")
    (user / "local.py").write_text("print('y')\n", encoding="utf-8")
    path = _write_toml(
        user, '["{python}", "providers/forge.py", "local.py", "-m", "pkg.mod", "x.py"]')
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    entry = load_entries(path, "user")[0]
    assert entry.argv == [
        sys.executable, str(script.resolve()), str((user / "local.py").resolve()),
        "-m", "pkg.mod", "x.py"]
    assert Path(entry.argv[1]).is_absolute() and Path(entry.argv[1]).is_file()


def test_relative_argv_dot_and_backslash_paths(tmp_path: Path) -> None:
    user = tmp_path / "user"
    (user / "sub").mkdir(parents=True)
    (user / "sub" / "f.py").write_text("", encoding="utf-8")
    expected = str((user / "sub" / "f.py").resolve())
    entry = load_entries(_write_toml(user, '["./sub/f.py"]'), "user")[0]
    assert entry.argv == [expected]
    if os.sep == "\\":
        entry = load_entries(_write_toml(user, "['sub\\f.py']"), "user")[0]
        assert entry.argv == [expected]


def test_missing_relative_path_argv_is_usage_error(tmp_path: Path) -> None:
    user = tmp_path / "user"
    user.mkdir()
    path = _write_toml(user, '["{python}", "providers/missing.py"]')
    with pytest.raises(UsageError, match="providers/missing.py"):
        load_entries(path, "user")
    path = _write_toml(user, "['{python}', 'providers\\missing.py']")
    with pytest.raises(UsageError, match="missing.py"):
        load_entries(path, "user")


def test_bare_command_and_absolute_argv_untouched(tmp_path: Path) -> None:
    user = tmp_path / "user"
    user.mkdir()
    (user / "python").write_text("", encoding="utf-8")
    absolute = str(tmp_path / "abs" / "not-there.py")
    entry = load_entries(_write_toml(user, f"['python', '{absolute}']"), "user")[0]
    assert entry.argv == ["python", absolute]


# --- provider fingerprint (4.5) -------------------------------------------------------------


def _script_entry(tmp_path: Path) -> tuple[ProviderEntry, Path]:
    script = tmp_path / "prov.py"
    script.write_text("print('v1')\n", encoding="utf-8")
    return ProviderEntry(id="x-forge", argv=[sys.executable, str(script), "--flag"]), script


def test_fingerprint_fields(tmp_path: Path) -> None:
    entry, script = _script_entry(tmp_path)
    fp = fingerprint(entry)
    assert isinstance(fp, ProviderFingerprint)
    assert fp.executable == sys.executable
    paths = [stat[0] for stat in fp.file_stats]
    assert str(script) in paths and sys.executable in paths
    st = script.stat()
    assert (str(script), st.st_size, st.st_mtime_ns) in fp.file_stats
    assert len(fp.digest) == 64 and fp.digest == fingerprint(entry).digest


def test_fingerprint_changes_with_mtime(tmp_path: Path) -> None:
    entry, script = _script_entry(tmp_path)
    before = fingerprint(entry).digest
    st = script.stat()
    os.utime(script, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
    assert fingerprint(entry).digest != before


def test_fingerprint_changes_with_size(tmp_path: Path) -> None:
    entry, script = _script_entry(tmp_path)
    st = script.stat()
    before = fingerprint(entry).digest
    script.write_text("print('version two')\n", encoding="utf-8")
    os.utime(script, ns=(st.st_atime_ns, st.st_mtime_ns))
    assert fingerprint(entry).digest != before


def test_fingerprint_resolves_bare_executable(monkeypatch: pytest.MonkeyPatch) -> None:
    import theforge.registry.identity as identity

    monkeypatch.setattr(identity.shutil, "which", lambda name: sys.executable)
    fp = fingerprint(ProviderEntry(id="x-forge", argv=["somecmd", "-m", "x"]))
    assert fp.executable == sys.executable
    monkeypatch.setattr(identity.shutil, "which", lambda name: None)
    fp = fingerprint(ProviderEntry(id="x-forge", argv=["nope-cmd"]))
    assert fp.executable == "nope-cmd" and fp.file_stats == []
