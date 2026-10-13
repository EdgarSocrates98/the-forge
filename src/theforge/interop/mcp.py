"""MCP registry bridge (Cycle 4, Wave J).

Decodes the official MCP Registry API (``GET /v0{,.1}/servers``,
``registry.modelcontextprotocol.io``) into bounded ``McpRegistryDocument``
metadata. Like the A2A bridge: document translation only — no tool
definitions are loaded (progressive discovery stays one page at a time,
§71) and nothing here installs or launches a server (§70).

Trust boundary (§72): server names, descriptions and tool authority are
*declared* by publishers — untrusted until verified independently. The
entry preserves the policy dimensions: network egress (``remotes``),
install paths (``packages``) and credential needs (headers/env vars).
"""

from __future__ import annotations

import json
from typing import Any

from theforge.contracts.mcp import (
    McpPackage,
    McpRegistryDocument,
    McpRemote,
    McpServerEntry,
)

__all__ = [
    "MAX_MCP_PAGE",
    "parse_server_list",
    "server_entry_from_json",
]

MAX_MCP_PAGE = 100  # hard bound regardless of what the remote returns

_MAX_FIELD = 4096
_MAX_PACKAGES = 64
_MAX_REMOTES = 16


def _text(value: Any, cap: int = _MAX_FIELD) -> str:
    return str(value)[:cap] if isinstance(value, str) else ""


def server_entry_from_json(data: Any, *, limitations: list[str]) -> McpServerEntry | None:
    """One ``server`` object → ``McpServerEntry``; ``None`` when structurally
    unusable (the reason is appended to ``limitations``)."""
    if not isinstance(data, dict):
        limitations.append("mcp entry is not an object — skipped")
        return None
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        limitations.append("mcp entry without a usable 'name' — skipped")
        return None

    entry_limits: list[str] = []
    remotes: list[McpRemote] = []
    requires_credentials = False
    for remote in (data.get("remotes") or [])[:_MAX_REMOTES]:
        if not isinstance(remote, dict):
            continue
        url = remote.get("url")
        rtype = remote.get("type")
        if not isinstance(url, str) or not isinstance(rtype, str):
            continue
        headers = remote.get("headers")
        header_names = (
            sorted(
                {
                    n
                    for n in (h.get("name") for h in headers if isinstance(h, dict))
                    if isinstance(n, str)
                }
            )
            if isinstance(headers, list)
            else []
        )
        if header_names:
            requires_credentials = True
        remotes.append(McpRemote(type=_text(rtype, 64), url=_text(url, 1024), headers=header_names))

    packages: list[McpPackage] = []
    for pkg in (data.get("packages") or [])[:_MAX_PACKAGES]:
        if not isinstance(pkg, dict):
            continue
        rtype, ident = pkg.get("registryType"), pkg.get("identifier")
        if not isinstance(rtype, str) or not isinstance(ident, str):
            continue
        packages.append(
            McpPackage(
                registry_type=_text(rtype, 32),
                identifier=_text(ident, 512),
                version=_text(pkg.get("version"), 128) or None,
            )
        )
        for var in pkg.get("environmentVariables") or []:
            if isinstance(var, dict) and (var.get("isSecret") or var.get("isRequired")):
                requires_credentials = True

    title = data.get("title")
    description = data.get("description")
    version = data.get("version")
    if remotes:
        entry_limits.append(
            "remote transports — use implies network egress to the declared endpoints"
        )
    if packages:
        entry_limits.append(
            "packages are install paths for humans — the Forge never installs MCP servers (§70)"
        )
    if requires_credentials:
        entry_limits.append("declared credential needs — secrets stay with the operator")
    entry_limits.append("metadata is publisher-declared — unverified")

    try:
        return McpServerEntry(
            name=_text(name, 256),
            title=_text(title, 256) or None,
            description=_text(description) or None,
            version=_text(version, 128) or None,
            remotes=remotes,
            packages=packages,
            requires_network=bool(remotes),
            requires_credentials=requires_credentials,
            limitations=entry_limits,
        )
    except Exception:  # invalid name shape — recorded, not fatal
        limitations.append(f"mcp entry {name[:64]!r} rejected by contract — skipped")
        return None


def parse_server_list(
    text: str, *, source_id: str, produced_at: str
) -> tuple[McpRegistryDocument | None, str | None]:
    """Decode a ``/v0{,.1}/servers`` response. Returns (document, error).

    Both official shapes are tolerated: ``{"servers": [{"server": {...}}]}``
    (envelope) and ``{"servers": [{...}]}`` (flat). The ``nextCursor`` is
    surfaced, never followed — the caller asks for the next page explicitly.
    """
    try:
        data = json.loads(text)
    except ValueError as exc:
        return None, f"mcp registry response is not valid JSON: {exc}"
    if not isinstance(data, dict):
        return None, "mcp registry response is not a JSON object"
    servers = data.get("servers")
    if not isinstance(servers, list):
        return None, "mcp registry response has no 'servers' array"

    limitations: list[str] = []
    entries: list[McpServerEntry] = []
    for raw in servers[:MAX_MCP_PAGE]:
        server = raw.get("server") if isinstance(raw, dict) else None
        entry = server_entry_from_json(
            server if isinstance(server, dict) else raw, limitations=limitations
        )
        if entry is not None:
            entries.append(entry)
    if len(servers) > MAX_MCP_PAGE:
        limitations.append(
            f"response truncated at {MAX_MCP_PAGE} servers (progressive discovery bound)"
        )

    metadata = data.get("metadata")
    cursor = metadata.get("nextCursor") if isinstance(metadata, dict) else None
    try:
        document = McpRegistryDocument(
            source_id=source_id,
            produced_at=produced_at,
            entries=entries,
            next_cursor=cursor if isinstance(cursor, str) else None,
            limitations=limitations,
        )
    except Exception as exc:
        return None, f"mcp registry document invalid: {exc}"
    return document, None
