"""Declared host capability matrix (cycle 16.1, FRENTE E §9.1).

``theforge hosts matrix`` answers "what does each host *declare* it can
consume" — skills, agent specs, subagents, instruction files, MCP config,
discovery verbs, install scopes. Two honesty rules:

- states come from **declared capability data** (the documented matrix in
  ``docs/experience/host-capability-matrix.json`` plus the install
  mechanics the kit writes), never from filesystem guesses — a file
  existing does not prove a host loads it;
- ``partial``/``unsupported``/``unverified`` are first-class answers.
  Everything the matrix itself marks ``UNVERIFIED`` stays unverified here
  instead of being promoted to a guess.

Host *detection* (which binary is on this machine) is a different question
— ``theforge hosts list`` answers it with evidence. This module answers
the capability question.
"""

from __future__ import annotations

from typing import Any, Final

MATRIX_SCHEMA: Final = "theforge/HostMatrix/v1"
SOURCE_DOC: Final = "docs/experience/host-capability-matrix.json"
SOURCE_OBSERVED: Final = "2026-10-10T12:40:00Z"

CAPABILITIES: Final[tuple[str, ...]] = (
    "skills",  # SKILL.md catalogs the host loads
    "agents",  # agent specs (.md/.toml) the host runs
    "subagents",  # delegated sub-execution inside the host
    "agents_md",  # reads AGENTS.md workspace instructions
    "claude_md",  # reads CLAUDE.md workspace instructions
    "mcp",  # registers/queries MCP servers
    "config_files",  # file-based host configuration the kit writes
    "discovery",  # CLI verbs to enumerate skills/mcp/agents
    "user_scope",  # config outside the workspace (~/.claude, ~/.agents…)
    "workspace_scope",  # config inside the repo (.claude/, .agents/…)
    "member_scope",  # config scoped to a workspace *member* dir
)

STATES: Final[tuple[str, ...]] = ("supported", "partial", "unsupported", "unverified")

_S, _P, _U, _V = "supported", "partial", "unsupported", "unverified"

