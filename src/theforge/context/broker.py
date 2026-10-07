"""Context Broker: provider-specific ContextPack by reference + hash, by tiers, within budget.

Tiers (1.1): ``metadata`` (the workspace summary, always present, 0 bytes), ``reference``
(whole file), ``excerpt`` (a line range) and ``requested`` (added by a provider request).
Effective tiers = profile tiers ∩ what the selected capability declares (1.6).

Selection walks the candidates in ``relevance.rank_candidates`` order: file limit reached ->
``max_files``; cited range with ``excerpt`` effective -> excerpt of that range; fits whole ->
``reference`` (hash via ``FingerprintStore``); does not fit and ``excerpt`` effective ->
excerpt of the longest prefix of complete lines (at least one), else ``budget``. Line-range
hashing is owned by ``context.fingerprints``, so re-verification recomputes the same hash.

No field carries file content (1.7). Paths that come from the task intent or from a provider
request and are refused are recorded through ``security.redact`` (they may be secret-shaped).
"""

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import Final

from theforge.context.fingerprints import FingerprintStore
from theforge.context.git import GitState
from theforge.context.relevance import (
    SIGNAL_DEPENDENCY,
    SIGNAL_INTENT_PATH,
    RankedFile,
    parse_intent_refs,
    rank_candidates,
)
from theforge.context.scan import WorkspaceScan
from theforge.contracts import ContextFile, ContextPack, ExcludedFile, TaskSpec
from theforge.contracts.canonical import utc_now
from theforge.contracts.context import LineRange, WorkspaceSummary
from theforge.contracts.manifest import CapabilityContext
from theforge.contracts.result import ContextRequest
from theforge.contracts.types import ExclusionReason, Metric, Tier
from theforge.meta import PRODUCER
from theforge.profiles import PROFILES, ContextProfile, assumed_profile
from theforge.security.paths import is_secret_name, resolve_inside
from theforge.security.redact import redact_text

# Derived from the profiles table (compat name used by callers and tests).
BUDGETS: Final[Mapping[str, int]] = MappingProxyType(
    {name: profile.budget_bytes for name, profile in PROFILES.items()}
)

SIGNAL_REQUESTED: Final = "requested"
_TIER_ORDER: Final[tuple[Tier, ...]] = ("metadata", "reference", "excerpt", "requested")
_DRIVE: Final = re.compile(r"^[A-Za-z]:")
_TRUNCATING: Final = frozenset({"budget", "max_files"})


def effective_tiers(profile: ContextProfile, capability: CapabilityContext) -> frozenset[Tier]:
    """Profile tiers ∩ (metadata, reference + excerpt/requested when the capability declares)."""
    declared: set[Tier] = {"metadata", "reference"}
    if capability.excerpts:
        declared.add("excerpt")
    if capability.requests:
        declared.add("requested")
    return profile.tiers & frozenset(declared)


@dataclass
class _Selection:
    """Mutable accumulator shared by the initial build and the extension."""

    budget: int
    max_files: int
    files: list[ContextFile]
    excluded: list[ExcludedFile]
    tier_bytes: dict[str, int]
    truncated: bool
    used: int = 0

    @property
    def remaining(self) -> int:
        return self.budget - self.used

    def add(self, item: ContextFile) -> None:
        self.files.append(item)
        self.used += item.bytes
        self.tier_bytes[item.tier] = self.tier_bytes.get(item.tier, 0) + item.bytes

    def exclude(self, path: str, reason: ExclusionReason, signals: list[str]) -> None:
        self.excluded.append(ExcludedFile(path=path, reason=reason, signals=signals))
        if reason in _TRUNCATING:
            self.truncated = True


