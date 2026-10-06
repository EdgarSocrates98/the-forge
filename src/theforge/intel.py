"""Project intelligence: the incremental technical memory under ``.forge/intel/``.

Two documents, both project-local, gitignored, written atomically after
``security.redact``:

- ``project.json`` — ``ProjectIntel/v1``: the cached ``WorkspaceDescriptor`` and
  the ``IntelFingerprints`` of everything it derives from. ``refresh_intel``
  recomputes the fingerprints first and recomputes only the sections whose
  inputs changed (I1); git state is always read live — a cached ``git`` summary
  would be precisely the silent staleness I2 forbids.
- ``decisions.json`` — ``DecisionMemory/v1``: reusable decisions (routing,
  profile, pattern, verdict), deduplicated by identity.

Everything here is best-effort like the metrics store (H): a read or write
problem degrades to a note, never to a failed run; malformed persisted data
fails closed — ignored, with the reason named.
"""

import contextlib
import json
import os
import tempfile
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Final, Literal

from theforge.context.scan import WorkspaceScan
from theforge.contracts.base import ContractError, from_dict, to_dict
from theforge.contracts.canonical import sha256_hex, sha256_of, utc_now
from theforge.contracts.decisions import (
    MAX_DECISIONS,
    MAX_RUN_TRAIL,
    DecisionKind,
    DecisionMemory,
    RememberedDecision,
)
from theforge.contracts.intel import IntelFingerprints, ProjectIntel
from theforge.contracts.types import DEPENDENCY_MANIFESTS
from theforge.meta import PRODUCER
from theforge.registry import RegistryRecord
from theforge.security.redact import redact
from theforge.state import FORGE_DIR_NAME
from theforge.workspace.describe import describe_workspace, discover_repositories

__all__ = [
    "INTEL_DIR", "INTEL_FILE", "DECISIONS_FILE", "IntelValidity",
    "compute_fingerprints", "freshness", "load_intel", "load_decisions",
    "record_decision", "refresh_intel", "save_intel", "stale_sections",
]

INTEL_DIR = "intel"
INTEL_FILE = "project.json"
DECISIONS_FILE = "decisions.json"
IntelValidity = Literal["current", "stale", "unknown"]

# Which fingerprint governs which descriptor section — the unit of "update only
# what is needed" (I1). ``repositories`` and git are never reusable: discovery is
# part of the fingerprint and git is live evidence, re-read on every refresh.
_SECTION_INPUTS: Final[dict[str, tuple[str, ...]]] = {
    "paths": ("repos_sha", "depfiles_sha"),
    "dependency_files": ("repos_sha", "depfiles_sha"),
    "technologies": ("files_sha", "depfiles_sha", "manifests_sha"),
    "relations": ("repos_sha", "relations_sha"),
}


def _dir(root: Path) -> Path:
    return root / FORGE_DIR_NAME / INTEL_DIR


def _intel_path(root: Path) -> Path:
    return _dir(root) / INTEL_FILE


def _decisions_path(root: Path) -> Path:
    return _dir(root) / DECISIONS_FILE


# --- fingerprints ---------------------------------------------------------------------------

def _dependency_files(root: Path, repos: Sequence[str]) -> list[Path]:
    """Every dependency manifest directly under each repository, scan-style."""
    found: list[Path] = []
    for repo in repos:
        base = root if repo == "." else root.joinpath(*repo.split("/"))
        for pattern in DEPENDENCY_MANIFESTS:
            candidates = sorted(base.glob(pattern)) if "*" in pattern else [base / pattern]
            for path in candidates:
                if path.is_file() and not path.is_symlink() and path not in found:
                    found.append(path)
    return sorted(found)


