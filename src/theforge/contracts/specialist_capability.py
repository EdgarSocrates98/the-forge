"""SpecialistCapability: what a specialist declares it can do (lf-0027, PHASE 1).

Namespace mapping: the cross-forge integrations spec
(``prompt_evo_integrations.md``, audited in forge-cli
``docs/integration/``) names this contract ``forge/SpecialistCapability/v1``.
Inside the-forge, ecosystem contracts live in the ``theforge/<Name>/v1``
namespace (``theforge/ForgeManifest/v1``, ``theforge/Handoff/v1``), so the
spec's ``forge/`` prefix maps to ``theforge/`` here — same contract, core
naming. The older specialist-control contracts in ``contracts/specialist.py``
keep their historical ``forge/...`` ids.

Who produces it: each specialist ships the document with its published
package (package-bundled manifest) and/or answers it through a governed
surface. Who consumes it: the-forge discovery/routing (``discovery.py``) and
sibling forges — always as data over the Forge Protocol or a file, never by
importing core internals.

What it is not: a routing manifest. ``theforge/ForgeManifest/v1`` (adapter
``describe``) keeps capabilities as routable protocol surface — actions,
state, operation_class, signals. ``SpecialistCapability`` is the *discovery
advertisement*: how a capability is invoked (``entrypoint`` argv), what it
needs (``requires``/``optional_deps``/``permissions``/``network``), what it
may cost (``external_cost``), and how it can be found and verified
(``discovery_mode``/``verification_mode``) before it runs. Declared, never
inferred: an absent manifest is an honest gap, not a zero-capability claim.

Vocabulary mapping from the spec's conceptual example: ``risk: read-only``
maps to ``risk="read_only"`` (``OperationClass`` — the existing closed
vocabulary is reused, not duplicated); ``execution_mode: cloud-read`` maps
to ``execution_mode="remote"`` with ``risk="external_read"`` and
``network=True``.
"""

from dataclasses import dataclass, field
from typing import Literal

from theforge.contracts.base import ContractError
from theforge.contracts.manifest import CAPABILITY_ID, PROVIDER_ID
from theforge.contracts.semver import parse_semver
from theforge.contracts.types import (
    FINDING_CLASSES as FINDING_CLASSES,
)
from theforge.contracts.types import (
    FindingClass as FindingClass,
)
from theforge.contracts.types import (
    OperationClass,
)

SPECIALIST_CAPABILITY_SCHEMA = "theforge/SpecialistCapability/v1"

# Bundled/checkout file names a specialist uses to ship this manifest.
# Discovery looks for them in checkout roots (``<checkout>/<name>``) and in
# installed distributions (``importlib.metadata`` file lists) — metadata
# reads only, never an arbitrary command execution.
CAPABILITY_MANIFEST_NAMES: tuple[str, ...] = (
    "forge.capabilities.json",
    "forge.capability.json",
)

# Specialist version that means "not pinned by the author — resolved at
# install/runtime" (the spec example's ``version: runtime-detected``).
RUNTIME_DETECTED = "runtime-detected"

# Where the capability executes relative to the caller: ``local`` runs on
# the caller's machine, ``remote`` reaches an external/cloud API, ``hybrid``
# does both.
CapabilityExecutionMode = Literal["local", "remote", "hybrid"]

# How a consumer may learn the capability exists: ``manifest`` (a document
# bundled with the package/checkout), ``package`` (installed package
# metadata), ``registry`` (a provider/registry listing), ``entry-point``
# (Python entry point or console script), ``probe`` (a governed probe — the
# specialist's own surface answers).
CapabilityDiscoveryMode = Literal[
    "manifest", "package", "registry", "entry-point", "probe"
]

# How the declaration can be validated before execution: ``self-declared``
# (the manifest is the only evidence — honest floor), ``handshake`` (a
# version handshake confirms the live surface), ``probe`` (a health/execute
# probe through the governed path confirms it).
CapabilityVerificationMode = Literal["self-declared", "handshake", "probe"]

# Declared possibility of cost outside the caller's machine. ``unknown`` is
# the honest default — "no external cost" is a positive claim
# (Observed != Estimated; undeclared is never "free").
ExternalCost = Literal["none", "possible", "metered", "unknown"]

# ``FindingClass``/``FINDING_CLASSES`` are imported from ``contracts.types``
# (above) so the ForgeManifest's ``Capability`` declares the same vocabulary
# (lf-0031) without importing this module; they stay importable from here.


