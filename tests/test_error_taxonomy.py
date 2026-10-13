"""Error taxonomy: every FORGE-* code has exactly one family, documented and frozen (13.1-13.3).

``docs/errors.md`` is the canonical code list; ``tests/golden/forge_codes.json`` freezes the
published values; native provider codes (``AF-*``, ``SPARKFORGE-*``...) have no family.
"""

import json
import re
from pathlib import Path
from typing import get_args

import pytest

from theforge import errors
from theforge.contracts.codes import CODE_FAMILIES, Codes, ErrorFamily, family_of
from theforge.errors import ForgeError, PersistenceError, ReplayRefused, UsageError
from theforge.runs import RunStore, new_run_id

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
ERRORS_MD = DOCS / "errors.md"
PROTOCOL_MD = DOCS / "protocol.md"
GOLDEN = Path(__file__).parent / "golden" / "forge_codes.json"

FAMILIES: frozenset[str] = frozenset(get_args(ErrorFamily))
# A FORGE-* token not preceded by a letter/digit/dash (excludes SPARKFORGE-*, APIFORGE-*).
_CODE_TOKEN = re.compile(r"(?<![A-Za-z0-9-])FORGE-[A-Z0-9*-]*[A-Z0-9*]")
_ERRORS_ROW = re.compile(r"^\|\s*`(FORGE-[A-Z0-9-]+)`\s*\|\s*`?([a-z]+)`?\s*\|")


def _code_values() -> dict[str, str]:
    return {name: value for name, value in vars(Codes).items() if name.isupper()}


def _errors_table() -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in ERRORS_MD.read_text(encoding="utf-8").splitlines():
        match = _ERRORS_ROW.match(line)
        if match:
            code, family = match.groups()
            assert code not in rows, f"{code} listed twice in docs/errors.md"
            rows[code] = family
    return rows


def _cited_codes(text: str) -> set[str]:
    """Concrete codes cited in a document (wildcards such as ``FORGE-PLAN-*`` are skipped)."""
    return {token for token in _CODE_TOKEN.findall(text) if "*" not in token}


def _doc_files() -> list[Path]:
    return sorted([*DOCS.glob("*.md"), *(DOCS / "adr").glob("*.md"), ROOT / "README.md"])


# --- taxonomy ------------------------------------------------------------------------------


def test_every_code_has_exactly_one_known_family() -> None:
    values = set(_code_values().values())
    assert set(CODE_FAMILIES) == values, "CODE_FAMILIES must cover exactly the Codes values"
    assert set(CODE_FAMILIES.values()) <= FAMILIES


def test_family_set_is_the_documented_one() -> None:
    documented = {
        "protocol",
        "registry",
        "routing",
        "plan",
        "context",
        "provider",
        "policy",
        "persistence",
        "security",
        "workspace",
        "replay",
        "usage",
        "internal",
    }
    assert set(get_args(ErrorFamily)) == documented


def test_routing_has_no_codes() -> None:
    assert "routing" not in set(CODE_FAMILIES.values())


@pytest.mark.parametrize(
    ("code", "family"),
    [
        (Codes.PROVIDER_BLOCKED, "security"),
        (Codes.PROVIDER_UNTRUSTED, "security"),
        (Codes.PROVIDER_NOT_READY, "provider"),
        (Codes.MANIFEST_VERSION, "registry"),
        (Codes.MANIFEST_TAXONOMY, "registry"),
        (Codes.MANIFEST_LIMITS, "registry"),
        (Codes.REGISTRY_MANIFEST_CHANGED, "registry"),
        (Codes.CONTEXT_REQUEST_LIMIT, "context"),
        (Codes.RECEIPT_INVALID, "persistence"),
        (Codes.RESULT_ARTIFACT_HASH, "provider"),
        (Codes.PERSIST_DIVERGENCE, "persistence"),
        (Codes.PLAN_FILE, "plan"),
        (Codes.WORKSPACE_GRAPH_EDGE, "workspace"),
        (Codes.REPLAY_NOT_REPRODUCIBLE, "replay"),
        (Codes.USAGE, "usage"),
        (Codes.INTERNAL, "internal"),
    ],
)
def test_family_of_known_codes(code: str, family: str) -> None:
    assert family_of(code) == family


