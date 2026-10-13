import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from helpers import write_file
from theforge.context import (
    BUDGETS,
    broker,
    build_context_pack,
    effective_tiers,
    extend_context_pack,
    scan_workspace,
)
from theforge.context.fingerprints import FingerprintStore, hash_lines
from theforge.context.git import GitState
from theforge.context.verify import reverify
from theforge.contracts import ExcludedFile, TaskSpec
from theforge.contracts.base import to_dict
from theforge.contracts.canonical import utc_now
from theforge.contracts.context import ContextPack, GitSummary, LineRange
from theforge.contracts.integrity import validate_context_pack
from theforge.contracts.manifest import CapabilityContext
from theforge.contracts.result import ContextRequest, ContextRequestItem
from theforge.contracts.types import BudgetProfile
from theforge.meta import PRODUCER
from theforge.profiles import ContextProfile, profile_for


def task(root: Path, profile: str = "balanced") -> TaskSpec:
    return TaskSpec(
        producer=PRODUCER,
        created_at=utc_now(),
        id="t1",
        intent="x",
        workspace_root=str(root),
        budget_profile=profile,
    )


def test_pack_selects_by_glob_and_hashes(tmp_path: Path) -> None:
    write_file(tmp_path, "api/openapi.yaml", "openapi: 3.0.0\n")
    write_file(tmp_path, "api/main.py", "x=1\n")
    write_file(tmp_path, ".env", "A=1")
    pack = build_context_pack(
        task(tmp_path), "api-forge", ["openapi.yaml", "*.yaml"], scan_workspace(tmp_path, ["."])
    )
    assert [f.path for f in pack.files] == ["api/openapi.yaml"]
    item = pack.files[0]
    assert item.sha256 == hashlib.sha256(b"openapi: 3.0.0\n").hexdigest()
    assert item.bytes == 15 and item.reason == "glob:*.yaml;glob:openapi.yaml"
    assert item.signals == ["glob:*.yaml", "glob:openapi.yaml"] and item.tier == "reference"
    assert pack.status == "complete" and not pack.truncated
    assert pack.used_bytes == 15 and pack.budget_bytes == BUDGETS["balanced"]
    assert ExcludedFile(path=".env", reason="secret") in pack.excluded


def test_pack_orders_by_glob_hits_then_path(tmp_path: Path) -> None:
    for name in ("b.yaml", "a.yaml", "openapi.yaml"):
        write_file(tmp_path, name, "x")
    pack = build_context_pack(
        task(tmp_path), "p", ["*.yaml", "openapi.yaml"], scan_workspace(tmp_path, ["."])
    )
    assert [f.path for f in pack.files] == ["openapi.yaml", "a.yaml", "b.yaml"]


def test_pack_respects_budget(tmp_path: Path) -> None:
    write_file(tmp_path, "big.txt", "x" * 70_000)
    write_file(tmp_path, "small.txt", "0123456789")
    pack = build_context_pack(
        task(tmp_path, "economy"), "p", ["*.txt"], scan_workspace(tmp_path, ["."])
    )
    assert [f.path for f in pack.files] == ["small.txt"]
    assert ExcludedFile(path="big.txt", reason="budget", signals=["glob:*.txt"]) in pack.excluded
    assert pack.truncated and pack.status == "truncated"


def grow_after_stat(monkeypatch: pytest.MonkeyPatch, target: Path, extra: bytes) -> None:
    """The broker's ``os.stat`` sees the old size; the file grows right after (TOCTOU)."""
    real_stat = os.stat

    def stat_then_grow(path: Any, *args: Any, **kwargs: Any) -> os.stat_result:
        result = real_stat(path, *args, **kwargs)
        if Path(path) == target and real_stat(target).st_size == result.st_size:
            with target.open("ab") as fh:
                fh.write(extra)
        return result

    monkeypatch.setattr(broker, "os", SimpleNamespace(stat=stat_then_grow, path=os.path))


