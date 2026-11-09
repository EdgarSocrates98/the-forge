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
_OUTCOMES = ("created", "unchanged", "conflict", "updated")


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
    path: str
    content_hash: str = field(metadata={"pattern": SHA256_RE.pattern})
    outcome: Literal["created", "unchanged", "conflict", "updated"]
    source: str = ""
    classification: Literal["public", "internal", "confidential", "restricted"] = "internal"
    previous_hash: str | None = field(default=None, metadata={"pattern": SHA256_RE.pattern})
    baseline_hash: str | None = field(default=None, metadata={"pattern": SHA256_RE.pattern})
    workspace: str = ""
    vault_id: str = ""
    warnings: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    planned_at: str = ""

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
    path: str
    content_hash: str = field(metadata={"pattern": SHA256_RE.pattern})
    sync_state: Literal["created", "updated", "unchanged"]
    previous_hash: str | None = field(default=None, metadata={"pattern": SHA256_RE.pattern})
    title: str = ""
    size: int = 0
    source: str = ""
    classification: Literal["public", "internal", "confidential", "restricted"] = "internal"
    backup_path: str | None = None
    warnings: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    exported_at: str = ""

    def __post_init__(self) -> None:
        if self.schema != OBSIDIAN_SYNC_RECEIPT_SCHEMA:
            raise ContractError(f"unsupported Obsidian sync receipt schema {self.schema!r}")
        _safe_relative_path(self.path)
        _hash(self.content_hash, "content_hash")
        if self.previous_hash is not None:
            _hash(self.previous_hash, "previous_hash")
        if self.backup_path is not None:
            _safe_relative_path(self.backup_path)
        if self.size < 0:
            raise ContractError("size must be non-negative")

