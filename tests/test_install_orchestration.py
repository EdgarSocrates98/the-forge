"""Orchestration tests for ``theforge install`` (ADR-0058, forge/* v1).

Drives ``theforge.install.service`` in-process against tmp consumer roots:
approval gating, ownership, drift/repair, uninstall and the ``install auto``
family delegation (isolated via FORGE_HOME_OVERRIDE).
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import pytest

from theforge import _installkit as kit
from theforge.install import service

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def target(tmp_path: Path) -> Path:
    d = tmp_path / "consumer"
    d.mkdir()
    return d


@pytest.fixture()
def forge_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("FORGE_HOME_OVERRIDE", str(home))
    return home


def test_vendored_kit_matches_canonical() -> None:
    def _norm(p: Path) -> bytes:
        # Vendored copies carry the stamped canonical hash where the source
        # has the literal "canonical" — normalize before comparing.
        return re.sub(
            rb'_SOURCE_SHA256 = "[0-9a-f]+"', rb'_SOURCE_SHA256 = "canonical"', p.read_bytes()
        )

    canon = _norm(ROOT / "scripts" / "installkit" / "forge_installkit.py")
    vend = _norm(ROOT / "src" / "theforge" / "_installkit.py")
    assert hashlib.sha256(vend).digest() == hashlib.sha256(canon).digest()


def test_apply_requires_approval(target: Path) -> None:
    with pytest.raises(kit.InstallError) as exc:
        service.install(scope="project", root=target)
    assert exc.value.kind == kit.E_NOTAPPROVED


def test_apply_dry_run_writes_nothing(target: Path) -> None:
    receipt = service.install(scope="project", root=target, dry_run=True)
    assert receipt["status"] == "planned"
    assert not (target / ".claude").exists()
    assert not (target / ".forge").exists()


def test_full_lifecycle(target: Path) -> None:
    receipt = service.install(scope="project", root=target, yes=True)
    assert receipt["status"] == "completed"
    assert receipt["verification"]["status"] == "PASS"
    assert (target / ".agents" / "skills").is_dir()
    assert (target / ".claude" / "skills").is_dir()
    assert (target / "AGENTS.md").exists()

    st = service.status(scope="project", root=target)
    assert st["status"] == "healthy"
    assert st["drift"]["missing"] == []

    # user-modified managed file -> drift -> repair re-asserts managed bytes
    skill = next((target / ".agents" / "skills").rglob("SKILL.md"))
    skill.write_text("user edit", encoding="utf-8")
    doc = service.doctor(scope="project", root=target)
    assert doc["status"] == "degraded"
    fixed = service.repair(scope="project", root=target)
    assert fixed["status"] == "completed"
    assert service.status(scope="project", root=target)["status"] == "healthy"

    out = service.uninstall(scope="project", root=target)
    assert out["status"] == "completed"
    assert not (target / ".agents" / "skills").exists()
    assert not (target / ".claude" / "skills").exists()
    assert not (target / "AGENTS.md").exists()


def test_apply_preserves_user_agents(target: Path) -> None:
    (target / "AGENTS.md").write_text("# my rules\nuser content\n", "utf-8")
    service.install(scope="project", root=target, yes=True, host="claude")
    body = (target / "AGENTS.md").read_text("utf-8")
    assert "user content" in body and "the-forge:managed" in body
    service.uninstall(scope="project", root=target)
    body = (target / "AGENTS.md").read_text("utf-8")
    assert "user content" in body and "the-forge:managed" not in body


def test_host_filter(target: Path) -> None:
    service.install(scope="project", root=target, yes=True, host="claude")
    assert (target / ".claude" / "skills").is_dir()
    assert not (target / ".devin").exists()
    assert not (target / ".github").exists()


def test_profile_minimal_installs_markers_only(target: Path) -> None:
    service.install(scope="project", root=target, yes=True, profile="minimal")
    assert (target / "AGENTS.md").exists()
    assert not (target / ".claude" / "skills").exists()


def test_profile_recommended_installs_agents(target: Path) -> None:
    service.install(scope="project", root=target, yes=True, profile="recommended")
    assert (target / ".codex" / "agents").is_dir()


def test_unknown_host_and_profile(target: Path) -> None:
    with pytest.raises(kit.InstallError) as exc:
        service.install("zsh", scope="project", root=target, yes=True)
    assert exc.value.kind == kit.E_HOST
    with pytest.raises(kit.InstallError) as exc:
        service.install(scope="project", root=target, yes=True, profile="mega")
    assert exc.value.kind == kit.E_PROFILE


def test_workspace_scope(target: Path) -> None:
    sub = target / "ws" / "repo"
    sub.mkdir(parents=True)
    receipt = service.install(scope="workspace", root=target / "ws", yes=True, host="codex")
    assert receipt["status"] == "completed"
    assert (target / "ws" / ".agents" / "skills").is_dir()


def test_update_rejects_latest(forge_home: Path) -> None:
    out = service.update(to="latest")
    assert out["status"] == "failed"
    assert "'latest'" in out["checks"][0]["detail"]


def test_uninstall_without_install_is_idempotent(target: Path) -> None:
    """Uninstall on a never-installed root is a no-op, not a refusal."""
    out = service.uninstall(scope="project", root=target)
    assert out["status"] == "completed"
    assert out["removed"] == []
    assert not (target / ".forge").exists()  # no-op writes no state


# --------------------------------------------------------------------------
# install auto — family delegation (registry isolated via FORGE_HOME_OVERRIDE)
# --------------------------------------------------------------------------


def test_auto_empty_registry(forge_home: Path, target: Path) -> None:
    out = service.install_auto(scope="project", root=target, yes=True)
    assert out["status"] == "failed"
    assert out["checks"][0]["id"] == "registry"
    assert out["checks"][0]["status"] == "BLOCKED"


def test_auto_refuses_without_yes(forge_home: Path, target: Path) -> None:
    (forge_home / ".forge" / "installations").mkdir(parents=True)
    (forge_home / ".forge" / "installations" / "api-forge.json").write_text(
        '{"forge_id": "api-forge", "cli": {"name": "apiforge"}}', "utf-8"
    )
    out = service.install_auto(scope="project", root=target)
    assert out["forges"][0]["status"] == "refused"
    assert out["status"] == "failed"


def test_auto_dry_run_plans_delegation(forge_home: Path, target: Path) -> None:
    (forge_home / ".forge" / "installations").mkdir(parents=True)
    (forge_home / ".forge" / "installations" / "the-forge.json").write_text(
        '{"forge_id": "the-forge", "cli": {"name": "theforge"}}', "utf-8"
    )
    out = service.install_auto(scope="project", root=target, dry_run=True)
    assert out["status"] == "planned"
    assert out["forges"][0]["via"] == "self"


def test_auto_self_installs_in_process(forge_home: Path, target: Path) -> None:
    (forge_home / ".forge" / "installations").mkdir(parents=True)
    (forge_home / ".forge" / "installations" / "the-forge.json").write_text(
        '{"forge_id": "the-forge", "cli": {"name": "theforge"}}', "utf-8"
    )
    out = service.install_auto(scope="project", root=target, yes=True)
    assert out["status"] == "completed"
    assert (target / ".agents" / "skills").is_dir()


def test_auto_forge_filter(forge_home: Path, target: Path) -> None:
    inst = forge_home / ".forge" / "installations"
    inst.mkdir(parents=True)
    (inst / "the-forge.json").write_text(
        '{"forge_id": "the-forge", "cli": {"name": "theforge"}}', "utf-8"
    )
    (inst / "ghost.json").write_text(
        '{"forge_id": "ghost", "cli": {"name": "definitely-not-a-cli-xyz"}}', "utf-8"
    )
    out = service.install_auto(scope="project", root=target, yes=True, forge="the-forge")
    assert [f["forge_id"] for f in out["forges"]] == ["the-forge"]
    assert out["status"] == "completed"
    with pytest.raises(kit.InstallError) as exc:
        service.install_auto(scope="project", root=target, yes=True, forge="nope")
    assert exc.value.kind == kit.E_NOTINSTALLED


def test_auto_reports_missing_cli(forge_home: Path, target: Path) -> None:
    (forge_home / ".forge" / "installations").mkdir(parents=True)
    (forge_home / ".forge" / "installations" / "ghost.json").write_text(
        '{"forge_id": "ghost", "cli": {"name": "definitely-not-a-cli-xyz"}}', "utf-8"
    )
    out = service.install_auto(scope="project", root=target, yes=True)
    assert out["status"] == "failed"
    assert out["checks"][0]["status"] == "BLOCKED"
    assert "definitely-not-a-cli-xyz" in out["checks"][0]["detail"]


def test_installations_list_reads_registry(forge_home: Path) -> None:
    assert service.installations() == []
    (forge_home / ".forge" / "installations").mkdir(parents=True)
    (forge_home / ".forge" / "installations" / "x.json").write_text(
        '{"forge_id": "x", "version": "1.0.0"}', "utf-8"
    )
    rows = service.installations()
    assert [r["forge_id"] for r in rows] == ["x"]


def test_delegated_cmd_install_command_template() -> None:
    """A forge whose package boundary forbids the install engine registers
    an ``install_command`` argv template — {python}/{checkout} resolve to
    the manifest's venv interpreter and source path."""
    manifest = {
        "forge_id": "forge-doctor-api",
        "cli": {"name": "forge-doctor-api"},
        "venv": "C:/v/fda",
        "source": {"path": "E:/checkouts/forge-doctor-api"},
        "install_command": ["{python}", "{checkout}/scripts/forge_install.py"],
    }
    argv = service._delegated_cmd(manifest, "project", Path("T"), True)
    assert argv[2:5] == ["install", "--scope", "project"]
    assert argv[-1] == "--dry-run"
    assert "forge_install.py" in argv[1]
    assert argv[1].startswith("E:/checkouts/forge-doctor-api")
    # venv python missing on disk -> sys.executable fallback
    assert argv[0] == sys.executable


