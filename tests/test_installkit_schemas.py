"""Emitted documents validate against the forge/* v1 JSON Schemas.

The schemas in ``docs/portable-installation/schemas/`` are the contract;
this test proves the installkit emits conforming instances.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "docs" / "portable-installation" / "schemas"
KIT_PATH = ROOT / "scripts" / "installkit" / "forge_installkit.py"

spec = importlib.util.spec_from_file_location("forge_installkit", KIT_PATH)
kit = importlib.util.module_from_spec(spec)
sys.modules["forge_installkit"] = kit
spec.loader.exec_module(kit)


def _schema(name: str) -> dict:
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


def _spec() -> kit.ForgeSpec:
    def render(ctx):
        return {".agents/skills/demo/SKILL.md": b"# s\n",
                ".mcp-extra/x.json": b"{}\n"}
    return kit.ForgeSpec(
        forge_id="forge-schema", package="forge_schema",
        distribution="forge-schema", cli_name="forge-schema",
        python_spec=">=3.10", state_dir=".forge-schema",
        mcp_command=("forge-schema", "mcp", "serve"),
        mcp_server_name="forge-schema",
        marker_body="managed", render_assets=render, spawn_ok=False)


def _ctx(tmp_path: Path) -> kit.InstallContext:
    spec = _spec()
    state = tmp_path / spec.state_dir
    return kit.InstallContext(
        spec=spec, scope="project", root=tmp_path, state_dir=state,
        profile="full", hosts=("claude",), ledger=kit.Ledger.load(state))


def test_installation_manifest_conforms(tmp_path):
    doc = kit.manifest_for(
        _spec(), install_root=tmp_path / "i", venv=tmp_path / "v",
        version="1.2.3",
        source={"kind": "git-checkout", "path": "/x", "rev": "abc"},
        shim=tmp_path / "bin" / "x")
    jsonschema.validate(doc, _schema("InstallationManifest.schema.json"))


def test_install_receipt_conforms(tmp_path):
    ctx = _ctx(tmp_path)
    rcpt = kit.apply_install(ctx, approved=True)
    jsonschema.validate(rcpt, _schema("InstallReceipt.schema.json"))


def test_health_conforms(tmp_path):
    ctx = _ctx(tmp_path)
    kit.apply_install(ctx, approved=True)
    health = kit.doctor(ctx)
    jsonschema.validate(health, _schema("InstallationHealth.schema.json"))


def test_schema_files_exist():
    for name in ("InstallationManifest", "InstallReceipt",
                 "InstallationHealth", "WorkspaceInstall"):
        assert (SCHEMAS / f"{name}.schema.json").exists(), name


@pytest.mark.parametrize("scope", ["project", "workspace", "user"])
def test_every_scope_emits_contract_docs(tmp_path, scope, monkeypatch):
    monkeypatch.setenv("FORGE_HOME_OVERRIDE", str(tmp_path / "home"))
    spec_ = _spec()
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".git").mkdir()
    state = tmp_path / "home" / ".forge-schema" if scope == "user" \
        else root / spec_.state_dir
    ctx = kit.InstallContext(
        spec=spec_, scope=scope,
        root=tmp_path / "home" if scope == "user" else root,
        state_dir=state, profile="minimal", hosts=(),
        ledger=kit.Ledger.load(state))
    rcpt = kit.apply_install(ctx, approved=True)
    assert rcpt["schema"] == "forge/InstallReceipt/v1"
