"""RunBudget: the effective budget a run operated under (Cycle 3 Wave H).

One per run that reaches routing: the resolved profile's bounds, plus any
bounded promotion the complexity evidence justified (``adjustments`` — each a
``<field> <old>→<new>`` note; empty means the profile's values verbatim). The
budget is persisted as the ``budget`` artifact and bound into the receipt via
``inputs.budget_sha256``, so what the run was allowed to spend is auditable.
"""

from dataclasses import dataclass, field

from theforge.contracts.base import ContractError
from theforge.contracts.types import Producer

BUDGET_SCHEMA = "theforge/RunBudget/v1"


@dataclass(frozen=True, kw_only=True)
class RunBudget:
    schema: str = BUDGET_SCHEMA
    producer: Producer
    created_at: str
    run_id: str
    profile: str  # the resolved named profile; promotions live in ``adjustments``
    context_bytes: int  # pack byte budget the broker enforced
    max_files: int  # pack file budget
    provider_calls: int  # execute calls the run may drive (profile.max_providers)
    semantic_calls: int  # tier-2 planner calls allowed (1 on non-economy, else 0)
    verification_calls: int  # verify-op calls allowed (1; a run verifies once)
    wall_time_s: float  # per-execute timeout (profile.execute_timeout_s)
    max_parallelism: int  # node-level concurrency bound (plan runs only)
    negotiation_rounds: int
    adjustments: list[str] = field(default_factory=list)  # bounded promotions applied

    def __post_init__(self) -> None:
        if self.schema != BUDGET_SCHEMA:
            raise ContractError(f"unsupported schema {self.schema!r}, expected {BUDGET_SCHEMA!r}")
        for name in (
            "context_bytes",
            "max_files",
            "provider_calls",
            "semantic_calls",
            "verification_calls",
            "max_parallelism",
            "negotiation_rounds",
        ):
            value = getattr(self, name)
            if value < 0:
                raise ContractError(f"budget {name} cannot be negative: {value}")
        if self.wall_time_s <= 0:
            raise ContractError(f"budget wall_time_s must be > 0: {self.wall_time_s}")
