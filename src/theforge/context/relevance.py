"""Relevance: generic, deterministic signals per scanned file and a fixed priority order.

Signals (stable codes recorded in ``ContextFile.signals``): ``intent_lines``,
``intent_path``, ``target:<target>``, ``glob:<glob>``, ``git:changed`` and
``dependency_manifest``. No domain rule lives here: globs come from the provider manifest,
dependency manifests from the generic ``contracts.types.DEPENDENCY_MANIFESTS`` list, and
everything else from the task and the workspace. No embeddings, LLM or network (2.6).

The result depends only on the content of the inputs, never on the order of
``scan.files`` or ``globs`` (1.8).
"""

import posixpath
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Final

from theforge.context.scan import WorkspaceScan
from theforge.contracts import TaskSpec
from theforge.contracts.base import ContractError
from theforge.contracts.context import LineRange
from theforge.contracts.types import DEPENDENCY_MANIFESTS, ExclusionReason
from theforge.security.paths import is_secret_name

SIGNAL_INTENT_LINES: Final = "intent_lines"
SIGNAL_INTENT_PATH: Final = "intent_path"
SIGNAL_GIT_CHANGED: Final = "git:changed"
SIGNAL_DEPENDENCY: Final = "dependency_manifest"
TARGET_PREFIX: Final = "target:"
GLOB_PREFIX: Final = "glob:"

# Range suffixes: ":N", ":N-M", ":LN-LM" and "#LN-LM".
_REF: Final = re.compile(
    r"^(?P<path>.+?)(?::L?(?P<a>\d+)(?:-L?(?P<b>\d+))?|#L(?P<c>\d+)-L(?P<d>\d+))?$")
_EXT: Final = re.compile(r"\.[A-Za-z][A-Za-z0-9_-]*$")
_DRIVE: Final = re.compile(r"^[A-Za-z]:")
_LEADING: Final = "\"'`([{<*"
_TRAILING: Final = "\"'`)]}>*,;:!?."


@dataclass(frozen=True, kw_only=True)
class IntentRefs:
    paths: frozenset[str]  # cited paths present in the scan
    ranges: Mapping[str, LineRange]  # cited line range per accepted path
    rejected: Mapping[str, ExclusionReason]  # cited path -> reason it was refused


@dataclass(frozen=True, kw_only=True)
class RankedFile:
    path: str
    signals: tuple[str, ...]
    lines: LineRange | None  # line range cited in the intent, if any


def parse_intent_refs(intent: str, scan: WorkspaceScan) -> IntentRefs:
    """Find path references in the intent and accept only exact scanned relative paths."""
    files = frozenset(scan.files)
    excluded = {e.path: e.reason for e in scan.excluded}
    paths: set[str] = set()
    ranges: dict[str, LineRange] = {}
    rejected: dict[str, ExclusionReason] = {}
    for raw in intent.split():
        parsed = _parse_token(raw)
        if parsed is None:
            continue
        path, lines = parsed
        reason = _rejection(path, files, excluded)
        if reason is not None:
            rejected[path] = reason
            continue
        paths.add(path)
        if lines is not None:
            prev = ranges.get(path)
            ranges[path] = lines if prev is None else LineRange(
                start=min(prev.start, lines.start), end=max(prev.end, lines.end))
    return IntentRefs(
        paths=frozenset(paths),
        ranges=MappingProxyType(dict(sorted(ranges.items()))),
        rejected=MappingProxyType(dict(sorted(rejected.items()))),
    )


def rank_candidates(
    task: TaskSpec, globs: Sequence[str], scan: WorkspaceScan,
    changed: frozenset[str], refs: IntentRefs,
) -> tuple[list[RankedFile], int]:
    """Return (candidates in fixed priority order, number of scanned files with no signal)."""
    targets = sorted({t for t in (_normalize_target(t, scan.root) for t in task.targets) if t})
    unique_globs = sorted(set(globs))
    keyed: list[tuple[tuple[bool, bool, bool, bool, int, bool, str], RankedFile]] = []
    files = sorted(set(scan.files))
    for rel in files:
        intent = rel in refs.paths
        lines = refs.ranges.get(rel) if intent else None
        target_hits = [t for t in targets if rel == t or rel.startswith(t + "/")]
        glob_hits = [g for g in unique_globs if PurePosixPath(rel).match(g)]
        git = rel in changed
        dependency = "/" not in rel and any(fnmatchcase(rel, p) for p in DEPENDENCY_MANIFESTS)
        signals: list[str] = []
        if lines is not None:
            signals.append(SIGNAL_INTENT_LINES)
        if intent:
            signals.append(SIGNAL_INTENT_PATH)
        signals += [TARGET_PREFIX + t for t in target_hits]
        signals += [GLOB_PREFIX + g for g in glob_hits]
        if git:
            signals.append(SIGNAL_GIT_CHANGED)
        if dependency:
            signals.append(SIGNAL_DEPENDENCY)
        if not signals:
            continue
        key = (not intent, not target_hits, not glob_hits, not git, -len(glob_hits),
               not dependency, rel)
        keyed.append((key, RankedFile(path=rel, signals=tuple(signals), lines=lines)))
    keyed.sort(key=lambda item: item[0])
    return [ranked for _, ranked in keyed], len(files) - len(keyed)


def _parse_token(raw: str) -> tuple[str, LineRange | None] | None:
    token = raw.lstrip(_LEADING).rstrip(_TRAILING)
    if not token or "://" in token:
        return None
    match = _REF.match(token.replace("\\", "/"))
    if match is None:
        return None
    path = match["path"]
    while path.startswith("./"):
        path = path[2:]
    if not path or path.endswith("/") or ("/" not in path and _EXT.search(path) is None):
        return None  # empty, a directory, or a plain word
    start, end = (match["a"], match["b"]) if match["a"] else (match["c"], match["d"])
    return path, _line_range(start, end)


def _line_range(start: str | None, end: str | None) -> LineRange | None:
    if start is None:
        return None
    try:
        return LineRange(start=int(start), end=int(end if end is not None else start))
    except ContractError:
        return None


def _rejection(
    path: str, files: frozenset[str], excluded: Mapping[str, str],
) -> ExclusionReason | None:
    if (path.startswith(("/", "~")) or _DRIVE.match(path)
            or ".." in path.split("/")):
        return "outside_root"
    if is_secret_name(path.rsplit("/", 1)[-1]) or excluded.get(path) == "secret":
        return "secret"
    if path in files:
        return None
    if excluded.get(path) == "outside_root":
        return "outside_root"
    return "missing"


def _normalize_target(target: str, root: Path) -> str:
    """Explicit target as a relative posix prefix, resolved like the scan resolves it.

    Pure path arithmetic (no filesystem access): an absolute target inside ``root`` becomes
    relative, ``.``/``..`` segments are collapsed, and the default target ``.`` (or the root
    itself, or anything that leaves the root) yields ``""`` -- no target signal.
    """
    candidate = Path(target)
    if candidate.anchor:
        try:
            candidate = candidate.relative_to(root)
        except ValueError:
            return ""
    norm = posixpath.normpath(candidate.as_posix().replace("\\", "/"))
    if norm in (".", "") or norm == ".." or norm.startswith(("../", "/")):
        return ""
    return norm
