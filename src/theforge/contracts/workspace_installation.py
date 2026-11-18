"""``forge/WorkspaceInstallation/v2`` — the consolidated workspace
installation document (install-2.1, ADR-0065).

The unified record of what the workspace install pipeline produces and
needs — it extends, never replaces, the v1 family:

- ``forge/InstallationManifest/v1`` (account registry entry, written by
  each forge's bootstrap) gains optional declared fields —
  ``installation_kind``, ``install`` (the install surface) and
  ``depends_on`` — that this document *consumes*.
- ``forge/WorkspaceInstall/v1`` (per-member install records) keeps its
  append-only ``projects[]`` semantics; the consolidated view lives
  under its ``installation`` block as this v2 document.

Per forge the document captures: identity (``forge_id``, ``version``,
``cli``, ``install_command``), ``installation_kind``
(``content``|``service``|``control-tool``), the declared install surface
(operations / flags / hosts / scopes / profiles / approval flag),
install-order dependencies (``depends_on``), resources as qualified ids,
the ownership policy and evidence source, security constraints, the plan
classification (``new``|``updated``|``reused``|``preserved``|``conflict``|
``unsupported-capability``) and the verification state. ``conflicts[]``
records cross-forge managed-path claims — never last-writer-wins.
"""

from dataclasses import dataclass, field
from typing import Literal

from theforge.contracts.base import ContractError

WORKSPACE_INSTALLATION_SCHEMA = "forge/WorkspaceInstallation/v2"

# What a forge installs into the workspace: ``content`` = host assets
# (skills, agents, markers, configs); ``service`` = a runtime service
# surface (e.g. an MCP server hosts connect to); ``control-tool`` =
# orchestration/control-plane tooling (the-forge itself).
INSTALLATION_KINDS = ("content", "service", "control-tool")
InstallationKind = Literal["content", "service", "control-tool"]

# The governed install operations a forge may declare on its surface.
INSTALL_OPERATIONS = (
    "plan",
    "apply",
    "status",
    "doctor",
    "repair",
    "update",
    "uninstall",
    "auto",
    "mcp-verify",
)
INSTALL_SCOPES = ("project", "workspace", "user")
INSTALL_PROFILES = ("minimal", "recommended", "full")
INSTALL_HOSTS = ("claude", "devin", "codex", "copilot")

# Per-forge operation classification of the consolidated plan — a closed
# vocabulary (a plan never guesses): ``new`` (no prior install evidence),
# ``updated`` (managed content would change), ``reused`` (installed and
# unchanged), ``preserved`` (a stronger-scope install takes precedence —
# specialize, never widen), ``conflict`` (loses ≥1 managed path to
# another forge), ``unsupported-capability`` (no honest delegation/plan
# surface for the request).
PLAN_CLASSIFICATIONS = (
    "new",
    "updated",
    "reused",
    "preserved",
    "conflict",
    "unsupported-capability",
)
PlanClassification = Literal[
    "new", "updated", "reused", "preserved", "conflict", "unsupported-capability"
]

# Verification states carried by forge/* documents (same set the
# installkit emits on checks — ``Verdict`` minus harness-level verdicts).
VERIFICATION_STATES = ("PASS", "FAIL", "BLOCKED", "UNVERIFIED", "NOT_APPLICABLE")
VerificationState = Literal["PASS", "FAIL", "BLOCKED", "UNVERIFIED", "NOT_APPLICABLE"]

# Ownership policy vocabulary — where a path/resource's update+removal
# authority lives. Mirrors the install ledger and forge_context kinds.
OWNERSHIP_POLICIES = (
    "forge-owned",  # ledger-managed: only the owning forge's engine mutates
    "shared",  # regenerated shared document (registry, ROUTING.md)
    "managed-block",  # delimited block inside a user file (markers)
    "managed-key",  # one managed key inside a shared config (.mcp.json)
    "user",  # pre-existing user content — never mutated
    "foreign",  # owned by another installer — never mutated
)

