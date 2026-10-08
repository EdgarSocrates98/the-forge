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


# --- ``theforge knowledge check`` (freshness vs. the live registry, §51-52) ---


def _manifest(path: Path, pid: str, version: str) -> Path:
    manifest = {
        "schema": "theforge/ForgeManifest/v1",
        "id": pid,
        "version": version,
        "protocols": ["forge/v1"],
        "ops": ["describe", "health"],
        "capabilities": [
            {
                "id": "demo.echo",
                "actions": ["review"],
                "default_action": "review",
                "state": "supported",
                "operation_class": "read_only",
            }
        ],
    }
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def _entry(pid: str, manifest: Path) -> dict:
    import sys

    from helpers import PROVIDERS

    return {
        "id": pid,
        "argv": [sys.executable, str(PROVIDERS / "fixture_forge.py"), str(manifest)],
        "trust": "local",
    }


def _check(capsys: pytest.CaptureFixture[str], root: Path) -> dict[str, dict]:
    from theforge.cli.main import main

    code = main(["knowledge", "check", "--root", str(root), "--json"])
    out, _ = capsys.readouterr()
    assert code == 0
    return {p["id"]: p for p in json.loads(out)["packages"]}


def test_knowledge_check_fresh_and_not_installed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    import dataclasses

    import theforge.knowledge as knowledge_mod
    from helpers import make_workspace
    from theforge.contracts.manifest import ForgeManifest
    from theforge.registry.surface import surface_fingerprint

    manifest_path = _manifest(tmp_path / "apiforge.json", "api-forge", "0.3.0")
    make_workspace(tmp_path, [_entry("api-forge", manifest_path)])
    # Real packages now record measured surfaces; a fixture manifest can't
    # reproduce them, so the package under test borrows the fixture's own
    # fingerprint — the check then exercises a true surface match.
    fixture_surface = surface_fingerprint(
        from_dict(ForgeManifest, json.loads(manifest_path.read_text()), "$")
    )
    packages = load_all()
    packages["api-forge"] = dataclasses.replace(
        packages["api-forge"], tested_surface=fixture_surface
    )
    monkeypatch.setattr(knowledge_mod, "load_all", lambda directory=None: packages)
    rows = _check(capsys, tmp_path)
    api = rows["api-forge"]
    assert api["status"] == "fresh"
    assert api["version"] == "match" and api["installed_version"] == "0.3.0"
    assert api["surface"] == "match"
    assert rows["spark-forge-aws"]["status"] == "not_installed"


def test_knowledge_check_version_drift(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from helpers import make_workspace

    make_workspace(
        tmp_path,
        [_entry("api-forge", _manifest(tmp_path / "apiforge.json", "api-forge", "9.9.9"))],
    )
    api = _check(capsys, tmp_path)["api-forge"]
    assert api["status"] == "drift"
    assert api["version"] == "drift" and api["installed_version"] == "9.9.9"


def test_knowledge_check_surface_drift(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from helpers import make_workspace

    # platform-forge's package records a measured surface fingerprint; a fixture
    # manifest cannot reproduce it, so version matches but surface drifts.
    make_workspace(
        tmp_path,
        [
            _entry(
                "platform-forge",
                _manifest(tmp_path / "pf.json", "platform-forge", "0.1.0"),
            )
        ],
    )
    pf = _check(capsys, tmp_path)["platform-forge"]
    assert pf["status"] == "drift"
    assert pf["version"] == "match" and pf["surface"] == "drift"


def test_knowledge_check_unavailable(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from helpers import bad_entry, make_workspace

    make_workspace(tmp_path, [bad_entry("describe-refused", "spark-forge-aws")])
    rows = _check(capsys, tmp_path)
    assert rows["spark-forge-aws"]["status"] == "unavailable"
