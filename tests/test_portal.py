"""Portal adapter + verb tests — ``theforge portal`` command center.

Covers the FASE-7 surface: honest NOT_INSTALLED state on a virgin
workspace, the federation view (specialists lifecycle + registry),
install plan → confirm → apply with a real receipt, the session-token
gate (403 without it), named refusals (ambiguous intent, stale plan
token, absent host), real MCP handshakes per specialist, federated
graph views and the vendored-assets refusal.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from theforge import _forge_portal as fp
from theforge.portal_adapter import TheForgePortal

ROOT = Path(__file__).resolve().parents[1]


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


def _call(
    srv: fp.PortalServer,
    method: str,
    path: str,
    body: dict | None = None,
    session: str | None = "USE_TOKEN",
) -> tuple[int, dict]:
    req = urllib.request.Request(
        f"http://127.0.0.1:{srv.port}/api/v1{path}",
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={
            "Content-Type": "application/json",
            "X-Forge-Session": srv.session_token if session == "USE_TOKEN" else session or "",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _ctx(server: fp.PortalServer, body: dict) -> fp.RequestContext:
    handler = type("H", (), {"server": server})()
    return fp.RequestContext(handler=handler, body=body, query={}, params={}, correlation_id="t")


# --- descriptor / health -----------------------------------------------------


def test_descriptor_is_federated_command_center(target: Path) -> None:
    d = TheForgePortal(target).descriptor()
    assert d["forge_id"] == "the-forge"
    assert d["cli"] == "theforge"
    assert d["federated"] is True
    caps = {c["id"]: c["state"] for c in d["capabilities"]}
    assert caps["federation"] == "supported"
    assert caps["skills"] == "supported"
    assert caps["agents"] == "supported"


def test_health_not_installed_on_virgin_workspace(target: Path) -> None:
    h = TheForgePortal(target).health()
    assert h["state"] == "NOT_INSTALLED"
    assert h["workspace"] == str(target)


# --- http layer: session, plan → apply, refusals ------------------------------


def test_bootstrap_requires_session(target: Path) -> None:
    srv = _server(TheForgePortal(target))
    try:
        code, _doc = _call(srv, "GET", "/bootstrap", session="")
        assert code == 403
    finally:
        srv.shutdown()
        srv.server_close()


def _call_with_headers(srv: fp.PortalServer, path: str, headers: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        f"http://127.0.0.1:{srv.port}/api/v1{path}",
        headers={"Content-Type": "application/json", **headers},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_session_cookie_authenticates_and_stays_bound(target: Path) -> None:
    srv = _server(TheForgePortal(target))
    try:
        # Cookie-only (SPA reload: in-memory header token is gone) → 200.
        code, doc = _call_with_headers(
            srv, "/bootstrap", {"Cookie": f"forge_session={srv.session_token}"}
        )
        assert code == 200 and "data" in doc
        # Forged cookie alone → 403.
        code, _ = _call_with_headers(srv, "/bootstrap", {"Cookie": "forge_session=forged"})
        assert code == 403
        # Valid header + forged cookie → 403 (cookie is bound, not ignored).
        code, _ = _call_with_headers(
            srv,
            "/bootstrap",
            {"X-Forge-Session": srv.session_token, "Cookie": "forge_session=forged"},
        )
        assert code == 403
        # Invalid header + valid cookie → 403 (header decides when present).
        code, _ = _call_with_headers(
            srv,
            "/bootstrap",
            {"X-Forge-Session": "bad", "Cookie": f"forge_session={srv.session_token}"},
        )
        assert code == 403
    finally:
        srv.shutdown()
        srv.server_close()


def test_install_plan_then_apply_roundtrip(target: Path) -> None:
    srv = _server(TheForgePortal(target))
    try:
        code, boot = _call(srv, "GET", "/bootstrap")
        assert code == 200, boot
        code, plan_doc = _call(
            srv,
            "POST",
            "/installation/plan",
            {"scope": "project", "host": "devin", "profile": "minimal"},
        )
        assert code == 200, plan_doc
        plan = plan_doc["data"]["plan"]
        token = plan_doc["data"]["plan_token"]
        code, applied = _call(
            srv,
            "POST",
            "/installation/apply",
            {"plan": plan, "plan_token": token, "confirm": "apply"},
        )
        assert code == 200, applied
        assert applied["data"]["status"] == "completed"
        code, health = _call(srv, "GET", "/health")
        assert health["data"]["state"] != "NOT_INSTALLED"
    finally:
        srv.shutdown()
        srv.server_close()


def test_apply_rejects_stale_plan_token(target: Path) -> None:
    srv = _server(TheForgePortal(target))
    try:
        code, doc = _call(
            srv,
            "POST",
            "/installation/apply",
            {"plan": {"scope": "project"}, "plan_token": "forged", "confirm": "apply"},
        )
        assert code == 409
        assert doc["error"]["code"] == "PORTAL-PLAN-STALE"
    finally:
        srv.shutdown()
        srv.server_close()


def test_spa_served(target: Path) -> None:
    adapter = TheForgePortal(target)
    assert adapter.assets_dir is not None
    srv = _server(adapter)
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{srv.port}/", timeout=30) as r:
            html = r.read().decode()
        assert "<" in html
    finally:
        srv.shutdown()
        srv.server_close()


# --- federation ---------------------------------------------------------------


def test_federation_reports_catalog_and_registry(target: Path) -> None:
    fed = TheForgePortal(target)._federation()
    providers = {r["provider"] for r in fed["specialists"]}
    # the catalog is data-driven — every specialist forge must be visible
    assert "spark-forge-aws" in providers
    assert "api-forge" in providers
    assert fed["registry"]["path"].endswith("installations")
    assert fed["summary"]["catalog"] == len(fed["specialists"])


def _seed_registry(home: Path, *forge_ids: str) -> None:
    """A minimal `forge/InstallationManifest/v1` per forge — what the real
    bootstrap writes into ~/.forge/installations/."""
    inst = home / ".forge" / "installations"
    inst.mkdir(parents=True, exist_ok=True)
    for fid in forge_ids:
        (inst / f"{fid}.json").write_text(
            json.dumps(
                {
                    "schema": "forge/InstallationManifest/v1",
                    "forge_id": fid,
                    "package": fid.replace("-", "_"),
                    "distribution": fid,
                    "cli": {"name": fid, "version_cmd": [fid, "--version"]},
                    "install_root": str(home / ".forge" / "installs" / fid),
                    "version": "0.0.0",
                    "installed_at": "2026-01-01T00:00:00Z",
                }
            ),
            encoding="utf-8",
        )


def test_federation_install_auto_plan_and_apply(target: Path, _isolate_home: Path) -> None:
    _seed_registry(_isolate_home, "the-forge")
    srv = _server(TheForgePortal(target))
    try:
        # plan spans the whole registered family — each forge's real CLI is
        # resolved, never spawned, at plan time
        choices = {
            "scope": "project",
            "host": "none",
            "profile": "minimal",
            "gateway_profile": "economy",
            "components": {"mcp": True, "tui": True, "skills": False},
        }
        code, plan_doc = _call(srv, "POST", "/federation/plan", choices)
        assert code == 200, plan_doc
        plan = plan_doc["data"]["plan"]
        assert plan == {
            "scope": "project",
            "forge": None,
            "host": "none",
            "profile": "minimal",
            "gateway_profile": "economy",
            "components": ["mcp", "tui"],
        }
        # apply restricted to the-forge itself: the self branch installs
        # in-process (no delegated 600s subprocess) — the portal→kit→receipt
        # path is still exercised end-to-end
        self_choices = {**choices, "forge": "the-forge"}
        code, self_doc = _call(srv, "POST", "/federation/plan", self_choices)
        self_token = self_doc["data"]["plan_token"]
        self_plan = self_doc["data"]["plan"]
        code, applied = _call(
            srv,
            "POST",
            "/federation/install-auto",
            {"plan": self_plan, "plan_token": self_token, "confirm": "install"},
        )
        assert code == 200, applied
        assert applied["data"]["schema"].endswith("InstallReceipt/v1")
        assert applied["data"]["operation"] == "install-auto"
        assert applied["data"]["host"] == "none"
        assert applied["data"]["profile"] == "minimal"
        assert applied["data"]["components"] == ["mcp", "tui"]
        assert applied["data"]["execution_profile"] == "economy"
        assert any(
            f.get("forge_id") == "the-forge" and f.get("via") == "self"
            for f in applied["data"]["forges"]
        )
    finally:
        srv.shutdown()
        srv.server_close()


# --- hosts / mcp ----------------------------------------------------------------


def test_hosts_flow_reports_real_probe(target: Path) -> None:
    hosts = TheForgePortal(target)._hosts()
    assert {h["host"] for h in hosts} >= {"claude", "devin", "codex"}


def test_hosts_launch_refuses_absent_or_copies_command(target: Path) -> None:
    adapter = TheForgePortal(target)
    doc = adapter._hosts_launch(type("C", (), {"body": {"host": "copilot"}})())
    if doc.get("refusal") == "PORTAL-HOST-ABSENT":
        assert doc["command"] is None
    else:
        assert isinstance(doc["command"], str)


def test_mcp_servers_per_specialist_state(target: Path) -> None:
    servers = TheForgePortal(target)._mcp_servers()
    ids = {s["id"] for s in servers}
    assert "spark-forge-aws" in ids
    for s in servers:
        assert s["state"] in (
            "CONFIGURED",
            "UNVERIFIED",
            "NOT_APPLICABLE",
            "DEGRADED",
        )


def test_mcp_verify_real_handshakes_or_named_refusal(target: Path) -> None:
    adapter = TheForgePortal(target)
    try:
        doc = adapter._mcp_verify(type("C", (), {"body": {}})())
    except fp.PortalError as e:
        assert e.code == "TF-PORTAL-MCP-NONE"
        return
    assert doc["status"] in ("PASS", "FAIL", "NOT_APPLICABLE")
    for r in doc["servers"]:
        assert r["status"] in ("PASS", "FAIL", "BLOCKED", "NOT_APPLICABLE")


# --- skills / agents: canonical sources ----------------------------------------


def test_skills_from_canonical_catalog(target: Path) -> None:
    skills = TheForgePortal(target)._skills()
    assert len(skills) > 0
    assert all(s["state"] == "available" for s in skills)


def test_agents_from_agentic_specs(target: Path) -> None:
    agents = TheForgePortal(target)._agents()
    ids = {a["id"] for a in agents}
    # the eight specialists from agentic/agents/*.toml
    assert "ecosystem-router" in ids
    assert all(a["authority"] for a in agents)


# --- tasks ---------------------------------------------------------------------


def test_tasks_plan_ambiguous_refuses(target: Path) -> None:
    adapter = TheForgePortal(target)
    srv = _server(adapter)
    try:
        with pytest.raises(fp.PortalError) as ei:
            adapter._tasks_plan(_ctx(srv, {"intent": "reformat my disk"}))
        assert ei.value.code == "TF-PORTAL-AMBIGUOUS"
    finally:
        srv.shutdown()
        srv.server_close()


def test_tasks_mcp_intent_maps_to_verify(target: Path) -> None:
    adapter = TheForgePortal(target)
    srv = _server(adapter)
    try:
        doc = adapter._tasks_plan(_ctx(srv, {"intent": "verificar o handshake mcp"}))
        assert doc["plan"]["verb"] == "mcp_verify"
    finally:
        srv.shutdown()
        srv.server_close()


def test_tasks_federation_executes_real_collect(target: Path) -> None:
    adapter = TheForgePortal(target)
    srv = _server(adapter)
    try:
        plan_doc = adapter._tasks_plan(
            _ctx(srv, {"intent": "status da federation de especialistas"})
        )
        assert plan_doc["plan"]["verb"] == "federation"
        out = adapter._tasks_execute(
            _ctx(srv, {"plan": plan_doc["plan"], "plan_token": plan_doc["plan_token"]})
        )
        assert out["status"] == "completed"
        receipt = out["task"]["receipt"]
        assert "specialists" in receipt and "summary" in receipt
        assert adapter._tasks[-1]["verb"] == "federation"
    finally:
        srv.shutdown()
        srv.server_close()


# --- graph --------------------------------------------------------------------


def test_federated_graph_view_or_honest_no_graph(target: Path) -> None:
    graphs = TheForgePortal(target)._graphs()
    assert graphs["availability"]["state"] in ("available", "no_graph")
    if graphs["availability"]["state"] == "available":
        assert graphs["views"]


# --- verb: subprocess, the real operator path ------------------------------------


def test_portal_verb_help(target: Path) -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "theforge", "portal", "--help"],
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "FORGE_HOME_OVERRIDE": str(target / "home")},
    )
    assert proc.returncode == 0
    assert "--no-browser" in proc.stdout
    assert "--port" in proc.stdout


def test_portal_verb_serves_and_answers(target: Path) -> None:
    env = dict(os.environ, PYTHONIOENCODING="utf-8", FORGE_HOME_OVERRIDE=str(target / "home"))
    proc = subprocess.Popen(
        [sys.executable, "-m", "theforge", "portal", "--no-browser", "--root", str(target)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )
    try:
        line = proc.stdout.readline()
        doc = json.loads(line)
        parts = urlsplit(doc["url"])
        token = parse_qs(parts.query)["forge_session"][0]
        port = parts.port
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=10) as r:
            assert r.status == 200
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/v1/bootstrap", headers={"X-Forge-Session": token}
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            boot = json.loads(r.read())
        assert boot["data"]["descriptor"]["forge_id"] == "the-forge"
        assert boot["data"]["descriptor"]["federated"] is True
        assert boot["data"]["health"]["state"] == "NOT_INSTALLED"
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_version_lookup_uses_real_dist_name() -> None:
    """Release-1 regression: a dist rename must keep the metadata lookup
    working. The name comes from pyproject — not a hardcoded literal —
    so this fails if `service.DIST_NAME` drifts from the shipped name."""
    import importlib.metadata as md
    import tomllib

    from theforge import portal_adapter
    from theforge.install import service

    project = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))["project"]
    assert project["name"] == service.DIST_NAME, (
        f"DIST_NAME {service.DIST_NAME!r} diverged from pyproject name {project['name']!r}"
    )
    # Resolves via the real dist metadata when the package is installed
    # (editable or wheel). Absent metadata stays honest, never guessed.
    try:
        installed_version = md.version(project["name"])
    except md.PackageNotFoundError:
        installed_version = None
    expected = installed_version if installed_version else "0.0.0+local"
    assert portal_adapter._version() == expected


def test_versions_reports_real_local_state(target: Path) -> None:
    """cyc8-06: GET /versions assembles real data — dist version, the
    committed ecosystem manifest (sha256 + verdict), CHANGELOG.md and
    receipts under .forge/install/receipts. Absent data stays null."""
    out = TheForgePortal(target)._versions()

    installed = out["installed"]
    assert installed["version"] is None or isinstance(installed["version"], str)
    assert installed["channel"] is None
    assert out["available"]["version"] is None
    assert "offline" in out["available"]["source"]

    manifest = Path(__file__).resolve().parents[1] / "ecosystem-compatibility.json"
    if manifest.is_file():
        import hashlib

        assert (
            out["integrity"]["manifest_sha256"] == hashlib.sha256(manifest.read_bytes()).hexdigest()
        )
        assert out["integrity"]["manifest_release"] is not None
        assert "forge/EcosystemCompatibility/v1" in out["compat"]
    else:
        assert out["integrity"]["manifest_sha256"] is None
        assert "unverified" in out["compat"]

    receipts_dir = target / ".forge" / "install" / "receipts"
    receipts_dir.mkdir(parents=True)
    (receipts_dir / "apply-20261015T120000Z.json").write_text(
        json.dumps(
            {
                "schema": "forge/InstallReceipt/v1",
                "operation": "apply",
                "status": "completed",
                "created_at": "2026-10-15T12:00:00Z",
                "created_by": "theforge/0.5.0",
            }
        )
    )
    out = TheForgePortal(target)._versions()
    assert [r["file"] for r in out["receipts"]] == ["apply-20261015T120000Z.json"]
    # receipts carry no version-transition field — created_by is the
    # installer's version, so history version stays honestly null.
    assert out["history"][0]["version"] is None
    assert out["history"][0]["at"] == "2026-10-15T12:00:00Z"
    assert out["rollback"]["supported"] is True
    assert "theforge install" in out["rollback"]["hint"]
    assert out["pending"] is None and out["upgrade_plan"] is None


def test_lab_reads_real_benchmark_artifacts(target: Path) -> None:
    """cyc9-10: GET /lab surfaces real collected runs + reports from
    docs/programs/ecosystem-2026/benchmarks — nothing synthesized; absent
    dir yields honest nulls; malformed lines become notes, not crashes."""
    out = TheForgePortal(target)._lab()

    bench = ROOT / "docs" / "programs" / "ecosystem-2026" / "benchmarks"
    if bench.is_dir():
        assert out["dir"] == "docs/programs/ecosystem-2026/benchmarks"
        expected_runs = sorted(p.name for p in bench.glob("results-*.jsonl"))
        assert [r["file"] for r in out["runs"]] == expected_runs
        expected_reports = sorted(p.name for p in bench.glob("*.md") if p.name != "methodology.md")
        assert [r["file"] for r in out["reports"]] == expected_reports
        # every forge row traces to a parsed receipt line — no invention
        for run in out["runs"]:
            for forge in run["forges"]:
                assert isinstance(forge["results"], list)
    else:
        assert out["dir"] is None
        assert out["runs"] == [] and out["reports"] == []

    assert isinstance(out["notes"], list)
