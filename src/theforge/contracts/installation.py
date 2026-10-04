"""InstallationPlan: what is missing to run a plan. Planning only: nothing is installed."""

from dataclasses import dataclass, field
from typing import Literal

from theforge.contracts.base import ContractError
from theforge.contracts.types import Producer

INSTALLATION_SCHEMA = "theforge/InstallationPlan/v1"


@dataclass(frozen=True, kw_only=True)
class InstallationItem:
    provider: str
    state: str  # registry state or "unavailable" (health)
    reason: str  # registry/provider detail (redacted)
    suggested_action: str  # ErrorInfo.unlock, else the detail itself
    source: Literal["registry", "health"]
    nodes: list[str] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class InstallationPlan:
    schema: str = INSTALLATION_SCHEMA
    producer: Producer
    created_at: str
    run_id: str
    planning_only: Literal[True] = True
    items: list[InstallationItem] = field(default_factory=list)  # at least one

    def __post_init__(self) -> None:
        if self.schema != INSTALLATION_SCHEMA:
            raise ContractError(
                f"unsupported schema {self.schema!r}, expected {INSTALLATION_SCHEMA!r}")
        if not self.items:
            raise ContractError("installation plan: items must not be empty")