@pytest.mark.parametrize("excerpts", [False, True])
def test_pack_bounds_read_when_file_grows_after_stat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, excerpts: bool
) -> None:
    write_file(tmp_path, "small.txt", "0123456789\n")
    scan = scan_workspace(tmp_path, ["."])
    target = (tmp_path / "small.txt").resolve()
    grow_after_stat(monkeypatch, target, b"y" * 70_000)
    store = FingerprintStore(tmp_path, enabled=False)
    pack = build_context_pack(
        task(tmp_path, "max"),
        "p",
        ["*.txt"],
        scan,
        profile=small("max", budget=100),
        capability_context=EXCERPTS if excerpts else CapabilityContext(),
        fingerprints=store,
    )
    validate_context_pack(pack)
    assert target.stat().st_size == 70_011  # grew between the size check and the read
    assert store.stats.misses == 1  # the stale size passed the pre-check: it was hashed
    if excerpts:  # does not fit any more -> longest prefix of complete lines
        (item,) = pack.files
        assert item.tier == "excerpt" and item.lines == LineRange(start=1, end=1)
        assert item.sha256 == hashlib.sha256(b"0123456789\n").hexdigest()
    else:
        assert pack.files == []
        assert (
            ExcludedFile(path="small.txt", reason="budget", signals=["glob:*.txt"]) in pack.excluded
        )
        assert pack.truncated
    assert pack.used_bytes <= pack.budget_bytes


def test_extend_bounds_read_when_file_grows_after_stat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_file(tmp_path, "a.md", "a\n")
    write_file(tmp_path, "b.py", "b\n")
    profile = small("max", budget=100)
    pack = build(tmp_path, ["*.md"], profile=profile, cap=EXCERPTS)
    target = (tmp_path / "b.py").resolve()
    grow_after_stat(monkeypatch, target, b"y" * 70_000)
    out = extend(pack, tmp_path, request(("b.py", None)), profile)
    assert target.stat().st_size == 70_002
    assert out.files == pack.files and out.used_bytes <= out.budget_bytes
    assert ExcludedFile(path="b.py", reason="budget", signals=["requested"]) in out.excluded


def test_pack_without_globs_is_empty(tmp_path: Path) -> None:
    write_file(tmp_path, "a.txt", "x")
    pack = build_context_pack(task(tmp_path), "p", [], scan_workspace(tmp_path, ["."]))
    assert pack.files == [] and pack.used_bytes == 0


# --- context v2: tiers, signals, budget and file limit (task 3.6) --------------------------

EXCERPTS = CapabilityContext(excerpts=True, requests=True)
LINES10 = "".join(f"line {i:02d}\n" for i in range(1, 11))  # 10 lines x 8 bytes
GH_TOKEN = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"


def v2_task(root: Path, profile: BudgetProfile = "balanced", intent: str = "x") -> TaskSpec:
    return TaskSpec(
        producer=PRODUCER,
        created_at=utc_now(),
        id="t1",
        intent=intent,
        workspace_root=str(root),
        budget_profile=profile,
    )


def small(
    name: BudgetProfile = "balanced", budget: int | None = None, max_files: int | None = None
) -> ContextProfile:
    base = profile_for(name)
    return replace(
        base,
        budget_bytes=base.budget_bytes if budget is None else budget,
        max_files=base.max_files if max_files is None else max_files,
    )


def build(
    root: Path,
    globs: list[str],
    *,
    profile: ContextProfile | None = None,
    cap: CapabilityContext | None = None,
    intent: str = "x",
    git: GitState | None = None,
    store: FingerprintStore | None = None,
    profile_name: BudgetProfile = "balanced",
) -> ContextPack:
    pack = build_context_pack(
        v2_task(root, profile_name, intent),
        "p",
        globs,
        scan_workspace(root, ["."]),
        profile=profile,
        capability_context=cap or CapabilityContext(),
        git=git,
        fingerprints=store,
    )
    validate_context_pack(pack)
    return pack


