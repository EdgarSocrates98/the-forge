"""lf-0022 scale-mode evidence for Graph Studio (overview / explore / full).

Same harness as ``test_graphstudio_physics.py``: the verbatim inline
``<script>`` from ``theforge.graphstudio.STUDIO_HTML`` runs under node with
stubbed DOM/RAF, and each driver pokes the real mode machinery —
``setMode``/``computeClusters``/``exploreSet``/``runSearch``/``inspect``/
``shortestPath``/``draw`` — never a re-implementation of it.
"""

from __future__ import annotations

import json
import shutil
from typing import Any

import pytest
from scripts.graphphysics_repro import (
    VIEWPORT_HALF_PX,
    build_harness,
    extract_script,
    run_harness,
)


def _view(n: int, edges: list[tuple[int, int]], kinds: list[str] | None = None) -> dict[str, Any]:
    """ForgeGraphView/v1 doc; ``kinds`` assigns per-node kind round-robin."""
    return {
        "schema": "forge/ForgeGraphView/v1",
        "descriptor": {
            "graph_id": "test/synthetic",
            "provider_id": "test",
            "domain": "synthetic",
            "node_count": n,
            "edge_count": len(edges),
        },
        "nodes": [
            {"id": f"n{i}", "kind": (kinds[i] if kinds else "module"), "label": f"node-{i}"}
            for i in range(n)
        ],
        "edges": [
            {"id": f"e{i}", "source": f"n{s}", "target": f"n{t}", "kind": "imports"}
            for i, (s, t) in enumerate(edges)
        ],
    }


def _node() -> str:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not installed")
    return node


def _run_driver(
    tmp_path, doc: dict[str, Any], driver: str, *, timeout: int = 240
) -> dict[str, Any]:
    fixture = tmp_path / "graph.json"
    fixture.write_text(json.dumps(doc))
    harness = build_harness(
        extract_script(),
        ticks=400,
        sample_every=25,
        viewport=VIEWPORT_HALF_PX,
        driver=driver,
    )
    return run_harness(fixture, harness, node=_node(), timeout=timeout)


_WAIT = """\
  const __deadline = Date.now() + 15000;
  while (!G.nodes.length) {
    if (Date.now() > __deadline) throw new Error('fixture graph never loaded');
    await new Promise((r) => setTimeout(r, 1));
  }
"""

_TAIL = """\
} catch (e) {
  process.stdout.write(JSON.stringify({error: String(e && e.stack || e)}) + '\\n');
  process.exitCode = 1;
}
"""


def test_extracted_script_carries_the_lf0022_surface():
    """Static fingerprint — every lf-0022 feature family must be present in the
    shipped script, so a partial revert fails loudly here."""
    script = extract_script()
    for token in (
        "setMode",  # three persisted modes
        "computeClusters",  # overview rollup
        "exploreSet",  # bounded progressive expansion
        "FULL_BUDGET",  # explicit renderable-element budget
        "Truncated — showing",  # honest notice, never silent
        "function srand",  # seeded layout — no unseeded Math.random
        "edgeStride",  # edge decimation + "drawn of eligible" footer
        "function inspect",  # inspector
        "shortestPath",  # bounded BFS
        "function blast(",  # bounded blast/subtree
        "drawMini",  # minimap
        "renderCrumbs",  # breadcrumbs
        "localStorage",  # persisted mode/depth/cap/lod
        "SIM_MS",  # time-sliced force work
    ):
        assert token in script, f"missing lf-0022 surface token: {token}"
    assert "Math.random()" not in script  # no unseeded randomness


