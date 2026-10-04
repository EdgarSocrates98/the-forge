"""GitReader: read-only, hardened git query (requirements 2.6, 3.1-3.5)."""

import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path

import pytest

from theforge.context import git as gitmod
from theforge.context.git import (
    EXECUTABLE_CONFIG_KEYS,
    GitRun,
    git_env,
    read_git_state,
    run_git,
)

GIT = shutil.which("git")
requires_git = pytest.mark.skipif(GIT is None, reason="git executable not found on PATH")


# --- helpers -------------------------------------------------------------------------------

@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated global git config (HOME/USERPROFILE survive safe_env)."""
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setenv("HOME", str(h))
    monkeypatch.setenv("USERPROFILE", str(h))
    return h


def _git(repo: Path, *args: str) -> str:
    assert GIT is not None
    out = subprocess.run(
        [GIT, "-c", "core.fsmonitor=false", "-c", "user.name=t", "-c", "user.email=t@t",
         "-c", "commit.gpgsign=false", *args],
        cwd=repo, capture_output=True, check=True, env={**os.environ, "LC_ALL": "C"},
    )
    return out.stdout.decode("utf-8", "replace")


def _init(repo: Path, *, commit: bool = True) -> Path:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q", "-b", "main", ".")
    if commit:
        (repo / "a.txt").write_text("a\n", encoding="utf-8")
        (repo / "b.txt").write_text("b\n", encoding="utf-8")
        _git(repo, "add", "a.txt", "b.txt")
        _git(repo, "commit", "-qm", "init")
    return repo


def _snapshot(d: Path) -> dict[str, tuple[bool, int, bytes]]:
    snap: dict[str, tuple[bool, int, bytes]] = {".": (True, d.lstat().st_mtime_ns, b"")}
    for p in sorted(d.rglob("*")):
        st = p.lstat()
        is_dir = p.is_dir()
        snap[p.relative_to(d).as_posix()] = (
            is_dir, st.st_mtime_ns, b"" if is_dir else p.read_bytes())
    return snap


def _dirty_worktree(repo: Path) -> None:
    (repo / "a.txt").write_text("changed\n", encoding="utf-8")
    # Same content, newer mtime: a plain `git status` would refresh and rewrite the index.
    past = time.time() + 5
    os.utime(repo / "b.txt", (past, past))
    (repo / "new dir").mkdir()
    (repo / "new dir" / "n.txt").write_text("n\n", encoding="utf-8")


class FakeRunner:
    def __init__(self, results: dict[str, GitRun]) -> None:
        self.results = results
        self.calls: list[list[str]] = []

    def __call__(self, argv: Sequence[str], cwd: Path, timeout: float) -> GitRun:
        self.calls.append(list(argv))
        key = " ".join(argv[3:])
        for prefix, result in self.results.items():
            if key.startswith(prefix):
                return result
        return GitRun(returncode=0, stdout=b"", stderr_tail="", timed_out=False)


def _ok(out: bytes) -> GitRun:
    return GitRun(returncode=0, stdout=out, stderr_tail="", timed_out=False)


def _fail(stderr: str, code: int = 128) -> GitRun:
    return GitRun(returncode=code, stdout=b"", stderr_tail=stderr, timed_out=False)


# --- real repositories: read-only invariants -----------------------------------------------

@requires_git
def test_reads_branch_head_and_changed_files(tmp_path: Path, home: Path) -> None:
    repo = _init(tmp_path / "repo")
    head = _git(repo, "rev-parse", "HEAD").strip()
    _dirty_worktree(repo)
    state = read_git_state(repo)
    assert state.limitations == ()
    s = state.summary
    assert s.available and s.branch == "main" and s.head == head and not s.detached
    assert s.state == []
    assert state.changed == frozenset({"a.txt", "new dir/n.txt"})
    assert s.dirty is True and s.changed_files == 2


@requires_git
def test_git_dir_is_byte_and_mtime_identical_after_query(tmp_path: Path, home: Path) -> None:
    repo = _init(tmp_path / "repo")
    _dirty_worktree(repo)
    time.sleep(0.05)
    before = _snapshot(repo / ".git")
    state = read_git_state(repo)
    assert state.summary.available
    assert not (repo / ".git" / "index.lock").exists()
    assert _snapshot(repo / ".git") == before


@requires_git
def test_control_plain_status_would_have_written(tmp_path: Path, home: Path) -> None:
    """Proves the invariant above is sensitive: an unhardened status rewrites the index."""
    repo = _init(tmp_path / "repo")
    _dirty_worktree(repo)
    before = _snapshot(repo / ".git")
    _git(repo, "status", "--porcelain")
    assert _snapshot(repo / ".git") != before


@requires_git
def test_global_fsmonitor_hook_is_never_run(tmp_path: Path, home: Path) -> None:
    repo = _init(tmp_path / "repo")
    marker = tmp_path / "marker"
    hook = tmp_path / "fsmon.sh"
    hook.write_text(f'#!/bin/sh\necho hit > "{marker.as_posix()}"\nprintf "\\0"\n',
                    encoding="utf-8", newline="\n")
    hook.chmod(0o755)
    (home / ".gitconfig").write_text(f"[core]\n\tfsmonitor = {hook.as_posix()}\n",
                                     encoding="utf-8")
    _dirty_worktree(repo)
    state = read_git_state(repo)
    assert state.summary.dirty is True  # status ran (global scope is not refused)
    assert not marker.exists()


@requires_git
def test_partial_clone_lazy_fetch_never_runs_repo_transport(tmp_path: Path, home: Path) -> None:
    """A missing object in a promisor repo must not make status run the remote's command."""
    repo = _init(tmp_path / "repo")
    tree = _git(repo, "rev-parse", "HEAD^{tree}").strip()
    loose = repo / ".git" / "objects" / tree[:2] / tree[2:]
    loose.chmod(0o644)  # loose objects are read-only (Windows refuses to unlink them)
    loose.unlink()
    marker = tmp_path / "pwned"
    for key, value in (("core.repositoryformatversion", "1"),
                       ("extensions.partialClone", "origin"),
                       ("remote.origin.promisor", "true"),
                       ("remote.origin.url", f"ext::sh -c touch% {marker.as_posix()}"),
                       ("protocol.ext.allow", "always")):
        _git(repo, "config", "--local", key, value)
    before = _snapshot(repo / ".git")
    state = read_git_state(repo)
    assert state.summary.available
    assert not marker.exists()
    assert _snapshot(repo / ".git") == before


