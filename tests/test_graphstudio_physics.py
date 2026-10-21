"""Physics evidence for the Graph Studio force loop (specs lf-0020/lf-0021).

The studio's inline ``<script>`` (``theforge/graphstudio.py``) is executed
headlessly under node by ``scripts/graphphysics_repro.py`` — real code, stubbed
DOM — over synthetic ForgeGraphView/v1 graphs.

lf-0020 pinned the divergent signature (quadratic spring + no finite guard);
lf-0021 fixed the force law, bounded velocities, added Barnes–Hut for large
graphs, annealing (alpha decay), a RAF generation counter, fit-to-view and a
visible error surface — and this file now asserts the FIXED behavior.
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
    run,
    run_harness,
)


def _view(n: int, edges: list[tuple[int, int]]) -> dict[str, Any]:
    """Minimal ForgeGraphView/v1 doc — only ``nodes``/``edges`` drive forces."""
    return {
        "schema": "forge/ForgeGraphView/v1",
        "descriptor": {
            "graph_id": "test/synthetic",
            "provider_id": "test",
            "domain": "synthetic",
            "node_count": n,
            "edge_count": len(edges),
        },
        "nodes": [{"id": f"n{i}", "kind": "module", "label": f"node-{i}"} for i in range(n)],
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


def _run_driver(tmp_path, doc: dict[str, Any], driver: str, *, ticks: int = 400):
    """Compose preamble + verbatim studio script + a custom driver, run it."""
    fixture = tmp_path / "graph.json"
    fixture.write_text(json.dumps(doc))
    harness = build_harness(
        extract_script(),
        ticks=ticks,
        sample_every=25,
        viewport=VIEWPORT_HALF_PX,
        driver=driver,
    )
    return run_harness(fixture, harness, node=_node(), timeout=180)


def test_extracted_script_carries_the_fixed_force_loop():
    """Fingerprint of the FIXED implementation — a regression to the lf-0020
    force law (quadratic kick, no guards) fails here, not silently later."""
    script = extract_script()
    # repulsion along the UNIT vector, capped; Barnes–Hut path for large N
    assert "REP/(dist*dist+40),FCAP" in script
    assert "function repulseBH" in script and "THETA" in script
    # linear spring — the quadratic `*d/120` kick must not come back
    assert "a.vx+=dx/d*f" in script and "f*d/120" not in script
    assert "f=(d-LINK_D)*SPRING_K*alpha" in script
    # integrator: damping + speed clamp + finite guard
    assert "SPMAX" in script and "every(Number.isFinite)" in script
    # annealing + RAF lifecycle (generation counter + real cancel)
    assert "alpha*=ALPHA_DECAY" in script and "ALPHA_MIN" in script
    assert "++gen" in script and "cancelAnimationFrame" in script
    # camera: fit-to-view on load/Escape/resize + zoom clamp
    assert "function fitToView" in script and "window.onresize" in script
    assert "SMIN" in script and "SMAX" in script
    # one byId index per load, used by draw()/pick()
    assert "G.byId=new Map" in script and "G.byId.get" in script


def test_star_topology_converges_finite(tmp_path):
    """lf-0021 flip: the 500-node star that diverged to NaN in <10 ticks must
    now stay finite, bounded, and actually settle (RAF stops on its own)."""
    fixture = tmp_path / "star500.json"
    fixture.write_text(json.dumps(_view(500, [(0, i) for i in range(1, 500)])))
    report = run(fixture, ticks=400, node=_node(), timeout=180)
    assert report["verdict"] == "STABLE", report
    assert report["final"]["non_finite"] == 0
    assert report["final"]["max_abs_coord"] < 10_000
    assert report["settled"] is True  # alpha decayed / motion died — loop exited
    assert report["raf_starved"] is False
    assert report["resets"] == 0
    # exact O(N²) path (N ≤ BH_N) is still fast at 500 nodes
    assert report["tick_ms"]["mean"] < 16.7


def test_high_degree_hubs_converge_finite(tmp_path):
    """Hubs were the other proven blow-up; at N > BH_N the Barnes–Hut path
    must keep every coordinate finite and let the sim settle."""
    # 10 hubs × 119 leaves + a hub chain — mirrors the codeintel shape (a file
    # containing hundreds of symbols).
    edges = [(i % 10, i) for i in range(10, 1200)] + [(i, i + 1) for i in range(9)]
    fixture = tmp_path / "hubs1200.json"
    fixture.write_text(json.dumps(_view(1200, edges)))
    report = run(fixture, ticks=400, node=_node(), timeout=180)
    assert report["verdict"] == "STABLE", report
    assert report["final"]["non_finite"] == 0
    assert report["final"]["max_abs_coord"] < 10_000
    assert report["settled"] is True
    assert report["resets"] == 0


def test_chain_topology_is_the_stable_control(tmp_path):
    """The negative control: no hub, and the loop was stable even pre-fix —
    it must stay stable now."""
    fixture = tmp_path / "chain500.json"
    fixture.write_text(json.dumps(_view(500, [(i, i + 1) for i in range(499)])))
    report = run(fixture, ticks=400, node=_node(), timeout=180)
    assert report["final"]["non_finite"] == 0
    assert report["final"]["max_abs_coord"] < 10_000
    assert report["settled"] is True


# --- lifecycle / guards: custom drivers over the same verbatim script --------

# After loadGraphs() drains, a second loadGraph() must leave exactly ONE live
# RAF chain: the pending stale callback is cancelled and, if invoked anyway,
# the generation check makes it a no-op (it must not reschedule).
_DRIVER_TWO_LOADS = """\
try {
  const __deadline = Date.now() + 15000;
  while (!G.nodes.length) {
    if (Date.now() > __deadline) throw new Error('fixture graph never loaded');
    await new Promise((r) => setTimeout(r, 1));
  }
  const g1 = gen;
  const staleCb = __raf;               // pending continuation of chain g1
  await loadGraph(__doc.descriptor.graph_id);
  const g2 = gen;
  const liveCb = __raf;
  const rafAfterLoad = __rafCount;
  staleCb();                           // stale chain: must not reschedule
  const staleRescheduled = __rafCount > rafAfterLoad;
  const slotIntact = __raf === liveCb; // live gen-2 callback still queued
  let maxNew = 0, steps = 0;
  while (steps < 40 && __raf) {
    const cb = __raf; __raf = null;
    const before = __rafCount; cb();
    maxNew = Math.max(maxNew, __rafCount - before);
    steps++;
  }
  process.stdout.write(JSON.stringify({
    gen1: g1, gen2: g2, staleRescheduled, slotIntact,
    maxNewPerStep: maxNew, steps,
  }) + '\\n');
} catch (e) {
  process.stdout.write(JSON.stringify({error: String(e && e.stack || e)}) + '\\n');
  process.exitCode = 1;
}
"""


def test_second_loadgraph_leaves_one_raf_chain(tmp_path):
    """Pre-fix, every ``loadGraph`` stacked another RAF chain on top — the
    effective force multiplied per frame. Now the generation counter +
    cancelAnimationFrame retire the old chain exactly once."""
    report = _run_driver(tmp_path, _view(60, [(i, i + 1) for i in range(59)]), _DRIVER_TWO_LOADS)
    assert "error" not in report, report
    assert report["gen2"] == report["gen1"] + 1  # generation bumped per load
    assert report["staleRescheduled"] is False  # stale cb never re-arms
    assert report["slotIntact"] is True  # pending cb is still the live chain's
    assert report["maxNewPerStep"] <= 1  # one RAF request per frame, not 2+


# Guards: byId index, fitToView, isFinite reset, and the visible error path.
_DRIVER_GUARDS = """\
try {
  const __deadline = Date.now() + 15000;
  while (!G.nodes.length) {
    if (Date.now() > __deadline) throw new Error('fixture graph never loaded');
    await new Promise((r) => setTimeout(r, 1));
  }
  const out = {};
  out.byIdMap = G.byId instanceof Map && G.byId.size === G.nodes.length
    && G.byId.get(G.nodes[0].id) === G.nodes[0];
  out.fitToViewFn = typeof fitToView === 'function';
  fitToView();
  const r = cv.getBoundingClientRect();
  out.allInside = G.nodes.every((n) => {
    const p = toS(n.x, n.y);
    return p[0] >= 0 && p[0] <= r.width && p[1] >= 0 && p[1] <= r.height;
  });
  out.zoomClamped = view.s >= SMIN && view.s <= SMAX;
  // poison one node — the next tick must reset it and COUNT the reset
  G.nodes[0].x = NaN;
  const before = resets;
  tick(gen);
  out.poisonFixed = Number.isFinite(G.nodes[0].x) && Number.isFinite(G.nodes[0].y);
  out.resetCounted = resets === before + 1;
  out.statsMentionResets = /resets/.test(document.getElementById('stats').textContent);
  // break the sim — a thrown tick must stop the loop and surface a banner
  G.byId = null;
  tick(gen);
  out.loopStopped = running === false;
  out.banner = document.getElementById('err').style.display === 'block'
    && /layout stopped/.test(document.getElementById('err').textContent);
  process.stdout.write(JSON.stringify(out) + '\\n');
} catch (e) {
  process.stdout.write(JSON.stringify({error: String(e && e.stack || e)}) + '\\n');
  process.exitCode = 1;
}
"""


def test_studio_guards_byid_fit_reset_and_error_banner(tmp_path):
    """One headless run over the real script asserts the four lf-0021 guards:
    the per-load ``byId`` map, ``fitToView`` coverage, the ``isFinite`` reset
    counter, and the tick exception → visible banner (never a blank canvas)."""
    report = _run_driver(tmp_path, _view(60, [(i, i + 1) for i in range(59)]), _DRIVER_GUARDS)
    assert "error" not in report, report
    assert report["byIdMap"] is True
    assert report["fitToViewFn"] is True
    assert report["allInside"] is True  # every node lands inside the viewport
    assert report["zoomClamped"] is True
    assert report["poisonFixed"] is True  # NaN node came back finite
    assert report["resetCounted"] is True  # ...and the reset was counted
    assert report["statsMentionResets"] is True  # ...and surfaced in the footer
    assert report["loopStopped"] is True  # exception disarmed the loop
    assert report["banner"] is True  # ...with a visible error, not white screen
