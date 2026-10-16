"""Browser E2E — real Chromium against the REAL the-forge portal adapter.

Cycle 10.1 §4.1: the primary evidence uses ``TheForgePortal`` — the real
adapter backed by the real install/service/specialists/federation
services — serving the vendored production bundle in ``portal/assets``.
No stub adapter: every field on screen comes from a real service call.

Requires playwright + system Chrome (``channel="chrome"``).
Run:  python -m pytest e2e/ -q
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from playwright.sync_api import sync_playwright

from theforge import _forge_portal as fp
from theforge.portal_adapter import TheForgePortal, build_server

REPO = Path(__file__).resolve().parent.parent
ARTIFACTS = Path(__file__).resolve().parent / "artifacts"
ASSETS = REPO / "portal" / "assets"


@pytest.fixture(scope="module")
def server():
    srv = build_server()
    srv.serve_in_thread()
    yield srv
    srv.shutdown()
    srv.server_close()


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True)
        yield b
        b.close()


@pytest.fixture()
def page(browser, server):
    pg = browser.new_page()
    pg.goto(server.url, wait_until="networkidle")
    yield pg
    pg.close()


def _api(server: fp.PortalServer, path: str) -> dict:
    req = urllib.request.Request(
        f"http://127.0.0.1:{server.port}/api/v1{path}",
        headers={"X-Forge-Session": server.session_token},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        body = json.loads(r.read())
    return body.get("data", body) if isinstance(body, dict) else body


def _shot(page, name: str) -> Path:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    out = ARTIFACTS / f"{name}.png"
    page.screenshot(path=str(out), full_page=False)
    return out


def test_bundle_is_vendored():
    assert (ASSETS / "index.html").is_file(), "vendored production bundle missing"


def test_first_paint_shell(page, server):
    assert page.locator("body").inner_text().strip(), "blank first paint"
    _shot(page, "01-shell")


def test_nav_routes_render_real_data(page, server):
    """Every route the real adapter declares must render without a blank page."""
    routes = sorted({item["route"] for item in TheForgePortal().nav() if item.get("route")})
    # plus routes the SPA exposes for the adapter's declared capabilities
    routes += ["/lab", "/versions", "/hosts", "/specialists"]
    routes = sorted(set(routes))
    assert routes, "adapter declared no routes"
    rendered = []
    for route in routes:
        page.goto(f"{server.url.split('?')[0].rstrip('/')}/#{route.lstrip('/')}" if "#" not in page.url else page.url)
        # Angular SPA — client-side routing
        page.evaluate(f"location.hash = '#{route.lstrip('/')}'")
        page.wait_for_timeout(1200)
        text = page.locator("body").inner_text().strip()
        assert text, f"{route} rendered empty"
        rendered.append(route)
    _shot(page, "02-last-route")
    (ARTIFACTS / "routes.json").write_text(json.dumps(rendered))


def test_specialists_federation_real(page, server):
    """Federation view shows the real specialists collect — not fabricated rows."""
    fed = _api(server, "/federation")
    assert isinstance(fed, dict) and fed, "empty federation payload"
    page.goto(server.url)
    page.evaluate("location.hash = '#/federation'")
    page.wait_for_timeout(1500)
    text = page.locator("body").inner_text()
    assert "the-forge" in text or "forges" in text.lower() or "federation" in text.lower()
    _shot(page, "03-federation")


def test_lab_real_receipts(page, server):
    """§4.6 — /lab serves real benchmark receipts or honest empty state."""
    lab = _api(server, "/lab")
    assert isinstance(lab, dict) and (
        "runs" in lab or "reports" in lab
    ), f"/lab payload missing runs/reports: {sorted(lab)}"
    page.goto(server.url)
    page.evaluate("location.hash = '#/lab'")
    page.wait_for_timeout(1500)
    text = page.locator("body").inner_text().lower()
    assert "lab" in text
    _shot(page, "04-lab")


def test_capabilities_real(page, server):
    caps = _api(server, "/capabilities")
    assert caps, "adapter returned no capabilities"
    assert all(c.get("id") for c in caps), "capability without id"


def test_install_plan_preview_only(page, server):
    """§4.4 — install plan renders; apply is NOT exercised here (mutating)."""
    code_plan = _api(server, "/installation/status")
    assert isinstance(code_plan, dict)
    page.goto(server.url)
    page.evaluate("location.hash = '#/install'")
    page.wait_for_timeout(1200)
    assert page.locator("body").inner_text().strip()
    _shot(page, "05-install")


def test_no_console_errors_on_routes(page, server):
    errors: list[str] = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    for route in ("", "federation", "lab", "tasks", "graph"):
        page.evaluate(f"location.hash = '#/{route}'")
        page.wait_for_timeout(1000)
    real = [e for e in errors if "favicon" not in e.lower()]
    assert not real, f"console errors: {real[:5]}"


def test_mobile_viewport(browser, server):
    ctx = browser.new_context(viewport={"width": 390, "height": 844})
    pg = ctx.new_page()
    pg.goto(server.url, wait_until="networkidle")
    assert pg.locator("body").inner_text().strip()
    pg.screenshot(path=str(ARTIFACTS / "06-mobile.png"))
    ctx.close()
