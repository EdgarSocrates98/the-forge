"""Compatibility matrix (real-provider-integration 4.2, 4.3): ``docs/versioning.md`` is the single
source of the matrix and must cover the versions the code actually ships.

Checked: a row exists for the current ``theforge.__version__``; that row lists the versions of
both adapters as declared in their ``pyproject.toml``; each adapter's ``SUPPORTED_SPECIALIST``
equals the specialist window in that row; the row's Forge Protocol major is supported by the
core. Every failure names the missing or mismatched version and cites the maintenance rule.
"""

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import pytest
import theforge_apiforge
import theforge_sparkforge

import theforge
from theforge.protocol import SUPPORTED_PROTOCOLS, major

REPO = Path(__file__).parents[1]
VERSIONING = REPO / "docs" / "versioning.md"
MATRIX_HEADING = "## Matriz de compatibilidade"
RULE = "docs/versioning.md, seção 'Regra de manutenção'"
COLUMNS = ("The Forge", "Forge Protocol", "theforge-sparkforge-adapter", "sparkforge-aws",
           "theforge-apiforge-adapter", "apiforge", "Suporte até")


@dataclass(frozen=True)
class Adapter:
    column: str          # adapter version column in the matrix
    window_column: str   # specialist window column in the matrix
    version: str         # from the adapter's pyproject.toml
    window: str          # the adapter's SUPPORTED_SPECIALIST


def _cell(text: str) -> str:
    return text.strip().strip("`").strip()


def parse_matrix(markdown: str) -> list[dict[str, str]]:
    """Rows of the first table after the matrix heading, keyed by column name."""
    lines = markdown.splitlines()
    try:
        start = lines.index(MATRIX_HEADING)
    except ValueError:
        raise AssertionError(f"'{MATRIX_HEADING}' missing from docs/versioning.md "
                             f"(rule: {RULE})") from None
    table: list[list[str]] = []
    for line in lines[start + 1:]:
        if line.startswith("## "):
            break
        if line.startswith("|"):
            table.append([_cell(c) for c in line.strip().strip("|").split("|")])
        elif table:
            break
    if len(table) < 2:
        raise AssertionError(f"no table under '{MATRIX_HEADING}' (rule: {RULE})")
    header, rows = table[0], table[2:]
    assert tuple(header) == COLUMNS, f"matrix columns {header} != {list(COLUMNS)}"
    return [dict(zip(header, row, strict=True)) for row in rows]


