"""Offline operation proven, not assumed (cycle 16.1 §5.2).

The session network block already *denies* non-loopback traffic; these
tests go further — socket creation, connection and DNS resolution are
instrumented to fail loudly, then a representative install → plan →
resource → status → uninstall path runs to completion underneath. Zero
outbound attempts is the claim; the counters prove it.

Honest boundary — operations that genuinely require network are NOT
claimed offline-ready:

- ``service.update`` / ``theforge install update`` — ``pip install`` from
  an index;
- ``theforge.registry.remote`` — remote provider-registry sync
  (``urllib.request`` — the only network client import in the core);
- ``scripts/installkit/forge_bootstrap.py --allow-download`` — the
  explicit download opt-in;
- provider/subprocess CLIs themselves when they call cloud services —
  outside this core's reach.
"""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

from theforge.context.plan import plan_context
from theforge.context.resources import ResourceResolver, discover_roots
from theforge.install import service


@pytest.fixture()
def net_police(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every outbound attempt is recorded and then explodes — a pass with
    an empty log is proof, not hope."""
    attempts: list[str] = []

    def _explode(*args: object, **kwargs: object) -> None:
        attempts.append(repr(args)[:160])
        raise AssertionError(f"outbound connection attempt: {args!r}")

    monkeypatch.setattr(socket, "socket", _explode)
    monkeypatch.setattr(socket, "create_connection", _explode)
    monkeypatch.setattr(socket, "getaddrinfo", _explode)
    return attempts


def _resolver(root: Path) -> ResourceResolver:
    explicit = [
        (p.name, p)
        for p in sorted(root.iterdir())
        if p.is_dir() and (p / "forge.agentic.json").is_file()
    ]
    return ResourceResolver(
        discover_roots(workspace_root=root, explicit=explicit, scan_installed=False)
    )


def test_install_plan_status_uninstall_never_dial_out(
    tmp_path: Path, net_police: list[str]
) -> None:
    target = tmp_path / "consumer"
    target.mkdir()

    # Representative install path — plan, apply, health, uninstall.
    plan = service.install(scope="project", root=target, dry_run=True)
    assert plan["status"] == "planned"
    receipt = service.install(scope="project", root=target, yes=True)
    assert receipt["status"] == "completed"
    health = service.status(scope="project", root=target)
    assert health["status"] in ("healthy", "degraded", "unverified")
    out = service.uninstall(scope="project", root=target)
    assert out["status"] == "completed"

    assert net_police == []


def test_resource_resolution_and_context_plan_stay_local(
    tmp_path: Path, net_police: list[str]
) -> None:
    import json

    forge = tmp_path / "ws" / "demo-forge"
    forge.mkdir(parents=True)
    (forge / "forge.agentic.json").write_text(
        json.dumps(
            {
                "schema": "forge/SpecialistAgenticManifest/v1",
                "id": "demo-forge",
                "version": "1.0.0",
                "resources": [
                    {
                        "id": "skill-demo",
                        "kind": "skill",
                        "location": "skills/demo/SKILL.md",
                        "tags": ["spark", "tuning"],
                        "availability": "available",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    body = forge / "skills" / "demo" / "SKILL.md"
    body.parent.mkdir(parents=True)
    body.write_text("# demo\n", encoding="utf-8")

    res = _resolver(tmp_path / "ws")
    assert res.list() and res.search("demo")
    content = res.get("demo-forge:skill-demo")
    assert content.text == "# demo\n"
    plan = plan_context("spark tuning job", res)
    assert plan.level2_forge == "demo-forge"

    assert net_police == []


def test_network_boundary_is_declared_and_closed() -> None:
    """The set of core modules allowed to hold a network client import is
    pinned — anything new is an undeclared boundary, not an accident."""
    import ast

    src = Path(__file__).resolve().parents[1] / "src" / "theforge"
    offenders: set[str] = set()
    for path in src.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            if any(
                n.split(".")[0] in {"urllib", "http", "requests", "httpx", "aiohttp"} for n in names
            ):
                offenders.add(path.relative_to(src).as_posix())
    # Loopback *server* boundaries (no outbound): the portal modules and
    # graphstudio's local viewer (http.server + urllib.parse, parsing only).
    # registry/remote is the single declared remote-sync *client*.
    assert offenders <= {
        "_forge_portal.py",
        "_portal_telemetry.py",
        "_portal_atlas.py",
        "graphstudio.py",
        "registry/remote.py",
    }, f"undeclared network boundary: {offenders}"
    assert "registry/remote.py" in offenders  # the declared exception exists