@requires_git
@pytest.mark.parametrize("key", ["core.fsmonitor", "filter.evil.clean", "filter.evil.smudge",
                                 "filter.evil.process"])
def test_local_executable_config_skips_status(tmp_path: Path, home: Path, key: str) -> None:
    repo = _init(tmp_path / "repo")
    marker = tmp_path / "marker"
    hook = tmp_path / "hook.sh"
    hook.write_text(f'#!/bin/sh\necho hit > "{marker.as_posix()}"\ncat\n',
                    encoding="utf-8", newline="\n")
    hook.chmod(0o755)
    _git(repo, "config", "--local", key, hook.as_posix())
    (repo / ".gitattributes").write_text("* filter=evil\n", encoding="utf-8")
    _dirty_worktree(repo)
    before = _snapshot(repo / ".git")
    state = read_git_state(repo)
    assert f"git: status skipped: repository config defines {key}" in state.limitations
    assert state.summary.available and state.summary.branch == "main"
    assert state.summary.dirty is None and state.summary.changed_files is None
    assert state.changed == frozenset()
    assert not marker.exists()
    assert _snapshot(repo / ".git") == before


@requires_git
def test_no_commits_state(tmp_path: Path, home: Path) -> None:
    repo = _init(tmp_path / "repo", commit=False)
    (repo / "x.py").write_text("x\n", encoding="utf-8")
    before = _snapshot(repo / ".git")
    state = read_git_state(repo)
    s = state.summary
    assert s.available and s.branch == "main" and s.head is None and not s.detached
    assert s.state == ["no_commits"]
    assert state.changed == frozenset({"x.py"})
    assert _snapshot(repo / ".git") == before


