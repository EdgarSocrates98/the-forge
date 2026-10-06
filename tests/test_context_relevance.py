"""Relevance: generic signals, intent path references and the fixed priority order.

Requirements 1.5, 1.8, 2.1-2.6, 4.2, 4.3.
"""

from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from theforge.context.relevance import IntentRefs, RankedFile, parse_intent_refs, rank_candidates
from theforge.context.scan import WorkspaceScan
from theforge.contracts import ExcludedFile, TaskSpec
from theforge.contracts.canonical import utc_now
from theforge.contracts.context import LineRange
from theforge.meta import PRODUCER

ROOT = Path("/ws")


def scan(files: list[str], excluded: list[ExcludedFile] | None = None) -> WorkspaceScan:
    return WorkspaceScan(root=ROOT, files=files, excluded=excluded or [])


def task(intent: str = "x", targets: list[str] | None = None) -> TaskSpec:
    return TaskSpec(producer=PRODUCER, created_at=utc_now(), id="t1", intent=intent,
                    workspace_root=str(ROOT), targets=targets if targets is not None else ["."])


def rank(
    files: list[str], *, intent: str = "x", targets: list[str] | None = None,
    globs: list[str] | None = None, changed: frozenset[str] = frozenset(),
    excluded: list[ExcludedFile] | None = None,
) -> tuple[list[RankedFile], int]:
    s = scan(files, excluded)
    return rank_candidates(task(intent, targets), globs or [], s, changed,
                           parse_intent_refs(intent, s))


def by_path(ranked: list[RankedFile]) -> dict[str, RankedFile]:
    return {r.path: r for r in ranked}


# --- intent references (2.3, 2.4, 1.5) -------------------------------------------------------

def test_intent_cites_relative_path_with_slash() -> None:
    refs = parse_intent_refs("please fix a/b.md now", scan(["a/b.md", "c.md"]))
    assert refs.paths == frozenset({"a/b.md"})
    assert dict(refs.ranges) == {} and dict(refs.rejected) == {}


def test_intent_cites_bare_file_name_with_extension() -> None:
    refs = parse_intent_refs("look at b.md", scan(["b.md"]))
    assert refs.paths == frozenset({"b.md"})


@pytest.mark.parametrize(("token", "expected"), [
    ("b.md:10-20", LineRange(start=10, end=20)),
    ("b.md:7", LineRange(start=7, end=7)),
    ("b.md:L3-L4", LineRange(start=3, end=4)),
    ("b.md#L3-L4", LineRange(start=3, end=4)),
])
def test_intent_line_range_suffixes(token: str, expected: LineRange) -> None:
    refs = parse_intent_refs(f"explain {token} please", scan(["b.md"]))
    assert refs.paths == frozenset({"b.md"})
    assert dict(refs.ranges) == {"b.md": expected}


def test_intent_hash_single_line_suffix() -> None:
    refs = parse_intent_refs("explain b.md#L7 please", scan(["b.md"]))
    assert refs.paths == frozenset({"b.md"})
    assert dict(refs.ranges) == {"b.md": LineRange(start=7, end=7)}


def test_intent_slash_words_without_extension_are_not_citations() -> None:
    refs = parse_intent_refs("read and/or write, input/output", scan(["a/b.md"]))
    assert refs.paths == frozenset() and dict(refs.rejected) == {}


def test_intent_extless_missing_path_is_not_a_missing_citation() -> None:
    refs = parse_intent_refs("check src/Makefile", scan(["a/b.md"]))
    assert refs.paths == frozenset() and dict(refs.rejected) == {}


def test_intent_extless_cited_path_still_resolves() -> None:
    refs = parse_intent_refs("check src/Makefile", scan(["src/Makefile"]))
    assert refs.paths == frozenset({"src/Makefile"})


def test_intent_normalizes_backslash_and_leading_dot_slash() -> None:
    refs = parse_intent_refs(r"see .\a\b.md and ./c/d.py", scan(["a/b.md", "c/d.py"]))
    assert refs.paths == frozenset({"a/b.md", "c/d.py"})


def test_intent_strips_surrounding_punctuation() -> None:
    refs = parse_intent_refs("check (`a/b.md`), and 'c.py'.", scan(["a/b.md", "c.py"]))
    assert refs.paths == frozenset({"a/b.md", "c.py"})


