"""Control-plane tests: lifecycle, host detection, activation, delegation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from theforge import activation, delegation, host_detect, specialists
from theforge.contracts.base import ContractError
from theforge.contracts.specialist import (
    AgenticManifest,
    DelegationEntry,
    SpecialistLifecycle,
    transition,
)

# -- lifecycle ---------------------------------------------------------------


def test_lifecycle_valid_transition():
    lc = SpecialistLifecycle(provider="p", installation_state="DISCOVERED")
    assert lc.advance("NOT_INSTALLED").installation_state == "NOT_INSTALLED"


def test_lifecycle_invalid_transition_raises():
    lc = SpecialistLifecycle(provider="p", installation_state="DISCOVERED")
    with pytest.raises(ContractError):
        lc.advance("READY")  # skipping states is not a transition


def test_lifecycle_unknown_state_raises():
    with pytest.raises(ContractError):
        transition("READY", "BOGUS")


def test_removed_is_terminal():
    assert transition("UNINSTALLING", "REMOVED") == "REMOVED"
    with pytest.raises(ContractError):
        transition("REMOVED", "DISCOVERED")


# -- host detection ----------------------------------------------------------


def test_host_detect_env_marker_is_running(tmp_path):
    result = host_detect.detect_hosts(project_root=tmp_path, env={"DEVIN_CLI": "1"})
    devin = result.for_host("devin")
    assert devin is not None and devin.running and devin.detected
    assert result.current == "devin"


def test_host_detect_config_dirs(tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "skills").mkdir()
    result = host_detect.detect_hosts(project_root=tmp_path, env={})
    claude = result.for_host("claude")
    assert claude is not None
    assert any(e.kind == "config_dir" for e in claude.evidence)


def test_host_detect_no_evidence(tmp_path):
    result = host_detect.detect_hosts(project_root=tmp_path, env={})
    copilot = result.for_host("copilot")
    assert copilot is not None and not copilot.detected
    assert copilot.confidence_basis == "no evidence"
    assert result.current is None


# -- activation --------------------------------------------------------------


def test_activation_restart_required_for_skills():
    plan = activation.build_activation_plan(
        host="devin",
        provider="p",
        scope="project",
        components=["skills"],
        writes=[".devin/skills/x"],
    )
    receipt = activation.evaluate_activation(
        plan, host_is_current_session=True, mcp_handshake_passed=None
    )
    assert receipt.outcome == "RESTART_REQUIRED"
    assert receipt.checks["skills"] == "UNVERIFIED"
    assert receipt.resume_instructions


def test_activation_active_now_only_with_real_mcp_handshake():
    plan = activation.build_activation_plan(
        host="claude", provider="p", scope="project", components=["mcp"], writes=[]
    )
    receipt = activation.evaluate_activation(
        plan, host_is_current_session=True, mcp_handshake_passed=True
    )
    assert receipt.outcome == "ACTIVE_NOW"


def test_activation_unsupported_component():
    plan = activation.build_activation_plan(
        host="copilot", provider="p", scope="project", components=["agents"], writes=[]
    )
    receipt = activation.evaluate_activation(
        plan, host_is_current_session=False, mcp_handshake_passed=None
    )
    assert receipt.outcome == "UNSUPPORTED"


# -- delegation --------------------------------------------------------------


def _req(**kw):
    return delegation.new_request(
        intent="i", provider="p", execution_mode="DIRECT_CAPABILITY", **kw
    )


def test_delegation_completed_requires_exit_code():
    from theforge.contracts.specialist import DelegationResult

    with pytest.raises(ContractError):
        DelegationResult(task_id="t", provider="p", stage="COMPLETED")


def test_delegation_host_agentic_is_prepared_not_executed():
    req = delegation.new_request(
        intent="i",
        provider="p",
        execution_mode="HOST_AGENTIC",
        command=["false"],
    )
    result = delegation.execute(req)
    assert result.stage == "PREPARED"
    assert result.exit_code is None


def test_delegation_missing_command_blocked():
    result = delegation.execute(_req(command=[]))
    assert result.stage == "BLOCKED"


def test_delegation_real_execution(tmp_path):
    marker = tmp_path / "ran.txt"
    req = _req(command=[sys.executable, "-c", f"open({str(marker)!r},'w').write('x')"])
    result = delegation.execute(req)
    assert result.stage == "COMPLETED"
    assert result.exit_code == 0
    assert marker.is_file()


def test_delegation_failure_stage():
    req = _req(command=[sys.executable, "-c", "import sys; sys.exit(3)"])
    result = delegation.execute(req)
    assert result.stage == "FAILED"
    assert result.exit_code == 3


def test_delegation_missing_binary_blocked():
    req = _req(command=["definitely-not-a-real-binary-xyz"])
    result = delegation.execute(req)
    assert result.stage == "BLOCKED"


def test_fan_out_budget_blocks_excess():
    reqs = [_req(command=[sys.executable, "-c", "pass"]) for _ in range(3)]
    results = delegation.fan_out(reqs, max_parallel=1)
    assert results[0].stage == "COMPLETED"
    assert all(r.stage == "BLOCKED" for r in results[1:])


# -- specialists collect + resolve -------------------------------------------


def _manifest(tmp_path: Path) -> AgenticManifest:
    return AgenticManifest(
        provider="spark-forge-aws",
        cli="sparkforge-aws",
        cli_entry="sparkforge_aws.adapters.cli:main",
        workflows=[
            DelegationEntry(
                id="analyze-pyspark",
                mode="DIRECT_CAPABILITY",
                command=["{cli}", "analyze", "pyspark", "--path", "{target}"],
            )
        ],
    )


def test_resolve_command_checkout_fallback(tmp_path):
    from theforge.contracts.specialist import SpecialistLifecycle
    from theforge.specialists import SpecialistView

    view = SpecialistView(
        lifecycle=SpecialistLifecycle(provider="spark-forge-aws", installation_state="INSTALLABLE"),
        cli=None,
        checkout=str(tmp_path),
        manifest=_manifest(tmp_path),
    )
    argv = specialists.resolve_command(
        ["{cli}", "analyze", "pyspark", "--path", "{target}"], view=view, target="."
    )
    assert argv is not None
    assert argv[0] == sys.executable
    assert "sparkforge_aws.adapters.cli" in argv[2]
    assert argv[-1] == "."


def test_resolve_command_no_cli_no_checkout():
    from theforge.contracts.specialist import SpecialistLifecycle
    from theforge.specialists import SpecialistView

    view = SpecialistView(
        lifecycle=SpecialistLifecycle(provider="x", installation_state="NOT_INSTALLED"),
        manifest=AgenticManifest(provider="x"),
    )
    assert specialists.resolve_command(["{cli}", "doctor"], view=view) is None


def test_collect_not_installed(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_HOME_OVERRIDE", str(tmp_path))
    ws = tmp_path / "ws"
    ws.mkdir()
    views = specialists.collect(workspace_root=ws, probe_cli=False)
    assert len(views) == len(specialists.catalog_ids(ws))
    assert all(v.lifecycle.installation_state == "NOT_INSTALLED" for v in views)


def test_collect_installed_manifest(tmp_path, monkeypatch):
    home = tmp_path / "home"
    install_dir = home / ".forge" / "installations"
    install_dir.mkdir(parents=True)
    (tmp_path / "install-root").mkdir()
    doc = {
        "schema": "forge/InstallationManifest/v1",
        "forge_id": "api-forge",
        "version": "0.1.0",
        "install_root": str(tmp_path / "install-root"),
        "cli": {"name": "apiforge", "version_cmd": [sys.executable, "--version"]},
        "mcp": {"command": ["apiforge-mcp"]},
    }
    (install_dir / "api-forge.json").write_text(json.dumps(doc))
    monkeypatch.setenv("FORGE_HOME_OVERRIDE", str(home))
    views = specialists.collect(workspace_root=tmp_path / "ws")
    api = next(v for v in views if v.lifecycle.provider == "api-forge")
    # version_cmd resolves to python --version → runnable → CONFIGURED
    assert api.lifecycle.installation_state == "CONFIGURED"
