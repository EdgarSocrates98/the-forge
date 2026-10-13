"""format_status_doc / approve_plan — the shared forge/* human renderer.

Covers the doc shapes the installkit emits: health (status/doctor),
receipts (planned/completed), refusals (approval gate), drift, and the
forge-portal presence block. ANSI/color output is checked separately
from the plain layout so pipes stay deterministic.
"""

from __future__ import annotations

import re

import pytest

from theforge.ui.kit import (
    NonInteractive,
    UIContext,
    approve_plan,
    format_status_doc,
    state_color,
)

ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _ctx(*, color: bool = False, language: str = "en") -> UIContext:
    return UIContext(
        interactive=False,
        color=color,
        unicode=True,
        width=100,
        ansi=False,
        language=language,
    )


HEALTH_DOC = {
    "schema": "forge/HealthDoc/v1",
    "forge_id": "api-forge",
    "status": "degraded",
    "scope": "project",
    "target_root": "E:/proj/demo",
    "state_dir": "E:/proj/demo/.apiforge/install",
    "ledger_entries": 12,
    "checks": [
        {"id": "ledger", "status": "PASS", "detail": "12 managed entries"},
        {"id": "drift:.mcp.json", "status": "FAIL", "detail": "modified",
         "repairable": True},
        {"id": "forge-portal", "status": "NOT_APPLICABLE",
         "detail": "vendored assets only"},
    ],
    "context": {"profile": "recommended", "managed_entries": 12},
    "repair_hint": "apiforge install repair",
}

REFUSAL_DOC = {
    "schema": "forge/InstallReceipt/v1",
    "forge_id": "api-forge",
    "operation": "install",
    "status": "failed",
    "error": {
        "kind": "FORGE-INSTALL-APPROVAL",
        "detail": "writes require explicit approval",
        "unlock": "run with --dry-run or --yes",
    },
    "checks": [],
    "managed_files": [],
    "verification": {"status": "FAIL"},
}

STATUS_DOC = {
    "schema": "forge/HealthDoc/v1",
    "forge_id": "the-forge",
    "status": "healthy",
    "scope": "project",
    "target_root": "E:/proj/demo",
    "ledger_entries": 10,
    "drift": {
        "ok": 10,
        "modified": [{"path": ".mcp.json", "status": "modified"}],
        "missing": [{"path": "AGENTS.md", "status": "missing"}],
    },
    "forge_portal": {"state": "vendored", "install_root": None,
                     "manifest": None, "locations": []},
    "receipts": ["r1.json"],
    "checked_at": "2026-01-01T00:00:00Z",
}


def test_health_doc_plain_has_all_sections():
    out = format_status_doc(HEALTH_DOC, ctx=_ctx())
    assert "API-FORGE" in out
    assert "DEGRADED" in out
    assert "E:/proj/demo" in out
    assert "ledger" in out and "12 managed entries" in out
    assert "repairable" in out  # drift check flagged
    assert "vendored assets only" in out
    assert "apiforge install repair" in out
    assert not ANSI.search(out)  # plain ctx: zero escapes


def test_refusal_shows_kind_detail_unlock():
    out = format_status_doc(REFUSAL_DOC, ctx=_ctx())
    assert "FORGE-INSTALL-APPROVAL" in out
    assert "writes require explicit approval" in out
    assert "unlock:" in out and "--yes" in out
    assert "FAILED" in out


def test_status_doc_drift_and_portal():
    out = format_status_doc(STATUS_DOC, ctx=_ctx())
    assert "ok 10" in out
    assert "modified 1" in out and "missing 1" in out
    assert ".mcp.json" in out and "AGENTS.md" in out
    assert "FORGE PORTAL" in out and "vendored" in out


def test_status_label_lowercase_and_target():
    out = format_status_doc(STATUS_DOC, ctx=_ctx())
    assert "status" in out and "HEALTHY" in out
    assert "target" in out


def test_color_marks_states():
    out = format_status_doc(HEALTH_DOC, ctx=_ctx(color=True))
    assert ANSI.search(out)
    # PASS green, FAIL red
    assert "\x1b[32m" in out and "\x1b[31m" in out


def test_state_color_unknown_is_dim_not_red():
    ctx = _ctx(color=True)
    rendered = state_color(ctx, "SOMETHING_NEW")
    assert "\x1b[2m" in rendered


def test_missing_sections_omitted():
    out = format_status_doc({"forge_id": "x", "status": "ok"}, ctx=_ctx())
    assert "CHECKS" not in out and "DRIFT" not in out
    assert "FORGE PORTAL" not in out


def test_planned_receipt_lists_files():
    doc = {
        "forge_id": "api-forge",
        "operation": "install",
        "status": "planned",
        "planned_files": [{"path": "a.md"}, {"path": "b.md"}],
        "verification": {"status": "UNVERIFIED"},
    }
    out = format_status_doc(doc, ctx=_ctx())
    assert "PLANNED FILES" in out
    assert "a.md" in out


def test_workspace_members_and_conflicts():
    doc = {
        "forge_id": "the-forge",
        "status": "planned",
        "workspace": {
            "members": [{"path": "../api-forge"}],
            "conflicts": [{"member": "../api-forge", "forge_id": "api-forge",
                           "decision": "install"}],
            "unknown_members": ["../ghost"],
            "member_results": [{"member": "../api-forge",
                                "status": "completed"}],
        },
    }
    out = format_status_doc(doc, ctx=_ctx())
    assert "WORKSPACE" in out
    assert "../api-forge/api-forge: install" in out
    assert "../ghost" in out
    assert "completed" in out


def test_non_tty_approve_plan_raises():
    ctx = _ctx()
    with pytest.raises(NonInteractive):
        approve_plan(HEALTH_DOC, ctx=ctx)
