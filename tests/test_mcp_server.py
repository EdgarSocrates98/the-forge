"""Native The Forge MCP surface and installation contract."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp", reason="MCP extra is optional")

from theforge.install import service
from theforge.mcp.server import build_server


def test_native_manifest_declares_installable_mcp() -> None:
    root = Path(__file__).resolve().parents[1]
    forge = json.loads((root / "forge.json").read_text(encoding="utf-8"))
    agentic = json.loads((root / "forge.agentic.json").read_text(encoding="utf-8"))
    assert forge["mcp_server_name"] == "theforge"
    assert forge["mcp_command"] == ["theforge", "mcp", "serve"]
    assert "mcp" in forge["extras"]
    assert agentic["mcp_command"] == ["{cli}", "mcp", "serve"]
    assert agentic["mcp_verify_tool"] == "theforge_status"


def test_server_exposes_structured_governed_surface(tmp_path: Path) -> None:
    async def exercise() -> None:
        server = build_server(tmp_path)
        tools = await server.list_tools()
        names = {tool.name for tool in tools}
        assert {
            "theforge_status",
            "theforge_agents_list",
            "theforge_skills_list",
            "theforge_plan_task",
            "theforge_install",
        } <= names

        result = await server.call_tool("theforge_status", {})
        assert not result.is_error
        assert result.structured_content is not None
        assert result.structured_content["initialized"] is False

        result = await server.call_tool("theforge_skills_list", {"limit": 2})
        assert not result.is_error
        page = result.structured_content["skills"]
        assert page["count"] == 2
        assert page["has_more"] is True

    asyncio.run(exercise())


def test_streamable_http_app_is_constructible(tmp_path: Path) -> None:
    app = build_server(tmp_path).streamable_http_app(stateless_http=True)
    assert any(getattr(route, "path", None) == "/mcp" for route in app.routes)


def test_stdio_handshake_and_tool_call(tmp_path: Path) -> None:
    process = subprocess.Popen(
        [sys.executable, "-m", "theforge", "mcp", "serve", "--root", str(tmp_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdin is not None and process.stdout is not None
    messages = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "theforge-test", "version": "1"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "theforge_status", "arguments": {}},
        },
    ]
    try:
        process.stdin.write("\n".join(json.dumps(item) for item in messages) + "\n")
        process.stdin.flush()
        responses = [json.loads(process.stdout.readline()) for _ in range(3)]
    finally:
        process.terminate()
        process.wait(timeout=10)
    assert responses[0]["result"]["serverInfo"]["name"] == "theforge_mcp"
    assert len(responses[1]["result"]["tools"]) >= 10
    assert responses[2]["result"]["structuredContent"]["initialized"] is False


def test_project_install_preserves_other_mcp_servers(tmp_path: Path) -> None:
    target = tmp_path / "consumer"
    target.mkdir()
    (target / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"other": {"command": "other", "args": []}}}),
        encoding="utf-8",
    )
    receipt = service.install(
        scope="project", root=target, host="claude", components=("mcp",), yes=True
    )
    assert receipt["status"] == "completed"
    config = json.loads((target / ".mcp.json").read_text(encoding="utf-8"))
    assert config["mcpServers"]["other"]["command"] == "other"
    assert config["mcpServers"]["theforge"] == {
        "command": "theforge",
        "args": ["mcp", "serve"],
    }
    service.uninstall(scope="project", root=target)
    config = json.loads((target / ".mcp.json").read_text(encoding="utf-8"))
    assert "theforge" not in config["mcpServers"]
    assert "other" in config["mcpServers"]


def test_workspace_install_writes_mcp_at_workspace_root(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    receipt = service.install(
        scope="workspace", root=workspace, host="codex", components=("mcp",), yes=True
    )
    assert receipt["status"] == "completed"
    config = json.loads((workspace / ".mcp.json").read_text(encoding="utf-8"))
    assert config["mcpServers"]["theforge"]["args"] == ["mcp", "serve"]


def test_user_install_writes_mcp_at_isolated_user_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The user scope is real, isolated and reversible — not a project alias."""
    home = tmp_path / "user-home"
    monkeypatch.setenv("FORGE_HOME_OVERRIDE", str(home))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))

    receipt = service.install(
        scope="user",
        root=tmp_path / "ignored-project",
        host="claude",
        components=("mcp",),
        yes=True,
    )
    assert receipt["status"] == "completed"
    config = json.loads((home / ".mcp.json").read_text(encoding="utf-8"))
    assert config["mcpServers"]["theforge"] == {
        "command": "theforge",
        "args": ["mcp", "serve"],
    }

    removed = service.uninstall(scope="user", root=tmp_path / "ignored-project")
    assert removed["status"] in {"completed", "empty"}
    if (home / ".mcp.json").exists():
        assert "theforge" not in json.loads((home / ".mcp.json").read_text(encoding="utf-8")).get(
            "mcpServers", {}
        )
