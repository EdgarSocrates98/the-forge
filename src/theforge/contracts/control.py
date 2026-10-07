"""Global stop and information-gain contracts (Cycle 4.1).

These artifacts are core-produced, deterministic and intentionally qualitative.
They never encode invented probabilities.
"""

from dataclasses import dataclass, field
from typing import Literal

from theforge.contracts.base import ContractError
from theforge.contracts.types import Producer

GLOBAL_STOP_SCHEMA = "theforge/GlobalStopDecision/v1"

InformationGain = Literal["high", "medium", "low", "none", "unknown"]
StopAction = Literal[
    "continue",
    "stop_sufficient_evidence",
    "stop_budget_exhausted",
    "stop_policy",
    "stop_no_expected_gain",
    "stop_repeated_failure",
    "stop_user_constraint",
    "unresolved",
]


@dataclass(frozen=True, kw_only=True)
class GlobalStopDecision:
    """Cross-provider continuation decision owned by The Forge."""

    schema: str = GLOBAL_STOP_SCHEMA
    producer: Producer
    created_at: str
    run_id: str
    action: StopAction
    information_gain: InformationGain
    reasons: list[str] = field(metadata={"min_items": 1})
    unresolved: list[str] = field(default_factory=list)
    budget_remaining: float | None = None
    verification_required: bool = False
    verification_satisfied: bool = False

    def __post_init__(self) -> None:
        if self.schema != GLOBAL_STOP_SCHEMA:
            raise ContractError(
                f"unsupported schema {self.schema!r}, expected {GLOBAL_STOP_SCHEMA!r}"
            )
        if not self.run_id:
            raise ContractError("global stop: run_id must not be empty")
        if not self.reasons:
            raise ContractError("global stop: reasons must not be empty")
        if self.budget_remaining is not None and self.budget_remaining < 0:
            raise ContractError("global stop: budget_remaining cannot be negative")
        if (
            self.action == "stop_no_expected_gain"
            and self.information_gain != "none"
        ):
            raise ContractError(
                "global stop: stop_no_expected_gain requires information_gain='none'"
            )
        if self.action == "stop_sufficient_evidence" and self.unresolved:
            raise ContractError(
                "global stop: sufficient-evidence stop cannot retain unresolved items"
            )
        if (
            self.verification_required
            and not self.verification_satisfied
            and self.action in ("stop_sufficient_evidence", "stop_no_expected_gain")
        ):
            raise ContractError(
                "global stop: mandatory verification prevents evidence/gain stop"
            )
