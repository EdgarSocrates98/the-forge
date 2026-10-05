"""WorkspaceDescriber: independent repositories, git state, technologies and relations.

- Discovery: the root and its subdirectories down to ``MAX_REPO_DEPTH`` levels, never
  following symlinks or junctions, skipping ``IGNORED_DIRS`` (which include ``.git`` and
  ``.forge``). A directory with a ``.git`` entry (directory or file) is a repository; nested
  repositories are independent; the root need not be a repository.
- Git: the Wave C read-only query (``context.git.read_git_state``) per repository, embedded as
  returned; its limitations are copied. The whole description spends at most
  ``WORKSPACE_GIT_BUDGET_S`` of git time: before each query, if the time already spent plus
  one Wave C query budget (``GIT_TIMEOUT_S``) would exceed it, that repository and the
  following ones keep ``git = None`` with a budget limitation.
- Technologies: only generic dependency files matched against dependencies declared by
  providers, and provider domains whose (non catch-all) file globs match repository files,
  always with the evidencing path.
- Relations: ``contains`` observed on the file system and explicit ``depends_on`` read from
  ``.forge/config/workspace.toml``. Nothing is inferred.

No file content is read beyond the dependency files (as Wave A routing already does) and no
provider process is started.
"""

import os
import time
from collections.abc import Callable, Sequence
from pathlib import Path, PurePosixPath
from typing import Literal

from theforge.context.git import GIT_TIMEOUT_S, GitState, read_git_state
from theforge.context.scan import WorkspaceScan
from theforge.contracts.canonical import utc_now
from theforge.contracts.context import GitSummary
from theforge.contracts.types import MAX_REPO_DEPTH, MAX_REPOSITORIES, is_catch_all_glob
from theforge.contracts.workspace import (
    WORKSPACE_GIT_BUDGET_S,
    RepositoryInfo,
    Technology,
    WorkspaceDescriptor,
    WorkspaceRelation,
)
from theforge.meta import PRODUCER
from theforge.registry import RegistryRecord
from theforge.routing.signals import dependencies_by_file, normalize_dep
from theforge.security.paths import IGNORED_DIRS
from theforge.state import FORGE_DIR_NAME
from theforge.workspace.relations import load_relations

__all__ = ["describe_workspace", "discover_repositories", "repository_of"]

GitReader = Callable[[Path], GitState]
TechSource = Literal["dependency_manifest", "provider_signal"]
_Found = dict[tuple[str, str, TechSource], tuple[str, set[str]]]


def describe_workspace(
    root: Path, records: Sequence[RegistryRecord], scan: WorkspaceScan, *,
    git_reader: GitReader = read_git_state,
    clock: Callable[[], float] = time.monotonic,
    git_budget_s: float = WORKSPACE_GIT_BUDGET_S,
) -> WorkspaceDescriptor:
    """Describe the workspace under ``root``; ``scan`` lists its files (relative to root)."""
    root = root.resolve()
    limitations: list[str] = []
    unknowns: list[str] = []
    paths = discover_repositories(root, limitations)
    git = _read_git(root, paths, git_reader, clock, git_budget_s)
    deps = {p: dependencies_by_file(_abs(root, p)) for p in paths}
    repositories: list[RepositoryInfo] = []
    all_paths: set[str] = set(paths)
    for path in paths:
        summary, git_limitations = git[path]
        dependency_files = [_rel(root, f) for f in deps[path]]
        all_paths.update(dependency_files)
        repositories.append(RepositoryInfo(
            path=path, git=summary, dependency_files=sorted(dependency_files),
            limitations=git_limitations))
        if summary is None or not summary.available or summary.dirty is None:
            unknowns.append(f"{path}: git head/dirty state unknown")
    relations = _contains_relations(paths)
    explicit, warnings = load_relations(_forge_dir(root), paths)
    limitations.extend(warnings)
    relations.extend(explicit)
    return WorkspaceDescriptor(
        producer=PRODUCER, created_at=utc_now(), root=str(root),
        repositories=repositories,
        paths=sorted(all_paths, key=_path_key),
        technologies=_technologies(root, paths, deps, records, scan),
        relations=sorted(relations, key=lambda r: (r.source, r.kind, r.target)),
        limitations=limitations, unknowns=unknowns,
    )


def repository_of(descriptor: WorkspaceDescriptor, path: str) -> str | None:
    """The deepest repository of ``descriptor`` that contains ``path`` (root-relative)."""
    return _owner([r.path for r in descriptor.repositories], path)


# --- discovery ------------------------------------------------------------------------------

def discover_repositories(root: Path, limitations: list[str] | None = None) -> list[str]:
    """Repository paths relative to ``root`` (``"."`` for the root), in path order."""
    found: list[str] = []
    notes = limitations if limitations is not None else []
    _walk(root, (), found, notes)
    if len(found) > MAX_REPOSITORIES:
        del found[MAX_REPOSITORIES:]
        notes.append(f"workspace: repositories truncated at {MAX_REPOSITORIES}")
    return found


def _walk(directory: Path, parts: tuple[str, ...], found: list[str], notes: list[str]) -> None:
    """Pre-order walk with sorted children: ``found`` comes out in ``_path_key`` order."""
    if len(found) > MAX_REPOSITORIES:
        return
    if os.path.lexists(directory / ".git"):
        found.append("/".join(parts) or ".")
    if len(parts) >= MAX_REPO_DEPTH:
        return
    try:
        with os.scandir(directory) as it:
            children = sorted(
                (entry for entry in it if entry.name not in IGNORED_DIRS
                 and _is_plain_dir(entry)),
                key=lambda entry: entry.name)
    except OSError as exc:
        notes.append(f"workspace: cannot list {'/'.join(parts) or '.'} ({type(exc).__name__})")
        return
    for entry in children:
        _walk(Path(entry.path), (*parts, entry.name), found, notes)


