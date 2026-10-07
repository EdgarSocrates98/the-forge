"""Deterministic global stop / information-gain evaluation (Cycle 4.1)."""

from dataclasses import dataclass, field

from theforge.contracts.canonical import utc_now
from theforge.contracts.control import GlobalStopDecision, InformationGain
from theforge.meta import PRODUCER


@dataclass(frozen=True, kw_only=True)
class StopSignals:
    """Observable inputs to a global continuation decision."""

    critical_unresolved: list[str] = field(default_factory=list)
    other_unresolved: list[str] = field(default_factory=list)
    candidate_unique_evidence: bool | None = None
    candidate_required_for_verification: bool = False
    verification_required: bool = False
    verification_satisfied: bool = False
    budget_exhausted: bool = False
    budget_remaining: int | None = None
    policy_blocked: bool = False
    user_stop: bool = False
    repeated_failures: int = 0
    repeated_failure_limit: int = 2

    def __post_init__(self) -> None:
        if self.repeated_failures < 0:
            raise ValueError("stop signals: repeated_failures cannot be negative")
        if self.repeated_failure_limit <= 0:
            raise ValueError("stop signals: repeated_failure_limit must be positive")
        if self.budget_remaining is not None and self.budget_remaining < 0:
            raise ValueError("stop signals: budget_remaining cannot be negative")


def expected_information_gain(signals: StopSignals) -> InformationGain:
    """Classify expected incremental value without invented probabilities."""
    if signals.candidate_required_for_verification:
        return "high"
    if signals.critical_unresolved:
        return "high" if signals.candidate_unique_evidence is not False else "unknown"
    if signals.candidate_unique_evidence is True:
        return "medium" if signals.other_unresolved else "low"
    if signals.candidate_unique_evidence is False:
        return "none" if not signals.critical_unresolved else "unknown"
    return "unknown"


def decide_global_stop(run_id: str, signals: StopSignals) -> GlobalStopDecision:
    """Apply global precedence: safety and verification dominate economy."""
    gain = expected_information_gain(signals)
    unresolved = [*signals.critical_unresolved, *signals.other_unresolved]

    if signals.policy_blocked:
        action = "stop_policy"
        reasons = ["global policy blocks the next execution"]
    elif signals.user_stop:
        action = "stop_user_constraint"
        reasons = ["user constraint requested stop"]
    elif signals.budget_exhausted:
        action = "stop_budget_exhausted"
        reasons = ["global execution budget is exhausted"]
    elif signals.verification_required and not signals.verification_satisfied:
        action = "continue"
        reasons = ["mandatory verification remains unsatisfied"]
    elif signals.candidate_required_for_verification:
        action = "continue"
        reasons = ["candidate is required for independent verification"]
    elif signals.repeated_failures >= max(1, signals.repeated_failure_limit):
        action = "stop_repeated_failure"
        reasons = ["repeated provider failures reached the configured limit"]
    elif not unresolved:
        action = "stop_sufficient_evidence"
        reasons = ["no unresolved engineering questions remain"]
    elif gain == "none":
        action = "stop_no_expected_gain"
        reasons = ["candidate contributes no unique evidence to remaining questions"]
    else:
        action = "continue"
        reasons = [f"expected information gain is {gain}"]

    return GlobalStopDecision(
        producer=PRODUCER,
        created_at=utc_now(),
        run_id=run_id,
        action=action,
        information_gain=gain,
        reasons=reasons,
        unresolved=unresolved,
        budget_remaining=signals.budget_remaining,
        verification_required=signals.verification_required,
        verification_satisfied=signals.verification_satisfied,
    )
