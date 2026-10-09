"""Contract tests for the shared installkit engine (forge/* v1 documents).

Loads the canonical ``scripts/installkit/forge_installkit.py`` by path —
the same file vendored into every Forge — and drives a fake Forge through
the whole lifecycle in isolated tmp dirs.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
KIT_PATH = ROOT / "scripts" / "installkit" / "forge_installkit.py"

spec = importlib.util.spec_from_file_location("forge_installkit", KIT_PATH)
kit = importlib.util.module_from_spec(spec)
sys.modules["forge_installkit"] = kit  # dataclass resolution needs the module
spec.loader.exec_module(kit)


def _spec(**kw) -> kit.ForgeSpec:
    assets = {
        ".agents/skills/demo/SKILL.md": b"# demo skill\n",
        ".claude/skills/demo/SKILL.md": b"# demo skill\n",
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


def _ctx(tmp_path: Path, scope: str = "project", **kw) -> kit.InstallContext:
    _SPEC_KEYS = ("mcp_server_name", "spawn_ok", "mcp_command", "mcp_verify_tool")
    spec = _spec(**{k: v for k, v in kw.items() if k in _SPEC_KEYS})
    kw2 = {k: v for k, v in kw.items() if k not in _SPEC_KEYS}
    cwd = kw2.pop("cwd", tmp_path)
    root = kit.resolve_scope(spec, scope, cwd, kw2.pop("root", tmp_path))
    state = kit.state_dir_for(spec, scope, root)
    return kit.InstallContext(
        spec=spec,
        scope=scope,
        root=root,
        state_dir=state,
        profile=kw2.pop("profile", "recommended"),
        hosts=kw2.pop("hosts", ("claude", "devin")),
        dry_run=kw2.pop("dry_run", False),
        ledger=kit.Ledger.load(state),
    )


# --- scope + validation -------------------------------------------------


def test_scope_unknown_refuses(tmp_path):
    with pytest.raises(kit.InstallError) as e:
        kit.resolve_scope(_spec(), "bogus", tmp_path, None)
    assert e.value.kind == kit.E_SCOPE


def test_profile_unknown_raises(tmp_path):
    ctx = _ctx(tmp_path)
    ctx.profile = "bogus"
    with pytest.raises(KeyError):
        kit.profile_asset_kinds(ctx.profile)


def test_install_requires_approval(tmp_path):
    ctx = _ctx(tmp_path)
    with pytest.raises(kit.InstallError) as e:
        kit.apply_install(ctx)
    assert e.value.kind == kit.E_NOTAPPROVED


def test_dry_run_never_writes(tmp_path):
    ctx = _ctx(tmp_path, dry_run=True)
    out = kit.apply_install(ctx)
    assert out["status"] == "planned"
    assert not (tmp_path / ".agents").exists()
    assert not ctx.state_dir.exists()


# --- install lifecycle ---------------------------------------------------


def test_install_writes_owned_files(tmp_path):
    ctx = _ctx(tmp_path)
    rcpt = kit.apply_install(ctx, approved=True)
    assert rcpt["status"] == "completed"
    assert (tmp_path / ".agents/skills/demo/SKILL.md").exists()
    assert (tmp_path / ".mcp.json").exists()
    ledger = kit.Ledger.load(ctx.state_dir)
    assert ledger.owned_paths()


def test_install_is_idempotent(tmp_path):
    ctx = _ctx(tmp_path)
    kit.apply_install(ctx, approved=True)
    before = kit.Ledger.load(ctx.state_dir).entries()
    kit.apply_install(ctx, approved=True)
    after = kit.Ledger.load(ctx.state_dir).entries()
    assert before.keys() == after.keys()
    unchanged = [p for p, e in after.items() if e["action"] in ("unchanged", "adopted")]
    assert unchanged  # second run adopts, doesn't rewrite


def test_install_adopts_preexisting_identical(tmp_path):
    p = tmp_path / ".agents/skills/demo/SKILL.md"
    p.parent.mkdir(parents=True)
    p.write_bytes(b"# demo skill\n")
    ctx = _ctx(tmp_path)
    kit.apply_install(ctx, approved=True)
    entry = kit.Ledger.load(ctx.state_dir).get(".agents/skills/demo/SKILL.md")
    assert entry["action"] in ("adopted", "unchanged")
    assert entry["managed"] is False  # adopted files are never owned


def test_install_never_overwrites_foreign_file(tmp_path):
    p = tmp_path / ".agents/skills/demo/SKILL.md"
    p.parent.mkdir(parents=True)
    p.write_bytes(b"# user-authored, different\n")
    ctx = _ctx(tmp_path)
    rcpt = kit.apply_install(ctx, approved=True)
    assert p.read_bytes() == b"# user-authored, different\n"
    skipped = [f for f in rcpt["managed_files"] if f["path"] == ".agents/skills/demo/SKILL.md"]
    assert skipped and skipped[0]["action"] == "unchanged"


def test_marker_block_coexists_with_user_content(tmp_path):
    ag = tmp_path / "AGENTS.md"
    ag.write_text("# my rules\n\nkeep this.\n", encoding="utf-8")
    ctx = _ctx(tmp_path)
    kit.apply_install(ctx, approved=True)
    txt = ag.read_text(encoding="utf-8")
    assert "keep this." in txt and "forge-test:managed:begin" in txt
    # second install is a no-op on the block
    kit.apply_install(ctx, approved=True)
    assert ag.read_text(encoding="utf-8").count("forge-test:managed:begin") == 1


def test_mcp_managed_key_preserves_other_servers(tmp_path):
    mcp = tmp_path / ".mcp.json"
    mcp.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}, "unrelated": True}))
    ctx = _ctx(tmp_path)
    kit.apply_install(ctx, approved=True)
    doc = json.loads(mcp.read_text())
    assert doc["mcpServers"]["other"] == {"command": "x"}
    assert doc["mcpServers"]["forge-test"]["command"] == "forge-test"
    assert doc["unrelated"] is True


# --- status / doctor / repair / uninstall --------------------------------


def test_status_healthy_after_install(tmp_path):
    ctx = _ctx(tmp_path)
    kit.apply_install(ctx, approved=True)
    st = kit.status(ctx)
    assert st["status"] == "healthy"
    assert st["drift"]["ok"] >= 1


def test_doctor_reports_drift(tmp_path):
    ctx = _ctx(tmp_path)
    kit.apply_install(ctx, approved=True)
    (tmp_path / ".agents/skills/demo/SKILL.md").write_bytes(b"tampered\n")
    health = kit.doctor(ctx)
    assert health["status"] == "degraded"
    assert any(c["id"].startswith("drift:") for c in health["checks"])


def test_repair_restores_drifted_managed(tmp_path):
    ctx = _ctx(tmp_path)
    kit.apply_install(ctx, approved=True)
    f = tmp_path / ".agents/skills/demo/SKILL.md"
    f.write_bytes(b"tampered\n")
    out = kit.repair(ctx)
    assert ".agents/skills/demo/SKILL.md" in out["repaired"]
    assert f.read_bytes() == b"# demo skill\n"


def test_marker_user_text_is_not_drift(tmp_path):
    ctx = _ctx(tmp_path)
    kit.apply_install(ctx, approved=True)
    ag = tmp_path / "AGENTS.md"
    ag.write_text(ag.read_text(encoding="utf-8") + "\n# user notes\n", encoding="utf-8")
    st = kit.status(ctx)
    assert st["drift"]["modified"] == []
    assert st["status"] == "healthy"


def test_repair_heals_damaged_marker_block(tmp_path):
    ctx = _ctx(tmp_path)
    kit.apply_install(ctx, approved=True)
    ag = tmp_path / "AGENTS.md"
    ag.write_text("# user notes\n\n(corrupted block)\n", encoding="utf-8")
    out = kit.repair(ctx)
    assert "AGENTS.md" in out["repaired"]
    txt = ag.read_text(encoding="utf-8")
    assert "# user notes" in txt  # user content survives
    assert "forge-test:managed:begin" in txt
    assert kit.status(ctx)["status"] == "healthy"


def test_repair_restores_missing_mcp_key_preserving_users(tmp_path):
    ctx = _ctx(tmp_path)
    kit.apply_install(ctx, approved=True)
    mcp = tmp_path / ".mcp.json"
    doc = json.loads(mcp.read_text())
    doc["mcpServers"].pop("forge-test")
    doc["mcpServers"]["other"] = {"command": "x"}
    mcp.write_text(json.dumps(doc))
    out = kit.repair(ctx)
    assert ".mcp.json" in out["repaired"]
    new = json.loads(mcp.read_text())
    assert new["mcpServers"]["forge-test"]["command"] == "forge-test"
    assert new["mcpServers"]["other"] == {"command": "x"}
    assert kit.status(ctx)["status"] == "healthy"


def test_repair_restores_missing_managed_asset(tmp_path):
    ctx = _ctx(tmp_path)
    kit.apply_install(ctx, approved=True)
    f = tmp_path / ".agents/skills/demo/SKILL.md"
    f.unlink()
    out = kit.repair(ctx)
    assert ".agents/skills/demo/SKILL.md" in out["repaired"]
    assert f.read_bytes() == b"# demo skill\n"


def test_uninstall_removes_only_owned(tmp_path):
    # foreign file at a managed path is kept; owned file removed
    foreign = tmp_path / ".agents/skills/foreign/SKILL.md"
    foreign.parent.mkdir(parents=True)
    foreign.write_bytes(b"mine\n")
    ctx = _ctx(tmp_path)
    kit.apply_install(ctx, approved=True)
    kit.uninstall(ctx)
    assert not (tmp_path / ".agents/skills/demo/SKILL.md").exists()
    assert foreign.exists()
    # AGENTS.md was created by the install (marker only) → fully removed
    assert not (tmp_path / "AGENTS.md").exists()


def test_uninstall_keeps_modified_managed_file(tmp_path):
    ctx = _ctx(tmp_path)
    kit.apply_install(ctx, approved=True)
    f = tmp_path / ".agents/skills/demo/SKILL.md"
    f.write_bytes(b"user modified after install\n")
    kit.uninstall(ctx)
    assert f.exists()  # sha mismatch → treated as user-owned


def test_lock_refuses_concurrent(tmp_path):
    state = tmp_path / ".forge-test"
    lock = kit.acquire_lock(state)
    with lock:
        with pytest.raises(kit.LockError) as e, kit.acquire_lock(state):
            pass
        assert e.value.kind == kit.E_LOCKED


def test_receipt_shape_conforms(tmp_path):
    ctx = _ctx(tmp_path)
    rcpt = kit.apply_install(ctx, approved=True)
    for key in (
        "schema",
        "receipt_id",
        "forge_id",
        "operation",
        "scope",
        "target_root",
        "managed_files",
        "checks",
        "verification",
        "status",
        "created_at",
    ):
        assert key in rcpt, key
    assert rcpt["schema"] == "forge/InstallReceipt/v1"
    assert rcpt["verification"]["status"] in (
        "PASS",
        "FAIL",
        "BLOCKED",
        "UNVERIFIED",
        "NOT_APPLICABLE",
    )


def test_manifest_shape(tmp_path):
    doc = kit.manifest_for(
        _spec(),
        install_root=tmp_path / "i",
        venv=tmp_path / "v",
        version="1.0.0",
        source={"kind": "git-checkout", "path": "x"},
        shim=tmp_path / "bin" / "x",
    )
    assert doc["schema"] == "forge/InstallationManifest/v1"
    assert doc["forge_id"] == "forge-test"
    assert doc["mcp"]["verified"] is False


def test_health_shape(tmp_path):
    ctx = _ctx(tmp_path)
    kit.apply_install(ctx, approved=True)
    h = kit.doctor(ctx)
    assert h["schema"] == "forge/InstallationHealth/v1"
    assert h["status"] in ("healthy", "degraded", "broken", "unverified")


def test_spawn_disabled_refuses_update_path(tmp_path):
    spec = _spec(spawn_ok=False)
    with pytest.raises(kit.InstallError) as e:
        kit._spawn(spec, ["x"])
    assert e.value.kind == kit.E_SPAWN


def test_mcp_verify_not_applicable_without_server(tmp_path):
    spec = _spec(mcp_server_name=None, mcp_command=())
    check = kit.mcp_verify(spec)
    assert check["status"] == "NOT_APPLICABLE"


def test_mcp_verify_blocked_when_spawn_off(tmp_path):
    spec = _spec(spawn_ok=False)
    check = kit.mcp_verify(spec)
    assert check["status"] == "BLOCKED"


def test_discover_projects_finds_repos(tmp_path):
    ws = tmp_path / "ws"
    for name in ("a", "b"):
        (ws / name / ".git").mkdir(parents=True)
    (ws / "not-a-repo").mkdir(parents=True)
    (ws / ".hidden" / ".git").mkdir(parents=True)
    assert kit.discover_projects(ws) == sorted((ws / n).resolve() for n in ("a", "b"))


def test_discover_projects_includes_root_repo(tmp_path):
    ws = tmp_path / "ws"
    (ws / ".git").mkdir(parents=True)
    (ws / "child" / ".git").mkdir(parents=True)
    found = kit.discover_projects(ws)
    assert found == [ws.resolve(), (ws / "child").resolve()]


def test_discover_projects_never_descends_into_repo(tmp_path):
    ws = tmp_path / "ws"
    (ws / "outer" / ".git").mkdir(parents=True)
    (ws / "outer" / "nested" / ".git").mkdir(parents=True)
    assert kit.discover_projects(ws) == [(ws / "outer").resolve()]


def test_member_precedence(tmp_path):
    spec = _spec()
    member = tmp_path / "m"
    member.mkdir()
    assert kit.member_precedence(member, spec) is None
    (member / ".mcp.json").write_text('{"mcpServers": {"forge-test": {}}}', "utf-8")
    assert kit.member_precedence(member, spec) == "project"


_MCP_STUB = r"""
import json, sys
for line in sys.stdin:
    try:
        m = json.loads(line)
    except ValueError:
        continue
    mid, method = m.get("id"), m.get("method")
    if method == "initialize":
        print(json.dumps({"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": "stub", "version": "0"},
            "capabilities": {"tools": {}}}}), flush=True)
    elif method == "tools/list":
        print(json.dumps({"jsonrpc": "2.0", "id": mid, "result": {
            "tools": [{"name": "ping"}, {"name": "status"}]}}), flush=True)
    elif method == "tools/call":
        if m["params"]["name"] == "ping":
            print(json.dumps({"jsonrpc": "2.0", "id": mid, "result": {
                "content": [{"type": "text", "text": "pong"}]}}), flush=True)
        else:
            print(json.dumps({"jsonrpc": "2.0", "id": mid, "error": {
                "code": -32601, "message": "unknown tool"}}), flush=True)
