"""Profiles: the single source of the economy/balanced/max parameters.

No other module defines budgets, timeouts or negotiation rounds; the Context Broker
budgets and the orchestrator's ``execute`` timeout are derived from this table.
Values are initial; changing them is a revalidation trigger for Wave D.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from theforge.contracts.types import BudgetProfile, ProfileRequest, Tier, VerificationLevel

MAX_NEGOTIATION_ROUNDS: Final = 2
# The profile a run assumes before a complexity assessment resolves ``auto`` —
# and the one it keeps when the assessment cannot run (no_route, early refusal).
DEFAULT_PROFILE: Final[BudgetProfile] = "balanced"


@dataclass(frozen=True, kw_only=True)
class ContextProfile:
    name: BudgetProfile
    budget_bytes: int
    max_files: int
    tiers: frozenset[Tier]
    negotiation_rounds: int
    max_providers: int
    fallback: bool
    verification: VerificationLevel
    execute_timeout_s: float


_BASE_TIERS: Final[frozenset[Tier]] = frozenset({"metadata", "reference"})
_ALL_TIERS: Final[frozenset[Tier]] = frozenset({"metadata", "reference", "excerpt", "requested"})

_TABLE: Final[dict[BudgetProfile, ContextProfile]] = {
    "economy": ContextProfile(
        name="economy",
        budget_bytes=64 * 1024,
        max_files=16,
        tiers=_BASE_TIERS,
        negotiation_rounds=0,
        max_providers=1,
        fallback=False,
        verification="minimal",
        execute_timeout_s=60.0,
    ),
    "balanced": ContextProfile(
        name="balanced",
        budget_bytes=256 * 1024,
        max_files=64,
        tiers=_ALL_TIERS,
        negotiation_rounds=1,
        max_providers=1,
        fallback=True,
        verification="conditional",
        execute_timeout_s=180.0,
    ),
    "max": ContextProfile(
        name="max",
        budget_bytes=1024 * 1024,
        max_files=256,
        tiers=_ALL_TIERS,
        negotiation_rounds=MAX_NEGOTIATION_ROUNDS,
        max_providers=4,
        fallback=True,
        verification="strong",
        execute_timeout_s=600.0,
    ),
}

PROFILES: Final[Mapping[BudgetProfile, ContextProfile]] = MappingProxyType(_TABLE)


def profile_for(name: BudgetProfile) -> ContextProfile:
    """The profile for ``name``; an unknown name raises ``KeyError``."""
    return PROFILES[name]


def assumed_profile(requested: ProfileRequest) -> ContextProfile:
    """The profile in force before an assessment resolves ``auto`` (the default)."""
    return profile_for(DEFAULT_PROFILE if requested == "auto" else requested)
