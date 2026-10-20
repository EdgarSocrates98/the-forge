"""Regression tests for the canonical installkit bootstrap
(``scripts/installkit/forge_bootstrap.py``) interpreter specifier checks.

Two-component bounds like ``>=3.12`` previously collapsed to ``(0, 0, 0)``
because ``_semver_tuple`` only parsed three-part versions — making every
interpreter satisfy any floor and no interpreter satisfy any ceiling.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP_PATH = ROOT / "scripts" / "installkit" / "forge_bootstrap.py"

spec = importlib.util.spec_from_file_location("forge_bootstrap", BOOTSTRAP_PATH)
fb = importlib.util.module_from_spec(spec)
sys.modules["forge_bootstrap"] = fb
spec.loader.exec_module(fb)


def test_semver_tuple_pads_two_component():
    assert fb._semver_tuple("3.12") == (3, 12, 0)
    assert fb._semver_tuple("3") == (3, 0, 0)
    assert fb._semver_tuple("3.12.5") == (3, 12, 5)


def test_semver_tuple_unparseable_falls_back_zero():
    assert fb._semver_tuple("abc") == (0, 0, 0)


def test_satisfies_floor_accepts_newer_python():
    # 3.13/3.14+ must not be refused by an open floor (>=3.12).
    assert fb._satisfies("3.14.6", ">=3.12")
    assert fb._satisfies("3.13.1", ">=3.12")
    assert fb._satisfies("3.12.0", ">=3.12")


def test_satisfies_floor_refuses_older_python():
    assert not fb._satisfies("3.11.9", ">=3.12")
    assert not fb._satisfies("3.9.9", ">=3.10")


def test_satisfies_ceiling_still_works():
    assert fb._satisfies("3.14.6", ">=3.12,<3.15")
    assert not fb._satisfies("3.15.0", ">=3.12,<3.15")
    # the historical api-forge pin is only satisfiable by 3.12.x itself
    assert fb._satisfies("3.12.13", ">=3.12,<3.13")
    assert not fb._satisfies("3.13.0", ">=3.12,<3.13")


def test_environment_contract_is_account_scoped_and_shell_safe(tmp_path):
    cfg = {"forge_id": "spark-forge-aws", "cli": "sparkforge-aws"}
    venv = tmp_path / "install" / ".venv"
    contract = fb.environment_contract(cfg, tmp_path / "checkout", tmp_path / "install", venv, None)

    assert contract["schema"] == "forge/InstallEnvironment/v1"
    assert contract["scope"] == "user"
    assert contract["prefix"] == "SPARK_FORGE_AWS"
    assert contract["variables"]["SPARK_FORGE_AWS_HOME"].endswith("checkout")
    venv_value = contract["variables"]["SPARK_FORGE_AWS_VENV"].replace("\\", "/")
    cli_value = contract["variables"]["SPARK_FORGE_AWS_CLI"].replace("\\", "/")
    assert venv_value.endswith("install/.venv")
    assert cli_value.endswith("install/.venv/Scripts/sparkforge-aws.exe") or cli_value.endswith(
        "install/.venv/bin/sparkforge-aws"
    )


def test_env_prefix_normalizes_hyphenated_forge_ids():
    assert fb.env_prefix("the-forge") == "THE_FORGE"
    assert fb.env_prefix("forge.doctor-api") == "FORGE_DOCTOR_API"


def test_posix_environment_file_is_idempotent(tmp_path, monkeypatch):
    env_file = tmp_path / "config" / "forjas" / "env.sh"
    rc_file = tmp_path / ".profile"
    monkeypatch.setattr(fb, "_posix_env_paths", lambda: (env_file, rc_file))
    values = {"SPARK_FORGE_AWS_HOME": str(tmp_path / "checkout")}

    fb._persist_posix(values, None)
    fb._persist_posix(values, None)

    rendered = env_file.read_text(encoding="utf-8")
    assert rendered.count("# >>> forjas account environment >>>") == 1
    assert rendered.count("SPARK_FORGE_AWS_HOME") == 1
    assert rc_file.read_text(encoding="utf-8").count("forjas-account-environment") == 1


def test_detects_git_bash_native_windows(monkeypatch):
    monkeypatch.setattr(fb.os, "name", "nt")
    monkeypatch.setenv("MSYSTEM", "UCRT64")
    monkeypatch.delenv("OSTYPE", raising=False)
    assert fb._is_git_bash()


def test_rejects_unrelated_msystem_value(monkeypatch):
    monkeypatch.setattr(fb.os, "name", "nt")
    monkeypatch.setenv("MSYSTEM", "custom-shell")
    monkeypatch.setenv("OSTYPE", "windows")
    assert not fb._is_git_bash()


def test_git_bash_persistence_writes_registry_and_shell_init(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(fb.os, "name", "nt")
    monkeypatch.setattr(fb, "_is_git_bash", lambda: True)
    monkeypatch.setattr(
        fb,
        "_persist_windows",
        lambda values, aliases, shim: calls.append(("windows", values, aliases, shim)),
    )
    monkeypatch.setattr(
        fb,
        "_persist_posix",
        lambda values, shim, shell_shim=None: (
            calls.append(("git-bash", values, shim, shell_shim)) or str(tmp_path / "env.sh")
        ),
    )
    env = {
        "variables": {"FORGE_TEST_HOME": str(tmp_path)},
        "windows_aliases": {"FORGE-TEST-HOME": str(tmp_path)},
    }

    out = fb.persist_environment(env, tmp_path / "bin" / "forge-test", lambda _: None)

    assert [call[0] for call in calls] == ["windows", "git-bash"]
    assert out["persistence"] == "HKCU\\Environment + Git Bash shell-init"
    assert out["shell"] == "git-bash"
    assert out["shell_init"].endswith("env.sh")


def test_registry_has_value_uses_winreg_function(monkeypatch):
    calls = []

    def query_value(key, name):
        calls.append((key, name))
        return "value", 1

    monkeypatch.setitem(sys.modules, "winreg", types.SimpleNamespace(QueryValueEx=query_value))
    key = object()
    assert fb._registry_has_value(key, "Path")
    assert calls == [(key, "Path")]

    def missing(_key, _name):
        raise FileNotFoundError

    monkeypatch.setitem(sys.modules, "winreg", types.SimpleNamespace(QueryValueEx=missing))
    assert not fb._registry_has_value(key, "Missing")


# --------------------------------------------------------------------------
# --dist: published-distribution install path
# --------------------------------------------------------------------------


def test_split_dist_spec_bare_name():
    assert fb.split_dist_spec("sparkforge-aws") == ("sparkforge-aws", "")


def test_split_dist_spec_version():
    assert fb.split_dist_spec("sparkforge-aws==0.5.2") == ("sparkforge-aws", "==0.5.2")


def test_split_dist_spec_existing_extras():
    assert fb.split_dist_spec("sparkforge-aws[mcp]==0.5.2") == (
        "sparkforge-aws",
        "[mcp]==0.5.2",
    )


def test_compose_dist_req_inserts_extras_before_specifier():
    req = fb.compose_dist_req("sparkforge-aws==0.5.2", ["mcp"])
    assert req == "sparkforge-aws[mcp]==0.5.2"


def test_compose_dist_req_no_extras_returns_spec():
    assert fb.compose_dist_req("sparkforge-aws==0.5.2", []) == "sparkforge-aws==0.5.2"


def test_compose_dist_req_merges_declared_extras():
    req = fb.compose_dist_req("sparkforge-aws[mcp]==0.5.2", ["mcp", "web"])
    assert req == "sparkforge-aws[mcp,web]==0.5.2"


def test_environment_contract_omits_home_without_checkout(tmp_path):
    cfg = {"forge_id": "spark-forge-aws", "cli": "sparkforge-aws"}
    venv = tmp_path / "install" / ".venv"
    contract = fb.environment_contract(
        cfg,
        tmp_path / "config-dir",
        tmp_path / "install",
        venv,
        None,
        has_checkout=False,
    )
    assert "SPARK_FORGE_AWS_HOME" not in contract["variables"]
    assert "SPARK_FORGE_AWS_HOME" not in contract["windows_aliases"]


def _write_forge_json(path: Path) -> None:
    path.write_text(
        '{"forge_id": "spark-forge-aws", "package": "sparkforge_aws",'
        ' "distribution": "sparkforge-aws", "cli": "sparkforge-aws",'
        ' "python": ">=3.10"}'
    )


def test_dist_mode_conflict_refuses(tmp_path, capsys):
    _write_forge_json(tmp_path / "forge.json")
    code = fb.run(
        [
            "--repo",
            str(tmp_path),
            "--dist",
            "sparkforge-aws==0.5.2",
            "--editable",
            "--dry-run",
        ]
    )
    out = capsys.readouterr().out
    assert code == 2
    assert "FORGE-INSTALL-MODE-CONFLICT" in out


def test_dist_mismatch_refuses(tmp_path, capsys):
    _write_forge_json(tmp_path / "forge.json")
    code = fb.run(["--repo", str(tmp_path), "--dist", "outro-pacote==1.0", "--dry-run", "--quiet"])
    out = capsys.readouterr().out
    assert code == 2
    assert "FORGE-INSTALL-DIST-MISMATCH" in out


def test_dist_url_requires_allow_url(tmp_path, capsys):
    _write_forge_json(tmp_path / "forge.json")
    code = fb.run(
        [
            "--repo",
            str(tmp_path),
            "--dist",
            "forge-test @ https://example.com/x.whl",
            "--dry-run",
            "--quiet",
        ]
    )
    out = capsys.readouterr().out
    assert code == 2
    assert "FORGE-INSTALL-DIST-URL" in out


def test_dist_url_with_allow_url_passes_name_check(tmp_path, capsys):
    _write_forge_json(tmp_path / "forge.json")
    fb.run(
        [
            "--repo",
            str(tmp_path),
            "--dist",
            "sparkforge-aws @ https://example.com/x.whl",
            "--allow-url",
            "--dry-run",
            "--quiet",
        ]
    )
    out = capsys.readouterr().out
    assert "FORGE-INSTALL-DIST-URL" not in out
    assert "FORGE-INSTALL-DIST-MISMATCH" not in out


def test_dist_malformed_spec_returns_json_refusal(tmp_path, capsys):
    """Refusal fora do try principal nao pode virar traceback (review R7)."""
    _write_forge_json(tmp_path / "forge.json")
    code = fb.run(["--repo", str(tmp_path), "--dist", "==1.0", "--dry-run", "--quiet"])
    out = capsys.readouterr().out
    assert code == 2
    assert "FORGE-INSTALL-DIST-INVALID" in out


def test_dist_empty_string_refuses(tmp_path, capsys):
    """--dist '' e' falsy mas deve recusar, nao cair no checkout (review R9)."""
    _write_forge_json(tmp_path / "forge.json")
    code = fb.run(["--repo", str(tmp_path), "--dist", "", "--dry-run", "--quiet"])
    out = capsys.readouterr().out
    assert code == 2
    assert "FORGE-INSTALL-DIST-INVALID" in out