def test_intent_ignores_plain_words_and_urls() -> None:
    refs = parse_intent_refs("refactor the parser, see https://example.com/x for v1.2",
                             scan(["parser.py"]))
    assert refs.paths == frozenset() and dict(refs.rejected) == {}


def test_intent_invalid_range_keeps_path_without_range() -> None:
    refs = parse_intent_refs("b.md:9-3 and b.md:0", scan(["b.md"]))
    assert refs.paths == frozenset({"b.md"}) and dict(refs.ranges) == {}


def test_intent_repeated_ranges_merge_to_covering_span() -> None:
    refs = parse_intent_refs("b.md:10-12 then b.md:3-4", scan(["b.md"]))
    assert dict(refs.ranges) == {"b.md": LineRange(start=3, end=12)}


@pytest.mark.parametrize(("token", "key", "reason"), [
    ("../x.md", "../x.md", "outside_root"),
    ("a/../../x.md", "a/../../x.md", "outside_root"),
    ("C:/x.md", "C:/x.md", "outside_root"),
    ("/etc/passwd", "/etc/passwd", "outside_root"),
    (".env", ".env", "secret"),
    ("conf/id_rsa.key", "conf/id_rsa.key", "secret"),
    ("nope/missing.md", "nope/missing.md", "missing"),
])
def test_intent_rejected_citations(token: str, key: str, reason: str) -> None:
    refs = parse_intent_refs(f"use {token}", scan(["a/b.md"]))
    assert refs.paths == frozenset()
    assert dict(refs.rejected) == {key: reason}


def test_intent_citation_excluded_as_secret_by_scan() -> None:
    s = scan(["a.md"], [ExcludedFile(path="cfg/prod.ini", reason="secret")])
    refs = parse_intent_refs("read cfg/prod.ini", s)
    assert dict(refs.rejected) == {"cfg/prod.ini": "secret"}


def test_intent_refs_type() -> None:
    assert isinstance(parse_intent_refs("x", scan([])), IntentRefs)


# --- each signal (2.1) --------------------------------------------------------------------

def test_signal_intent_path_and_lines() -> None:
    ranked, _ = rank(["a/b.md", "c.md"], intent="see a/b.md and c.md:2-3")
    got = by_path(ranked)
    assert got["a/b.md"].signals == ("intent_path",) and got["a/b.md"].lines is None
    assert got["c.md"].signals == ("intent_lines", "intent_path")
    assert got["c.md"].lines == LineRange(start=2, end=3)


def test_signal_target_explicit_only() -> None:
    files = ["src/a.py", "src2/b.py", "docs/c.md", "top.py"]
    ranked, unmatched = rank(files, targets=["src", "./docs/", "top.py"])
    got = by_path(ranked)
    assert got["src/a.py"].signals == ("target:src",)
    assert got["docs/c.md"].signals == ("target:docs",)
    assert got["top.py"].signals == ("target:top.py",)
    assert "src2/b.py" not in got and unmatched == 1


def test_signal_default_target_gives_nothing() -> None:
    ranked, unmatched = rank(["a.py", "b.py"], targets=["."])
    assert ranked == [] and unmatched == 2


def test_signal_glob_sorted_and_deduplicated() -> None:
    ranked, _ = rank(["api/openapi.yaml"], globs=["openapi.yaml", "*.yaml", "*.yaml"])
    assert ranked[0].signals == ("glob:*.yaml", "glob:openapi.yaml")


def test_signal_git_changed_only_for_scanned_files() -> None:
    ranked, _ = rank(["a.py"], changed=frozenset({"a.py", "gone.py"}))
    assert [(r.path, r.signals) for r in ranked] == [("a.py", ("git:changed",))]


def test_signal_dependency_manifest_generic_and_root_only() -> None:
    files = ["pyproject.toml", "requirements-dev.txt", "package.json",
             "sub/package.json", "requirements/dev.txt", "setup.cfg"]
    ranked, unmatched = rank(files)
    assert sorted(r.path for r in ranked) == ["package.json", "pyproject.toml",
                                              "requirements-dev.txt"]
    assert all(r.signals == ("dependency_manifest",) for r in ranked)
    assert unmatched == 3


