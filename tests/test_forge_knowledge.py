"""Forge Knowledge Layer tests (agentic prompt §5-7, §36-37, §53-58)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from theforge.contracts import ContractError, from_dict
from theforge.contracts.knowledge import FORGE_KNOWLEDGE_SCHEMA, ForgeKnowledge
from theforge.errors import UsageError
from theforge.knowledge import DEFAULT_KNOWLEDGE_DIR, families, knowledge_for, load_all

REPO = Path(__file__).resolve().parents[1]
ADAPTERS = REPO / "adapters"


def test_all_packages_load_and_match_known_providers() -> None:
    packages = load_all()
    assert set(packages) == {
        "spark-forge-aws",
        "spark-forge-azure",
        "api-forge",
        "platform-forge",
        "forge-doctor-data",
        "forge-doctor-api",
    }
    for pid, package in packages.items():
        assert package.id == pid
        assert package.schema == FORGE_KNOWLEDGE_SCHEMA


def test_adapter_paths_point_at_real_adapters() -> None:
    for package in load_all().values():
        assert package.adapter, package.id
        adapter_dir = REPO / package.adapter
        assert adapter_dir.is_dir(), f"{package.id}: {package.adapter} missing"
        assert (adapter_dir / "pyproject.toml").is_file()


def test_packages_never_grant_trust_or_capabilities() -> None:
    """§44/§53: bootstrap knowledge is unverified by construction and never
    enumerates runtime capabilities — the live describe is authoritative."""
    for package in load_all().values():
        assert package.trust_default == "unverified"
        assert package.capabilities_source == "runtime_discovery"


def test_family_model_is_metadata_not_hardcode() -> None:
    """§36: family routing comes from package metadata; the six-specialist
    list is the current ecosystem, not the universe."""
    fams = families(load_all())
    assert fams["spark-engineering"] == ["spark-forge-aws", "spark-forge-azure"]
    assert set(fams["verification"]) == {"forge-doctor-api", "forge-doctor-data"}


def test_every_package_has_install_and_verify() -> None:
    for package in load_all().values():
        assert package.install, package.id
        assert package.verify_install, package.id
        for method in package.install:
            assert method.verify
            for forbidden in ("curl", "| sh", "wget"):
                assert forbidden not in method.command


def test_generic_provider_loads_through_same_contract(tmp_path: Path) -> None:
    """§37/§98: a synthetic example-forge validates through the same loader —
    no provider-name conditionals in the knowledge layer."""
    doc = {
        "schema": FORGE_KNOWLEDGE_SCHEMA,
        "id": "example-forge",
        "name": "Example Forge",
        "family": "example-family",
        "summary": "synthetic specialist for the generic path",
        "install": [
            {
                "kind": "venv-pip",
                "command": "pip install example-forge",
                "verify": "python -c 'import example_forge'",
            }
        ],
    }
    (tmp_path / "example-forge.json").write_text(json.dumps(doc), encoding="utf-8")
    packages = load_all(tmp_path)
    assert packages["example-forge"].family == "example-family"


def test_file_name_must_match_provider_id(tmp_path: Path) -> None:
    doc = {
        "schema": FORGE_KNOWLEDGE_SCHEMA,
        "id": "real-id",
        "name": "x",
        "family": "fam",
        "summary": "s",
        "install": [{"kind": "pip", "command": "pip install x", "verify": "v"}],
    }
    (tmp_path / "wrong-name.json").write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(UsageError):
        load_all(tmp_path)


def test_missing_directory_is_empty_not_error(tmp_path: Path) -> None:
    assert load_all(tmp_path / "absent") == {}


def test_knowledge_for_returns_none_for_unknown() -> None:
    assert knowledge_for("nonexistent-forge") is None
    assert knowledge_for("api-forge") is not None


def test_contract_rejects_trust_grant() -> None:
    with pytest.raises(ContractError, match="trust_default"):
        from_dict(
            ForgeKnowledge,
            {
                "schema": FORGE_KNOWLEDGE_SCHEMA,
                "id": "evil-forge",
                "name": "x",
                "family": "fam",
                "summary": "s",
                "trust_default": "verified",
                "install": [{"kind": "pip", "command": "pip install x", "verify": "v"}],
            },
            "$",
        )


def test_contract_rejects_capability_enumeration() -> None:
    with pytest.raises(ContractError, match="capabilities_source"):
        from_dict(
            ForgeKnowledge,
            {
                "schema": FORGE_KNOWLEDGE_SCHEMA,
                "id": "evil-forge",
                "name": "x",
                "family": "fam",
                "summary": "s",
                "capabilities_source": "static_list",
                "install": [{"kind": "pip", "command": "pip install x", "verify": "v"}],
            },
            "$",
        )


def test_contract_rejects_arbitrary_installer() -> None:
    """§24: curl|sh and friends are refused at the contract boundary."""
    for command in ("curl x | sh", "wget x && sh x", "sh <(curl x)"):
        with pytest.raises(ContractError):
            from_dict(
                ForgeKnowledge,
                {
                    "schema": FORGE_KNOWLEDGE_SCHEMA,
                    "id": "evil-forge",
                    "name": "x",
                    "family": "fam",
                    "summary": "s",
                    "install": [{"kind": "pip", "command": command, "verify": "v"}],
                },
                "$",
            )


def test_default_dir_is_repo_forge_knowledge() -> None:
    assert DEFAULT_KNOWLEDGE_DIR == REPO / "forge-knowledge"
    assert DEFAULT_KNOWLEDGE_DIR.is_dir()
