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


def test_component_options_selection():
    from theforge import _installkit as kit

    opts = kit.component_options("recommended", ("skills", "mcp"))
    assert opts["graph_studio"] is False
    assert "skill" in opts["asset_kinds"]
    assert "agent" not in opts["asset_kinds"]


def test_component_options_unknown_rejected():
    import pytest

    from theforge import _installkit as kit

    with pytest.raises(kit.InstallError):
        kit.component_options("recommended", ("bogus",))


def test_install_apply_persists_components(tmp_path):
    from theforge.install import service

    receipt = service.install(
        "claude",
        scope="project",
        root=tmp_path,
        profile="recommended",
        yes=True,
        components=("skills", "mcp"),
    )
    assert receipt["status"] == "completed"
    comp = tmp_path / ".forge" / "install" / "components.json"
    assert comp.is_file()
    doc = json.loads(comp.read_text())
    assert doc["graph_studio"] is False
    assert receipt["components"]["graph_studio"] is False


def test_graph_studio_enabled_gate(tmp_path):
    from theforge.graphstudio import graph_studio_enabled

    assert graph_studio_enabled(tmp_path) is True
    sd = tmp_path / ".forge" / "install"
    sd.mkdir(parents=True)
    (sd / "components.json").write_text(
        json.dumps({"graph_studio": False}), encoding="utf-8"
    )
    assert graph_studio_enabled(tmp_path) is False


def test_graph_ui_refuses_when_declined(tmp_path, capsys):
    from theforge.cli.main import main

    sd = tmp_path / ".forge" / "install"
    sd.mkdir(parents=True)
    (sd / "components.json").write_text(
        json.dumps({"graph_studio": False}), encoding="utf-8"
    )
    rc = main(["graph", "--ui", "--root", str(tmp_path), "--json"])
    assert rc == 2
    doc = json.loads(capsys.readouterr().out)
    assert doc["refusal"] == "FORGE-GRAPH-STUDIO-DISABLED"


# -- federation boundary -------------------------------------------------------


def _fake_checkout(tmp_path: Path, body: str, *, manifest: bool = True) -> Path:
    """A minimal sibling checkout: agentic manifest + a cli_entry module."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    if manifest:
        (tmp_path / "forge.agentic.json").write_text(
            '{"schema": "forge/SpecialistAgenticManifest/v1",'
            ' "provider": "fake", "cli_entry": "fake_cli:main"}',
            encoding="utf-8",
        )
    else:
        # minimal provider without a manifest may put cli_entry on forge.json
        (tmp_path / "forge.json").write_text(
            'cli_entry = "fake_cli:main"\n', encoding="utf-8"
        )
    (tmp_path / "fake_cli.py").write_text(body, encoding="utf-8")
    return tmp_path


def test_view_from_cli_real_subprocess(tmp_path):
    """End-to-end: a sibling CLI emits a view doc; federation parses it."""
    from theforge.contracts.graphview import ForgeGraphView, GraphNodeView, new_descriptor
    from theforge.graphview import _view_from_cli

    doc = ForgeGraphView(
        descriptor=new_descriptor(provider_id="fake", domain="d", graph_id="fake/g"),
        nodes=(GraphNodeView(id="n", kind="k", label="n"),),
    ).to_dict()
    checkout = _fake_checkout(
        tmp_path,
        "import json, sys\n"
        "def main():\n"
        f"    print(json.dumps({doc!r}))\n"
        "    return 0\n",
    )
    view, reason = _view_from_cli(checkout, "fake", timeout=20)
    assert view is not None, reason
    assert view.descriptor.provider_id == "fake"
    assert view.nodes[0].id == "n"


def test_view_from_cli_forge_json_fallback(tmp_path):
    """forge.json cli_entry still works for providers without a manifest."""
    from theforge.contracts.graphview import ForgeGraphView, GraphNodeView, new_descriptor
    from theforge.graphview import _view_from_cli

    doc = ForgeGraphView(
        descriptor=new_descriptor(provider_id="fake", domain="d", graph_id="fake/g"),
        nodes=(GraphNodeView(id="n", kind="k", label="n"),),
    ).to_dict()
    checkout = _fake_checkout(
        tmp_path,
        "import json, sys\n"
        "def main():\n"
        f"    print(json.dumps({doc!r}))\n"
        "    return 0\n",
        manifest=False,
    )
    view, reason = _view_from_cli(checkout, "fake", timeout=20)
    assert view is not None, reason
    assert view.descriptor.provider_id == "fake"


def test_federated_views_real_workspace():
    """Real FORJAS workspace: siblings discovered via forge.agentic.json.

    Skips when the repo isn't beside sibling checkouts (CI isolation).
    """
    from theforge.graphview import federated_views

    workspace = Path(__file__).resolve().parents[2]
    siblings = [
        d.name for d in workspace.iterdir()
        if (d / "forge.agentic.json").is_file()
    ]
    if len(siblings) < 2:
        import pytest

        pytest.skip("no sibling checkouts beside this repo")
    views, notes = federated_views(workspace_root=workspace, timeout=60)
    providers = {v.descriptor.provider_id for v in views}
    assert "the-forge" in providers
    produced = providers & set(siblings)
    # producers either emit a view or fail with a named reason — a
    # refusal code or exit status proves the subprocess reached the CLI
    assert produced or any(
        "refused " in n or "exited " in n for n in notes
    ), f"producers neither produced nor reported; notes={notes}"
    assert all(": " in n for n in notes)  # every note carries a reason


def test_view_from_cli_degrades_honestly(tmp_path):
    from theforge.graphview import _view_from_cli

    view, reason = _view_from_cli(tmp_path / "missing", "x", timeout=10)
    assert view is None and reason
    bad = _fake_checkout(tmp_path / "bad", "def main():\n    return 1\n")
    view, reason = _view_from_cli(bad, "x", timeout=10)
    assert view is None and "exited" in reason
    junk = _fake_checkout(tmp_path / "junk", "def main():\n    print('not json')\n")
    view, reason = _view_from_cli(junk, "x", timeout=10)
    assert view is None and "JSON" in reason

    refused = _fake_checkout(
        tmp_path / "ref",
        'import json\n'
        'def main():\n'
        '    print(json.dumps({"refusal": "X-NO-GRAPH"}))\n'
        '    return 2\n',
    )
    view, reason = _view_from_cli(refused, "x", timeout=10)
    assert view is None and reason == "refused X-NO-GRAPH"


# -- studio assets -------------------------------------------------------------


def test_studio_inline_script_parses(tmp_path):
    """The embedded Studio ships one inline <script> — it must be valid JS.

    A real DOM smoke needs a browser harness we don't have; node --check
    is the cheap honest layer that catches a mangled template.
    """
    import re
    import shutil
    import subprocess

    from theforge.graphstudio import STUDIO_HTML

    node = shutil.which("node")
    if node is None:
        import pytest

        pytest.skip("node not installed")
    m = re.search(r"<script>(.*)</script>", STUDIO_HTML, re.DOTALL)
    assert m, "STUDIO_HTML has no inline script"
    js = tmp_path / "studio.js"
    js.write_text(m.group(1), encoding="utf-8")
    proc = subprocess.run(
        [node, "--check", str(js)], capture_output=True, text=True, timeout=30
    )
    assert proc.returncode == 0, proc.stderr
