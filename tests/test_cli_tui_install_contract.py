"""Executable guard for the ecosystem CLI/TUI/install matrix."""

from __future__ import annotations

import pytest
from scripts.cli_install_matrix import PROJECTS, WORKSPACE, collect


def _require_federated_workspace() -> None:
    """Run the 14-repository gate only where its inputs are checked out.

    The local release workspace contains every sibling checkout.  GitHub's
    single-repository jobs intentionally clone only ``the-forge``; treating
    absent siblings there as product failures makes CI prove an impossible
    topology instead of the code under test.
    """
    missing = [item["repo"] for item in PROJECTS if not (WORKSPACE / item["repo"]).is_dir()]
    if missing:
        pytest.skip("federated CLI matrix requires sibling checkouts: " + ", ".join(missing))


def test_all_official_projects_have_a_checked_surface() -> None:
    _require_federated_workspace()
    matrix = collect()
    assert matrix["repository_count"] == 14
    assert matrix["status"] == "PASS", matrix["errors"]
    assert {row["repo"] for row in matrix["projects"]} == {
        "api-forge",
        "code-atlas-forge",
        "data-sentinel-forge",
        "forge-agent-bridge",
        "forge-cli",
        "forge-doctor-api",
        "forge-doctor-data",
        "forge-lens",
        "forge-portal",
        "platform-forge",
        "product-forge",
        "spark-forge-aws",
        "spark-forge-azure",
        "the-forge",
    }


def test_portal_keeps_web_primary_surface_and_cli_companion() -> None:
    _require_federated_workspace()
    matrix = collect()
    portal = next(row for row in matrix["projects"] if row["repo"] == "forge-portal")
    assert portal["surface"] == "home+tui+wizard"
    assert portal["install"] == "tools/portal-cli.mjs"
