"""Handoff: structured items a plan node receives from the nodes it depends on.

The evidence bus (Cycle 3 Wave D): a handoff never carries file content nor the
provider's full output — only typed knowledge objects (evidence, findings, artifact
references, the source node's decision, constraints, assumptions and its verification
status), each with its origin, provenance chain and original epistemic status. Items
are deduplicated by content (``also_from`` keeps every origin) and filtered by the
consumer's declared needs. Item and byte limits are relational (``validate_handoff``);
the ``claim`` cap is local.
"""

from dataclasses import dataclass, field
from typing import Literal

from theforge.contracts.base import ContractError
from theforge.contracts.result import EvidenceSource, Location
from theforge.contracts.types import (
    MAX_CLAIM_CHARS,
    SHA256_RE,
    Epistemic,
    Producer,
    Severity,
    check_sha256,
)

HANDOFF_SCHEMA = "theforge/Handoff/v1"
HandoffKind = Literal[
    "evidence", "finding", "artifact", "decision", "constraint", "assumption", "verification"
]
_NO_EPISTEMIC: frozenset[HandoffKind] = frozenset(
    {"finding", "artifact", "constraint", "assumption"}
)
_CLAIM_REQUIRED: frozenset[HandoffKind] = frozenset({"constraint", "assumption", "verification"})


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
    epistemic: Epistemic | None = None  # evidence: original; decision/verification: observed
    subject: str = ""
    claim: str = ""
    location: Location | None = None
    hash: str | None = field(default=None, metadata={"pattern": SHA256_RE.pattern})
    severity: Severity | None = None  # finding
    evidence_ids: list[str] = field(default_factory=list)  # finding
    # Provenance (D2): the upstream item this evidence derives from, verbatim.
    derived_from: EvidenceSource | None = None  # evidence
    # Content-addressed reuse (D3): origins of identical items merged into this one.
    also_from: list[HandoffOrigin] = field(default_factory=list)
    # Inferred artifact type (D4): unambiguous ``produces`` declaration of the source
    # capability; None when the type cannot be inferred.
    artifact_type: str | None = None

    def __post_init__(self) -> None:
        if len(self.claim) > MAX_CLAIM_CHARS:
            raise ContractError(
                f"handoff item {self.id!r}: claim longer than "
                f"{MAX_CLAIM_CHARS} chars ({len(self.claim)})"
            )
        if self.kind == "evidence" and self.epistemic is None:
            raise ContractError(f"handoff evidence {self.id!r}: epistemic is required")
        if self.kind in _NO_EPISTEMIC and self.epistemic is not None:
            raise ContractError(f"handoff {self.kind} {self.id!r}: epistemic must be absent")
        if self.kind in _CLAIM_REQUIRED and not self.claim:
            raise ContractError(f"handoff {self.kind} {self.id!r}: claim is required")
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
