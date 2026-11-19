"""MCP config audit (cycle 16.1, FRENTE E §9.3): namespacing, duplicate
detection, PATH-dependence classification, and honest launch states."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from theforge.install.mcp_audit import audit_mcp


def _write(tmp: Path, doc: dict) -> Path:
    (tmp / ".mcp.json").write_text(json.dumps(doc), "utf-8")
    return tmp


def _status(audit: dict, check_id: str) -> str:
    for c in audit["checks"]:
        if c["id"] == check_id:
            return c["status"]
    raise AssertionError(f"check {check_id!r} missing: {[c['id'] for c in audit['checks']]}")


def test_absent_file_is_not_applicable_not_fail(tmp_path: Path) -> None:
    audit = audit_mcp(tmp_path)
    assert audit["present"] is False
    assert _status(audit, "mcp-config") == "NOT_APPLICABLE"


def test_unrelated_user_servers_are_preserved_in_report(tmp_path: Path) -> None:
    """`.mcp.json` is shared config — the audit reports other entries and
    never treats non-forge keys as defects."""
    _write(
        tmp_path,
        {
            "mcpServers": {
                "user-server": {"command": sys.executable, "args": []},
            },
        },
    )
    audit = audit_mcp(tmp_path)
    assert "user-server" in audit["servers"]
    assert all(c["status"] != "FAIL" for c in audit["checks"])


def test_duplicate_argv_is_a_defect(tmp_path: Path) -> None:
    _write(
        tmp_path,
        {
            "mcpServers": {
                "a": {"command": str(tmp_path / "bin/x"), "args": ["serve"]},
                "b": {"command": str(tmp_path / "bin/x"), "args": ["serve"]},
            }
        },
    )
    audit = audit_mcp(tmp_path)
    assert _status(audit, "mcp-duplicates") == "FAIL"
    assert _status(audit, "mcp-duplicate:b") == "FAIL"


def test_namespace_claim_for_missing_server_fails(tmp_path: Path) -> None:
    _write(
        tmp_path,
        {
            "mcpServers": {},
            "_forge_managed": {"forge-a": ["mcpServers.forge-a"]},
        },
    )
    audit = audit_mcp(tmp_path)
    assert _status(audit, "mcp-namespace:mcpServers.forge-a") == "FAIL"


def test_double_claimed_key_is_a_conflict(tmp_path: Path) -> None:
    _write(
        tmp_path,
        {
            "mcpServers": {"shared": {"command": "x"}},
            "_forge_managed": {
                "forge-a": ["mcpServers.shared"],
                "forge-b": ["mcpServers.shared"],
            },
        },
    )
    audit = audit_mcp(tmp_path)
    assert _status(audit, "mcp-namespace:mcpServers.shared") == "FAIL"
    assert "conflict" in next(
        c["detail"] for c in audit["checks"] if c["id"] == "mcp-namespace:mcpServers.shared"
    )


def test_bare_command_is_path_dependent_and_warned(tmp_path: Path) -> None:
    _write(tmp_path, {"mcpServers": {"s": {"command": "python3", "args": []}}})
    audit = audit_mcp(tmp_path)
    assert audit["servers"]["s"]["command_kind"] == "path-dependent"
    assert _status(audit, "mcp-launch:s") == "WARN"


def test_unresolvable_command_fails(tmp_path: Path) -> None:
    _write(
        tmp_path,
        {"mcpServers": {"s": {"command": "definitely-not-a-real-binary-xyz", "args": []}}},
    )
    audit = audit_mcp(tmp_path)
    assert _status(audit, "mcp-launch:s") == "FAIL"


def test_absolute_command_missing_fails_honestly(tmp_path: Path) -> None:
    _write(
        tmp_path,
        {"mcpServers": {"s": {"command": str(tmp_path / "no-such-bin"), "args": []}}},
    )
    audit = audit_mcp(tmp_path)
    assert audit["servers"]["s"]["command_kind"] == "absolute"
    assert _status(audit, "mcp-launch:s") == "FAIL"


def test_own_entry_reports_absolute_vs_path_dependent(tmp_path: Path) -> None:
    spec = SimpleNamespace(mcp_server_name="theforge")
    # PATH-dependent own entry → FAIL with repairable hint
    doc = {"mcpServers": {"theforge": {"command": "theforge", "args": ["mcp", "serve"]}}}
    _write(tmp_path, doc)
    audit = audit_mcp(tmp_path, spec=spec)
    assert _status(audit, "mcp-own-entry") == "FAIL"
    check = next(c for c in audit["checks"] if c["id"] == "mcp-own-entry")
    assert check["repairable"] is True

    # absolute own entry → PASS
    _write(
        tmp_path,
        {
            "mcpServers": {
                "theforge": {
                    "command": sys.executable,
                    "args": ["-m", "theforge", "mcp", "serve"],
                }
            }
        },
    )
    audit = audit_mcp(tmp_path, spec=spec)
    assert _status(audit, "mcp-own-entry") == "PASS"


def test_missing_own_entry_is_unverified_not_fail(tmp_path: Path) -> None:
    spec = SimpleNamespace(mcp_server_name="theforge")
    _write(tmp_path, {"mcpServers": {"other": {"command": "x"}}})
    audit = audit_mcp(tmp_path, spec=spec)
    assert _status(audit, "mcp-own-entry") == "UNVERIFIED"


@pytest.mark.integration()
def test_install_writes_absolute_managed_argv(tmp_path: Path) -> None:
    """End-to-end §9.3: the managed `.mcp.json` entry the install writes is
    PATH-independent — audit sees `absolute`, never a bare `theforge`."""
    from theforge.install import service

    target = tmp_path / "consumer"
    target.mkdir()
    service.install(scope="project", root=target, yes=True)
    doc = json.loads((target / ".mcp.json").read_text("utf-8"))
    entry = doc["mcpServers"]["theforge"]
    assert Path(entry["command"]).is_absolute(), entry["command"]
    # resolution order: registered shim, else sys.executable -m <pkg> —
    # either way the written argv never depends on PATH
    assert entry["command"] == sys.executable or Path(entry["command"]).name.startswith("theforge")
    # managed namespace claims the key the audit will check
    tags = doc.get("_forge_managed", {})
    assert any("mcpServers.theforge" in keys for keys in tags.values() if isinstance(keys, list))
    spec = SimpleNamespace(mcp_server_name="theforge")
    audit = audit_mcp(target, spec=spec)
    assert _status(audit, "mcp-own-entry") == "PASS"
    # duplicates impossible: idempotent re-install keeps one managed key
    service.install(scope="project", root=target, yes=True)
    doc2 = json.loads((target / ".mcp.json").read_text("utf-8"))
    assert "theforge" in doc2["mcpServers"]
    assert _status(audit_mcp(target), "mcp-duplicates") == "PASS"
