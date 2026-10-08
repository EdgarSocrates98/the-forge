"""Cross-provider economy contracts (Wave F / Phases 19-21).

A specialist owns its internal economy; The Forge never re-derives it, it
federates it. ``ProviderEconomyReceipt`` is the provider's own accounting,
summarized as data: per-metric status makes UNKNOWN != ZERO structural — a
metric the provider did not measure is ``unresolved`` (or ``not_applicable``)
with no value, never a ``0`` that a rollup could silently treat as free.

``EconomyRollup`` is the plan run's cross-provider aggregate, composed by the
core deterministically from the node receipts: totals sum only compatible
values, ``not_applicable`` contributes nothing, one ``unresolved`` contributor
blocks the sum, and sources that disagree are named in ``conflicts`` — never
averaged silently.
"""

from dataclasses import dataclass, field
from typing import Final, Literal

from theforge.contracts.base import ContractError
from theforge.contracts.types import Producer

__all__ = [
    "ECONOMY_METRICS",
    "ECONOMY_RECEIPT_SCHEMA",
    "ECONOMY_ROLLUP_SCHEMA",
    "EconomyMetric",
    "EconomyRollup",
    "MetricStatus",
    "NodeEconomy",
    "ProviderEconomyReceipt",
]

ECONOMY_RECEIPT_SCHEMA = "theforge/ProviderEconomyReceipt/v1"
ECONOMY_ROLLUP_SCHEMA = "theforge/EconomyRollup/v1"

# The provider's per-metric confidence. ``unresolved`` = not measured (never a
# hidden zero); ``not_applicable`` = the provider does not spend this at all.
MetricStatus = Literal["measured", "estimated", "unresolved", "not_applicable"]

# The metric names a ProviderEconomyReceipt carries, in canonical order; the
# rollup's ``totals`` uses them as keys.
ECONOMY_METRICS: Final = (
    "context_bytes",
    "tool_calls",
    "model_calls",
    "provider_tokens",
    "cost_usd",
    "wall_time_ms",
)


@dataclass(frozen=True, kw_only=True)
class EconomyMetric:
    """One economy metric: a value plus the status that says what it means.

    ``measured``/``estimated`` require a non-negative number; ``unresolved``
    and ``not_applicable`` reject one — an unmeasured cost cannot masquerade
    as ``0``.
    """

    value: float | None = None
    status: MetricStatus = "unresolved"

    def __post_init__(self) -> None:
        if self.status in ("measured", "estimated"):
            if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
                raise ContractError(
                    f"economy metric: status {self.status!r} requires a numeric value"
                )
            if self.value < 0:
                raise ContractError("economy metric: value cannot be negative")
        elif self.value is not None:
            raise ContractError(f"economy metric: status {self.status!r} cannot carry a value")


@dataclass(frozen=True, kw_only=True)
class ProviderEconomyReceipt:
    """The provider's internal economy for one execution, summarized (v1).

    ``run`` is the provider-native run/case ref the accounting belongs to
    (``""`` when the provider has no such identity). ``basis`` names what the
    summary was computed from (e.g. ``"case-metrics"``, ``"transcript"``) so a
    reader can judge the accounting; ``limitations`` carries the caveats.
    """

    schema: str = ECONOMY_RECEIPT_SCHEMA
    provider: str
    run: str = ""
    context_bytes: EconomyMetric = field(default_factory=EconomyMetric)
    tool_calls: EconomyMetric = field(default_factory=EconomyMetric)
    model_calls: EconomyMetric = field(default_factory=EconomyMetric)
    provider_tokens: EconomyMetric = field(default_factory=EconomyMetric)
    cost_usd: EconomyMetric = field(default_factory=EconomyMetric)
    wall_time_ms: EconomyMetric = field(default_factory=EconomyMetric)
    basis: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != ECONOMY_RECEIPT_SCHEMA:
            raise ContractError(
                f"unsupported schema {self.schema!r}, expected {ECONOMY_RECEIPT_SCHEMA!r}"
            )
        if not self.provider:
            raise ContractError("provider economy: provider must not be empty")


@dataclass(frozen=True, kw_only=True)
class NodeEconomy:
    """A provider economy receipt attributed to the plan node that produced it."""

    node: str
    receipt: ProviderEconomyReceipt

    def __post_init__(self) -> None:
        if not self.node:
            raise ContractError("node economy: node must not be empty")


@dataclass(frozen=True, kw_only=True)
class EconomyRollup:
    """A plan run's cross-provider economy view (v1), core-composed.

    ``receipts`` keeps each node's provider accounting verbatim; ``totals``
    aggregates per metric under the never-silent rules (an ``unresolved``
    contributor blocks the sum, ``not_applicable`` contributes nothing);
    ``conflicts`` names sources that reported the same native run with
    different values — their metric stays ``unresolved``.
    """

    schema: str = ECONOMY_ROLLUP_SCHEMA
    producer: Producer
    created_at: str
    plan_run: str
    receipts: list[NodeEconomy] = field(default_factory=list)
    totals: dict[str, EconomyMetric] = field(default_factory=dict)
    conflicts: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != ECONOMY_ROLLUP_SCHEMA:
            raise ContractError(
                f"unsupported schema {self.schema!r}, expected {ECONOMY_ROLLUP_SCHEMA!r}"
            )
        if not self.plan_run:
            raise ContractError("economy rollup: plan_run must not be empty")
