"""GraphBuilder: minimal, deterministic graph of workspace, providers and plan (8.1-8.6).

Nodes: ``workspace:.``, ``repository:<path>``, ``provider:<id>``,
``capability:<provider>/<cap>``, ``plan_node:<id>``, ``evidence:<node>/<id>`` and
``artifact:<node>/<path>``. Every edge carries the evidence it comes from:

- ``contains`` (observed, ``<path>/.git``) and ``depends_on`` between repositories
  (explicit, ``.forge/config/workspace.toml``), copied from the workspace descriptor;
- ``declares`` provider -> capability (explicit, ``manifest:<sha256>``);
- ``uses`` / ``targets`` plan_node -> capability / repository (explicit, ``plan:<sha256>``);
- ``depends_on`` plan_node -> plan_node (as declared by the plan: explicit for a plan file,
  inferred with its rule for a decomposed plan; evidence ``plan:<sha256>``);
- ``produced`` plan_node -> evidence/artifact (observed, ``result:<sha256>``);
- ``handed_off_to`` evidence -> plan_node (observed, ``handoff:<sha256>``), one per
  ``evidence`` item of the handoff the node received.

An edge without evidence, with a missing endpoint or inferred without a rule is dropped
and recorded as a ``Codes.WORKSPACE_GRAPH_EDGE`` limitation (8.3, 8.4). Nodes are sorted by
id and edges by (source, kind, target) (8.5). Above the node limit, evidence and artifact
nodes are cut in id order and the graph is marked ``truncated``. The graph is a plain run
artifact: nothing here touches the disk (8.6).
"""

from collections.abc import Sequence
from typing import Final

from theforge.contracts.base import ContractError, to_dict
from theforge.contracts.canonical import sha256_of, utc_now
from theforge.contracts.codes import Codes
from theforge.contracts.graph import (
    EdgeKind,
    GraphEdge,
    GraphNode,
    WorkspaceGraph,
)
from theforge.contracts.integrity import check_graph_edge
from theforge.contracts.plan import ExecutionPlan
from theforge.contracts.types import MAX_GRAPH_NODES, EdgeEpistemic
from theforge.contracts.workspace import WorkspaceDescriptor
from theforge.meta import PRODUCER
from theforge.planning.execution import NodeExecution
from theforge.registry import RegistryRecord
from theforge.workspace import repository_of

__all__ = ["WORKSPACE_NODE", "GraphBuilder", "build_graph"]

WORKSPACE_NODE: Final = "workspace:."
# Node kinds that may be cut when the graph exceeds its node limit.
_TRUNCATABLE: Final = frozenset({"evidence", "artifact"})


class GraphBuilder:
    """Accumulates nodes and evidenced edges; ``build`` returns the ordered graph."""

    def __init__(self, plan_run: str, *, max_nodes: int = MAX_GRAPH_NODES) -> None:
        self._plan_run = plan_run
        self._max_nodes = max_nodes
        self._nodes: dict[str, GraphNode] = {}
        self._ids: set[str] = set()
        self._edges: dict[GraphEdge, None] = {}  # insertion-ordered set
        self._limitations: dict[str, None] = {}

    def add_node(self, node: GraphNode) -> None:
        """Add ``node``; a node with an id already present is ignored (first wins)."""
        self._nodes.setdefault(node.id, node)
        self._ids.add(node.id)

    def add_edge(self, edge: GraphEdge) -> bool:
        """Add ``edge`` if both endpoints exist; otherwise drop it with a limitation."""
        violation = check_graph_edge(edge, self._ids)
        if violation is not None:
            self._reject(f"{violation.code}: {violation.detail}")
            return False
        self._edges.setdefault(edge, None)
        return True

    def propose(self, *, source: str, target: str, kind: EdgeKind, epistemic: EdgeEpistemic,
                evidence: str, rule: str | None = None) -> bool:
        """Build and add an edge; one without evidence or inferred without rule is dropped."""
        try:
            edge = GraphEdge(source=source, target=target, kind=kind, epistemic=epistemic,
                             evidence=evidence, rule=rule)
        except ContractError as exc:
            self._reject(f"{Codes.WORKSPACE_GRAPH_EDGE}: {exc}")
            return False
        return self.add_edge(edge)

    def build(self, *, created_at: str | None = None) -> WorkspaceGraph:
        nodes = sorted(self._nodes.values(), key=lambda n: n.id)
        limitations = list(self._limitations)
        truncated = False
        excess = len(nodes) - self._max_nodes
        if excess > 0:
            cuttable = [n.id for n in nodes if n.kind in _TRUNCATABLE]
            dropped = set(cuttable[max(len(cuttable) - excess, 0):])
            nodes = [n for n in nodes if n.id not in dropped]
            truncated = True
            limitations.append(f"graph-truncated: {len(dropped)} evidence/artifact nodes "
                               f"dropped above {self._max_nodes} nodes")
        kept = {n.id for n in nodes}
        edges = sorted((e for e in self._edges if e.source in kept and e.target in kept),
                       key=_edge_key)
        return WorkspaceGraph(producer=PRODUCER, created_at=created_at or utc_now(),
                              plan_run=self._plan_run, nodes=nodes, edges=edges,
                              truncated=truncated, limitations=limitations)

    def _reject(self, limitation: str) -> None:
        self._limitations.setdefault(limitation, None)


