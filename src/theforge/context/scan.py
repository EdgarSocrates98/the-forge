"""Workspace scan: list candidate files under targets, never escaping the root."""

import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from theforge.contracts import ExcludedFile
from theforge.security.paths import IGNORED_DIRS, is_secret_name, resolve_inside

MAX_FILES = 20_000


@dataclass(frozen=True, kw_only=True)
class WorkspaceScan:
    root: Path
    files: list[str]
    excluded: list[ExcludedFile]


def scan_workspace(root: Path, targets: Sequence[str]) -> WorkspaceScan:
    root_resolved = root.resolve()
    files: set[str] = set()
    excluded: dict[str, str] = {}
    capped = False
    for target in list(targets) or ["."]:
        start = root_resolved / target
        inside = resolve_inside(root_resolved, start)
        if inside is None:
            excluded[target] = "missing" if not os.path.lexists(start) else "outside_root"
            continue
        if inside.is_file():
            _consider(root_resolved, inside, files, excluded)
            continue
        for dirpath, dirnames, filenames in os.walk(inside, followlinks=False):
            kept: list[str] = []
            for name in sorted(dirnames):
                if name in IGNORED_DIRS:
                    continue
                child = Path(dirpath) / name
                if not _is_plain_dir(root_resolved, Path(dirpath), child):
                    excluded[child.relative_to(root_resolved).as_posix()] = "symlinked_dir"
                    continue
                kept.append(name)
            dirnames[:] = kept
            for name in sorted(filenames):
                if len(files) >= MAX_FILES:
                    capped = True
                    break
                _consider(root_resolved, Path(dirpath) / name, files, excluded)
            if capped:
                dirnames[:] = []
                break
        if capped:
            break
    if capped:
        excluded["*"] = "max_files_reached"
    return WorkspaceScan(
        root=root_resolved,
        files=sorted(files),
        excluded=[ExcludedFile(path=p, reason=r) for p, r in sorted(excluded.items())],
    )


def _is_plain_dir(root: Path, parent: Path, child: Path) -> bool:
    """True only for a real directory inside root: not a symlink, junction or redirect."""
    if resolve_inside(root, child) is None:
        return False
    if os.path.islink(child) or (hasattr(os.path, "isjunction") and os.path.isjunction(child)):
        return False
    return child.resolve() == parent.resolve() / child.name


def _consider(root: Path, path: Path, files: set[str], excluded: dict[str, str]) -> None:
    rel = path.relative_to(root).as_posix()
    resolved = resolve_inside(root, path)
    if is_secret_name(path.name) or (resolved is not None and is_secret_name(resolved.name)):
        excluded[rel] = "secret"
    elif resolved is None:
        excluded[rel] = "outside_root"
    else:
        files.add(rel)
