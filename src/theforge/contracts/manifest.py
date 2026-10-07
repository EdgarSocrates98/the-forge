"""ForgeManifest: what a provider declares about itself via `describe`."""

import re
from dataclasses import dataclass, field

from theforge.contracts.base import ContractError
from theforge.contracts.negotiation import CapabilityOffer
from theforge.contracts.types import (
    FEATURE_ID_RE,
    SHA256_RE,
    CapabilityState,
    OperationClass,
    RevalidationStrategy,
)

MANIFEST_SCHEMA = "theforge/ForgeManifest/v1"
CAPABILITY_ID = re.compile(r"^[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)+$")
PROVIDER_ID = re.compile(r"^[a-z][a-z0-9-]*$")
REQUIRED_OPS = ("describe", "health")


@dataclass(frozen=True, kw_only=True)
class Signals:
    keywords: list[str] = field(default_factory=list)
    file_globs: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class CapabilityContext:
    """Context tiers a capability accepts beyond references (defaults reproduce v1)."""

    excerpts: bool = False
    requests: bool = False


# Artifact/evidence type identifier (e.g. "code-analysis-evidence"); free of any
# domain registry: a provider declares what it produces/consumes, the graph links.
ARTIFACT_TYPE_ID = re.compile(r"^[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)*$")
# MCP server names as declared by the official registry (e.g.
# "io.github.org/server") — same loose pattern as contracts/mcp.py.
MCP_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,255}$")
# Capability reference: "<capability>" (same provider) or "<provider>/<capability>".
CAPABILITY_REF = re.compile(
    r"^([a-z][a-z0-9-]*/)?[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)+$")


@dataclass(frozen=True, kw_only=True)
class CapabilityRelations:
    """Optional declared relationships of a capability (capability-graph edges).

    ``produces``/``consumes`` name artifact types; the rest name capabilities
    (``<capability>`` for same-provider, ``<provider>/<capability>`` across).
    Declared, not verified: the target may be absent from the registry — the
    graph keeps the edge and names it in limitations.
    """

    produces: list[str] = field(default_factory=list)
    consumes: list[str] = field(default_factory=list)
    requires: list[str] = field(default_factory=list)
    complements: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    can_verify: list[str] = field(default_factory=list)
    can_review: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        for name in ("produces", "consumes"):
            for value in getattr(self, name):
                if not ARTIFACT_TYPE_ID.match(value):
                    raise ContractError(
                        f"capability relations.{name}: invalid artifact type {value!r}")
        for name in ("requires", "complements", "conflicts", "can_verify",
                     "can_review"):
            for value in getattr(self, name):
                if not CAPABILITY_REF.match(value):
                    raise ContractError(
                        f"capability relations.{name}: invalid capability ref {value!r}")


@dataclass(frozen=True, kw_only=True)
class Capability:
    id: str = field(metadata={"pattern": CAPABILITY_ID.pattern})
    actions: list[str]
    default_action: str
    state: CapabilityState
    operation_class: OperationClass
    description: str = ""
    signals: Signals = field(default_factory=Signals)
    # Alternative names that resolve to this capability (format rules live in the taxonomy).
    aliases: list[str] = field(default_factory=list)
    deprecated: bool = False
    # Suggested replacement capability id; may belong to another provider.
    replaced_by: str | None = None
    context: CapabilityContext = field(default_factory=CapabilityContext)
    # Whether the capability declares it consumes the handoff of an ExecuteRequest.
    accepts_handoff: bool = False
    # Whether the capability answers ``plan`` requests of ``purpose="proposal"``
    # with a SemanticPlanProposal (the tier-2 semantic planner, wave C).
    proposes_plans: bool = False
    # Whether the capability answers ``resolve`` requests with a RoutingProposal
    # (the semantic routing fallback, wave K); the provider must also declare
    # the ``resolve`` op.
    resolves_ambiguity: bool = False
    # Optional declared relationships feeding the capability graph (v1 additive).
    relations: CapabilityRelations = field(default_factory=CapabilityRelations)
    # Richer self-description for capability negotiation v2 (additive): None =
    # legacy mode — the negotiator answers demands from the plain fields only.
    offer: "CapabilityOffer | None" = None
    # Cycle 4/Wave J (additive): declared MCP tooling dependencies — official
    # registry server names (e.g. "io.github.org/server"). The Forge may
    # *detect* availability; it never installs or configures MCP servers.
    mcp_requires: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not CAPABILITY_ID.match(self.id):
            raise ContractError(f"invalid capability id {self.id!r}")
        for dep in self.mcp_requires:
            if not MCP_NAME_RE.match(dep):
                raise ContractError(
                    f"capability {self.id}: invalid mcp_requires name {dep!r}")
        if not self.actions:
            raise ContractError(f"capability {self.id}: actions must not be empty")
        if self.default_action not in self.actions:
            raise ContractError(
                f"capability {self.id}: default_action {self.default_action!r} not in actions"
            )
        if self.replaced_by == self.id:
            raise ContractError(f"capability {self.id}: replaced_by equal to its own id")


