"""Handoff: structured items a plan node receives from the nodes it depends on.

A handoff never carries file content nor the provider's full output: only evidence,
findings, artifact references (path + hash) and the source node's decision, each with
its origin and original epistemic status. Item and byte limits are relational
(``validate_handoff``); the ``claim`` cap is local.
"""

from dataclasses import dataclass, field
from typing import Literal

from theforge.contracts.base import ContractError
from theforge.contracts.result import Location
from theforge.contracts.types import (
    MAX_CLAIM_CHARS,
    SHA256_RE,
    Epistemic,
    Producer,
    Severity,
    check_sha256,
)

HANDOFF_SCHEMA = "theforge/Handoff/v1"
HandoffKind = Literal["evidence", "finding", "artifact", "decision"]


@dataclass(frozen=True, kw_only=True)
class HandoffOrigin:
    plan_run: str
    node: str
    run_id: str
    provider: Producer  # id and version of the source provider


@dataclass(frozen=True, kw_only=True)
class HandoffItem:
    kind: HandoffKind
    id: str  # original evidence/finding id, artifact path, or "outcome" for a decision
    origin: HandoffOrigin
    epistemic: Epistemic | None = None  # evidence: original; decision: observed
    subject: str = ""
    claim: str = ""
    location: Location | None = None
    hash: str | None = field(default=None, metadata={"pattern": SHA256_RE.pattern})
    severity: Severity | None = None  # finding
    evidence_ids: list[str] = field(default_factory=list)  # finding

    def __post_init__(self) -> None:
        if len(self.claim) > MAX_CLAIM_CHARS:
            raise ContractError(f"handoff item {self.id!r}: claim longer than "
                                f"{MAX_CLAIM_CHARS} chars ({len(self.claim)})")
        if self.kind == "evidence" and self.epistemic is None:
            raise ContractError(f"handoff evidence {self.id!r}: epistemic is required")
        if self.kind in ("finding", "artifact") and self.epistemic is not None:
            raise ContractError(f"handoff {self.kind} {self.id!r}: epistemic must be absent")
        if self.kind == "artifact" and self.hash is None:
            raise ContractError(f"handoff artifact {self.id!r}: hash is required")
        if self.hash is not None:
            check_sha256(self.hash, field="hash")


@dataclass(frozen=True, kw_only=True)
class Handoff:
    schema: str = HANDOFF_SCHEMA
    producer: Producer  # theforge
    created_at: str
    plan_run: str
    target_node: str
    items: list[HandoffItem] = field(default_factory=list)
    truncated: bool = False
    dropped: int = 0
    limitations: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != HANDOFF_SCHEMA:
            raise ContractError(f"unsupported schema {self.schema!r}, expected {HANDOFF_SCHEMA!r}")
        if self.dropped < 0 or (self.dropped > 0 and not self.truncated):
            raise ContractError(f"handoff dropped={self.dropped} requires truncated and >= 0")
