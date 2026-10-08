"""WorkspaceGraph: minimal graph of workspace, providers and plan; every edge has evidence.

Local invariants: an edge has non-empty evidence and names its rule exactly when it is
inferred. Edges pointing to missing nodes are a relational check (``validate_graph``).
"""

from dataclasses import dataclass, field
from typing import Literal

from theforge.contracts.base import ContractError
from theforge.contracts.types import EdgeEpistemic, Producer

GRAPH_SCHEMA = "theforge/WorkspaceGraph/v1"
NodeKind = Literal[
    "workspace", "repository", "provider", "capability", "plan_node", "evidence", "artifact",
    # Cycle 5 (wave C): intelligence nodes — knowledge and execution records.
    "component", "file", "decision", "failure", "memory", "execution",
]
EdgeKind = Literal[
    "contains", "depends_on", "declares", "uses", "targets", "produced", "handed_off_to",
    # Cycle 5 (wave C): reasoning/trace relations between knowledge nodes.
    "requires", "produces", "consumes", "verifies", "calls", "reads", "writes",
    "affects", "derived_from", "supersedes", "executed_by", "supports",
    "specializes", "conflicts_with",
]


@dataclass(frozen=True, kw_only=True)
class GraphNode:
    id: str  # "<kind>:<key>"
    kind: NodeKind
    label: str = ""


@dataclass(frozen=True, kw_only=True)
class GraphEdge:
    source: str
    target: str
    kind: EdgeKind
    epistemic: EdgeEpistemic
    evidence: str  # never empty
    rule: str | None = None  # required when inferred; forbidden otherwise

    def __post_init__(self) -> None:
        edge = f"edge {self.source!r} -{self.kind}-> {self.target!r}"
        if not self.evidence.strip():
            raise ContractError(f"{edge}: evidence must not be empty")
        if self.epistemic == "inferred" and not self.rule:
            raise ContractError(f"{edge}: inferred edge requires a rule")
        if self.epistemic != "inferred" and self.rule is not None:
            raise ContractError(f"{edge}: rule is only allowed on inferred edges")


@dataclass(frozen=True, kw_only=True)
class WorkspaceGraph:
    schema: str = GRAPH_SCHEMA
    producer: Producer
    created_at: str
    plan_run: str
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    truncated: bool = False
    limitations: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != GRAPH_SCHEMA:
            raise ContractError(f"unsupported schema {self.schema!r}, expected {GRAPH_SCHEMA!r}")
