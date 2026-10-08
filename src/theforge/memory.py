"""Engineering Memory store: provenance-bound knowledge under ``.forge/memory/``
(Cycle 5, Wave B).

Local-first, deterministic, stdlib-only (§16-17): entries live in
``entries.jsonl`` — append-only, bounded, written after ``security.redact`` —
and summaries in ``summaries.json``. There is no vector database and no
semantic index: retrieval is structured lookup over declared fields
(§18-19); semantic retrieval may be layered on top later as an optional
fallback only.

The store enforces what the contract cannot:

- deduplication by content-derived id (re-recording a claim reaffirms it);
- ``stale``/``superseded`` are *transitions* written through this module —
  supersession links forward and never deletes the source;
- cross-project export/import only moves ``portable``/``organization``
  entries (§112-115): a project/workspace-scoped entry offered for import is
  refused, by construction;
- every write/read problem degrades to a note, never a failed run — like the
  intel and observations stores.
"""

import contextlib
import json
import os
import tempfile
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any, Final

from theforge.contracts.base import ContractError, from_dict, to_dict
from theforge.contracts.canonical import sha256_hex, utc_now
from theforge.contracts.memory import (
    CrossProjectScopes,
    EngineeringMemoryEntry,
    FailurePattern,
    MemoryEpistemic,
    MemoryKind,
    MemoryPack,
    MemorySummary,
)
from theforge.contracts.plan import DecisionRecord, PlanResult
from theforge.contracts.verification import VerificationResult
from theforge.meta import PRODUCER
from theforge.runs.store import RunStore
from theforge.security.redact import redact
from theforge.state import FORGE_DIR_NAME

__all__ = [
    "ENTRIES_FILE",
    "MEMORY_DIR",
    "SUMMARIES_FILE",
    "MemoryQuery",
    "export_entries",
    "failure_patterns",
    "import_entries",
    "learn_from_run",
    "load_entries",
    "load_summaries",
    "mark_stale",
    "memory_entry_id",
    "memory_pack",
    "record_entry",
    "summarize",
    "supersede",
]

MEMORY_DIR = "memory"
ENTRIES_FILE = "entries.jsonl"
SUMMARIES_FILE = "summaries.json"
# Bounded stores: memory that cannot be trusted should be dropped explicitly,
# not grown without limit — same compaction rule as the observations store.
MAX_ENTRIES_BYTES: Final = 1 << 20
MAX_SUMMARIES: Final = 256
# Retrieval budget: a pack is bounded by count *and* bytes so a query can
# never dump the whole memory into a context assembly (§21).
DEFAULT_PACK_ENTRIES: Final = 32
MAX_PACK_ENTRIES: Final = 128
DEFAULT_PACK_BYTES: Final = 32 * 1024
MAX_PACK_BYTES: Final = 256 * 1024

_UNSET: Final = object()


def _dir(root: Path) -> Path:
    return root / FORGE_DIR_NAME / MEMORY_DIR


def _entries_path(root: Path) -> Path:
    return _dir(root) / ENTRIES_FILE


def _summaries_path(root: Path) -> Path:
    return _dir(root) / SUMMARIES_FILE


def memory_entry_id(entry: EngineeringMemoryEntry) -> str:
    """Content-derived id: ``sha256(kind|scope|subject|claim|producer.id)``.

    The id is a pure function of the claim — the same knowledge recorded twice
    is the same memory. Provenance deliberately does not participate: two runs
    confirming the same fact reaffirm one entry.
    """
    return sha256_hex(
        f"{entry.kind}|{entry.scope}|{entry.subject}|{entry.claim}|{entry.producer.id}".encode()
    )


# --- store ------------------------------------------------------------------------------------


