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
                if os.path.islink(os.path.join(dirpath, name)):
                    rel = (Path(dirpath) / name).relative_to(root_resolved).as_posix()
                    excluded[rel] = "symlinked_dir"
                    continue
                kept.append(name)
            dirnames[:] = kept
            for name in sorted(filenames):
                if len(files) >= MAX_FILES:
                    break
                _consider(root_resolved, Path(dirpath) / name, files, excluded)
    return WorkspaceScan(
        root=root_resolved,
        files=sorted(files),
        excluded=[ExcludedFile(path=p, reason=r) for p, r in sorted(excluded.items())],
    )


def _consider(root: Path, path: Path, files: set[str], excluded: dict[str, str]) -> None:
    rel = path.relative_to(root).as_posix()
    if is_secret_name(path.name):
        excluded[rel] = "secret"
    elif path.is_symlink() and resolve_inside(root, path) is None:
        excluded[rel] = "outside_root"
    else:
        files.add(rel)