def test_effective_tiers_intersect_profile_and_capability() -> None:
    assert effective_tiers(profile_for("max"), CapabilityContext()) == frozenset(
        {"metadata", "reference"}
    )
    assert effective_tiers(profile_for("max"), EXCERPTS) == frozenset(
        {"metadata", "reference", "excerpt", "requested"}
    )
    assert effective_tiers(profile_for("economy"), EXCERPTS) == frozenset({"metadata", "reference"})


@pytest.mark.parametrize("profile_name", ["economy", "balanced", "max"])
def test_workspace_summary_always_present_with_zero_bytes(
    tmp_path: Path, profile_name: BudgetProfile
) -> None:
    write_file(tmp_path, "pyproject.toml", "[project]\n")
    write_file(tmp_path, "notes.txt", "n\n")
    pack = build(tmp_path, [], profile_name=profile_name, cap=EXCERPTS)
    assert pack.workspace is not None
    assert pack.workspace.files_scanned == 2 and pack.workspace.unmatched_files == 1
    assert pack.workspace.dependency_files == ["pyproject.toml"]
    assert pack.tier_bytes["metadata"] == 0
    assert sum(pack.tier_bytes.values()) == pack.used_bytes
    assert pack.tokens.kind == "unknown" and pack.tokens.value is None
    assert [f.signals for f in pack.files] == [["dependency_manifest"]]


def test_empty_workspace_still_has_metadata(tmp_path: Path) -> None:
    pack = build(tmp_path, ["*.py"])
    assert pack.workspace is not None and pack.workspace.files_scanned == 0
    assert pack.files == [] and pack.tier_bytes["metadata"] == 0


def test_git_summary_changed_signal_and_limitations(tmp_path: Path) -> None:
    write_file(tmp_path, "a.txt", "a\n")
    write_file(tmp_path, "b.txt", "b\n")
    summary = GitSummary(available=True, branch="main", head="0" * 40, dirty=True, changed_files=1)
    git = GitState(
        summary=summary, changed=frozenset({"b.txt"}), limitations=("git: something degraded",)
    )
    pack = build(tmp_path, [], git=git)
    assert pack.workspace is not None and pack.workspace.git == summary
    assert [(f.path, f.signals) for f in pack.files] == [("b.txt", ["git:changed"])]
    assert "git: something degraded" in pack.limitations


def test_reference_when_whole_file_fits_uses_fingerprints(tmp_path: Path) -> None:
    write_file(tmp_path, "a.py", "print(1)\n")
    store = FingerprintStore(tmp_path, cache_dir=tmp_path.parent / f"{tmp_path.name}-fp")
    pack = build(tmp_path, ["*.py"], store=store)
    (item,) = pack.files
    assert item.tier == "reference" and item.lines is None
    assert item.sha256 == hashlib.sha256(b"print(1)\n").hexdigest()
    assert store.stats.misses == 1 and store.stats.files_hashed == 1
    assert pack.tier_bytes == {"metadata": 0, "reference": 9}


def test_prefix_excerpt_when_file_does_not_fit(tmp_path: Path) -> None:
    write_file(tmp_path, "big.txt", LINES10)
    pack = build(tmp_path, ["*.txt"], profile=small("balanced", budget=30), cap=EXCERPTS)
    (item,) = pack.files
    assert item.tier == "excerpt" and item.lines == LineRange(start=1, end=3)
    assert item.bytes == 24
    assert item.sha256 == hashlib.sha256(LINES10[:24].encode()).hexdigest()
    assert pack.tier_bytes["excerpt"] == 24 and pack.used_bytes == 24
    assert pack.status == "complete" and not pack.truncated


def test_prefix_needs_at_least_one_line(tmp_path: Path) -> None:
    write_file(tmp_path, "big.txt", LINES10)
    pack = build(tmp_path, ["*.txt"], profile=small("balanced", budget=5), cap=EXCERPTS)
    assert pack.files == [] and pack.truncated
    assert ExcludedFile(path="big.txt", reason="budget", signals=["glob:*.txt"]) in pack.excluded


