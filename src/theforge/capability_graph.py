"""Capability graph builder and queries (cycle 3 wave B).

``build_capability_graph`` derives the graph from two evidence sources only:
provider manifests (declared structure and ``capability.relations``) and the
workspace descriptor (observed technologies). It knows nothing about any
provider's domain — every edge is either declared by a manifest or observed by
the descriptor, and the epistemic marker on each edge says which.

Node ids are ``"<kind>:<key>"``; capability keys are ``"<provider>/<capability>"``
(the ``matched_by`` convention of ``Technology``). Nodes and edges are sorted so
the artifact is deterministic and diffable.
"""

from collections.abc import Mapping, Sequence
from typing import Any, Final

from theforge.contracts import (
    CapabilityGraph,
    CapEdge,
    CapEdgeKind,
    CapNode,
    CapNodeKind,
    Producer,
    WorkspaceDescriptor,
)
from theforge.contracts.canonical import utc_now
from theforge.contracts.types import EdgeEpistemic
from theforge.meta import PRODUCER
from theforge.registry import RegistryRecord

# capability.relations fields -> edge kinds, in manifest field order. The first
# two point at artifact-type nodes; the rest at capability nodes.
_RELATION_EDGES: Final[tuple[tuple[str, CapEdgeKind], ...]] = (
    ("produces", "produces"),
    ("consumes", "consumes"),
    ("requires", "requires"),
    ("complements", "complements"),
    ("conflicts", "conflicts"),
    ("can_verify", "can_verify"),
    ("can_review", "can_review"),
)
_ARTIFACT_RELATIONS: Final = frozenset({"produces", "consumes"})


def _key(provider: str, capability: str) -> str:
    """The ``<provider>/<capability>`` key of capability nodes and refs."""
    return f"{provider}/{capability}"


def _cap_node_ids(graph: CapabilityGraph, ref: str) -> list[str]:
    """Node ids a ref denotes: ``p/c`` is exact; bare ``c`` matches every provider."""
    qualified = f"capability:{ref}"
    if "/" in ref:
        return [qualified] if qualified in {n.id for n in graph.nodes} else []
    return sorted(n.id for n in graph.nodes if n.kind == "capability" and n.id.endswith(f"/{ref}"))


def build_capability_graph(
    records: Mapping[str, RegistryRecord] | Sequence[RegistryRecord],
    descriptor: WorkspaceDescriptor | None = None,
    *,
    run_id: str = "",
    producer: Producer = PRODUCER,
    created_at: str | None = None,
) -> CapabilityGraph:
    """The declared+observed capability graph of the registry and workspace.

    Providers without a manifest (broken, unreachable at describe) contribute no
    nodes and are named in limitations. Relation targets absent from the registry
    keep their edge — declared intent is evidence — and are listed in
    limitations.
    """
    nodes: dict[str, CapNode] = {}
    edges: list[CapEdge] = []
    limitations: list[str] = []
    real_capabilities: set[str] = set()  # node ids backed by a manifest

    def node(kind: CapNodeKind, key: str, label: str = "") -> str:
        nid = f"{kind}:{key}"
        if nid not in nodes:
            nodes[nid] = CapNode(id=nid, kind=kind, label=label)
        return nid

    def edge(
        source: str, target: str, kind: CapEdgeKind, epistemic: EdgeEpistemic, evidence: str
    ) -> None:
        edges.append(
            CapEdge(source=source, target=target, kind=kind, epistemic=epistemic, evidence=evidence)
        )

    record_list = records.values() if isinstance(records, Mapping) else list(records)
    for record in record_list:
        manifest = record.manifest
        if manifest is None:
            limitations.append(f"provider {record.entry.id}: no manifest; absent from the graph")
            continue
        provider = node("provider", manifest.id, f"{manifest.id} {manifest.version}")
        for domain in sorted(manifest.domains):
            edge(
                provider,
                node("domain", domain),
                "in_domain",
                "explicit",
                f"manifest {manifest.id} domains",
            )
        for cap in manifest.capabilities:
            capability = node("capability", _key(manifest.id, cap.id), cap.description)
            real_capabilities.add(capability)
            edge(
                provider,
                capability,
                "has_capability",
                "explicit",
                f"manifest {manifest.id} capabilities",
            )
            for action in sorted(cap.actions):
                edge(
                    capability,
                    node("action", f"{manifest.id}/{cap.id}/{action}"),
                    "has_action",
                    "explicit",
                    f"capability {cap.id} actions",
                )
            for field_name, kind in _RELATION_EDGES:
                artifact = field_name in _ARTIFACT_RELATIONS
                for ref in sorted(getattr(cap.relations, field_name)):
                    target = node(
                        "artifact_type" if artifact else "capability",
                        ref if artifact else _resolve(ref, manifest.id),
                    )
                    edge(
                        capability,
                        target,
                        kind,
                        "explicit",
                        f"{manifest.id}/{cap.id} relations.{field_name}",
                    )

    if descriptor is None:
        limitations.append("no workspace descriptor: repository/technology nodes absent")
    else:
        for repo in descriptor.repositories:
            node("repository", repo.path)
        for tech in descriptor.technologies:
            technology = node("technology", f"{tech.repository}:{tech.name}", tech.name)
            repo_id = f"repository:{tech.repository}"
            if repo_id in nodes:
                edge(repo_id, technology, "uses_technology", "observed", tech.evidence)
            else:
                limitations.append(
                    f"technology {tech.name}: repository {tech.repository!r} not in the descriptor"
                )
            for matcher in tech.matched_by:  # "<provider>/<capability>"
                cap_id = f"capability:{matcher}"
                if cap_id in real_capabilities:
                    edge(
                        cap_id,
                        technology,
                        "relevant_to",
                        "observed",
                        f"signals matched {tech.name} ({tech.evidence})",
                    )
                else:
                    limitations.append(f"technology {tech.name}: matcher {matcher} not in registry")

    unresolved = sorted(
        {
            e.target
            for e in edges
            if e.target.startswith("capability:") and e.target not in real_capabilities
        }
    )
    if unresolved:
        limitations.append(
            "declared relation targets not in the registry: " + ", ".join(unresolved)
        )

    return CapabilityGraph(
        producer=producer,
        created_at=created_at or utc_now(),
        run_id=run_id,
        nodes=[nodes[k] for k in sorted(nodes)],
        edges=sorted(edges, key=lambda e: (e.source, e.kind, e.target)),
        limitations=limitations,
    )


