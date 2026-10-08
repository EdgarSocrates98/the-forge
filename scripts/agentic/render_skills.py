#!/usr/bin/env python3
"""Canonical skill renderer (agentic prompt §16; ADR 0020 revision).

One canonical source per skill — ``agentic/skills/<name>.md`` — renders to the
three host directories instead of three hand-edited mirrors:

  .claude/skills/<name>/SKILL.md        Claude Code frontmatter + plain body
  .agents/skills/<name>/SKILL.md        Codex: background_information/instructions
  .agents/skills/<name>/agents/openai.yaml   Codex UI metadata
  .devin/skills/<name>/SKILL.md         Devin: same envelope as Codex

Canonical file = markdown with a ``+++`` TOML frontmatter:

    +++
    name = "forge-routing"
    description = "…"                      # the trigger sentence (§33)
    [freshness]                            # optional, per §51-52
    specialists = ["spark-forge-aws"]      # forge-knowledge ids it covers
    tested_version = "0.3.0"
    [claude]
    allowed_tools = "Read, Bash, Grep"
    argument_hint = "<task>"
    [codex]
    display_name = "Forge Routing"
    short_description = "…"
    +++

Body conventions:

  - ``## Overview`` → ``<background_information>`` on Codex/Devin.
  - ``<!-- host:claude|codex|devin[,…] -->`` … ``<!-- /host -->`` includes the
    block only on the listed hosts (drops the markers themselves).
  - Everything else renders verbatim on all hosts.

Usage:

    python scripts/agentic/render_skills.py [--check]

``--check`` regenerates into memory and fails if the tracked outputs differ —
the drift gate the manual mirrors never had.
"""

from __future__ import annotations

import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCES = ROOT / "agentic" / "skills"

FRONT = re.compile(r"\A\+\+\+\n(.*?)\n\+\+\+\n", re.DOTALL)
HOST_BLOCK = re.compile(r"<!-- host:([a-z,]+) -->\n(.*?)<!-- /host -->\n?", re.DOTALL)
OVERVIEW = re.compile(r"^## Overview\n\n(.*?)(?=^## |\Z)", re.DOTALL | re.MULTILINE)


class RenderError(Exception):
    """A canonical source is invalid; the message names the file and key."""


@dataclass(frozen=True)
class SkillSource:
    name: str
    description: str
    body: str
    allowed_tools: str | None
    argument_hint: str | None
    display_name: str
    short_description: str
    specialists: tuple[str, ...]
    tested_version: str | None
    tested_surface: str | None


def _require(table: dict[str, object], key: str, path: Path) -> str:
    value = table.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RenderError(f"{path.name}: missing or empty `{key}`")
    return value.strip()


def parse_source(path: Path) -> SkillSource:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    match = FRONT.match(text)
    if not match:
        raise RenderError(f"{path.name}: no +++ TOML frontmatter")
    try:
        meta = tomllib.loads(match.group(1))
    except tomllib.TOMLDecodeError as exc:
        raise RenderError(f"{path.name}: invalid TOML frontmatter: {exc}") from exc

    name = _require(meta, "name", path)
    if name != path.stem:
        raise RenderError(f"{path.name}: name {name!r} must match the filename")
    claude = meta.get("claude", {})
    codex = meta.get("codex", {})
    freshness = meta.get("freshness", {})
    body = text[match.end() :]

    if "## Overview" not in body:
        raise RenderError(f"{path.name}: body needs an '## Overview' section")

    return SkillSource(
        name=name,
        description=_require(meta, "description", path),
        body=body,
        allowed_tools=claude.get("allowed_tools"),
        argument_hint=claude.get("argument_hint"),
        display_name=_require(codex, "display_name", path),
        short_description=_require(codex, "short_description", path),
        specialists=tuple(freshness.get("specialists", ())),
        tested_version=freshness.get("tested_version"),
        tested_surface=freshness.get("tested_surface"),
    )