def test_delegated_cmd_default_cli() -> None:
    argv = service._delegated_cmd(
        {"forge_id": "x", "cli": {"name": "x-cli"}}, "user", Path("T"), False
    )
    assert argv[0] == "x-cli"


def test_delegated_cmd_propagates_setup_choices() -> None:
    argv = service._delegated_cmd(
        {"forge_id": "x", "cli": {"name": "x-cli"}},
        "workspace",
        Path("T"),
        True,
        host="none",
        profile="minimal",
        components=("mcp", "tui"),
    )
    assert argv == [
        "x-cli",
        "install",
        "--scope",
        "workspace",
        "--root",
        "T",
        "--host",
        "none",
        "--profile",
        "minimal",
        "--components",
        "mcp,tui",
        "--dry-run",
    ]


def test_install_auto_self_persists_execution_profile(forge_home: Path, target: Path) -> None:
    inst = forge_home / ".forge" / "installations"
    inst.mkdir(parents=True)
    (inst / "the-forge.json").write_text(
        '{"forge_id": "the-forge", "cli": {"name": "theforge"}}', "utf-8"
    )
    out = service.install_auto(
        scope="project",
        root=target,
        host="none",
        profile="minimal",
        components=("mcp", "tui"),
        gateway_profile="economy",
        yes=True,
    )
    assert out["status"] == "completed"
    state = json.loads((target / ".forge" / "install" / "components.json").read_text("utf-8"))
    assert state["execution_profile"] == "economy"


