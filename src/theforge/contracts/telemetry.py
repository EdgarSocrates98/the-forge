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
from theforge.contracts.types import (
    REF_RE,
    BudgetProfile,
    Metric,
    Producer,
    VerificationLevel,
    check_ref,
)

TELEMETRY_SCHEMA = "theforge/RunTelemetry/v1"

MAX_SPANS = 256  # bounded local trace per run
SPAN_NAME_MAX = 80  # span names are short labels: "routing", "provider:<id>"…
SPAN_ATTRS_MAX = 16  # bounded attributes per span
SPAN_ATTR_LEN = 120  # attribute keys/values are short strings

NATIVE_TRACE_SUMMARY_MAX = 240  # a line, not a dump
NATIVE_TRACE_PATH_MAX = 32   # critical-path stages; deeper detail stays native


@dataclass(frozen=True, kw_only=True)
class NativeTrace:
    """A pointer plus bounded summary of the provider's internal trace (Wave F).

    Trace federation keeps internal spans inside the specialist: the provider
    returns ``ref`` (its native trace identity, e.g. an agentops run id) and a
    short ``summary``/``critical_path``; the node span carries only the
    ``native_trace_ref`` link. Expansion is on-demand, never imported whole.
    """

    ref: str = field(metadata={"pattern": REF_RE.pattern})
    summary: str = ""
    critical_path: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.ref:
            raise ContractError("native_trace.ref must not be empty")
        check_ref(self.ref, field="native_trace.ref")
        if len(self.ref) > SPAN_ATTR_LEN:
            raise ContractError(
                f"native_trace.ref exceeds {SPAN_ATTR_LEN} chars")
        if len(self.summary) > NATIVE_TRACE_SUMMARY_MAX:
            raise ContractError(
                f"native_trace.summary exceeds {NATIVE_TRACE_SUMMARY_MAX} chars")
        if len(self.critical_path) > NATIVE_TRACE_PATH_MAX:
            raise ContractError(
                f"native_trace.critical_path exceeds {NATIVE_TRACE_PATH_MAX} entries")
        for stage in self.critical_path:
            if not isinstance(stage, str) or len(stage) > SPAN_ATTR_LEN:
                raise ContractError(
                    f"native_trace.critical_path entries are strings "
                    f"of at most {SPAN_ATTR_LEN} chars")


@dataclass(frozen=True, kw_only=True)
class Span:
    """One timed unit inside a run — the local trace (Cycle 3 Wave J).

    Spans answer *what happened*: which stage ran, for how long, in which order,
    and whether it raised. ``explain`` still answers *why* it happened. Spans
    are append-only per run: the recorder assigns ``id`` in start order and
    ``start_ms`` as an offset from the recorder's creation (monotonic clock —
    never wall time, so ordering survives clock adjustments). ``status`` is
    ``"error"`` when the instrumented block raised; the failure detail lives in
    the run's ``error``/``diagnostic``, the span only marks that it raised.
    """

    id: str  # "s<N>", in start order
    name: str
    start_ms: float
    duration_ms: float
    parent: str | None = None  # id of the enclosing span; None = child of the run
    status: Literal["ok", "error"] = "ok"
    attributes: dict[str, str] = field(default_factory=dict)  # provider, node, outcome…

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not 0 < len(self.name) <= SPAN_NAME_MAX:
            raise ContractError(
                f"span {self.id!r}: name must be a non-empty string of at most "
                f"{SPAN_NAME_MAX} chars")
        for name in ("start_ms", "duration_ms"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ContractError(f"span {self.id!r}: {name} must be a number")
            if value < 0:
                raise ContractError(f"span {self.id!r}: {name} cannot be negative")
        if len(self.attributes) > SPAN_ATTRS_MAX:
            raise ContractError(
                f"span {self.id!r}: attributes exceed {SPAN_ATTRS_MAX}")
        for key, value in self.attributes.items():
            if not isinstance(key, str) or not isinstance(value, str) \
                    or len(key) > SPAN_ATTR_LEN or len(value) > SPAN_ATTR_LEN:
                raise ContractError(
                    f"span {self.id!r}: attributes are bounded strings "
                    f"(<= {SPAN_ATTR_LEN} chars)")


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
    # Tier-2 planner calls this run (plan runs only; 0 on every other outcome).
    semantic_planner_calls: Metric = field(default_factory=Metric)
    # Semantic routing-resolver calls this run (ask runs whose deterministic
    # routing ended ``ambiguous``; 0 elsewhere). The proposal itself is the
    # ``routing-proposal`` artifact, bound by ``ReceiptInputs``.
    semantic_resolver_calls: Metric = field(default_factory=Metric)
    # Context ROI of an ask run (Wave H): pack files the returned evidence cited,
    # and the evidence/finding counts the result carried. ``0`` on every outcome
    # without a valid result; ``unknown`` on plan runs (each node run counts its own).
    files_cited: Metric = field(default_factory=Metric)
    evidence_returned: Metric = field(default_factory=Metric)
    findings_returned: Metric = field(default_factory=Metric)
    provider_revalidation: Literal["hash", "core", "none", "undeclared"] | None = None
    verification_performed: VerificationLevel | None = None
    context_drift: list[str] = field(default_factory=list)
    # The local trace (Wave J): the run's timed units in start order. The same
    # artifact stays the one observability record — metrics aggregate, spans
    # structure; no second tracing system (J1).
    spans: list[Span] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != TELEMETRY_SCHEMA:
            raise ContractError(
                f"unsupported schema {self.schema!r}, expected {TELEMETRY_SCHEMA!r}")
        if len(self.spans) > MAX_SPANS:
            raise ContractError(f"telemetry: {len(self.spans)} spans exceed {MAX_SPANS}")
        seen: set[str] = set()
        for span in self.spans:
            if span.id in seen:
                raise ContractError(f"telemetry: duplicate span id {span.id!r}")
            seen.add(span.id)
            if span.parent is not None and span.parent not in seen:
                raise ContractError(
                    f"telemetry: span {span.id!r} parents unknown/forward span "
                    f"{span.parent!r}")
