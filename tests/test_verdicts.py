"""contracts.verdicts — the closed taxonomy and its acceptance rules."""

from __future__ import annotations

import pytest

from theforge.contracts.verdicts import (
    ACCEPTANCE,
    Acceptance,
    Verdict,
    acceptance,
    is_blocking,
    is_success,
)


def test_taxonomy_is_closed_and_fully_mapped() -> None:
    assert {v.value for v in Verdict} == {
        "PASS",
        "FAIL",
        "BLOCKED",
        "SKIPPED",
        "NOT_APPLICABLE",
        "UNVERIFIED",
        "ERROR",
    }
    assert set(ACCEPTANCE) == set(Verdict)  # no verdict lacks a rule


def test_parse_is_case_and_separator_insensitive() -> None:
    assert Verdict.parse("pass") is Verdict.PASS
    assert Verdict.parse("Fail") is Verdict.FAIL
    assert Verdict.parse("not_applicable") is Verdict.NOT_APPLICABLE
    assert Verdict.parse("not-applicable") is Verdict.NOT_APPLICABLE
    assert Verdict.parse(Verdict.UNVERIFIED) is Verdict.UNVERIFIED


def test_parse_rejects_off_taxonomy_values() -> None:
    for bad in ("maybe", "", "PASSED", None, 0):
        with pytest.raises(ValueError):
            Verdict.parse(bad)


def test_acceptance_rules_partition_the_set() -> None:
    assert acceptance(Verdict.PASS) is Acceptance.SUCCESS
    assert is_success(Verdict.PASS) and is_success("pass")
    for v in (Verdict.FAIL, Verdict.ERROR):
        assert acceptance(v) is Acceptance.BLOCKING
        assert is_blocking(v)
    for v in (Verdict.BLOCKED, Verdict.SKIPPED, Verdict.NOT_APPLICABLE, Verdict.UNVERIFIED):
        assert acceptance(v) is Acceptance.UNVERIFIED
        assert not is_success(v)
        assert not is_blocking(v)