def test_setup_and_auto_parser_expose_governed_choices() -> None:
    from theforge.cli.main import build_parser

    parser = build_parser()
    setup = parser.parse_args(
        [
            "setup",
            "--scope",
            "workspace",
            "--host",
            "none",
            "--profile",
            "minimal",
            "--components",
            "mcp,tui",
            "--gateway-profile",
            "economy",
            "--dry-run",
        ]
    )
    assert setup.command == "setup"
    assert setup.scope == "workspace"
    assert setup.host == "none"
    assert setup.profile == "minimal"
    assert setup.components == "mcp,tui"

    auto = parser.parse_args(
        ["install", "auto", "--host", "codex", "--profile", "full", "--components", "skills"]
    )
    assert auto.host == "codex"
    assert auto.profile == "full"
    assert auto.components == "skills"


def test_ask_parser_exposes_one_step_auto_install() -> None:
    from theforge.cli.main import build_parser

    parser = build_parser()
    args = parser.parse_args(
        [
            "ask",
            "analyze api",
            "--auto-install",
            "--install-profile",
            "minimal",
            "--install-host",
            "none",
            "--gateway-profile",
            "economy",
            "--install-components",
            "mcp,tui",
            "--yes",
        ]
    )
    assert args.auto_install is True
    assert args.install_profile == "minimal"
    assert args.install_host == "none"
    assert args.gateway_profile == "economy"
    assert args.install_components == "mcp,tui"