def _resolve(ref: str, owner: str) -> str:
    """A declared relation ref to its capability key: ``p/c`` stays, bare ``c``
    is the declaring provider's own capability."""
    return ref if "/" in ref else _key(owner, ref)


# --- wave B queries (B5): planning-readable answers over the graph -------------


def _out(graph: CapabilityGraph, source: str, kind: CapEdgeKind) -> list[str]:
    return sorted(e.target for e in graph.edges if e.source == source and e.kind == kind)


def executors(graph: CapabilityGraph, ref: str) -> list[str]:
    """Provider ids that declare the capability (``p/c`` or bare ``c``)."""
    seen: set[str] = set()
    for node_id in _cap_node_ids(graph, ref):
        for e in graph.edges:
            if e.kind == "has_capability" and e.target == node_id:
                seen.add(e.source.removeprefix("provider:"))
    return sorted(seen)


def producers(graph: CapabilityGraph, artifact_type: str) -> list[str]:
    """Capability keys declaring they produce the artifact type."""
    return sorted(
        e.source.removeprefix("capability:")
        for e in graph.edges
        if e.kind == "produces" and e.target == f"artifact_type:{artifact_type}"
    )


def consumers(graph: CapabilityGraph, artifact_type: str) -> list[str]:
    """Capability keys declaring they consume the artifact type."""
    return sorted(
        e.source.removeprefix("capability:")
        for e in graph.edges
        if e.kind == "consumes" and e.target == f"artifact_type:{artifact_type}"
    )


def _related(graph: CapabilityGraph, ref: str, kind: CapEdgeKind, *, symmetric: bool) -> list[str]:
    """Capability keys linked to ``ref`` by ``kind``; symmetric kinds count both
    directions (complements/conflicts), directed kinds count sources only."""
    targets = {nid for nid in _cap_node_ids(graph, ref)}
    out: set[str] = set()
    for e in graph.edges:
        if e.kind != kind:
            continue
        if e.target in targets:
            out.add(e.source.removeprefix("capability:"))
        if symmetric and e.source in targets:
            out.add(e.target.removeprefix("capability:"))
    return sorted(out)


def verifiers(graph: CapabilityGraph, ref: str) -> list[str]:
    """Capability keys declaring ``can_verify`` on ``ref``."""
    return _related(graph, ref, "can_verify", symmetric=False)


def reviewers(graph: CapabilityGraph, ref: str) -> list[str]:
    """Capability keys declaring ``can_review`` on ``ref``."""
    return _related(graph, ref, "can_review", symmetric=False)


def complements(graph: CapabilityGraph, ref: str) -> list[str]:
    """Refs declared complementary to ``ref`` (either direction suggests)."""
    return _related(graph, ref, "complements", symmetric=True)


def conflicts(graph: CapabilityGraph, ref: str) -> list[str]:
    """Refs declared conflicting with ``ref`` (symmetric)."""
    return _related(graph, ref, "conflicts", symmetric=True)


