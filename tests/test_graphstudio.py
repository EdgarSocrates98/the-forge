"""Graph Studio tests: ForgeGraphView/v1, adapters, local server, federation."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from theforge.contracts.graphview import (
    ForgeGraphView,
    GraphEdgeView,
    GraphNodeView,
    new_descriptor,
)

# -- contract -----------------------------------------------------------------


def test_descriptor_schema_and_capabilities_filtered():
    d = new_descriptor(
        provider_id="p",
        domain="d",
        capabilities=("neighbors", "teleport"),
    )
    assert d.graph_schema == "forge/GraphDescriptor/v1"
    assert d.capabilities == ("neighbors",)  # unreal capability dropped
    assert d.generated_at


def test_node_epistemic_translation_and_fallback():
    n = GraphNodeView(id="x", kind="k", label="x", epistemic_state="explicit")
    assert n.epistemic_state == "declared"  # explicit → declared (reversible map)
    n2 = GraphNodeView(id="y", kind="k", label="y", epistemic_state="banana")
    assert n2.epistemic_state == "unknown"  # never upgraded


def test_edge_view_roundtrip():
    e = GraphEdgeView(
        id="e1",
        source="a",
        target="b",
        kind="depends_on",
        provenance="static",
        epistemic_state="inferred",
        evidence_refs=("f-1",),
        confidence=0.5,
        temporal={"from": "t0"},
    )
    d = e.to_dict()
    assert d["confidence"] == 0.5 and d["temporal"]["from"] == "t0"
    view = ForgeGraphView(
        descriptor=new_descriptor(provider_id="p", domain="d", graph_id="g"),
        nodes=(GraphNodeView(id="a", kind="k", label="a"),),
        edges=(e,),
    )
    doc = view.to_dict()
    assert doc["schema"] == "forge/ForgeGraphView/v1"
    back = ForgeGraphView.from_dict(doc)
    assert back.edges[0].evidence_refs == ("f-1",)
    assert back.nodes[0].id == "a"


# -- the-forge adapter ---------------------------------------------------------


def test_capability_view_real(tmp_path):
    from theforge.graphview import capability_view

    view = capability_view(root=Path("."))
    doc = view.to_dict()
    assert doc["descriptor"]["provider_id"] == "the-forge"
    assert doc["descriptor"]["node_count"] == len(doc["nodes"])
    for e in doc["edges"]:
        assert e["epistemic_state"] in (
            "observed",
            "declared",
            "inferred",
            "unknown",
        )
        assert e["provenance"]  # raw engine term preserved


def test_federated_merge_namespaces_nodes():
    def mk(pid: str, nid: str) -> ForgeGraphView:
        return ForgeGraphView(
            descriptor=new_descriptor(provider_id=pid, domain="d", graph_id=f"{pid}/g"),
            nodes=(GraphNodeView(id=nid, kind="k", label=nid, source_provider=pid),),
            edges=(
                GraphEdgeView(
                    id="e", source=nid, target=nid, kind="self", provenance="declared"
                ),
            ),
        )

    from theforge.graphview import federated_merge

    merged = federated_merge([mk("a", "x"), mk("b", "x")])
    ids = {n.id for n in merged.nodes}
    assert ids == {"a:x", "b:x"}  # same-name entities never unify
    assert merged.edges[0].provenance == "a/declared"


# -- server --------------------------------------------------------------------


def _serve(views):
    from theforge.graphstudio import _handler

    by_id = {v["descriptor"]["graph_id"]: v for v in views}
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _handler(by_id))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


@pytest.fixture
def studio():
    view = ForgeGraphView(
        descriptor=new_descriptor(provider_id="p", domain="d", graph_id="g1"),
        nodes=(GraphNodeView(id="n1", kind="k", label="n1"),),
    ).to_dict()
    srv, base = _serve([view])
    yield base
    srv.shutdown()


def test_server_endpoints(studio):
    assert "FORGE GRAPH STUDIO" in urllib.request.urlopen(studio + "/").read().decode()
    health = json.loads(urllib.request.urlopen(studio + "/api/health").read())
    assert health["status"] == "ok" and health["graphs"] == 1
    graphs = json.loads(urllib.request.urlopen(studio + "/api/graphs").read())
    assert graphs["graphs"][0]["graph_id"] == "g1"
    view = json.loads(urllib.request.urlopen(studio + "/api/graph/g1").read())
    assert view["nodes"][0]["id"] == "n1"


def test_server_404_and_read_only(studio):
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(studio + "/api/graph/nope")
    assert exc.value.code == 404
    req = urllib.request.Request(studio + "/api/graphs", method="POST")
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req)
    assert exc.value.code == 405


# -- CLI surface ----------------------------------------------------------------


def test_graph_view_cli(tmp_path, capsys):
    from theforge.cli.main import main

    rc = main(["graph", "--view", "--root", ".", "--json"])
    doc = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert doc["schema"] == "forge/ForgeGraphView/v1"


def test_graph_federated_cli(capsys):
    from theforge.cli.main import main

    rc = main(["graph", "--federated", "--root", "..", "--json"])
    out = capsys.readouterr()
    assert rc == 0
    doc = json.loads(out.out)
    assert "views" in doc and "notes" in doc
    assert any(
        v["descriptor"]["provider_id"] == "the-forge" for v in doc["views"]
    )


def test_graph_default_still_works(capsys):
    """``theforge graph`` without new flags keeps the old listing."""
    from theforge.cli.main import main

    rc = main(["graph", "--root", ".", "--json"])
    assert rc == 0
    doc = json.loads(capsys.readouterr().out)
    assert "nodes" in doc and "edges" in doc
