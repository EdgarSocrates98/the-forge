"""WorkspaceDescriber and WorkspaceRelations (requirements 7.1-7.6)."""

import json
import os
import shutil
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from cross_workspace import CrossWorkspace, mount_cross_workspace, remove_cross_workspace
from helpers import API_ENTRY, PROVIDERS, SPARK_ENTRY
from theforge.context import git as gitmod
from theforge.context import scan_workspace
from theforge.context.git import GitState, read_git_state
from theforge.contracts import ForgeManifest, from_dict, to_dict
from theforge.contracts.codes import Codes
from theforge.contracts.context import GitSummary
from theforge.contracts.workspace import WORKSPACE_GIT_BUDGET_S, WorkspaceDescriptor
from theforge.registry import ProviderEntry, RegistryRecord
from theforge.workspace import describe, describe_workspace, load_relations, repository_of
from theforge.workspace.relations import MAX_WORKSPACE_CONFIG_BYTES

GIT = shutil.which("git")
requires_git = pytest.mark.skipif(GIT is None, reason="git executable not found on PATH")
BUDGET_NOTE = "git: skipped: workspace git budget exhausted (20 s)"


def _record(name: str, entry: dict[str, Any]) -> RegistryRecord:
    data = json.loads((PROVIDERS / name).read_text(encoding="utf-8"))
    return RegistryRecord(entry=ProviderEntry(id=entry["id"], argv=["x"], trust="local"),
                          state="ready", manifest=from_dict(ForgeManifest, data),
                          manifest_sha256="0" * 64, protocol="forge/v1")


RECORDS = [_record("fixture-spark.json", SPARK_ENTRY), _record("fixture-api.json", API_ENTRY)]


def _unavailable(_: Path) -> GitState:
    return GitState(summary=GitSummary(available=False), changed=frozenset(),
                    limitations=("git: not available",))


def _describe(root: Path, records: list[RegistryRecord] | None = None,
              **kw: Any) -> WorkspaceDescriptor:
    kw.setdefault("git_reader", _unavailable)
    return describe_workspace(root, RECORDS if records is None else records,
                              scan_workspace(root, []), **kw)


def _fake_repo(path: Path) -> Path:
    (path / ".git").mkdir(parents=True)
    return path


def _git(repo: Path, *args: str) -> str:
    assert GIT is not None
    out = subprocess.run(
        [GIT, "-c", "core.fsmonitor=false", "-c", "user.name=t", "-c", "user.email=t@t",
         "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main", *args],
        cwd=repo, capture_output=True, check=True, env={**os.environ, "LC_ALL": "C"})
    return out.stdout.decode("utf-8", "replace")


