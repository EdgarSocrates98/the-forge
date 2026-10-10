"""GraphView adapters — real engines → ForgeGraphView/v1.

Each adapter maps its own engine's vocabulary onto the view contract and
declares only the capabilities the engine really has. ``federated_views``
collects views from sibling checkouts through each CLI's
``graph view --json`` (the uniform producer surface) — subprocess
isolation, no cross-imports.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from theforge.contracts.graphview import (
    ForgeGraphView,
    GraphEdgeView,
    GraphNodeView,
    new_descriptor,
)


def capability_view(*, root: Path) -> ForgeGraphView:
    """The Forge capability graph → a view (declared+observed edges)."""
    from theforge.capability_graph import build_capability_graph
    from theforge.context import scan_workspace
    from theforge.registry import Registry
    from theforge.state import find_forge_dir
    from theforge.workspace import describe_workspace

    registry = Registry(find_forge_dir(root))
    records = registry.cached_records()
    descriptor_ws = describe_workspace(root, records, scan_workspace(root, ["."]))
    graph = build_capability_graph(records, descriptor_ws)

    desc = new_descriptor(
        provider_id="the-forge",
        domain="capabilities",
        graph_id="capability-graph",
        capabilities=("node_inspect", "edge_inspect", "neighbors", "search", "filter", "export"),
        limitations=tuple(graph.limitations),
    )
    object.__setattr__(desc, "node_count", len(graph.nodes))
    object.__setattr__(desc, "edge_count", len(graph.edges))
    object.__setattr__(
        desc,
        "available_layers",
        tuple(sorted({n.kind for n in graph.nodes})),
    )
    nodes = tuple(
        GraphNodeView(
            id=n.id,
            kind=n.kind,
            label=n.label or n.id,
            domain="capabilities",
            source_provider="the-forge",
            epistemic_state="observed",
        )
        for n in graph.nodes
    )
    edges = tuple(
        GraphEdgeView(
            id=f"{e.source}|{e.kind}|{e.target}",
            source=e.source,
            target=e.target,
            kind=e.kind,
            provenance=e.epistemic,
            epistemic_state=e.epistemic,
            evidence_refs=(e.evidence,) if e.evidence else (),
            attributes=({"rule": e.rule} if e.rule else {}),
        )
        for e in graph.edges
    )
    return ForgeGraphView(descriptor=desc, nodes=nodes, edges=edges)


def _view_from_cli(checkout: Path, provider_id: str, *, timeout: int = 30) -> ForgeGraphView | None:
    """Run ``<cli> graph view --json`` in a sibling checkout via its cli_entry.

    Returns None when the sibling does not implement the producer or the
    invocation failed — federation degrades honestly, never fabricates.
    """
    import tomllib

    forge_json = checkout / "forge.json"
    if not forge_json.is_file():
        return None
    try:
        entry = tomllib.loads(forge_json.read_text(encoding="utf-8")).get("cli_entry", "")
    except (OSError, tomllib.TOMLDecodeError):
        return None
    if not entry or ":" not in entry:
        return None
    module, _, fn = entry.partition(":")
    code = (
        "import sys; "
        f"sys.path.insert(0, {str(checkout)!r});"
        f"sys.path.insert(0, {str(checkout / 'src')!r});"
        f"sys.argv=[{provider_id!r}, 'graph', 'view', '--json'];"
        f"from {module} import {fn} as _main; sys.exit(_main())"
    )
    argv = [sys.executable, "-c", code]
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    try:
        doc: dict[str, Any] = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    if doc.get("schema") != "forge/ForgeGraphView/v1":
        return None
    try:
        return ForgeGraphView.from_dict(doc)
    except (KeyError, TypeError):
        return None


def federated_views(
    *, workspace_root: Path, timeout: int = 30
) -> tuple[list[ForgeGraphView], list[str]]:
    """Collect views from every catalog specialist checkout + the-forge.

    Returns ``(views, notes)`` — notes honestly name providers that could
    not produce a view (missing checkout, no graph verb, stale engine).
    """
    from theforge import specialists

    views: list[ForgeGraphView] = []
    notes: list[str] = []
    views.append(capability_view(root=workspace_root))
    for v in specialists.collect(workspace_root=workspace_root, probe_cli=False):
        if not v.checkout:
            notes.append(f"{v.lifecycle.provider}: no checkout — skipped")
            continue
        view = _view_from_cli(Path(v.checkout), v.lifecycle.provider, timeout=timeout)
        if view is None:
            notes.append(
                f"{v.lifecycle.provider}: no ForgeGraphView producer "
                "(graph view unavailable or failed)"
            )
            continue
        views.append(view)
    return views, notes


def federated_merge(views: list[ForgeGraphView]) -> ForgeGraphView:
    """Merge views into one federated view, namespaced by provider.

    Node/edge ids gain a ``<provider>:`` prefix so identically-named
    entities across forges never silently unify (§3.2). Cross-forge
    relations are NOT inferred — only native edges are shown.
    """
    nodes: list[GraphNodeView] = []
    edges: list[GraphEdgeView] = []
    for view in views:
        pid = view.descriptor.provider_id
        for n in view.nodes:
            nodes.append(
                GraphNodeView(
                    id=f"{pid}:{n.id}",
                    kind=n.kind,
                    label=n.label,
                    domain=n.domain,
                    source_provider=pid,
                    attributes={**n.attributes, "provider_node_id": n.id},
                    epistemic_state=n.epistemic_state,
                    evidence_refs=n.evidence_refs,
                    snapshot_ref=n.snapshot_ref,
                )
            )
        for e in view.edges:
            edges.append(
                GraphEdgeView(
                    id=f"{pid}:{e.id}",
                    source=f"{pid}:{e.source}",
                    target=f"{pid}:{e.target}",
                    kind=e.kind,
                    provenance=f"{pid}/{e.provenance}",
                    epistemic_state=e.epistemic_state,
                    evidence_refs=e.evidence_refs,
                    confidence=e.confidence,
                    temporal=e.temporal,
                    attributes=e.attributes,
                )
            )
    desc = new_descriptor(
        provider_id="the-forge",
        domain="federated",
        graph_id="federated",
        capabilities=("node_inspect", "edge_inspect", "search", "filter", "export"),
        limitations=(
            "cross-forge relations are not inferred; each subgraph keeps "
            "its own provenance and namespace"
        ),
    )
    object.__setattr__(desc, "node_count", len(nodes))
    object.__setattr__(desc, "edge_count", len(edges))
    object.__setattr__(
        desc,
        "available_layers",
        tuple(sorted({n.domain for n in nodes if n.domain})),
    )
    return ForgeGraphView(descriptor=desc, nodes=tuple(nodes), edges=tuple(edges))