def test_dist_url_refusal_redacts_userinfo(tmp_path, capsys):
    """A recusa echoa o spec mas nunca a credencial embutida (§6.5)."""
    _write_forge_json(tmp_path / "forge.json")
    code = fb.run(
        [
            "--repo",
            str(tmp_path),
            "--dist",
            "theforge-core @ https://u:sekret@h/w.whl",
            "--dry-run",
            "--quiet",
        ]
    )
    out = capsys.readouterr().out
    assert code == 2
    assert "sekret" not in out
    assert "FORGE-INSTALL-DIST-URL" in out


def test_redact_url_userinfo_strips_credentials():
    assert fb.redact_url_userinfo("x @ https://u:t@host/f.whl") == "x @ https://***@host/f.whl"
    assert fb.redact_url_userinfo("x @ https://host/f.whl") == "x @ https://host/f.whl"


def test_install_package_never_leaks_url_credentials(tmp_path, monkeypatch):
    """R10: log e Refusal levam so' o spec redigido; stderr do pip tambe'm."""
    import subprocess

    lines: list[str] = []

    def fake_run(cmd, timeout=300, **kw):
        return subprocess.CompletedProcess(
            cmd, 2, "", "ERROR: no matching distribution 'https://u:sekret@h/x.whl'"
        )

    monkeypatch.setattr(fb, "_run", fake_run)
    dist = "theforge-core @ https://u:sekret@h/x.whl"
    try:
        fb.install_package(
            tmp_path, tmp_path / ".venv", ["mcp"], False, False, lines.append, dist=dist
        )
    except fb.Refusal as exc:
        detail = exc.detail
    else:  # pragma: no cover
        raise AssertionError("expected Refusal")
    blob = detail + "\n".join(lines)
    assert "sekret" not in blob
    assert "https://***@h/x.whl" in detail
    assert "theforge-core[mcp]" in detail  # spec composto, extras preservados
    assert any("theforge-core[mcp]" in line and "sekret" not in line for line in lines)


