"""Profiles: the single table of economy/balanced/max parameters (8.3, 9.1-9.6)."""

import dataclasses
from typing import get_args

import pytest

from theforge.context import BUDGETS
from theforge.contracts.types import BudgetProfile
from theforge.forger.orchestrator import EXECUTE_TIMEOUTS
from theforge.profiles import MAX_NEGOTIATION_ROUNDS, PROFILES, ContextProfile, profile_for

ORDER: tuple[BudgetProfile, ...] = ("economy", "balanced", "max")


def test_table_covers_every_budget_profile_in_order() -> None:
    assert tuple(PROFILES) == ORDER
    assert set(PROFILES) == set(get_args(BudgetProfile))
    for name, profile in PROFILES.items():
        assert profile.name == name
        assert profile_for(name) is profile


def test_table_values_match_the_design() -> None:
    economy, balanced, maximum = (PROFILES[n] for n in ORDER)
    assert economy == ContextProfile(
        name="economy", budget_bytes=65_536, max_files=16,
        tiers=frozenset({"metadata", "reference"}), negotiation_rounds=0, max_providers=1,
        fallback=False, verification="minimal", execute_timeout_s=60.0)
    assert balanced == ContextProfile(
        name="balanced", budget_bytes=262_144, max_files=64,
        tiers=frozenset({"metadata", "reference", "excerpt", "requested"}),
        negotiation_rounds=1, max_providers=1, fallback=True, verification="conditional",
        execute_timeout_s=180.0)
    assert maximum == ContextProfile(
        name="max", budget_bytes=1_048_576, max_files=256,
        tiers=frozenset({"metadata", "reference", "excerpt", "requested"}),
        negotiation_rounds=2, max_providers=4, fallback=True, verification="strong",
        execute_timeout_s=600.0)


def test_budget_and_max_files_strictly_grow_from_economy_to_max() -> None:
    profiles = [PROFILES[n] for n in ORDER]
    for smaller, larger in zip(profiles, profiles[1:], strict=False):
        assert smaller.budget_bytes < larger.budget_bytes
        assert smaller.max_files < larger.max_files


def test_no_profile_exceeds_the_fixed_negotiation_cap() -> None:
    assert MAX_NEGOTIATION_ROUNDS == 2
    for profile in PROFILES.values():
        assert 0 <= profile.negotiation_rounds <= MAX_NEGOTIATION_ROUNDS


def test_only_max_allows_more_than_one_provider() -> None:
    assert {n for n, p in PROFILES.items() if p.max_providers > 1} == {"max"}
    for profile in PROFILES.values():
        assert profile.max_providers >= 1


def test_metadata_and_reference_tiers_in_every_profile() -> None:
    for profile in PROFILES.values():
        assert {"metadata", "reference"} <= profile.tiers


def test_profiles_are_immutable() -> None:
    profile = PROFILES["balanced"]
    with pytest.raises(dataclasses.FrozenInstanceError):
        profile.budget_bytes = 1  # type: ignore[misc]
    with pytest.raises(TypeError):
        PROFILES["economy"] = profile  # type: ignore[index]


def test_unknown_profile_is_rejected() -> None:
    with pytest.raises(KeyError):
        profile_for("bogus")  # type: ignore[arg-type]


def test_broker_budgets_are_derived_from_the_table() -> None:
    assert dict(BUDGETS) == {n: p.budget_bytes for n, p in PROFILES.items()}
    # Same public values the existing suite relies on.
    assert dict(BUDGETS) == {"economy": 64 * 1024, "balanced": 256 * 1024, "max": 1024 * 1024}


def test_execute_timeouts_are_derived_from_the_table() -> None:
    assert dict(EXECUTE_TIMEOUTS) == {n: p.execute_timeout_s for n, p in PROFILES.items()}
    assert dict(EXECUTE_TIMEOUTS) == {"economy": 60.0, "balanced": 180.0, "max": 600.0}
