"""Canonical Obsidian synchronization contracts for the Forge ecosystem.

The contracts contain metadata and decisions only.  Vault bytes remain owned by
the specialist that has the configured vault access; the Portal and other
Forjas exchange plans and receipts without importing that implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from theforge.contracts.base import ContractError
from theforge.contracts.types import SHA256_RE

OBSIDIAN_SYNC_PLAN_SCHEMA = "theforge/ObsidianSyncPlan/v1"
OBSIDIAN_SYNC_RECEIPT_SCHEMA = "theforge/ObsidianSyncReceipt/v1"
OBSIDIAN_VAULT_DESCRIPTOR_SCHEMA = "theforge/ObsidianVaultDescriptor/v1"
OBSIDIAN_NOTE_REF_SCHEMA = "theforge/ObsidianNoteRef/v1"
OBSIDIAN_CONFLICT_SCHEMA = "theforge/ObsidianConflict/v1"
OBSIDIAN_EXPORT_PROFILE_SCHEMA = "theforge/ObsidianExportProfile/v1"
_OUTCOMES = (
    "created",
    "unchanged",
    "conflict",
    "updated",
    "skipped",
    "denied",
    "failed",
    "rolled_back",
)


def _required(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{name} is required")


def _safe_relative_path(path: str) -> None:
    _required(path, "path")
    if path.startswith(("/", "\\")) or ":" in path:
        raise ContractError("path must be relative to the configured vault")
    if any(part == ".." for part in path.replace("\\", "/").split("/")):
        raise ContractError("path traversal is not allowed")


def _hash(value: str, name: str) -> None:
    if SHA256_RE.fullmatch(value) is None:
        raise ContractError(f"{name} must be a lowercase sha256 digest")


@dataclass(frozen=True, kw_only=True)
class ObsidianSyncPlan:
    schema: str = OBSIDIAN_SYNC_PLAN_SCHEMA
    version: str = "v1"
    path: str
    content_hash: str = field(metadata={"pattern": SHA256_RE.pattern})
    outcome: Literal[
        "created",
        "unchanged",
        "conflict",
        "updated",
        "skipped",
        "denied",
        "failed",
        "rolled_back",
    ]
    source: str = ""
    classification: Literal["public", "internal", "confidential", "restricted"] = "internal"
    previous_hash: str | None = field(default=None, metadata={"pattern": SHA256_RE.pattern})
    baseline_hash: str | None = field(default=None, metadata={"pattern": SHA256_RE.pattern})
    workspace: str = ""
    vault_id: str = ""
    provenance: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    planned_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if self.schema != OBSIDIAN_SYNC_PLAN_SCHEMA:
            raise ContractError(f"unsupported Obsidian sync plan schema {self.schema!r}")
        _safe_relative_path(self.path)
        _hash(self.content_hash, "content_hash")
        if self.previous_hash is not None:
            _hash(self.previous_hash, "previous_hash")
        if self.baseline_hash is not None:
            _hash(self.baseline_hash, "baseline_hash")
        if self.outcome not in _OUTCOMES:
            raise ContractError(f"unsupported sync outcome {self.outcome!r}")
        if self.outcome == "conflict" and not self.unresolved:
            raise ContractError("conflict plans must declare unresolved items")


@dataclass(frozen=True, kw_only=True)
class ObsidianSyncReceipt:
    schema: str = OBSIDIAN_SYNC_RECEIPT_SCHEMA
    version: str = "v1"
    path: str
    content_hash: str = field(metadata={"pattern": SHA256_RE.pattern})
    sync_state: Literal[
        "created",
        "updated",
        "unchanged",
        "skipped",
        "denied",
        "failed",
        "rolled_back",
    ]
    workspace: str = ""
    vault_id: str = ""
    previous_hash: str | None = field(default=None, metadata={"pattern": SHA256_RE.pattern})
    baseline_hash: str | None = field(default=None, metadata={"pattern": SHA256_RE.pattern})
    title: str = ""
    size: int = 0
    source: str = ""
    classification: Literal["public", "internal", "confidential", "restricted"] = "internal"
    backup_path: str | None = None
    outcome: str = ""
    provenance: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    exported_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if self.schema != OBSIDIAN_SYNC_RECEIPT_SCHEMA:
            raise ContractError(f"unsupported Obsidian sync receipt schema {self.schema!r}")
        _safe_relative_path(self.path)
        _hash(self.content_hash, "content_hash")
        if self.previous_hash is not None:
            _hash(self.previous_hash, "previous_hash")
        if self.baseline_hash is not None:
            _hash(self.baseline_hash, "baseline_hash")
        if self.backup_path is not None:
            _safe_relative_path(self.backup_path)
        if self.size < 0:
            raise ContractError("size must be non-negative")


@dataclass(frozen=True, kw_only=True)
class ObsidianVaultDescriptor:
    schema: str = OBSIDIAN_VAULT_DESCRIPTOR_SCHEMA
    version: str = "v1"
    workspace: str
    vault_id: str
    path: str
    source: str
    classification: Literal["public", "internal", "confidential", "restricted"] = "internal"
    detected: bool = False
    capabilities: list[str] = field(default_factory=list)
    detected_at: str = ""
    content_hash: str | None = field(default=None, metadata={"pattern": SHA256_RE.pattern})
    previous_hash: str | None = field(default=None, metadata={"pattern": SHA256_RE.pattern})
    updated_at: str = ""
    outcome: str = ""
    provenance: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != OBSIDIAN_VAULT_DESCRIPTOR_SCHEMA:
            raise ContractError(f"unsupported Obsidian vault schema {self.schema!r}")
        for name in ("workspace", "vault_id", "source"):
            _required(getattr(self, name), name)
        _safe_relative_path(self.path)
        if self.content_hash is not None:
            _hash(self.content_hash, "content_hash")
        if self.previous_hash is not None:
            _hash(self.previous_hash, "previous_hash")


@dataclass(frozen=True, kw_only=True)
class ObsidianNoteRef:
    schema: str = OBSIDIAN_NOTE_REF_SCHEMA
    version: str = "v1"
    workspace: str
    vault_id: str
    path: str
    source: str
    classification: Literal["public", "internal", "confidential", "restricted"] = "internal"
    content_hash: str = field(metadata={"pattern": SHA256_RE.pattern})
    previous_hash: str | None = field(default=None, metadata={"pattern": SHA256_RE.pattern})
    updated_at: str = ""
    provenance: dict[str, str] = field(default_factory=dict)
    outcome: str = ""
    warnings: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != OBSIDIAN_NOTE_REF_SCHEMA:
            raise ContractError(f"unsupported Obsidian note ref schema {self.schema!r}")
        for name in ("workspace", "vault_id", "source"):
            _required(getattr(self, name), name)
        _safe_relative_path(self.path)
        _hash(self.content_hash, "content_hash")
        if self.previous_hash is not None:
            _hash(self.previous_hash, "previous_hash")


@dataclass(frozen=True, kw_only=True)
class ObsidianConflict:
    schema: str = OBSIDIAN_CONFLICT_SCHEMA
    version: str = "v1"
    workspace: str
    vault_id: str
    path: str
    source: str
    classification: Literal["public", "internal", "confidential", "restricted"] = "internal"
    baseline_hash: str = field(metadata={"pattern": SHA256_RE.pattern})
    vault_hash: str = field(metadata={"pattern": SHA256_RE.pattern})
    candidate_hash: str = field(metadata={"pattern": SHA256_RE.pattern})
    detected_at: str = ""
    content_hash: str | None = field(default=None, metadata={"pattern": SHA256_RE.pattern})
    previous_hash: str | None = field(default=None, metadata={"pattern": SHA256_RE.pattern})
    updated_at: str = ""
    provenance: dict[str, str] = field(default_factory=dict)
    outcome: Literal["conflict", "resolved", "denied"] = "conflict"
    warnings: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=lambda: ["manual conflict resolution required"])

    def __post_init__(self) -> None:
        if self.schema != OBSIDIAN_CONFLICT_SCHEMA:
            raise ContractError(f"unsupported Obsidian conflict schema {self.schema!r}")
        for name in ("workspace", "vault_id", "source"):
            _required(getattr(self, name), name)
        _safe_relative_path(self.path)
        for name in ("baseline_hash", "vault_hash", "candidate_hash"):
            _hash(getattr(self, name), name)
        if self.content_hash is not None:
            _hash(self.content_hash, "content_hash")
        if self.previous_hash is not None:
            _hash(self.previous_hash, "previous_hash")
        if self.outcome == "conflict" and not self.unresolved:
            raise ContractError("unresolved conflict must retain an unresolved reason")


@dataclass(frozen=True, kw_only=True)
class ObsidianExportProfile:
    schema: str = OBSIDIAN_EXPORT_PROFILE_SCHEMA
    version: str = "v1"
    workspace: str
    vault_id: str
    source: str
    path: str = ""
    classification: Literal["public", "internal", "confidential", "restricted"] = "internal"
    mode: Literal["export_only", "import_read_only", "reviewed_sync"] = "export_only"
    include_frontmatter: bool = True
    include_relations: bool = True
    template: str = ""
    allowed_extensions: list[str] = field(default_factory=lambda: [".md"])
    provenance: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    content_hash: str | None = field(default=None, metadata={"pattern": SHA256_RE.pattern})
    previous_hash: str | None = field(default=None, metadata={"pattern": SHA256_RE.pattern})
    updated_at: str = ""
    outcome: str = ""

    def __post_init__(self) -> None:
        if self.schema != OBSIDIAN_EXPORT_PROFILE_SCHEMA:
            raise ContractError(f"unsupported Obsidian export profile schema {self.schema!r}")
        for name in ("workspace", "vault_id", "source"):
            _required(getattr(self, name), name)
        if self.path:
            _safe_relative_path(self.path)
        if not self.allowed_extensions:
            raise ContractError("allowed_extensions must not be empty")
        if self.content_hash is not None:
            _hash(self.content_hash, "content_hash")
        if self.previous_hash is not None:
            _hash(self.previous_hash, "previous_hash")

