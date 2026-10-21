"""GraphView adapters — real engines → ForgeGraphView/v1.

Each adapter maps its own engine's vocabulary onto the view contract and
declares only the capabilities the engine really has. ``federated_views``
collects views from sibling checkouts through each CLI's
``graph view --json`` (the uniform producer surface) — subprocess
isolation, no cross-imports.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

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


def _view_from_cli(
    checkout: Path, provider_id: str, *, timeout: int = 30
) -> tuple[ForgeGraphView | None, str]:
    """Run ``<cli> graph view --json`` in a sibling checkout via its cli_entry.

    Returns ``(view, "")`` on success or ``(None, reason)`` — the reason
    feeds federation ``notes[]`` so a refused/absent producer is named
    honestly instead of collapsing into one generic message.
    """
    import tomllib

    from theforge.specialists import load_agentic_manifest

    manifest = load_agentic_manifest(provider_id, checkout)
    entry = manifest.cli_entry if manifest is not None else ""
    if not entry:
        # minimal providers without forge.agentic.json may declare the
        # entry point directly on the identity file
        forge_json = checkout / "forge.json"
        if not forge_json.is_file():
            return None, "no forge.agentic.json/forge.json — checkout absent"
        try:
            text = forge_json.read_text(encoding="utf-8")
        except OSError:
            return None, "unreadable forge.json"
        # real forge.json files are JSON; the documented fallback also
        # accepts TOML (`cli_entry = "mod:fn"`) for minimal providers
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            try:
                data = tomllib.loads(text)
            except tomllib.TOMLDecodeError:
                return None, "unreadable forge.json"
        entry = data.get("cli_entry", "") if isinstance(data, dict) else ""
    if not entry or ":" not in entry:
        return None, "no cli_entry declared"
    module, _, fn = entry.partition(":")
    code_t = (
        "import sys; "
        f"sys.path.insert(0, {str(checkout)!r});"
        f"sys.path.insert(0, {str(checkout / 'src')!r});"
        "sys.argv=[{p!r}, 'graph', 'view'] + {flags!r};"
        f"from {module} import {fn} as _main; sys.exit(_main())"
    )
    proc = None
    # Prefer the checkout's own venv interpreter — a producer CLI can
    # only import its deps (typer etc.) in the interpreter it was
    # installed into. Fall back to ours for stdlib-only producers.
    candidates = [
        checkout / ".venv" / "Scripts" / "python.exe",  # Windows
        checkout / ".venv" / "bin" / "python",  # POSIX
    ]
    interpreter = next((str(p) for p in candidates if p.is_file()), sys.executable)
    # cwd=checkout, not inherited: producers resolve `graph view` without an
    # explicit root against "." — running them from OUR cwd made every sibling
    # read the caller's state dir and refuse "no index" even when its own
    # checkout carried a built graph. The checkout cwd is also what makes the
    # producer's *relative* state dir (`.<forge>/`, `.forge/`) resolve to the
    # workspace it was built in.
    for flags in (["--json"], []):
        argv = [interpreter, "-c", code_t.format(p=provider_id, flags=flags)]
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
                cwd=checkout,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if proc.returncode == 0 and proc.stdout.strip():
            break
    if proc is None:
        return None, "producer invocation failed (timeout/os error)"
    if proc.returncode != 0 or not proc.stdout.strip():
        # a fail-closed producer still names its refusal on stdout/stderr
        for stream in (proc.stdout, proc.stderr):
            try:
                doc = json.loads(stream.strip())
            except (json.JSONDecodeError, AttributeError):
                continue
            refusal = doc.get("refusal")
            if refusal:
                return None, f"refused {refusal}"
        # text-dialect refusals: `AF-CODE-NAME: detail` (apiforge family)
        for stream in (proc.stdout, proc.stderr):
            for line in stream.splitlines():
                m = re.match(r"^([A-Z]{2,6}-[A-Z0-9-]{3,}):", line.strip())
                if m:
                    return None, f"refused {m.group(1)}"
        tail = (proc.stderr or proc.stdout).strip().splitlines()
        detail = tail[-1].strip()[:120] if tail else ""
        reason = f"producer exited {proc.returncode}"
        return None, f"{reason} — {detail}" if detail else reason
    try:
        doc = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None, "producer output was not JSON"
    if doc.get("schema") != "forge/ForgeGraphView/v1":
        return None, "output is not forge/ForgeGraphView/v1"
    try:
        return ForgeGraphView.from_dict(doc), ""
    except (KeyError, TypeError):
        return None, "view document did not parse"


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
        view, reason = _view_from_cli(Path(v.checkout), v.lifecycle.provider, timeout=timeout)
        if view is None:
            notes.append(f"{v.lifecycle.provider}: {reason}")
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
            "its own provenance and namespace",
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
