"""Contract tests for offline Engineering Excellence audit."""

from pathlib import Path

import pytest

from theforge.cli import render
from theforge.excellence import CapabilitySpec, RepositorySpec, audit_workspace


@pytest.mark.unit
def test_audit_is_stable_and_reports_evidence(tmp_path: Path) -> None:
    repository = tmp_path / "demo"
    (repository / "docs").mkdir(parents=True)
    (repository / "tests").mkdir()
    spec = RepositorySpec(
        "demo",
        "demo",
        (
            CapabilitySpec("docs", ("docs",)),
            CapabilitySpec("tests", ("tests",)),
            CapabilitySpec("mcp", ("mcp",)),
        ),
    )

    first = audit_workspace(tmp_path, (spec,))
    second = audit_workspace(tmp_path, (spec,))

    assert first == second
    assert first["schema"] == "theforge/EngineeringAudit/v1"
    assert first["summary"] == {
        "repositories": 1,
        "observed": 1,
        "unavailable": 0,
        "invalid": 0,
        "capabilities": 3,
        "capabilities_observed": 2,
        "capabilities_unknown": 1,
    }
    checks = {check["capability"]: check for check in first["repositories"][0]["checks"]}
    assert checks["docs"]["evidence"] == ["docs"]
    assert checks["mcp"]["state"] == "unknown"


@pytest.mark.unit
def test_missing_repository_is_explicit(tmp_path: Path) -> None:
    spec = RepositorySpec("missing", "missing", (CapabilitySpec("docs", ("docs",)),))

    data = audit_workspace(tmp_path, (spec,))

    assert data["summary"]["unavailable"] == 1
    assert data["repositories"][0]["state"] == "unavailable"
    assert data["repositories"][0]["checks"][0]["next_action"].startswith("restore repository")


@pytest.mark.security
def test_audit_rejects_repository_escape_and_external_marker(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-excellence"
    outside.mkdir()
    (outside / "secret").mkdir()
    spec = RepositorySpec(
        "escape",
        "../outside-excellence",
        (CapabilitySpec("secret", ("secret",)),),
    )

    data = audit_workspace(tmp_path, (spec,))

    assert data["summary"]["invalid"] == 1
    check = data["repositories"][0]["checks"][0]
    assert check["state"] == "invalid"
    assert check["evidence"] == []


@pytest.mark.unit
def test_text_render_has_no_control_or_terminal_escape_sequences(tmp_path: Path) -> None:
    data = audit_workspace(tmp_path, ())
    rendered = render.excellence_audit(data)

    assert "Engineering Excellence audit" in rendered
    assert "\\x1b" not in rendered