@requires_git
def test_detached_head(tmp_path: Path, home: Path) -> None:
    repo = _init(tmp_path / "repo")
    head = _git(repo, "rev-parse", "HEAD").strip()
    _git(repo, "checkout", "-q", "--detach")
    s = read_git_state(repo).summary
    assert s.detached and s.branch is None and s.head == head


@requires_git
@pytest.mark.parametrize(("marker", "expected"), [
    ("MERGE_HEAD", "merge"), ("rebase-merge", "rebase"), ("rebase-apply", "rebase"),
    ("CHERRY_PICK_HEAD", "cherry_pick"), ("BISECT_LOG", "bisect"),
])
def test_unusual_states_are_reported(tmp_path: Path, home: Path, marker: str,
                                     expected: str) -> None:
    repo = _init(tmp_path / "repo")
    head = _git(repo, "rev-parse", "HEAD").strip()
    target = repo / ".git" / marker
    if marker.startswith("rebase"):
        target.mkdir()
    else:
        target.write_text(head + "\n", encoding="utf-8")
    state = read_git_state(repo)
    assert expected in state.summary.state
    assert state.summary.available


@requires_git
def test_real_merge_conflict_state(tmp_path: Path, home: Path) -> None:
    repo = _init(tmp_path / "repo")
    _git(repo, "checkout", "-q", "-b", "other")
    (repo / "a.txt").write_text("other\n", encoding="utf-8")
    _git(repo, "commit", "-qam", "other")
    _git(repo, "checkout", "-q", "main")
    (repo / "a.txt").write_text("main\n", encoding="utf-8")
    _git(repo, "commit", "-qam", "main")
    with pytest.raises(subprocess.CalledProcessError):
        _git(repo, "merge", "-q", "other")
    state = read_git_state(repo)
    assert "merge" in state.summary.state
    assert "a.txt" in state.changed


@requires_git
def test_paths_relative_to_workspace_root_subdir(tmp_path: Path, home: Path) -> None:
    repo = _init(tmp_path / "repo")
    (repo / "pkg").mkdir()
    (repo / "pkg" / "m.py").write_text("m\n", encoding="utf-8")
    (repo / "a.txt").write_text("changed\n", encoding="utf-8")
    state = read_git_state(repo / "pkg")
    assert state.changed == frozenset({"m.py"})  # a.txt is outside the workspace root
    assert state.summary.changed_files == 1


@requires_git
def test_submodules_and_nested_repos_ignored(tmp_path: Path, home: Path) -> None:
    repo = _init(tmp_path / "repo")
    _init(repo / "nested")  # nested repository (untracked) appears as a directory entry
    state = read_git_state(repo)
    assert all(not p.startswith("nested") for p in state.changed)


@requires_git
def test_not_a_repository(home: Path) -> None:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        probe = subprocess.run([str(GIT), "rev-parse", "--git-dir"], cwd=root,
                               capture_output=True, check=False)
        if probe.returncode == 0:
            pytest.skip("system temp directory is inside a git repository")
        state = read_git_state(root)
    assert state.limitations == ("git: not a repository",)
    assert state.summary.available is False and state.changed == frozenset()


@requires_git
def test_zero_budget_times_out_without_exception(tmp_path: Path, home: Path) -> None:
    repo = _init(tmp_path / "repo")
    state = read_git_state(repo, timeout_s=0.0)
    assert any(lim.startswith("git: timed out") for lim in state.limitations)