_DRIVER_CLUSTERS = (
    """\
try {
"""
    + _WAIT
    + """\
  setMode('overview');
  const rendered = R.nodes.length === clusters.filter((c) => c.vis).length
    && R.nodes.every((n) => n.cluster);
  const sig = () => clusters.map((c) => c.id + '=' + c.members.join(',')).join(';');
  const s1 = sig(), count1 = clusters.length;
  // recompute from scratch — same input must give the same clusters
  clusters = null; clusterMap = null; aggEdges = [];
  computeClusters();
  const s2 = sig();
  const cids = new Set(clusters.map((c) => c.id));
  const aggOk = aggEdges.every((e) => cids.has(e.source) && cids.has(e.target));
  const c0 = clusters.slice().sort((a, b) => b.size - a.size)[0];
  drill(c0);
  const members = new Set(c0.members);
  process.stdout.write(JSON.stringify({
    deterministic: s1 === s2,
    count: count1,
    coverage: clusterMap.size === G.nodes.length,
    aggOk,
    rendered,
    modeAfter: mode,
    crumbs: crumbs.map((c) => c.label),
    seedsOk: explore.seeds.size > 0 && [...explore.seeds].every((id) => members.has(id)),
    exploreNodesReal: R.nodes.every((n) => !n.cluster),
  }) + '\\n');
"""
    + _TAIL
)


def test_overview_clusters_deterministic_and_drill_seeds_explore(tmp_path):
    """Overview rollup must be byte-deterministic (run twice → same assignment),
    cover every node exactly once, aggregate inter-cluster edges, and drilling a
    cluster must seed Explore inside that cluster with an overview breadcrumb."""
    # three dense communities of 60 joined by single links + 40 isolates
    edges: list[tuple[int, int]] = []
    for base in (0, 60, 120):
        edges += [(base + i, base + (i + 1) % 60) for i in range(60)]
        edges += [(base, base + i) for i in range(1, 20)]
    edges += [(0, 60), (60, 120)]
    doc = _view(220, edges, kinds=(["file", "module", "class"] * 74)[:220])
    report = _run_driver(tmp_path, doc, _DRIVER_CLUSTERS)
    assert "error" not in report, report
    assert report["deterministic"] is True  # same input → same clusters
    assert report["coverage"] is True  # every node assigned exactly once
    assert report["count"] >= 3  # the three dense communities survive
    assert report["count"] <= 250  # CLUST_MAX respected
    assert report["aggOk"] is True  # aggregate edges only join cluster ids
    assert report["rendered"] is True  # overview renders clusters, not members
    assert report["modeAfter"] == "explore"  # drill switches mode
    assert report["crumbs"][0] == "overview"  # breadcrumb keeps the origin
    assert report["seedsOk"] is True  # explore seeds ⊆ drilled cluster members
    assert report["exploreNodesReal"] is True  # explore shows real nodes


_DRIVER_EXPLORE = (
    """\
try {
"""
    + _WAIT
    + """\
  explore.seeds = new Set(['n30']); explore.depth = 2; explore.cap = 2;
  explore.extra = new Set();
  setMode('explore');
  const d2c2 = R.nodes.map((n) => n.id).sort();
  explore.cap = 1; buildRender();
  const d2c1 = R.nodes.map((n) => n.id).sort();
  explore.cap = 2; explore.depth = 1; buildRender();
  const d1c2 = R.nodes.map((n) => n.id).sort();
  // node-driven expansion beyond the cap is still bounded by `cap`
  explore.depth = 1; explore.cap = 2; expandNode('n0');
  const xtra = R.nodes.map((n) => n.id).sort();
  process.stdout.write(JSON.stringify({d2c2, d2c1, d1c2, xtra, mode}) + '\\n');
"""
    + _TAIL
)


def test_explore_honors_depth_and_degree_caps(tmp_path):
    """On a deterministic chain the render set is exactly the capped BFS:
    depth 2 + cap 2 → seed ±2 hops (5 nodes); cap 1 → the leftmost arm only;
    depth 1 → seed + first `cap` sorted neighbours. Adjacency order is the
    documented (-degree, id) sort, so the expectation is exact."""
    doc = _view(60, [(i, i + 1) for i in range(59)])
    report = _run_driver(tmp_path, doc, _DRIVER_EXPLORE)
    assert "error" not in report, report
    assert report["mode"] == "explore"
    assert report["d2c2"] == ["n28", "n29", "n30", "n31", "n32"]  # depth 2, cap 2
    assert report["d2c1"] == ["n28", "n29", "n30"]  # cap 1 → n29 arm only
    assert report["d1c2"] == ["n29", "n30", "n31"]  # depth 1 → seed + 2 nbrs
    assert len(report["xtra"]) <= 60  # expansion stays bounded