def load_entries(root: Path) -> tuple[list[EngineeringMemoryEntry], str | None]:
    """Every persisted entry in file order; corrupt lines are skipped, not fatal.

    Returns ``(entries, warning)``: one poisoned line never erases honest
    memory — it is skipped and counted in the warning.
    """
    path = _entries_path(root)
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return [], None
    except OSError as exc:
        return [], f"memory: cannot read {path}: {exc}"
    entries: list[EngineeringMemoryEntry] = []
    skipped = 0
    for line in raw.decode("utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            entries.append(from_dict(EngineeringMemoryEntry, json.loads(line), strict=True))
        except (ValueError, ContractError):
            skipped += 1
    warning = (
        f"memory: skipped {skipped} corrupt entr{'y' if skipped == 1 else 'ies'}"
        if skipped
        else None
    )
    return entries, warning


def _atomic_write(path: Path, text: str) -> str | None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.stem}-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
            os.replace(tmp, path)
        except OSError:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise
    except OSError as exc:
        return f"memory: {path.name} not written: {exc}"
    return None


def _write_entries(root: Path, entries: Sequence[EngineeringMemoryEntry]) -> str | None:
    lines = [json.dumps(redact(to_dict(e)), sort_keys=True, ensure_ascii=False) for e in entries]
    if any(redact(to_dict(e)) != to_dict(e) for e in entries):
        return "memory: entries not written (redaction would alter them)"
    text = "".join(line + "\n" for line in lines)
    # Compaction: when the file would exceed the bound, keep the newest
    # entries that fit — oldest dropped first, deterministically.
    while len(text.encode("utf-8")) > MAX_ENTRIES_BYTES and len(lines) > 1:
        lines = lines[len(lines) // 2 :]
        text = "".join(line + "\n" for line in lines)
    return _atomic_write(_entries_path(root), text)


def record_entry(root: Path, entry: EngineeringMemoryEntry) -> str | None:
    """Append ``entry`` unless its id is already recorded; returns a warning.

    Re-recording the same claim is a reaffirmation — no second line. The
    entry's own contract rules (provenance, epistemic shape) are enforced by
    construction.
    """
    try:
        entries, warning = load_entries(root)
        if any(existing.id == entry.id for existing in entries):
            return warning  # same content-derived id: reaffirmed, not duplicated
        return _write_entries(root, [*entries, entry]) or warning
    except (OSError, ContractError, ValueError) as exc:
        return f"memory: entry not recorded: {exc}"


def _update_entries(
    root: Path, mutate: Callable[[EngineeringMemoryEntry], EngineeringMemoryEntry]
) -> tuple[int, str | None]:
    """Rewrite ``entries.jsonl`` applying ``mutate`` per entry; returns
    ``(changed, warning)``. History is preserved: only the fields the
    transition owns change, ids never do."""
    entries, warning = load_entries(root)
    changed = 0
    updated: list[EngineeringMemoryEntry] = []
    for entry in entries:
        new = mutate(entry)
        changed += new is not entry
        updated.append(new)
    if not changed:
        return 0, warning
    return changed, _write_entries(root, updated) or warning


def mark_stale(root: Path, entry_ids: Iterable[str], reason: str) -> tuple[int, str | None]:
    """Transition entries to ``stale`` with an explicit reason.

    Only entries with provenance can go stale — an ``unresolved`` orphan has
    no claim strong enough to expire; those are skipped and counted in the
    note (stale means "was believed, now outdated", not "never sourced").
    """
    wanted = set(entry_ids)

    def _mutate(entry: EngineeringMemoryEntry) -> EngineeringMemoryEntry:
        if entry.id not in wanted or entry.epistemic in ("stale", "superseded"):
            return entry
        if not (
            entry.source_refs or entry.evidence_refs or entry.decision_refs or entry.artifact_refs
        ):
            return entry  # cannot stale an orphan — it was never sourced
        return replace(entry, epistemic="stale", stale_reason=reason)

    changed, warning = _update_entries(root, _mutate)
    skipped = len(wanted) - changed if len(wanted) > changed else 0
    note = None
    if skipped > 0 and changed == 0:
        note = "memory: nothing staled (ids unknown, terminal, or unprovenanced)"
    return changed, note or warning


def supersede(root: Path, old_id: str, new: EngineeringMemoryEntry) -> tuple[bool, str | None]:
    """Record ``new`` and link ``old`` forward (``superseded_by``/``supersedes``).

    The source entry is kept — supersession is a transition, not deletion
    (§15). ``new`` must carry ``supersedes=old_id``; the old entry is marked
    ``superseded`` only if it can satisfy that epistemic's provenance rule.
    """
    entries, warning = load_entries(root)
    old = next((e for e in entries if e.id == old_id), None)
    if old is None:
        return False, f"memory: cannot supersede unknown entry {old_id[:12]}…"
    if new.supersedes != old_id:
        return False, "memory: superseding entry must carry supersedes=<old id>"
    if new.epistemic == "superseded":
        return False, "memory: a new entry cannot be born superseded"
    if any(e.id == new.id for e in entries):
        return False, "memory: superseding entry already recorded"

    marked: list[EngineeringMemoryEntry] = []
    for entry in entries:
        if entry.id == old_id:
            marked.append(replace(entry, epistemic="superseded", superseded_by=new.id))
        else:
            marked.append(entry)
    return True, _write_entries(root, [*marked, new]) or warning


# --- retrieval ---------------------------------------------------------------------------------


class MemoryQuery:
    """Structured retrieval filters (§18-19): all declared fields are exact
    matches — retrieval is deterministic-first, never a similarity search."""

    __slots__ = (
        "kind",
        "scope",
        "provider",
        "capability",
        "task_family",
        "surface_fingerprint",
        "subject",
        "tag",
        "epistemic",
        "include_terminal",
    )

    def __init__(
        self,
        *,
        kind: MemoryKind | None = None,
        scope: str | None = None,
        provider: str | None = None,
        capability: str | None = None,
        task_family: str | None = None,
        surface_fingerprint: str | None = None,
        subject: str | None = None,
        tag: str | None = None,
        epistemic: MemoryEpistemic | None = None,
        include_terminal: bool = False,
    ) -> None:
        self.kind = kind
        self.scope = scope
        self.provider = provider
        self.capability = capability
        self.task_family = task_family
        self.surface_fingerprint = surface_fingerprint
        self.subject = subject
        self.tag = tag
        self.epistemic = epistemic
        self.include_terminal = include_terminal

    def echo(self) -> dict[str, str]:
        """The filters actually applied — echoed in the pack so the result is
        replayable (``query`` keys are always strings)."""
        out: dict[str, str] = {}
        for name in self.__slots__:
            value = getattr(self, name)
            if value is not None and value is not False and value != "":
                out[name] = str(value)
        return out

    def matches(self, entry: EngineeringMemoryEntry) -> bool:
        if not self.include_terminal and entry.epistemic in ("stale", "superseded"):
            return False
        for name in (
            "kind",
            "scope",
            "provider",
            "capability",
            "task_family",
            "surface_fingerprint",
            "subject",
            "epistemic",
        ):
            wanted = getattr(self, name)
            if wanted is not None and getattr(entry, name) != wanted:
                return False
        return self.tag is None or self.tag in entry.tags


def memory_pack(
    root: Path,
    query: MemoryQuery | None = None,
    *,
    max_entries: int = DEFAULT_PACK_ENTRIES,
    max_bytes: int = DEFAULT_PACK_BYTES,
) -> tuple[MemoryPack, str | None]:
    """A bounded, deterministic retrieval result (§21).

    Entries are ordered by ``(created_at, id)`` — the same store and filters
    always produce the same pack. ``truncated``/``limitations`` never hide a
    cut-off.
    """
    query = query if query is not None else MemoryQuery()
    entries, warning = load_entries(root)
    matched = sorted((e for e in entries if query.matches(e)), key=lambda e: (e.created_at, e.id))
    max_entries = max(1, min(max_entries, MAX_PACK_ENTRIES))
    max_bytes = max(1024, min(max_bytes, MAX_PACK_BYTES))
    delivered: list[EngineeringMemoryEntry] = []
    used = 0
    for entry in matched:
        size = len(json.dumps(to_dict(entry), sort_keys=True).encode("utf-8"))
        if len(delivered) >= max_entries or (delivered and used + size > max_bytes):
            break
        delivered.append(entry)
        used += size
    limitations: list[str] = []
    truncated = len(delivered) < len(matched)
    if truncated:
        limitations.append(
            f"pack truncated: {len(matched) - len(delivered)} matching entries withheld by budget"
        )
    if warning is not None:
        limitations.append(warning)
    pack = MemoryPack(
        producer=PRODUCER,
        created_at=utc_now(),
        query=query.echo(),
        entries=delivered,
        total_matches=len(matched),
        delivered_bytes=used,
        truncated=truncated,
        limitations=limitations,
    )
    return pack, warning


# --- distillation (Wave T) ----------------------------------------------------------------------


def load_summaries(root: Path) -> tuple[list[MemorySummary], str | None]:
    path = _summaries_path(root)
    try:
        data = json.loads(path.read_bytes().decode("utf-8"))
    except FileNotFoundError:
        return [], None
    except (OSError, ValueError) as exc:
        return [], f"memory: cannot read {path}: {exc}"
    if not isinstance(data, list):
        return [], f"memory: malformed summaries file {path}"
    summaries: list[MemorySummary] = []
    skipped = 0
    for item in data:
        try:
            summaries.append(from_dict(MemorySummary, item, strict=True))
        except (ValueError, ContractError):
            skipped += 1
    warning = f"memory: skipped {skipped} corrupt summaries" if skipped else None
    return summaries, warning


def summarize(
    root: Path,
    *,
    subject: str,
    summary: str,
    source_ids: Sequence[str],
    coverage: str = "",
) -> tuple[MemorySummary | None, str | None]:
    """Distill ``source_ids`` into a ``MemorySummary`` — an index over sources,
    never a replacement (§116-117): sources are verified to exist and are
    never deleted."""
    entries, warning = load_entries(root)
    known = {e.id for e in entries}
    missing = [sid for sid in source_ids if sid not in known]
    if missing:
        return None, (
            f"memory: summary not written — {len(missing)} source id(s) are not recorded entries"
        )
    doc = MemorySummary(
        producer=PRODUCER,
        created_at=utc_now(),
        id=sha256_hex(f"summary|{subject}|{sorted(source_ids)}".encode()),
        subject=subject,
        summary=summary,
        source_ids=sorted(set(source_ids)),
        coverage=coverage or f"{len(set(source_ids))} entries",
        generated_at=utc_now(),
    )
    summaries, load_warning = load_summaries(root)
    warning = warning or load_warning
    if any(s.id == doc.id for s in summaries):
        return doc, warning  # same distillation already recorded
    data = [to_dict(s) for s in summaries] + [to_dict(doc)]
    data = data[-MAX_SUMMARIES:]
    problem = _atomic_write(
        _summaries_path(root), json.dumps(data, indent=2, sort_keys=True) + "\n"
    )
    return (None if problem else doc), problem or warning


# --- cross-project boundary (Wave S) -------------------------------------------------------------


def export_entries(root: Path) -> tuple[list[EngineeringMemoryEntry], str | None]:
    """Entries allowed to leave the project: ``portable``/``organization``
    scopes only (§113). The contract already demands origin classification +
    redaction for those scopes; the filter is the second fence."""
    entries, warning = load_entries(root)
    return [e for e in entries if e.scope in CrossProjectScopes], warning


def import_entries(root: Path, entries: Iterable[Mapping[str, Any]]) -> tuple[int, str | None]:
    """Import memory from another project. ``project``/``workspace``-scoped
    entries are refused outright — cross-project isolation is a default-deny
    boundary (§112, §144). Returns ``(imported, warning)``."""
    existing, warning = load_entries(root)
    known = {e.id for e in existing}
    imported = 0
    refused = 0
    out = list(existing)
    for raw in entries:
        try:
            entry = from_dict(EngineeringMemoryEntry, raw, strict=True)
        except (ContractError, ValueError):
            refused += 1
            continue
        if entry.scope not in CrossProjectScopes:
            refused += 1
            continue
        if entry.id in known:
            continue
        out.append(entry)
        known.add(entry.id)
        imported += 1
    notes: list[str] = []
    if warning:
        notes.append(warning)
    if refused:
        notes.append(
            f"memory: refused {refused} entr{'y' if refused == 1 else 'ies'} "
            "(malformed or project/workspace scope)"
        )
    if not imported and not refused:
        return 0, warning
    return imported, (_write_entries(root, out) if imported else None) or "; ".join(notes)


# --- learning from the run store (evidence-bound, §7-13) -----------------------------------------


def _bounded(text: str, limit: int = 240) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _entry(
    *,
    kind: MemoryKind,
    epistemic: MemoryEpistemic,
    subject: str,
    claim: str,
    run_id: str,
    workspace: str,
    provider: str | None = None,
    capability: str | None = None,
    task_family: str | None = None,
    evidence_refs: Sequence[str] = (),
    decision_refs: Sequence[str] = (),
    tags: Sequence[str] = (),
) -> EngineeringMemoryEntry:
    stub = EngineeringMemoryEntry(
        producer=PRODUCER,
        created_at=utc_now(),
        id="0" * 64,
        kind=kind,
        scope="project",
        workspace=workspace,
        subject=_bounded(subject),
        claim=_bounded(claim),
        epistemic=epistemic,
        provider=provider,
        capability=capability,
        task_family=task_family,
        source_refs=[f"run:{run_id}"],
        evidence_refs=list(evidence_refs),
        decision_refs=list(decision_refs),
        tags=list(tags)[:16],
    )
    return replace(stub, id=memory_entry_id(stub))


def learn_from_run(root: Path, store: RunStore, run_id: str) -> tuple[int, list[str]]:
    """Distill one run's persisted artifacts into memory entries (deterministic).

    Sources read (all optional, all on disk): ``decision`` → ``decision``
    entry; ``verification`` → ``resolution`` (forge/independent verdict
    passed ⇒ ``confirmed``) or ``failure``; ``plan-result`` node failures →
    ``failure`` entries keyed by provider/capability. Provider output text is
    never stored as fact — every entry cites its run, and only verifier
    verdicts produce ``confirmed``.
    """
    workspace = str(root.resolve())
    notes: list[str] = []
    made: list[EngineeringMemoryEntry] = []

    decision = store.read_optional(run_id, "decision")
    if decision is not None:
        record = from_dict(DecisionRecord, decision, strict=True)
        made.append(
            _entry(
                kind="decision",
                epistemic="observed",
                subject=_bounded(record.question, 120),
                claim=(
                    f"debate chose {record.chosen} (confidence {record.confidence})"
                    if record.chosen != "unresolved"
                    else "debate ended unresolved"
                ),
                run_id=run_id,
                workspace=workspace,
                decision_refs=[f"run:{run_id}:decision"],
                tags=["debate"],
            )
        )

    verification = store.read_optional(run_id, "verification")
    plan_result = store.read_optional(run_id, "plan-result")
    task = store.read_optional(run_id, "task")
    task_family = (task or {}).get("task_family")
    if verification is not None:
        ver = from_dict(VerificationResult, verification, strict=True)
        passed = [c.status for c in (ver.forge, ver.independent)]
        if "passed" in passed:
            made.append(
                _entry(
                    kind="resolution",
                    epistemic="confirmed",
                    subject=f"run {run_id} verified",
                    claim="result passed forge/independent verification",
                    run_id=run_id,
                    workspace=workspace,
                    task_family=task_family,
                    evidence_refs=[f"run:{run_id}:verification"],
                    tags=["verification"],
                )
            )
        elif "failed" in passed:
            made.append(
                _entry(
                    kind="failure",
                    epistemic="observed",
                    subject=f"run {run_id} failed verification",
                    claim="forge/independent verification reported failure",
                    run_id=run_id,
                    workspace=workspace,
                    task_family=task_family,
                    evidence_refs=[f"run:{run_id}:verification"],
                    tags=["verification", "failure"],
                )
            )

    if plan_result is not None:
        plan_outcome = from_dict(PlanResult, plan_result, strict=True)
        # Provider/capability of each failed node come from the persisted plan.
        plan = store.read_optional(run_id, "plan")
        node_meta = {
            n["id"]: (n.get("provider"), n.get("capability"))
            for n in (plan or {}).get("nodes", [])
            if isinstance(n, dict)
        }
        for outcome in plan_outcome.nodes:
            if outcome.status in ("ok", "partial", "skipped"):
                continue
            provider, capability = node_meta.get(outcome.node, (None, None))
            code = outcome.error.code if outcome.error else outcome.status
            made.append(
                _entry(
                    kind="failure",
                    epistemic="observed",
                    subject=f"{outcome.node}: {code}",
                    claim=(
                        f"node {outcome.node} ended {outcome.status}"
                        + (f" ({outcome.error.detail})" if outcome.error else "")
                    ),
                    run_id=run_id,
                    workspace=workspace,
                    provider=provider,
                    capability=capability,
                    task_family=task_family,
                    evidence_refs=[f"run:{run_id}:plan-result"],
                    tags=["failure", code],
                )
            )

    count = 0
    for entry in made:
        problem = record_entry(root, entry)
        if problem is None:
            count += 1
        else:
            notes.append(problem)
    return count, notes


def failure_patterns(root: Path) -> tuple[list[FailurePattern], str | None]:
    """Aggregate ``failure``-kind entries into ``FailurePattern``s (Wave Y).

    The key is ``(error tag, provider, capability, surface, task_family)`` —
    a pattern is an observation rollup, never a promoted rule.
    """
    entries, warning = load_entries(root)
    groups: dict[
        tuple[str, str | None, str | None, str | None, str | None], list[EngineeringMemoryEntry]
    ] = {}
    for entry in entries:
        if entry.kind != "failure" or entry.epistemic in ("stale", "superseded"):
            continue
        family = next(
            (t for t in entry.tags if t not in ("failure", "verification", "debate")),
            entry.subject.split(":")[-1].strip() or "unknown",
        )
        key = (
            family,
            entry.provider,
            entry.capability,
            entry.surface_fingerprint,
            entry.task_family,
        )
        groups.setdefault(key, []).append(entry)
    patterns: list[FailurePattern] = []
    for (family, provider, capability, surface, family_name), group in sorted(
        groups.items(), key=lambda item: (item[0][0], item[0][1] or "", item[0][2] or "")
    ):
        seen = sorted(e.created_at for e in group)
        resolved_by = sorted({ref for e in group for ref in e.decision_refs})
        patterns.append(
            FailurePattern(
                producer=PRODUCER,
                created_at=utc_now(),
                id=sha256_hex(
                    "|".join(
                        str(part) for part in (family, provider, capability, surface, family_name)
                    ).encode()
                ),
                error_family=family,
                provider=provider,
                capability=capability,
                surface_fingerprint=surface,
                task_family=family_name,
                occurrences=len(group),
                first_seen=seen[0],
                last_seen=seen[-1],
                resolved_by=resolved_by,
                limitations=["aggregated from recorded failure memory; observation only"],
            )
        )
    return patterns, warning
