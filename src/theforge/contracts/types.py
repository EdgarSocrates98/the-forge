"""Shared literal types and small value objects for all contracts."""

import re
from dataclasses import dataclass
from typing import Final, Literal

from theforge.contracts.base import ContractError

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

SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")


def check_sha256(value: str, *, field: str) -> None:
    """Reject anything that is not a lowercase hex SHA-256 digest."""
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise ContractError(f"{field}: invalid sha256 {value!r}, expected 64 lowercase hex chars")


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