# How the ownership evidence was obtained — honesty about provenance.
# ``plan`` = projected ownership from a dry-run plan (nothing written yet);
# the applied values name the actual evidence source.
OWNERSHIP_SOURCES = ("ledger", "receipt", "registry", "manifest", "inventory", "plan")

OwnershipPolicy = Literal[
    "forge-owned", "shared", "managed-block", "managed-key", "user", "foreign"
]
OwnershipSource = Literal["ledger", "receipt", "registry", "manifest", "inventory", "plan"]

_RESOURCE_KINDS = (
    "managed-file",
    "managed-block",
    "managed-key",
    "copied",
    "referenced",
    "bundled",
    "materialized",
)

_FORGE_ID_RE = r"^[a-z0-9][a-z0-9-]*$"


@dataclass(frozen=True, kw_only=True)
class InstallSurface:
    """The install surface a forge declares — the delegation argv builder
    consumes this and only this. Empty lists mean "not declared"."""

    operations: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)  # e.g. "--host"
    hosts: list[str] = field(default_factory=list)
    scopes: list[str] = field(default_factory=list)
    profiles: list[str] = field(default_factory=list)
    approval: str = "--yes"  # the flag the forge's gate honors

    def __post_init__(self) -> None:
        bad_ops = sorted(set(self.operations) - set(INSTALL_OPERATIONS))
        if bad_ops:
            raise ContractError(f"install surface: unknown operations {bad_ops}")
        bad_scopes = sorted(set(self.scopes) - set(INSTALL_SCOPES))
        if bad_scopes:
            raise ContractError(f"install surface: unknown scopes {bad_scopes}")
        bad_profiles = sorted(set(self.profiles) - set(INSTALL_PROFILES))
        if bad_profiles:
            raise ContractError(f"install surface: unknown profiles {bad_profiles}")
        bad_hosts = sorted(set(self.hosts) - set(INSTALL_HOSTS))
        if bad_hosts:
            raise ContractError(f"install surface: unknown hosts {bad_hosts}")
        bad_flags = sorted(f for f in self.flags if not f.startswith("--"))
        if bad_flags:
            raise ContractError(f"install surface: flags must be --long names {bad_flags}")
        if not self.approval.startswith("-"):
            raise ContractError("install surface: approval must be a flag name")


@dataclass(frozen=True, kw_only=True)
class InstallResource:
    """A qualified resource the forge owns or references at the target —
    ``id`` is ``<forge-id>:<resource-id>`` (collision-proof, install-2.0
    §9.4) or a relative managed path."""

    id: str
    kind: str  # one of _RESOURCE_KINDS
    location: str  # relative path or resource location at the target
    sha256: str | None = None
    owner: str | None = None  # forge_id owning update/removal authority
    policy: str | None = None  # update/removal policy where declared

    def __post_init__(self) -> None:
        if not self.id:
            raise ContractError("install resource: id must not be empty")
        if self.kind not in _RESOURCE_KINDS:
            raise ContractError(f"install resource {self.id!r}: unknown kind {self.kind!r}")
        if not self.location:
            raise ContractError(f"install resource {self.id!r}: location must not be empty")


@dataclass(frozen=True, kw_only=True)
class InstallSecurity:
    """Declared install-time security constraints — None = undeclared,
    never assumed permissive or restrictive."""

    requires_network: bool | None = None
    requires_credentials: bool | None = None
    spawn_allowed: bool | None = None
    notes: str | None = None