_DRIVER_TRUNC = (
    """\
try {
"""
    + _WAIT
    + """\
  FULL_BUDGET = 150;
  setMode('full');
  process.stdout.write(JSON.stringify({
    notice: document.getElementById('notice').textContent,
    display: document.getElementById('notice').style.display,
    shown: R.nodes.length,
    total: G.nodes.length,
    stats: document.getElementById('stats').textContent,
  }) + '\\n');
"""
    + _TAIL
)


def test_full_mode_shows_truncation_notice_over_budget(tmp_path):
    """Over the renderable-element budget the studio must SAY so — a visible
    ``Truncated …`` banner plus the footer count — never silently drop data."""
    doc = _view(500, [(i, i + 1) for i in range(499)])
    report = _run_driver(tmp_path, doc, _DRIVER_TRUNC)
    assert "error" not in report, report
    assert report["shown"] == 150
    assert report["total"] == 500
    assert "Truncated" in report["notice"]
    assert "150/500" in report["notice"]
    assert report["display"] == "block"  # visible, not just populated
    assert "150 nodes" in report["stats"]


_DRIVER_SEARCH = (
    """\
try {
"""
    + _WAIT
    + """\
  setMode('full');
  document.getElementById('q').value = 'node-1';
  runSearch();
  const hits = searchHits ? [...searchHits] : [];
  const prov = document.getElementById('prov').textContent;
  const allMatch = hits.every((id) => {
    const n = G.byId.get(id);
    return n && ((n.label || '') + ' ' + n.id).includes('node-1');
  });
  const stats = document.getElementById('stats').textContent;
  document.getElementById('q').value = '';
  runSearch();
  process.stdout.write(JSON.stringify({
    hits: hits.length, allMatch, prov, stats, cleared: searchHits === null,
  }) + '\\n');
"""
    + _TAIL
)


def test_search_finds_highlights_and_reports_counts(tmp_path):
    """Enter-on-search filters the render set to matches, highlights every hit
    and reports ``shown of total``; clearing the query restores everything."""
    doc = _view(200, [(i, i + 1) for i in range(199)])
    report = _run_driver(tmp_path, doc, _DRIVER_SEARCH)
    assert "error" not in report, report
    # 'node-1' matches node-1, node-10..19, node-100..199 → 111
    assert report["hits"] == 111
    assert report["allMatch"] is True
    assert "111 shown of 111 matches" in report["prov"]
    assert "111 hits" in report["stats"]  # hit count also in the footer
    assert report["cleared"] is True


_DRIVER_INSPECT = (
    """\
try {
"""
    + _WAIT
    + """\
  setMode('full');
  sel = G.byId.get('n0'); inspect();
  const node = document.getElementById('ibody').innerHTML;
  sel = G.edges[0]; inspect();
  const edge = document.getElementById('ibody').innerHTML;
  sel = null; inspect();
  const blank = document.getElementById('ibody').innerHTML;
  process.stdout.write(JSON.stringify({node, edge, blank}) + '\\n');
"""
    + _TAIL
)


def test_inspector_renders_node_and_edge_detail(tmp_path):
    """Click-select a hub: id, kind, degree and the neighbour list appear, the
    list is capped at 50 with a ``more`` affordance, and an edge shows its
    endpoints/kind. Deselect returns to the placeholder."""
    doc = _view(200, [(0, i) for i in range(1, 200)])  # star — n0 has 199 nbrs
    report = _run_driver(tmp_path, doc, _DRIVER_INSPECT)
    assert "error" not in report, report
    node = report["node"]
    assert "n0" in node
    assert "module" in node  # kind pill
    assert "deg 199" in node
    assert "Neighbors (199)" in node
    assert "more +50" in node  # capped list has a visible affordance
    assert "Attributes" in node
    edge = report["edge"]
    assert "n0 → n1" in edge  # endpoints
    assert "imports" in edge  # kind
    assert "Attributes" in edge
    assert "select a node or edge" in report["blank"]