def test_cited_range_becomes_excerpt_with_range_hash(tmp_path: Path) -> None:
    write_file(tmp_path, "src/m.py", LINES10)
    pack = build(tmp_path, [], cap=EXCERPTS, intent="fix src/m.py:3-4 please")
    (item,) = pack.files
    assert item.tier == "excerpt" and item.lines == LineRange(start=3, end=4)
    assert item.signals == ["intent_lines", "intent_path"]
    assert item.sha256 == hashlib.sha256(LINES10[16:32].encode()).hexdigest()
    assert item.bytes == 16


def test_excerpt_hash_matches_reverification(tmp_path: Path) -> None:
    write_file(tmp_path, "src/m.py", LINES10)
    write_file(tmp_path, "big.txt", LINES10)
    pack = build(
        tmp_path,
        ["*.txt"],
        profile=small("max", budget=40),
        cap=EXCERPTS,
        intent="see src/m.py#L2-L5",
    )
    excerpts = [f for f in pack.files if f.tier == "excerpt"]
    assert {f.path for f in excerpts} == {"src/m.py", "big.txt"}
    for item in excerpts:
        assert item.lines is not None
        assert hash_lines(tmp_path / item.path, item.lines) == (item.sha256, item.bytes)
    assert reverify(tmp_path, pack.files) == frozenset()


def test_capability_without_excerpts_never_gets_excerpt_even_in_max(tmp_path: Path) -> None:
    write_file(tmp_path, "src/m.py", LINES10)
    write_file(tmp_path, "big.txt", "x\n" * 100)
    pack = build(tmp_path, ["*.txt"], profile=small("max", budget=100), intent="fix src/m.py:3-4")
    assert all(f.tier == "reference" for f in pack.files)
    assert [f.path for f in pack.files] == ["src/m.py"]  # cited range -> whole file
    assert ExcludedFile(path="big.txt", reason="budget", signals=["glob:*.txt"]) in pack.excluded
    assert "excerpt" not in pack.tier_bytes


def test_economy_never_gets_excerpt(tmp_path: Path) -> None:
    write_file(tmp_path, "big.txt", "x\n" * 40_000)
    pack = build(tmp_path, ["*.txt"], profile_name="economy", cap=EXCERPTS)
    assert pack.files == [] and pack.truncated


def test_file_limit_applied(tmp_path: Path) -> None:
    for name in ("a.txt", "b.txt", "c.txt"):
        write_file(tmp_path, name, "x")
    pack = build(tmp_path, ["*.txt"], profile=small("balanced", max_files=2))
    assert [f.path for f in pack.files] == ["a.txt", "b.txt"]
    assert ExcludedFile(path="c.txt", reason="max_files", signals=["glob:*.txt"]) in pack.excluded
    assert pack.truncated and pack.status == "truncated"


def test_selection_order_follows_relevance(tmp_path: Path) -> None:
    write_file(tmp_path, "pyproject.toml", "x")
    write_file(tmp_path, "z.py", "x")
    write_file(tmp_path, "cited.md", "x")
    pack = build(tmp_path, ["*.py"], intent="read cited.md")
    assert [f.path for f in pack.files] == ["cited.md", "z.py", "pyproject.toml"]
    assert pack.files[0].reason == "intent_path"


def test_same_selection_in_two_runs(tmp_path: Path) -> None:
    write_file(tmp_path, "src/m.py", LINES10)
    write_file(tmp_path, "big.txt", LINES10)
    for i in range(5):
        write_file(tmp_path, f"d/f{i}.txt", "y\n" * i)
    args: dict[str, Any] = {
        "profile": small("max", budget=60, max_files=4),
        "cap": EXCERPTS,
        "intent": "see src/m.py:2-3 and ghost.py",
    }
    one, two = build(tmp_path, ["*.txt"], **args), build(tmp_path, ["*.txt"], **args)
    d1 = {k: v for k, v in to_dict(one).items() if k != "created_at"}
    d2 = {k: v for k, v in to_dict(two).items() if k != "created_at"}
    assert d1 == d2