def compute_fingerprints(
    root: Path, scan_files: Sequence[str], repos: Sequence[str],
    records: Sequence[tuple[str, str, str | None]],
) -> IntelFingerprints:
    """Content digests of the descriptor's inputs — no git, no manifest parsing.

    ``records`` is ``(id, state, manifest_sha256)`` per registry record (all of
    them: a broken provider changing state also changes the observable graph).
    """
    dep_parts: list[str] = []
    for path in _dependency_files(root, repos):
        try:
            dep_parts.append(f"{path.relative_to(root).as_posix()}:"
                             f"{sha256_hex(path.read_bytes())}")
        except OSError:
            dep_parts.append(f"{path.relative_to(root).as_posix()}:unreadable")
    manifest_parts = sorted(f"{pid}:{state}:{sha or '-'}"
                            for pid, state, sha in records)
    toml = root / FORGE_DIR_NAME / "config" / "workspace.toml"
    try:
        relations = sha256_hex(toml.read_bytes()) if toml.is_file() else ""
    except OSError:
        relations = "unreadable"
    return IntelFingerprints(
        files_sha=sha256_of(sorted(scan_files)),
        repos_sha=sha256_of(repos),
        depfiles_sha=sha256_of(dep_parts),
        manifests_sha=sha256_of(manifest_parts),
        relations_sha=relations,
    )


def freshness(
    intel: ProjectIntel, scan_files: Sequence[str], repos: Sequence[str],
    records: Sequence[tuple[str, str, str | None]],
) -> tuple[IntelValidity, list[str]]:
    """Read-time verdict: ``(validity, stale sections)`` — never stored (I2).

    ``current`` only when every fingerprint still matches; ``stale`` names the
    sections whose inputs changed; ``unknown`` when the fingerprints cannot be
    recomputed (the honest answer to "cannot confirm freshness").
    """
    try:
        current = compute_fingerprints(
            Path(intel.root), scan_files, repos, records)
    except OSError:
        return "unknown", ["fingerprints-uncomputable"]
    stale = sorted({section
                    for section, inputs in _SECTION_INPUTS.items()
                    for name in inputs
                    if getattr(current, name) != getattr(intel.fingerprints, name)})
    return ("current", []) if not stale else ("stale", stale)


# --- store ------------------------------------------------------------------------------------

def _load(path: Path, cls: type, label: str) -> tuple[object | None, str | None]:
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None, None
    except OSError as exc:
        return None, f"intel: cannot read {path}: {exc}"
    try:
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("expected a JSON object")
        return from_dict(cls, data, strict=True), None
    except (ValueError, ContractError) as exc:
        # Poisoned intelligence fails closed: no memory, one audible note.
        return None, f"intel: ignored malformed {label} at {path}: {exc}"


def _write(path: Path, obj: object) -> str | None:
    data = to_dict(obj)
    if redact(data) != data:  # refuse rather than persist a silently altered file
        return f"intel: {path.name} not written (redaction would alter it)"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.stem}-",
                                   suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(data, indent=2, sort_keys=True))
            os.replace(tmp, path)
        except OSError:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise
    except OSError as exc:
        return f"intel: {path.name} not written: {exc}"
    return None


def load_intel(root: Path) -> tuple[ProjectIntel | None, str | None]:
    """The stored snapshot, or ``(None, warning)`` on unreadable/malformed data."""
    intel, warning = _load(_intel_path(root), ProjectIntel, "project intel")
    return intel, warning  # type: ignore[return-value]


def save_intel(root: Path, intel: ProjectIntel) -> str | None:
    return _write(_intel_path(root), intel)


def load_decisions(root: Path) -> tuple[DecisionMemory | None, str | None]:
    memory, warning = _load(_decisions_path(root), DecisionMemory, "decision memory")
    return memory, warning  # type: ignore[return-value]


