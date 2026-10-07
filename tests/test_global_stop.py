"""Cycle 4.1 global stop / information-gain invariants."""

import pytest
from hypothesis import given, strategies as st

from theforge.contracts import ContractError, GlobalStopDecision, from_dict, to_dict
from theforge.control import StopSignals, decide_global_stop, expected_information_gain
from theforge.meta import PRODUCER


def test_information_gain_never_invents_probability() -> None:
    assert expected_information_gain(StopSignals(candidate_unique_evidence=True)) == "low"
    assert expected_information_gain(
        StopSignals(other_unresolved=["x"], candidate_unique_evidence=True)
    ) == "medium"
    assert expected_information_gain(
        StopSignals(critical_unresolved=["x"], candidate_unique_evidence=True)
    ) == "high"
    assert expected_information_gain(
        StopSignals(other_unresolved=["x"], candidate_unique_evidence=False)
    ) == "none"
    assert expected_information_gain(StopSignals()) == "unknown"


def test_mandatory_verification_dominates_no_gain() -> None:
    decision = decide_global_stop(
        "r1",
        StopSignals(
            other_unresolved=["nice-to-have"],
            candidate_unique_evidence=False,
            verification_required=True,
            verification_satisfied=False,
        ),
    )
    assert decision.action == "continue"
    assert decision.information_gain == "none"
    assert "mandatory verification" in decision.reasons[0]


def test_candidate_required_for_verification_is_high_gain() -> None:
    decision = decide_global_stop(
        "r1",
        StopSignals(
            candidate_required_for_verification=True,
            verification_required=True,
            verification_satisfied=False,
        ),
    )
    assert decision.action == "continue"
    assert decision.information_gain == "high"


def test_policy_and_budget_stop_are_global_authority() -> None:
    assert decide_global_stop(
        "r1", StopSignals(policy_blocked=True, critical_unresolved=["x"])
    ).action == "stop_policy"
    assert decide_global_stop(
        "r1", StopSignals(budget_exhausted=True, critical_unresolved=["x"])
    ).action == "stop_budget_exhausted"


def test_no_unknowns_stops_as_sufficient_evidence() -> None:
    decision = decide_global_stop("r1", StopSignals(verification_satisfied=True))
    assert decision.action == "stop_sufficient_evidence"
    assert decision.unresolved == []


def test_no_unique_evidence_stops_when_verification_is_satisfied() -> None:
    decision = decide_global_stop(
        "r1",
        StopSignals(
            other_unresolved=["non-critical follow-up"],
            candidate_unique_evidence=False,
            verification_required=True,
            verification_satisfied=True,
        ),
    )
    assert decision.action == "stop_no_expected_gain"


def test_repeated_failure_is_bounded_and_auditable() -> None:
    before = decide_global_stop(
        "r1", StopSignals(other_unresolved=["x"], repeated_failures=1, repeated_failure_limit=2)
    )
    after = decide_global_stop(
        "r1", StopSignals(other_unresolved=["x"], repeated_failures=2, repeated_failure_limit=2)
    )
    assert before.action == "continue"
    assert after.action == "stop_repeated_failure"


def test_contract_rejects_unsafe_sufficient_stop() -> None:
    with pytest.raises(ContractError, match="unresolved"):
        GlobalStopDecision(
            producer=PRODUCER,
            created_at="t",
            run_id="r",
            action="stop_sufficient_evidence",
            information_gain="none",
            unresolved=["still unknown"],
        )


def test_contract_rejects_gain_stop_before_mandatory_verification() -> None:
    with pytest.raises(ContractError, match="mandatory verification"):
        GlobalStopDecision(
            producer=PRODUCER,
            created_at="t",
            run_id="r",
            action="stop_no_expected_gain",
            information_gain="none",
            verification_required=True,
            verification_satisfied=False,
        )


def test_roundtrip_is_strict() -> None:
    decision = decide_global_stop("r1", StopSignals(other_unresolved=["x"]))
    assert from_dict(GlobalStopDecision, to_dict(decision), strict=True) == decision


@given(
    unresolved=st.lists(st.text(min_size=1, max_size=30), min_size=1, max_size=8),
)
def test_property_mandatory_verification_never_stops_for_low_gain(
    unresolved: list[str],
) -> None:
    decision = decide_global_stop(
        "property-run",
        StopSignals(
            other_unresolved=unresolved,
            candidate_unique_evidence=False,
            verification_required=True,
            verification_satisfied=False,
        ),
    )
    assert decision.action == "continue"


@given(
    remaining=st.floats(min_value=0, max_value=1_000_000, allow_nan=False, allow_infinity=False),
    failures=st.integers(min_value=0, max_value=20),
)
def test_property_budget_exhaustion_is_global_ceiling(
    remaining: float, failures: int
) -> None:
    decision = decide_global_stop(
        "property-run",
        StopSignals(
            critical_unresolved=["critical"],
            candidate_unique_evidence=True,
            budget_exhausted=True,
            budget_remaining=remaining,
            repeated_failures=failures,
            verification_required=True,
            verification_satisfied=False,
        ),
    )
    assert decision.action == "stop_budget_exhausted"
