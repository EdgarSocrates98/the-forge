"""Project-scope asset rendering for The Forge.

The Forge ships skills plus Codex agent specs — its surface on a consumer repo
is host-aware and never claims unsupported agent formats. Canonical source: the
checkout's `.agents/skills/`, or the bundled `theforge/host_assets/skills/`
inside the wheel, and checkout `agentic/agents/` for agent specs
(ADR-0058, emenda a ADR-0020).
"""

from __future__ import annotations

from pathlib import Path

HOSTS: tuple[str, ...] = ("claude", "devin", "codex", "copilot")

_SKILL_DIRS = {
    "claude": ".claude/skills",
    "devin": ".devin/skills",
    "copilot": ".github/skills",
    "codex": ".agents/skills",
}
_AGENT_DIRS = {"codex": ".codex/agents"}


def _skills_src() -> Path | None:
    here = Path(__file__).resolve()
    bundled = here.parents[1] / "host_assets" / "skills"
    if bundled.is_dir():
        return bundled
    # An editable checkout has one well-defined root.  Do not walk every
    # ancestor: an installed wheel under a user's home would otherwise adopt
    # unrelated ~/.agents/skills content (including quarantine directories).
    repo_root = here.parents[3] if len(here.parents) > 3 else None
    repo_skills = repo_root / ".agents" / "skills" if repo_root else None
    return repo_skills if repo_skills and repo_skills.is_dir() else None


def _agents_src() -> Path | None:
    here = Path(__file__).resolve()
    bundled = here.parents[1] / "host_assets" / "agents"
    if bundled.is_dir():
        return bundled
    repo_root = here.parents[3] if len(here.parents) > 3 else None
    repo_agents = repo_root / "agentic" / "agents" if repo_root else None
    return repo_agents if repo_agents and repo_agents.is_dir() else None


def render(hosts: tuple[str, ...], *, skills: bool, agents: bool = False) -> dict[str, bytes]:
    """``{rel_path: bytes}`` de assets canônicos suportados por host."""
    src = _skills_src()
    out: dict[str, bytes] = {}
    if src is not None and skills:
        targets = {_SKILL_DIRS[h] for h in hosts if h in _SKILL_DIRS}
        if any(h in hosts for h in ("devin", "codex", "copilot")):
            targets.add(".agents/skills")
        for dest in sorted(targets):
            for path in sorted(src.rglob("*")):
                if path.is_file() and "__pycache__" not in path.parts:
                    rel = path.relative_to(src).as_posix()
                    out[f"{dest}/{rel}"] = path.read_bytes()
    agent_src = _agents_src()
    if agent_src is not None and agents:
        for host in sorted(set(hosts) & set(_AGENT_DIRS)):
            dest = _AGENT_DIRS[host]
            for path in sorted(agent_src.glob("*.toml")):
                out[f"{dest}/{path.name}"] = path.read_bytes()
    return out


__all__ = ["HOSTS", "render"]
