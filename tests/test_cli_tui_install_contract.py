"""Executable guard for the ecosystem CLI/TUI/install matrix."""

from __future__ import annotations

from scripts.cli_install_matrix import collect


def test_all_official_projects_have_a_checked_surface() -> None:
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
    matrix = collect()
    portal = next(row for row in matrix["projects"] if row["repo"] == "forge-portal")
    assert portal["surface"] == "home+tui+wizard"
    assert portal["install"] == "tools/portal-cli.mjs"
