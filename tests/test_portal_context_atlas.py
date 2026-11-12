"""Portal — Code Atlas probe op + forge/context projection tests.

``GET /api/v1/atlas/status`` is served by the vendored ``_portal_atlas``
module (canonical: forge-portal ``portal_core/atlas_ops.py``); the
federation payload additionally projects ``.forge/context`` granular
state (manifest state / health / kind / discovery) so forge cards can
render the shared vocabulary honestly — absent, corrupt and unverified
are named states, never fabricated values.
"""

from __future__ import annotations

import importlib.util
import json
import socket
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from theforge import _forge_portal as fp
from theforge.portal_adapter import TheForgePortal

ROOT = Path(__file__).resolve().parents[1]

spec = importlib.util.spec_from_file_location(
    "_forgecontext", ROOT / "src" / "theforge" / "_forgecontext.py"
)
fctx = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fctx)


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


def _server(adapter: TheForgePortal) -> fp.PortalServer:
    server = fp.PortalServer(adapter, quiet=True)
    server.serve_in_thread()
    return server


def _call(srv: fp.PortalServer, path: str) -> tuple[int, dict]:
    req = urllib.request.Request(
        f"http://127.0.0.1:{srv.port}/api/v1{path}",
        headers={"X-Forge-Session": srv.session_token},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _closed_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    return port


def _manifest(fid: str, **over) -> dict:
    kw = {
        "forge_id": fid,
        "name": f"Forge {fid}",
        "version": "1.2.3",
        "cli": fid,
        "package": fid.replace("-", "_"),
        "distribution": fid,
        "python_spec": ">=3.11",
        "scope": "project",
        "domains": ("forge-ecosystem",),
        "skills": ("forge-routing",),
        "recorded_at": "2026-10-22T00:00:00Z",
    }
    kw.update(over)
    return fctx.build_manifest(**kw)


# --- GET /atlas/status ------------------------------------------------------


class _StubAtlas(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        body = (
            json.dumps({"status": "ok", "service": "code-atlas-api", "version": 1}).encode()
            if self.path == "/api/v1/health"
            else json.dumps({"items": [{"repository_id": 1, "ready_snapshots": 1}]}).encode()
        )
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a) -> None:
        pass


def test_atlas_status_op_serves_named_state(target: Path, monkeypatch) -> None:
    monkeypatch.setenv("FORGE_ATLAS_URL", f"http://127.0.0.1:{_closed_port()}")
    srv = _server(TheForgePortal(target))
    try:
        status, env = _call(srv, "/atlas/status")
        assert status == 200  # a named state is data, not a transport error
        assert env["schema"] == "forge/PortalApi/1"
        doc = env["data"]
        assert doc["schema"] == "forge/PortalAtlasStatus/1"
        assert doc["state"] == "unavailable"
        assert doc["detail"]  # named failure token, e.g. connection-refused
        assert doc["index"] is None
    finally:
        srv.shutdown()
        srv.server_close()


def test_atlas_status_op_available_with_index(target: Path, monkeypatch) -> None:
    stub = ThreadingHTTPServer(("127.0.0.1", 0), _StubAtlas)
    thread = threading.Thread(target=stub.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("FORGE_ATLAS_URL", f"http://127.0.0.1:{stub.server_address[1]}")
    srv = _server(TheForgePortal(target))
    try:
        status, env = _call(srv, "/atlas/status")
        assert status == 200
        doc = env["data"]
        assert doc["state"] == "available"
        assert doc["service"] == "code-atlas-api"
        assert doc["index"]["repositories"] == 1
        assert doc["index"]["ready_snapshots"] == 1
    finally:
        srv.shutdown()
        srv.server_close()
        stub.shutdown()
        stub.server_close()
        thread.join(timeout=5)


def test_atlas_capability_declared(target: Path) -> None:
    caps = {c["id"]: c["state"] for c in TheForgePortal(target).capabilities()}
    assert caps["atlas"] == "supported"


# --- federation.context — forge/context-registry/v1 projection ---------------


def test_federation_context_absent_on_virgin_workspace(target: Path) -> None:
    ctx = TheForgePortal(target)._federation()["context"]
    assert ctx["schema"] == "forge/context-registry/v1"
    assert ctx["state"] == "absent"
    assert ctx["forges"] == {}


def test_federation_context_corrupt_registry_is_named(target: Path) -> None:
    ctx_dir = target / ".forge" / "context"
    ctx_dir.mkdir(parents=True)
    (ctx_dir / "registry.json").write_text("{ not json", encoding="utf-8")
    ctx = TheForgePortal(target)._federation()["context"]
    assert ctx["state"] == "corrupt"
    assert ctx["forges"] == {}


def test_federation_context_projects_registered_forges(target: Path) -> None:
    fctx.register_forge(
        target,
        _manifest(
            "atlas-x",
            kind="code-intelligence",
            state="degraded",
            degraded_reasons=("partial index",),
            health={"status": "degraded", "checks": [{"id": "db", "status": "PASS"}]},
        ),
        owner="atlas-x",
    )
    fctx.register_forge(target, _manifest("plain-y"), owner="plain-y")
    ctx = TheForgePortal(target)._federation()["context"]

    assert ctx["state"] == "registered"
    assert ctx["count"] == 2
    proj = ctx["forges"]["atlas-x"]
    assert proj["state"] == "degraded"
    assert proj["kind"] == "code-intelligence"
    assert proj["health"] == "degraded"
    assert proj["health_checks"] == 1
    assert proj["degraded_reasons"] == ["partial index"]
    # skills/agents capabilities record discovery="workspace-file"
    assert "workspace-file" in proj["discovery"]
    assert proj["scope"] == "project"

    plain = ctx["forges"]["plain-y"]
    assert plain["state"] == "available"
    assert plain["kind"] is None  # undeclared stays null, not invented
    assert plain["health"] == "unverified"


def test_federation_context_entry_without_manifest_is_honest(target: Path) -> None:
    fctx.register_forge(target, _manifest("ghost-forge"), owner="ghost-forge")
    (target / ".forge" / "context" / "capabilities" / "ghost-forge.json").unlink()
    proj = TheForgePortal(target)._federation()["context"]["forges"]["ghost-forge"]
    assert proj["state"] == "available"  # registry-level evidence
    assert proj["health"] is None  # manifest gone → unverified, not healthy
    assert proj["discovery"] == []
