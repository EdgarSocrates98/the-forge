"""Orchestration tests for ``theforge install`` (ADR-0058, forge/* v1).

Drives ``theforge.install.service`` in-process against tmp consumer roots:
approval gating, ownership, drift/repair, uninstall and the ``install auto``
family delegation (isolated via FORGE_HOME_OVERRIDE).
"""

from __future__ import annotations

import hashlib
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
    canon = (ROOT / "scripts" / "installkit" / "forge_installkit.py").read_bytes()
    vend = (ROOT / "src" / "theforge" / "_installkit.py").read_bytes()
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
    receipt = service.install(scope="workspace", root=target / "ws", yes=True,
                              host="codex")
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
        '{"forge_id": "api-forge", "cli": {"name": "apiforge"}}', "utf-8")
    out = service.install_auto(scope="project", root=target)
    assert out["forges"][0]["status"] == "refused"
    assert out["status"] == "failed"


def test_auto_dry_run_plans_delegation(forge_home: Path, target: Path) -> None:
    (forge_home / ".forge" / "installations").mkdir(parents=True)
    (forge_home / ".forge" / "installations" / "the-forge.json").write_text(
        '{"forge_id": "the-forge", "cli": {"name": "theforge"}}', "utf-8")
    out = service.install_auto(scope="project", root=target, dry_run=True)
    assert out["status"] == "planned"
    assert out["forges"][0]["via"] == "self"


def test_auto_self_installs_in_process(forge_home: Path, target: Path) -> None:
    (forge_home / ".forge" / "installations").mkdir(parents=True)
    (forge_home / ".forge" / "installations" / "the-forge.json").write_text(
        '{"forge_id": "the-forge", "cli": {"name": "theforge"}}', "utf-8")
    out = service.install_auto(scope="project", root=target, yes=True)
    assert out["status"] == "completed"
    assert (target / ".agents" / "skills").is_dir()


def test_auto_forge_filter(forge_home: Path, target: Path) -> None:
    inst = forge_home / ".forge" / "installations"
    inst.mkdir(parents=True)
    (inst / "the-forge.json").write_text(
        '{"forge_id": "the-forge", "cli": {"name": "theforge"}}', "utf-8")
    (inst / "ghost.json").write_text(
        '{"forge_id": "ghost", "cli": {"name": "definitely-not-a-cli-xyz"}}',
        "utf-8")
    out = service.install_auto(scope="project", root=target, yes=True,
                               forge="the-forge")
    assert [f["forge_id"] for f in out["forges"]] == ["the-forge"]
    assert out["status"] == "completed"
    with pytest.raises(kit.InstallError) as exc:
        service.install_auto(scope="project", root=target, yes=True,
                             forge="nope")
    assert exc.value.kind == kit.E_NOTINSTALLED


def test_auto_reports_missing_cli(forge_home: Path, target: Path) -> None:
    (forge_home / ".forge" / "installations").mkdir(parents=True)
    (forge_home / ".forge" / "installations" / "ghost.json").write_text(
        '{"forge_id": "ghost", "cli": {"name": "definitely-not-a-cli-xyz"}}',
        "utf-8")
    out = service.install_auto(scope="project", root=target, yes=True)
    assert out["status"] == "failed"
    assert out["checks"][0]["status"] == "BLOCKED"
    assert "definitely-not-a-cli-xyz" in out["checks"][0]["detail"]


def test_installations_list_reads_registry(forge_home: Path) -> None:
    assert service.installations() == []
    (forge_home / ".forge" / "installations").mkdir(parents=True)
    (forge_home / ".forge" / "installations" / "x.json").write_text(
        '{"forge_id": "x", "version": "1.0.0"}', "utf-8")
    rows = service.installations()
    assert [r["forge_id"] for r in rows] == ["x"]
