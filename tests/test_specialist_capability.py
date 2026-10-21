"""lf-0027: theforge/SpecialistCapability/v1 contract validation tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from theforge.contracts import (
    SPECIALIST_CAPABILITY_SCHEMA,
    ContractError,
    SpecialistCapability,
    from_dict,
    to_dict,
)

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"


def _doc(**over):
    doc = {
        "schema": "theforge/SpecialistCapability/v1",
        "specialist": {
            "id": "data-sentinel",
            "version": "1.0.0",
            "domain": "data-diagnostics",
        },
        "capabilities": [
            {
                "id": "data.detect-schema",
                "description": "infer column types from samples",
                "version": "1.0.0",
                "entrypoint": ["{cli}", "capabilities", "detect-schema"],
                "execution_mode": "local",
                "risk": "read_only",
                "requires": ["python>=3.11"],
                "optional_deps": [],
                "permissions": ["fs:read"],
                "network": False,
                "external_cost": "none",
                "timeout_s": 30,
                "limitations": ["sampled inference only"],
                "discovery_mode": "manifest",
                "verification_mode": "probe",
            },
            {
                "id": "data.profile-cloud",
                "description": "remote dataset profile",
                "execution_mode": "remote",
                "risk": "external_read",
                "network": True,
                "external_cost": "metered",
            },
        ],
        "health": {"supported": True, "detail": "forge/v1 health op"},
        "handoff": {"supported": True},
    }
    doc.update(over)
    return doc


def test_valid_document_parses_and_roundtrips():
    manifest = from_dict(SpecialistCapability, _doc())
    assert manifest.specialist.id == "data-sentinel"
    assert manifest.capabilities[0].id == "data.detect-schema"
    assert manifest.capabilities[0].entrypoint == ["{cli}", "capabilities", "detect-schema"]
    assert manifest.capabilities[1].external_cost == "metered"
    assert manifest.health.supported and manifest.handoff.supported
    assert from_dict(SpecialistCapability, to_dict(manifest)) == manifest


def test_schema_pinned_to_theforge_namespace():
    """The spec's ``forge/SpecialistCapability/v1`` maps to ``theforge/`` here —
    the foreign schema id is rejected, not silently accepted."""
    assert SPECIALIST_CAPABILITY_SCHEMA == "theforge/SpecialistCapability/v1"
    with pytest.raises(ContractError):
        from_dict(SpecialistCapability, _doc(schema="forge/SpecialistCapability/v1"))


def test_specialist_id_must_match_provider_id():
    with pytest.raises(ContractError):
        from_dict(
            SpecialistCapability,
            _doc(specialist={"id": "Bad ID", "version": "1.0.0"}),
        )


def test_specialist_version_semver_or_runtime_detected():
    with pytest.raises(ContractError):
        from_dict(
            SpecialistCapability,
            _doc(specialist={"id": "data-sentinel", "version": "v1.beta"}),
        )
    manifest = from_dict(
        SpecialistCapability,
        _doc(specialist={"id": "data-sentinel", "version": "runtime-detected"}),
    )
    assert manifest.specialist.version == "runtime-detected"


def test_capability_id_requires_dotted_convention():
    with pytest.raises(ContractError):
        from_dict(
            SpecialistCapability,
            _doc(capabilities=[{"id": "nodot"}]),
        )
    with pytest.raises(ContractError):
        from_dict(
            SpecialistCapability,
            _doc(capabilities=[{"id": "data.detect_schema"}]),  # '_' not allowed
        )


def test_duplicate_capability_ids_rejected():
    with pytest.raises(ContractError):
        from_dict(
            SpecialistCapability,
            _doc(capabilities=[{"id": "a.b"}, {"id": "a.b"}]),
        )


def test_closed_vocabularies_rejected():
    with pytest.raises(ContractError):
        from_dict(
            SpecialistCapability,
            _doc(capabilities=[{"id": "a.b", "execution_mode": "cloud-read"}]),
        )
    with pytest.raises(ContractError):
        from_dict(
            SpecialistCapability,
            _doc(capabilities=[{"id": "a.b", "external_cost": "free"}]),
        )
    with pytest.raises(ContractError):
        from_dict(
            SpecialistCapability,
            _doc(capabilities=[{"id": "a.b", "verification_mode": "magic"}]),
        )


def test_local_capability_cannot_require_network():
    with pytest.raises(ContractError):
        from_dict(
            SpecialistCapability,
            _doc(capabilities=[{"id": "a.b", "execution_mode": "local", "network": True}]),
        )


def test_timeout_must_be_positive():
    with pytest.raises(ContractError):
        from_dict(
            SpecialistCapability,
            _doc(capabilities=[{"id": "a.b", "timeout_s": 0}]),
        )


def test_generated_schema_file_exists_and_matches_shape():
    schema_path = SCHEMAS_DIR / "SpecialistCapability.schema.json"
    assert schema_path.is_file(), "run python -m theforge.contracts.schema schemas"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    props = schema["properties"]
    assert "specialist" in props and "capabilities" in props
    assert props["specialist"]["properties"]["id"]["pattern"] == r"^[a-z][a-z0-9-]*$"
    cap = props["capabilities"]["items"]["properties"]
    assert cap["id"]["pattern"] == r"^[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)+$"
    assert cap["execution_mode"]["enum"] == ["local", "remote", "hybrid"]
    assert cap["external_cost"]["enum"] == ["none", "possible", "metered", "unknown"]
    assert cap["verification_mode"]["enum"] == ["self-declared", "handshake", "probe"]
