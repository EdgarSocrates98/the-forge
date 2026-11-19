"""SHA↔evidence binding (cycle 16.1 §5.6) — ``context.git.head_sha``.

Certification receipts must name the commit actually tested, captured at
run time from ``git rev-parse --verify HEAD`` through the hardened runner
— never a hand-written or stale value. Absent git proof returns ``None``
and the receipt records the gap; it never invents a SHA.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from theforge.context.git import GitRun, head_sha


def _git_repo(root: Path) -> Path:
    if shutil.which("git") is None:
        pytest.skip("git not on PATH")
    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
        "PATH": os.environ.get("PATH", ""),
    }
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True, env=env)
    (root / "f.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, env=env)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=root, check=True, env=env)
    return root


def test_head_sha_binds_live_rev_parse(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path / "repo")
    want = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert head_sha(repo) == want
    assert head_sha(repo) == want  # stable across calls


def test_head_sha_tracks_new_commit(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path / "repo")
    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
        "PATH": os.environ.get("PATH", ""),
    }
    (repo / "f.txt").write_text("y", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, env=env)
    subprocess.run(["git", "commit", "-qm", "second"], cwd=repo, check=True, env=env)
    want = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert head_sha(repo) == want


def test_head_sha_none_outside_repo() -> None:
    # basetemp lives inside the checkout (still a valid rev-parse target —
    # it returns the repo's own HEAD), so use a system tmpdir outside it.
    with tempfile.TemporaryDirectory() as d:
        assert head_sha(Path(d)) is None


def test_head_sha_inside_repo_binds_repo_head() -> None:
    # A directory *inside* a repository legitimately binds that repo's HEAD.
    root = Path(__file__).resolve().parents[1]
    want = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert head_sha(root / "tests") == want


def test_head_sha_none_when_git_fails(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path / "repo")

    def _failing(argv: object, cwd: Path, timeout: float) -> GitRun:
        return GitRun(returncode=128, stdout=b"", stderr_tail="boom", timed_out=False)

    assert head_sha(repo, runner=_failing) is None
