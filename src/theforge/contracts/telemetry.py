"""RunTelemetry: per-run phase durations, typed counters and the effective profile.

Core-only artifact (never crosses the Forge Protocol; closed schema). The same contract
represents an ``ask`` run and a plan run (Wave D): every metric defaults to
``Metric(kind="unknown")`` so a writer fills only what it measured, and the contract does
not cap ``providers_executed`` (> 1 is valid for a plan run; the ``ask`` invariant of at
most one provider is proven by the flow tests).
"""

from dataclasses import dataclass, field
from typing import Literal

from theforge.contracts.base import ContractError
from theforge.contracts.types import BudgetProfile, Metric, Producer, VerificationLevel

TELEMETRY_SCHEMA = "theforge/RunTelemetry/v1"


@dataclass(frozen=True, kw_only=True)
class ProfileSnapshot:
    name: BudgetProfile
    budget_bytes: int
    max_files: int
    tiers: list[str]
    # Profile tiers intersected with the capability declaration (empty if the run never
    # reached the context phase, and for plan runs).
    effective_tiers: list[str]
    negotiation_rounds: int
    max_providers: int
    fallback: bool
    verification: VerificationLevel
    execute_timeout_s: float


@dataclass(frozen=True, kw_only=True)
class RunTelemetry:
    schema: str = TELEMETRY_SCHEMA
    producer: Producer
    created_at: str
    run_id: str
    profile: ProfileSnapshot
    scan_ms: Metric = field(default_factory=Metric)
    routing_ms: Metric = field(default_factory=Metric)
    context_ms: Metric = field(default_factory=Metric)
    provider_ms: Metric = field(default_factory=Metric)
    files_scanned: Metric = field(default_factory=Metric)
    files_selected: Metric = field(default_factory=Metric)
    files_hashed: Metric = field(default_factory=Metric)
    bytes_hashed: Metric = field(default_factory=Metric)
    cache_hits: Metric = field(default_factory=Metric)
    cache_misses: Metric = field(default_factory=Metric)
    context_bytes: Metric = field(default_factory=Metric)
    providers_executed: Metric = field(default_factory=Metric)
    fallbacks_used: Metric = field(default_factory=Metric)
    negotiation_rounds: Metric = field(default_factory=Metric)
    provider_revalidation: Literal["hash", "core", "none", "undeclared"] | None = None
    verification_performed: VerificationLevel | None = None
    context_drift: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != TELEMETRY_SCHEMA:
            raise ContractError(
                f"unsupported schema {self.schema!r}, expected {TELEMETRY_SCHEMA!r}")
