#!/usr/bin/env python3
"""Canonical agent renderer (agentic prompt §16, §70-74).

Canonical agent specs — ``agentic/agents/<id>.toml`` — render to the hosts
that have a real repo-level agent file format:

  .codex/agents/<id>.toml   Codex custom agent (same shape as spec-reviewer.toml)

Hosts without a tracked format are honest about it, not fake-rendered:

  - Claude Code reads agents from the AgentSpec plugin; the repo's
    ``.claude/agents/`` is a gitignored local-override directory — rendering
    there would produce untracked, undeliverable files.
  - Devin dispatches subagents via ``run_subagent`` profiles defined by the
    harness; there is no repo file format. The canonical spec + the
    ``theforge.agents`` registry are what a Devin worker is handed.

The rendered TOML carries role, authority, forbidden actions, required skills
and the input/output contracts so the Codex agent file alone describes the
boundary — the registry keeps it enforceable.

Usage::

    python scripts/agentic/render_agents.py [--check]
"""

from __future__ import annotations

import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCES = ROOT / "agentic" / "agents"


class RenderError(Exception):
    """A canonical agent spec is invalid; the message names the file."""


@dataclass(frozen=True)
class AgentSpecDoc:
    id: str
    name: str
    role: str
    authority: str
    purpose: str
    required_skills: tuple[str, ...]
    allowed_actions: tuple[str, ...]
    forbidden_actions: tuple[str, ...]
    input_contracts: tuple[str, ...]
    output_contracts: tuple[str, ...]
    context_budget_bytes: int
    max_skills: int
    rendered_hosts: tuple[str, ...]


def parse_spec(path: Path) -> AgentSpecDoc:
    try:
        meta = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise RenderError(f"{path.name}: invalid TOML: {exc}") from exc
    for key in ("id", "name", "role", "authority", "purpose"):
        value = meta.get(key)
        if not isinstance(value, str) or not value.strip():
            raise RenderError(f"{path.name}: missing or empty `{key}`")
    if meta["id"] != path.stem:
        raise RenderError(f"{path.name}: id {meta['id']!r} must match the filename")
    return AgentSpecDoc(
        id=meta["id"].strip(),
        name=meta["name"].strip(),
        role=meta["role"].strip(),
        authority=meta["authority"].strip(),
        purpose=" ".join(meta["purpose"].split()),
        required_skills=tuple(meta.get("required_skills", ())),
        allowed_actions=tuple(meta.get("allowed_actions", ())),
        forbidden_actions=tuple(meta.get("forbidden_actions", ())),
        input_contracts=tuple(meta.get("input_contracts", ())),
        output_contracts=tuple(meta.get("output_contracts", ())),
        context_budget_bytes=int(meta.get("context_budget_bytes", 65536)),
        max_skills=int(meta.get("max_skills", 4)),
        rendered_hosts=tuple(meta.get("rendered_hosts", ())),
    )


def _toml_str(value: str) -> str:
    return '"""' + value.replace('"""', '\\"\\"\\"') + '"""'


def render_codex(spec: AgentSpecDoc) -> str:
    instructions = (
        f"{spec.role}\n\n"
        f"{spec.purpose}\n\n"
        f"Authority: {spec.authority} — proposals are decided by deterministic "
        "validation, never by you.\n"
        f"Allowed actions: {', '.join(spec.allowed_actions) or 'none'}.\n"
        f"Forbidden actions: {', '.join(spec.forbidden_actions)}.\n"
        f"Load at most {spec.max_skills} skills: {', '.join(spec.required_skills)}. "
        f"Context budget: {spec.context_budget_bytes} bytes — bounded inputs only: "
        "the task, the relevant forge-* skill, relevant artifact refs, required "
        "contracts. Never the whole repo, full history or every skill.\n"
        f"Inputs: {', '.join(spec.input_contracts)}.\n"
        f"Outputs: {', '.join(spec.output_contracts)} — structured contracts only."
    )
    return (
        f'name = "{spec.id}"\n'
        f"description = {_toml_str(spec.role)}\n"
        'model = "gpt-5.4"\n'
        'model_reasoning_effort = "high"\n'
        f"developer_instructions = {_toml_str(instructions)}\n"
    )


def render_all(spec: AgentSpecDoc) -> dict[str, str]:
    outputs: dict[str, str] = {}
    if "codex" in spec.rendered_hosts:
        outputs[f".codex/agents/{spec.id}.toml"] = render_codex(spec)
    return outputs


def load_sources(directory: Path = SOURCES) -> list[AgentSpecDoc]:
    if not directory.is_dir():
        return []
    return [parse_spec(p) for p in sorted(directory.glob("*.toml"))]


def main(argv: list[str]) -> int:
    check = "--check" in argv
    sources = load_sources()
    if not sources:
        print("render_agents: no canonical specs under agentic/agents/", file=sys.stderr)
        return 1
    drift: list[str] = []
    written = 0
    for spec in sources:
        for rel, content in render_all(spec).items():
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
            print("render_agents: stale outputs — re-run without --check:", file=sys.stderr)
            for rel in drift:
                print(f"  {rel}", file=sys.stderr)
            return 1
        print(f"render_agents: {len(sources)} specs in sync")
        return 0
    print(f"render_agents: wrote {written} files for {len(sources)} specs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