def build_context_pack(
    task: TaskSpec,
    provider_id: str,
    globs: list[str],
    scan: WorkspaceScan,
    *,
    profile: ContextProfile | None = None,
    capability_context: CapabilityContext | None = None,
    git: GitState | None = None,
    fingerprints: FingerprintStore | None = None,
) -> ContextPack:
    """ContextPack round 0. Defaults: the task's profile, no excerpts, no git, no cache."""
    profile = profile if profile is not None else assumed_profile(task.budget_profile)
    tiers = effective_tiers(profile, capability_context or CapabilityContext())
    store = fingerprints if fingerprints is not None else FingerprintStore(scan.root, enabled=False)
    refs = parse_intent_refs(task.intent, scan)
    changed = git.changed if git is not None else frozenset()
    ranked, unmatched = rank_candidates(task, globs, scan, changed, refs)

    sel = _Selection(
        budget=profile.budget_bytes,
        max_files=profile.max_files,
        files=[],
        excluded=[],
        tier_bytes={t: 0 for t in _TIER_ORDER if t in tiers},
        truncated=False,
    )
    for candidate in ranked:
        _select(sel, scan.root, candidate, store, excerpts="excerpt" in tiers)

    workspace = WorkspaceSummary(
        files_scanned=len(scan.files),
        unmatched_files=unmatched,
        dependency_files=sorted(c.path for c in ranked if SIGNAL_DEPENDENCY in c.signals),
        git=git.summary if git is not None else None,
    )
    return ContextPack(
        producer=PRODUCER,
        created_at=utc_now(),
        status="truncated" if sel.truncated else "complete",
        task_id=task.id,
        provider_id=provider_id,
        root=str(scan.root),
        files=sel.files,
        excluded=_merge_exclusions(scan.excluded, refs.rejected, sel.excluded),
        budget_bytes=sel.budget,
        used_bytes=sel.used,
        truncated=sel.truncated,
        limitations=list(git.limitations) if git is not None else [],
        workspace=workspace,
        tier_bytes=sel.tier_bytes,
        tokens=Metric(),
        round=0,
    )


def _select(
    sel: _Selection, root: Path, candidate: RankedFile, store: FingerprintStore, *, excerpts: bool
) -> None:
    rel, signals = candidate.path, list(candidate.signals)
    if len(sel.files) >= sel.max_files:
        sel.exclude(rel, "max_files", signals)
        return
    resolved = resolve_inside(root, root / rel)
    if resolved is None:
        sel.exclude(rel, "missing" if not os.path.lexists(root / rel) else "outside_root", signals)
        return
    reason = ";".join(signals)
    if candidate.lines is not None and excerpts:
        got = store.lines(resolved, candidate.lines)
        if got is not None:
            sha, size = got
            if size > sel.remaining:
                sel.exclude(rel, "budget", signals)
            else:
                sel.add(
                    ContextFile(
                        path=rel,
                        sha256=sha,
                        bytes=size,
                        reason=reason,
                        tier="excerpt",
                        lines=candidate.lines,
                        signals=signals,
                    )
                )
            return
        # Range past the end of the file (or unreadable): handled as the whole file.
    try:
        size = os.stat(resolved).st_size
    except OSError:
        sel.exclude(rel, "unreadable", signals)
        return
    if size <= sel.remaining:  # cheap pre-check: never hash a file that cannot fit
        fp = store.file(rel, resolved)
        if fp is None:
            sel.exclude(rel, "unreadable", signals)
            return
        if fp.size <= sel.remaining:  # the file may have grown after stat
            sel.add(
                ContextFile(
                    path=rel,
                    sha256=fp.sha256,
                    bytes=fp.size,
                    reason=reason,
                    tier="reference",
                    signals=signals,
                )
            )
            return
    if excerpts:
        prefix = store.prefix(resolved, sel.remaining)
        if prefix is not None:
            lines, sha, size = prefix
            sel.add(
                ContextFile(
                    path=rel,
                    sha256=sha,
                    bytes=size,
                    reason=reason,
                    tier="excerpt",
                    lines=lines,
                    signals=signals,
                )
            )
            return
    sel.exclude(rel, "budget", signals)


def _merge_exclusions(
    scanned: list[ExcludedFile],
    rejected: Mapping[str, ExclusionReason],
    selected: list[ExcludedFile],
) -> list[ExcludedFile]:
    """Scan exclusions, then refused intent citations (redacted), then selection exclusions.

    A citation of a path the scan already excluded for the same reason adds the
    ``intent_path`` signal to that entry instead of duplicating it.
    """
    merged = list(scanned)
    index = {e.path: i for i, e in enumerate(merged)}
    for raw, reason in rejected.items():
        path = redact_text(raw)
        at = index.get(path)
        if at is not None and merged[at].reason == reason:
            merged[at] = replace(merged[at], signals=[*merged[at].signals, SIGNAL_INTENT_PATH])
            continue
        index[path] = len(merged)
        merged.append(ExcludedFile(path=path, reason=reason, signals=[SIGNAL_INTENT_PATH]))
    return merged + selected


