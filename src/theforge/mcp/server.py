"""The Forge MCP server.

This module is a thin, governed adapter over the existing CLI and services.
The CLI remains the source of truth for routing, policy, installation and
redaction; MCP adds a structured tool surface for hosts such as Claude, Codex,
Devin and Copilot.

The SDK import is deliberately lazy because the MCP extra is optional. The
default transport is stdio, while Streamable HTTP is available explicitly for
multi-client/local service scenarios.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from theforge import __version__

_MAX_PAGE = 100
_MAX_SKILL_BYTES = 12_000
_SDK_HINT = (
    "The Forge MCP is optional. Install it with `pip install 'theforge-core[mcp]'` "
    "or `uv tool install 'theforge-core[mcp]'`."
)


def _page(items: list[dict[str, Any]], limit: int, offset: int) -> dict[str, Any]:
    if not 1 <= limit <= _MAX_PAGE:
        raise ValueError(f"limit must be between 1 and {_MAX_PAGE}")
    if offset < 0:
        raise ValueError("offset must be zero or greater")
    selected = items[offset : offset + limit]
    next_offset = offset + len(selected) if offset + len(selected) < len(items) else None
    return {
        "items": selected,
        "total_count": len(items),
        "count": len(selected),
        "offset": offset,
        "has_more": next_offset is not None,
        "next_offset": next_offset,
    }


def _json_payload(stdout: str, code: int) -> dict[str, Any]:
    text = stdout.strip()
    if text:
        try:
            payload = json.loads(text)
            if isinstance(payload, dict):
                if code != 0:
                    payload.setdefault("exit_code", code)
                return payload
        except json.JSONDecodeError:
            pass
    return {
        "status": "error",
        "exit_code": code,
        "error": {
            "code": "MCP_CLI_OUTPUT_INVALID",
            "detail": "The Forge CLI did not return a structured JSON document.",
        },
    }


def _run_cli(root: Path, *argv: str) -> dict[str, Any]:
    """Run an existing read/write CLI workflow and preserve its JSON contract."""
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "theforge.cli.main", *argv, "--root", str(root), "--json"],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "error": {"code": "MCP_CLI_TIMEOUT", "detail": "The Forge CLI exceeded 120 seconds."},
        }
    except OSError as exc:
        return {
            "status": "error",
            "error": {"code": "MCP_CLI_SPAWN_FAILED", "detail": type(exc).__name__},
        }
    return _json_payload(completed.stdout, completed.returncode)


def _skills() -> list[dict[str, Any]]:
    from theforge.install import render

    source = render._skills_src()
    if source is None:
        return []
    result: list[dict[str, Any]] = []
    for path in sorted(source.iterdir()):
        skill_file = path / "SKILL.md" if path.is_dir() else None
        if skill_file is None or not skill_file.is_file():
            continue
        try:
            head = skill_file.read_text(encoding="utf-8")[:2_000]
        except OSError:
            continue
        description = ""
        for line in head.splitlines():
            value = line.strip()
            if value.startswith("description:"):
                description = value.split(":", 1)[1].strip()[:200]
                break
            if value and not value.startswith(("#", "---", "name:")):
                description = value[:200]
                break
        result.append(
            {
                "id": path.name,
                "description": description,
                "source": "theforge-host-assets",
                "path": str(skill_file),
            }
        )
    return result


def _skill_read(skill_id: str) -> dict[str, Any]:
    if not skill_id or skill_id in {".", ".."} or any(c in skill_id for c in "/\\"):
        return {"status": "error", "error": {"code": "INVALID_SKILL_ID"}}
    from theforge.install import render

    source = render._skills_src()
    path = source / skill_id / "SKILL.md" if source is not None else None
    if path is None or not path.is_file():
        return {"status": "error", "error": {"code": "SKILL_NOT_FOUND", "skill_id": skill_id}}
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return {"status": "error", "error": {"code": "SKILL_UNREADABLE", "skill_id": skill_id}}
    truncated = len(content.encode("utf-8")) > _MAX_SKILL_BYTES
    encoded = content.encode("utf-8")[:_MAX_SKILL_BYTES]
    return {
        "status": "ok",
        "skill_id": skill_id,
        "content": encoded.decode("utf-8", errors="ignore"),
        "truncated": truncated,
        "max_bytes": _MAX_SKILL_BYTES,
    }


def _register(
    server: Any,
    *,
    name: str,
    description: str,
    read_only: bool,
    destructive: bool,
    idempotent: bool = True,
    open_world: bool = False,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    from mcp.types import ToolAnnotations

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        server.add_tool(
            fn,
            name=name,
            description=description,
            annotations=ToolAnnotations(
                title=description.split(".", 1)[0],
                readOnlyHint=read_only,
                destructiveHint=destructive,
                idempotentHint=idempotent,
                openWorldHint=open_world,
            ),
            structured_output=True,
        )
        return fn

    return decorator


def build_server(root: Path | None = None) -> Any:
    """Build the server without starting a transport, which keeps it testable."""
    try:
        from mcp.server.mcpserver import MCPServer
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised without extra
        raise RuntimeError(_SDK_HINT) from exc

    workspace = (root or Path.cwd()).expanduser().resolve()
    server = MCPServer(
        name="theforge_mcp",
        version=__version__,
        instructions=(
            "The Forge is a local-first control plane. Start with discovery or plan tools. "
            "Use ask/orchestrate only when execution is intended; installation tools are "
            "preview-only until confirm=true. The server operates on its configured workspace."
        ),
    )

    @_register(
        server,
        name="theforge_status",
        description="Return The Forge workspace status and the last recorded run.",
        read_only=True,
        destructive=False,
    )
    def status() -> dict[str, Any]:
        return _run_cli(workspace, "status")

    @_register(
        server,
        name="theforge_doctor",
        description="Inspect The Forge host, workspace and registered provider health.",
        read_only=True,
        destructive=False,
    )
    def doctor() -> dict[str, Any]:
        return _run_cli(workspace, "doctor")

    @_register(
        server,
        name="theforge_agents_list",
        description="List the governed AgentSpec agents shipped by The Forge with pagination.",
        read_only=True,
        destructive=False,
    )
    def agents_list(limit: int = 50, offset: int = 0) -> dict[str, Any]:
        data = _run_cli(workspace, "agents", "list")
        return {**data, "agents": _page(data.get("agents", []), limit, offset)}

    @_register(
        server,
        name="theforge_skills_list",
        description="List The Forge skills available to host integrations with pagination.",
        read_only=True,
        destructive=False,
    )
    def skills_list(limit: int = 50, offset: int = 0) -> dict[str, Any]:
        return {"skills": _page(_skills(), limit, offset)}

    @_register(
        server,
        name="theforge_skill_read",
        description="Read one bounded The Forge SKILL.md by its catalog id.",
        read_only=True,
        destructive=False,
    )
    def skill_read(skill_id: str) -> dict[str, Any]:
        return _skill_read(skill_id)

    @_register(
        server,
        name="theforge_specialists_list",
        description="List federated specialist Forges and their observed lifecycle state.",
        read_only=True,
        destructive=False,
        open_world=True,
    )
    def specialists_list(limit: int = 50, offset: int = 0, probe: bool = False) -> dict[str, Any]:
        args = ["specialists", "list"]
        if not probe:
            args.append("--no-probe")
        data = _run_cli(workspace, *args)
        return {**data, "specialists": _page(data.get("specialists", []), limit, offset)}

    @_register(
        server,
        name="theforge_capabilities_search",
        description="Search registered specialist capabilities by a human task query.",
        read_only=True,
        destructive=False,
        open_world=True,
    )
    def capabilities_search(query: str) -> dict[str, Any]:
        if not query.strip():
            return {"status": "error", "error": {"code": "EMPTY_QUERY"}}
        return _run_cli(workspace, "capabilities", "search", query)

    @_register(
        server,
        name="theforge_graph",
        description="Return the cached declared and observed capability graph for the workspace.",
        read_only=True,
        destructive=False,
        open_world=True,
    )
    def graph(ref: str | None = None, federated: bool = False) -> dict[str, Any]:
        args = ["graph"]
        if ref:
            args.extend(["--ref", ref])
        if federated:
            args.append("--federated")
        return _run_cli(workspace, *args)

    @_register(
        server,
        name="theforge_workspace_show",
        description="Describe the workspace using cached manifests without executing providers.",
        read_only=True,
        destructive=False,
    )
    def workspace_show() -> dict[str, Any]:
        return _run_cli(workspace, "workspace", "show")

    @_register(
        server,
        name="theforge_installation_status",
        description="Inspect The Forge installation ledger and drift for a project or workspace.",
        read_only=True,
        destructive=False,
    )
    def installation_status(scope: str = "project") -> dict[str, Any]:
        if scope not in {"project", "workspace", "user"}:
            return {"status": "error", "error": {"code": "INVALID_SCOPE"}}
        return _run_cli(workspace, "install", "status", "--scope", scope)

    @_register(
        server,
        name="theforge_plan_task",
        description="Create a governed, read-only multi-provider plan for an engineering task.",
        read_only=True,
        destructive=False,
        open_world=True,
    )
    def plan_task(intent: str, profile: str = "auto", target: str | None = None) -> dict[str, Any]:
        if not intent.strip():
            return {"status": "error", "error": {"code": "EMPTY_INTENT"}}
        if profile not in {"auto", "economy", "balanced", "max"}:
            return {"status": "error", "error": {"code": "INVALID_PROFILE"}}
        args = ["plan", intent, "--profile", profile]
        if target:
            args.extend(["--target", target])
        return _run_cli(workspace, *args)

    @_register(
        server,
        name="theforge_ask_task",
        description="Route and execute one task through The Forge's governed specialist path.",
        read_only=False,
        destructive=False,
        idempotent=False,
        open_world=True,
    )
    def ask_task(
        intent: str,
        capability: str | None = None,
        target: str | None = None,
        provider: str | None = None,
        approvals: list[str] | None = None,
        allow_unverified: bool = False,
    ) -> dict[str, Any]:
        if not intent.strip():
            return {"status": "error", "error": {"code": "EMPTY_INTENT"}}
        args = ["ask", intent]
        if capability:
            args.extend(["--capability", capability])
        if target:
            args.extend(["--target", target])
        if provider:
            args.extend(["--use", provider])
        if allow_unverified:
            args.append("--allow-unverified")
        for approval in approvals or []:
            args.extend(["--approve", approval])
        return _run_cli(workspace, *args)

    @_register(
        server,
        name="theforge_orchestrate_plan",
        description="Build a justified multi-specialist DAG without executing it.",
        read_only=True,
        destructive=False,
        open_world=True,
    )
    def orchestrate_plan(intent: str, max_providers: int = 4) -> dict[str, Any]:
        if not intent.strip():
            return {"status": "error", "error": {"code": "EMPTY_INTENT"}}
        if not 1 <= max_providers <= 16:
            return {"status": "error", "error": {"code": "INVALID_MAX_PROVIDERS"}}
        return _run_cli(
            workspace,
            "orchestrate",
            "plan",
            intent,
            "--max-providers",
            str(max_providers),
        )

    @_register(
        server,
        name="theforge_orchestrate_run",
        description="Execute a governed multi-specialist DAG for an engineering task.",
        read_only=False,
        destructive=False,
        idempotent=False,
        open_world=True,
    )
    def orchestrate_run(
        intent: str,
        target: str | None = None,
        max_providers: int = 4,
        authorizations: list[str] | None = None,
    ) -> dict[str, Any]:
        if not intent.strip():
            return {"status": "error", "error": {"code": "EMPTY_INTENT"}}
        if not 1 <= max_providers <= 16:
            return {"status": "error", "error": {"code": "INVALID_MAX_PROVIDERS"}}
        args = ["orchestrate", "run", intent, "--max-providers", str(max_providers)]
        if target:
            args.extend(["--target", target])
        for authorization in authorizations or []:
            args.extend(["--authorize", authorization])
        return _run_cli(workspace, *args)

    @_register(
        server,
        name="theforge_install",
        description=(
            "Preview or apply The Forge assets and MCP configuration in a target scope; "
            "confirm is required to write."
        ),
        read_only=False,
        destructive=False,
        idempotent=True,
    )
    def install(
        scope: str = "project",
        components: str = "mcp,skills,agents",
        host: str = "all",
        confirm: bool = False,
    ) -> dict[str, Any]:
        if scope not in {"project", "workspace", "user"}:
            return {"status": "error", "error": {"code": "INVALID_SCOPE"}}
        if host not in {"claude", "devin", "codex", "copilot", "all"}:
            return {"status": "error", "error": {"code": "INVALID_HOST"}}
        args = [
            "install",
            "apply",
            "--scope",
            scope,
            "--host",
            host,
            "--components",
            components,
            "--dry-run" if not confirm else "--yes",
        ]
        return _run_cli(workspace, *args)

    return server


def run_server(
    *, transport: str = "stdio", host: str = "127.0.0.1", port: int = 8000, root: Path | None = None
) -> int:
    try:
        server = build_server(root)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    if transport == "stdio":
        server.run("stdio")
    else:
        server.run("streamable-http", host=host, port=port, streamable_http_path="/mcp")
    return 0


__all__ = ["build_server", "run_server"]