def _edge_key(edge: GraphEdge) -> tuple[str, str, str, str, str, str]:
    return (edge.source, edge.kind, edge.target, edge.epistemic, edge.evidence,
            edge.rule or "")


def build_graph(plan_run: str, descriptor: WorkspaceDescriptor,
                records: Sequence[RegistryRecord], plan: ExecutionPlan | None,
                plan_sha256: str | None, outcomes: Sequence[NodeExecution], *,
                created_at: str | None = None,
                max_nodes: int = MAX_GRAPH_NODES) -> WorkspaceGraph:
    """Graph of an (executed) plan; inputs are visited in sorted order (8.5).

    Without a plan (an ``ambiguous``/``no_route`` decomposition) the graph holds only the
    workspace, its repositories and the providers with their capabilities.
    """
    builder = GraphBuilder(plan_run, max_nodes=max_nodes)
    repos = sorted(r.path for r in descriptor.repositories)
    recs = sorted(records, key=lambda r: r.entry.id)
    plan_nodes = sorted(plan.nodes, key=lambda n: n.id) if plan is not None else []
    executions = sorted(outcomes, key=lambda e: e.node.id)

    # Nodes first: an edge is only accepted between nodes already present.
    builder.add_node(GraphNode(id=WORKSPACE_NODE, kind="workspace"))
    for path in repos:
        builder.add_node(GraphNode(id=f"repository:{path}", kind="repository", label=path))
    for rec in recs:
        manifest = rec.manifest
        builder.add_node(GraphNode(id=f"provider:{rec.entry.id}", kind="provider",
                                   label=manifest.version if manifest else rec.state))
        for capability in manifest.capabilities if manifest else []:
            builder.add_node(GraphNode(id=f"capability:{rec.entry.id}/{capability.id}",
                                       kind="capability", label=capability.state))
    for node in plan_nodes:
        builder.add_node(GraphNode(id=f"plan_node:{node.id}", kind="plan_node",
                                   label=f"{node.provider}/{node.capability}:{node.action}"))
    for ex in executions:
        if ex.result is None:
            continue
        for item in ex.result.evidence:
            builder.add_node(GraphNode(id=f"evidence:{ex.node.id}/{item.id}",
                                       kind="evidence", label=item.epistemic))
        for artifact in ex.result.artifacts:
            builder.add_node(GraphNode(id=f"artifact:{ex.node.id}/{artifact.path}",
                                       kind="artifact", label=artifact.sha256))

    # Workspace relations, as evidenced by the descriptor.
    def repo_node(path: str) -> str:
        return WORKSPACE_NODE if path == "." and "." not in repos else f"repository:{path}"

    if "." in repos:
        builder.propose(source=WORKSPACE_NODE, target="repository:.", kind="contains",
                        epistemic="observed", evidence="./.git")
    for rel in sorted(descriptor.relations, key=lambda r: (r.source, r.kind, r.target)):
        builder.propose(source=repo_node(rel.source), target=repo_node(rel.target),
                        kind=rel.kind, epistemic=rel.epistemic, evidence=rel.evidence)

    for rec in recs:
        evidence = f"manifest:{rec.manifest_sha256}" if rec.manifest_sha256 else ""
        for capability in rec.manifest.capabilities if rec.manifest else []:
            builder.propose(source=f"provider:{rec.entry.id}",
                            target=f"capability:{rec.entry.id}/{capability.id}",
                            kind="declares", epistemic="explicit", evidence=evidence)

    plan_evidence = f"plan:{plan_sha256}" if plan_sha256 else ""
    for node in plan_nodes:
        me = f"plan_node:{node.id}"
        builder.propose(source=me, target=f"capability:{node.provider}/{node.capability}",
                        kind="uses", epistemic="explicit", evidence=plan_evidence)
        owners = {repository_of(descriptor, target) for target in node.targets}
        for owner in sorted(WORKSPACE_NODE if o is None else f"repository:{o}"
                            for o in owners):
            builder.propose(source=me, target=owner, kind="targets", epistemic="explicit",
                            evidence=plan_evidence)
        for dep in sorted(node.depends_on, key=lambda d: d.node):
            builder.propose(source=me, target=f"plan_node:{dep.node}", kind="depends_on",
                            epistemic=dep.epistemic, evidence=plan_evidence,
                            rule=dep.rule if dep.epistemic == "inferred" else None)

    for ex in executions:
        me = f"plan_node:{ex.node.id}"
        if ex.result is not None:
            sha = ex.outcome.result_sha256
            evidence = f"result:{sha}" if sha else ""
            for item in sorted(ex.result.evidence, key=lambda e: e.id):
                builder.propose(source=me, target=f"evidence:{ex.node.id}/{item.id}",
                                kind="produced", epistemic="observed", evidence=evidence)
            for artifact in sorted(ex.result.artifacts, key=lambda a: a.path):
                builder.propose(source=me, target=f"artifact:{ex.node.id}/{artifact.path}",
                                kind="produced", epistemic="observed", evidence=evidence)
        if ex.handoff is not None:
            # The handoff is already redacted: this is the hash of the persisted artifact.
            evidence = f"handoff:{sha256_of(to_dict(ex.handoff))}"
            for hitem in ex.handoff.items:
                if hitem.kind != "evidence":
                    continue
                builder.propose(source=f"evidence:{hitem.origin.node}/{hitem.id}", target=me,
                                kind="handed_off_to", epistemic="observed", evidence=evidence)

    return builder.build(created_at=created_at)
