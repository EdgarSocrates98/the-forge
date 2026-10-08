"""Specialized agent registry tests (agentic prompt §18-32, §43-50, §70-74, §97).

The agent authority model is enforced three ways: the ``AgentSpec`` contract
(closed authority set, universal forbidden actions, no allow/deny overlap),
``check_authority`` (authority ceiling + spec lists + universal wall), and the
rendered Codex files staying in sync with the canonical specs.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from theforge.agents import check_authority, load_all, load_spec
from theforge.contracts import ContractError, from_dict
from theforge.contracts.agent import (
    AGENT_SPEC_SCHEMA,
    UNIVERSAL_FORBIDDEN,
    AgentSpec,
)
from theforge.errors import UsageError

REPO = Path(__file__).resolve().parents[1]
RENDER_AGENTS = REPO / "scripts" / "agentic" / "render_agents.py"
SKILLS_SRC = REPO / "agentic" / "skills"

ALL_IDS = {
    "ecosystem-router",
    "forge-discovery",
    "capability-negotiator",
    "bootstrap-installation",
    "cross-forge-planner",
    "execution-orchestrator",
    "verification-orchestrator",
    "ecosystem-debugger",
}


def _spec(**kw: object) -> dict[str, object]:
    base: dict[str, object] = {
        "schema": AGENT_SPEC_SCHEMA,
        "id": "x-agent",
        "name": "X",
        "role": "r",
        "authority": "propose",
        "purpose": "p",
        "output_contracts": ["theforge/RoutingProposal/v1"],
        "forbidden_actions": sorted(UNIVERSAL_FORBIDDEN),
    }
    base.update(kw)
    return base


def test_eight_specs_load() -> None:
    specs = load_all()
    assert set(specs) == ALL_IDS


def test_required_skills_exist_as_canonical_sources() -> None:
    """Every skill an agent loads must be a real canonical skill (§33)."""
    known = {p.stem for p in SKILLS_SRC.glob("*.md")}
    for spec in load_all().values():
        assert spec.required_skills, spec.id
        for skill in spec.required_skills:
            assert skill in known, f"{spec.id}: unknown skill {skill}"


def test_named_output_contracts_are_real_schemas() -> None:
    schema_dir = REPO / "schemas"
    for spec in load_all().values():
        for contract in (*spec.input_contracts, *spec.output_contracts):
            assert contract.startswith("theforge/"), contract
            name = contract.removeprefix("theforge/").removesuffix("/v1")
            assert (schema_dir / f"{name}.schema.json").is_file(), (
                f"{spec.id}: {contract} has no published schema"
            )


def test_prompt_non_escalation_matrix() -> None:
    """§44-45: the required non-escalations, checked per agent."""
    specs = load_all()
    router = specs["ecosystem-router"]
    assert not check_authority(router, "install")[0]
    assert not check_authority(router, "execute")[0]
    installer = specs["bootstrap-installation"]
    assert not check_authority(installer, "grant-trust")[0]
    assert not check_authority(installer, "approve")[0]
    assert check_authority(installer, "install")[0]
    planner = specs["cross-forge-planner"]
    assert not check_authority(planner, "waive-verification")[0]
    assert not check_authority(planner, "execute")[0]
    negotiator = specs["capability-negotiator"]
    assert not check_authority(negotiator, "install")[0]
    verifier = specs["verification-orchestrator"]
    assert not check_authority(verifier, "waive-verification")[0]
    debugger = specs["ecosystem-debugger"]
    assert check_authority(debugger, "diagnose")[0]
    assert not check_authority(debugger, "modify-registry")[0]


def test_no_agent_can_approve_or_grant_trust() -> None:
    for spec in load_all().values():
        for action in UNIVERSAL_FORBIDDEN:
            ok, reason = check_authority(spec, action)
            assert not ok, spec.id
            assert "policy/human gate" in reason


def test_propose_cannot_execute() -> None:
    for spec in load_all().values():
        if spec.authority == "propose":
            assert not check_authority(spec, "execute")[0], spec.id
            assert not check_authority(spec, "install")[0], spec.id


def test_bounded_context_is_declared() -> None:
    for spec in load_all().values():
        assert 1024 <= spec.context_budget_bytes <= 512 * 1024
        assert spec.max_skills <= 4


def test_codex_outputs_in_sync() -> None:
    result = subprocess.run(
        [sys.executable, str(RENDER_AGENTS), "--check"], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_rendered_hosts_honest() -> None:
    """§70-74: only Codex has a tracked repo-level agent format; no spec may
    claim a rendered host file that does not exist."""
    for spec in load_all().values():
        assert set(spec.rendered_hosts) <= {"codex"}
        for _host in spec.rendered_hosts:
            assert (REPO / ".codex" / "agents" / f"{spec.id}.toml").is_file()


def test_contract_rejects_unknown_authority() -> None:
    with pytest.raises(ContractError, match="authority"):
        from_dict(AgentSpec, _spec(authority="root"), "$")


def test_contract_rejects_missing_universal_forbidden() -> None:
    with pytest.raises(ContractError, match="grant-trust|approve"):
        from_dict(AgentSpec, _spec(forbidden_actions=["install"]), "$")


def test_contract_rejects_allow_deny_overlap() -> None:
    with pytest.raises(ContractError, match="both allowed and forbidden"):
        from_dict(
            AgentSpec,
            _spec(allowed_actions=["route"], forbidden_actions=["route", *UNIVERSAL_FORBIDDEN]),
            "$",
        )


def test_contract_rejects_unknown_action_vocabulary() -> None:
    with pytest.raises(ContractError, match="unknown actions"):
        from_dict(AgentSpec, _spec(forbidden_actions=["become-root", *UNIVERSAL_FORBIDDEN]), "$")


def test_spec_filename_binds_id(tmp_path: Path) -> None:
    """The file name IS the id — a spec named wrong.toml cannot claim a
    different agent id."""
    doc = _spec(id="real-agent")
    lines = []
    for k, v in doc.items():
        if isinstance(v, str):
            lines.append(f'{k} = {v!r}'.replace("'", '"'))
        elif isinstance(v, list):
            inner = ", ".join(f'"{i}"' for i in v)
            lines.append(f"{k} = [{inner}]")
    path = tmp_path / "wrong.toml"
    path.write_text("\n".join(lines), encoding="utf-8")
    with pytest.raises(UsageError, match="named after"):
        load_spec(path)
