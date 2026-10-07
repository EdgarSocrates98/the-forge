"""ContextVerify: context drift (TOCTOU) between the ContextPack hashes and what was read.

``Evidence.hash`` semantics (normative, see ``docs/protocol.md``): the sha256 of exactly the
content delivered for ``location.path`` -- the whole file for ``reference`` items (and
``requested`` without ``lines``); the bytes of the item's ``lines`` range (newline rule of
``fingerprints.hash_lines``) for ``excerpt`` items and ``requested`` with ``lines``.
``Location.line`` never changes that scope; anything else must leave ``hash`` null.

Drift is either reported by the provider (a non-null ``hash`` that matches no item with the
same path) or found by re-verification, which re-hashes the selected items without any cache.
``apply_drift`` demotes ``confirmed``/``observed`` evidence on drifted items to ``unresolved``
and marks the result ``partial``; without drift it returns the result unchanged.
"""

import os
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final

from theforge.context.fingerprints import hash_file, hash_lines
from theforge.contracts.context import ContextFile, ContextPack
from theforge.contracts.result import Evidence, ExecutionResult
from theforge.contracts.types import VerificationLevel
from theforge.security.paths import resolve_inside

DRIFT_LIMITATION_PREFIX: Final = "context-drift:"
NOT_REVERIFIED_LIMITATION: Final = "context-not-reverified"
_ASSERTIVE: Final = frozenset({"confirmed", "observed"})


@dataclass(frozen=True, kw_only=True)
class DriftReport:
    drifted: tuple[str, ...]  # sorted paths
    checked: int  # items re-verified
    level: VerificationLevel
    limitations: tuple[str, ...]


def _evidence_path(evidence: Evidence) -> str:
    """Item path an evidence refers to: ``location.path``, else ``subject``."""
    return evidence.location.path if evidence.location is not None else evidence.subject


def provider_reported_drift(pack: ContextPack, result: ExecutionResult) -> frozenset[str]:
    """Paths whose reported ``Evidence.hash`` matches no pack item with the same path.

    Evidence without ``location`` or with a null ``hash`` never reports drift, and a path
    absent from the pack is not a pack item (the provider should have left ``hash`` null).
    """
    hashes: dict[str, set[str]] = {}
    for item in pack.files:
        hashes.setdefault(item.path, set()).add(item.sha256)
    drifted: set[str] = set()
    for evidence in result.evidence:
        if evidence.location is None or evidence.hash is None:
            continue
        known = hashes.get(evidence.location.path)
        if known is not None and evidence.hash not in known:
            drifted.add(evidence.location.path)
    return frozenset(drifted)


def items_to_verify(
    pack: ContextPack, result: ExecutionResult, level: VerificationLevel
) -> list[ContextFile]:
    """minimal: none; conditional: items cited by confirmed/observed evidence; strong: all."""
    if level == "minimal":
        return []
    if level == "strong":
        return list(pack.files)
    cited = {_evidence_path(e) for e in result.evidence if e.epistemic in _ASSERTIVE}
    return [item for item in pack.files if item.path in cited]


def _whole_file_sha256(resolved: Path) -> str | None:
    """Uncached whole-file hash (never through FingerprintStore). None = unreadable."""
    got = hash_file(resolved)
    return None if got is None else got[0]


def current_file_sha256(root: Path, path: str) -> str | None:
    """Uncached whole-file sha256 of ``root/path``; None if missing, unreadable or outside.

    Shared with the forge verification of provider artifacts (``forger.verification``).
    """
    resolved = resolve_inside(root, root / path)
    if resolved is None or not resolved.is_file():
        return None
    return _whole_file_sha256(resolved)


def declared_artifact_problem(root: Path, path: str, sha256: str) -> str | None:
    """Why a provider-declared artifact fails verification, or None when its hash matches.

    Classification order, each stricter check gating the next: the declared path must be
    lexically under ``root`` (an absolute or ``..`` path is refused without stat'ing
    outside), must exist, must resolve physically inside ``root`` (a link that escapes
    or cannot be resolved fails), must be a regular file, and its uncached content must
    hash to ``sha256``. A link whose target stays inside ``root`` verifies by content.
    """
    base = Path(os.path.normpath(root))
    lexical = Path(os.path.normpath(root / path))
    if not lexical.is_relative_to(base):
        return "declared path escapes work/"
    resolved = resolve_inside(root, root / path)
    if resolved is None:
        if not os.path.lexists(lexical):
            return "missing"
        return "unresolvable or a link resolving outside work/"
    if not resolved.is_file():
        return "not a regular file"
    if _whole_file_sha256(resolved) != sha256:
        return "hash differs"
    return None


def _current_sha256(root: Path, item: ContextFile) -> str | None:
    if item.lines is None:
        return current_file_sha256(root, item.path)
    resolved = resolve_inside(root, root / item.path)
    if resolved is None or not resolved.is_file():
        return None
    got = hash_lines(resolved, item.lines)
    return got[0] if got is not None else None


def reverify(root: Path, items: Sequence[ContextFile]) -> frozenset[str]:
    """Paths whose current content (same scope as the item) differs from ``item.sha256``.

    Missing, unreadable, outside-root files and ranges past the end count as drift.
    """
    return frozenset(item.path for item in items if _current_sha256(root, item) != item.sha256)


def check_drift(
    root: Path, pack: ContextPack, result: ExecutionResult, level: VerificationLevel
) -> DriftReport:
    items = items_to_verify(pack, result, level)
    drifted = provider_reported_drift(pack, result) | reverify(root, items)
    limitations = (NOT_REVERIFIED_LIMITATION,) if level == "minimal" else ()
    return DriftReport(
        drifted=tuple(sorted(drifted)), checked=len(items), level=level, limitations=limitations
    )


def apply_drift(result: ExecutionResult, report: DriftReport) -> ExecutionResult:
    """Demote evidence on drifted items, record the paths and mark the result partial.

    With no drifted path the very same result object is returned (the report's own
    limitations, e.g. ``context-not-reverified``, belong to the run telemetry/receipt).
    """
    if not report.drifted:
        return result
    drifted = set(report.drifted)
    evidence = [
        replace(
            e,
            epistemic="unresolved",
            limitations=[*e.limitations, f"{DRIFT_LIMITATION_PREFIX} was {e.epistemic}"],
        )
        if e.epistemic in _ASSERTIVE and _evidence_path(e) in drifted
        else e
        for e in result.evidence
    ]
    limitations = [
        *result.limitations,
        *(f"{DRIFT_LIMITATION_PREFIX} {path}" for path in report.drifted),
    ]
    return replace(result, status="partial", evidence=evidence, limitations=limitations)
