"""Resource Catalog Contract (Wave 03) — typed entries on AgenticManifest.

Covers the contract vocabulary, additive parsing of ``resources`` inside
``forge/SpecialistAgenticManifest/v1`` and the catalog gate: every declared
resource resolves to a verifiable location (or an explicit unavailable
state) without loading its contents.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from theforge.contracts.base import ContractError, from_dict
from theforge.contracts.specialist import (
    AGENTIC_MANIFEST_SCHEMA,
    AgenticManifest,
    ResourceEntry,
)
from theforge.specialists import catalog_resources, verify_resource_locations

WORKSPACE = Path(__file__).resolve().parents[2]


def _manifest(**over) -> AgenticManifest:
    base = {
        "schema": AGENTIC_MANIFEST_SCHEMA,
        "provider": "forge-x",
        "version": "0.0.1",
        "cli": "forge-x",
        "cli_entry": "forge_x.cli:main",
    }
    base.update(over)
    return from_dict(AgenticManifest, base)


def test_resource_entry_minimal() -> None:
    res = ResourceEntry(id="sdd-check", kind="command", location="src/forge_x/cli.py")
    assert res.availability == "available"
    assert res.load_policy == "lazy"


def test_resource_entry_rejects_unknown_kind() -> None:
    with pytest.raises(ContractError, match="unknown kind"):
        ResourceEntry(id="x", kind="embedding", location="a")


def test_available_resource_requires_location() -> None:
    with pytest.raises(ContractError, match="verifiable location"):
        ResourceEntry(id="x", kind="knowledge")


def test_unavailable_requires_reason() -> None:
    with pytest.raises(ContractError, match="unavailable_reason"):
        ResourceEntry(id="x", kind="eval", availability="unavailable")


@pytest.mark.parametrize(
    "loc", ["../escape.md", "/abs/path.md", "C:/win.md", "a/../../b.md"]
)
def test_location_must_stay_inside_checkout(loc: str) -> None:
    with pytest.raises(ContractError, match="relative path"):
        ResourceEntry(id="x", kind="knowledge", location=loc)


def test_manifest_parses_resources_additively() -> None:
    manifest = _manifest(
        resources=[
            {
                "id": "ontology",
                "kind": "knowledge",
                "location": "knowledge/ontology.yaml",
                "domain": "spark",
                "tags": ["sdd", "glue"],
                "sha256": "0" * 64,
            }
        ]
    )
    assert manifest.resources[0].id == "ontology"
    assert manifest.resources[0].domain == "spark"


def test_manifest_without_resources_still_parses() -> None:
    assert _manifest().resources == []


def test_duplicate_resource_ids_rejected() -> None:
    with pytest.raises(ContractError, match="duplicate"):
        _manifest(
            resources=[
                {"id": "a", "kind": "knowledge", "location": "x"},
                {"id": "a", "kind": "rule", "location": "y"},
            ]
        )


def test_typed_resource_supersedes_legacy_name(tmp_path: Path) -> None:
    (tmp_path / "s.md").write_text("x", encoding="utf-8")
    manifest = _manifest(
        skills=["sdd"],
        resources=[{"id": "sdd", "kind": "skill", "location": "s.md"}],
    )
    entries = {r.id: r for r in catalog_resources(manifest)}
    assert entries["sdd"].location == "s.md"  # typed entry wins, not promoted
    assert verify_resource_locations(manifest, tmp_path) == []


def test_catalog_promotes_legacy_entries(tmp_path: Path) -> None:
    manifest = _manifest(skills=["sdd"], agents=["reviewer"])
    kinds = {(r.id, r.kind) for r in catalog_resources(manifest)}
    assert ("sdd", "skill") in kinds
    assert ("reviewer", "agent") in kinds


def test_verify_locations_reports_missing(tmp_path: Path) -> None:
    (tmp_path / "real.md").write_text("x", encoding="utf-8")
    manifest = _manifest(
        resources=[
            {"id": "ok", "kind": "knowledge", "location": "real.md"},
            {"id": "gone", "kind": "knowledge", "location": "missing.md"},
        ]
    )
    issues = verify_resource_locations(manifest, tmp_path)
    assert issues == ["gone: declared location missing: missing.md"]


def test_verify_locations_detects_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.md"
    outside.write_text("x", encoding="utf-8")
    (tmp_path / "link.md").symlink_to(outside)
    manifest = _manifest(
        resources=[{"id": "esc", "kind": "knowledge", "location": "link.md"}]
    )
    try:
        issues = verify_resource_locations(manifest, tmp_path)
        assert any("escapes checkout" in i for i in issues)
    finally:
        outside.unlink(missing_ok=True)


def _workspace_checkouts() -> list[Path]:
    from theforge import _installkit as kit

    if not WORKSPACE.is_dir():
        return []
    return [
        m
        for m in kit.discover_projects(WORKSPACE)
        if (m / "forge.agentic.json").is_file()
    ]


@pytest.mark.skipif(
    not _workspace_checkouts(),
    reason="requires sibling forge checkouts (FORJAS workspace layout)",
)
def test_workspace_manifest_resources_verify() -> None:
    """Every typed resource declared by a sibling checkout resolves."""
    for checkout in _workspace_checkouts():
        doc = json.loads((checkout / "forge.agentic.json").read_text(encoding="utf-8"))
        manifest = from_dict(AgenticManifest, doc)
        issues = verify_resource_locations(manifest, checkout)
        assert not issues, f"{checkout.name}: {issues}"
