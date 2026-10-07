"""ExecutionObservation and GlobalEconomyReceipt (Cycle 4, Wave G).

``ExecutionObservation`` is the atomic, append-only grain of the economy:
one record per provider execution that reached ``execute``, persisted to
``.forge/metrics/observations.jsonl``. Every numeric field is optional —
``None`` means *unknown*, never zero; an unmeasured cost cannot masquerade
as ``0`` (same rule as ``EconomyMetric``).

``GlobalEconomyReceipt`` aggregates the stored observation stream per axis
under the never-silent rules: an axis is ``observed`` only when every
counted observation carried a value, ``unresolved`` when coverage is
partial, ``conflict`` when two observations of the same run disagree on it
(preserved, never silently picked), and ``not_applicable`` when no
observation exists at all.
"""

from dataclasses import dataclass, field
from typing import Final, Literal

from theforge.contracts.base import ContractError
from theforge.contracts.types import Outcome, Producer

EXECUTION_OBSERVATION_SCHEMA = "theforge/ExecutionObservation/v1"
GLOBAL_ECONOMY_SCHEMA = "theforge/GlobalEconomyReceipt/v1"

# Axes the global receipt aggregates, in canonical order. ``estimated`` is a
# valid axis status but never produced by the v1 aggregator — the core does
# not invent values; it is accepted on decode for forward compatibility.
GLOBAL_AXES: Final = (
    "context_bytes",
    "provider_calls",
    "tool_calls",
    "semantic_calls",
    "tokens",
    "cost_usd",
    "wall_time_ms",
)

# History maturity states (§44): the same vocabulary ``negotiation.maturity``
# uses, kept here so receipts and docs share one source of truth concept.
MaturityState = Literal["absent", "cold", "warming", "mature", "stale"]

# Per-axis economy status (§45): exactly what was measured, never a hidden
# zero. ``conflict`` preserves a disagreement instead of resolving it.
EconomyAxisStatus = Literal["observed", "estimated", "unresolved", "conflict", "not_applicable"]

# Verification recorded on an observation: the forge check's verdict, or
# ``not_performed`` when the run never reached verification.
ObservationVerification = Literal["passed", "failed", "not_performed"]


def _nonneg(name: str, value: int | float | None) -> None:
    if value is not None and value < 0:
        raise ContractError(f"observation: {name} cannot be negative")


@dataclass(frozen=True, kw_only=True)
class ExecutionObservation:
    """One measured provider execution (v1).

    ``provider``/``capability``/``run_id`` identify what ran; the
    fingerprint fields scope the observation so history never crosses a
    surface or environment boundary silently (§42-43). ``task_family`` is
    the deterministic label the caller's requirement carried (``None`` when
    the task declared none — families are never inferred). All metric
    fields are ``None`` when the source did not measure them.
    """

    schema: str = EXECUTION_OBSERVATION_SCHEMA
    producer: Producer
    created_at: str
    run_id: str
    provider: str
    capability: str
    status: Outcome
    task_family: str | None = None
    surface_fingerprint: str | None = None
    environment_fingerprint: str | None = None
    profile: str | None = None
    complexity: str | None = None
    context_bytes: int | None = None
    context_items: int | None = None
    context_items_cited: int | None = None
    provider_calls: int | None = None
    tool_calls: int | None = None
    semantic_calls: int | None = None
    tokens: int | None = None
    cost_usd: float | None = None
    wall_time_ms: float | None = None
    verification: ObservationVerification = "not_performed"
    evidence_count: int = 0
    artifact_count: int = 0
    limitations: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != EXECUTION_OBSERVATION_SCHEMA:
            raise ContractError(
                f"unsupported schema {self.schema!r}, expected {EXECUTION_OBSERVATION_SCHEMA!r}"
            )
        for name in ("run_id", "provider", "capability"):
            if not getattr(self, name):
                raise ContractError(f"observation: {name} must not be empty")
        for name in (
            "context_bytes",
            "context_items",
            "context_items_cited",
            "provider_calls",
            "tool_calls",
            "semantic_calls",
            "tokens",
            "cost_usd",
            "wall_time_ms",
            "evidence_count",
            "artifact_count",
        ):
            _nonneg(name, getattr(self, name))
        if (
            self.context_items is not None
            and self.context_items_cited is not None
            and self.context_items_cited > self.context_items
        ):
            raise ContractError("observation: context_items_cited exceeds context_items")


@dataclass(frozen=True, kw_only=True)
class EconomyAxis:
    """One metric aggregated across the observation stream.

    ``coverage`` counts observations that carried a value; ``missing``
    counts those that did not. ``value`` is the sum of observed values and
    is present only when ``status`` is ``observed`` or ``estimated`` — a
    partial or conflicted sum is never shown as a number.
    """

    status: EconomyAxisStatus
    value: float | None = None
    coverage: int = 0
    missing: int = 0

    def __post_init__(self) -> None:
        if self.status in ("observed", "estimated"):
            if not isinstance(self.value, (int, float)) or isinstance(self.value, bool):
                raise ContractError(f"economy axis: status {self.status!r} requires a value")
            if self.value < 0:
                raise ContractError("economy axis: value cannot be negative")
        elif self.value is not None:
            raise ContractError(f"economy axis: status {self.status!r} cannot carry a value")
        if self.coverage < 0 or self.missing < 0:
            raise ContractError("economy axis: coverage/missing cannot be negative")


@dataclass(frozen=True, kw_only=True)
class GlobalEconomyReceipt:
    """Workspace-level economy view built from stored observations (v1).

    ``axes`` always carries every ``GLOBAL_AXES`` key — an absent metric is
    reported ``not_applicable``, never omitted. ``maturity`` maps each
    recorded ``provider/capability@surface`` key to its history state so a
    reader sees which numbers rest on mature vs cold evidence. Conflicting
    observations stay visible in ``conflicts``; their axis reads
    ``conflict``, not a chosen value.
    """

    schema: str = GLOBAL_ECONOMY_SCHEMA
    producer: Producer
    created_at: str
    observations: int
    runs: int
    axes: dict[str, EconomyAxis] = field(default_factory=dict)
    maturity: dict[str, MaturityState] = field(default_factory=dict)
    task_families: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != GLOBAL_ECONOMY_SCHEMA:
            raise ContractError(
                f"unsupported schema {self.schema!r}, expected {GLOBAL_ECONOMY_SCHEMA!r}"
            )
        if self.observations < 0 or self.runs < 0:
            raise ContractError("global economy: counts cannot be negative")
        if self.runs > self.observations:
            raise ContractError("global economy: runs exceed observations")
        unknown = set(self.axes) - set(GLOBAL_AXES)
        if unknown:
            raise ContractError(f"global economy: unknown axes {sorted(unknown)}")