# Declared capability data. Every row cites the matrix evidence; anything
# the matrix does not establish stays "unverified" — never inferred
# cross-host (the matrix's own rule: nothing is inferred host→host).
_HOST_CAPABILITIES: Final[dict[str, dict[str, dict[str, str]]]] = {
    "claude": {
        "skills": {
            "state": _S,
            "detail": ".claude/skills/<name>/SKILL.md + plugins; /<skill> or "
            "auto-trigger by description",
        },
        "agents": {
            "state": _S,
            "detail": ".claude/agents/*.md + `claude agents` + --agents flag",
        },
        "subagents": {
            "state": _S,
            "detail": "declared SUBAGENTS_SUPPORTED in the observed matrix",
        },
        "agents_md": {
            "state": _P,
            "detail": "CLAUDE.md is canonical; AGENTS.md is honored only via "
            "link/import — reading it natively is unverified in the matrix",
        },
        "claude_md": {
            "state": _S,
            "detail": "WORKSPACE_CONTEXT_SUPPORTED: CLAUDE.md + .claude/settings.json",
        },
        "mcp": {
            "state": _S,
            "detail": "`claude mcp add|list` observed; real health-check in `claude mcp list`",
        },
        "config_files": {
            "state": _S,
            "detail": ".claude/settings.json + .mcp.json managed keys",
        },
        "discovery": {
            "state": _S,
            "detail": "`claude mcp list`, `claude agents` observed",
        },
        "user_scope": {
            "state": _S,
            "detail": "~/.claude/ user settings documented",
        },
        "workspace_scope": {
            "state": _S,
            "detail": "project .claude/ dirs observed",
        },
        "member_scope": {
            "state": _V,
            "detail": "per-member scoping is not established by the matrix",
        },
    },
    "devin": {
        "skills": {
            "state": _S,
            "detail": "SKILL.md; project .devin/skills/ + .agents/skills/, "
            "user ~/.agents/skills/ (devin skills paths)",
        },
        "agents": {
            "state": _S,
            "detail": ".devin/agents/*.md + .agents/agents/*.md profiles",
        },
        "subagents": {
            "state": _S,
            "detail": "run_subagent built-in (subagent_general/subagent_explore)",
        },
        "agents_md": {
            "state": _S,
            "detail": "WORKSPACE_CONTEXT_SUPPORTED: AGENTS.md + .devin/config.json",
        },
        "claude_md": {
            "state": _U,
            "detail": "no CLAUDE.md mechanism in the observed matrix",
        },
        "mcp": {
            "state": _S,
            "detail": "`devin mcp add|list|get|remove` observed",
        },
        "config_files": {
            "state": _S,
            "detail": ".devin/config.json + devin rules",
        },
        "discovery": {
            "state": _S,
            "detail": "`devin skills list|show|paths`, `devin mcp list` observed",
        },
        "user_scope": {
            "state": _S,
            "detail": "~/.agents/skills/ user dir documented",
        },
        "workspace_scope": {
            "state": _S,
            "detail": "project .devin/ + .agents/ dirs observed",
        },
        "member_scope": {
            "state": _V,
            "detail": "per-member scoping is not established by the matrix",
        },
    },
    "codex": {
        "skills": {
            "state": _S,
            "detail": ".agents/skills/<name>/SKILL.md (same convention as "
            "Devin); $skill or by-description invocation",
        },
        "agents": {
            "state": _S,
            "detail": "AGENTS.md instructions + .codex/agents/*.toml when present",
        },
        "subagents": {
            "state": _S,
            "detail": "subagents enabled by default per the observed matrix",
        },
        "agents_md": {
            "state": _S,
            "detail": "WORKSPACE_CONTEXT_SUPPORTED: AGENTS.md at the repo root",
        },
        "claude_md": {
            "state": _U,
            "detail": "no CLAUDE.md mechanism in the observed matrix",
        },
        "mcp": {
            "state": _S,
            "detail": "`codex mcp add|list|get|remove` observed",
        },
        "config_files": {
            "state": _S,
            "detail": ".codex/ config + AGENTS.md",
        },
        "discovery": {
            "state": _S,
            "detail": "`codex mcp list|get` observed",
        },
        "user_scope": {
            "state": _S,
            "detail": "user-level codex config documented (~/.codex)",
        },
        "workspace_scope": {
            "state": _S,
            "detail": "project .codex/ + .agents/ dirs observed",
        },
        "member_scope": {
            "state": _V,
            "detail": "per-member scoping is not established by the matrix",
        },
    },
    "copilot": {
        "skills": {
            "state": _V,
            "detail": "SKILLS_SUPPORTED is UNVERIFIED — no CLI installed on "
            "the reference machine; .github/skills shipped but load behavior "
            "unproven",
        },
        "agents": {
            "state": _P,
            "detail": ".github/agents/*.agent.md files are the documented "
            "integration; host loading is unverified",
        },
        "subagents": {
            "state": _V,
            "detail": "SUBAGENTS_SUPPORTED is UNVERIFIED",
        },
        "agents_md": {
            "state": _V,
            "detail": "WORKSPACE_CONTEXT_SUPPORTED is UNVERIFIED",
        },
        "claude_md": {
            "state": _U,
            "detail": "no CLAUDE.md mechanism documented",
        },
        "mcp": {
            "state": _V,
            "detail": "MCP_SUPPORTED is UNVERIFIED — ~/.agents config dirs "
            "observed, no CLI to verify",
        },
        "config_files": {
            "state": _P,
            "detail": "file-based config dirs exist (.github/, ~/.agents); "
            "what the host consumes is unverified",
        },
        "discovery": {
            "state": _U,
            "detail": "no shell CLI on the reference machine — nothing to enumerate with",
        },
        "user_scope": {
            "state": _V,
            "detail": "UNVERIFIED",
        },
        "workspace_scope": {
            "state": _P,
            "detail": ".github/ workspace integration documented; load behavior unverified",
        },
        "member_scope": {
            "state": _V,
            "detail": "UNVERIFIED",
        },
    },
}


def capability_state(host: str, capability: str) -> dict[str, str] | None:
    """The declared ``{state, detail}`` for ``(host, capability)`` or None."""
    return (_HOST_CAPABILITIES.get(host) or {}).get(capability)


def host_matrix() -> dict[str, Any]:
    """The full declared matrix as a ``theforge/HostMatrix/v1`` document."""
    hosts: dict[str, dict[str, dict[str, str]]] = {}
    for host in sorted(_HOST_CAPABILITIES):
        row: dict[str, dict[str, str]] = {}
        for cap in CAPABILITIES:
            declared = _HOST_CAPABILITIES[host].get(cap)
            row[cap] = (
                dict(declared) if declared is not None else {"state": _V, "detail": "not declared"}
            )
        hosts[host] = row
    return {
        "schema": MATRIX_SCHEMA,
        "kind": "declared",
        "capabilities": list(CAPABILITIES),
        "hosts": hosts,
        "source": {
            "document": SOURCE_DOC,
            "observed_at": SOURCE_OBSERVED,
            "note": "declared capability data — states are documented/observed "
            "values, never inferred from filesystem presence",
        },
    }


__all__ = [
    "CAPABILITIES",
    "MATRIX_SCHEMA",
    "STATES",
    "capability_state",
    "host_matrix",
]
