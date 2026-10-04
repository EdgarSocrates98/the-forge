"""ExecutionResult, Finding and Evidence returned by providers."""

from dataclasses import dataclass, field
from typing import Literal

from theforge.contracts.base import ContractError
from theforge.contracts.types import (
    SHA256_RE,
    Epistemic,
    Metric,
    Producer,
    Severity,
    check_sha256,
)

__all__ = ["RESULT_SCHEMA", "Artifact", "Evidence", "ExecutionResult", "Finding", "Location",
           "Metric", "Metrics"]

RESULT_SCHEMA = "theforge/ExecutionResult/v1"


@dataclass(frozen=True, kw_only=True)
class Location:
    path: str
    line: int | None = None


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

    def __post_init__(self) -> None:
        if self.schema != RESULT_SCHEMA:
            raise ContractError(f"unsupported schema {self.schema!r}, expected {RESULT_SCHEMA!r}")
