"""ContextPack: references + hashes of the files a provider may read."""

from dataclasses import dataclass, field
from typing import Literal

from theforge.contracts.base import ContractError
from theforge.contracts.types import Producer

CONTEXT_SCHEMA = "theforge/ContextPack/v1"


@dataclass(frozen=True, kw_only=True)
class ContextFile:
    path: str
    sha256: str
    bytes: int
    reason: str = ""


@dataclass(frozen=True, kw_only=True)
class ExcludedFile:
    path: str
    reason: str


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

    def __post_init__(self) -> None:
        if self.schema != CONTEXT_SCHEMA:
            raise ContractError(f"unsupported schema {self.schema!r}, expected {CONTEXT_SCHEMA!r}")
        if self.truncated != (self.status == "truncated"):
            raise ContractError("context pack truncated flag does not match status")
