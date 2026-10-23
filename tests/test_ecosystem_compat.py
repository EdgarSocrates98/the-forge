"""forge/EcosystemCompatibility/v1 — committed manifest conforms to schema.

Cycle 8 (ecosystem-2026): the manifest at the repo root declares the certified
component combination and the supported contract-major windows. These tests
prove (a) the manifest validates against the hand-written JSON Schema, (b) the
declared component versions match the versions the projects actually declare,
and (c) the Python contract rejects malformed documents.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import jsonschema
import pytest

from theforge.contracts.base import ContractError
from theforge.install.compatibility import (
    ECOSYSTEM_SCHEMA,
    load_manifest,
    parse_manifest,
)

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "ecosystem-compatibility.json"
SCHEMA_PATH = (
    ROOT / "docs" / "portable-installation" / "schemas" / "EcosystemCompatibility.schema.json"
)


@pytest.fixture()
def manifest():
    return load_manifest(MANIFEST_PATH)


def test_committed_manifest_conforms_to_json_schema(manifest):
    doc = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    jsonschema.validate(doc, json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))


def test_manifest_declares_the_nine_components(manifest):
    assert {c.component for c in manifest.components} == {
        "the-forge",
        "api-forge",
        "platform-forge",
        "spark-forge-aws",
        "spark-forge-azure",
        "forge-doctor-data",
        "forge-doctor-api",
        "forge-cli",
        "forge-portal",
    }


def _declared_version(repo: Path, source: str) -> str | None:
    """Version the repo itself declares in `source` — never inferred."""
    if source == "pyproject.toml":
        path = repo / "pyproject.toml"
        if not path.is_file():
            return None
        project = tomllib.loads(path.read_text(encoding="utf-8"))
        return (project.get("project") or {}).get("version") or (
            (project.get("tool") or {}).get("poetry") or {}
        ).get("version")
    if source == "package.json":
        path = repo / "package.json"
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8")).get("version")
    return None


def test_declared_versions_match_project_files(manifest):
    """Zero fictional versions: each declared version is what that repo
    declares in its own version file. the-forge is always checked (it is
    this repo); siblings are checked when their checkout is present."""
    workspace = ROOT.parent
    checked = 0
    for component in manifest.components:
        source = component.source or "pyproject.toml"
        repo = workspace / component.component if component.component != "the-forge" else ROOT
        if not repo.is_dir():
            continue  # sibling checkout absent — nothing to compare against
        declared = _declared_version(repo, source)
        if declared is None:
            continue
        assert component.version == declared, (
            f"{component.component}: manifest {component.version} != {source} {declared}"
        )
        checked += 1
    assert checked >= 1  # the-forge itself must always be verified


def test_forge_json_distribution_matches_pyproject_name():
    """`forge.json.distribution` is the PyPI name `--dist` validates against.
    A stale value makes the guard reject the real package and accept a
    homonymous foreign one — the exact name-confusion path §12.1 targets.
    Each repo with a forge.json is checked when its checkout is present."""
    import re

    def canon(name: str) -> str:
        return re.sub(r"[-_.]+", "-", name.strip().lower())

    workspace = ROOT.parent
    checked = 0
    for repo_dir in sorted(workspace.iterdir()):
        forge_json = repo_dir / "forge.json"
        pyproject = repo_dir / "pyproject.toml"
        if not (repo_dir.is_dir() and forge_json.is_file() and pyproject.is_file()):
            continue
        dist = json.loads(forge_json.read_text(encoding="utf-8")).get("distribution")
        project = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        name = (project.get("project") or {}).get("name") or (
            (project.get("tool") or {}).get("poetry") or {}
        ).get("name")
        if not dist or not name:
            continue
        assert canon(dist) == canon(name), (
            f"{repo_dir.name}: forge.json distribution {dist!r} != pyproject name {name!r}"
        )
        checked += 1
    assert checked >= 1  # the-forge's own forge.json must always be verified


def test_check_verdicts(manifest):
    assert manifest.check("the-forge", "0.6.2") == "certified"
    assert manifest.check("the-forge", "9.9.9") == "incompatible"
    assert manifest.check("no-such-component", "0.5.0") == "unknown"


def test_contract_supported_windows(manifest):
    assert manifest.contract_supported("specialist_manifest", 1)
    assert not manifest.contract_supported("specialist_manifest", 2)
    # forge/PortalApi/1 is a real contract served by `<cli> portal`.
    assert manifest.contract_supported("portal_api", 1)
    assert not manifest.contract_supported("portal_api", 2)
    assert manifest.contract_supported("portal_assets", 1)
    assert not manifest.contract_supported("absent_family", 1)


def test_unversioned_family_declared_without_range():
    """contract=None is the honest unversioned state — ranges are rejected there."""
    doc = _base_doc()
    doc["contracts"].append({"family": "future_contract", "contract": None})
    manifest = parse_manifest(doc)
    assert not manifest.contract_supported("future_contract", 1)


def _base_doc() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_rejects_latest_version():
    doc = _base_doc()
    doc["components"][0]["version"] = "latest"
    with pytest.raises(ContractError):
        parse_manifest(doc)


def test_rejects_bad_scheme_version():
    doc = _base_doc()
    doc["components"][0]["version"] = "1.0.0rc1"  # valid pep440, invalid semver
    with pytest.raises(ContractError):
        parse_manifest(doc)


def test_rejects_range_on_unversioned_family():
    doc = _base_doc()
    doc["contracts"].append({"family": "unversioned_thing", "contract": None, "min_major": 1})
    with pytest.raises(ContractError):
        parse_manifest(doc)


def test_rejects_duplicate_components():
    doc = _base_doc()
    doc["components"].append(dict(doc["components"][0]))
    with pytest.raises(ContractError):
        parse_manifest(doc)


def test_rejects_wrong_schema_id():
    doc = _base_doc()
    doc["schema"] = "forge/EcosystemCompatibility/v2"
    with pytest.raises(ContractError):
        parse_manifest(doc)


def test_schema_constant():
    assert ECOSYSTEM_SCHEMA == "forge/EcosystemCompatibility/v1"
