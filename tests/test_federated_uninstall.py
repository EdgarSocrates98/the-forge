"""Adversarial federated uninstall (cycle 16.1 §5.5).

The federated e2e proved install-time containment; this is the permanent
uninstall-side regression: several specialists share one workspace, the
user's own files are hashed before anything happens, and every order /
reinstall / mid-uninstall failure permutation must leave every foreign
byte — and every sibling forge's bytes — exactly where they were.

Full delegation (each specialist driving its own CLI) is impractical
here — the same canonical installkit uninstall machinery runs against
prepared per-forge ledgers, which is exactly the code path each CLI
uninstall executes.
"""

from __future__ import annotations

import hashlib
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

FORGES = ("forge-alpha", "forge-beta", "forge-gamma")

FOREIGN_FILES: dict[str, bytes] = {
    "README.md": b"# user's own readme\n",
    "src/user.py": b"# user code\n",
    # a foreign file *inside* a dir that also receives managed content
    ".claude/skills/user-skill/SKILL.md": b"# user's own skill\n",
    "frontend-web/package.json": b'{"name": "user-app"}\n',
}

# User-authored content that must survive inside shared documents.
_USER_AGENTS = "# My agents\n\nuser text above\n\nuser text below\n"
_USER_MCP = {
    "mcpServers": {"user-server": {"command": "user-srv"}},
    "note": "user metadata",
}


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _foreign_snapshot(root: Path) -> dict[str, str]:
    return {rel: _sha(root / rel) for rel in FOREIGN_FILES}


def _spec(fid: str) -> kit.ForgeSpec:
    assets = {
        f".agents/skills/{fid}/SKILL.md": f"# {fid} skill\n".encode(),
        f".claude/skills/{fid}/SKILL.md": f"# {fid} skill\n".encode(),
        f".{fid}/config/state.json": b"{}\n",
    }

    def render(ctx: kit.InstallContext) -> dict[str, bytes]:
        return assets

    return kit.ForgeSpec(
        forge_id=fid,
        package=fid.replace("-", "_"),
        distribution=fid,
        cli_name=fid,
        python_spec=">=3.10",
        state_dir=f".{fid}",
        mcp_command=(fid, "mcp", "serve"),
        mcp_server_name=fid,
        marker_body=f"**{fid}** is installed in this project.",
        render_assets=render,
        spawn_ok=False,
    )


def _ctx(root: Path, fid: str) -> kit.InstallContext:
    spec = _spec(fid)
    return kit.InstallContext(
        spec=spec,
        scope="project",
        root=root,
        state_dir=kit.state_dir_for(spec, "project", root),
        hosts=(),
        profile="recommended",
        dry_run=False,
    )


def _workspace(tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    root.mkdir()
    for rel, body in FOREIGN_FILES.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body)
    (root / "AGENTS.md").write_text(_USER_AGENTS, encoding="utf-8")
    (root / ".mcp.json").write_text(json.dumps(_USER_MCP), encoding="utf-8")
    return root


def _install_all(root: Path, forges: tuple[str, ...] = FORGES) -> None:
    for fid in forges:
        receipt = kit.apply_install(_ctx(root, fid), approved=True)
        assert receipt["status"] == "completed"


def test_uninstall_order_alpha_beta_gamma_preserves_foreign(
    tmp_path: Path,
) -> None:
    root = _workspace(tmp_path)
    before = _foreign_snapshot(root)
    _install_all(root)
    for fid in FORGES:  # reinstall pass — idempotent, still foreign-safe
        kit.apply_install(_ctx(root, fid), approved=True)
    assert _foreign_snapshot(root) == before

    for fid in FORGES:
        kit.uninstall(_ctx(root, fid))

    assert _foreign_snapshot(root) == before
    # every managed file of every forge is gone (state dirs themselves
    # stay — uninstall without purge_state keeps the forge-owned ledger)
    for fid in FORGES:
        assert not (root / ".claude" / "skills" / fid).exists()
        assert not (root / ".agents" / "skills" / fid).exists()
        assert not (root / f".{fid}" / "config" / "state.json").exists()
    # shared documents: user content + sibling keys survive
    agents = (root / "AGENTS.md").read_text(encoding="utf-8")
    assert "user text above" in agents and "user text below" in agents
    for fid in FORGES:
        assert f"{fid}:managed:begin" not in agents
    mcp = json.loads((root / ".mcp.json").read_text(encoding="utf-8"))
    assert mcp["mcpServers"] == {"user-server": {"command": "user-srv"}}
    assert mcp["note"] == "user metadata"