def test_all_signals_on_one_file_in_fixed_order() -> None:
    ranked, _ = rank(["pyproject.toml"], intent="edit pyproject.toml:1-2",
                     targets=["pyproject.toml"], globs=["*.toml"],
                     changed=frozenset({"pyproject.toml"}))
    assert ranked[0].signals == ("intent_lines", "intent_path", "target:pyproject.toml",
                                 "glob:*.toml", "git:changed", "dependency_manifest")


# --- priority (2.2) and aggregate no_signal (4.3) -------------------------------------------

def test_priority_one_file_per_class() -> None:
    files = ["pyproject.toml",  # dependency only
             "y_git.py", "x_glob.yaml", "w_glob_git.yaml", "v_target/f.py",
             "u_intent.md", "t_none.txt"]
    ranked, unmatched = rank(
        files, intent="see u_intent.md", targets=["v_target"], globs=["*.yaml"],
        changed=frozenset({"y_git.py", "w_glob_git.yaml"}),
    )
    assert [r.path for r in ranked] == [
        "u_intent.md", "v_target/f.py", "w_glob_git.yaml", "x_glob.yaml", "y_git.py",
        "pyproject.toml",
    ]
    assert unmatched == 1


def test_priority_more_glob_hits_first_then_path() -> None:
    ranked, _ = rank(["b.yaml", "a.yaml", "openapi.yaml"], globs=["*.yaml", "openapi.yaml"])
    assert [r.path for r in ranked] == ["openapi.yaml", "a.yaml", "b.yaml"]


def test_priority_glob_beats_git_hits_count_after_git() -> None:
    ranked, _ = rank(["a.yaml", "openapi.yaml"], globs=["*.yaml", "openapi.yaml"],
                     changed=frozenset({"a.yaml"}))
    # git-changed glob files come before unchanged ones, even with fewer glob hits.
    assert [r.path for r in ranked] == ["a.yaml", "openapi.yaml"]


def test_rejected_citation_never_ranked() -> None:
    ranked, unmatched = rank(["a.md"], intent="use ../a.md and .env")
    assert ranked == [] and unmatched == 1


def test_duplicate_scan_entries_counted_once() -> None:
    ranked, unmatched = rank(["a.py", "a.py", "b.yaml"], globs=["*.yaml"])
    assert [r.path for r in ranked] == ["b.yaml"] and unmatched == 1


# --- determinism (1.8): permutation of scan.files and globs ---------------------------------

_NAMES = ["pyproject.toml", "a/b.md", "a/c.yaml", "openapi.yaml", "src/x.py", "src/y.yaml",
          "requirements.txt", "z.txt", "docs/d.md", "e.yaml"]
_GLOBS = ["*.yaml", "openapi.yaml", "*.md", "src/*.py"]


@settings(max_examples=60, deadline=None)
@given(files=st.permutations(_NAMES), globs=st.permutations(_GLOBS))
def test_same_output_for_any_permutation(files: list[str], globs: list[str]) -> None:
    intent = "fix a/b.md:2-5 and z.txt, not ../q.md"
    changed = frozenset({"e.yaml", "z.txt"})
    expected = rank(sorted(_NAMES), intent=intent, targets=["src"], globs=sorted(_GLOBS),
                    changed=changed)
    got = rank(list(files), intent=intent, targets=["src"], globs=list(globs), changed=changed)
    assert got == expected
    s = scan(list(files))
    assert parse_intent_refs(intent, s) == parse_intent_refs(intent, scan(sorted(_NAMES)))


@pytest.mark.parametrize(
    "target", ["src", "./src/", "src/../src", "docs/../src", str(ROOT / "src")])
def test_signal_target_normalized_like_the_scan(target: str) -> None:
    ranked, _ = rank(["src/a.py", "docs/b.md"], targets=[target])
    assert [(r.path, r.signals) for r in ranked] == [("src/a.py", ("target:src",))]


@pytest.mark.parametrize("target", [".", "./", str(ROOT), "..", "../other", "src/../..",
                                    "/elsewhere/src"])
def test_signal_target_root_or_outside_gives_nothing(target: str) -> None:
    ranked, unmatched = rank(["src/a.py"], targets=[target])
    assert ranked == [] and unmatched == 1


def test_intent_rejects_home_relative_citation() -> None:
    refs = parse_intent_refs("use ~/notes.md", scan(["a.md"]))
    assert dict(refs.rejected) == {"~/notes.md": "outside_root"}