@pytest.mark.parametrize(
    "code",
    [
        "AF-X",
        "AF-CLI-INTERNAL",
        "SPARKFORGE-TOOL-ERROR",
        "SPARKFORGE-ADAPTER-NATIVE-FAILED",
        "APIFORGE-ADAPTER-NATIVE-INVALID",
        "ADAPTER-INTERNAL",
        "FORGE-NOT-A-CODE",
        "",
    ],
)
def test_native_and_unknown_codes_have_no_family(code: str) -> None:
    assert family_of(code) is None


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("PLAN_INVALID", "FORGE-PLAN-INVALID"),
        ("PLAN_CAPABILITY", "FORGE-PLAN-CAPABILITY"),
        ("PLAN_LIMIT", "FORGE-PLAN-LIMIT"),
        ("PLAN_PATTERN_RESERVED", "FORGE-PLAN-PATTERN-RESERVED"),
        ("PLAN_FILE", "FORGE-PLAN-FILE"),
        ("PLAN_DEPENDENCY_FAILED", "FORGE-PLAN-DEPENDENCY-FAILED"),
        ("PLAN_ESTIMATE", "FORGE-PLAN-ESTIMATE"),
        ("WORKSPACE_CONFIG", "FORGE-WORKSPACE-CONFIG"),
        ("WORKSPACE_GRAPH_EDGE", "FORGE-WORKSPACE-GRAPH-EDGE"),
        ("PERSIST_WRITE", "FORGE-PERSIST-WRITE"),
        ("PERSIST_READ", "FORGE-PERSIST-READ"),
        ("PERSIST_DIVERGENCE", "FORGE-PERSIST-DIVERGENCE"),
        ("RESULT_ARTIFACT_HASH", "FORGE-RESULT-ARTIFACT-HASH"),
        ("REPLAY_NOT_REPRODUCIBLE", "FORGE-REPLAY-NOT-REPRODUCIBLE"),
        ("REPLAY_UNSUPPORTED", "FORGE-REPLAY-UNSUPPORTED"),
    ],
)
def test_new_wave_d_codes_are_declared(name: str, value: str) -> None:
    assert getattr(Codes, name) == value


# --- frozen values -------------------------------------------------------------------------


def test_published_values_match_golden() -> None:
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert _code_values() == golden, (
        "a published FORGE-* value changed or a code was added/removed: values never change; "
        "additions must also update tests/golden/forge_codes.json"
    )


# --- documentation -------------------------------------------------------------------------


def test_errors_md_table_matches_code_families() -> None:
    assert _errors_table() == dict(CODE_FAMILIES)


def test_errors_md_explains_routing_outcomes() -> None:
    text = ERRORS_MD.read_text(encoding="utf-8")
    assert "`routing`" in text
    assert "`ambiguous`" in text and "`no_route`" in text


def test_protocol_md_links_errors_md() -> None:
    assert "(errors.md)" in PROTOCOL_MD.read_text(encoding="utf-8")


def test_protocol_md_has_no_competing_full_table() -> None:
    """protocol.md keeps a short table (manifest/context-request codes); the list is errors.md."""
    text = PROTOCOL_MD.read_text(encoding="utf-8")
    tabled = {
        m.group(1)
        for line in text.splitlines()
        if (m := re.match(r"^\|\s*`(FORGE-[A-Z0-9-]+)`", line))
    }
    assert tabled, "protocol.md lost its short code table"
    assert all(code.startswith(("FORGE-MANIFEST-", "FORGE-CONTEXT-REQUEST-")) for code in tabled), (
        sorted(tabled)
    )


