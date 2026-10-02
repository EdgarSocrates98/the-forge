"""Shared literal types and small value objects for all contracts."""

from dataclasses import dataclass
from typing import Literal

TrustLevel = Literal["builtin", "trusted", "local", "unverified", "blocked"]
CapabilityState = Literal["supported", "heuristic", "unresolved", "unsupported"]
OperationClass = Literal[
    "read_only", "local_mutation", "external_read", "external_mutation", "destructive"
]
BudgetProfile = Literal["economy", "balanced", "max"]
Epistemic = Literal["confirmed", "observed", "inferred", "proposed", "unresolved"]
MetricKind = Literal["measured", "estimated", "unknown"]
ResponseStatus = Literal["ok", "partial", "refused", "error"]
Outcome = Literal["ok", "partial", "refused", "provider_failure", "ambiguous", "no_route"]
Severity = Literal["info", "low", "medium", "high", "critical"]
HealthStatus = Literal["ok", "degraded", "unavailable"]

TRUST_RANK: dict[str, int] = {
    "builtin": 0, "trusted": 1, "local": 2, "unverified": 3, "blocked": 4,
}


@dataclass(frozen=True, kw_only=True)
class Producer:
    id: str
    version: str


@dataclass(frozen=True, kw_only=True)
class ErrorInfo:
    code: str
    detail: str
    field: str | None = None
    unlock: str | None = None