# install auto --scope workspace — member discovery, precedence, manifest
# --------------------------------------------------------------------------

_STUB = "import sys; sys.exit(0)"


def _workspace(tmp_path: Path, *members: str) -> Path:
    ws = tmp_path / "ws"
    for m in members:
        (ws / m / ".git").mkdir(parents=True)
    (ws / "not-a-repo").mkdir(parents=True)
    return ws


def _register_stub_forge(forge_home: Path, fid: str = "fake-forge") -> None:
    inst = forge_home / ".forge" / "installations"
    inst.mkdir(parents=True, exist_ok=True)
    stub = forge_home / f"{fid}-stub.py"
    stub.write_text(_STUB, "utf-8")
    (inst / f"{fid}.json").write_text(
        json.dumps(
            {
                "forge_id": fid,
                "cli": {"name": fid},
                "install_command": ["{python}", str(stub).replace("\\", "/")],
            }
        ),
        "utf-8",
    )


def test_workspace_discovers_members(forge_home: Path, tmp_path: Path) -> None:
    ws = _workspace(tmp_path, "backend-api", "spark-jobs", "terraform")
    _register_stub_forge(forge_home)
    out = service.install_auto(scope="workspace", root=ws, yes=True)
    assert out["status"] == "completed"
    paths = [m["path"] for m in out["workspace"]["members"]]
    assert paths == ["backend-api", "spark-jobs", "terraform"]
    manifest = json.loads((ws / ".forge" / "workspace-install.json").read_text("utf-8"))
    assert manifest["schema"] == "forge/WorkspaceInstall/v1"
    assert manifest["workspace_root"] == str(ws.resolve())
    assert manifest["projects"] == []  # no --member, no member installs


def test_workspace_member_fanout(forge_home: Path, tmp_path: Path) -> None:
    ws = _workspace(tmp_path, "backend-api", "spark-jobs")
    _register_stub_forge(forge_home)
    out = service.install_auto(scope="workspace", root=ws, yes=True, members=("backend-api",))
    results = out["workspace"]["member_results"]
    assert [(r["member"], r["status"]) for r in results] == [("backend-api", "completed")]
    manifest = json.loads((ws / ".forge" / "workspace-install.json").read_text("utf-8"))
    assert [p["path"] for p in manifest["projects"]] == ["backend-api"]
    assert manifest["projects"][0]["forge_id"] == "fake-forge"