def test_no_field_carries_file_content(tmp_path: Path) -> None:
    marker = "UNIQUE_CONTENT_MARKER_42"
    write_file(tmp_path, "src/m.py", f"{marker}\n" * 10)
    write_file(tmp_path, "big.txt", f"{marker}\n" * 50)
    pack = build(
        tmp_path, ["*.txt"], profile=small("max", budget=300), cap=EXCERPTS, intent="src/m.py:1-2"
    )
    assert {f.tier for f in pack.files} == {"excerpt"}
    assert marker not in json.dumps(to_dict(pack))


def test_rejected_intent_citations_recorded_with_reason(tmp_path: Path) -> None:
    write_file(tmp_path, ".env", "A=1")
    pack = build(tmp_path, [], intent="look at ../up.py and .env and ghost.py")
    reasons = {e.path: (e.reason, e.signals) for e in pack.excluded}
    assert reasons["../up.py"] == ("outside_root", ["intent_path"])
    assert reasons["ghost.py"] == ("missing", ["intent_path"])
    assert reasons[".env"] == ("secret", ["intent_path"])
    assert [e.path for e in pack.excluded].count(".env") == 1


def test_secret_shaped_intent_citation_is_redacted(tmp_path: Path) -> None:
    pack = build(tmp_path, [], intent=f"read cfg/{GH_TOKEN}.txt now")
    assert GH_TOKEN not in json.dumps(to_dict(pack))
    assert any(e.reason == "missing" and "[REDACTED]" in e.path for e in pack.excluded)


def test_every_generated_pack_passes_integrity(tmp_path: Path) -> None:
    write_file(tmp_path, "src/m.py", LINES10)
    write_file(tmp_path, "big.txt", LINES10 * 3)
    for i in range(6):
        write_file(tmp_path, f"d/f{i}.txt", "y\n" * (i + 1))
    names: tuple[BudgetProfile, ...] = ("economy", "balanced", "max")
    for name in names:
        for cap in (CapabilityContext(), EXCERPTS):
            for budget in (0, 7, 50, 10_000):
                for max_files in (0, 1, 3, 100):
                    build(
                        tmp_path,
                        ["*.txt"],
                        profile=small(name, budget, max_files),
                        cap=cap,
                        intent="src/m.py:4-9 ghost.py",
                    )


# --- context v2: extension by provider request (task 3.7) ---------------------------------


def request(*items: tuple[str, LineRange | None]) -> ContextRequest:
    return ContextRequest(items=[ContextRequestItem(path=p, lines=r) for p, r in items])


def extend(
    pack: ContextPack, root: Path, req: ContextRequest, profile: ContextProfile
) -> ContextPack:
    out = extend_context_pack(
        pack,
        req,
        scan_workspace(root, ["."]),
        profile=profile,
        fingerprints=FingerprintStore(root, enabled=False),
    )
    validate_context_pack(out)
    return out


def test_extend_adds_requested_items_and_increments_round(tmp_path: Path) -> None:
    write_file(tmp_path, "a.md", "aaaa\n")
    write_file(tmp_path, "src/m.py", LINES10)
    write_file(tmp_path, "src/n.py", "n\n")
    profile = profile_for("balanced")
    pack = build(tmp_path, ["*.md"], profile=profile, cap=EXCERPTS)
    out = extend(
        pack,
        tmp_path,
        request(("src/m.py", LineRange(start=2, end=3)), ("./src/n.py", None)),
        profile,
    )
    assert out.round == pack.round + 1 == 1
    assert out.files[: len(pack.files)] == pack.files
    new = out.files[len(pack.files) :]
    assert [(f.path, f.tier, f.lines, f.signals) for f in new] == [
        ("src/m.py", "requested", LineRange(start=2, end=3), ["requested"]),
        ("src/n.py", "requested", None, ["requested"]),
    ]
    assert new[0].sha256 == hashlib.sha256(LINES10[8:24].encode()).hexdigest()
    assert new[1].sha256 == hashlib.sha256(b"n\n").hexdigest()
    assert out.tier_bytes["requested"] == 16 + 2
    assert out.used_bytes == pack.used_bytes + 18
    assert out.workspace == pack.workspace and out.excluded[: len(pack.excluded)] == pack.excluded
    assert reverify(tmp_path, out.files) == frozenset()


