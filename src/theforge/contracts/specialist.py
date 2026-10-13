"""Forge Specialist Lifecycle Contract v1.

Separated axes (per FASE 1): *installation state* is not *activation
state* is not *execution stage*. Each is its own Literal so the states
can never be confused.
"""

from dataclasses import dataclass, field

from .base import ContractError

LIFECYCLE_SCHEMA = "forge/SpecialistLifecycleState/v1"
AGENTIC_MANIFEST_SCHEMA = "forge/SpecialistAgenticManifest/v1"
DELEGATION_REQUEST_SCHEMA = "forge/SpecialistDelegationRequest/v1"
DELEGATION_RESULT_SCHEMA = "forge/SpecialistDelegationResult/v1"
HOST_ACTIVATION_PLAN_SCHEMA = "forge/HostActivationPlan/v1"
HOST_ACTIVATION_RECEIPT_SCHEMA = "forge/HostActivationReceipt/v1"

LifecycleState = (
    "UNKNOWN",
    "DISCOVERED",
    "NOT_INSTALLED",
    "INSTALLABLE",
    "INSTALLING",
    "INSTALLED",
    "CONFIGURED",
    "REGISTERED",
    "HEALTHY",
    "HOST_ACTIVATION_PENDING",
    "HOST_ACTIVATED",
    "READY",
    "DEGRADED",
    "INCOMPATIBLE",
    "FAILED",
    "UNINSTALLING",
    "REMOVED",
)

# Valid transitions; anything else is a ContractError at transition() time.
TRANSITIONS: dict[str, frozenset[str]] = {
    "UNKNOWN": frozenset({"DISCOVERED"}),
    "DISCOVERED": frozenset({"NOT_INSTALLED", "INSTALLED", "INCOMPATIBLE"}),
    "NOT_INSTALLED": frozenset({"INSTALLABLE", "UNKNOWN"}),
    "INSTALLABLE": frozenset({"INSTALLING", "NOT_INSTALLED"}),
    "INSTALLING": frozenset({"INSTALLED", "FAILED"}),
    "INSTALLED": frozenset({"CONFIGURED", "FAILED", "UNINSTALLING"}),
    "CONFIGURED": frozenset({"REGISTERED", "INSTALLED", "FAILED"}),
    "REGISTERED": frozenset({"HEALTHY", "DEGRADED", "FAILED"}),
    "HEALTHY": frozenset({"HOST_ACTIVATION_PENDING", "READY", "DEGRADED"}),
    "HOST_ACTIVATION_PENDING": frozenset({"HOST_ACTIVATED", "HEALTHY", "DEGRADED"}),
    "HOST_ACTIVATED": frozenset({"READY", "DEGRADED"}),
    "READY": frozenset({"DEGRADED", "FAILED", "UNINSTALLING"}),
    "DEGRADED": frozenset({"HEALTHY", "FAILED", "UNINSTALLING"}),
    "FAILED": frozenset({"INSTALLING", "UNINSTALLING", "REMOVED"}),
    "UNINSTALLING": frozenset({"REMOVED", "INSTALLED", "FAILED"}),
    "REMOVED": frozenset(),
}

ExecutionMode = (
    "DIRECT_CAPABILITY",
    "SPECIALIST_WORKFLOW",
    "HOST_AGENTIC",
    "MULTI_SPECIALIST",
    "DIAGNOSTIC_ONLY",
)

# Host-driven delegation stages; COMPLETED requires real evidence.
DelegationStage = (
    "PREPARED",
    "SUBMITTED",
    "RUNNING",
    "COMPLETED",
    "FAILED",
    "BLOCKED",
)

ActivationOutcome = ("ACTIVE_NOW", "RESTART_REQUIRED", "UNSUPPORTED")


def transition(current: str, target: str) -> str:
    """Validate a lifecycle transition; return target or raise."""
    if current not in TRANSITIONS:
        raise ContractError(f"unknown lifecycle state {current!r}")
    if target not in TRANSITIONS[current]:
        raise ContractError(f"invalid lifecycle transition {current!r} -> {target!r}")
    return target


@dataclass(frozen=True, kw_only=True)
class SpecialistLifecycle:
    """State snapshot for one specialist; persisted per installation."""

    schema: str = LIFECYCLE_SCHEMA
    provider: str = ""
    version: str = "unknown"
    installation_state: str = "UNKNOWN"
    activation_state: str = "HOST_ACTIVATION_PENDING"
    host: str | None = None
    evidence: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != LIFECYCLE_SCHEMA:
            raise ContractError(f"unsupported schema {self.schema!r}")
        if self.installation_state not in TRANSITIONS:
            raise ContractError(f"unknown installation_state {self.installation_state!r}")

    def advance(self, target: str, evidence: str | None = None) -> "SpecialistLifecycle":
        """Return a new snapshot moved to `target` (validates transition)."""
        transition(self.installation_state, target)
        ev = [*self.evidence, evidence] if evidence else list(self.evidence)
        return SpecialistLifecycle(
            provider=self.provider,
            version=self.version,
            installation_state=target,
            activation_state=self.activation_state,
            host=self.host,
            evidence=ev,
        )