@dataclass(frozen=True, kw_only=True)
class ExecutionInfo:
    local: bool = True
    offline: bool = True
    requires_network: bool = False
    # Same inputs give the same result; None = undeclared (never "reproducible").
    deterministic: bool | None = None


@dataclass(frozen=True, kw_only=True)
class ForgeManifest:
    schema: str = MANIFEST_SCHEMA
    id: str = field(metadata={"pattern": PROVIDER_ID.pattern})
    version: str
    protocols: list[str]
    ops: list[str]
    domains: list[str] = field(default_factory=list)
    capabilities: list[Capability] = field(default_factory=list)
    execution: ExecutionInfo = field(default_factory=ExecutionInfo)
    limitations: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    # How the provider revalidates the content it read; None = undeclared (v1).
    context_revalidation: RevalidationStrategy | None = None
    # Declared protocol features ("<name>/v<major>", e.g. "handoff/v1"); empty means
    # the provider declares none beyond what its ops/capability flags imply.
    features: list[str] = field(default_factory=list)
    # The adapter release the responder declares itself to be, when it is one.
    adapter_version: str | None = None
    # Provider-declared sha256 of the native/specialist surface it serves.
    native_surface_fingerprint: str | None = None

    def __post_init__(self) -> None:
        if self.schema != MANIFEST_SCHEMA:
            raise ContractError(f"unsupported manifest schema {self.schema!r}")
        if not PROVIDER_ID.match(self.id):
            raise ContractError(f"invalid provider id {self.id!r}")
        missing = [op for op in REQUIRED_OPS if op not in self.ops]
        if missing:
            raise ContractError(f"manifest {self.id}: missing required ops {missing}")
        if not self.protocols:
            raise ContractError(f"manifest {self.id}: protocols must not be empty")
        ids = [c.id for c in self.capabilities]
        dups = sorted({i for i in ids if ids.count(i) > 1})
        if dups:
            raise ContractError(f"manifest {self.id}: duplicate capability ids {dups}")
        aliases = [a for c in self.capabilities for a in c.aliases]
        dup_aliases = sorted({a for a in aliases if aliases.count(a) > 1})
        if dup_aliases:
            raise ContractError(f"manifest {self.id}: duplicate capability aliases {dup_aliases}")
        clashes = sorted(set(aliases) & set(ids))
        if clashes:
            raise ContractError(f"manifest {self.id}: alias equal to capability id {clashes}")
        bad_features = sorted({f for f in self.features if not FEATURE_ID_RE.match(f)})
        if bad_features:
            raise ContractError(f"manifest {self.id}: malformed feature ids {bad_features}")
        dup_features = sorted({f for f in self.features if self.features.count(f) > 1})
        if dup_features:
            raise ContractError(f"manifest {self.id}: duplicate features {dup_features}")
        if self.native_surface_fingerprint is not None and not SHA256_RE.fullmatch(
                self.native_surface_fingerprint):
            raise ContractError(
                f"manifest {self.id}: native_surface_fingerprint is not a sha256 digest")

    def capability(self, capability_id: str) -> Capability | None:
        return next((c for c in self.capabilities if c.id == capability_id), None)

    def resolve(self, name: str) -> tuple[Capability, bool] | None:
        """(capability, via_alias): the canonical id wins over an alias; None if unknown."""
        canonical = self.capability(name)
        if canonical is not None:
            return canonical, False
        aliased = next((c for c in self.capabilities if name in c.aliases), None)
        return (aliased, True) if aliased is not None else None
