"""Forge Knowledge Layer contracts (agentic prompt §5-7, §36-37, §51-58).

A ``ForgeKnowledge`` package is *bootstrap knowledge*: what the control plane
must know about a specialist before it is installed — identity, purpose,
recognition signals, real install methods, how to verify the install, which
verifiers to prefer and the default trust classification. It never enumerates
runtime capabilities: ``capabilities_source`` is pinned to
``runtime_discovery`` — the live ``describe`` surface is authoritative, and a
knowledge file that lists capabilities would drift by construction (§53).

Bootstrap metadata never overrides runtime reality (§7): when the provider is
installed, the manifest, surface fingerprint and health answer; the package
only guides discovery, routing hints and installation.
"""

from dataclasses import dataclass, field

from theforge.contracts.base import ContractError
from theforge.contracts.manifest import PROVIDER_ID
from theforge.contracts.types import SHA256_RE

FORGE_KNOWLEDGE_SCHEMA = "theforge/ForgeKnowledge/v1"

_MAX_LIST = 64

INSTALL_KINDS = ("venv-pip", "pip", "pipx", "uv", "editable", "git")


@dataclass(frozen=True, kw_only=True)
class InstallMethod:
    """One real, verifiable install path — never an arbitrary recipe (§24, §54).

    ``command`` is documentation-grade: the adapter checkout path stays a
    placeholder (``<the-forge>``) because the recipe is local, not a remote
    payload. ``verify`` is the command that proves the install (import probe,
    ``--version``, doctor).
    """

    kind: str  # one of INSTALL_KINDS
    command: str
    verify: str
    prerequisites: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.kind not in INSTALL_KINDS:
            raise ContractError(f"install method: unknown kind {self.kind!r}")
        for forbidden in ("curl", "| sh", "|sh", "wget"):
            if forbidden in self.command:
                raise ContractError(
                    f"install method: forbidden installer pattern {forbidden!r} (§24)"
                )


@dataclass(frozen=True, kw_only=True)
class ForgeKnowledge:
    """Bootstrap knowledge package for one specialist (v1)."""

    schema: str = FORGE_KNOWLEDGE_SCHEMA
    id: str
    name: str
    family: str
    summary: str
    repository: str = ""
    package: str | None = None
    binary: str | None = None
    adapter: str | None = None  # adapters/<name> path inside this repo
    python: str | None = None  # e.g. ">=3.11"
    appropriate_for: list[str] = field(default_factory=list)
    inappropriate_for: list[str] = field(default_factory=list)
    intents: list[str] = field(default_factory=list)
    technologies: list[str] = field(default_factory=list)
    environments: list[str] = field(default_factory=list)
    install: list[InstallMethod] = field(default_factory=list)
    verify_install: str | None = None
    discover_command: str | None = None
    preferred_verifiers: list[str] = field(default_factory=list)
    independent_verification: bool = True
    trust_default: str = "unverified"
    composes_with: list[str] = field(default_factory=list)
    fallback: list[str] = field(default_factory=list)
    limitations_note: str = ""
    examples: list[str] = field(default_factory=list)
    capabilities_source: str = "runtime_discovery"
    # §51-52 freshness: the version/surface this package was recorded against.
    tested_version: str | None = None
    tested_surface: str | None = field(
        default=None, metadata={"pattern": SHA256_RE.pattern}
    )
    recorded_at: str | None = None

    def __post_init__(self) -> None:
        if self.schema != FORGE_KNOWLEDGE_SCHEMA:
            raise ContractError(f"forge knowledge: unsupported schema {self.schema!r}")
        if not PROVIDER_ID.match(self.id):
            raise ContractError(f"forge knowledge: invalid provider id {self.id!r}")
        if not PROVIDER_ID.match(self.family):
            raise ContractError(f"forge knowledge: invalid family id {self.family!r}")
        if not self.summary:
            raise ContractError(f"forge knowledge {self.id}: summary is required")
        if not self.install:
            raise ContractError(
                f"forge knowledge {self.id}: at least one install method is required"
            )
        if self.trust_default != "unverified":
            raise ContractError(
                f"forge knowledge {self.id}: trust_default must be 'unverified' — "
                "bootstrap knowledge can never grant trust (§44-45)"
            )
        if self.capabilities_source != "runtime_discovery":
            raise ContractError(
                f"forge knowledge {self.id}: capabilities_source must be "
                "'runtime_discovery' — knowledge packages never enumerate "
                "capabilities (§53)"
            )
        for ref in (*self.preferred_verifiers, *self.composes_with, *self.fallback):
            if not PROVIDER_ID.match(ref):
                raise ContractError(
                    f"forge knowledge {self.id}: invalid provider reference {ref!r}"
                )
        for field_name, values in (
            ("appropriate_for", self.appropriate_for),
            ("inappropriate_for", self.inappropriate_for),
            ("intents", self.intents),
            ("technologies", self.technologies),
            ("environments", self.environments),
            ("examples", self.examples),
        ):
            if len(values) > _MAX_LIST:
                raise ContractError(f"forge knowledge {self.id}: {field_name} too long")
