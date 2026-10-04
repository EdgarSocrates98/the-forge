"""WorkspaceRelations: explicit relations from ``.forge/config/workspace.toml``.

The file is optional and committable (like ``providers.toml``)::

    [[relations]]
    source = "orders-api"
    target = "data-pipeline"
    kind = "depends_on"

Only ``depends_on`` between two discovered repositories is accepted. An invalid entry or one
naming a repository that does not exist is ignored with a ``FORGE-WORKSPACE-CONFIG`` warning;
a malformed file ignores every entry with one warning. Loading never fails the run.
"""

import tomllib
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

from theforge.contracts.codes import Codes
from theforge.contracts.workspace import WorkspaceRelation

__all__ = ["MAX_WORKSPACE_CONFIG_BYTES", "WORKSPACE_CONFIG", "load_relations"]

WORKSPACE_CONFIG: Final = "config/workspace.toml"  # relative to the .forge directory
RELATIONS_EVIDENCE: Final = ".forge/config/workspace.toml"
MAX_WORKSPACE_CONFIG_BYTES: Final = 64 * 1024
_ENTRY_KEYS: Final = frozenset({"source", "target", "kind"})
_EXPLICIT_KINDS: Final = frozenset({"depends_on"})


def _warning(detail: str) -> str:
    return f"{Codes.WORKSPACE_CONFIG}: {RELATIONS_EVIDENCE}: {detail}"


def load_relations(
    forge_dir: Path | None, repositories: Sequence[str],
) -> tuple[list[WorkspaceRelation], list[str]]:
    """Explicit relations and the warnings of ignored entries (both deterministic)."""
    if forge_dir is None:
        return [], []
    path = forge_dir / WORKSPACE_CONFIG
    try:
        if not path.is_file():
            return [], []
        with path.open("rb") as handle:  # bounded read: never loads more than the cap + 1
            raw = handle.read(MAX_WORKSPACE_CONFIG_BYTES + 1)
    except OSError as exc:
        return [], [_warning(f"unreadable, all relations ignored ({type(exc).__name__})")]
    if len(raw) > MAX_WORKSPACE_CONFIG_BYTES:
        return [], [_warning(
            f"larger than {MAX_WORKSPACE_CONFIG_BYTES} bytes, all relations ignored")]
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        return [], [_warning(f"malformed ({type(exc).__name__}), all relations ignored")]
    warnings = [_warning(f"unknown key {key!r} ignored")
                for key in sorted(data) if key != "relations"]
    entries = data.get("relations", [])
    if not isinstance(entries, list):
        return [], [*warnings, _warning("'relations' must be an array of tables, all ignored")]
    known = set(repositories)
    relations: dict[tuple[str, str, str], WorkspaceRelation] = {}
    for index, entry in enumerate(entries):
        problem = _entry_problem(entry, known)
        if problem is not None:
            warnings.append(_warning(f"relations[{index}] ignored: {problem}"))
            continue
        key = (entry["source"], entry["kind"], entry["target"])
        relations.setdefault(key, WorkspaceRelation(
            source=entry["source"], target=entry["target"], kind="depends_on",
            epistemic="explicit", evidence=RELATIONS_EVIDENCE))
    return [relations[key] for key in sorted(relations)], warnings


def _entry_problem(entry: Any, known: set[str]) -> str | None:
    if not isinstance(entry, dict):
        return "not a table"
    extra = sorted(set(entry) - _ENTRY_KEYS)
    if extra:
        return f"unknown keys {extra}"
    for field in ("source", "target", "kind"):
        if not isinstance(entry.get(field), str) or not entry[field]:
            return f"{field!r} must be a non-empty string"
    if entry["kind"] not in _EXPLICIT_KINDS:
        return f"kind {_short(entry['kind'])} is not one of {sorted(_EXPLICIT_KINDS)}"
    if entry["source"] == entry["target"]:
        return "source and target are the same repository"
    for field in ("source", "target"):
        if entry[field] not in known:
            return f"{field} {_short(entry[field])} is not a repository of the workspace"
    return None


def _short(value: str, limit: int = 80) -> str:
    text = repr(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"