@dataclass(frozen=True, kw_only=True)
class ForgeInstallation:
    """One forge's installation inside the consolidated document — the
    declared surface plus what the run observed (classification,
    ownership evidence, verification state)."""

    forge_id: str
    installation_kind: InstallationKind = "content"
    version: str | None = None
    cli: str | None = None
    install_command: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    surface: InstallSurface = field(default_factory=InstallSurface)
    resources: list[InstallResource] = field(default_factory=list)
    owned_paths: list[str] = field(default_factory=list)
    ownership: OwnershipPolicy = "forge-owned"  # one of OWNERSHIP_POLICIES
    ownership_source: OwnershipSource | None = None  # one of OWNERSHIP_SOURCES
    security: InstallSecurity = field(default_factory=InstallSecurity)
    verification: VerificationState = "UNVERIFIED"  # one of VERIFICATION_STATES
    classification: PlanClassification | None = None
    classification_detail: str = ""

    def __post_init__(self) -> None:
        import re

        if not re.match(_FORGE_ID_RE, self.forge_id):
            raise ContractError(f"invalid forge_id {self.forge_id!r}")
        if self.installation_kind not in INSTALLATION_KINDS:
            raise ContractError(
                f"{self.forge_id}: installation_kind {self.installation_kind!r} "
                f"not in {INSTALLATION_KINDS}"
            )
        if self.classification is not None and self.classification not in PLAN_CLASSIFICATIONS:
            raise ContractError(
                f"{self.forge_id}: classification {self.classification!r} "
                f"not in {PLAN_CLASSIFICATIONS}"
            )
        if self.forge_id in self.depends_on:
            raise ContractError(f"{self.forge_id}: depends_on may not list itself")
        if self.verification not in VERIFICATION_STATES:
            raise ContractError(
                f"{self.forge_id}: verification {self.verification!r} not in {VERIFICATION_STATES}"
            )
        if self.ownership not in OWNERSHIP_POLICIES:
            raise ContractError(
                f"{self.forge_id}: ownership {self.ownership!r} not in {OWNERSHIP_POLICIES}"
            )
        if self.ownership_source is not None and self.ownership_source not in OWNERSHIP_SOURCES:
            raise ContractError(
                f"{self.forge_id}: ownership_source {self.ownership_source!r} not in "
                f"{OWNERSHIP_SOURCES}"
            )
        if len(set(self.depends_on)) != len(self.depends_on):
            raise ContractError(f"{self.forge_id}: duplicate depends_on entries")


@dataclass(frozen=True, kw_only=True)
class PathConflict:
    """Two forges claiming the same managed asset path. The winner keeps
    write authority (existing owner first, then install order); the loser
    is skipped for that path — never last-writer-wins."""

    path: str
    claimants: list[str]  # every forge_id planning this path
    winner: str
    loser: str
    resolution: str | None = None  # apply outcome; None in plan-only mode
    detail: str = ""

    def __post_init__(self) -> None:
        if self.winner == self.loser:
            raise ContractError(f"path conflict {self.path!r}: winner equals loser")
        if self.winner not in self.claimants or self.loser not in self.claimants:
            raise ContractError(f"path conflict {self.path!r}: winner/loser must be claimants")


@dataclass(frozen=True, kw_only=True)
class WorkspaceInstallation:
    """The consolidated workspace installation document — plan view,
    apply record and ownership inventory in one shape."""

    schema: str = WORKSPACE_INSTALLATION_SCHEMA
    workspace_root: str
    created_at: str
    updated_at: str
    scope: str = "workspace"  # resolved scope of the run
    order: list[str] = field(default_factory=list)  # install order (forge_ids)
    order_note: str | None = None  # undeclared deps / broken cycles, honestly
    forges: list[ForgeInstallation] = field(default_factory=list)
    conflicts: list[PathConflict] = field(default_factory=list)
    members: list[str] = field(default_factory=list)  # discovered member paths
    notes: list[str] = field(default_factory=list)
    verification: VerificationState = "UNVERIFIED"  # aggregate of forge verifications

    def __post_init__(self) -> None:
        if self.schema != WORKSPACE_INSTALLATION_SCHEMA:
            raise ContractError(
                f"unsupported schema {self.schema!r}, expected {WORKSPACE_INSTALLATION_SCHEMA!r}"
            )
        if self.scope not in INSTALL_SCOPES:
            raise ContractError(f"scope {self.scope!r} not in {INSTALL_SCOPES}")
        if self.verification not in VERIFICATION_STATES:
            raise ContractError(f"verification {self.verification!r}")
        ids = [f.forge_id for f in self.forges]
        dups = sorted({i for i in ids if ids.count(i) > 1})
        if dups:
            raise ContractError(f"duplicate forge entries {dups}")
        unknown = sorted(set(self.order) - set(ids))
        if unknown:
            raise ContractError(f"install order names unregistered forges {unknown}")