def _resolve_host_blocks(body: str, host: str) -> str:
    def keep(match: re.Match[str]) -> str:
        hosts = match.group(1).split(",")
        return match.group(2) if host in hosts else ""

    resolved = HOST_BLOCK.sub(keep, body)
    if "host:" in resolved:
        raise RenderError(f"unclosed or nested host block left in output ({host})")
    return resolved


def _split_overview(body: str) -> tuple[str, str]:
    match = OVERVIEW.search(body)
    if not match:
        raise RenderError("body has no Overview content")
    overview = match.group(1).strip()
    rest = (body[: match.start()] + body[match.end() :]).strip()
    rest = re.sub(r"^# .*\n+", "", rest, count=1)  # title lives in frontmatter
    return overview, rest


def _freshness_marker(src: SkillSource) -> str:
    """Machine-checkable freshness trailer (§51-52): audit_assets binds the
    rendered skill to the forge-knowledge packages and versions it was
    recorded against."""
    if not src.specialists and not src.tested_version:
        return ""
    parts = []
    if src.specialists:
        parts.append(f"specialists={','.join(src.specialists)}")
    if src.tested_version:
        parts.append(f"version={src.tested_version}")
    if src.tested_surface:
        parts.append(f"surface={src.tested_surface}")
    return "<!-- forge:freshness " + " ".join(parts) + " -->\n"


def render_claude(src: SkillSource) -> str:
    lines = ["---", f"name: {src.name}", f"description: {src.description}"]
    if src.allowed_tools:
        lines.append(f"allowed-tools: {src.allowed_tools}")
    if src.argument_hint:
        lines.append(f"argument-hint: {src.argument_hint}")
    lines.append("---")
    return (
        "\n".join(lines)
        + "\n"
        + _resolve_host_blocks(src.body, "claude")
        + _freshness_marker(src)
    )


def render_envelope(src: SkillSource, host: str) -> str:
    body = _resolve_host_blocks(src.body, host)
    overview, rest = _split_overview(body)
    return (
        f"---\nname: {src.name}\ndescription: {src.description}\n---\n\n"
        f"# {src.name}\n\n"
        f"<background_information>\n{overview}\n</background_information>\n\n"
        f"<instructions>\n{rest}\n</instructions>\n"
        + _freshness_marker(src)
    )


def render_openai_yaml(src: SkillSource) -> str:
    return (
        "interface:\n"
        f'  display_name: "{src.display_name}"\n'
        f'  short_description: "{src.short_description}"\n'
        "\npolicy:\n"
        "  allow_implicit_invocation: false\n"
    )


def render_all(src: SkillSource) -> dict[str, str]:
    """repo-relative output path → content."""
    return {
        f".claude/skills/{src.name}/SKILL.md": render_claude(src),
        f".agents/skills/{src.name}/SKILL.md": render_envelope(src, "codex"),
        f".agents/skills/{src.name}/agents/openai.yaml": render_openai_yaml(src),
        f".devin/skills/{src.name}/SKILL.md": render_envelope(src, "devin"),
    }


def load_sources(directory: Path = SOURCES) -> list[SkillSource]:
    if not directory.is_dir():
        return []
    return [parse_source(p) for p in sorted(directory.glob("*.md"))]


def main(argv: list[str]) -> int:
    check = "--check" in argv
    sources = load_sources()
    if not sources:
        print("render_skills: no canonical sources under agentic/skills/", file=sys.stderr)
        return 1

    drift: list[str] = []
    written = 0
    for src in sources:
        for rel, content in render_all(src).items():
            target = ROOT / rel
            if check:
                current = (
                    target.read_text(encoding="utf-8").replace("\r\n", "\n")
                    if target.is_file()
                    else None
                )
                if current != content:
                    drift.append(rel)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8", newline="\n")
                written += 1

    if check:
        if drift:
            print("render_skills: stale outputs — re-run without --check:", file=sys.stderr)
            for rel in drift:
                print(f"  {rel}", file=sys.stderr)
            return 1
        print(f"render_skills: {len(sources)} skills in sync across 3 hosts")
        return 0
    print(f"render_skills: wrote {written} files for {len(sources)} skills")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
