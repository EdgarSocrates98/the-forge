"""ForgeManifest: what a provider declares about itself via `describe`."""

import re
from dataclasses import dataclass, field

from theforge.contracts.base import ContractError
from theforge.contracts.types import CapabilityState, OperationClass, RevalidationStrategy

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

    def __post_init__(self) -> None:
        if not CAPABILITY_ID.match(self.id):
            raise ContractError(f"invalid capability id {self.id!r}")
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

    def capability(self, capability_id: str) -> Capability | None:
        return next((c for c in self.capabilities if c.id == capability_id), None)

    def resolve(self, name: str) -> tuple[Capability, bool] | None:
        """(capability, via_alias): the canonical id wins over an alias; None if unknown."""
        canonical = self.capability(name)
        if canonical is not None:
            return canonical, False
        aliased = next((c for c in self.capabilities if name in c.aliases), None)
        return (aliased, True) if aliased is not None else None
