"""Project-scope asset rendering for The Forge: canonical `.agents/skills/`
into the host skill directories.

The Forge ships skills, not agents/MCP — its surface on a consumer repo is
the skill tree plus the managed marker block. Canonical source: the
checkout's `.agents/skills/`, or the bundled `theforge/host_assets/skills/`
inside the wheel (ADR-0058, emenda a ADR-0020).
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


def _skills_src() -> Path | None:
    here = Path(__file__).resolve()
    for cand in (here, *here.parents):
        repo_skills = cand / ".agents" / "skills"
        if repo_skills.is_dir():
            return repo_skills
    bundled = here.parents[1] / "host_assets" / "skills"
    return bundled if bundled.is_dir() else None


def render(hosts: tuple[str, ...], *, skills: bool) -> dict[str, bytes]:
    """``{rel_path: bytes}`` das skills canonicas por host."""
    src = _skills_src()
    if src is None or not skills:
        return {}
    out: dict[str, bytes] = {}
    targets = {_SKILL_DIRS[h] for h in hosts if h in _SKILL_DIRS}
    if any(h in hosts for h in ("devin", "codex", "copilot")):
        targets.add(".agents/skills")
    for dest in sorted(targets):
        for path in sorted(src.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                rel = path.relative_to(src).as_posix()
                out[f"{dest}/{rel}"] = path.read_bytes()
    return out


__all__ = ["HOSTS", "render"]