_DRIVER_PATH = (
    """\
try {
"""
    + _WAIT
    + """\
  const p = shortestPath('n0', 'n5');
  const far = shortestPath('n0', 'n59'); // 59 hops — beyond PATH_MAX_DEPTH
  pathA = 'n0'; pathB = 'n5'; runPath();
  const prov = document.getElementById('prov').textContent;
  const hi = pathHi ? pathHi.size : -1, he = pathEdges ? pathEdges.size : -1;
  pathA = 'n0'; pathB = 'n59'; runPath();
  const provMiss = document.getElementById('prov').textContent;
  process.stdout.write(JSON.stringify({
    path: p, farNull: far === null, hi, he, prov, provMiss,
    noPathHighlight: pathHi === null,
  }) + '\\n');
"""
    + _TAIL
)


def test_bfs_shortest_path_is_bounded_and_highlights(tmp_path):
    """BFS finds the 6-node chain path and highlights nodes+edges; a request
    deeper than PATH_MAX_DEPTH reports the bound instead of hanging."""
    doc = _view(60, [(i, i + 1) for i in range(59)])
    report = _run_driver(tmp_path, doc, _DRIVER_PATH)
    assert "error" not in report, report
    assert report["path"] == ["n0", "n1", "n2", "n3", "n4", "n5"]
    assert report["farNull"] is True  # bounded miss → null, not a hang
    assert report["hi"] == 6 and report["he"] == 5  # path + edges highlighted
    assert "path n0 → n5: 6 nodes" in report["prov"]
    assert "no path" in report["provMiss"]


_DRIVER_LABELS = (
    """\
try {
"""
    + _WAIT
    + """\
  setMode('full');
  view = {x: 0, y: 0, s: 1}; draw();
  const zoomed = drawMeta.labels;
  view.s = 0.02; draw();
  const zoomedOut = drawMeta.labels;
  view.s = 0.02; lod = 'coarse'; draw();
  const coarse = drawMeta.edges;
  lod = 'auto'; draw();
  const auto = drawMeta.edges;
  process.stdout.write(JSON.stringify({
    zoomed, zoomedOut, coarse, auto, eligible: drawMeta.edgesOk,
    nodes: R.nodes.length,
  }) + '\\n');
"""
    + _TAIL
)


def test_labels_virtualize_when_zoomed_out(tmp_path):
    """Past LABEL_MAX and zoomed out, node labels must not be painted (the
    virtualization that keeps 10k-node frames cheap); zooming back in
    restores them."""
    doc = _view(400, [(i, i + 1) for i in range(399)])
    report = _run_driver(tmp_path, doc, _DRIVER_LABELS)
    assert "error" not in report, report
    assert report["nodes"] == 400
    assert report["zoomed"] == 400  # zoomed-in: every node labelled
    assert report["zoomedOut"] < 50  # zoomed-out: labels virtualized away


def test_sliced_layout_still_settles(tmp_path):
    """The time-sliced force loop (SIM_MS deadline per RAF) must still run the
    sim to settlement — just spread over more frames than logical ticks."""
    doc = _view(550, [(i, i + 1) for i in range(549)])
    driver = (
        """\
try {
"""
        + _WAIT
        + """\
  SIM_MS = -1; // expired deadline forces slicing on any timer resolution
               // (Windows Date.now() is ~15.6ms — SIM_MS=1 may never trip)
  let ran = 0;
  while (__raf && !settled && ran < 60000) {
    const cb = __raf; __raf = null; cb(); ran++;
  }
  let nf = 0;
  for (const a of G.nodes) if (![a.x, a.y, a.vx, a.vy].every(Number.isFinite)) nf++;
  process.stdout.write(JSON.stringify({
    settled, lticks, raf: ran, sliced: ran > lticks, non_finite: nf,
  }) + '\\n');
"""
        + _TAIL
    )
    report = _run_driver(tmp_path, doc, driver, timeout=300)
    assert "error" not in report, report
    assert report["settled"] is True  # converged, not abandoned mid-slice
    assert report["non_finite"] == 0
    assert report["lticks"] >= 1
    assert report["sliced"] is True  # frames really did span multiple ticks
