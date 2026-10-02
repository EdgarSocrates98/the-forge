"""TaskSpec: the normalized request The Forger works on."""

from dataclasses import dataclass, field
from typing import Any, Literal

from theforge.contracts.base import ContractError
from theforge.contracts.types import BudgetProfile, Producer

TASK_SCHEMA = "theforge/TaskSpec/v1"


@dataclass(frozen=True, kw_only=True)
class TaskSpec:
    schema: str = TASK_SCHEMA
    producer: Producer
    created_at: str
    status: Literal["created"] = "created"
    id: str
    intent: str
    workspace_root: str
    targets: list[str] = field(default_factory=lambda: ["."])
    budget_profile: BudgetProfile = "balanced"
    requested_capability: str | None = None
    requested_action: str | None = None
    constraints: dict[str, Any] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != TASK_SCHEMA:
            raise ContractError(f"unsupported schema {self.schema!r}, expected {TASK_SCHEMA!r}")
        if not self.intent.strip():
            raise ContractError("task intent must not be empty")
