"""RiskAssessment: persisted record of a run's declared risk and the policy decision."""

from dataclasses import dataclass, field
from typing import Final, Literal

from theforge.contracts.base import ContractError
from theforge.contracts.types import OperationClass, Producer

RISK_SCHEMA: Final = "theforge/RiskAssessment/v1"
OPERATION_CLASS_LIMITATION: Final = (
    "operation_class is a provider declaration, not sandbox enforcement"
)

RiskLevel = Literal["yes", "no", "unknown"]
Decision = Literal["allow", "ask", "deny"]


@dataclass(frozen=True, kw_only=True)
class RiskDimensions:
    read_only: RiskLevel
    local_mutation: RiskLevel
    external_read: RiskLevel
    external_mutation: RiskLevel
    destructive: RiskLevel
    credentials: RiskLevel
    cross_account: RiskLevel


@dataclass(frozen=True, kw_only=True)
class PolicyDecision:
    decision: Decision
    rule: str
    reason: str
    approved: bool
    unlock: str | None = None


@dataclass(frozen=True, kw_only=True)
class RiskAssessment:
    schema: Literal["theforge/RiskAssessment/v1"] = RISK_SCHEMA
    producer: Producer
    created_at: str
    run_id: str
    provider_id: str
    capability: str
    action: str
    operation_class: OperationClass
    source: Literal["provider_declaration"]
    dimensions: RiskDimensions
    policy: PolicyDecision
    limitations: list[str]
    unknowns: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != RISK_SCHEMA:
            raise ContractError(f"unsupported schema {self.schema!r}, expected {RISK_SCHEMA!r}")
        if self.source != "provider_declaration":
            raise ContractError(f"unsupported risk source {self.source!r}")
        if OPERATION_CLASS_LIMITATION not in self.limitations:
            raise ContractError(f"limitations must contain {OPERATION_CLASS_LIMITATION!r}")
