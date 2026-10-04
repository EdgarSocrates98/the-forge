"""WorkspaceDescriptor: repositories, technologies and relations of a multi-repo workspace.

Each repository embeds the Wave C ``GitSummary`` as returned by the read-only git query
(no field redeclared). Technologies and relations always carry the path that evidences
them.
"""

from dataclasses import dataclass, field
from typing import Final, Literal

from theforge.contracts.base import ContractError
from theforge.contracts.context import GitSummary
from theforge.contracts.types import Producer

WORKSPACE_SCHEMA = "theforge/WorkspaceDescriptor/v1"
# Total git time of one workspace description (seconds), not one timeout per repository.
WORKSPACE_GIT_BUDGET_S: Final = 20.0


def _require_evidence(evidence: str, what: str) -> None:
    if not evidence.strip():
        raise ContractError(f"{what}: evidence must not be empty")


@dataclass(frozen=True, kw_only=True)
class RepositoryInfo:
    path: str  # relative to the root, "." for the root
    git: GitSummary | None = None  # None = git not queried (budget exhausted)
    dependency_files: list[str] = field(default_factory=list)  # relative to the root
    limitations: list[str] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class Technology:
    name: str  # normalized dependency or provider-declared domain
    repository: str
    source: Literal["dependency_manifest", "provider_signal"]
    evidence: str  # path that evidences it
    matched_by: list[str] = field(default_factory=list)  # "<provider>/<capability>"

    def __post_init__(self) -> None:
        _require_evidence(self.evidence, f"technology {self.name!r}")


@dataclass(frozen=True, kw_only=True)
class WorkspaceRelation:
    source: str  # repository paths
    target: str
    kind: Literal["contains", "depends_on"]
    epistemic: Literal["explicit", "observed"]
    evidence: str  # ".forge/config/workspace.toml" or the .git path

    def __post_init__(self) -> None:
        _require_evidence(self.evidence, f"relation {self.source!r} -> {self.target!r}")


@dataclass(frozen=True, kw_only=True)
class WorkspaceDescriptor:
    schema: str = WORKSPACE_SCHEMA
    producer: Producer
    created_at: str
    root: str
    repositories: list[RepositoryInfo] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)  # repository roots and dependency files
    technologies: list[Technology] = field(default_factory=list)
    relations: list[WorkspaceRelation] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != WORKSPACE_SCHEMA:
            raise ContractError(
                f"unsupported schema {self.schema!r}, expected {WORKSPACE_SCHEMA!r}")