def _snapshot(d: Path) -> dict[str, tuple[bool, int, bytes]]:
    snap: dict[str, tuple[bool, int, bytes]] = {".": (True, d.lstat().st_mtime_ns, b"")}
    for p in sorted(d.rglob("*")):
        st = p.lstat()
        is_dir = p.is_dir()
        snap[p.relative_to(d).as_posix()] = (
            is_dir, st.st_mtime_ns, b"" if is_dir else p.read_bytes())
    return snap


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated global git config (HOME/USERPROFILE survive safe_env)."""
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setenv("HOME", str(h))
    monkeypatch.setenv("USERPROFILE", str(h))
    return h


@pytest.fixture
def cross(home: Path) -> Iterator[CrossWorkspace]:
    if GIT is None:
        pytest.skip("git executable not found on PATH")
    workspace = mount_cross_workspace(git=True)
    try:
        yield workspace
    finally:
        remove_cross_workspace(workspace)


# --- real repositories ----------------------------------------------------------------------

@requires_git
def test_cross_workspace_two_independent_repositories(cross: CrossWorkspace) -> None:
    root = cross.root
    before = {r.name: _snapshot(r / ".git") for r in cross.repositories}
    time.sleep(0.05)
    descriptor = describe_workspace(root, RECORDS, scan_workspace(root, []))
    assert [r.path for r in descriptor.repositories] == ["data-pipeline", "orders-api"]
    assert descriptor.root == str(root.resolve())
    for info in descriptor.repositories:
        expected = read_git_state(root / info.path)
        assert info.git == expected.summary  # embedded as returned by the Wave C query
        assert info.limitations == list(expected.limitations)
        assert info.git is not None and info.git.available and info.git.head
        assert info.git.branch == "main" and not info.git.detached
        assert info.git.dirty is False and info.git.changed_files == 0
    assert {r.name: _snapshot(r / ".git") for r in cross.repositories} == before
    assert [(r.source, r.target, r.kind, r.epistemic, r.evidence)
            for r in descriptor.relations] == [
        (".", "data-pipeline", "contains", "observed", "data-pipeline/.git"),
        (".", "orders-api", "contains", "observed", "orders-api/.git"),
    ]
    assert descriptor.unknowns == [] and descriptor.limitations == []
    # The descriptor is a strict-round-trip contract.
    assert from_dict(WorkspaceDescriptor, to_dict(descriptor), strict=True) == descriptor


@requires_git
def test_cross_workspace_technologies_with_evidence(cross: CrossWorkspace) -> None:
    descriptor = describe_workspace(cross.root, RECORDS, scan_workspace(cross.root, []))
    techs = [(t.repository, t.name, t.source, t.evidence, t.matched_by)
             for t in descriptor.technologies]
    assert techs == [
        ("data-pipeline", "data-engineering", "provider_signal",
         "data-pipeline/jobs/daily_orders_job.py", ["fixture-spark/spark.performance"]),
        ("data-pipeline", "pyspark", "dependency_manifest", "data-pipeline/requirements.txt",
         ["fixture-spark/spark.performance"]),
        ("orders-api", "api-engineering", "provider_signal", "orders-api/openapi.yaml",
         ["fixture-api/api.contract"]),
        ("orders-api", "fastapi", "dependency_manifest", "orders-api/requirements.txt",
         ["fixture-api/api.contract"]),
    ]
    assert [r.dependency_files for r in descriptor.repositories] == [
        ["data-pipeline/requirements.txt"], ["orders-api/requirements.txt"]]
    assert descriptor.paths == ["data-pipeline", "data-pipeline/requirements.txt",
                                "orders-api", "orders-api/requirements.txt"]


@requires_git
def test_nested_repository_is_independent_and_contained(cross: CrossWorkspace) -> None:
    nested = cross.root / "orders-api" / "vendor" / "lib"
    nested.mkdir(parents=True)
    (nested / "x.txt").write_text("x\n", encoding="utf-8")
    _git(nested, "init", "-q")
    _git(nested, "add", "x.txt")
    _git(nested, "commit", "-qm", "nested")
    descriptor = describe_workspace(cross.root, RECORDS, scan_workspace(cross.root, []))
    paths = [r.path for r in descriptor.repositories]
    assert paths == ["data-pipeline", "orders-api", "orders-api/vendor/lib"]
    info = descriptor.repositories[2]
    assert info.git == read_git_state(nested).summary
    assert ("orders-api", "orders-api/vendor/lib", "orders-api/vendor/lib/.git") in [
        (r.source, r.target, r.evidence) for r in descriptor.relations]
    assert repository_of(descriptor, "orders-api/vendor/lib/x.txt") == "orders-api/vendor/lib"
    assert repository_of(descriptor, "orders-api/app/main.py") == "orders-api"
    assert repository_of(descriptor, "README.md") is None


@requires_git
def test_detached_head_and_changed_count_match_wave_c(cross: CrossWorkspace) -> None:
    repo = cross.root / "data-pipeline"
    _git(repo, "checkout", "-q", "--detach")
    (repo / "requirements.txt").write_text("pyspark\nboto3\n", encoding="utf-8")
    (repo / "new.txt").write_text("n\n", encoding="utf-8")
    before = _snapshot(repo / ".git")
    time.sleep(0.05)
    descriptor = describe_workspace(cross.root, RECORDS, scan_workspace(cross.root, []))
    info = descriptor.repositories[0]
    assert info.git == read_git_state(repo).summary
    assert info.git is not None and info.git.detached and info.git.branch is None
    assert info.git.dirty is True and info.git.changed_files == 2
    assert _snapshot(repo / ".git") == before


def test_git_unavailable_is_unknown_with_limitation(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_repo(tmp_path / "a")
    monkeypatch.setattr(gitmod.shutil, "which", lambda _name: None)
    descriptor = describe_workspace(tmp_path, RECORDS, scan_workspace(tmp_path, []))
    info = descriptor.repositories[0]
    assert info.git == GitSummary(available=False)
    assert info.git.head is None and info.git.dirty is None
    assert info.limitations == ["git: not available"]
    assert descriptor.unknowns == ["a: git head/dirty state unknown"]


def test_failing_injected_reader_becomes_limitation(tmp_path: Path) -> None:
    _fake_repo(tmp_path / "a")

    def boom(_: Path) -> GitState:
        raise RuntimeError("x")

    info = _describe(tmp_path, git_reader=boom).repositories[0]
    assert info.git == GitSummary(available=False)
    assert info.limitations == ["git: failed (RuntimeError)"]


# --- git budget -----------------------------------------------------------------------------

def test_git_budget_exhausted_with_fake_clock(tmp_path: Path) -> None:
    for name in ("r1", "r2", "r3", "r4", "r5", "r6"):
        _fake_repo(tmp_path / name)
    now = [0.0]
    queried: list[str] = []

    def slow(path: Path) -> GitState:
        queried.append(path.name)
        now[0] += 4.9  # just under the Wave C per-query budget
        return GitState(summary=GitSummary(available=True, branch="main", dirty=False),
                        changed=frozenset(), limitations=())

    descriptor = _describe(tmp_path, git_reader=slow, clock=lambda: now[0])
    assert queried == ["r1", "r2", "r3", "r4"]
    assert now[0] <= WORKSPACE_GIT_BUDGET_S
    infos = descriptor.repositories
    assert all(i.git is not None and i.limitations == [] for i in infos[:4])
    assert all(i.git is None and i.limitations == [BUDGET_NOTE] for i in infos[4:])
    assert descriptor.unknowns == ["r5: git head/dirty state unknown",
                                   "r6: git head/dirty state unknown"]


def test_fast_git_queries_every_repository(tmp_path: Path) -> None:
    for name in ("r1", "r2", "r3", "r4", "r5", "r6", "r7"):
        _fake_repo(tmp_path / name)
    now = [0.0]

    def fast(_: Path) -> GitState:
        now[0] += 0.5
        return GitState(summary=GitSummary(available=True), changed=frozenset(),
                        limitations=())

    descriptor = _describe(tmp_path, git_reader=fast, clock=lambda: now[0])
    assert all(i.git is not None for i in descriptor.repositories)


def test_tiny_budget_skips_everything(tmp_path: Path) -> None:
    _fake_repo(tmp_path / "a")
    calls: list[Path] = []
    info = _describe(tmp_path, git_reader=lambda p: calls.append(p) or _unavailable(p),
                     git_budget_s=4.0).repositories[0]
    assert calls == [] and info.git is None
    assert info.limitations == ["git: skipped: workspace git budget exhausted (4 s)"]


# --- discovery ------------------------------------------------------------------------------

def test_root_repository_depth_limit_and_ignored_dirs(tmp_path: Path) -> None:
    _fake_repo(tmp_path)
    _fake_repo(tmp_path / "a" / "b" / "c")  # depth 3: found
    _fake_repo(tmp_path / "a" / "b" / "c" / "d")  # depth 4: ignored
    _fake_repo(tmp_path / "x" / "y" / "z" / "w")  # depth 4: ignored
    _fake_repo(tmp_path / "node_modules" / "pkg")
    _fake_repo(tmp_path / ".forge" / "inner")
    (tmp_path / "plain").mkdir()
    descriptor = _describe(tmp_path)
    assert [r.path for r in descriptor.repositories] == [".", "a/b/c"]
    assert [(r.source, r.target) for r in descriptor.relations] == [(".", "a/b/c")]


def test_git_file_marks_a_repository(tmp_path: Path) -> None:
    (tmp_path / "wt").mkdir()
    (tmp_path / "wt" / ".git").write_text("gitdir: elsewhere\n", encoding="utf-8")
    assert [r.path for r in _describe(tmp_path).repositories] == ["wt"]


def test_symlinked_directory_is_not_followed(tmp_path: Path) -> None:
    outside = _fake_repo(tmp_path / "outside" / "repo")
    root = tmp_path / "root"
    _fake_repo(root / "real")
    try:
        os.symlink(outside, root / "link", target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"cannot create a directory symlink here: {exc}")
    assert [r.path for r in _describe(root).repositories] == ["real"]


def test_repositories_truncated_at_limit(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("a", "b", "c"):
        _fake_repo(tmp_path / name)
    monkeypatch.setattr(describe, "MAX_REPOSITORIES", 2)
    descriptor = _describe(tmp_path)
    assert [r.path for r in descriptor.repositories] == ["a", "b"]
    assert descriptor.limitations == ["workspace: repositories truncated at 2"]


def test_path_order_is_by_components(tmp_path: Path) -> None:
    _fake_repo(tmp_path / "a" / "x")
    _fake_repo(tmp_path / "a-b")
    _fake_repo(tmp_path / "a")
    assert [r.path for r in _describe(tmp_path).repositories] == ["a", "a/x", "a-b"]


def test_root_not_a_repository_and_no_repositories(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("x", encoding="utf-8")
    descriptor = _describe(tmp_path)
    assert descriptor.repositories == [] and descriptor.relations == []
    assert descriptor.technologies == [] and descriptor.paths == []


# --- technologies ---------------------------------------------------------------------------

def test_technologies_only_from_provider_declarations(tmp_path: Path) -> None:
    repo = _fake_repo(tmp_path / "svc")
    (repo / "requirements.txt").write_text("PySpark==3.5\nrequests\n", encoding="utf-8")
    (repo / "pyproject.toml").write_text(
        '[project]\ndependencies = ["pyspark", "awsglue"]\n', encoding="utf-8")
    (repo / "readme.md").write_text("fastapi is mentioned here\n", encoding="utf-8")
    descriptor = _describe(tmp_path)
    techs = [(t.name, t.source, t.evidence) for t in descriptor.technologies]
    # requests is not declared by any provider; README content is never a signal.
    assert techs == [("awsglue", "dependency_manifest", "svc/pyproject.toml"),
                     ("pyspark", "dependency_manifest", "svc/pyproject.toml")]
    assert descriptor.repositories[0].dependency_files == [
        "svc/pyproject.toml", "svc/requirements.txt"]
    assert _describe(tmp_path, records=[]).technologies == []


def test_files_belong_to_their_deepest_repository(tmp_path: Path) -> None:
    _fake_repo(tmp_path)
    inner = _fake_repo(tmp_path / "inner")
    (inner / "openapi.yaml").write_text("openapi: 3.0.0\n", encoding="utf-8")
    techs = [(t.repository, t.name) for t in _describe(tmp_path).technologies]
    assert techs == [("inner", "api-engineering")]


# --- explicit relations ---------------------------------------------------------------------

def _workspace_toml(root: Path, text: str) -> None:
    config = root / ".forge" / "config"
    config.mkdir(parents=True, exist_ok=True)
    (config / "workspace.toml").write_text(text, encoding="utf-8")


def test_explicit_relations_valid_and_invalid(tmp_path: Path) -> None:
    for name in ("orders-api", "data-pipeline"):
        _fake_repo(tmp_path / name)
    _workspace_toml(tmp_path, """