def _is_plain_dir(entry: os.DirEntry[str]) -> bool:
    """A real directory: never a symlink or a junction (not followed)."""
    try:
        if entry.is_symlink() or not entry.is_dir(follow_symlinks=False):
            return False
    except OSError:
        return False
    isjunction = getattr(os.path, "isjunction", None)
    return not (isjunction is not None and isjunction(entry.path))


# --- git ------------------------------------------------------------------------------------

def _read_git(
    root: Path, paths: Sequence[str], reader: GitReader, clock: Callable[[], float],
    budget_s: float,
) -> dict[str, tuple[GitSummary | None, list[str]]]:
    out: dict[str, tuple[GitSummary | None, list[str]]] = {}
    spent = 0.0
    exhausted = False
    for path in paths:  # already in path order
        if not exhausted and spent + GIT_TIMEOUT_S > budget_s:
            exhausted = True
        if exhausted:
            out[path] = (None, [
                f"git: skipped: workspace git budget exhausted ({budget_s:g} s)"])
            continue
        started = clock()
        try:
            state = reader(_abs(root, path))
            summary, notes = state.summary, list(state.limitations)
        except Exception as exc:  # an injected reader must not break the description
            summary, notes = GitSummary(available=False), [f"git: failed ({type(exc).__name__})"]
        spent += max(clock() - started, 0.0)
        out[path] = (summary, notes)
    return out


# --- technologies ---------------------------------------------------------------------------

def _technologies(
    root: Path, paths: Sequence[str], deps: dict[str, dict[Path, set[str]]],
    records: Sequence[RegistryRecord], scan: WorkspaceScan,
) -> list[Technology]:
    declared: dict[str, set[str]] = {}  # normalized dependency -> {"provider/capability"}
    glob_signals: list[tuple[str, list[str], list[str]]] = []  # (who, names, globs)
    for record in sorted(records, key=lambda r: r.entry.id):
        if record.state != "ready" or record.manifest is None:
            continue
        domains = sorted(set(record.manifest.domains))
        for cap in sorted(record.manifest.capabilities, key=lambda c: c.id):
            if cap.state == "unsupported":
                continue
            who = f"{record.entry.id}/{cap.id}"
            for dep in cap.signals.dependencies:
                declared.setdefault(normalize_dep(dep), set()).add(who)
            globs = sorted({g for g in cap.signals.file_globs if not is_catch_all_glob(g)})
            if globs:
                glob_signals.append((who, domains or [cap.id], globs))

    files_by_repo: dict[str, list[str]] = {}
    for file in sorted(scan.files):
        owner = _owner(paths, file)
        if owner is not None:
            files_by_repo.setdefault(owner, []).append(file)

    found: _Found = {}
    for path in paths:
        for dep_file, names in deps[path].items():
            evidence = _rel(root, dep_file)
            for name in sorted(names & declared.keys()):
                _add(found, (path, name, "dependency_manifest"), evidence, declared[name])
        repo_files = files_by_repo.get(path, [])
        for who, signal_names, globs in glob_signals:
            hit = next((f for f in repo_files
                        if any(PurePosixPath(_inside(path, f)).match(g) for g in globs)), None)
            if hit is None:
                continue
            for name in signal_names:
                _add(found, (path, name, "provider_signal"), hit, {who})
    return [
        Technology(name=name, repository=repo, source=source,
                   evidence=evidence, matched_by=sorted(who))
        for (repo, name, source), (evidence, who) in sorted(
            found.items(), key=lambda item: (_path_key(item[0][0]), item[0][1], item[0][2]))
    ]


def _add(found: _Found, key: tuple[str, str, TechSource], evidence: str,
         who: set[str]) -> None:
    current = found.get(key)
    if current is None:
        found[key] = (evidence, set(who))
        return
    first = min(current[0], evidence, key=_path_key)
    found[key] = (first, current[1] | who)


# --- relations ------------------------------------------------------------------------------

def _contains_relations(paths: Sequence[str]) -> list[WorkspaceRelation]:
    relations: list[WorkspaceRelation] = []
    for path in paths:
        if path == ".":
            continue
        parent = _owner([p for p in paths if p != path], path) or "."
        relations.append(WorkspaceRelation(
            source=parent, target=path, kind="contains", epistemic="observed",
            evidence=f"{path}/.git"))
    return relations


def _forge_dir(root: Path) -> Path | None:
    candidate = root / FORGE_DIR_NAME
    return candidate if candidate.is_dir() and not candidate.is_symlink() else None


# --- paths ----------------------------------------------------------------------------------

def _path_key(path: str) -> tuple[str, ...]:
    return () if path == "." else tuple(path.split("/"))


def _owner(repositories: Sequence[str], path: str) -> str | None:
    best: str | None = None
    for repo in repositories:
        if (repo == "." or path == repo or path.startswith(repo + "/")) and (
                best is None or len(_path_key(repo)) > len(_path_key(best))):
            best = repo
    return best


def _inside(repo: str, path: str) -> str:
    return path if repo == "." else path[len(repo) + 1:]


def _abs(root: Path, path: str) -> Path:
    return root if path == "." else root.joinpath(*path.split("/"))


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()