@pytest.mark.parametrize("doc", _doc_files(), ids=lambda p: p.relative_to(ROOT).as_posix())
def test_codes_cited_in_docs_exist_in_errors_md(doc: Path) -> None:
    unknown = _cited_codes(doc.read_text(encoding="utf-8")) - set(_errors_table())
    assert unknown == set()


@pytest.mark.parametrize("doc", _doc_files(), ids=lambda p: p.relative_to(ROOT).as_posix())
def test_doc_tables_agree_on_family(doc: Path) -> None:
    """A table row pairing a code with a family name must use the errors.md family."""
    canonical = _errors_table()
    conflicts = []
    for line in doc.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip().strip("`") for cell in line.strip("|").split("|")]
        codes = [cell for cell in cells if cell in canonical]
        families = [cell for cell in cells if cell in FAMILIES]
        if codes and families:
            conflicts += [(code, families[0]) for code in codes if canonical[code] != families[0]]
    assert conflicts == []


# --- every expected error carries a taxonomy code ------------------------------------------


def test_errors_module_exposes_replay_refused() -> None:
    assert "ReplayRefused" in errors.__all__


@pytest.mark.parametrize("cls", [ForgeError, UsageError, PersistenceError, ReplayRefused])
def test_every_forge_error_class_has_a_taxonomy_default_code(cls: type[ForgeError]) -> None:
    assert family_of(cls.default_code) is not None


def test_usage_error_codes() -> None:
    assert UsageError("bad").code == Codes.USAGE
    plan_file = UsageError("unreadable plan", code=Codes.PLAN_FILE)
    assert plan_file.code == Codes.PLAN_FILE
    assert str(plan_file) == "unreadable plan"


def test_forge_error_rejects_codes_outside_the_taxonomy() -> None:
    with pytest.raises(ValueError, match="taxonomy"):
        UsageError("x", code="AF-X")
    with pytest.raises(ValueError, match="taxonomy"):
        UsageError("x", code="FORGE-NOT-A-CODE")


def test_replay_refused_carries_code_and_reasons() -> None:
    refused = ReplayRefused(("non_reproducible", "provider version changed"))
    assert refused.code == Codes.REPLAY_NOT_REPRODUCIBLE
    assert refused.reasons == ("non_reproducible", "provider version changed")
    assert "provider version changed" in str(refused)
    plan = ReplayRefused(("plan runs cannot be re-executed",), code=Codes.REPLAY_UNSUPPORTED)
    assert plan.code == Codes.REPLAY_UNSUPPORTED
    assert family_of(plan.code) == "replay"


def test_replay_refused_requires_a_replay_code() -> None:
    with pytest.raises(ValueError):
        ReplayRefused(("x",), code=Codes.USAGE)


def test_persistence_write_failure_has_write_code(tmp_path: Path) -> None:
    not_a_dir = tmp_path / "forge-file"
    not_a_dir.write_text("x", encoding="utf-8")
    with pytest.raises(PersistenceError) as caught:
        RunStore(not_a_dir).create(new_run_id())
    assert caught.value.code == Codes.PERSIST_WRITE


def test_persistence_read_failure_has_read_code(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    run_id = new_run_id()
    store.create(run_id)
    (store.run_dir(run_id) / "task.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(PersistenceError) as caught:
        store.read_optional(run_id, "task")
    assert caught.value.code == Codes.PERSIST_READ
    (store.run_dir(run_id) / "task.json").write_text("[1]", encoding="utf-8")
    with pytest.raises(PersistenceError) as caught:
        store.read_optional(run_id, "task")
    assert caught.value.code == Codes.PERSIST_READ


def test_workspace_init_failure_has_write_code(tmp_path: Path) -> None:
    from theforge.state import init_workspace

    (tmp_path / ".forge").write_text("not a directory", encoding="utf-8")
    with pytest.raises(PersistenceError) as caught:
        init_workspace(tmp_path)
    assert caught.value.code == Codes.PERSIST_WRITE