[[relations]]
source = "orders-api"
target = "data-pipeline"
kind = "depends_on"

[[relations]]
source = "orders-api"
target = "data-pipeline"
kind = "depends_on"

[[relations]]
source = "orders-api"
target = "ghost"
kind = "depends_on"

[[relations]]
source = "orders-api"
target = "data-pipeline"
kind = "contains"

[[relations]]
source = "orders-api"
target = "orders-api"
kind = "depends_on"

[[relations]]
source = "orders-api"
target = "data-pipeline"
kind = "depends_on"
weight = 3

[[relations]]
source = 1
target = "data-pipeline"
kind = "depends_on"
""")
    descriptor = _describe(tmp_path)
    explicit = [r for r in descriptor.relations if r.epistemic == "explicit"]
    assert [(r.source, r.kind, r.target, r.evidence) for r in explicit] == [
        ("orders-api", "depends_on", "data-pipeline", ".forge/config/workspace.toml")]
    warnings = descriptor.limitations
    assert len(warnings) == 5
    assert all(w.startswith(f"{Codes.WORKSPACE_CONFIG}: .forge/config/workspace.toml: ")
               for w in warnings)
    assert "relations[2] ignored: target 'ghost' is not a repository" in warnings[0]
    assert "relations[3] ignored: kind 'contains'" in warnings[1]
    assert "relations[4] ignored: source and target are the same" in warnings[2]
    assert "relations[5] ignored: unknown keys ['weight']" in warnings[3]
    assert "relations[6] ignored: 'source' must be a non-empty string" in warnings[4]


def test_malformed_workspace_toml_ignores_everything(tmp_path: Path) -> None:
    _fake_repo(tmp_path / "a")
    _workspace_toml(tmp_path, "[[relations]\nsource = \n")
    descriptor = _describe(tmp_path)
    assert [r.kind for r in descriptor.relations] == ["contains"]
    assert len(descriptor.limitations) == 1
    assert "malformed (TOMLDecodeError), all relations ignored" in descriptor.limitations[0]


def test_load_relations_edge_cases(tmp_path: Path) -> None:
    forge = tmp_path / ".forge"
    assert load_relations(None, ["a"]) == ([], [])
    assert load_relations(forge, ["a"]) == ([], [])  # optional file
    _workspace_toml(tmp_path, 'relations = "x"\nother = 1\n')
    relations, warnings = load_relations(forge, ["a"])
    assert relations == [] and len(warnings) == 2
    assert "unknown key 'other' ignored" in warnings[0]
    assert "'relations' must be an array of tables" in warnings[1]
    _workspace_toml(tmp_path, "#" * (MAX_WORKSPACE_CONFIG_BYTES + 1))
    relations, warnings = load_relations(forge, ["a"])
    assert relations == [] and "all relations ignored" in warnings[0]
    _workspace_toml(tmp_path, 'relations = ["not a table"]\n')
    relations, warnings = load_relations(forge, ["a"])
    assert relations == [] and "relations[0] ignored: not a table" in warnings[0]