def test_dist_mismatch_refusal_redacts_userinfo(tmp_path, capsys):
    """R11: name-mismatch + URL com credencial nao ecoa userinfo (§6.5)."""
    _write_forge_json(tmp_path / "forge.json")
    code = fb.run(
        [
            "--repo",
            str(tmp_path),
            "--dist",
            "other-pkg @ https://u:sekret@h/x.whl",
            "--allow-url",
            "--dry-run",
            "--quiet",
        ]
    )
    out = capsys.readouterr().out
    assert code == 2
    assert "FORGE-INSTALL-DIST-MISMATCH" in out
    assert "sekret" not in out
    assert "https://***@h/x.whl" in out


def test_smoke_failure_never_writes_installation(tmp_path, monkeypatch, capsys):
    """Smoke FAIL → FORGE-INSTALL-VERIFY-FAILED antes do register:
    nenhum manifesto em installations/, nenhuma etapa 'register' no report."""
    _write_forge_json(tmp_path / "forge.json")
    monkeypatch.setenv("FORGE_HOME_OVERRIDE", str(tmp_path / "home"))
    monkeypatch.setattr(fb, "detect_hosts", lambda: {})
    monkeypatch.setattr(fb, "find_python", lambda *a, **k: sys.executable)
    monkeypatch.setattr(fb, "create_venv", lambda *a, **k: tmp_path / "venv")
    monkeypatch.setattr(fb, "install_package", lambda *a, **k: None)
    monkeypatch.setattr(fb, "write_launcher", lambda *a, **k: tmp_path / "shim")
    monkeypatch.setattr(fb, "smoke", lambda *a, **k: {"status": "FAIL", "detail": "boom"})
    registered = []
    monkeypatch.setattr(fb, "register", lambda *a, **k: registered.append(1))
    code = fb.run(["--repo", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 2
    assert "FORGE-INSTALL-VERIFY-FAILED" in out
    assert not registered
    manifests = [
        p
        for p in (tmp_path / "home").glob(".forge/installations/*.json")
        if not p.name.startswith(".")
    ]
    assert not manifests


# --------------------------------------------------------------------------
# lf-0018 — shared InstallReceipt contract: python{}, environment{shell,
# msystem, execution_environment}, source provenance, install_method,
# managed_files; FORGE-* surfacing.
# --------------------------------------------------------------------------


def _gitless_forge(path: Path, *, structure: bool = True) -> Path:
    """Gitless source fixture: forge.json (+ pyproject + the bootstrap
    file) with NO .git — the GITLESS_VALID_FORGE shape."""
    path.mkdir(parents=True, exist_ok=True)
    _write_forge_json(path / "forge.json")
    if structure:
        (path / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
        (path / "scripts").mkdir(exist_ok=True)
        (path / "scripts" / "forge_bootstrap.py").write_text("# vendored\n", encoding="utf-8")
    return path


def _stub_stages(monkeypatch, tmp_path):
    monkeypatch.setenv("FORGE_HOME_OVERRIDE", str(tmp_path / "home"))
    monkeypatch.setattr(fb, "detect_hosts", lambda: {})
    monkeypatch.setattr(fb, "create_venv", lambda *a, **k: tmp_path / "venv")
    monkeypatch.setattr(fb, "install_package", lambda *a, **k: None)
    monkeypatch.setattr(fb, "write_launcher", lambda *a, **k: tmp_path / "shim")
    monkeypatch.setattr(fb, "smoke", lambda *a, **k: {"status": "PASS", "version": "1.0.0"})


def _receipt(out: str) -> dict:
    return json.loads(out[out.index("{") :])


def test_source_provenance_gitless_valid(tmp_path):
    repo = _gitless_forge(tmp_path / "src")
    prov = fb._source_provenance(repo, manifest_valid=True)
    assert prov == {
        "is_git": False,
        "source_trust": "B",
        "manifest_valid": True,
        "integrity": "unverified",
    }


def test_source_provenance_gitless_partial(tmp_path):
    repo = _gitless_forge(tmp_path / "src", structure=False)
    prov = fb._source_provenance(repo, manifest_valid=True)
    assert prov["is_git"] is False
    assert prov["source_trust"] == "C"


def test_source_provenance_git_repo(tmp_path):
    repo = _gitless_forge(tmp_path / "src")
    (repo / ".git").mkdir()
    prov = fb._source_provenance(repo, manifest_valid=True)
    assert prov["is_git"] is True
    assert prov["source_trust"] == "B"  # checksums unverified → never A


def test_source_provenance_git_verified_checksums(tmp_path):
    repo = _gitless_forge(tmp_path / "src")
    (repo / ".git").mkdir()
    target = repo / "pyproject.toml"
    import hashlib

    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    (repo / "SHA256SUMS").write_text(f"{digest}  pyproject.toml\n", encoding="utf-8")
    prov = fb._source_provenance(repo, manifest_valid=True)
    assert prov["integrity"] == "verified"
    assert prov["source_trust"] == "A"


def test_source_provenance_worktree_caps_at_b(tmp_path):
    repo = _gitless_forge(tmp_path / "src")
    (repo / ".git").write_text("gitdir: /elsewhere/x\n", encoding="utf-8")
    import hashlib

    digest = hashlib.sha256((repo / "pyproject.toml").read_bytes()).hexdigest()
    (repo / "SHA256SUMS").write_text(f"{digest}  pyproject.toml\n", encoding="utf-8")
    prov = fb._source_provenance(repo, manifest_valid=True)
    assert prov["is_git"] is True
    assert prov["integrity"] == "verified"
    assert prov["source_trust"] == "B"  # worktree file, not a repo dir


def test_checksum_integrity_partial_on_divergence(tmp_path):
    repo = _gitless_forge(tmp_path / "src")
    (repo / "SHA256SUMS").write_text(
        "0" * 64 + "  pyproject.toml\n" + "1" * 64 + "  missing.txt\n", encoding="utf-8"
    )
    assert fb._checksum_integrity(repo) == "partial"


def test_checksum_integrity_partial_on_traversal(tmp_path):
    repo = _gitless_forge(tmp_path / "src")
    (repo / "checksums.sha256").write_text("a" * 64 + "  ../outside.txt\n", encoding="utf-8")
    assert fb._checksum_integrity(repo) == "partial"


def test_checksum_integrity_unverified_without_manifest(tmp_path):
    repo = _gitless_forge(tmp_path / "src")
    assert fb._checksum_integrity(repo) == "unverified"


def test_explicit_python_argv_never_splits_real_path(tmp_path):
    spaced = tmp_path / "dir with space" / "python"
    spaced.parent.mkdir()
    spaced.write_text("", encoding="utf-8")
    assert fb._explicit_python_argv(str(spaced)) == [str(spaced)]
    assert fb._explicit_python_argv("py -3.11") == ["py", "-3.11"]
    assert fb._explicit_python_argv("python3") == ["python3"]


def test_find_python_fills_provenance_for_explicit(tmp_path):
    prov: dict = {}
    exe = fb.find_python(">=3.0", sys.executable, False, lambda _m: None, prov)
    assert exe == sys.executable or exe.endswith("python")
    assert prov["source"] == "explicit"
    assert prov["version"]


def test_find_python_fills_provenance_for_path_scan():
    prov: dict = {}
    exe = fb.find_python(">=3.0", None, False, lambda _m: None, prov)
    assert exe
    assert prov["source"] == "path"
    assert "PATH" in prov["selection_reason"]


def test_receipt_gitless_carries_contract_fields(tmp_path, monkeypatch, capsys):
    """The fixture-based parity case: a gitless install emits a receipt
    with is_git:false + source_trust + manifest_valid + the python{} and
    environment{} contract objects — same names as forge-cli's receipt."""
    repo = _gitless_forge(tmp_path / "src")
    _stub_stages(monkeypatch, tmp_path)
    code = fb.run(["--repo", str(repo), "--python", sys.executable])
    rcpt = _receipt(capsys.readouterr().out)
    assert code == 0
    assert rcpt["schema"] == "forge/InstallReceipt/v1"
    assert rcpt["is_git"] is False
    assert rcpt["source_trust"] == "B"
    assert rcpt["manifest_valid"] is True
    assert rcpt["integrity"] == "unverified"
    assert rcpt["install_method"] == "wheel"
    py = rcpt["python"]
    assert py["source"] == "flag"
    assert py["executable"] == sys.executable
    assert py["version"] and py["selection_reason"]
    env = rcpt["environment"]
    assert env["schema"] == "forge/InstallEnvironment/v1"
    assert env["execution_environment"] in ("posix", "windows", "git-bash")
    assert env["shell"]
    managed = rcpt["managed_files"]
    assert str(tmp_path / "home" / ".forge" / "installs" / "spark-forge-aws") in managed
    assert any(p.endswith("spark-forge-aws.json") for p in managed)
    assert any(p.endswith(".spark-forge-aws-bootstrap.json") for p in managed)


def test_receipt_forge_python_env_marks_source_env(tmp_path, monkeypatch, capsys):
    repo = _gitless_forge(tmp_path / "src")
    _stub_stages(monkeypatch, tmp_path)
    monkeypatch.setenv("FORGE_PYTHON", sys.executable)
    code = fb.run(["--repo", str(repo)])
    rcpt = _receipt(capsys.readouterr().out)
    assert code == 0
    assert rcpt["python"]["source"] == "env"
    assert rcpt["python"]["version"]


def test_receipt_managed_files_parity_between_routes(tmp_path, monkeypatch):
    """install.sh-route vs install.windows.sh-route: the managed set
    differs only by the artifacts each platform owns (.cmd launcher on
    nt) — stages, fields and semantics are identical. The home/shim/env
    roots are stubbed so `os.name` can flip without WindowsPath."""
    cfg = {
        "forge_id": "spark-forge-aws",
        "cli": "sparkforge-aws",
    }
    monkeypatch.setattr(fb, "forge_home", lambda: tmp_path / "home" / ".forge")
    monkeypatch.setattr(fb, "shim_dir", lambda: tmp_path / "shim")
    monkeypatch.setattr(fb, "_posix_env_paths", lambda: (tmp_path / "env.sh", tmp_path / "rc"))

    monkeypatch.setattr(fb.os, "name", "posix")
    monkeypatch.setattr(fb, "_is_git_bash", lambda: False)
    posix_set = set(fb.managed_files(cfg, tmp_path / "install", True, False))

    monkeypatch.setattr(fb.os, "name", "nt")
    monkeypatch.setattr(fb, "_is_git_bash", lambda: True)
    gitbash_set = set(fb.managed_files(cfg, tmp_path / "install", True, False))

    common = posix_set & gitbash_set
    assert str(tmp_path / "install") in common
    assert any(p.endswith("spark-forge-aws.json") for p in common)
    assert any(p.endswith("env.sh") for p in common)  # Git Bash keeps env.sh too
    # The delta is exactly the Windows .cmd companion launcher.
    assert gitbash_set - posix_set == {
        str(tmp_path / "shim" / "sparkforge-aws.cmd"),
    }
    assert not (posix_set - gitbash_set)


def test_receipt_git_bash_environment_fields(tmp_path, monkeypatch, capsys):
    """Under simulated Git Bash (_is_git_bash + MSYSTEM) the environment
    block marks shell/execution_environment 'git-bash' and carries
    msystem — the fields that legitimately differ between shell routes."""
    repo = _gitless_forge(tmp_path / "src")
    _stub_stages(monkeypatch, tmp_path)
    # _shell_label/_execution_environment consult _is_git_bash() first —
    # no os.name flip needed (it would force WindowsPath on POSIX).
    monkeypatch.setattr(fb, "_is_git_bash", lambda: True)
    monkeypatch.setenv("MSYSTEM", "MINGW64")
    monkeypatch.setattr(fb, "_posix_env_paths", lambda: (tmp_path / "env.sh", tmp_path / "rc"))
    persisted = []
    monkeypatch.setattr(
        fb,
        "persist_environment",
        lambda env, shim, log: persisted.append(env) or env,
    )
    code = fb.run(["--repo", str(repo), "--persist-env", "--python", sys.executable])
    rcpt = _receipt(capsys.readouterr().out)
    assert code == 0
    env = rcpt["environment"]
    assert env["shell"] == "git-bash"
    assert env["execution_environment"] == "git-bash"
    assert env["msystem"] == "MINGW64"
    assert persisted  # --persist-env ran the persist stage


def test_persist_failure_is_named_refusal(tmp_path, monkeypatch, capsys):
    """OS-level persistence failure → FORGE-ENV-PERSISTENCE-FAILED in the
    receipt's error{kind,detail} — never a bare traceback."""
    repo = _gitless_forge(tmp_path / "src")
    _stub_stages(monkeypatch, tmp_path)

    def boom(_env, _shim, _log):
        raise OSError("permission denied")

    monkeypatch.setattr(fb, "persist_environment", boom)
    code = fb.run(["--repo", str(repo), "--persist-env", "--python", sys.executable])
    rcpt = _receipt(capsys.readouterr().out)
    assert code == 2
    assert rcpt["error"]["kind"] == "FORGE-ENV-PERSISTENCE-FAILED"
    stage = next(s for s in rcpt["stages"] if s["stage"] == "persist-environment")
    assert stage["status"] == "refused"
    assert stage["kind"] == "FORGE-ENV-PERSISTENCE-FAILED"
