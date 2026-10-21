"""lf-0023 parity — the portal ``/graphs`` endpoint serves the identical
``forge/ForgeGraphView/v1`` document the CLI ``graph --federated --ui``
hands to the Graph Studio.

``theforge graph --federated --ui`` collects sibling views and opens the
``federated_merge`` product in the studio; ``TheForgePortal._graphs``
serves the same merged document. Both must be the identical projection —
this test pins the contract at the producer boundary.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from theforge.portal_adapter import TheForgePortal


@pytest.fixture()
def target(tmp_path: Path) -> Path:
    root = tmp_path / "consumer"
    root.mkdir()
    (root / ".git").mkdir()
    (root / ".forge").mkdir()
    return root


@pytest.fixture(autouse=True)
def _isolate_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("FORGE_HOME_OVERRIDE", str(home))
    return home


def test_portal_graphs_serves_identical_federated_view_as_cli_ui(
    target: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Capture the document `graph --federated --ui` would hand to the
    # Graph Studio — same code path as the real CLI verb.
    captured: dict = {}
    monkeypatch.setattr(
        "theforge.graphstudio.graph_studio_enabled", lambda *a, **kw: True
    )

    def _studio(views, **_kw):
        captured["views"] = views
        return 0

    monkeypatch.setattr("theforge.graphstudio.open_studio", _studio)

    from theforge.cli.commands import _cmd_graph_view

    args = argparse.Namespace(
        ui=True,
        federated=True,
        no_browser=True,
        port=0,
        out=None,
        json=False,
    )
    code = _cmd_graph_view(args, target)
    assert code == 0
    cli_views = captured.get("views")
    assert cli_views and len(cli_views) == 1
    cli_doc = cli_views[0].to_dict()

    # Portal side — the adapter's GET /api/v1/graphs response.
    bundle = TheForgePortal(target)._graphs()
    assert bundle["availability"]["state"] == "available"
    assert len(bundle["views"]) == 1
    portal_doc = json.loads(json.dumps(bundle["views"][0], default=str))
    cli_wire = json.loads(json.dumps(cli_doc, default=str))

    # The merged projection is identical modulo two non-data fields:
    # - `federation_notes`: the adapter's transport diagnostic — the CLI
    #   reports the same producer notes on stderr ("note: <provider>: …");
    # - `descriptor.generated_at`: a wall-clock stamp taken per call —
    #   the two invocations can legitimately straddle a second boundary.
    # Neither is graph data; node/edge sets below pin the real parity.
    portal_notes = portal_doc.pop("federation_notes", [])
    cli_wire.pop("federation_notes", None)
    portal_doc["descriptor"]["generated_at"] = cli_wire["descriptor"][
        "generated_at"
    ]
    assert portal_doc == cli_wire
    assert {n["id"] for n in portal_doc["nodes"]} == {
        n["id"] for n in cli_wire["nodes"]
    }
    assert {e["id"] for e in portal_doc["edges"]} == {
        e["id"] for e in cli_wire["edges"]
    }
    # producer notes honestly name every forge that could not serve a
    # view — they are strings, never silent omissions
    assert all(isinstance(n, str) for n in portal_notes)
