"""TelemetryRecorder: measure the phases and counters of a run and build its RunTelemetry.

Phases (``scan``, ``routing``, ``context``, ``provider``) are timed with an injectable
monotonic clock (seconds) and accumulate, so ``provider`` sums every ``execute`` call of
every negotiation round. Counters accumulate too. Anything never recorded comes out of
``build()`` as ``Metric(kind="unknown")`` and its field name is listed in ``unknowns``; no
method assumes the context or provider phases were reached, so the plan run of
``cross-forge-foundation`` can record only ``scan``, ``routing`` and ``providers_executed``
(no upper bound here: the ``ask`` limit of one provider belongs to the flow).

Spans (Wave J): every ``phase`` and every explicit ``span`` also appends a ``Span``
to the same artifact — the local trace of what ran, in which order, for how long and
whether it raised. Span ids are assigned at start under a lock (``s<N>``), so workers
of a concurrent plan cannot collide; ``start_ms`` is an offset from recorder creation.
The yielded ``SpanHandle.attrs`` is filled by the body — the outcome is only known on
the way out. The trace stays inside ``RunTelemetry``: one observability artifact, no
second system (J1).
"""

import threading
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from time import perf_counter
from typing import Final, Literal, get_args

from theforge.context.verify import DriftReport
from theforge.contracts.canonical import utc_now
from theforge.contracts.telemetry import (
    SPAN_NAME_MAX,
    ProfileSnapshot,
    RunTelemetry,
    Span,
)
from theforge.contracts.types import Metric, RevalidationStrategy, Tier, VerificationLevel
from theforge.meta import PRODUCER
from theforge.profiles import ContextProfile

Phase = Literal["scan", "routing", "context", "provider"]

PHASES: Final[tuple[Phase, ...]] = get_args(Phase)
COUNTERS: Final[tuple[str, ...]] = (
    "files_scanned",
    "files_selected",
    "files_hashed",
    "bytes_hashed",
    "cache_hits",
    "cache_misses",
    "context_bytes",
    "providers_executed",
    "fallbacks_used",
    "negotiation_rounds",
    "semantic_planner_calls",
    "semantic_resolver_calls",
    "files_cited",
    "evidence_returned",
    "findings_returned",
    # Agentic surface economy (agentic prompt §34-35, §64): subagent/agent
    # invocations and the bytes of skill/knowledge context they consumed.
    "agent_calls",
    "subagent_calls",
    "skills_considered",
    "skills_loaded",
    "skill_bytes",
    "knowledge_bytes",
    "planning_calls",
    "verification_calls",
)
REVALIDATION_UNDECLARED_LIMITATION: Final = "provider-revalidation-undeclared"

_TIER_ORDER: Final[tuple[Tier, ...]] = get_args(Tier)
_METRICS: Final[tuple[str, ...]] = (*(f"{p}_ms" for p in PHASES), *COUNTERS)


def _ordered_tiers(tiers: Iterable[str]) -> list[str]:
    given = set(tiers)
    unknown = given.difference(_TIER_ORDER)
    if unknown:
        raise ValueError(f"unknown tier(s): {sorted(unknown)}")
    return [t for t in _TIER_ORDER if t in given]


class SpanHandle:
    """What ``TelemetryRecorder.span`` yields: the assigned id, the attribute bag
    the body fills on the way out (``outcome``, ``attempts``…) and the measured
    duration — ``phase`` accumulates it, so instrumenting a phase costs the same
    two clock reads it always did."""

    __slots__ = ("id", "attrs", "duration_ms")

    def __init__(self, span_id: str) -> None:
        self.id = span_id
        self.attrs: dict[str, str] = {}
        self.duration_ms = 0.0


