"""DecisionMemory: the reusable decisions of past runs (Cycle 3 Wave I).

Not everything a run decided — only the decisions worth reusing: which provider
was routed a capability, which profile a task shape resolved to, which pattern a
plan took, which verdict a debate reached. One document at
``.forge/intel/decisions.json``, deduplicated by ``id`` (the sha256 of
kind|subject|choice): a repeated decision reaffirms the entry — new run id,
bumped ``corroborations`` — instead of duplicating it.

Each entry keeps its ``basis``: the recorded reason is evidence, not opinion.
The memory informs; it never routes by itself.
"""

from dataclasses import dataclass, field
from typing import Literal

from theforge.contracts.base import ContractError
from theforge.contracts.types import Producer

DECISIONS_SCHEMA = "theforge/DecisionMemory/v1"
DecisionKind = Literal["routing", "profile", "pattern", "verdict"]

MAX_DECISIONS = 256  # bounded memory: oldest ``updated_at`` dropped first
MAX_RUN_TRAIL = 16  # bounded audit trail per decision


@dataclass(frozen=True, kw_only=True)
class RememberedDecision:
    """One reusable decision and the runs that corroborated it."""

    id: str  # sha256 over kind|subject|choice — the dedup identity
    kind: DecisionKind
    subject: str  # what the decision was about (capability id, "plan-pattern"…)
    choice: str  # what was chosen
    basis: str  # the recorded reason — evidence, not opinion
    created_at: str  # first made
    updated_at: str  # last reaffirmed
    corroborations: int = 1  # total times this exact decision recurred
    runs: list[str] = field(default_factory=list)  # run ids, oldest dropped

    def __post_init__(self) -> None:
        if self.corroborations < 1:
            raise ContractError(f"decision {self.id!r}: corroborations must be >= 1")
        if len(self.runs) > MAX_RUN_TRAIL:
            raise ContractError(f"decision {self.id!r}: run trail exceeds {MAX_RUN_TRAIL}")
        for name in ("id", "subject", "choice", "basis", "created_at", "updated_at"):
            if not isinstance(getattr(self, name), str):
                raise ContractError(f"decision {name} must be a string")


@dataclass(frozen=True, kw_only=True)
class DecisionMemory:
    """The bounded, deduplicated store of reusable decisions."""

    schema: str = DECISIONS_SCHEMA
    producer: Producer
    created_at: str
    entries: list[RememberedDecision] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != DECISIONS_SCHEMA:
            raise ContractError(
                f"unsupported schema {self.schema!r}, expected {DECISIONS_SCHEMA!r}"
            )
        ids = [e.id for e in self.entries]
        if len(ids) != len(set(ids)):
            raise ContractError("decision-memory: duplicate decision id")
        if len(self.entries) > MAX_DECISIONS:
            raise ContractError(
                f"decision-memory: {len(self.entries)} entries exceed {MAX_DECISIONS}"
            )