def test_workspace_unknown_member_reported(forge_home: Path, tmp_path: Path) -> None:
    ws = _workspace(tmp_path, "backend-api")
    _register_stub_forge(forge_home)
    out = service.install_auto(scope="workspace", root=ws, yes=True, members=("ghost",))
    assert out["workspace"]["unknown_members"] == ["ghost"]
    assert out["workspace"]["member_results"] == []


def test_workspace_project_precedence_conflict(forge_home: Path, tmp_path: Path) -> None:
    ws = _workspace(tmp_path, "backend-api")
    (ws / "backend-api" / "AGENTS.md").write_text(
        "<!-- fake-forge:managed:begin -->x<!-- fake-forge:managed:end -->", "utf-8"
    )
    _register_stub_forge(forge_home)
    out = service.install_auto(scope="workspace", root=ws, yes=True)
    conflicts = out["workspace"]["conflicts"]
    assert [(c["member"], c["forge_id"], c["decision"]) for c in conflicts] == [
        ("backend-api", "fake-forge", "project")
    ]


def test_workspace_dry_run_writes_nothing(forge_home: Path, tmp_path: Path) -> None:
    ws = _workspace(tmp_path, "backend-api")
    _register_stub_forge(forge_home)
    out = service.install_auto(scope="workspace", root=ws, dry_run=True, members=("backend-api",))
    assert out["status"] == "planned"
    assert out["workspace"]["member_results"][0]["status"] == "planned"
    assert not (ws / ".forge" / "workspace-install.json").exists()
    assert not (ws / "backend-api" / ".mcp.json").exists()


def test_workspace_manifest_merges_incrementally(forge_home: Path, tmp_path: Path) -> None:
    ws = _workspace(tmp_path, "backend-api", "spark-jobs")
    _register_stub_forge(forge_home)
    service.install_auto(scope="workspace", root=ws, yes=True, members=("backend-api",))
    first = json.loads((ws / ".forge" / "workspace-install.json").read_text("utf-8"))
    service.install_auto(scope="workspace", root=ws, yes=True, members=("spark-jobs",))
    merged = json.loads((ws / ".forge" / "workspace-install.json").read_text("utf-8"))
    assert merged["created_at"] == first["created_at"]
    assert [p["path"] for p in merged["projects"]] == ["backend-api", "spark-jobs"]


def test_hosts_contract_all_none_csv_unknown(tmp_path: Path) -> None:
    """GAP-003 contract: none -> zero hosts; csv subset validated; unknown
    -> E_HOST refusal with the known set in the message."""
    from theforge._installkit import InstallError
    from theforge.install import render, service

    assert service._hosts("all") == render.HOSTS
    assert service._hosts("none") == ()
    assert service._hosts(None) == ()
    first = render.HOSTS[0]
    assert service._hosts(first) == (first,)
    if len(render.HOSTS) > 1:
        assert service._hosts(f"{first},{render.HOSTS[1]}") == (first, render.HOSTS[1])
    with pytest.raises(InstallError):
        service._hosts("emacs")


def test_wizard_opt_out_installs_no_host_assets(tmp_path: Path) -> None:
    """End-to-end of the contract: host='none' must not write any host
    mirror dir — the bug wrote all of them."""
    target = tmp_path / "consumer"
    target.mkdir()
    receipt = service.install(scope="project", root=target, yes=True, host="none")
    assert receipt["status"] == "completed"
    assert not (target / ".mcp.json").exists()


def test_update_pypi_uses_pip_upgrade_spec(monkeypatch, forge_home: Path, tmp_path: Path) -> None:
    fake_py = tmp_path / "bin" / "python"
    fake_py.parent.mkdir()
    fake_py.write_text("")
    monkeypatch.setattr(
        service,
        "_manifest",
        lambda: {
            "source": {"kind": "pypi", "spec": "theforge-core[mcp]==1.2.3"},
            "distribution": "theforge-core",
            "venv": str(tmp_path),
        },
    )
    out = service.update(dry_run=True)
    assert out["status"] == "planned"
    assert "pip" in out["checks"][0]["id"]
    assert "theforge-core[mcp]==1.2.3" in out["checks"][0]["detail"]
    assert "--upgrade" in out["checks"][0]["detail"]