# --- absence and failure scenarios (no exception, limitation recorded) ----------------------

def test_git_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gitmod.shutil, "which", lambda name: None)
    state = read_git_state(tmp_path)
    assert state.limitations == ("git: not available",)
    assert state.summary.available is False


def test_git_executable_unspawnable(tmp_path: Path) -> None:
    state = read_git_state(tmp_path, executable=str(tmp_path / "no-such-git.exe"))
    assert state.limitations == ("git: not available",)
    assert state.summary.available is False


@pytest.mark.parametrize(("stderr", "expected"), [
    ("fatal: not a git repository (or any of the parent directories): .git",
     "git: not a repository"),
    ("fatal: detected dubious ownership in repository at '/x'\nTo add an exception ...",
     "git: repository not trusted by git (safe.directory)"),
    ("fatal: this operation must be run in a work tree", "git: not a work tree"),
    ("fatal: something odd", "git: rev-parse failed (exit 128)"),
])
def test_rev_parse_failures_become_limitations(tmp_path: Path, stderr: str,
                                               expected: str) -> None:
    runner = FakeRunner({"rev-parse --show-toplevel": _fail(stderr)})
    state = read_git_state(tmp_path, executable="git", runner=runner)
    assert state.limitations == (expected,)
    assert state.summary.available is False
    assert len(runner.calls) == 1


def test_timeout_becomes_limitation(tmp_path: Path) -> None:
    runner = FakeRunner({"rev-parse --show-toplevel": GitRun(
        returncode=-1, stdout=b"", stderr_tail="", timed_out=True)})
    state = read_git_state(tmp_path, executable="git", runner=runner, timeout_s=1.5)
    assert state.limitations == ("git: timed out after 1.5s",)


def test_runner_exception_becomes_limitation(tmp_path: Path) -> None:
    def boom(argv: Sequence[str], cwd: Path, timeout: float) -> GitRun:
        raise RuntimeError("boom")
    state = read_git_state(tmp_path, executable="git", runner=boom)
    assert state.summary.available is False
    assert state.limitations and state.limitations[0].startswith("git: failed")


def _repo_runner(tmp_path: Path, **overrides: GitRun) -> FakeRunner:
    top = tmp_path.as_posix().encode()
    results = {
        "rev-parse --show-toplevel": _ok(top + b"\n" + top + b"/.git\n"),
        "symbolic-ref": _ok(b"main\n"),
        "rev-parse --verify": _ok(b"a" * 40 + b"\n"),
        "config": _ok(b"local\x00core.bare\nfalse\x00"),
        "status": _ok(b" M a.txt\x00?? b.txt\x00"),
    }
    for key, value in overrides.items():
        results[key.replace("_", " ")] = value
    return FakeRunner(results)


def test_old_git_without_show_scope_refuses_status(tmp_path: Path) -> None:
    runner = _repo_runner(tmp_path, config=_fail(
        "error: unknown option `show-scope'\nusage: git config", code=129))
    state = read_git_state(tmp_path, executable="git", runner=runner)
    assert state.limitations == ("git: version too old for safe status",)
    assert not any(call[3] == "status" for call in runner.calls)
    assert state.summary.dirty is None


def test_worktree_scope_key_refuses_status(tmp_path: Path) -> None:
    runner = _repo_runner(tmp_path, config=_ok(
        b"global\x00core.fsmonitor\n/g\x00worktree\x00filter.x.clean\nrun\x00"))
    state = read_git_state(tmp_path, executable="git", runner=runner)
    assert state.limitations == ("git: status skipped: repository config defines "
                                 "filter.x.clean",)


