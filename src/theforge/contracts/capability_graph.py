"""CapabilityGraph: the relational view of providers, capabilities and workspace.

Built deterministically from manifests (declared edges) and the workspace
descriptor (observed edges) — never from domain knowledge: the builder does not
know what Spark or an API is. Every edge carries its evidence; inferred edges
must name their rule (same discipline as ``WorkspaceGraph``).

Answers the planning questions of wave B: who can execute a capability, who can
verify or review it, who produces/consumes an artifact type, what complements or
conflicts, and a deterministic topological order over the requires/produces→
consumes chains.
"""

from dataclasses import dataclass, field
from typing import Literal

from theforge.contracts.base import ContractError
from theforge.contracts.types import EdgeEpistemic, Producer, check_sha256

CAPABILITY_GRAPH_SCHEMA = "theforge/CapabilityGraph/v1"

CapNodeKind = Literal[
    "provider",
    "capability",
    "action",
    "artifact_type",
    "technology",
    "repository",
    "domain",
]
CapEdgeKind = Literal[
    # derived from the manifest itself
    "has_capability",
    "has_action",
    "in_domain",
    # declared by capability.relations
    "produces",
    "consumes",
    "requires",
    "complements",
    "conflicts",
    "can_verify",
    "can_review",
    # Cycle 5: explicit artifact-aware verification / specialization links
    "accepts",
    "verifies",
    "verified_by",
    "specializes",
    "refines",
    # observed by the workspace descriptor
    "uses_technology",
    "relevant_to",
]
_CAP_NODE_KINDS: tuple[CapNodeKind, ...] = (
    "provider",
    "capability",
    "action",
    "artifact_type",
    "technology",
    "repository",
    "domain",
)
_CAP_EDGE_KINDS: tuple[CapEdgeKind, ...] = (
    "has_capability",
    "has_action",
    "in_domain",
    "produces",
    "consumes",
    "requires",
    "complements",
    "conflicts",
    "can_verify",
    "can_review",
    "accepts",
    "verifies",
    "verified_by",
    "specializes",
    "refines",
    "uses_technology",
    "relevant_to",
)


@dataclass(frozen=True, kw_only=True)
class CapNode:
    """One vertex; ``id`` is ``"<kind>:<key>"`` (e.g. ``capability:forge/x.y``)."""

    id: str
    kind: CapNodeKind
    label: str = ""

    def __post_init__(self) -> None:
        if self.kind not in _CAP_NODE_KINDS:
            raise ContractError(f"capability graph node kind {self.kind!r} unknown")
        if not self.id.startswith(f"{self.kind}:"):
            raise ContractError(
                f"capability graph node id {self.id!r} must start with {self.kind!r}:"
            )


@dataclass(frozen=True, kw_only=True)
class CapEdge:
    """``source -kind-> target``; evidence never empty; rule iff inferred."""

    source: str
    target: str
    kind: CapEdgeKind
    epistemic: EdgeEpistemic
    evidence: str
    rule: str | None = None

    def __post_init__(self) -> None:
        edge = f"capability graph edge {self.source!r} -{self.kind}-> {self.target!r}"
        if self.kind not in _CAP_EDGE_KINDS:
            raise ContractError(f"{edge}: unknown kind")
        if not self.evidence.strip():
            raise ContractError(f"{edge}: evidence must not be empty")
        if self.epistemic == "inferred" and not self.rule:
            raise ContractError(f"{edge}: inferred edge requires a rule")
        if self.epistemic != "inferred" and self.rule is not None:
            raise ContractError(f"{edge}: rule is only allowed on inferred edges")


@dataclass(frozen=True, kw_only=True)
class CapabilityGraph:
    schema: str = CAPABILITY_GRAPH_SCHEMA
    producer: Producer
    created_at: str
    run_id: str
    nodes: list[CapNode] = field(default_factory=list)
    edges: list[CapEdge] = field(default_factory=list)
    truncated: bool = False
    limitations: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != CAPABILITY_GRAPH_SCHEMA:
            raise ContractError(
                f"unsupported schema {self.schema!r}, expected {CAPABILITY_GRAPH_SCHEMA}"
            )
        ids = [n.id for n in self.nodes]
        dups = sorted({i for i in ids if ids.count(i) > 1})
        if dups:
            raise ContractError(f"capability graph: duplicate node ids {dups}")
        known = set(ids)
        dangling = sorted(({e.source for e in self.edges} | {e.target for e in self.edges}) - known)
        if dangling:
            raise ContractError(
                f"capability graph: edges point at nodes not in the graph {dangling}"
            )


CAPABILITY_RELATION_SCHEMA = "theforge/CapabilityRelation/v1"

RELATION_KINDS: tuple[str, ...] = (
    "produces",
    "consumes",
    "accepts",
    "verifies",
    "requires",
    "complements",
    "conflicts",
    "can_verify",
    "can_review",
    "verified_by",
    "refines",
    "specializes",
)


@dataclass(frozen=True, kw_only=True)
class CapabilityRelation:
    """A standalone, evidence-bound relation between two capability/artifact
    endpoints (Cycle 5, Wave D).

    ``source``/``target`` are capability or artifact_type ids (``<kind>:<key>``
    convention is *not* required here — adapters declare bare ids); ``surface``
    scopes the relation to the provider surface it was declared/observed on, so
    a surface change cannot silently keep a stale relation authoritative.
    """

    schema: str = CAPABILITY_RELATION_SCHEMA
    producer: Producer
    created_at: str
    source: str
    relation: str
    target: str
    epistemic: EdgeEpistemic = "observed"
    constraints: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list, metadata={"min_items": 1})
    surface: str | None = None

    def __post_init__(self) -> None:
        if self.schema != CAPABILITY_RELATION_SCHEMA:
            raise ContractError(f"capability relation: unsupported schema {self.schema!r}")
        if self.relation not in RELATION_KINDS:
            raise ContractError(f"capability relation: unknown relation {self.relation!r}")
        if not self.source or not self.target:
            raise ContractError("capability relation: source/target are required")
        if not self.evidence:
            raise ContractError("capability relation: evidence must not be empty")
        if self.epistemic not in ("explicit", "observed", "inferred"):
            raise ContractError(f"capability relation: unknown epistemic {self.epistemic!r}")
        if len(self.constraints) > 32 or len(self.evidence) > 32:
            raise ContractError("capability relation: constraints/evidence exceed bound")
        if self.surface is not None:
            check_sha256(self.surface, field="capability relation surface")