"""


def test_mcp_verify_real_handshake_and_invoke(tmp_path):
    stub = tmp_path / "stub_mcp.py"
    stub.write_text(_MCP_STUB, "utf-8")
    spec = _spec(
        mcp_command=(sys.executable, str(stub)),
        mcp_server_name="stub-mcp",
        mcp_verify_tool="ping",
        spawn_ok=True,
    )
    check = kit.mcp_verify(spec)
    assert check["status"] == "PASS"
    assert check["tools"] == ["ping", "status"]
    assert check["invoke"] == {
        "tool": "ping",
        "status": "PASS",
        "detail": "structured result returned",
    }
    assert check["process"]["exit"] in ("clean", "terminated")
    assert check["process"]["returncode"] is not None


def test_mcp_verify_invoke_error_is_fail(tmp_path):
    stub = tmp_path / "stub_mcp.py"
    stub.write_text(_MCP_STUB, "utf-8")
    spec = _spec(
        mcp_command=(sys.executable, str(stub)),
        mcp_server_name="stub-mcp",
        mcp_verify_tool="nosuch",
        spawn_ok=True,
    )
    check = kit.mcp_verify(spec)
    assert check["status"] == "PASS"  # handshake fine
    assert check["invoke"]["status"] == "FAIL"
    assert "unknown tool" in check["invoke"]["detail"]


def test_mcp_verify_unresolvable_exe_blocked(tmp_path):
    spec = _spec(
        mcp_command=("definitely-not-an-mcp-exe-xyz",),
        mcp_server_name="stub-mcp",
        spawn_ok=True,
    )
    check = kit.mcp_verify(spec)
    assert check["status"] == "BLOCKED"
    assert "not resolvable" in check["detail"]


def test_mcp_verify_process_fields_on_fail(tmp_path):
    spec = _spec(
        mcp_command=(sys.executable, "-c", "import time; time.sleep(60)"),
        mcp_server_name="stub-mcp",
        spawn_ok=True,
    )
    check = kit.mcp_verify(spec, timeout=1)
    assert check["status"] == "FAIL"
    assert "process" in check


def test_doctor_surfaces_invoke_check(tmp_path):
    stub = tmp_path / "stub_mcp.py"
    stub.write_text(_MCP_STUB, "utf-8")
    spec = _spec(
        mcp_command=(sys.executable, str(stub)),
        mcp_server_name="stub-mcp",
        mcp_verify_tool="ping",
        spawn_ok=True,
    )
    root = tmp_path / "proj"
    root.mkdir()
    ctx = _ctx(
        tmp_path,
        root=root,
        mcp_command=spec.mcp_command,
        mcp_server_name=spec.mcp_server_name,
        mcp_verify_tool=spec.mcp_verify_tool,
        spawn_ok=True,
    )
    kit.apply_install(ctx, approved=True)
    health = kit.doctor(ctx)
    invoke = [c for c in health["checks"] if c["id"] == "mcp-invoke"]
    assert invoke and invoke[0]["status"] == "PASS"


def test_receipt_context_metrics(tmp_path):
    ctx = _ctx(tmp_path, mcp_server_name="forge-test", spawn_ok=False, profile="recommended")
    receipt = kit.apply_install(ctx, approved=True)
    ctxm = receipt["context"]
    assert ctxm["profile"] == "recommended"
    assert ctxm["skills_bytes"] > 0  # rendered demo skill counted
    assert ctxm["managed_bytes"] > 0


def test_health_context_reports_tools(tmp_path):
    stub = tmp_path / "stub_mcp.py"
    stub.write_text(_MCP_STUB, "utf-8")
    root = tmp_path / "proj"
    root.mkdir()
    ctx = _ctx(
        tmp_path,
        root=root,
        mcp_command=(sys.executable, str(stub)),
        mcp_server_name="stub-mcp",
        mcp_verify_tool="ping",
        spawn_ok=True,
    )
    kit.apply_install(ctx, approved=True)
    health = kit.doctor(ctx)
    assert health["context"]["tools_exposed"] == 2
    assert health["context"]["managed_entries"] > 0