class TelemetryRecorder:
    def __init__(
        self,
        run_id: str,
        profile: ContextProfile,
        *,
        correlation_id: str | None = None,
        parent_run: str | None = None,
        clock: Callable[[], float] = perf_counter,
        now: Callable[[], str] = utc_now,
    ) -> None:
        self._run_id = run_id
        self._profile = profile
        self._correlation_id = correlation_id
        self._parent_run = parent_run
        self._clock = clock
        self._now = now
        self._t0: float | None = None  # first instrumented instant, lazily (J3)
        self._phase_ms: dict[str, float] = {}
        self._counters: dict[str, int] = {}
        self._limitations: list[str] = []
        self._effective_tiers: list[str] = []
        self._revalidation: Literal["hash", "core", "none", "undeclared"] | None = None
        self._verification: VerificationLevel | None = None
        self._drift: list[str] = []
        self._span_lock = threading.Lock()  # plan workers share this recorder
        self._spans: list[Span] = []
        self._span_seq = 0

    @contextmanager
    def phase(
        self, name: Phase, *, span_name: str | None = None, parent: str | None = None, **attrs: str
    ) -> Iterator[None]:
        """Time the block (also when it raises), add it to the phase total and
        record it as a trace span — ``span_name`` overrides the displayed name
        (``provider:<id>``, ``negotiation``…) while the metric keeps its name."""
        if name not in PHASES:
            raise ValueError(f"unknown phase {name!r}")
        handle: SpanHandle | None = None
        try:
            with self.span(span_name or name, parent=parent, **attrs) as handle:
                yield
        finally:
            if handle is not None:  # the span measured it; accumulate unrounded
                self._phase_ms[name] = self._phase_ms.get(name, 0.0) + handle.duration_ms

    @contextmanager
    def span(self, name: str, *, parent: str | None = None, **attrs: str) -> Iterator[SpanHandle]:
        """Record one trace span around the block; the handle's ``attrs`` is the
        late-bound attribute bag. A raising block leaves a ``status="error"``
        span behind — the trace records that it happened and that it failed."""
        if not 0 < len(name) <= SPAN_NAME_MAX:
            raise ValueError(f"span name must be 1..{SPAN_NAME_MAX} chars: {name!r}")
        with self._span_lock:
            self._span_seq += 1
            span_id = f"s{self._span_seq}"
            start = self._clock()
            if self._t0 is None:
                self._t0 = start
        t0 = self._t0
        handle = SpanHandle(span_id)
        status: Literal["ok", "error"] = "ok"
        try:
            yield handle
        except BaseException:
            status = "error"
            raise
        finally:
            handle.duration_ms = (self._clock() - start) * 1000.0
            attributes = {**{k: str(v) for k, v in attrs.items()}, **handle.attrs}
            with self._span_lock:
                self._spans.append(
                    Span(
                        id=span_id,
                        name=name,
                        start_ms=round((start - t0) * 1000.0, 3),
                        duration_ms=round(handle.duration_ms, 3),
                        parent=parent,
                        status=status,
                        attributes=attributes,
                    )
                )

    def count(self, name: str, value: int) -> None:
        """Add ``value`` to the counter ``name`` (a counter field of RunTelemetry)."""
        if name not in COUNTERS:
            raise ValueError(f"unknown counter {name!r}")
        if value < 0:
            raise ValueError(f"counter {name!r} cannot be negative: {value}")
        self._counters[name] = self._counters.get(name, 0) + value

    def counter(self, name: str) -> int:
        """Current value of counter ``name`` (``0`` when never counted)."""
        if name not in COUNTERS:
            raise ValueError(f"unknown counter {name!r}")
        return self._counters.get(name, 0)

    def elapsed_ms(self, phase: Phase) -> float | None:
        """Accumulated milliseconds of ``phase``; None when it never ran."""
        if phase not in PHASES:
            raise ValueError(f"unknown phase {phase!r}")
        return self._phase_ms.get(phase)

    def note(self, limitation: str) -> None:
        if limitation not in self._limitations:
            self._limitations.append(limitation)

    def set_effective_tiers(self, tiers: Iterable[str]) -> None:
        self._effective_tiers = _ordered_tiers(tiers)

    def set_revalidation(self, strategy: RevalidationStrategy | None) -> None:
        """Record the manifest's strategy; ``None`` → ``undeclared`` plus a limitation."""
        if strategy is None:
            self._revalidation = "undeclared"
            self.note(REVALIDATION_UNDECLARED_LIMITATION)
        else:
            self._revalidation = strategy

    @property
    def correlation_id(self) -> str | None:
        """The correlation id this run records (None when unfederated)."""
        return self._correlation_id

    def set_profile(self, profile: ContextProfile) -> None:
        """Replace the assumed profile when ``auto`` resolves (the snapshot is taken at
        ``build``, so a run that ends before the assessment records the assumed one)."""
        self._profile = profile

    def set_drift(self, report: DriftReport) -> None:
        self._verification = report.level
        self._drift = list(report.drifted)
        for limitation in report.limitations:
            self.note(limitation)

    def _metric(self, name: str) -> Metric:
        if name.endswith("_ms"):
            ms = self._phase_ms.get(name.removesuffix("_ms"))
            return Metric() if ms is None else Metric(value=round(ms, 3), kind="measured")
        count = self._counters.get(name)
        return Metric() if count is None else Metric(value=float(count), kind="measured")

    def build(self) -> RunTelemetry:
        p = self._profile
        snapshot = ProfileSnapshot(
            name=p.name,
            budget_bytes=p.budget_bytes,
            max_files=p.max_files,
            tiers=_ordered_tiers(p.tiers),
            effective_tiers=list(self._effective_tiers),
            negotiation_rounds=p.negotiation_rounds,
            max_providers=p.max_providers,
            fallback=p.fallback,
            verification=p.verification,
            execute_timeout_s=p.execute_timeout_s,
        )
        metrics = {name: self._metric(name) for name in _METRICS}
        return RunTelemetry(
            producer=PRODUCER,
            created_at=self._now(),
            run_id=self._run_id,
            profile=snapshot,
            scan_ms=metrics["scan_ms"],
            routing_ms=metrics["routing_ms"],
            context_ms=metrics["context_ms"],
            provider_ms=metrics["provider_ms"],
            files_scanned=metrics["files_scanned"],
            files_selected=metrics["files_selected"],
            files_hashed=metrics["files_hashed"],
            bytes_hashed=metrics["bytes_hashed"],
            cache_hits=metrics["cache_hits"],
            cache_misses=metrics["cache_misses"],
            context_bytes=metrics["context_bytes"],
            providers_executed=metrics["providers_executed"],
            fallbacks_used=metrics["fallbacks_used"],
            negotiation_rounds=metrics["negotiation_rounds"],
            semantic_planner_calls=metrics["semantic_planner_calls"],
            semantic_resolver_calls=metrics["semantic_resolver_calls"],
            files_cited=metrics["files_cited"],
            evidence_returned=metrics["evidence_returned"],
            findings_returned=metrics["findings_returned"],
            agent_calls=metrics["agent_calls"],
            subagent_calls=metrics["subagent_calls"],
            skills_considered=metrics["skills_considered"],
            skills_loaded=metrics["skills_loaded"],
            skill_bytes=metrics["skill_bytes"],
            knowledge_bytes=metrics["knowledge_bytes"],
            planning_calls=metrics["planning_calls"],
            verification_calls=metrics["verification_calls"],
            provider_revalidation=self._revalidation,
            verification_performed=self._verification,
            context_drift=list(self._drift),
            # Start order: ids are assigned at start, so id order is the trace order;
            # start_ms breaks no ties (it can only be equal for concurrent spans).
            spans=sorted(self._spans, key=lambda s: int(s.id[1:])),
            correlation_id=self._correlation_id,
            parent_run=self._parent_run,
            limitations=list(self._limitations),
            unknowns=sorted(name for name, m in metrics.items() if m.kind == "unknown"),
        )
