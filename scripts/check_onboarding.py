"""Onboarding docs gate (cyc10-01, §10.2–§10.4).

Verifies the public first-run surface stays honest and complete:

- the unified journey lists the 8 stages of §10.2;
- all 11 getting-started guides of §10.3 exist and carry the 8 mandatory
  sections (pré-requisitos → próximos passos);
- all 4 golden paths of §10.4 exist and demonstrate the required stages;
- every ``theforge <verb>`` referenced in the docs is a real verb of the
  installed CLI (no invented commands);
- every ``docs/...`` path referenced in the docs exists.

Specialist commands (``apiforge``, ``platformforge``, ``sparkforge-*``,
``forge-doctor-*``) are validated at authoring time against the installed
surfaces — the gate cannot assume a sibling install and must not fake one.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ONB = REPO / "docs" / "onboarding"
PY = sys.executable

STAGES_8 = [
    "Discover",
    "Install",
    "Choose Forge",
    "Configure Host",
    "Validate Environment",
    "Run First Task",
    "See Evidence",
    "Explore Advanced Features",
]

SECTIONS_8 = [
    "Pré-requisitos",
    "Instalação",
    "Configuração",
    "Primeiro comando",
    "Resultado esperado",
    "Explicação do resultado",
    "Resolução de problemas",
    "Próximos passos",
]

GUIDES = [
    "new-user",
    "backend-developer",
    "data-engineer-aws",
    "data-engineer-azure",
    "platform-engineer",
    "claude-code",
    "codex",
    "devin",
    "copilot",
    "cli-tui",
    "portal",
]

GOLDEN_PATHS = {
    "spark-aws": [
        "instalação",
        "especialista",
        "diagnóstico",
        "evidências",
        "recomend",
        "testes",
        "resultado",
    ],
    "api": ["contratos", "diagnóstico", "planejamento", "validação"],
    "platform": ["determinística", "evidências", "recomend"],
    "multi-forge": ["descoberta", "integração", "especialistas"],
}

_THEFORGE_VERB = re.compile(r"\btheforge\s+([a-z][a-z0-9-]*)")
_THEFORGE_CMD = re.compile(r"\btheforge[ \t]+([a-z][a-z0-9-]*)[ \t]+([a-z][a-z0-9-]*)")
_DOC_PATH = re.compile(r"docs/[A-Za-z0-9_./-]+")
_FENCE = re.compile(r"^```")
_INLINE_CODE = re.compile(r"`[^`\n]*`")


def _code_spans(text: str) -> list[str]:
    """Command lines visible to the gate: fenced-block lines + inline code.

    Prose is dropped so a sentence like "use theforge install the forges"
    cannot false-fail as an invented ``install the`` subcommand — commands
    that are meant to run belong in code spans. Each fenced line and each
    inline span is returned separately so two adjacent spans on different
    lines cannot combine into a phantom command.
    """
    parts: list[str] = []
    inside = False
    for line in text.splitlines():
        if _FENCE.match(line.strip()):
            inside = not inside
            continue
        if inside:
            parts.append(line)
        else:
            parts.extend(m.group(0)[1:-1] for m in _INLINE_CODE.finditer(line))
    return parts


def _theforge_verbs() -> set[str]:
    out = subprocess.run(
        [PY, "-m", "theforge", "--help"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    if out.returncode != 0:
        return set()
    m = re.search(r"\{([^}]+)\}", out.stdout)
    return set(m.group(1).split(",")) if m else set()


def _subcommands(verb: str) -> set[str] | None:
    """Subcommand group of ``theforge <verb>``, or None when the verb takes
    positional arguments instead of a closed subcommand set."""
    out = subprocess.run(
        [PY, "-m", "theforge", verb, "--help"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    if out.returncode != 0:
        return None
    # A ``{...}`` group is a closed subcommand set only when argparse puts it
    # under ``positional arguments:``; under ``options:`` it is an option's
    # choices (e.g. ``--scope {project,workspace,user}``), not a grammar.
    pos = out.stdout.find("positional arguments:")
    if pos < 0:
        return None
    section = out.stdout[pos:]
    end = section.find("\noptions:")
    if end >= 0:
        section = section[:end]
    m = re.search(r"\{([^}]+)\}", section)
    return set(m.group(1).split(",")) if m else None


def _failures() -> list[str]:
    fails: list[str] = []

    readme = ONB / "README.md"
    if not readme.is_file():
        return ["docs/onboarding/README.md missing"]
    body = readme.read_text(encoding="utf-8")
    for stage in STAGES_8:
        if stage not in body:
            fails.append(f"journey stage '{stage}' absent from onboarding/README.md")

    gs = ONB / "getting-started"
    for guide in GUIDES:
        f = gs / f"{guide}.md"
        if not f.is_file():
            fails.append(f"getting-started/{guide}.md missing")
            continue
        text = f.read_text(encoding="utf-8")
        for sec in SECTIONS_8:
            if f"## {sec}" not in text:
                fails.append(f"{f.relative_to(REPO)}: missing section '## {sec}'")

    gp = ONB / "golden-paths"
    for name, stages in GOLDEN_PATHS.items():
        f = gp / f"{name}.md"
        if not f.is_file():
            fails.append(f"golden-paths/{name}.md missing")
            continue
        text = f.read_text(encoding="utf-8").lower()
        for st in stages:
            if st not in text:
                fails.append(f"{f.relative_to(REPO)}: missing stage '{st}'")

    verbs = _theforge_verbs()
    subs_cache: dict[str, set[str] | None] = {}
    docs = list(ONB.rglob("*.md"))
    for f in docs:
        text = f.read_text(encoding="utf-8")
        code_lines = _code_spans(text)
        for verb in {v for line in code_lines for v in _THEFORGE_VERB.findall(line)}:
            if verbs and verb not in verbs:
                fails.append(f"{f.relative_to(REPO)}: 'theforge {verb}' is not a real verb")
        for verb, sub in {pair for line in code_lines for pair in _THEFORGE_CMD.findall(line)}:
            if verbs and verb not in verbs:
                continue
            if verb not in subs_cache:
                subs_cache[verb] = _subcommands(verb)
            subs = subs_cache[verb]
            if subs and sub not in subs:
                fails.append(
                    f"{f.relative_to(REPO)}: 'theforge {verb} {sub}' is not a real subcommand"
                )
        for ref in set(_DOC_PATH.findall(text)):
            if not (REPO / ref).exists():
                fails.append(f"{f.relative_to(REPO)}: referenced path '{ref}' does not exist")

    return fails


def main() -> int:
    if not ONB.is_dir():
        print("docs/onboarding/ missing")
        return 1
    fails = _failures()
    if fails:
        for f in fails:
            print(f"FAIL {f}")
        return 1
    print(
        "onboarding docs: 8-stage journey, 11 guides, 4 golden paths, "
        "all theforge verbs + docs/ paths verified"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
