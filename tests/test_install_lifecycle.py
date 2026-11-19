"""Install lifecycle state model (cycle 16.1 §5.3) — ``forge/InstallLifecycle/v1``.

The receipt ``status`` is the coarse operation verdict; ``lifecycle.state``
is the derived, honest position of the installation. ``completed`` is never
a synonym for production-ready: it maps to ``applied`` (writes executed,
verification pending), ``verified`` (checks PASS) or ``failed`` —
never to ``ready``/``certified``.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from theforge.install import lifecycle, service

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "docs" / "portable-installation" / "schemas"


def _receipt(status: str, verification: str | None = None, **kw: object) -> dict:
    doc: dict = {"status": status, "verification": {"status": verification or "PASS"}}
    doc.update(kw)
    return doc


def test_state_vocabulary_is_closed() -> None:
    assert set(lifecycle.STATES) == {
        "planned",
        "blocked",
        "failed",
        "applied",
        "partially_applied",
        "verified",
        "unverified",
        "ready",
        "certified",
    }


@pytest.mark.parametrize(
    ("doc", "want"),
    [
        (_receipt("planned", "UNVERIFIED"), "planned"),
        (_receipt("blocked", "UNVERIFIED"), "blocked"),
        (_receipt("refused", "UNVERIFIED"), "blocked"),
        (_receipt("unsupported", "UNVERIFIED"), "blocked"),
        (_receipt("failed", "FAIL"), "failed"),
        (_receipt("unverified", "UNVERIFIED"), "unverified"),
        (_receipt(""), "unverified"),
        # completed is never production-ready by itself:
        (_receipt("completed", "PASS"), "verified"),
        (_receipt("completed", "UNVERIFIED"), "applied"),
        (_receipt("completed", "BLOCKED"), "applied"),
        (_receipt("completed", "FAIL"), "failed"),
        (_receipt("mystery", "PASS"), "unverified"),
    ],
)
def test_receipt_state_mapping(doc: dict, want: str) -> None:
    state, detail = lifecycle.receipt_state(doc)
    assert state == want
    assert detail


def test_completed_never_ready_or_certified() -> None:
    """§5.3 core: 'completed' alone can never reach the ready/certified
    states — those require health or external certification evidence."""
    for verification in ("PASS", "FAIL", "UNVERIFIED", "BLOCKED", "NOT_APPLICABLE"):
        state, _ = lifecycle.receipt_state(_receipt("completed", verification))
        assert state not in {"ready", "certified"}


def test_partial_batch_is_partially_applied() -> None:
    doc = _receipt(
        "failed",
        "FAIL",
        forges=[
            {"forge_id": "a", "status": "completed"},
            {"forge_id": "b", "status": "blocked"},
            {"forge_id": "c", "status": "failed"},
        ],
        checks=[{"id": "forge:b", "status": "FAIL"}],
    )
    state, detail = lifecycle.receipt_state(doc)
    assert state == "partially_applied"
    assert "1/3" in detail


def test_all_gated_batch_is_blocked_not_failed() -> None:
    doc = _receipt(
        "failed",
        "FAIL",
        checks=[
            {"id": "forge:a", "status": "BLOCKED"},
            {"id": "forge:b", "status": "BLOCKED"},
        ],
    )
    state, _ = lifecycle.receipt_state(doc)
    assert state == "blocked"


@pytest.mark.parametrize(
    ("health", "want"),
    [
        ("healthy", "ready"),
        ("degraded", "partially_applied"),
        ("broken", "failed"),
        ("unverified", "unverified"),
    ],
)
def test_health_state_mapping(health: str, want: str) -> None:
    state, _ = lifecycle.health_state({"status": health})
    assert state == want


def test_old_receipt_without_lifecycle_still_derives() -> None:
    """Backward compat: a pre-16.1 receipt parses and gets a state view."""
    legacy = {
        "schema": "forge/InstallReceipt/v1",
        "receipt_id": "sha256:abc",
        "forge_id": "x",
        "operation": "install",
        "scope": "project",
        "target_root": "/tmp/x",
        "managed_files": [],
        "checks": [],
        "created_at": "2025-01-01T00:00:00+00:00",
        "status": "completed",
        "verification": {"status": "PASS"},
    }
    state, _ = lifecycle.receipt_state(legacy)
    assert state == "verified"
    block = lifecycle.receipt_block(legacy)
    assert block["schema"] == lifecycle.LIFECYCLE_SCHEMA
    jsonschema.validate({"lifecycle": block} | legacy, _load("InstallReceipt"))


def _load(name: str) -> dict:
    return json.loads((SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8"))


def test_receipt_with_lifecycle_conforms_schema(tmp_path: Path) -> None:
    receipt = service.install(scope="project", root=tmp_path, yes=True)
    assert receipt["status"] == "completed"
    lc = receipt["lifecycle"]
    assert lc["schema"] == lifecycle.LIFECYCLE_SCHEMA
    assert lc["state"] == "verified"
    jsonschema.validate(receipt, _load("InstallReceipt"))


def test_dry_run_lifecycle_is_planned(tmp_path: Path) -> None:
    plan = service.install(scope="project", root=tmp_path, dry_run=True)
    assert plan["lifecycle"]["state"] == "planned"


def test_status_and_doctor_carry_lifecycle(tmp_path: Path) -> None:
    service.install(scope="project", root=tmp_path, yes=True)
    st = service.status(scope="project", root=tmp_path)
    assert st["lifecycle"]["state"] == "ready"
    doc = service.doctor(scope="project", root=tmp_path)
    assert doc["lifecycle"]["schema"] == lifecycle.LIFECYCLE_SCHEMA
    assert doc["lifecycle"]["state"] in lifecycle.STATES


def test_status_unverified_install_is_unverified(tmp_path: Path) -> None:
    st = service.status(scope="project", root=tmp_path)
    assert st["lifecycle"]["state"] == "unverified"


def test_uninstall_receipt_carries_lifecycle(tmp_path: Path) -> None:
    service.install(scope="project", root=tmp_path, yes=True)
    r = service.uninstall(scope="project", root=tmp_path)
    assert r["lifecycle"]["schema"] == lifecycle.LIFECYCLE_SCHEMA
    assert r["lifecycle"]["state"] in lifecycle.STATES


def test_terminal_success_set() -> None:
    assert {"verified", "ready", "certified"} == lifecycle.TERMINAL_SUCCESS
    assert "applied" not in lifecycle.TERMINAL_SUCCESS
    assert "planned" not in lifecycle.TERMINAL_SUCCESS