def test_update_pypi_without_spec_or_dist_blocks(monkeypatch, forge_home: Path) -> None:
    monkeypatch.setattr(service, "_manifest", lambda: {"source": {"kind": "pypi"}, "venv": "/v"})
    out = service.update(dry_run=True)
    assert out["status"] == "failed"
    assert out["checks"][0]["status"] == "BLOCKED"


def test_update_pypi_to_composes_pin(monkeypatch, forge_home: Path, tmp_path: Path) -> None:
    fake_py = tmp_path / "bin" / "python"
    fake_py.parent.mkdir()
    fake_py.write_text("")
    monkeypatch.setattr(
        service,
        "_manifest",
        lambda: {
            "source": {"kind": "pypi", "spec": "theforge-core==1.0.0"},
            "distribution": "theforge-core",
            "venv": str(tmp_path),
        },
    )
    out = service.update(to="0.5.2", dry_run=True)
    assert out["status"] == "planned"
    assert "theforge-core==0.5.2" in out["checks"][0]["detail"]


def test_update_pypi_to_without_distribution_blocks(monkeypatch, forge_home: Path) -> None:
    monkeypatch.setattr(
        service,
        "_manifest",
        lambda: {"source": {"kind": "pypi", "spec": "x==1"}, "venv": "/v"},
    )
    out = service.update(to="0.5.2", dry_run=True)
    assert out["status"] == "failed"
    assert out["checks"][0]["status"] == "BLOCKED"


def test_update_missing_venv_python_fails(monkeypatch, forge_home: Path) -> None:
    monkeypatch.setattr(
        service,
        "_manifest",
        lambda: {
            "source": {"kind": "pypi", "spec": "x==1"},
            "distribution": "x",
            "venv": "/nonexistent-venv",
        },
    )
    out = service.update()
    assert out["status"] == "failed"
    assert "venv" in out["checks"][0]["id"]


def test_update_pypi_to_preserves_extras(monkeypatch, forge_home: Path, tmp_path: Path) -> None:
    fake_py = tmp_path / "bin" / "python"
    fake_py.parent.mkdir()
    fake_py.write_text("")
    monkeypatch.setattr(
        service,
        "_manifest",
        lambda: {
            "source": {"kind": "pypi", "spec": "theforge-core[mcp]==1.0.0"},
            "distribution": "theforge-core",
            "venv": str(tmp_path),
        },
    )
    out = service.update(to="0.5.2", dry_run=True)
    assert "theforge-core[mcp]==0.5.2" in out["checks"][0]["detail"]


def test_update_pypi_spec_name_divergence_blocks(
    monkeypatch, forge_home: Path, tmp_path: Path
) -> None:
    fake_py = tmp_path / "bin" / "python"
    fake_py.parent.mkdir()
    fake_py.write_text("")
    monkeypatch.setattr(
        service,
        "_manifest",
        lambda: {
            "source": {"kind": "pypi", "spec": "outro-pacote==1.0.0"},
            "distribution": "theforge-core",
            "venv": str(tmp_path),
        },
    )
    out = service.update(dry_run=True)
    assert out["status"] == "failed"
    assert "diverge" in out["checks"][0]["detail"]


def test_update_pypi_with_repo_fails_named(monkeypatch, forge_home: Path) -> None:
    # --repo num manifesto pypi trocaria a origem: recusa nomeada, nao ignora.
    monkeypatch.setattr(
        service,
        "_manifest",
        lambda: {
            "source": {"kind": "pypi", "spec": "theforge-core==1.0.0"},
            "distribution": "theforge-core",
            "venv": str(forge_home / "v"),
        },
    )
    out = service.update(repo=forge_home, dry_run=True)
    assert out["status"] == "failed"
    check = out["checks"][0]
    assert check["status"] == "FAIL" and "--repo" in check["detail"]


