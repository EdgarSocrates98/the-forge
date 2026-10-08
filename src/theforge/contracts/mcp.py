"""MCP (Model Context Protocol) boundary contracts (Cycle 4, Wave J).

MCP = tools/resources/prompts access — *not* Forge provider orchestration.
An MCP server is tooling a provider may depend on, never a routable Forge
provider; these documents therefore use their own schema names and never
flow into ``RegistryDocument.entries`` or capability negotiation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from theforge.contracts.base import ContractError

MCP_SERVER_SCHEMA = "theforge/McpServerEntry/v1"
MCP_DOCUMENT_SCHEMA = "theforge/McpRegistryDocument/v1"

# Official MCP registry server names look like "io.github.org/server";
# permissive on purpose — validation is on the source side, tolerant decode.
MCP_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,255}$")


@dataclass(frozen=True, kw_only=True)
class McpRemote:
    """A remote transport endpoint declared by an MCP server entry."""

    type: str  # "streamable-http", "sse", ...
    url: str
    # Header *names* only — remote MCP auth needs credentials the Forge never
    # stores; declaring them preserves "credential needs" (§72).
    headers: list[str] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class McpPackage:
    """An installable package reference — declared, never installed by the
    Forge (§70/§72): this is how a human would obtain the server, not how
    the Forge runs it."""

    registry_type: str  # npm, pypi, oci, nuget, mcpb
    identifier: str
    version: str | None = None


@dataclass(frozen=True, kw_only=True)
class McpServerEntry:
    """One MCP server's declared metadata (theforge/McpServerEntry/v1)."""

    schema: str = MCP_SERVER_SCHEMA
    name: str
    title: str | None = None
    description: str | None = None
    version: str | None = None
    remotes: list[McpRemote] = field(default_factory=list)
    packages: list[McpPackage] = field(default_factory=list)
    # Policy dimensions preserved from the declaration (§72): whether the
    # server needs network egress and/or credentials to be usable.
    requires_network: bool = False
    requires_credentials: bool = False
    limitations: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != MCP_SERVER_SCHEMA:
            raise ContractError(
                f"unsupported schema {self.schema!r}, expected {MCP_SERVER_SCHEMA!r}"
            )
        if not MCP_NAME_RE.match(self.name):
            raise ContractError(f"mcp server entry: invalid name {self.name!r}")


@dataclass(frozen=True, kw_only=True)
class McpRegistryDocument:
    """Bounded page of MCP server metadata (theforge/McpRegistryDocument/v1).

    Progressive discovery (§71): one page, ``limit``-bounded — the cursor is
    surfaced for an explicit next call, never auto-followed.
    """

    schema: str = MCP_DOCUMENT_SCHEMA
    source_id: str
    produced_at: str
    entries: list[McpServerEntry] = field(default_factory=list)
    next_cursor: str | None = None  # explicit pagination handle, not followed
    limitations: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != MCP_DOCUMENT_SCHEMA:
            raise ContractError(
                f"unsupported schema {self.schema!r}, expected {MCP_DOCUMENT_SCHEMA!r}"
            )
        names = [e.name for e in self.entries]
        if len(set(names)) != len(names):
            raise ContractError("mcp registry document: duplicate server names")
