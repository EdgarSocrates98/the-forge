"""Mounts the cross-forge-foundation proof workspace (``fixtures/workspaces/cross``).

The fixture tree is a root that is not a repository with one repository per subdirectory
(``data-pipeline``: PySpark job + ``pyspark``; ``orders-api``: OpenAPI contract + FastAPI
app + ``fastapi``). It is copied into a fresh directory under ``tempfile.gettempdir()`` --
outside any enclosing git repository, so git discovery never walks up into this checkout --
and, when git is available, each repository is initialized independently with one commit.
"""

import contextlib
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CROSS_FIXTURE = Path(__file__).parent / "fixtures" / "workspaces" / "cross"
CROSS_REPOSITORIES = ("data-pipeline", "orders-api")
GIT_TIMEOUT_S = 30
# Variables that would redirect git away from the repository being created.
_GIT_REDIRECTS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_CEILING_DIRECTORIES",
)
_GIT_CONFIG = (
    "-c",
    "user.name=The Forge Tests",
    "-c",
    "user.email=tests@theforge.invalid",
    "-c",
    "commit.gpgsign=false",
    "-c",
    "core.autocrlf=false",
    "-c",
    "init.defaultBranch=main",
)


@dataclass(frozen=True)
class CrossWorkspace:
    root: Path
    repositories: tuple[Path, ...]
    git: bool  # every repository was initialized with git and has one commit


def git_available() -> bool:
    return shutil.which("git") is not None


def enclosing_repository(path: Path) -> Path | None:
    """The nearest directory at or above ``path`` that holds a ``.git`` entry."""
    for candidate in (path, *path.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _git(repo: Path, *args: str) -> None:
    env = {k: v for k, v in os.environ.items() if k not in _GIT_REDIRECTS}
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"
    subprocess.run(
        ["git", *_GIT_CONFIG, *args],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT_S,
        check=True,
    )


def mount_cross_workspace(*, git: bool = True) -> CrossWorkspace:
    """Copy the fixture into a new temp dir; ``git`` is honored only when git exists."""
    base = Path(tempfile.mkdtemp(prefix="theforge-cross-", dir=tempfile.gettempdir()))
    root = base / "cross"
    try:
        enclosing = enclosing_repository(base)
        if enclosing is not None:
            raise RuntimeError(f"temp dir {base} is inside the git repository {enclosing}")
        shutil.copytree(CROSS_FIXTURE, root)
        repositories = tuple(root / name for name in CROSS_REPOSITORIES)
        use_git = git and git_available()
        if use_git:
            for repo in repositories:
                _git(repo, "init", "-q")
                _git(repo, "add", "-A")
                _git(repo, "commit", "-q", "--no-verify", "-m", "cross fixture")
        return CrossWorkspace(root=root, repositories=repositories, git=use_git)
    except BaseException:
        _rmtree(base)
        raise


def remove_cross_workspace(workspace: CrossWorkspace) -> None:
    _rmtree(workspace.root.parent)


def _make_writable_and_retry(func: Callable[..., Any], path: str, *_: Any) -> None:
    # git stores objects read-only; Windows refuses to delete them until they are writable.
    os.chmod(path, stat.S_IWRITE)
    func(path)


def _rmtree(path: Path) -> None:
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_make_writable_and_retry)
    else:
        shutil.rmtree(path, onerror=_make_writable_and_retry)


@contextlib.contextmanager
def mounted_cross_workspace(*, git: bool = True) -> Iterator[CrossWorkspace]:
    workspace = mount_cross_workspace(git=git)
    try:
        yield workspace
    finally:
        remove_cross_workspace(workspace)
