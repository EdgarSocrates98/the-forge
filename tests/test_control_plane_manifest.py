"""Control-plane capability manifest contract tests."""

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _version() -> str:
    source = (REPO / "src" / "theforge" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)', source)
    assert match
    return match.group(1)


def test_control_plane_manifest_matches_package_and_identity() -> None:
    manifest = json.loads((REPO / "forge.agentic.json").read_text(encoding="utf-8"))
    identity = json.loads((REPO / "forge.json").read_text(encoding="utf-8"))
    assert manifest["provider"] == identity["forge_id"]
    assert manifest["version"] == identity["version"] == _version()
    assert all("{cli}" in workflow["command"] for workflow in manifest["workflows"])
    assert any(workflow["read_only"] is False for workflow in manifest["workflows"])
