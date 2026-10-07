"""ExecutionResult, Finding and Evidence returned by providers."""

from dataclasses import dataclass, field
from typing import Literal

from theforge.contracts.base import ContractError
from theforge.contracts.context import LineRange
from theforge.contracts.economy import ProviderEconomyReceipt
from theforge.contracts.telemetry import NativeTrace
from theforge.contracts.types import (
    REF_RE,
    SHA256_RE,
    Epistemic,
    Metric,
    Producer,
    Severity,
    check_ref,
    check_sha256,
)

__all__ = ["RESULT_SCHEMA", "Artifact", "ContextRequest", "ContextRequestItem", "Evidence",
           "EvidenceSource", "ExecutionResult", "Finding", "Location", "Metric", "Metrics",
           "NativeTrace", "ProviderEconomyReceipt", "ProviderReceipt"]

RESULT_SCHEMA = "theforge/ExecutionResult/v1"


@dataclass(frozen=True, kw_only=True)
class ProviderReceipt:
    """A pointer to the provider's own run record — never its contents.

    ``ref`` is the native receipt identity verbatim (e.g. an API Forge
    ``case:<id>``); ``sha256`` is the hash of the native receipt document the
    provider wrote, so the pointer can be resolved and checked against the
    run's artifacts. Providers without a native receipt emit nothing.
    """

    ref: str = field(metadata={"pattern": REF_RE.pattern})
    sha256: str = field(metadata={"pattern": SHA256_RE.pattern})

    def __post_init__(self) -> None:
        if not self.ref:
            raise ContractError("provider_receipt.ref must not be empty")
        check_ref(self.ref, field="provider_receipt.ref")
        check_sha256(self.sha256, field="sha256")


@dataclass(frozen=True, kw_only=True)
class Location:
    path: str
    line: int | None = None


@dataclass(frozen=True, kw_only=True)
class EvidenceSource:
    """Upstream provenance of a derived evidence: the handoff item it builds on.

    A provider that consumed a handoff may mark the evidence it carries forward
    with the source node's identity — never stronger than the item it cites
    (``handoff-provenance`` verification check).
    """

    provider: str  # id of the provider that produced the item
    run_id: str    # the provider run the item came from
    item: str      # handoff item id
    node: str | None = None      # plan node of the item (plan context)
    plan_run: str | None = None  # plan run the handoff belonged to


@dataclass(frozen=True, kw_only=True)
class Evidence:
    id: str
    epistemic: Epistemic
    subject: str
    claim: str
    producer: Producer
    location: Location | None = None
    hash: str | None = field(default=None, metadata={"pattern": SHA256_RE.pattern})
    limitations: list[str] = field(default_factory=list)
    derived_from: EvidenceSource | None = None

    def __post_init__(self) -> None:
        if self.hash is not None:
            check_sha256(self.hash, field="hash")


@dataclass(frozen=True, kw_only=True)
class Finding:
    id: str
    title: str
    severity: Severity = "info"
    evidence_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class Artifact:
    path: str
    sha256: str = field(metadata={"pattern": SHA256_RE.pattern})

    def __post_init__(self) -> None:
        check_sha256(self.sha256, field="sha256")


@dataclass(frozen=True, kw_only=True)
class Metrics:
    duration_ms: Metric = field(default_factory=Metric)
    context_bytes: Metric = field(default_factory=Metric)
    tokens: Metric = field(default_factory=Metric)


@dataclass(frozen=True, kw_only=True)
class ContextRequestItem:
    path: str
    lines: LineRange | None = None  # 1-based inclusive; None = whole file
    reason: str = ""


@dataclass(frozen=True, kw_only=True)
class ContextRequest:
    # No item limit here: the limit is relational (validate_context_request), so it can
    # carry its own code; per-item path checks belong to the broker.
    items: list[ContextRequestItem]


@dataclass(frozen=True, kw_only=True)
class ExecutionResult:
    schema: str = RESULT_SCHEMA
    producer: Producer
    created_at: str
    status: Literal["ok", "partial"]
    findings: list[Finding] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    artifacts: list[Artifact] = field(default_factory=list)
    metrics: Metrics = field(default_factory=Metrics)
    limitations: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    # Declared assumptions the result relies on (evidence bus: handed off as
    # ``assumption`` items); additive — providers that declare none emit [].
    assumptions: list[str] = field(default_factory=list)
    # Optional negotiation request: a response carrying it is never persisted as `result`.
    context_request: ContextRequest | None = None
    # Provider-native run receipt (ref + hash, never the content); nested-receipt
    # drill-down — the run receipt copies it as is.
    provider_receipt: ProviderReceipt | None = None
    # The provider's internal economy for this execution, summarized
    # (ProviderEconomyReceipt/v1); a plan run aggregates them into the
    # EconomyRollup. None when the provider does not report economy.
    provider_economy: ProviderEconomyReceipt | None = None
    # Bounded pointer to the provider's internal trace (ref + summary, never the
    # spans); the run's node span links to it via ``native_trace_ref``.
    native_trace: NativeTrace | None = None

    def __post_init__(self) -> None:
        if self.schema != RESULT_SCHEMA:
            raise ContractError(f"unsupported schema {self.schema!r}, expected {RESULT_SCHEMA!r}")
