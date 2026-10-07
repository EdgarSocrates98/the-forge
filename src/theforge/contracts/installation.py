"""InstallationPlan: what is missing to run a plan. Planning only: nothing is installed.

v2 (Cycle 4, Wave F): ``InstallationPlanV2`` — the deterministic, approval-gated
plan to provision a *remote candidate* into an isolated environment. A v2 plan
is a document: it declares steps and evidence requirements and stops.
``planning_only=True`` is contractual, not a hint — no path in this codebase
executes it (remote/actual installation is a separate milestone).
"""

from dataclasses import dataclass, field
from typing import Literal

from theforge.contracts.base import ContractError
from theforge.contracts.registry import DistributionRef, RuntimeRequirements, SignatureRef
from theforge.contracts.semver import parse_semver
from theforge.contracts.types import SHA256_RE, Producer

INSTALLATION_SCHEMA = "theforge/InstallationPlan/v1"


@dataclass(frozen=True, kw_only=True)
class InstallationItem:
    provider: str
    state: str  # registry state or "unavailable" (health)
    reason: str  # registry/provider detail (redacted)
    suggested_action: str  # ErrorInfo.unlock, else the detail itself
    source: Literal["registry", "health"]
    nodes: list[str] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class InstallationPlan:
    schema: str = INSTALLATION_SCHEMA
    producer: Producer
    created_at: str
    run_id: str
    planning_only: Literal[True] = True
    items: list[InstallationItem] = field(default_factory=list)  # at least one

    def __post_init__(self) -> None:
        if self.schema != INSTALLATION_SCHEMA:
            raise ContractError(
                f"unsupported schema {self.schema!r}, expected {INSTALLATION_SCHEMA!r}")
        if not self.items:
            raise ContractError("installation plan: items must not be empty")


INSTALLATION_V2_SCHEMA = "theforge/InstallationPlan/v2"

# The approval flow as an ordered, enumerable contract (§29) — the plan carries
# every stage with status; execution is out of scope for this milestone.
INSTALL_STAGES = ("plan", "approval", "download", "verify", "isolated-install",
                  "provider-check", "surface-fingerprint", "health")


@dataclass(frozen=True, kw_only=True)
class InstallStep:
    """One stage of the governed install flow (§29)."""

    stage: str                        # one of INSTALL_STAGES
    description: str
    status: Literal["pending"] = "pending"


@dataclass(frozen=True, kw_only=True)
class InstallApproval:
    """The approval gate — recorded on the plan, not implied by it."""

    required: bool = True
    granted: bool = False
    granted_by: str | None = None     # e.g. "cli-user", a policy id
    granted_at: str | None = None


@dataclass(frozen=True, kw_only=True)
class RollbackStrategy:
    """How to undo: previous version/environment/fingerprints (§F-rollback)."""

    action: Literal["restore-previous", "remove-new"] = "remove-new"
    previous_version: str | None = None
    previous_manifest_sha256: str | None = None
    previous_surface_fingerprint: str | None = None
    environment: str | None = None    # isolated env that would be discarded


@dataclass(frozen=True, kw_only=True)
class InstallationPlanV2:
    """Deterministic, approval-gated install plan for a remote candidate
    (theforge/InstallationPlan/v2). Plan-only by construction."""

    schema: str = INSTALLATION_V2_SCHEMA
    producer: Producer
    created_at: str
    planning_only: Literal[True] = True
    # What is being installed — pinned, never "latest" (§30).
    provider: str
    version: str
    source: str                       # configured registry source id
    registry: str | None = None       # declared registry identity
    distribution: DistributionRef
    expected_hashes: dict[str, str] = field(default_factory=dict)
    signature: SignatureRef | None = None
    runtime: RuntimeRequirements | None = None
    # Where: an isolated environment is the default target (name, not a path —
    # the plan describes, it does not create).
    environment: str                  # e.g. "venv:providers/security-forge-1.3.2"
    dependencies: list[str] = field(default_factory=list)   # pinned name==ver
    permissions: list[str] = field(default_factory=list)    # declared needs
    post_install_checks: list[str] = field(default_factory=list)
    rollback: RollbackStrategy = field(default_factory=RollbackStrategy)
    steps: list[InstallStep] = field(default_factory=list)
    approval: InstallApproval = field(default_factory=InstallApproval)
    limitations: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != INSTALLATION_V2_SCHEMA:
            raise ContractError(
                f"unsupported schema {self.schema!r}, expected "
                f"{INSTALLATION_V2_SCHEMA!r}")
        parsed = parse_semver(self.version)
        if parsed is None or self.version in ("latest", ""):
            raise ContractError(
                f"installation plan: version {self.version!r} is not a pinned "
                "SemVer — 'latest' is never installable (§30)")
        if self.distribution.kind == "pip-package" and (
                not self.distribution.package or not self.distribution.version):
            raise ContractError(
                "installation plan: pip-package distribution requires pinned "
                "package + version")
        for name, digest in self.expected_hashes.items():
            if not SHA256_RE.fullmatch(digest):
                raise ContractError(
                    f"installation plan: expected hash {name!r} is not sha256")
        stages = [s.stage for s in self.steps]
        unknown = [s for s in stages if s not in INSTALL_STAGES]
        if unknown:
            raise ContractError(
                f"installation plan: unknown stages {sorted(set(unknown))}")
        if stages != sorted(stages, key=INSTALL_STAGES.index) or len(
                set(stages)) != len(stages):
            raise ContractError(
                "installation plan: steps must follow the governed stage order "
                "(plan→approval→download→verify→isolated-install→provider-check"
                "→surface-fingerprint→health)")
        if not self.approval.required and not self.approval.granted:
            raise ContractError(
                "installation plan: approval.required=false demands "
                "approval.granted — a plan cannot skip its own gate")
