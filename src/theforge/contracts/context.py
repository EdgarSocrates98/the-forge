"""ContextPack: references + hashes of the files a provider may read.

Context v2 fields (tiers, line ranges, signals, workspace summary) are additive: every
new field has a default that reproduces v1, so v1 packs are re-read strictly. No field
carries file content.
"""

from dataclasses import dataclass, field
from typing import Literal

from theforge.contracts.base import ContractError
from theforge.contracts.types import SHA256_RE, ItemTier, Metric, Producer, check_sha256

CONTEXT_SCHEMA = "theforge/ContextPack/v1"


@dataclass(frozen=True, kw_only=True)
class LineRange:
    start: int  # 1-based, >= 1
    end: int  # inclusive, >= start

    def __post_init__(self) -> None:
        if self.start < 1 or self.end < self.start:
            raise ContractError(
                f"invalid line range {self.start}-{self.end}: expected 1 <= start <= end"
            )


@dataclass(frozen=True, kw_only=True)
class ContextFile:
    path: str
    # Whole file (reference) or the line range (excerpt/requested with lines).
    sha256: str = field(metadata={"pattern": SHA256_RE.pattern})
    bytes: int
    reason: str = ""  # human-readable summary (v1 compat)
    tier: ItemTier = "reference"
    lines: LineRange | None = None  # required for excerpt; forbidden for reference
    signals: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        check_sha256(self.sha256, field="sha256")
        if self.tier == "excerpt" and self.lines is None:
            raise ContractError(f"context item {self.path!r}: tier excerpt requires lines")
        if self.tier == "reference" and self.lines is not None:
            raise ContractError(f"context item {self.path!r}: tier reference must not have lines")


@dataclass(frozen=True, kw_only=True)
class ExcludedFile:
    path: str
    reason: str  # one ExclusionReason value
    signals: list[str] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class GitSummary:
    available: bool
    branch: str | None = None
    head: str | None = None
    detached: bool = False
    dirty: bool | None = None
    changed_files: int | None = None
    state: list[str] = field(default_factory=list)  # no_commits, merge, rebase, cherry_pick, bisect


@dataclass(frozen=True, kw_only=True)
class WorkspaceSummary:
    files_scanned: int
    unmatched_files: int  # aggregate of files without any signal
    dependency_files: list[str] = field(default_factory=list)
    git: GitSummary | None = None


@dataclass(frozen=True, kw_only=True)
class ContextPack:
    schema: str = CONTEXT_SCHEMA
    producer: Producer
    created_at: str
    status: Literal["complete", "truncated"]
    task_id: str
    provider_id: str
    root: str
    files: list[ContextFile] = field(default_factory=list)
    excluded: list[ExcludedFile] = field(default_factory=list)
    budget_bytes: int
    used_bytes: int = 0
    truncated: bool = False
    limitations: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    workspace: WorkspaceSummary | None = None  # metadata tier (always present in v2 packs)
    tier_bytes: dict[str, int] = field(default_factory=dict)
    tokens: Metric = field(default_factory=Metric)  # always unknown in the core
    round: int = 0  # 0 = initial; 1..2 = negotiation round

    def __post_init__(self) -> None:
        if self.schema != CONTEXT_SCHEMA:
            raise ContractError(f"unsupported schema {self.schema!r}, expected {CONTEXT_SCHEMA!r}")
        if self.truncated != (self.status == "truncated"):
            raise ContractError("context pack truncated flag does not match status")
