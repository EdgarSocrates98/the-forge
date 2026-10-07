"""ProviderPerformance: measured, observable provider statistics (Cycle 3 Wave H).

Aggregated per ``provider``+``capability`` under ``.forge/metrics/`` and updated
after every provider run. The data is *history* — a secondary factor and
tie-break only (H5): it never overrides trust, policy, capability compatibility
or routing evidence, and a missing or malformed entry simply yields no opinion.
Counts are validated on construction so a poisoned metrics file fails closed
(rejected, never partially trusted).
"""

from dataclasses import dataclass, field

from theforge.contracts.base import ContractError
from theforge.contracts.types import Producer

PERFORMANCE_SCHEMA = "theforge/ProviderPerformance/v1"


@dataclass(frozen=True, kw_only=True)
class ProviderCapabilityPerformance:
    """Measured statistics of one provider executing one capability.

    ``surface`` is the ``ProviderSurfaceIdentity.surface_fingerprint`` of the
    manifest the runs executed against: a provider that changes its surface
    starts a fresh history — old entries stay recorded (scoped, never silently
    reused) and only answer ``score`` for their own fingerprint. Entries
    written before surfaces existed carry ``None`` and never match a real
    fingerprint.
    """

    provider: str
    capability: str
    runs: int  # provider runs measured (execute attempted)
    surface: str | None = None
    ok: int
    partial: int
    failed: int  # provider_failure + refused + error envelope outcomes
    verified_runs: int  # runs whose ``forge`` check passed
    evidence: int  # total evidence items returned across runs
    artifacts: int  # total declared artifacts across runs
    context_bytes: int  # total pack bytes sent across runs
    files_sent: int  # total pack files sent across runs
    files_cited: int  # sent files that the returned evidence actually cited
    duration_ms: float  # total provider-phase time; the average is /runs
    updated_at: str

    def __post_init__(self) -> None:
        if (
            self.runs < 0
            or min(
                self.ok,
                self.partial,
                self.failed,
                self.verified_runs,
                self.evidence,
                self.artifacts,
                self.context_bytes,
                self.files_sent,
                self.files_cited,
            )
            < 0
            or self.duration_ms < 0
        ):
            raise ContractError(
                f"provider-performance {self.provider}/{self.capability}: negative counter"
            )
        if self.ok + self.partial + self.failed > self.runs:
            raise ContractError(
                f"provider-performance {self.provider}/"
                f"{self.capability}: outcome counts exceed runs"
            )
        if self.files_cited > self.files_sent:
            raise ContractError(
                f"provider-performance {self.provider}/"
                f"{self.capability}: files_cited exceeds files_sent"
            )
        if self.verified_runs > self.ok + self.partial:
            raise ContractError(
                f"provider-performance {self.provider}/"
                f"{self.capability}: verified runs exceed delivered ones"
            )


@dataclass(frozen=True, kw_only=True)
class ProviderPerformance:
    """The metrics store snapshot: one entry per provider+capability."""

    schema: str = PERFORMANCE_SCHEMA
    producer: Producer
    created_at: str
    entries: list[ProviderCapabilityPerformance] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != PERFORMANCE_SCHEMA:
            raise ContractError(
                f"unsupported schema {self.schema!r}, expected {PERFORMANCE_SCHEMA!r}"
            )
        keys = [(e.provider, e.capability, e.surface) for e in self.entries]
        if len(keys) != len(set(keys)):
            raise ContractError("provider-performance: duplicate provider/capability/surface")

    def score(
        self, provider: str, capability: str, surface: str | None = None
    ) -> tuple[float, float, float, int]:
        """Measured-history key — higher is better, for tie-break only (H5).

        Ordered (verified-run rate, delivered rate, negated mean latency, runs):
        verification first because an unverified ``ok`` is weaker evidence; run
        count last so a long mediocre history never beats a short clean one on
        volume. No entry (or no runs) yields the all-zero floor, so providers
        without history tie each other and lose to any clean one.

        ``surface`` scopes the lookup: only history recorded against that exact
        surface fingerprint counts — a changed surface never inherits it, and a
        ``None`` argument matches only legacy entries that recorded no surface.
        """
        entry = next(
            (
                e
                for e in self.entries
                if e.provider == provider and e.capability == capability and e.surface == surface
            ),
            None,
        )
        if entry is None or entry.runs <= 0:
            return (0.0, 0.0, 0.0, 0)
        return (
            entry.verified_runs / entry.runs,
            (entry.ok + entry.partial) / entry.runs,
            -entry.duration_ms / entry.runs,
            entry.runs,
        )
