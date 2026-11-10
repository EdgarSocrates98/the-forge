"""Versioned, provider-neutral knowledge interoperability contracts.

These contracts describe document metadata and evidence crossing Forge
boundaries.  They deliberately contain references to artifacts, never the
artifact store itself, so bootstrap knowledge and runtime document ownership
remain separate.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from theforge.contracts.base import ContractError
from theforge.contracts.canonical import canonical_json

KNOWLEDGE_SOURCE_SCHEMA = "theforge/KnowledgeSource/v1"
KNOWLEDGE_DOCUMENT_SCHEMA = "theforge/KnowledgeDocument/v1"
KNOWLEDGE_CHUNK_SCHEMA = "theforge/KnowledgeChunk/v1"
KNOWLEDGE_EVIDENCE_SCHEMA = "theforge/KnowledgeEvidence/v1"
KNOWLEDGE_CONTEXT_PACK_SCHEMA = "theforge/KnowledgeContextPack/v1"
KNOWLEDGE_RELATION_SCHEMA = "theforge/KnowledgeRelation/v1"
KNOWLEDGE_IMPORT_RECEIPT_SCHEMA = "theforge/KnowledgeImportReceipt/v1"
KNOWLEDGE_STATES = (
    "captured",
    "draft",
    "reviewed",
    "validated",
    "deprecated",
    "rejected",
)

_RELATION_TYPES = (
    "references",
    "documents",
    "depends_on",
    "derived_from",
    "related_to",
    "observed_during",
    "validated_by",
)


def _required(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field_name} is required")


@dataclass(frozen=True, kw_only=True)
class KnowledgeSource:
    schema: str = KNOWLEDGE_SOURCE_SCHEMA
    source_id: str
    source_type: str
    locator: str
    workspace_id: str
    product_id: str | None = None
    classification: str = "internal"
    access_scope: list[str] = field(default_factory=list)
    auth_ref: str | None = None
    sync_config: dict[str, Any] = field(default_factory=dict)
    canonical_id: str | None = None
    state: Literal["active", "paused", "revoked", "unknown"] = "unknown"
    version_id: str | None = None
    retention_policy: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.schema != KNOWLEDGE_SOURCE_SCHEMA:
            raise ContractError(f"unsupported knowledge source schema {self.schema!r}")
        for name in ("source_id", "source_type", "locator", "workspace_id"):
            _required(getattr(self, name), name)
        secret_markers = ("password=", "secret=", "token=")
        if self.auth_ref and any(token in self.auth_ref.lower() for token in secret_markers):
            raise ContractError("auth_ref must reference a secret, never embed one")


@dataclass(frozen=True, kw_only=True)
class KnowledgeDocument:
    schema: str = KNOWLEDGE_DOCUMENT_SCHEMA
    document_id: str
    source_id: str
    workspace_id: str
    title: str
    content_type: str
    original_artifact_ref: str
    normalized_artifact_ref: str
    content_hash: str
    version: str
    classification: str
    trust_state: str
    created_at: str
    updated_at: str
    # Lifecycle is separate from trust_state: indexed storage is not
    # authority. Producers enter as captured/draft and consumers promote only
    # after their domain-specific evidence gate.
    knowledge_state: Literal[
        "captured", "draft", "reviewed", "validated", "deprecated", "rejected"
    ] = "captured"
    product_id: str | None = None
    source_updated_at: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.schema != KNOWLEDGE_DOCUMENT_SCHEMA:
            raise ContractError(f"unsupported knowledge document schema {self.schema!r}")
        for name in (
            "document_id",
            "source_id",
            "workspace_id",
            "title",
            "content_type",
            "original_artifact_ref",
            "normalized_artifact_ref",
            "content_hash",
            "version",
            "classification",
            "trust_state",
            "created_at",
            "updated_at",
        ):
            _required(getattr(self, name), name)
        if self.knowledge_state not in KNOWLEDGE_STATES:
            raise ContractError(f"unsupported knowledge state {self.knowledge_state!r}")


@dataclass(frozen=True, kw_only=True)
class KnowledgeChunk:
    schema: str = KNOWLEDGE_CHUNK_SCHEMA
    chunk_id: str
    document_id: str
    document_version: str
    text: str
    heading_path: list[str] = field(default_factory=list)
    start_offset: int = 0
    end_offset: int = 0
    sequence: int = 0
    token_estimate: int = 0
    content_hash: str = ""
    evidence_ids: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        for name in ("chunk_id", "document_id", "document_version", "text", "content_hash"):
            _required(getattr(self, name), name)
        invalid_offsets = (
            self.sequence < 0
            or self.token_estimate < 0
            or self.start_offset < 0
            or self.end_offset < self.start_offset
        )
        if invalid_offsets:
            raise ContractError("chunk offsets and counters must be non-negative and ordered")


@dataclass(frozen=True, kw_only=True)
class KnowledgeEvidence:
    schema: str = KNOWLEDGE_EVIDENCE_SCHEMA
    evidence_id: str
    source_id: str
    document_id: str
    document_version: str
    location: str
    excerpt: str
    extraction_method: str
    validation_method: str
    confidence_state: Literal["high", "medium", "low", "unknown"] = "unknown"

    def __post_init__(self) -> None:
        for name in (
            "evidence_id",
            "source_id",
            "document_id",
            "document_version",
            "location",
            "extraction_method",
            "validation_method",
        ):
            _required(getattr(self, name), name)


@dataclass(frozen=True, kw_only=True)
class KnowledgeContextItem:
    """Authorized inline content with explicit provenance."""

    item_id: str
    source_id: str
    document_id: str
    workspace_id: str
    version: str
    content_hash: str
    product_id: str | None = None
    body: str = ""
    kind: str = ""
    title: str = ""
    path: str = ""
    symbol_key: str = ""

    def __post_init__(self) -> None:
        for name in (
            "item_id",
            "source_id",
            "document_id",
            "workspace_id",
            "version",
            "content_hash",
        ):
            _required(getattr(self, name), name)


@dataclass(frozen=True, kw_only=True)
class KnowledgeContextPack:
    schema: str = KNOWLEDGE_CONTEXT_PACK_SCHEMA
    pack_id: str
    query: str
    workspace_id: str
    principal: str
    product_id: str | None = None
    source_versions: dict[str, str] = field(default_factory=dict)
    selected_items: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    estimated_tokens: int = 0
    budget_tokens: int = 0
    truncations: list[str] = field(default_factory=list)
    degraded_state: Literal["none", "partial", "unavailable"] = "none"
    diagnostics: list[str] = field(default_factory=list)
    items: list[KnowledgeContextItem] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != KNOWLEDGE_CONTEXT_PACK_SCHEMA:
            raise ContractError(f"unsupported knowledge context pack schema {self.schema!r}")
        for name in ("pack_id", "query", "workspace_id", "principal"):
            _required(getattr(self, name), name)
        if self.estimated_tokens < 0 or self.budget_tokens < 0:
            raise ContractError("context token counts must be non-negative")
        over_budget = self.budget_tokens and self.estimated_tokens > self.budget_tokens
        if over_budget and not self.truncations:
            raise ContractError("over-budget context packs must record truncations")
        if self.items and not self.source_versions:
            raise ContractError("context packs with inline items require source versions")
        selected = set(self.selected_items)
        for item in self.items:
            item_id = item.item_id
            source_id = item.source_id
            document_id = item.document_id
            item_workspace = item.workspace_id
            version = item.version
            if not item_id or (selected and item_id not in selected):
                raise ContractError("context pack inline item is not selected")
            if not source_id or source_id not in self.source_versions:
                raise ContractError("context pack inline item source is not declared")
            if not document_id or item_workspace != self.workspace_id:
                raise ContractError("context pack inline item workspace is invalid")
            if not version or version != self.source_versions[source_id]:
                raise ContractError("context pack inline item version is invalid")
            if self.product_id and item.product_id != self.product_id:
                raise ContractError("context pack inline item product is invalid")

    def ensure_authorized(self, allowed_item_ids: set[str]) -> None:
        unauthorized = sorted(set(self.selected_items) - allowed_item_ids)
        if unauthorized:
            raise ContractError(f"context pack contains unauthorized items: {unauthorized}")


@dataclass(frozen=True, kw_only=True)
class KnowledgeRelation:
    schema: str = KNOWLEDGE_RELATION_SCHEMA
    relation_id: str
    relation_type: Literal[
        "references",
        "documents",
        "depends_on",
        "derived_from",
        "related_to",
        "observed_during",
        "validated_by",
    ]
    source_id: str
    from_ref: str
    to_ref: str
    semantics: str
    evidence_ids: list[str] = field(default_factory=list)
    confidence_state: Literal["high", "medium", "low", "unknown"] = "unknown"
    inferred: bool = False

    def __post_init__(self) -> None:
        if self.schema != KNOWLEDGE_RELATION_SCHEMA:
            raise ContractError(f"unsupported knowledge relation schema {self.schema!r}")
        for name in ("relation_id", "source_id", "from_ref", "to_ref", "semantics"):
            _required(getattr(self, name), name)
        if self.relation_type not in _RELATION_TYPES:
            raise ContractError(f"unsupported knowledge relation type {self.relation_type!r}")


@dataclass(frozen=True, kw_only=True)
class KnowledgeImportReceipt:
    schema: str = KNOWLEDGE_IMPORT_RECEIPT_SCHEMA
    receipt_id: str
    operation: Literal["import", "update", "preview", "rollback"]
    source_id: str
    created_ids: list[str] = field(default_factory=list)
    updated_ids: list[str] = field(default_factory=list)
    skipped_ids: list[str] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    previous_version: str | None = None
    new_version: str | None = None
    content_hashes: dict[str, str] = field(default_factory=dict)
    duration_ms: int = 0
    audit_id: str = ""
    rollback_available: bool = False

    def __post_init__(self) -> None:
        if self.schema != KNOWLEDGE_IMPORT_RECEIPT_SCHEMA:
            raise ContractError(f"unsupported knowledge import receipt schema {self.schema!r}")
        for name in ("receipt_id", "source_id"):
            _required(getattr(self, name), name)
        if self.duration_ms < 0:
            raise ContractError("duration_ms must be non-negative")


def knowledge_canonical_json(value: Any) -> str:
    """Serialize one interoperability contract deterministically."""
    return canonical_json(asdict(value))
