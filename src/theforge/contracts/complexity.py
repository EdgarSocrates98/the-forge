"""ComplexityAssessment: the deterministic measurement behind ``--profile auto``.

One per run whose requested profile is ``auto``: the engine scores the declared
dimensions, maps the weighted score to a level (trivial < low < medium < high <
critical) and selects the effective budget profile. Dimensions without evidence
stay unmeasured (``score=None``) — they reduce ``confidence`` and are named in
``limitations``, never guessed. Prompt length is never an input.
"""

from dataclasses import dataclass, field
from typing import Literal

from theforge.contracts.base import ContractError
from theforge.contracts.types import BudgetProfile, Producer, ProfileRequest

COMPLEXITY_SCHEMA = "theforge/ComplexityAssessment/v1"
ComplexityLevel = Literal["trivial", "low", "medium", "high", "critical"]
LEVELS: tuple[ComplexityLevel, ...] = ("trivial", "low", "medium", "high", "critical")


@dataclass(frozen=True, kw_only=True)
class ComplexityDimension:
    name: str
    score: float | None  # 0..1; None = not measured (no evidence for this dimension)
    weight: float  # the configured weight actually applied (0 = disabled)
    value: str = ""  # the measured evidence ("3", "external_mutation", "unknown: ...")


@dataclass(frozen=True, kw_only=True)
class ComplexityAssessment:
    schema: str = COMPLEXITY_SCHEMA
    producer: Producer
    created_at: str
    task_id: str
    level: ComplexityLevel
    score: float  # weighted mean of the measured dimensions, 0..1
    confidence: float  # share of total weight backed by measurement, 0..1
    dimensions: list[ComplexityDimension] = field(default_factory=list)
    signals: list[str] = field(default_factory=list)  # "dimension=value" tokens
    requested_profile: ProfileRequest = "auto"  # what the task asked for
    selected_profile: BudgetProfile = "balanced"
    # Why selected_profile won: "level high -> max" or "confidence 0.31 < 0.5 -> fallback".
    profile_reason: str = ""
    config_source: str = "default"  # which complexity.toml layers fed the policy
    limitations: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != COMPLEXITY_SCHEMA:
            raise ContractError(
                f"unsupported schema {self.schema!r}, expected {COMPLEXITY_SCHEMA!r}"
            )
        if self.level not in LEVELS:
            raise ContractError(f"complexity level {self.level!r} is not one of {LEVELS}")
        for name, value in (("score", self.score), ("confidence", self.confidence)):
            if not 0.0 <= value <= 1.0:
                raise ContractError(f"complexity {name} {value} outside 0..1")
        if self.selected_profile not in ("economy", "balanced", "max"):
            raise ContractError(
                f"complexity selected_profile {self.selected_profile!r} is not a budget profile"
            )
        for dim in self.dimensions:
            if dim.score is not None and not 0.0 <= dim.score <= 1.0:
                raise ContractError(
                    f"complexity dimension {dim.name!r} score {dim.score} outside 0..1"
                )
            if dim.weight < 0:
                raise ContractError(
                    f"complexity dimension {dim.name!r} weight {dim.weight} is negative"
                )