def test_status_failure_and_timeout(tmp_path: Path) -> None:
    runner = _repo_runner(tmp_path, status=_fail("fatal: index corrupt"))
    state = read_git_state(tmp_path, executable="git", runner=runner)
    assert state.limitations == ("git: status failed (exit 128)",)
    assert state.summary.available and state.summary.dirty is None
    runner = _repo_runner(tmp_path, status=GitRun(
        returncode=-1, stdout=b"", stderr_tail="", timed_out=True))
    state = read_git_state(tmp_path, executable="git", runner=runner, timeout_s=5.0)
    assert state.limitations == ("git: timed out after 5s",)


def test_truncated_status_keeps_complete_entries(tmp_path: Path) -> None:
    runner = _repo_runner(tmp_path, status=GitRun(
        returncode=-1, stdout=b" M a.txt\x00?? b.t", stderr_tail="", timed_out=False,
        truncated=True))
    state = read_git_state(tmp_path, executable="git", runner=runner)
    assert state.changed == frozenset({"a.txt"})
    assert any("truncated" in lim for lim in state.limitations)


def test_changed_paths_capped_at_max_files(tmp_path: Path,
                                           monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gitmod, "MAX_FILES", 2)
    runner = _repo_runner(tmp_path, status=_ok(b"?? a\x00?? b\x00?? c\x00"))
    state = read_git_state(tmp_path, executable="git", runner=runner)
    assert len(state.changed) == 2
    assert any("truncated" in lim for lim in state.limitations)


def test_every_call_is_hardened(tmp_path: Path) -> None:
    runner = _repo_runner(tmp_path)
    state = read_git_state(tmp_path, executable="git", runner=runner)
    assert state.changed == frozenset({"a.txt", "b.txt"})
    assert [c[3] for c in runner.calls] == [
        "rev-parse", "symbolic-ref", "rev-parse", "config", "status"]
    for argv in runner.calls:
        assert argv[:3] == ["git", "-c", "core.fsmonitor=false"]
        assert not any("safe.directory" in a for a in argv)
    status = runner.calls[-1]
    assert "--ignore-submodules=all" in status and "--porcelain=v1" in status
    assert "-z" in status and "--no-renames" in status


def test_git_env_is_minimal_and_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_secret")
    monkeypatch.setenv("GIT_DIR", "/elsewhere")
    monkeypatch.setenv("GIT_CONFIG_PARAMETERS", "'core.fsmonitor'='/x'")
    env = git_env()
    assert env["GIT_OPTIONAL_LOCKS"] == "0"
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert env["GIT_PAGER"] == "cat" and env["LC_ALL"] == "C"
    assert env["GIT_NO_LAZY_FETCH"] == "1" and env["GIT_ALLOW_PROTOCOL"] == "none"
    assert "GITHUB_TOKEN" not in env and "GIT_DIR" not in env
    assert "GIT_CONFIG_PARAMETERS" not in env


def test_executable_config_keys_are_the_documented_set() -> None:
    assert EXECUTABLE_CONFIG_KEYS == ("core.fsmonitor", "filter.*.clean", "filter.*.smudge",
                                      "filter.*.process")


# --- default runner: process-tree kill on timeout ------------------------------------------

def test_run_git_kills_on_timeout(tmp_path: Path) -> None:
    start = time.monotonic()
    run = run_git([sys.executable, "-c", "import time; time.sleep(30)"], tmp_path, 0.5)
    assert run.timed_out
    assert time.monotonic() - start < 15


def test_run_git_caps_stdout(tmp_path: Path) -> None:
    code = "import sys; sys.stdout.write('x' * 200000); sys.stdout.flush()"
    run = run_git([sys.executable, "-c", code], tmp_path, 20.0, max_stdout=1000)
    assert run.truncated and len(run.stdout) <= 1000


def test_run_git_captures_output_and_stderr(tmp_path: Path) -> None:
    code = "import sys; sys.stdout.write('ok'); sys.stderr.write('warn'); sys.exit(3)"
    run = run_git([sys.executable, "-c", code], tmp_path, 20.0)
    assert run == GitRun(returncode=3, stdout=b"ok", stderr_tail="warn", timed_out=False)
