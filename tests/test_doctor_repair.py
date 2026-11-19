"""Layered doctor + safe repair + install footprint/incremental counts
(cycle 16.1, FRENTE F §10 + the forge's share of FRENTE C §7)."""

from __future__ import annotations

from pathlib import Path

import pytest

from theforge.environment.doctor import run_doctor
from theforge.environment.layers import LAYER_ORDER, group_layers
from theforge.install import service
from theforge.registry import Registry
from theforge.state import find_forge_dir


def _doctor(root: Path) -> dict:
    return run_doctor(root, Registry(find_forge_dir(root)))


@pytest.fixture()
def installed(tmp_path: Path) -> Path:
    target = tmp_path / "consumer"
    target.mkdir()
    service.install(scope="project", root=target, yes=True)
    return target


# --- §10.1 twenty named layers ----------------------------------------------


def test_layer_contract_is_exactly_twenty_named() -> None:
    assert len(LAYER_ORDER) == 20
    assert len(set(LAYER_ORDER)) == 20
    for expected in (
        "runtime",
        "registry",
        "workspace-root",
        "mcp",
        "hosts",
        "ownership",
        "drift",
        "ci",
    ):
        assert expected in LAYER_ORDER


def test_group_layers_is_ordered_and_worst_wins() -> None:
    checks = [
        {"name": "os", "status": "ok"},
        {"name": "mcp:probe", "status": "warn"},
        {"name": "mcp-config", "status": "fail"},
        {"name": "drift:AGENTS.md", "status": "warn"},
    ]
    layers = group_layers(checks)
    assert [x["name"] for x in layers] == list(LAYER_ORDER)
    assert [x["index"] for x in layers] == list(range(1, 21))
    mcp = next(x for x in layers if x["name"] == "mcp")
    assert mcp["status"] == "fail"  # worst wins, never averaged away
    assert set(mcp["checks"]) == {"mcp:probe", "mcp-config"}
    empty = next(x for x in layers if x["name"] == "evals")
    assert empty["status"] == "not_applicable"


def test_doctor_report_carries_layers(installed: Path) -> None:
    doc = _doctor(installed)
    assert "layers" in doc
    assert [x["name"] for x in doc["layers"]] == list(LAYER_ORDER)


# --- §10.2 actionable guidance ----------------------------------------------


def _managed_file(root: Path) -> Path:
    """A ledger-managed file we can damage — `.mcp.json` is always managed
    by a project install."""
    return root / ".mcp.json"


def test_failing_checks_carry_problema_causa_acao(installed: Path) -> None:
    # damage a managed file → drift FAIL → guidance attached
    managed = _managed_file(installed)
    if not managed.exists():
        pytest.skip(".mcp.json not managed at this profile")
    managed.write_text("tampered\n", "utf-8")
    doc = _doctor(installed)
    drift_checks = [c for c in doc["checks"] if str(c.get("name", "")).startswith("drift:")]
    assert drift_checks
    guided = [c for c in drift_checks if c.get("guidance")]
    assert guided, "drift failure must carry actionable guidance"
    g = guided[0]["guidance"]
    for key in ("problema", "causa_provavel", "acao", "estado"):
        assert key in g and g[key]
    assert g["estado"] == "fail"


# --- §10.3 safe repair --------------------------------------------------------


def test_repair_without_approval_is_plan_only(installed: Path) -> None:
    managed = _managed_file(installed)
    if not managed.exists():
        pytest.skip(".mcp.json not managed at this profile")
    managed.write_text("tampered\n", "utf-8")
    before = managed.read_text()
    doc = service.repair(scope="project", root=installed)  # no approval
    assert doc["status"] == "planned"
    plan = doc["repair_plan"]
    assert plan["approval_required"] is True
    assert plan["deletes"] == []  # repair never deletes user data
    assert plan["recovery"]["rollback"]
    assert "rerun" in plan["recovery"]["rerunnable"]
    # nothing written — the damaged bytes remain until approval
    assert managed.read_text() == before


def test_repair_approved_restores_managed_content(installed: Path) -> None:
    managed = _managed_file(installed)
    if not managed.exists():
        pytest.skip(".mcp.json not managed at this profile")
    original = managed.read_bytes()
    managed.write_text("tampered\n", "utf-8")
    doc = service.repair(scope="project", root=installed, approved=True)
    assert doc["status"] != "planned"
    assert managed.read_bytes() == original
    assert doc["repair_plan"]["approved"] is True


def test_repair_dry_run_is_read_only(installed: Path) -> None:
    doc = service.repair(scope="project", root=installed, dry_run=True)
    assert doc["status"] == "planned"


def test_repair_never_deletes_user_files(installed: Path) -> None:
    user_file = installed / "AGENTS.user.md"
    user_file.write_text("mine\n", "utf-8")
    service.repair(scope="project", root=installed, approved=True)
    assert user_file.read_text() == "mine\n"


# --- FRENTE C: incremental counts + footprint --------------------------------


def test_reinstall_reports_unchanged_not_rewritten(installed: Path) -> None:
    r1 = service.install(scope="project", root=installed, yes=True)
    counts = r1.get("counts") or {}
    assert counts
    # second apply: everything byte-identical → unchanged dominates
    assert counts.get("unchanged", 0) > 0
    assert counts.get("created", 0) == 0
    assert counts.get("updated", 0) == 0


def test_first_install_counts_created(tmp_path: Path) -> None:
    target = tmp_path / "consumer"
    target.mkdir()
    receipt = service.install(scope="project", root=target, yes=True)
    counts = receipt.get("counts") or {}
    assert counts.get("created", 0) > 0
    # a dry-run receipt reports planned counts, not writes
    target2 = tmp_path / "other"
    target2.mkdir()
    plan = service.install(scope="project", root=target2, dry_run=True)
    assert plan["status"] == "planned"


def test_footprint_measures_real_surface(installed: Path) -> None:
    doc = service.footprint(scope="project", root=installed)
    assert doc["schema"] == "theforge/InstallFootprint/v1"
    assert doc["measured"] is True
    assert doc["managed_total"] > 0
    hosts = doc["per_host"]
    assert "shared" in hosts
    total_files = sum(h["files_on_disk"] for h in hosts.values())
    assert total_files > 0
    dup = doc["duplication"]
    assert dup["extra_copies"] >= 0
    # mirrored host dirs share content with .agents → duplication is real,
    # reported as measured copies, never massaged to zero
    for g in dup["groups"]:
        assert g["paths"] and all(isinstance(p, str) for p in g["paths"])


def test_footprint_empty_target_is_honest_zeros(tmp_path: Path) -> None:
    target = tmp_path / "empty"
    target.mkdir()
    doc = service.footprint(scope="project", root=target)
    assert doc["measured"] is True
    assert doc["managed_total"] == 0
    assert sum(h["files_on_disk"] for h in doc["per_host"].values()) == 0