def record_decision(
    root: Path, kind: DecisionKind, subject: str, choice: str, basis: str,
    run_id: str,
) -> str | None:
    """Fold one reusable decision into the memory; returns a warning on failure.

    Reuse is deduplication by identity: the same (kind, subject, choice) reaffirms
    the existing entry — ``corroborations`` and the bounded run trail grow, the
    memory does not. Bounded: at most ``MAX_DECISIONS`` entries, oldest
    ``updated_at`` evicted first.
    """
    try:
        memory, warning = load_decisions(root)
        entries = list(memory.entries) if memory is not None else []
        ident = sha256_hex(f"{kind}|{subject}|{choice}".encode())
        now = utc_now()
        existing = next((e for e in entries if e.id == ident), None)
        if existing is not None:
            trail = [r for r in existing.runs if r != run_id][-MAX_RUN_TRAIL + 1:]
            trail.append(run_id)
            entries[entries.index(existing)] = replace(
                existing, updated_at=now,
                corroborations=existing.corroborations + 1, runs=trail)
        else:
            entries.append(RememberedDecision(
                id=ident, kind=kind, subject=subject, choice=choice, basis=basis,
                created_at=now, updated_at=now, corroborations=1, runs=[run_id]))
        if len(entries) > MAX_DECISIONS:
            entries.sort(key=lambda e: e.updated_at, reverse=True)
            del entries[MAX_DECISIONS:]
        entries.sort(key=lambda e: e.id)
        problem = _write(_decisions_path(root), DecisionMemory(
            producer=PRODUCER, created_at=memory.created_at
            if memory is not None else now, entries=entries))
        return problem or warning  # a prior read problem still surfaces once
    except (OSError, ContractError, ValueError) as exc:
        return f"intel: decision not recorded: {exc}"


# --- incremental refresh (I1) -------------------------------------------------------------------

def stale_sections(prior: ProjectIntel, current: IntelFingerprints) -> list[str]:
    """The descriptor sections whose inputs changed since ``prior``."""
    return sorted({section
                   for section, inputs in _SECTION_INPUTS.items()
                   for name in inputs
                   if getattr(current, name) != getattr(prior.fingerprints, name)})


def refresh_intel(
    root: Path, scan: WorkspaceScan, records: list[RegistryRecord],
) -> tuple[ProjectIntel, list[str]]:
    """Describe the workspace, reusing still-fresh sections of the snapshot (I1).

    Returns ``(intel, notes)``: the persisted snapshot (also written to
    ``.forge/intel/project.json``, best-effort) and the run notes — the load
    warning, the save warning, and one ``intel: reused <sections>`` audit note.
    The ``descriptor`` inside is the fresh truth for this call: git re-read live,
    stale sections recomputed, fresh sections taken verbatim from the snapshot
    and named in ``intel.reused``.
    """
    notes: list[str] = []
    prior, warning = load_intel(root)
    if warning is not None:
        notes.append(warning)
    if prior is not None and prior.root != str(root.resolve()):
        # A snapshot written for another root is not this workspace's memory —
        # identical content does not make it trustworthy here.
        prior = None
        notes.append("intel: snapshot root differs; treated as a first refresh")
    try:
        repos = discover_repositories(root)
    except OSError:
        repos = []
        notes.append("intel: repository discovery failed; snapshot treated as stale")
    manifest_rows = [(r.entry.id, r.state, r.manifest_sha256) for r in records]
    fingerprints = compute_fingerprints(root, scan.files, repos, manifest_rows)
    reusable: frozenset[str] = frozenset()
    if prior is not None:
        stale = set(stale_sections(prior, fingerprints))
        # Only the genuinely expensive sections are reuse candidates; ``paths``,
        # repositories and relations cost a walk plus a bounded TOML read and are
        # always recomputed (``stale`` still reports them — that is the point).
        reusable = frozenset(s for s in ("technologies", "dependency_files")
                             if s not in stale)
        if stale:
            notes.append(f"intel: stale sections recomputed: {', '.join(sorted(stale))}")
    descriptor = describe_workspace(root, records, scan, prior=prior.descriptor
                                    if prior is not None else None,
                                    reusable=reusable)
    reused = sorted(reusable) if prior is not None else []
    intel = ProjectIntel(
        producer=PRODUCER, created_at=prior.created_at if prior is not None else utc_now(),
        updated_at=utc_now(), root=str(root.resolve()), fingerprints=fingerprints,
        descriptor=descriptor, reused=reused)
    problem = save_intel(root, intel)
    if problem is not None:
        notes.append(problem)
    return intel, notes