@dataclass(frozen=True, kw_only=True)
class DelegationEntry:
    """One executable delegation entry point declared by a specialist.

    ``command`` is a template resolved at delegation time:
    ``{cli}`` → runnable cli argv (installed launcher, else
    ``python -c <cli_entry>`` from the checkout), ``{python}`` →
    interpreter, ``{checkout}`` → local clone path, ``{target}`` → the
    delegation target path.
    """

    id: str
    mode: str  # ExecutionMode
    command: list[str] = field(default_factory=list)  # argv template
    description: str = ""
    read_only: bool = True


@dataclass(frozen=True, kw_only=True)
class AgenticManifest:
    """What a specialist exposes beyond deterministic capabilities.

    Declarative; every entry must name a real executable surface —
    `verify_command` presence is what makes a workflow delegable.
    """

    schema: str = AGENTIC_MANIFEST_SCHEMA
    provider: str = ""
    version: str = "unknown"
    cli: str = ""
    cli_entry: str = ""  # "module:function" for checkout-based invocation
    workflows: list[DelegationEntry] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    agents: list[str] = field(default_factory=list)
    coordinators: list[str] = field(default_factory=list)
    mcp_command: list[str] = field(default_factory=list)
    mcp_verify_tool: str | None = None
    host_adapters: list[str] = field(default_factory=list)  # claude/devin/codex/copilot
    requires_network: bool = False
    requires_credentials: bool = False
    read_only_default: bool = True

    def __post_init__(self) -> None:
        if self.schema != AGENTIC_MANIFEST_SCHEMA:
            raise ContractError(f"unsupported schema {self.schema!r}")


@dataclass(frozen=True, kw_only=True)
class DelegationRequest:
    schema: str = DELEGATION_REQUEST_SCHEMA
    task_id: str = ""
    intent: str = ""
    provider: str = ""
    execution_mode: str = "DIRECT_CAPABILITY"
    target: str = "project"  # project | workspace
    command: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    budget: dict[str, int] = field(default_factory=dict)
    expected_outputs: list[str] = field(default_factory=list)
    verification: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != DELEGATION_REQUEST_SCHEMA:
            raise ContractError(f"unsupported schema {self.schema!r}")
        if self.execution_mode not in ExecutionMode:
            raise ContractError(f"unknown execution_mode {self.execution_mode!r}")


@dataclass(frozen=True, kw_only=True)
class DelegationResult:
    schema: str = DELEGATION_RESULT_SCHEMA
    task_id: str = ""
    provider: str = ""
    stage: str = "PREPARED"  # DelegationStage
    execution_mode: str = "DIRECT_CAPABILITY"
    executed_steps: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    stdout_tail: list[str] = field(default_factory=list)
    stderr_tail: list[str] = field(default_factory=list)
    exit_code: int | None = None
    elapsed_ms: int = 0

    def __post_init__(self) -> None:
        if self.schema != DELEGATION_RESULT_SCHEMA:
            raise ContractError(f"unsupported schema {self.schema!r}")
        if self.stage not in DelegationStage:
            raise ContractError(f"unknown delegation stage {self.stage!r}")
        # FASE 5.3: COMPLETED requires real execution evidence.
        if self.stage == "COMPLETED" and self.exit_code is None:
            raise ContractError("stage COMPLETED requires exit_code evidence")


@dataclass(frozen=True, kw_only=True)
class HostActivationPlan:
    schema: str = HOST_ACTIVATION_PLAN_SCHEMA
    host: str = ""
    provider: str = ""
    scope: str = "project"
    components: list[str] = field(default_factory=list)  # skills|agents|mcp
    writes: list[str] = field(default_factory=list)
    approval_required: bool = True

    def __post_init__(self) -> None:
        if self.schema != HOST_ACTIVATION_PLAN_SCHEMA:
            raise ContractError(f"unsupported schema {self.schema!r}")


@dataclass(frozen=True, kw_only=True)
class HostActivationReceipt:
    schema: str = HOST_ACTIVATION_RECEIPT_SCHEMA
    host: str = ""
    provider: str = ""
    scope: str = "project"
    outcome: str = "UNSUPPORTED"  # ActivationOutcome
    checks: dict[str, str] = field(default_factory=dict)  # name -> PASS/FAIL/UNVERIFIED
    resume_instructions: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != HOST_ACTIVATION_RECEIPT_SCHEMA:
            raise ContractError(f"unsupported schema {self.schema!r}")
        if self.outcome not in ActivationOutcome:
            raise ContractError(f"unknown activation outcome {self.outcome!r}")