def test_uninstall_order_reverse_preserves_foreign(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    before = _foreign_snapshot(root)
    _install_all(root)
    for fid in reversed(FORGES):
        kit.uninstall(_ctx(root, fid))
    assert _foreign_snapshot(root) == before
    agents = (root / "AGENTS.md").read_text(encoding="utf-8")
    assert "user text above" in agents
    mcp = json.loads((root / ".mcp.json").read_text(encoding="utf-8"))
    assert "user-server" in mcp["mcpServers"]


def test_partial_uninstall_keeps_sibling_forges_working(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    before = _foreign_snapshot(root)
    _install_all(root)
    kit.uninstall(_ctx(root, "forge-beta"))
    assert _foreign_snapshot(root) == before
    # siblings' assets and marker blocks untouched
    for fid in ("forge-alpha", "forge-gamma"):
        assert (root / ".claude" / "skills" / fid / "SKILL.md").exists()
        agents = (root / "AGENTS.md").read_text(encoding="utf-8")
        assert f"{fid}:managed:begin" in agents
        mcp = json.loads((root / ".mcp.json").read_text(encoding="utf-8"))
        assert fid in mcp["mcpServers"]
    # beta's own bytes are gone
    assert not (root / ".claude" / "skills" / "forge-beta").exists()
    agents = (root / "AGENTS.md").read_text(encoding="utf-8")
    assert "forge-beta:managed:begin" not in agents
    assert (
        "forge-beta"
        not in json.loads((root / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]
    )


def test_mid_uninstall_failure_recovers_and_preserves_foreign(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _workspace(tmp_path)
    before = _foreign_snapshot(root)
    _install_all(root)

    # Kill the first atomic write inside forge-beta's uninstall — the
    # shared-document rewrite — and let it explode mid-flight.
    real_write = kit._atomic_write
    calls = {"n": 0}

    def _boom(path: Path, data: bytes) -> None:
        calls["n"] += 1
        raise RuntimeError("injected mid-uninstall failure")

    monkeypatch.setattr(kit, "_atomic_write", _boom)
    with pytest.raises(RuntimeError):
        kit.uninstall(_ctx(root, "forge-beta"))
    assert calls["n"] == 1
    monkeypatch.setattr(kit, "_atomic_write", real_write)

    # Foreign files survived the aborted run; on-disk ledger is whole —
    # the crashed save never rewrote it.
    assert _foreign_snapshot(root) == before
    ledger_path = _ctx(root, "forge-beta").state_dir / "install-ledger.json"
    assert json.loads(ledger_path.read_text(encoding="utf-8"))["entries"]

    # Recovery: the same uninstall now completes; foreign files and every
    # sibling forge's bytes are still intact.
    kit.uninstall(_ctx(root, "forge-beta"))
    assert _foreign_snapshot(root) == before
    for fid in ("forge-alpha", "forge-gamma"):
        assert (root / ".claude" / "skills" / fid / "SKILL.md").exists()
        mcp = json.loads((root / ".mcp.json").read_text(encoding="utf-8"))
        assert fid in mcp["mcpServers"]
    assert (
        "forge-beta"
        not in json.loads((root / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]
    )


def test_user_modified_managed_file_is_never_deleted(tmp_path: Path) -> None:
    """A managed file the user edited since install is reclassified as
    user-owned at uninstall time — sha mismatch means keep."""
    root = _workspace(tmp_path)
    before = _foreign_snapshot(root)
    _install_all(root, ("forge-alpha",))
    target = root / ".claude" / "skills" / "forge-alpha" / "SKILL.md"
    target.write_bytes(b"# user took this file over\n")
    kit.uninstall(_ctx(root, "forge-alpha"))
    assert _foreign_snapshot(root) == before
    assert target.read_bytes() == b"# user took this file over\n"