def produces_consumes_order(
    graph: CapabilityGraph, refs: Sequence[str]
) -> tuple[list[str], list[str]]:
    """Deterministic topological order of ``refs`` over ``requires`` edges and
    produces→consumes chains (a producer runs before the consumer of its
    artifact type). Refs absent from the graph keep their input order at the
    end; cycle members are named in the second element, never dropped silently.
    """
    in_graph: dict[str, str] = {}  # ref -> node id
    missing: list[str] = []
    for ref in refs:
        ids = _cap_node_ids(graph, ref)
        if ids:
            in_graph[ref] = ids[0]
        else:
            missing.append(ref)

    nodes = set(in_graph.values())
    before: dict[str, set[str]] = {n: set() for n in nodes}  # node -> prerequisites
    produced_by: dict[str, set[str]] = {}  # artifact_type node -> producer nodes
    for e in graph.edges:
        if e.kind == "produces" and e.source in nodes:
            produced_by.setdefault(e.target, set()).add(e.source)
    for e in graph.edges:
        if e.source not in nodes:
            continue
        if e.kind == "requires" and e.target in nodes:
            before[e.source].add(e.target)
        elif e.kind == "consumes":
            before[e.source] |= produced_by.get(e.target, set()) - {e.source}

    order_ids: list[str] = []
    done: set[str] = set()
    ready = sorted(n for n in nodes if not before[n])
    while ready:
        nid = ready.pop(0)
        done.add(nid)
        order_ids.append(nid)
        for n in sorted(nodes):
            if nid in before[n]:
                before[n].discard(nid)
                if not before[n] and n not in done and n not in ready:
                    ready.append(n)
        ready.sort()

    # Two refs may name the same node; emit each ref at its node's position and
    # keep input order inside it.
    ordered = [ref for nid in order_ids for ref in refs if in_graph.get(ref) == nid]
    cyclic = nodes - done
    unresolved = sorted(ref for ref in refs if in_graph.get(ref) in cyclic)
    return ordered + missing, unresolved


def mesh_view(graph: CapabilityGraph) -> dict[str, Any]:
    """DOMAIN → {observe, engineer, verify} rows (cycle 3.1 Phase 83), derived
    only from declared relations — no provider-name or domain knowledge in the
    core: a capability producing an artifact type that another capability
    consumes is an *observer* of that type's namespace; the consumer is an
    *engineer*; a capability with ``can_verify`` on a mesh member is a
    *verifier* of every namespace that member produces or consumes.

    ``unplaced`` names ``can_verify`` edges whose target neither produces nor
    consumes a consumed artifact type — a real relation outside the mesh, never
    dropped silently.
    """
    produced: dict[str, set[str]] = {}  # artifact_type node -> producer caps
    consumed: dict[str, set[str]] = {}  # artifact_type node -> consumer caps
    verifies: list[tuple[str, str]] = []  # (verifier cap, target cap)
    declared_domains: dict[str, set[str]] = {}  # provider id -> manifest domains
    for edge in graph.edges:
        if edge.kind == "produces" and edge.target.startswith("artifact_type:"):
            produced.setdefault(edge.target, set()).add(edge.source)
        elif edge.kind == "consumes" and edge.target.startswith("artifact_type:"):
            consumed.setdefault(edge.target, set()).add(edge.source)
        elif edge.kind == "can_verify":
            verifies.append((edge.source, edge.target))
        elif edge.kind == "in_domain" and edge.target.startswith("domain:"):
            declared_domains.setdefault(edge.source.removeprefix("provider:"), set()).add(
                edge.target.removeprefix("domain:")
            )

    def strip(cap_node: str) -> str:
        return cap_node.removeprefix("capability:")

    def namespace(artifact_node: str) -> str:
        return artifact_node.removeprefix("artifact_type:").split(".", 1)[0]

    rows: dict[str, dict[str, set[str]]] = {}
    for art in sorted(set(produced) & set(consumed)):
        domain = namespace(art)
        row = rows.setdefault(domain, {"observe": set(), "engineer": set(), "verify": set()})
        row["observe"] |= {strip(c) for c in produced[art]}
        row["engineer"] |= {strip(c) for c in consumed[art]}
    mesh_domains = set(rows)
    # A verifier covers the mesh domains where its target's provider already
    # appears (observe/engineer), narrowed by the domains the verifier's own
    # manifest declares; a verifier without declared domains covers them all.
    member_providers: dict[str, set[str]] = {
        domain: {key.split("/", 1)[0] for caps in row.values() for key in caps}
        for domain, row in rows.items()
    }
    unplaced: list[str] = []
    for verifier, target in sorted(verifies):
        target_provider = strip(target).split("/", 1)[0]
        candidates = {d for d in mesh_domains if target_provider in member_providers[d]}
        declared = declared_domains.get(strip(verifier).split("/", 1)[0])
        placed = candidates & declared if declared else candidates
        if not placed:
            unplaced.append(f"{strip(verifier)} -> {strip(target)}")
        for domain in sorted(placed):
            rows[domain]["verify"].add(strip(verifier))
    return {
        "domains": [
            {
                "domain": domain,
                "observe": sorted(row["observe"]),
                "engineer": sorted(row["engineer"]),
                "verify": sorted(row["verify"]),
            }
            for domain, row in sorted(rows.items())
        ],
        "unplaced_verify": sorted(unplaced),
    }