def _pyproject_version(adapter_dir: str) -> str:
    data = tomllib.loads((REPO / "adapters" / adapter_dir / "pyproject.toml")
                         .read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def current_adapters() -> dict[str, Adapter]:
    return {
        "spark-forge": Adapter("theforge-sparkforge-adapter", "sparkforge-aws",
                               _pyproject_version("sparkforge"),
                               theforge_sparkforge.SUPPORTED_SPECIALIST),
        "api-forge": Adapter("theforge-apiforge-adapter", "apiforge",
                             _pyproject_version("apiforge"),
                             theforge_apiforge.SUPPORTED_SPECIALIST),
    }


def matrix_problems(rows: list[dict[str, str]], forge_version: str,
                    adapters: Mapping[str, Adapter],
                    protocols: tuple[str, ...]) -> list[str]:
    matching = [r for r in rows if r["The Forge"] == forge_version]
    if not matching:
        return [f"The Forge {forge_version} has no row in the compatibility matrix; add it in "
                f"the same commit that changes theforge.__version__ (rule: {RULE})"]
    if len(matching) > 1:
        return [f"The Forge {forge_version} has {len(matching)} rows in the compatibility "
                f"matrix; keep exactly one (rule: {RULE})"]
    row = matching[0]
    problems = []
    for adapter_id, a in adapters.items():
        if row[a.column] != a.version:
            problems.append(f"{a.column} {a.version} ({adapter_id}) is not in the matrix row "
                            f"for The Forge {forge_version} (found '{row[a.column]}'; "
                            f"rule: {RULE})")
        if row[a.window_column] != a.window:
            problems.append(f"{a.window_column} window '{row[a.window_column]}' in the matrix "
                            f"row for The Forge {forge_version} differs from {adapter_id} "
                            f"SUPPORTED_SPECIALIST '{a.window}' (rule: {RULE})")
    supported = {major(p) for p in protocols}
    row_major = major(row["Forge Protocol"])
    if row_major is None or row_major not in supported:
        problems.append(f"Forge Protocol '{row['Forge Protocol']}' in the matrix row for "
                        f"The Forge {forge_version} is not in SUPPORTED_PROTOCOLS "
                        f"{list(protocols)} (rule: {RULE})")
    if not row["Suporte até"]:
        problems.append(f"'Suporte até' is empty in the matrix row for The Forge "
                        f"{forge_version} (rule: {RULE})")
    return problems


def _rows() -> list[dict[str, str]]:
    return parse_matrix(VERSIONING.read_text(encoding="utf-8"))


def test_matrix_covers_current_versions() -> None:
    assert matrix_problems(_rows(), theforge.__version__, current_adapters(),
                           SUPPORTED_PROTOCOLS) == []


def test_versioning_doc_states_rules_separately() -> None:
    text = VERSIONING.read_text(encoding="utf-8")
    for heading in ("## Versão de pacote", "## Versão de protocolo",
                    "## Versão de schema de contrato", "## Versão de provider",
                    "## Evolução de capability", "## Janela de suporte",
                    MATRIX_HEADING, "## Regra de manutenção"):
        assert heading in text.splitlines(), f"{heading!r} missing from docs/versioning.md"


def test_forge_version_bump_without_row_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(theforge, "__version__", "0.99.0")
    problems = matrix_problems(_rows(), theforge.__version__, current_adapters(),
                               SUPPORTED_PROTOCOLS)
    assert len(problems) == 1
    assert "0.99.0" in problems[0] and RULE in problems[0]


@pytest.mark.parametrize("adapter_id", ["spark-forge", "api-forge"])
def test_adapter_version_bump_without_row_fails(adapter_id: str) -> None:
    adapters = current_adapters()
    bumped = {**adapters, adapter_id: Adapter(adapters[adapter_id].column,
                                              adapters[adapter_id].window_column, "0.98.0",
                                              adapters[adapter_id].window)}
    problems = matrix_problems(_rows(), theforge.__version__, bumped, SUPPORTED_PROTOCOLS)
    assert len(problems) == 1
    assert "0.98.0" in problems[0] and adapter_id in problems[0] and RULE in problems[0]


@pytest.mark.parametrize("module", [theforge_sparkforge, theforge_apiforge])
def test_specialist_window_change_without_row_fails(monkeypatch: pytest.MonkeyPatch,
                                                    module: object) -> None:
    monkeypatch.setattr(module, "SUPPORTED_SPECIALIST", ">=9.0.0,<9.1.0")
    problems = matrix_problems(_rows(), theforge.__version__, current_adapters(),
                               SUPPORTED_PROTOCOLS)
    assert len(problems) == 1
    assert ">=9.0.0,<9.1.0" in problems[0] and RULE in problems[0]


def test_unsupported_protocol_major_fails() -> None:
    problems = matrix_problems(_rows(), theforge.__version__, current_adapters(),
                               ("forge/v2",))
    assert len(problems) == 1
    assert "forge/v1" in problems[0] and RULE in problems[0]


def test_parse_matrix_reads_table_and_rejects_missing_heading() -> None:
    header = "| " + " | ".join(COLUMNS) + " |"
    doc = "\n".join([MATRIX_HEADING, "", header, "|" + "---|" * len(COLUMNS),
                     "| 1.0.0 | `forge/v1` | 1.0.0 | `>=1.0.0,<1.1.0` | 1.0.0 | "
                     "`>=1.0.0,<1.1.0` | x |", "", "## Next"])
    assert parse_matrix(doc) == [dict(zip(COLUMNS, ["1.0.0", "forge/v1", "1.0.0",
                                                    ">=1.0.0,<1.1.0", "1.0.0",
                                                    ">=1.0.0,<1.1.0", "x"], strict=True))]
    with pytest.raises(AssertionError, match="Regra de manutenção"):
        parse_matrix("# nothing here\n")