def extend_context_pack(
    pack: ContextPack,
    request: ContextRequest,
    scan: WorkspaceScan,
    *,
    profile: ContextProfile,
    fingerprints: FingerprintStore,
) -> ContextPack:
    """The next round's pack: previous items kept, approved request items added as
    ``requested``, refused ones recorded in ``excluded`` with their reason (8.2).

    Whether the capability may ask at all and the round limit are the orchestrator's checks
    (they carry their own error codes); here every item passes the same path, secret,
    presence, remaining-budget and file-limit rules as the initial selection. An item
    already delivered with the same scope is skipped (neither added nor refused).
    """
    sel = _Selection(
        budget=pack.budget_bytes,
        max_files=profile.max_files,
        files=list(pack.files),
        excluded=list(pack.excluded),
        tier_bytes=dict(pack.tier_bytes),
        truncated=pack.truncated,
        used=pack.used_bytes,
    )
    sel.tier_bytes.setdefault("requested", 0)
    allowed = "requested" in profile.tiers
    files = frozenset(scan.files)
    scan_reasons = {e.path: e.reason for e in scan.excluded}
    signals = [SIGNAL_REQUESTED]
    for item in request.items:
        rel = item.path.strip()
        while rel.startswith("./"):
            rel = rel[2:]
        if any((f.path, f.lines) == (rel, item.lines) for f in sel.files):
            continue
        reason = _request_rejection(rel, files, scan_reasons) if allowed else "tier_not_allowed"
        if reason is not None:
            sel.exclude(redact_text(item.path), reason, list(signals))
            continue
        if len(sel.files) >= sel.max_files:
            sel.exclude(rel, "max_files", list(signals))
            continue
        added = _requested_item(scan.root, rel, item.lines, fingerprints, sel.remaining)
        if isinstance(added, ContextFile):
            sel.add(added)
        else:
            sel.exclude(rel, added, list(signals))
    return replace(
        pack,
        created_at=utc_now(),
        files=sel.files,
        excluded=sel.excluded,
        used_bytes=sel.used,
        tier_bytes=sel.tier_bytes,
        truncated=sel.truncated,
        status="truncated" if sel.truncated else "complete",
        round=pack.round + 1,
    )


def _request_rejection(
    rel: str, files: frozenset[str], scan_reasons: Mapping[str, str]
) -> ExclusionReason | None:
    """Lexical containment, secret name, presence in the scan (no filesystem access)."""
    parts = rel.split("/")
    if (
        not rel
        or "\x00" in rel
        or "\\" in rel
        or rel.startswith(("/", "~"))
        or _DRIVE.match(rel)
        or ".." in parts
    ):
        return "outside_root"
    if is_secret_name(parts[-1]) or scan_reasons.get(rel) == "secret":
        return "secret"
    if rel in files:
        return None
    if scan_reasons.get(rel) in ("outside_root", "symlinked_dir"):
        return "outside_root"
    return "missing"


def _requested_item(
    root: Path, rel: str, lines: LineRange | None, store: FingerprintStore, remaining: int
) -> ContextFile | ExclusionReason:
    resolved = resolve_inside(root, root / rel)
    if resolved is None:
        return "missing" if not os.path.lexists(root / rel) else "outside_root"
    if lines is not None:
        got = store.lines(resolved, lines)
        if got is None:
            return "missing"  # range past the last line (or file unreadable)
        sha, size = got
    else:
        try:
            if os.stat(resolved).st_size > remaining:
                return "budget"
        except OSError:
            return "unreadable"
        fp = store.file(rel, resolved)
        if fp is None:
            return "unreadable"
        sha, size = fp.sha256, fp.size
    if size > remaining:
        return "budget"
    return ContextFile(
        path=rel,
        sha256=sha,
        bytes=size,
        reason=SIGNAL_REQUESTED,
        tier="requested",
        lines=lines,
        signals=[SIGNAL_REQUESTED],
    )
