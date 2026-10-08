"""Engineering Memory contracts (Cycle 5, Wave B).

Memory is *verifiable engineering knowledge*, not conversation history:
every entry carries an epistemic state and provenance refs into the artifact
store. The rules these contracts enforce:

- ``reported`` never becomes ``confirmed`` without a verification event —
  ``confirmed`` requires at least one ``evidence_refs`` or ``decision_refs``
  entry pointing at persisted, hash-checkable material.
- memory without provenance is ``unresolved``/low-trust by construction:
  an entry that is not ``unresolved`` must cite at least one source.
- ``stale``/``superseded`` entries keep their history (``superseded_by``
  links forward, never deletes).
- ``scope`` governs cross-project visibility: only ``portable`` or
  ``organization`` entries may leave the project boundary — and only when
  they carry ``origin_project_class`` + redaction evidence.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from theforge.contracts.base import ContractError
from theforge.contracts.types import SHA256_RE, Producer, check_ref, check_sha256

MEMORY_ENTRY_SCHEMA = "theforge/EngineeringMemoryEntry/v1"
MEMORY_PACK_SCHEMA = "theforge/MemoryPack/v1"
MEMORY_SUMMARY_SCHEMA = "theforge/MemorySummary/v1"
FAILURE_PATTERN_SCHEMA = "theforge/FailurePattern/v1"

MemoryKind = Literal[
    "fact",
    "decision",
    "failure",
    "resolution",
    "constraint",
    "architecture",
    "compatibility",
    "strategy_result",
    "incident",
    "performance_observation",
]

MemoryEpistemic = Literal[
    "confirmed",
    "observed",
    "reported",
    "inferred",
    "unresolved",
    "stale",
    "superseded",
]

# Cross-project visibility ladder. ``project`` is the default and never leaves
# the workspace; ``workspace`` narrows to one repository root; ``portable``
# and ``organization`` are the only scopes allowed across projects, and both
# demand explicit classification evidence.
MemoryScope = Literal["project", "workspace", "portable", "organization"]

CrossProjectScopes = ("portable", "organization")

MAX_TAGS = 16
MAX_REFS = 64
MAX_TEXT = 2000  # subject/claim/stale_reason bound


def _require_text(name: str, value: object, *, allow_empty: bool = False) -> None:
    if not isinstance(value, str) or (not allow_empty and not value):
        raise ContractError(f"{name} must be a non-empty string")
    if len(value) > MAX_TEXT:
        raise ContractError(f"{name} exceeds {MAX_TEXT} chars")


def _check_timestamp(name: str, value: str | None) -> None:
    if value is None:
        return
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError(f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ContractError(f"{name} must carry a timezone offset")


def _check_refs(name: str, values: tuple[str, ...] | list[str]) -> None:
    if len(values) > MAX_REFS:
        raise ContractError(f"{name} exceeds {MAX_REFS} refs")
    for ref in values:
        check_ref(ref, field=name)


@dataclass(frozen=True, kw_only=True)
class EngineeringMemoryEntry:
    """One durable, provenance-bound unit of engineering knowledge (v1).

    ``id`` is content-derived by the store (sha256 of kind|scope|subject|claim
    |producer); ``source_refs`` are opaque URIs into the run store or external
    systems (``forge:``/``run:``/``commit:``/``artifact:`` conventions —
    opaque, never dereferenced by the core).
    """

    schema: str = MEMORY_ENTRY_SCHEMA
    producer: Producer
    created_at: str
    id: str = field(metadata={"pattern": SHA256_RE.pattern})
    kind: MemoryKind = "fact"
    scope: MemoryScope = "project"
    subject: str = ""
    claim: str = ""
    epistemic: MemoryEpistemic = "unresolved"
    workspace: str | None = None
    project: str | None = None
    task_family: str | None = None
    provider: str | None = None
    capability: str | None = None
    surface_fingerprint: str | None = None
    execution_target: str | None = None
    source_refs: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    decision_refs: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    surface_refs: list[str] = field(default_factory=list)
    valid_from: str | None = None
    valid_until: str | None = None
    stale_reason: str | None = None
    supersedes: str | None = field(default=None, metadata={"pattern": SHA256_RE.pattern})
    superseded_by: str | None = field(default=None, metadata={"pattern": SHA256_RE.pattern})
    last_confirmed_at: str | None = None
    origin_project_class: str | None = None
    redaction: str | None = None  # how portable/org content was sanitized
    tags: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != MEMORY_ENTRY_SCHEMA:
            raise ContractError(f"memory entry: unsupported schema {self.schema!r}")
        check_sha256(self.id, field="memory entry: id")
        _require_text("memory entry: subject", self.subject)
        _require_text("memory entry: claim", self.claim)
        _check_timestamp("memory entry: created_at", self.created_at)
        for name in (
            "source_refs",
            "evidence_refs",
            "decision_refs",
            "artifact_refs",
            "surface_refs",
        ):
            _check_refs(f"memory entry: {name}", getattr(self, name))
        if len(self.tags) > MAX_TAGS:
            raise ContractError(f"memory entry: tags exceed {MAX_TAGS}")
        for tag in self.tags:
            _require_text("memory entry: tag", tag)
        if len(self.limitations) > MAX_REFS:
            raise ContractError("memory entry: limitations exceed bound")
        # Provenance rule: any non-unresolved entry must cite at least one
        # source. Orphan memory stays unresolved/low-trust by construction.
        has_provenance = bool(
            self.source_refs or self.evidence_refs or self.decision_refs or self.artifact_refs
        )
        if self.epistemic != "unresolved" and not has_provenance:
            raise ContractError(
                f"memory entry: epistemic {self.epistemic!r} requires provenance "
                "(source/evidence/decision/artifact refs)"
            )
        # ``confirmed`` is a *verified* claim: it needs evidence or a decision
        # record, never a bare source pointer.
        if self.epistemic == "confirmed" and not (self.evidence_refs or self.decision_refs):
            raise ContractError(
                "memory entry: 'confirmed' requires evidence_refs or decision_refs"
            )
        if self.epistemic == "superseded" and not self.superseded_by:
            raise ContractError("memory entry: 'superseded' requires superseded_by")
        if self.epistemic == "stale" and not self.stale_reason:
            raise ContractError("memory entry: 'stale' requires stale_reason")
        if self.stale_reason is not None:
            _require_text("memory entry: stale_reason", self.stale_reason)
        for name, value in (
            ("supersedes", self.supersedes),
            ("superseded_by", self.superseded_by),
        ):
            if value is not None:
                check_sha256(value, field=f"memory entry: {name}")
        if self.supersedes is not None and self.supersedes == self.id:
            raise ContractError("memory entry: an entry cannot supersede itself")
        for name in ("valid_from", "valid_until", "last_confirmed_at"):
            _check_timestamp(f"memory entry: {name}", getattr(self, name))
        if (
            self.valid_from is not None
            and self.valid_until is not None
            and self.valid_until < self.valid_from
        ):
            raise ContractError("memory entry: valid_until precedes valid_from")
        # Cross-project isolation (Wave S): portable/organization entries must
        # declare where the knowledge came from and how it was sanitized.
        if self.scope in CrossProjectScopes:
            if not self.origin_project_class:
                raise ContractError(
                    f"memory entry: scope {self.scope!r} requires origin_project_class"
                )
            if not self.redaction:
                raise ContractError(
                    f"memory entry: scope {self.scope!r} requires a redaction statement"
                )
        elif self.origin_project_class is not None or self.redaction is not None:
            raise ContractError(
                "memory entry: origin_project_class/redaction belong to cross-project scopes"
            )


@dataclass(frozen=True, kw_only=True)
class MemoryPack:
    """A bounded, deterministic retrieval result (v1).

    The pack is what planning/context assembly consumes — never the raw store.
    ``truncated`` + ``limitations`` make a cut-off explicit; ``query`` echoes
    the structured filters used, so the result is replayable.
    """

    schema: str = MEMORY_PACK_SCHEMA
    producer: Producer
    created_at: str
    query: dict[str, str] = field(default_factory=dict)
    entries: list[EngineeringMemoryEntry] = field(default_factory=list)
    total_matches: int = 0
    delivered_bytes: int = 0
    truncated: bool = False
    limitations: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != MEMORY_PACK_SCHEMA:
            raise ContractError(f"memory pack: unsupported schema {self.schema!r}")
        if isinstance(self.total_matches, bool) or not isinstance(self.total_matches, int):
            raise ContractError("memory pack: total_matches must be an integer")
        if self.total_matches < 0:
            raise ContractError("memory pack: total_matches cannot be negative")
        if self.total_matches < len(self.entries):
            raise ContractError("memory pack: total_matches below delivered entries")
        if isinstance(self.delivered_bytes, bool) or not isinstance(self.delivered_bytes, int):
            raise ContractError("memory pack: delivered_bytes must be an integer")
        if self.delivered_bytes < 0:
            raise ContractError("memory pack: delivered_bytes cannot be negative")
        if self.truncated and self.total_matches == len(self.entries):
            raise ContractError("memory pack: truncated with nothing withheld")
        for key in self.query:
            if not isinstance(key, str) or not key:
                raise ContractError("memory pack: query keys must be non-empty strings")


@dataclass(frozen=True, kw_only=True)
class MemorySummary:
    """A distillation of memory entries — an index over sources, never a
    replacement for them (Wave T). ``source_ids`` must cover every entry the
    summary claims to compress; deleting sources is forbidden."""

    schema: str = MEMORY_SUMMARY_SCHEMA
    producer: Producer
    created_at: str
    id: str = field(metadata={"pattern": SHA256_RE.pattern})
    scope: MemoryScope = "project"
    subject: str = ""
    summary: str = ""
    source_ids: list[str] = field(default_factory=list, metadata={"min_items": 1})
    coverage: str = ""
    generated_at: str = ""
    limitations: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != MEMORY_SUMMARY_SCHEMA:
            raise ContractError(f"memory summary: unsupported schema {self.schema!r}")
        check_sha256(self.id, field="memory summary: id")
        _require_text("memory summary: subject", self.subject)
        _require_text("memory summary: summary", self.summary)
        if not self.source_ids:
            raise ContractError("memory summary: source_ids must not be empty")
        for sid in self.source_ids:
            check_sha256(sid, field="memory summary: source_ids")
        if len(set(self.source_ids)) != len(self.source_ids):
            raise ContractError("memory summary: duplicate source_ids")
        if self.scope in CrossProjectScopes:
            raise ContractError(
                "memory summary: summaries are project-local; portable/org knowledge "
                "crosses as entries, not summaries"
            )
        _check_timestamp("memory summary: generated_at", self.generated_at)
        if not self.generated_at:
            raise ContractError("memory summary: generated_at is required")


@dataclass(frozen=True, kw_only=True)
class FailurePattern:
    """A recurring failure signature distilled from run history (Wave Y).

    Keyed by (error family, provider, capability, surface, task family). It is
    an *observation* — ``resolved_by`` cites the decision/artifact that fixed
    it previously, as a recommendation, never an automatic action.
    """

    schema: str = FAILURE_PATTERN_SCHEMA
    producer: Producer
    created_at: str
    id: str = field(metadata={"pattern": SHA256_RE.pattern})
    error_family: str = ""
    provider: str | None = None
    capability: str | None = None
    surface_fingerprint: str | None = None
    task_family: str | None = None
    artifact: str | None = None
    environment: str | None = None
    occurrences: int = 0
    first_seen: str = ""
    last_seen: str = ""
    resolved_by: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != FAILURE_PATTERN_SCHEMA:
            raise ContractError(f"failure pattern: unsupported schema {self.schema!r}")
        check_sha256(self.id, field="failure pattern: id")
        _require_text("failure pattern: error_family", self.error_family)
        if isinstance(self.occurrences, bool) or not isinstance(self.occurrences, int):
            raise ContractError("failure pattern: occurrences must be an integer")
        if self.occurrences <= 0:
            raise ContractError("failure pattern: occurrences must be positive")
        for name in ("first_seen", "last_seen"):
            _check_timestamp(f"failure pattern: {name}", getattr(self, name))
        if not self.first_seen or not self.last_seen:
            raise ContractError("failure pattern: first_seen/last_seen are required")
        if self.last_seen < self.first_seen:
            raise ContractError("failure pattern: last_seen precedes first_seen")
        for ref in self.resolved_by:
            check_ref(ref, field="failure pattern: resolved_by")
