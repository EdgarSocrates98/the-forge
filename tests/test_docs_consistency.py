"""Mechanical consistency of the versioned documentation (agentic-maintainability 5.4, 5.5).

Scope: ``README.md``, ``CLAUDE.md``, ``AGENTS.md`` and ``docs/**/*.md`` (UTF-8, LF-normalized).
Every checker is a pure function over a repository root and returns the list of problems, so
each one is exercised on the real repository and on a deliberately broken temporary copy.

Requirements: 7.1 (``docs/errors.md`` canonical), 7.2, 7.3, 7.5, 7.6, 8.3, 8.4, 9.2, 9.4, 9.5, 10.4.
"""

import argparse
import os
import re
import shutil
from collections.abc import Callable, Iterator
from pathlib import Path
from urllib.parse import unquote

import pytest

from theforge.cli import main as cli_main
from theforge.cli.commands import EXIT_BY_STATUS

REPO = Path(__file__).resolve().parents[1]

ROOT_DOCS = ("README.md", "CLAUDE.md", "AGENTS.md")
# Cycle-1 historical records: snapshots, exempt only from link resolution (never from `.kiro/`).
HISTORICAL_DIR = "docs/superpowers/"
# Local, unversioned assets (ADR 0020): versioned documentation never links into them.
LOCAL_ASSET_PREFIXES = (".kiro/", ".claude/agents/", ".agents/skills/source-command-")
REPORT = "docs/reports/cycle-2.md"
ADR_INDEX = "docs/adr/README.md"

# Exit codes emitted outside EXIT_BY_STATUS (which maps run statuses: ok/partial/planned -> 0,
# ambiguous/no_route -> 3, refused/provider_failure -> 4; a refused replay also exits 4):
# 1 doctor/providers health failure, 2 usage / uninitialized workspace / unknown run,
# 5 run persistence failure, 6 integrity divergence (`explain` and `replay --mode verify`),
# 70 internal error, 130 interrupted.
# Revalidation trigger (cross-forge-foundation / Wave D): any change to the CLI exits must update
# this set, the README table and the docs/cli.md table in the same change.
CLI_FIXED_EXITS = frozenset({1, 2, 5, 6, 70, 130})

# Frozen ADR numbering for Cycle 2 (no alternative numbering): decision -> (ADR, owning spec).
REQUIRED_DECISIONS: dict[str, tuple[str, str]] = {
    "ownership dos adapters reais": ("0014", "real-provider-integration"),
    "taxonomia de capabilities": ("0017", "real-provider-integration"),
    "matriz de suporte de CI": ("0011", "cycle2-reality-hardening"),
    "integridade de contexto": ("0015", "context-intelligence-v2"),
    "local do cache do registry": ("0009", "cycle2-reality-hardening"),
    "modelo de execução multi-provider": ("0018", "cross-forge-foundation"),
    "fonte canônica de assets agentic": ("0020", "agentic-maintainability"),
    "modelo de policy": ("0010", "cycle2-reality-hardening"),
}
REPORT_SECTIONS: tuple[str, ...] = (
    "Implementado",
    "Mudanças de arquitetura",
    "Integração real Spark/API",
    "Contexto e economy",
    "Hardening de segurança",
    "CI",
    "Prova cross-forge",
    "Resultados medidos",
    "Limitações",
    "Adiamentos intencionais",
    "Próximo ciclo recomendado",
)
SHELL_LANGS = frozenset({"", "bash", "sh", "shell", "console"})

FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})\s*([\w+-]*)")
HEADING_RE = re.compile(r"^ {0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
INLINE_CODE_RE = re.compile(r"(`+)(.+?)\1")
LINK_RE = re.compile(r"!?\[(?:[^\[\]]|\[[^\]]*\])*\]\(\s*(<[^>]*>|[^)\s]+)(?:\s+\"[^\"]*\")?\s*\)")
REF_DEF_RE = re.compile(r"^ {0,3}\[[^\]]+\]:\s+(<[^>]*>|\S+)")
HTML_ANCHOR_RE = re.compile(r"<a\s+(?:name|id)=\"([^\"]+)\"")
SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
CODE_CELL_RE = re.compile(r"FORGE-[A-Z0-9-]+")
ADR_FILE_RE = re.compile(r"^(\d{4})-.+\.md$")


# --- reading ---------------------------------------------------------------------------------


def read_md(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def doc_files(root: Path) -> list[Path]:
    files = [root / name for name in ROOT_DOCS if (root / name).is_file()]
    return files + sorted((root / "docs").rglob("*.md"))


def rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def split_fences(md: str) -> Iterator[tuple[str | None, str]]:
    """Yield (fence language or None for prose, line) for every line of ``md``."""
    fence: str | None = None
    lang = ""
    for line in md.split("\n"):
        match = FENCE_RE.match(line)
        if fence is None and match:
            fence, lang = match.group(1), match.group(2).lower()
            continue
        if (
            fence is not None
            and line.strip().startswith(fence[0] * len(fence))
            and line.strip().strip(fence[0]) == ""
        ):
            fence = None
            continue
        yield (lang if fence is not None else None), line


def prose_lines(md: str) -> Iterator[str]:
    for lang, line in split_fences(md):
        if lang is None:
            yield line


def code_blocks(md: str) -> Iterator[tuple[str, str]]:
    for lang, line in split_fences(md):
        if lang is not None:
            yield lang, line


def iter_links(md: str) -> Iterator[tuple[str, str]]:
    """Yield (link text, target) for every Markdown link/image outside code."""
    for line in prose_lines(md):
        bare = INLINE_CODE_RE.sub(lambda m: " " * len(m.group(0)), line)
        for match in LINK_RE.finditer(bare):
            yield match.group(0), match.group(1).strip("<>")
        ref = REF_DEF_RE.match(bare)
        if ref:
            yield ref.group(0), ref.group(1).strip("<>")


def slug(heading: str) -> str:
    """GitHub-style heading anchor."""
    text = INLINE_CODE_RE.sub(lambda m: m.group(2), heading)
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[^\w\- ]", "", text.strip().lower())
    return text.replace(" ", "-")


def headings(md: str) -> list[tuple[int, str]]:
    found = []
    for line in prose_lines(md):
        match = HEADING_RE.match(line)
        if match:
            found.append((len(match.group(1)), match.group(2)))
    return found


def anchors(md: str) -> set[str]:
    seen: dict[str, int] = {}
    result: set[str] = set()
    for _, text in headings(md):
        base = slug(text)
        count = seen.get(base, 0)
        seen[base] = count + 1
        result.add(base if count == 0 else f"{base}-{count}")
    result.update(HTML_ANCHOR_RE.findall(md))
    return result


def resolve(root: Path, doc: Path, target: str) -> tuple[str | None, str]:
    """Return (repo-relative POSIX path or None if it escapes the repo, anchor)."""
    path_part, _, anchor = target.partition("#")
    path_part = unquote(path_part)
    if not path_part:
        return rel(root, doc), unquote(anchor)
    joined = os.path.normpath(os.path.join(doc.parent, path_part))
    try:
        return Path(joined).relative_to(root).as_posix(), unquote(anchor)
    except ValueError:
        return None, unquote(anchor)


def table_rows(lines: list[str]) -> list[list[str]]:
    """Rows of the first Markdown table in ``lines`` (header included, separator dropped)."""
    rows: list[list[str]] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|"):
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if not all(re.fullmatch(r":?-{2,}:?", cell) for cell in cells):
                rows.append(cells)
        elif rows:
            break
    return rows


def section_lines(md: str, title_prefix: str, level: int | None = None) -> list[str] | None:
    """Prose lines under the first heading starting with ``title_prefix``, up to the next one
    of the same or higher level."""
    lines = list(prose_lines(md))
    for index, line in enumerate(lines):
        match = HEADING_RE.match(line)
        if (
            match
            and match.group(2).startswith(title_prefix)
            and (level is None or len(match.group(1)) == level)
        ):
            depth = len(match.group(1))
            body = []
            for following in lines[index + 1 :]:
                nxt = HEADING_RE.match(following)
                if nxt and len(nxt.group(1)) <= depth:
                    break
                body.append(following)
            return body
    return None


# --- checkers --------------------------------------------------------------------------------


def link_problems(root: Path) -> list[str]:
    problems = []
    anchor_cache: dict[str, set[str]] = {}
    for doc in doc_files(root):
        name = rel(root, doc)
        for text, target in iter_links(read_md(doc)):
            if SCHEME_RE.match(target):
                continue
            path, anchor = resolve(root, doc, target)
            if path is None:
                problems.append(f"{name}: {text} leaves the repository")
                continue
            if any(
                path.startswith(prefix) or path == prefix.rstrip("/")
                for prefix in LOCAL_ASSET_PREFIXES
            ):
                problems.append(f"{name}: {text} points to an unversioned local asset ({path})")
                continue
            if name.startswith(HISTORICAL_DIR):
                continue
            target_file = root / path
            if not target_file.exists():
                problems.append(f"{name}: {text} points to a missing file ({path})")
                continue
            if anchor and target_file.suffix == ".md" and target_file.is_file():
                if path not in anchor_cache:
                    anchor_cache[path] = anchors(read_md(target_file))
                if anchor not in anchor_cache[path]:
                    problems.append(
                        f"{name}: {text} points to a missing anchor #{anchor} in {path}"
                    )
    return problems


def linked_paths(root: Path, doc: Path) -> set[str]:
    paths = set()
    for _, target in iter_links(read_md(doc)):
        if not SCHEME_RE.match(target):
            path, _ = resolve(root, doc, target)
            if path is not None:
                paths.add(path)
    return paths


def readme_index_problems(root: Path) -> list[str]:
    required = {rel(root, path) for path in sorted((root / "docs").glob("*.md"))}
    required.add(ADR_INDEX)
    if (root / REPORT).is_file():
        required.add(REPORT)
    linked = linked_paths(root, root / "README.md")
    return [f"README.md does not link {path}" for path in sorted(required - linked)]


def canonical_cli_problems(root: Path) -> list[str]:
    problems = []
    for doc in doc_files(root):
        md = read_md(doc)
        for lang, line in code_blocks(md):
            command = re.sub(r"^\s*(?:\$|>|PS>)\s+", "", line).strip()
            if lang in SHELL_LANGS and (command == "forge" or command.startswith("forge ")):
                problems.append(f"{rel(root, doc)}: example uses the alias: {line.strip()}")
    for name in ("README.md", "docs/cli.md"):
        prose = "\n".join(prose_lines(read_md(root / name)))
        if not re.search(r"`forge`[^\n]*\balias\b|\balias\b[^\n]*`forge`", prose):
            problems.append(f"{name}: does not present `forge` as an alias of `theforge`")
    return problems


def errors_doc_problems(root: Path) -> list[str]:
    problems = []
    errors = "docs/errors.md"
    if errors not in linked_paths(root, root / "README.md"):
        problems.append(f"README.md does not index {errors}")
    must_link = {"docs/protocol.md"}
    for doc in sorted((root / "docs").rglob("*.md")):
        name = rel(root, doc)
        if name == errors or name.startswith(HISTORICAL_DIR):
            continue
        if any(
            line.lstrip().startswith("|") and CODE_CELL_RE.search(line)
            for line in prose_lines(read_md(doc))
        ):
            must_link.add(name)
    for name in sorted(must_link):
        if errors not in linked_paths(root, root / name):
            problems.append(f"{name} has FORGE-* codes but does not link {errors} (canonical list)")
    return problems


def expected_exits() -> frozenset[int]:
    return frozenset(EXIT_BY_STATUS.values()) | CLI_FIXED_EXITS


def exit_table(md: str) -> dict[int, str] | None:
    lines = section_lines(md, "Exit codes")
    if lines is None:
        return None
    rows = table_rows(lines)[1:]
    return {
        int(row[0].strip("` ")): row[1] if len(row) > 1 else ""
        for row in rows
        if row and row[0].strip("` ").isdigit()
    }


def exit_code_problems(root: Path) -> list[str]:
    problems = []
    expected = expected_exits()
    tables: dict[str, dict[int, str]] = {}
    for name in ("README.md", "docs/cli.md"):
        table = exit_table(read_md(root / name))
        if table is None:
            problems.append(f"{name}: no 'Exit codes' table")
            continue
        tables[name] = table
        for code in sorted(expected - table.keys()):
            problems.append(
                f"{name}: exit code {code} emitted by the CLI is missing from the table"
            )
        for code in sorted(table.keys() - expected):
            problems.append(f"{name}: exit code {code} is not emitted by the CLI")
        meaning = table.get(6, "")
        if 6 in table and not ("`explain`" in meaning and "replay --mode verify" in meaning):
            problems.append(
                f"{name}: exit code 6 must describe the integrity divergence of "
                "`explain` and `replay --mode verify`"
            )
    if len(tables) == 2:
        readme, cli = tables["README.md"], tables["docs/cli.md"]
        for code in sorted(readme.keys() ^ cli.keys()):
            problems.append(f"exit code {code}: README.md and docs/cli.md tables differ")
    return problems


def cli_coverage_problems(root: Path) -> list[str]:
    """Every top-level CLI verb must appear as a `verb`-prefixed row in the
    docs/cli.md summary table — the drift gate for new commands."""
    doc = read_md(root / "docs" / "cli.md")
    parser = cli_main.build_parser()
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    return [
        f"docs/cli.md: no `| `{verb}` row in the command table"
        for verb in sorted(sub.choices)
        if not re.search(rf"^\|\s*`{re.escape(verb)}[ `]", doc, re.MULTILINE)
    ]


def adr_problems(root: Path) -> list[str]:
    problems = []
    adr_dir = root / "docs" / "adr"
    by_number: dict[str, list[str]] = {}
    for path in sorted(adr_dir.glob("*.md")):
        match = ADR_FILE_RE.match(path.name)
        if not match:
            continue
        by_number.setdefault(match.group(1), []).append(path.name)
        if not any(line.startswith("- Status:") for line in read_md(path).split("\n")):
            problems.append(f"ADR {path.name} does not declare '- Status:'")
    for number, names in sorted(by_number.items()):
        if len(names) > 1:
            problems.append(f"ADR number {number} is shared by {', '.join(names)}")
    index = root / ADR_INDEX
    if not index.is_file():
        return problems + [f"{ADR_INDEX} is missing"]
    md = read_md(index)
    linked = linked_paths(root, index)
    for names in by_number.values():
        for name in names:
            if f"docs/adr/{name}" not in linked:
                problems.append(f"ADR {name} is not linked in {ADR_INDEX}")
    decision_lines = section_lines(md, "Decisões exigidas") or []
    decision_rows = {row[0]: row for row in table_rows(decision_lines)}
    for decision, (number, owner) in REQUIRED_DECISIONS.items():
        files = by_number.get(number, [])
        if not files:
            problems.append(
                f"required decision '{decision}': ADR {number} is missing "
                f"(blocked on owning spec {owner})"
            )
            continue
        row = decision_rows.get(decision)
        if row is None or len(row) < 3 or f"{files[0]}" not in row[1] or owner not in row[2]:
            problems.append(
                f"required decision '{decision}' is not mapped to ADR {number} "
                f"(owning spec {owner}) in {ADR_INDEX}"
            )
    return problems


def report_problems(root: Path) -> list[str]:
    md = read_md(root / REPORT)
    titles = {text.strip() for level, text in headings(md) if level == 2}
    problems = [
        f"{REPORT}: section '## {title}' is missing"
        for title in REPORT_SECTIONS
        if title not in titles
    ]
    lines = section_lines(md, "Resultados medidos", level=2)
    if lines is None:
        return problems
    rows = table_rows(lines)
    if not rows or "Origem" not in rows[0]:
        return problems + [f"{REPORT}: 'Resultados medidos' has no table with an 'Origem' column"]
    column = rows[0].index("Origem")
    for row in rows[1:]:
        if column >= len(row) or not row[column].strip():
            problems.append(
                f"{REPORT}: measured result '{row[0]}' has an empty Origem "
                "(cite the source or write 'não medido')"
            )
    return problems


# --- the real repository ---------------------------------------------------------------------


def test_relative_links_resolve_and_avoid_local_assets() -> None:
    assert link_problems(REPO) == []


def test_readme_indexes_all_docs() -> None:
    assert readme_index_problems(REPO) == []


def test_examples_use_canonical_cli() -> None:
    assert canonical_cli_problems(REPO) == []


def test_errors_doc_is_canonical() -> None:
    assert errors_doc_problems(REPO) == []


def test_fixed_exits_match_the_cli() -> None:
    assert CLI_FIXED_EXITS == cli_main.FIXED_EXITS, "Wave D revalidation trigger: CLI exits changed"


def test_exit_codes_tables() -> None:
    assert exit_code_problems(REPO) == []


def test_cli_verbs_documented() -> None:
    assert cli_coverage_problems(REPO) == []


def test_adr_index() -> None:
    assert adr_problems(REPO) == []


def test_cycle_report_sections() -> None:
    if not (REPO / REPORT).is_file():
        pytest.skip(f"{REPORT} not written yet (agentic-maintainability task 5.3)")
    assert report_problems(REPO) == []


# --- sensitivity: every checker fails on a deliberately broken copy --------------------------


@pytest.fixture
def docs_copy(tmp_path: Path) -> Path:
    for name in ROOT_DOCS:
        shutil.copyfile(REPO / name, tmp_path / name)
    shutil.copytree(REPO / "docs", tmp_path / "docs")
    return tmp_path


def _edit(path: Path, old: str, new: str) -> None:
    text = read_md(path)
    assert old in text, f"fixture drift: {old!r} not in {path.name}"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def _new_problems(
    root: Path, checker: Callable[[Path], list[str]], mutate: Callable[[], object]
) -> list[str]:
    before = set(checker(root))
    mutate()
    return [problem for problem in checker(root) if problem not in before]


VALID_REPORT = "# Relatório final do Cycle 2\n\n" + "".join(
    f"## {title}\n\nTexto.\n\n" for title in REPORT_SECTIONS
).replace(
    "## Resultados medidos\n\nTexto.\n",
    "## Resultados medidos\n\n| Métrica | Valor | Origem |\n|---|---|---|\n"
    "| suíte offline | verde | `python -m pytest` (2026-10-04) |\n"
    "| latência real | — | não medido |\n",
)


@pytest.mark.parametrize(
    ("doc", "old", "new", "expected"),
    [
        ("README.md", "](docs/cli.md#exit-codes-gerais)", "](docs/missing.md)", "missing file"),
        (
            "README.md",
            "](docs/cli.md#exit-codes-gerais)",
            "](docs/cli.md#nao-existe)",
            "missing anchor",
        ),
        ("docs/cli.md", "## Exit codes gerais", "## Exit codes", "missing anchor"),
        (
            "docs/agentic.md",
            "\n## ",
            "\nVer [roadmap](../.kiro/steering/roadmap.md).\n\n## ",
            "unversioned local asset",
        ),
    ],
)
def test_link_check_detects_defects(
    docs_copy: Path, doc: str, old: str, new: str, expected: str
) -> None:
    found = _new_problems(docs_copy, link_problems, lambda: _edit(docs_copy / doc, old, new))
    assert any(expected in problem for problem in found), found


def test_link_check_flags_kiro_even_in_historical_records(docs_copy: Path) -> None:
    plan = next((docs_copy / "docs" / "superpowers").rglob("*.md"))
    found = _new_problems(
        docs_copy,
        link_problems,
        lambda: plan.write_text(
            read_md(plan) + "\n[spec](../../../.kiro/specs/x/design.md)\n", encoding="utf-8"
        ),
    )
    assert any("unversioned local asset" in problem for problem in found), found


def test_cli_coverage_detects_undocumented_verb(docs_copy: Path) -> None:
    found = _new_problems(
        docs_copy,
        cli_coverage_problems,
        lambda: _edit(docs_copy / "docs/cli.md", "| `decisions` |", "| `removed` |"),
    )
    assert any("decisions" in problem for problem in found), found


def test_readme_index_detects_unindexed_doc(docs_copy: Path) -> None:
    def mutate() -> None:
        (docs_copy / "docs" / "new-doc.md").write_text("# Novo\n", encoding="utf-8")
        (docs_copy / "docs" / "reports").mkdir(exist_ok=True)
        (docs_copy / REPORT).write_text(VALID_REPORT, encoding="utf-8")
        readme = docs_copy / "README.md"  # the real README already links the real report
        readme.write_text(
            re.sub(rf"\[[^\]]*\]\({re.escape(REPORT)}\)", "relatório", read_md(readme)),
            encoding="utf-8",
        )

    found = _new_problems(docs_copy, readme_index_problems, mutate)
    assert found == ["README.md does not link docs/new-doc.md", f"README.md does not link {REPORT}"]


def test_canonical_cli_detects_alias_in_examples(docs_copy: Path) -> None:
    found = _new_problems(
        docs_copy,
        canonical_cli_problems,
        lambda: _edit(docs_copy / "README.md", "theforge doctor\n", "forge doctor\n"),
    )
    assert found == ["README.md: example uses the alias: forge doctor"]


def test_canonical_cli_requires_alias_mention(docs_copy: Path) -> None:
    def mutate() -> None:
        path = docs_copy / "docs" / "cli.md"
        path.write_text(read_md(path).replace("alias", "apelido"), encoding="utf-8")

    found = _new_problems(docs_copy, canonical_cli_problems, mutate)
    assert found == ["docs/cli.md: does not present `forge` as an alias of `theforge`"]


def test_errors_doc_check_detects_code_table_without_link(docs_copy: Path) -> None:
    found = _new_problems(
        docs_copy,
        errors_doc_problems,
        lambda: (docs_copy / "docs" / "codes-excerpt.md").write_text(
            "# Recorte\n\n| Código | Causa |\n|---|---|\n| `FORGE-PLAN-FILE` | x |\n",
            encoding="utf-8",
        ),
    )
    assert found == [
        "docs/codes-excerpt.md has FORGE-* codes but does not link docs/errors.md (canonical list)"
    ]


def test_errors_doc_check_requires_protocol_link(docs_copy: Path) -> None:
    def mutate() -> None:
        path = docs_copy / "docs" / "protocol.md"
        path.write_text(
            re.sub(r"\]\(errors\.md[^)]*\)", "](cli.md)", read_md(path)), encoding="utf-8"
        )

    found = _new_problems(docs_copy, errors_doc_problems, mutate)
    assert any(problem.startswith("docs/protocol.md") for problem in found), found


@pytest.mark.parametrize("doc", ["README.md", "docs/cli.md"])
def test_exit_code_check_detects_missing_code(docs_copy: Path, doc: str) -> None:
    found = _new_problems(
        docs_copy,
        exit_code_problems,
        lambda: _edit(docs_copy / doc, "| 130 | interrompido (Ctrl+C) |\n", ""),
    )
    assert f"{doc}: exit code 130 emitted by the CLI is missing from the table" in found
    assert "exit code 130: README.md and docs/cli.md tables differ" in found


def test_exit_code_check_detects_unknown_code(docs_copy: Path) -> None:
    found = _new_problems(
        docs_copy,
        exit_code_problems,
        lambda: _edit(docs_copy / "README.md", "| 130 |", "| 99 | outro |\n| 130 |"),
    )
    assert "README.md: exit code 99 is not emitted by the CLI" in found


def test_exit_code_check_requires_integrity_meaning(docs_copy: Path) -> None:
    found = _new_problems(
        docs_copy,
        exit_code_problems,
        lambda: _edit(docs_copy / "docs" / "cli.md", "`replay --mode verify`", "`replay`"),
    )
    assert any("exit code 6 must describe" in problem for problem in found), found


def test_adr_check_detects_unindexed_adr(docs_copy: Path) -> None:
    found = _new_problems(
        docs_copy,
        adr_problems,
        lambda: (docs_copy / "docs" / "adr" / "0099-new.md").write_text(
            "# ADR 0099\n\n- Status: proposto\n", encoding="utf-8"
        ),
    )
    assert found == [f"ADR 0099-new.md is not linked in {ADR_INDEX}"]


def test_adr_check_detects_duplicate_number_and_missing_status(docs_copy: Path) -> None:
    found = _new_problems(
        docs_copy,
        adr_problems,
        lambda: (docs_copy / "docs" / "adr" / "0003-duplicate.md").write_text(
            "# Dup\n", encoding="utf-8"
        ),
    )
    assert "ADR 0003-duplicate.md does not declare '- Status:'" in found
    assert "ADR number 0003 is shared by 0003-duplicate.md, 0003-python-stdlib-only.md" in found


def test_adr_check_names_owning_spec_of_missing_decision(docs_copy: Path) -> None:
    found = _new_problems(
        docs_copy,
        adr_problems,
        lambda: (docs_copy / "docs" / "adr" / "0014-provider-adapter-location.md").unlink(),
    )
    assert (
        "required decision 'ownership dos adapters reais': ADR 0014 is missing "
        "(blocked on owning spec real-provider-integration)"
    ) in found


def test_adr_check_detects_unmapped_decision(docs_copy: Path) -> None:
    found = _new_problems(
        docs_copy,
        adr_problems,
        lambda: _edit(docs_copy / ADR_INDEX, "| modelo de policy |", "| outra decisão |"),
    )
    assert found == [
        "required decision 'modelo de policy' is not mapped to ADR 0010 "
        f"(owning spec cycle2-reality-hardening) in {ADR_INDEX}"
    ]


def test_report_check_accepts_a_complete_report(tmp_path: Path) -> None:
    (tmp_path / "docs" / "reports").mkdir(parents=True)
    (tmp_path / REPORT).write_text(VALID_REPORT, encoding="utf-8")
    assert report_problems(tmp_path) == []


def test_report_check_detects_missing_section(tmp_path: Path) -> None:
    (tmp_path / "docs" / "reports").mkdir(parents=True)
    (tmp_path / REPORT).write_text(
        VALID_REPORT.replace("## Prova cross-forge\n", ""), encoding="utf-8"
    )
    assert report_problems(tmp_path) == [f"{REPORT}: section '## Prova cross-forge' is missing"]


def test_report_check_detects_empty_origin(tmp_path: Path) -> None:
    (tmp_path / "docs" / "reports").mkdir(parents=True)
    (tmp_path / REPORT).write_text(VALID_REPORT.replace("| não medido |", "|  |"), encoding="utf-8")
    assert report_problems(tmp_path) == [
        f"{REPORT}: measured result 'latência real' has an empty Origem "
        "(cite the source or write 'não medido')"
    ]


def test_report_links_into_kiro_are_flagged(docs_copy: Path) -> None:
    def mutate() -> None:
        (docs_copy / "docs" / "reports").mkdir(exist_ok=True)
        (docs_copy / REPORT).write_text(
            VALID_REPORT + "\n[spec](../../.kiro/specs/agentic-maintainability/tasks.md)\n",
            encoding="utf-8",
        )

    found = _new_problems(docs_copy, link_problems, mutate)
    assert any(
        problem.startswith(f"{REPORT}:") and "unversioned local asset" in problem
        for problem in found
    ), found