def test_extend_refuses_invalid_items_with_reason(tmp_path: Path) -> None:
    write_file(tmp_path, "a.md", "aaaa\n")
    write_file(tmp_path, ".env", "A=1")
    write_file(tmp_path, "big.py", "x" * 500)
    write_file(tmp_path, "short.py", "one\n")
    profile = small("balanced", budget=100)
    pack = build(tmp_path, ["*.md"], profile=profile, cap=EXCERPTS)
    out = extend(
        pack,
        tmp_path,
        request(
            ("../outside.py", None),
            ("/etc/passwd", None),
            ("C:/x.py", None),
            (".env", None),
            ("ghost.py", None),
            ("big.py", None),
            ("short.py", LineRange(start=5, end=9)),
        ),
        profile,
    )
    assert out.files == pack.files and out.round == 1
    refused = {e.path: e.reason for e in out.excluded if e.signals == ["requested"]}
    assert refused == {
        "../outside.py": "outside_root",
        "/etc/passwd": "outside_root",
        "C:/x.py": "outside_root",
        ".env": "secret",
        "ghost.py": "missing",
        "big.py": "budget",
        "short.py": "missing",
    }
    assert out.truncated and out.status == "truncated"


def test_extend_respects_file_limit(tmp_path: Path) -> None:
    write_file(tmp_path, "a.md", "a\n")
    write_file(tmp_path, "b.py", "b\n")
    profile = small("balanced", max_files=1)
    pack = build(tmp_path, ["*.md"], profile=profile, cap=EXCERPTS)
    out = extend(pack, tmp_path, request(("b.py", None)), profile)
    assert ExcludedFile(path="b.py", reason="max_files", signals=["requested"]) in out.excluded
    assert len(out.files) == 1 and out.truncated


def test_extend_refuses_when_profile_has_no_requested_tier(tmp_path: Path) -> None:
    write_file(tmp_path, "a.md", "a\n")
    write_file(tmp_path, "b.py", "b\n")
    profile = profile_for("economy")
    pack = build(tmp_path, ["*.md"], profile=profile, cap=EXCERPTS)
    out = extend(pack, tmp_path, request(("b.py", None)), profile)
    assert (
        ExcludedFile(path="b.py", reason="tier_not_allowed", signals=["requested"]) in out.excluded
    )
    assert out.files == pack.files


def test_extend_redacts_secret_shaped_requested_path(tmp_path: Path) -> None:
    write_file(tmp_path, "a.md", "a\n")
    profile = profile_for("max")
    pack = build(tmp_path, ["*.md"], profile=profile, cap=EXCERPTS)
    out = extend(pack, tmp_path, request((f"x/{GH_TOKEN}.py", None)), profile)
    assert GH_TOKEN not in json.dumps(to_dict(out))


def test_extend_twice_preserves_previous_rounds(tmp_path: Path) -> None:
    write_file(tmp_path, "a.md", "a\n")
    write_file(tmp_path, "b.py", "b\n")
    write_file(tmp_path, "c.py", "c\n")
    profile = profile_for("max")
    r1 = extend(
        build(tmp_path, ["*.md"], profile=profile, cap=EXCERPTS),
        tmp_path,
        request(("b.py", None)),
        profile,
    )
    r2 = extend(r1, tmp_path, request(("c.py", None), ("b.py", None)), profile)
    assert r2.round == 2 and r2.files[: len(r1.files)] == r1.files
    assert [f.path for f in r2.files] == ["a.md", "b.py", "c.py"]  # duplicate not re-added
