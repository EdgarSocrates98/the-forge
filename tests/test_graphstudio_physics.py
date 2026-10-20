"""Physics evidence for the Graph Studio force loop (spec lf-0020).

The studio's inline ``<script>`` (``theforge/graphstudio.py``) is executed
headlessly under node by ``scripts/graphphysics_repro.py`` — real code, stubbed
DOM — over synthetic ForgeGraphView/v1 graphs.
"""

from __future__ import annotations

import json
import shutil
from typing import Any

import pytest
from scripts.graphphysics_repro import extract_script, run


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


def test_extracted_script_carries_the_force_loop():
    """The harness must be exercising the real studio code, not a stand-in.

    Guards the whole file: if the inline <script> is rewritten (lf-0021),
    these fingerprints disappear and the physics test is re-baselined
    consciously instead of silently testing a different program.
    """
    script = extract_script()
    # repulsion with squared-distance denominator (the r^-3 tail)
    assert "d=dx*dx+dy*dy+40" in script
    # spring with the quadratic-in-distance kick
    assert "f=(d-120)*0.02" in script and "a.vx+=dx/d*f*d/120" in script
    # integrator: gravity + 0.85 damping + Euler step, no alpha decay
    assert "a.vx-=a.x*0.001" in script and "a.x+=a.vx" in script


def test_star_topology_blows_up_coordinates(tmp_path):
    """lf-0020: documents P0 blow-up; lf-0021 flips this to assert finite.

    A 500-node star — one hub, 499 leaves — is the minimal deterministic
    reproduction: the crowd around the hub is flung out by the short-range
    repulsion, then the quadratic spring (kick ~ d(d-120)/6000) runs away
    and every coordinate reaches NaN/±Infinity in <10 ticks — the same
    "space out, then disappear" reported for ``graph ui`` at ~3.000 nodes.
    """
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not installed")
    fixture = tmp_path / "star500.json"
    fixture.write_text(json.dumps(_view(500, [(0, i) for i in range(1, 500)])))
    report = run(fixture, ticks=60, node=node, timeout=120)
    assert report["verdict"] == "REPRODUCED", report
    assert report["final"]["non_finite"] > 0 or report["final"]["max_abs_coord"] > 1e5


def test_chain_topology_is_the_stable_control(tmp_path):
    """Same node count, no hub: the loop settles — the defect is not the
    harness or any 500-node graph, it is hub concentration × the force law."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not installed")
    fixture = tmp_path / "chain500.json"
    fixture.write_text(json.dumps(_view(500, [(i, i + 1) for i in range(499)])))
    report = run(fixture, ticks=120, node=node, timeout=120)
    assert report["final"]["non_finite"] == 0
    assert report["final"]["max_abs_coord"] < 10_000
