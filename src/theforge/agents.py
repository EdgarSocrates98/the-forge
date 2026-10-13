"""Specialized agent registry (agentic prompt §18-32, §43-50).

Canonical agent specs live in ``agentic/agents/<id>.toml`` — one file per
agent, TOML, human-authored. The loader validates each through the
``AgentSpec`` contract and answers the questions hosts need: who may propose
vs. decide, which skills an agent must load, what contracts it accepts and
emits, and its bounded-context budget.

``check_authority(spec, action)`` is the runtime gate hosts consult before
letting an agent take an action — it encodes the non-escalation matrix: a
``propose``-authority agent can never ``execute`` or ``install``, no agent can
``approve`` or ``grant-trust``, and every spec's own forbidden list applies.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from theforge.contracts import from_dict
from theforge.contracts.agent import AUTHORITIES, UNIVERSAL_FORBIDDEN, AgentSpec
from theforge.errors import PersistenceError, UsageError

__all__ = ["DEFAULT_AGENTS_DIR", "agent_for", "check_authority", "load_all", "load_spec"]

DEFAULT_AGENTS_DIR = Path(__file__).resolve().parents[2] / "agentic" / "agents"

# Authority → the strongest actions it may ever take. Anything not listed is
# denied. ``execute-approved`` reaches execution — including running an
# approved InstallationPlanV2 — only after a plan exists and approval evidence
# is attached; approval itself is never in an agent's power
# (UNIVERSAL_FORBIDDEN).
_AUTHORITY_ACTIONS: dict[str, frozenset[str]] = {
    "propose": frozenset({"route", "plan", "verify", "discover", "diagnose", "invoke-llm"}),
    "classify": frozenset({"discover", "diagnose"}),
    "advise": frozenset({"diagnose", "discover"}),
    "execute-approved": frozenset(
        {"execute", "install", "route", "plan", "verify", "discover", "diagnose", "invoke-llm"}
    ),
}


def load_spec(path: Path) -> AgentSpec:
    """Load and validate one agent spec; contract violations raise."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise PersistenceError(f"agent spec: cannot parse {path}: {exc}") from exc
    spec = from_dict(AgentSpec, data, "$")
    if spec.id != path.stem:
        raise UsageError(
            f"agent spec: file {path.name} must be named after the agent id {spec.id!r}"
        )
    return spec


def load_all(directory: Path | None = None) -> dict[str, AgentSpec]:
    """All agent specs in ``directory`` (default: repo ``agentic/agents/``),
    keyed by id. An absent directory is an empty registry, not an error."""
    root = directory if directory is not None else DEFAULT_AGENTS_DIR
    if not root.is_dir():
        return {}
    return {spec.id: spec for spec in (load_spec(p) for p in sorted(root.glob("*.toml")))}


def agent_for(agent_id: str, directory: Path | None = None) -> AgentSpec | None:
    return load_all(directory).get(agent_id)


def check_authority(spec: AgentSpec, action: str) -> tuple[bool, str]:
    """May ``spec`` take ``action``? Returns (allowed, reason).

    Order matters: the universal forbidden wall first (no agent approves or
    grants trust), then the spec's own list, then the authority ceiling —
    an action the authority class cannot reach is denied even if the spec
    forgot to list it as forbidden.
    """
    if action in UNIVERSAL_FORBIDDEN:
        return False, f"{action} is a policy/human gate — no agent holds it"
    if action in spec.forbidden_actions:
        return False, f"{spec.id}: {action} is forbidden by spec"
    ceiling = _AUTHORITY_ACTIONS[spec.authority]
    if action not in ceiling:
        return False, f"{spec.id}: authority {spec.authority!r} cannot {action}"
    if spec.allowed_actions and action not in spec.allowed_actions:
        return False, f"{spec.id}: {action} not in allowed_actions"
    return True, "allowed"


assert set(_AUTHORITY_ACTIONS) == set(AUTHORITIES)
