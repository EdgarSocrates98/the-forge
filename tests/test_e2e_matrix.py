"""§15 acceptance matrix — kit- and service-level scenarios.

Each test maps to a numbered section of prompt_evo_install.md §15.
Real-host and multi-OS gates (§15.7 execução real, §15.8 CI) are
environment-dependent and recorded as pending in
docs/portable-installation/acceptance-matrix.md — never claimed here.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

KIT_PATH = ROOT / "scripts" / "installkit" / "forge_installkit.py"
spec = importlib.util.spec_from_file_location("forge_installkit", KIT_PATH)
kit = importlib.util.module_from_spec(spec)
sys.modules["forge_installkit"] = kit
spec.loader.exec_module(kit)


def _spec(**kw) -> kit.ForgeSpec:
    assets = {
        ".agents/skills/demo/SKILL.md": b"# demo skill\n",
        ".claude/skills/demo/SKILL.md": b"# demo skill\n",
        ".codex/skills/demo/SKILL.md": b"# demo skill\n",
        ".devin/skills/demo/SKILL.md": b"# demo skill\n",
        ".agents/agents/demo.md": b"# demo agent\n",
        ".forge-test/state.json": b"{}\n",
    }

    def render(ctx):
        return assets

    base = dict(
        forge_id="forge-test",
        package="forge_test",
        distribution="forge-test",
        cli_name="forge-test",
        python_spec=">=3.10",
        state_dir=".forge-test",
        mcp_command=("forge-test", "mcp", "serve"),
        mcp_server_name="forge-test",
        marker_body="**forge-test** is installed in this project.",
        render_assets=render,
        spawn_ok=False,
    )
    base.update(kw)
    return kit.ForgeSpec(**base)


def _ctx(tmp_path: Path, **kw) -> kit.InstallContext:
    _SPEC_KEYS = ("mcp_server_name", "spawn_ok", "mcp_command", "mcp_verify_tool")
    spec = _spec(**{k: kw.pop(k) for k in _SPEC_KEYS if k in kw})
    root = kw.pop("root", tmp_path)
    state = kit.state_dir_for(spec, kw.get("scope", "project"), root)
    return kit.InstallContext(
        spec=spec,
        scope=kw.pop("scope", "project"),
        root=root,
        state_dir=state,
        hosts=kw.pop("hosts", ()),
        profile=kw.pop("profile", "recommended"),
        dry_run=kw.pop("dry_run", False),
        **kw,
    )


# --- §15.1 instalação limpa + §15.2 repetição ------------------------------


def test_clean_install_then_second_apply_is_idempotent(tmp_path):
    ctx = _ctx(tmp_path)
    kit.apply_install(ctx, approved=True)
    state = ctx.state_dir
    snap1 = {
        p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file() and state not in p.parents
    }
    receipt2 = kit.apply_install(_ctx(tmp_path), approved=True)
    snap2 = {
        p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file() and state not in p.parents
    }
    created = [f for f in receipt2["managed_files"] if f.get("action") == "created"]
    assert created == [], f"second apply created: {created}"
    assert snap1 == snap2  # managed tree byte-identical after reapply


def test_marker_block_not_duplicated_on_reapply(tmp_path):
    ctx = _ctx(tmp_path)
    kit.apply_install(ctx, approved=True)
    kit.apply_install(_ctx(tmp_path), approved=True)
    text = (tmp_path / "AGENTS.md").read_text("utf-8")
    assert text.count("forge-test:managed:begin") == 1


def test_mcp_key_not_duplicated_on_reapply(tmp_path):
    ctx = _ctx(tmp_path)
    kit.apply_install(ctx, approved=True)
    kit.apply_install(_ctx(tmp_path), approved=True)
    mcp = json.loads((tmp_path / ".mcp.json").read_text("utf-8"))
    assert list(mcp["mcpServers"]) == ["forge-test"]
    managed = mcp.get("_forge_managed", {})
    assert managed.get("forge-test", []).count("mcpServers.forge-test") <= 1


# --- §15.4 reparação + §15.5 desinstalação (round trip) ---------------------


def test_repair_restores_deleted_managed_file_only(tmp_path):
    ctx = _ctx(tmp_path)
    kit.apply_install(ctx, approved=True)
    user_file = tmp_path / "notes.txt"
    user_file.write_text("mine", "utf-8")
    victim = tmp_path / ".agents/skills/demo/SKILL.md"
    victim.unlink()
    out = kit.repair(_ctx(tmp_path))
    assert victim.exists()
    assert ".agents/skills/demo/SKILL.md" in out["repaired"]
    assert user_file.read_text("utf-8") == "mine"


def test_uninstall_removes_only_managed_leaves_user_content(tmp_path):
    ctx = _ctx(tmp_path)
    kit.apply_install(ctx, approved=True)
    (tmp_path / ".agents/skills/mine/SKILL.md").parent.mkdir(parents=True)
    (tmp_path / ".agents/skills/mine/SKILL.md").write_text("user skill", "utf-8")
    kit.uninstall(_ctx(tmp_path))
    assert not (tmp_path / ".agents/skills/demo").exists()
    assert (tmp_path / ".agents/skills/mine/SKILL.md").exists()


# --- §15.6 interrupção -------------------------------------------------------


def test_stale_lock_from_interrupted_run_is_recovered(tmp_path):
    ctx = _ctx(tmp_path)
    kit.apply_install(ctx, approved=True)
    lock_file = ctx.state_dir / kit.LOCK_NAME
    lock_file.write_text(json.dumps({"pid": 2**22 + 321, "created_at": "x"}))
    lock = kit.acquire_lock(ctx.state_dir)
    with lock:
        assert lock.recovered is True
        kit.apply_install(_ctx(tmp_path), approved=True)
    assert not lock_file.exists()


def test_failed_write_reverts_to_prior_state(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path)
    kit.apply_install(ctx, approved=True)
    mcp = tmp_path / ".mcp.json"
    mcp.write_text('{"mcpServers": {"forge-test": {"command": "drifted"}}}', "utf-8")
    before = mcp.read_bytes()
    real = kit._atomic_write

    def bomb(path, data):
        if Path(path).name == ".mcp.json" and Path(path).parent == tmp_path:
            raise OSError("interrupted")
        return real(path, data)

    monkeypatch.setattr(kit, "_atomic_write", bomb)
    with pytest.raises(kit.InstallError):
        kit.apply_install(_ctx(tmp_path), approved=True)
    assert mcp.read_bytes() == before  # drifted pre-state restored


# --- §15.7 múltiplos hosts — estrutural --------------------------------------


def test_host_dirs_are_distinct_per_host(tmp_path):
    ctx = _ctx(tmp_path, profile="recommended")
    kit.apply_install(ctx, approved=True)
    for host_dir in (".claude", ".codex", ".devin", ".agents"):
        assert (tmp_path / host_dir / "skills/demo/SKILL.md").exists(), host_dir


def test_minimal_profile_writes_no_skill_mirrors(tmp_path):
    ctx = _ctx(tmp_path, profile="minimal")
    kit.apply_install(ctx, approved=True)
    assert not (tmp_path / ".claude").exists()
    assert (tmp_path / "AGENTS.md").exists() or (tmp_path / ".mcp.json").exists()


# --- §15.9 offline / artefato ausente ----------------------------------------


def test_mcp_verify_blocked_when_exe_missing_is_honest(tmp_path):
    ctx = _ctx(
        tmp_path,
        mcp_command=("definitely-not-a-forge-cli-xyz", "mcp"),
        mcp_server_name="forge-test",
    )
    kit.apply_install(ctx, approved=True)
    out = kit.mcp_verify(ctx.spec)
    assert out["status"] in ("BLOCKED", "FAIL")
    assert out["status"] != "PASS"