def test_update_checkout_with_to_fails_named(monkeypatch, forge_home: Path) -> None:
    # --to num checkout antes era ignorado: agora recusa nomeada.
    monkeypatch.setattr(
        service,
        "_manifest",
        lambda: {"source": {"kind": "git", "path": str(forge_home)}},
    )
    out = service.update(to="0.5.2", dry_run=True)
    assert out["status"] == "failed"
    check = out["checks"][0]
    assert check["status"] == "FAIL" and "--to" in check["detail"]


def test_update_redacted_spec_fails_named(monkeypatch, forge_home: Path) -> None:
    # manifesto com spec redigido (***@) nao pode re-autenticar: FAIL nomeado.
    monkeypatch.setattr(
        service,
        "_manifest",
        lambda: {
            "source": {"kind": "pypi", "spec": "theforge-core @ https://***@h/x.whl"},
            "distribution": "theforge-core",
            "venv": str(forge_home / "v"),
        },
    )
    out = service.update(dry_run=True)
    assert out["status"] == "failed"
    check = out["checks"][0]
    assert check["status"] == "FAIL" and "redigido" in check["detail"]


def test_update_to_on_url_spec_refuses_origin_swap(monkeypatch, forge_home: Path) -> None:
    """`--to` num spec de referência direta trocaria URL→PyPI: recusa nomeada."""
    monkeypatch.setattr(
        service,
        "_manifest",
        lambda: {
            "source": {"kind": "pypi", "spec": "theforge-core @ https://h/x.whl"},
            "distribution": "theforge-core",
            "venv": "/v",
        },
    )
    out = service.update(to="1.4.0", dry_run=True)
    assert out["status"] == "failed"
    assert out["checks"][0]["status"] == "FAIL"
    assert "PyPI" in out["checks"][0]["detail"]


def test_update_to_on_file_spec_refuses_origin_swap(monkeypatch, forge_home: Path) -> None:
    """Wheelhouse `file://` também é direct reference: `--to` recusa a troca."""
    monkeypatch.setattr(
        service,
        "_manifest",
        lambda: {
            "source": {"kind": "pypi", "spec": "theforge-core @ file:///wheels/x.whl"},
            "distribution": "theforge-core",
            "venv": "/v",
        },
    )
    out = service.update(to="1.4.0", dry_run=True)
    assert out["status"] == "failed"
    assert out["checks"][0]["status"] == "FAIL"
    assert "PyPI" in out["checks"][0]["detail"]


def test_update_to_on_unspaced_url_spec_refuses_origin_swap(monkeypatch, forge_home: Path) -> None:
    """`name@https://…` sem espaços também é direct reference PEP 508."""
    monkeypatch.setattr(
        service,
        "_manifest",
        lambda: {
            "source": {"kind": "pypi", "spec": "theforge-core@https://h/x.whl"},
            "distribution": "theforge-core",
            "venv": "/v",
        },
    )
    out = service.update(to="1.4.0", dry_run=True)
    assert out["status"] == "failed"


def test_update_url_spec_no_to_keeps_same_origin(monkeypatch, forge_home: Path, tmp_path) -> None:
    """Sem `--to`, `-U` re-executa o spec da mesma origem (não troca)."""
    fake_py = tmp_path / "bin" / "python"
    fake_py.parent.mkdir()
    fake_py.write_text("")
    monkeypatch.setattr(
        service,
        "_manifest",
        lambda: {
            "source": {"kind": "pypi", "spec": "theforge-core @ https://h/x.whl"},
            "distribution": "theforge-core",
            "venv": str(tmp_path),
        },
    )
    out = service.update(dry_run=True)
    assert out["status"] == "planned"
    assert "theforge-core @ https://h/x.whl" in out["checks"][0]["detail"]
