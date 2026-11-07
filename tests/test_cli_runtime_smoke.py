from __future__ import annotations

import scripts.cli_runtime_smoke as smoke
from scripts.cli_runtime_smoke import CASES, FLAGS, collect, scrubbed_environment


def test_runtime_smoke_manifest_covers_fourteen_repositories_and_two_safe_flags():
    assert len(CASES) == 14
    assert len({case.repo for case in CASES}) == 14
    assert FLAGS == ("--version", "--help")
    assert all(case.args for case in CASES)


def test_runtime_smoke_scrubs_ambient_credentials(monkeypatch):
    monkeypatch.setenv("FORGE_RUNTIME_TEST_TOKEN", "should-not-propagate")
    monkeypatch.setenv("PATH", "kept-for-tool-discovery")
    env = scrubbed_environment()
    assert "FORGE_RUNTIME_TEST_TOKEN" not in env
    assert env["PATH"] == "kept-for-tool-discovery"


def test_runtime_smoke_collects_the_full_matrix_without_launching_processes(monkeypatch):
    monkeypatch.setattr(
        smoke,
        "run_case",
        lambda case, flag, timeout_s, env: {
            "repo": case.repo,
            "flag": flag,
            "status": "PASS",
        },
    )
    result = collect(timeout_s=0.01)
    assert result["schema"] == "forge/cli-runtime-smoke/v1"
    assert result["repository_count"] == 14
    assert result["check_count"] == 28
    assert result["status"] == "PASS", result