@dataclass(frozen=True, kw_only=True)
class SpecialistIdentity:
    """Who publishes the manifest: provider id, version, domain."""

    id: str = field(metadata={"pattern": PROVIDER_ID.pattern})
    version: str = "unknown"
    domain: str = ""

    def __post_init__(self) -> None:
        if not PROVIDER_ID.match(self.id):
            raise ContractError(f"invalid specialist id {self.id!r}")
        if (
            self.version not in (RUNTIME_DETECTED, "unknown")
            and parse_semver(self.version) is None
        ):
            raise ContractError(
                f"specialist {self.id}: version {self.version!r} is not SemVer 2.0.0 "
                f"(or {RUNTIME_DETECTED!r})"
            )


@dataclass(frozen=True, kw_only=True)
class SurfaceSupport:
    """A governed surface the specialist declares (``health``/``handoff``)."""

    supported: bool = False
    detail: str = ""


@dataclass(frozen=True, kw_only=True)
class DeclaredCapability:
    """One invocable capability declared by a specialist.

    ``entrypoint`` is a typed argv template — the same placeholder convention
    as ``DelegationEntry.command`` (``{cli}``, ``{python}``, ``{checkout}``,
    ``{target}``) — never a shell string. Empty means the capability is only
    reachable through the specialist's own surface (Forge Protocol ops or a
    declared workflow), not through a direct argv.
    """

    id: str = field(metadata={"pattern": CAPABILITY_ID.pattern})
    description: str = ""
    version: str = ""
    input_schema: str = ""
    output_schema: str = ""
    entrypoint: list[str] = field(default_factory=list)
    execution_mode: CapabilityExecutionMode = "local"
    risk: OperationClass = "read_only"
    requires: list[str] = field(default_factory=list)
    optional_deps: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    network: bool = False
    external_cost: ExternalCost = "unknown"
    timeout_s: int | None = None
    limitations: list[str] = field(default_factory=list)
    discovery_mode: CapabilityDiscoveryMode = "manifest"
    verification_mode: CapabilityVerificationMode = "self-declared"
    # Declared analysis class of emitted findings (lf-0031). Data, never an
    # instruction: consumers group by it, nothing executes on it.
    finding_class: FindingClass = ""

    def __post_init__(self) -> None:
        if not CAPABILITY_ID.match(self.id):
            raise ContractError(f"invalid capability id {self.id!r}")
        if self.version and parse_semver(self.version) is None:
            raise ContractError(
                f"capability {self.id}: version {self.version!r} is not SemVer 2.0.0"
            )
        if self.timeout_s is not None and self.timeout_s <= 0:
            raise ContractError(
                f"capability {self.id}: timeout_s must be a positive integer"
            )
        if self.finding_class not in ("", "static", "runtime", "architectural"):
            raise ContractError(
                f"capability {self.id}: finding_class {self.finding_class!r} is not "
                "one of '', 'static', 'runtime', 'architectural'"
            )
        if self.execution_mode == "local" and self.network:
            # An honest declaration never pairs "runs locally" with "needs
            # network" — that combination is remote or hybrid.
            raise ContractError(
                f"capability {self.id}: network=True requires execution_mode "
                "'remote' or 'hybrid', not 'local'"
            )


@dataclass(frozen=True, kw_only=True)
class SpecialistCapability:
    """The discovery advertisement one specialist publishes (v1)."""

    schema: str = SPECIALIST_CAPABILITY_SCHEMA
    specialist: SpecialistIdentity
    capabilities: list[DeclaredCapability] = field(default_factory=list)
    health: SurfaceSupport = field(default_factory=SurfaceSupport)
    handoff: SurfaceSupport = field(default_factory=SurfaceSupport)

    def __post_init__(self) -> None:
        if self.schema != SPECIALIST_CAPABILITY_SCHEMA:
            raise ContractError(
                f"unsupported schema {self.schema!r}, expected {SPECIALIST_CAPABILITY_SCHEMA!r}"
            )
        ids = [c.id for c in self.capabilities]
        dups = sorted({i for i in ids if ids.count(i) > 1})
        if dups:
            raise ContractError(f"duplicate capability ids {dups}")

    def capability(self, capability_id: str) -> DeclaredCapability | None:
        return next((c for c in self.capabilities if c.id == capability_id), None)
