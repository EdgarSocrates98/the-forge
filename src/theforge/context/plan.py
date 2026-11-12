"""Progressive context routing (Onda 08): L1 metadata → L2 specialist → L3 deep.

The pipeline is deterministic and offline: a task description is scored
against catalog metadata (already-loaded L1), the best specialists become
L2 selections, and only their *relevant* resources escalate to L3 retrieval
refs — bounded by an explicit byte budget. Adding Forges to the machine
must not inflate per-task context (§14.7): L1 cost grows with catalog
size, L2/L3 stay budget-capped.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .resources import ResourceRef, ResourceResolver

STOP = {
    "a", "o", "e", "de", "da", "do", "em", "um", "uma", "para", "com",
    "the", "to", "of", "in", "and", "or", "for", "on", "an", "is",
}
DEFAULT_L2_BUDGET = 16_000
DEFAULT_L3_BUDGET = 8_000
MAX_L2_FORGES = 3


def _terms(text: str) -> set[str]:
    return {
        t.strip(".,;:!?()[]\"'").lower()
        for t in text.split()
        if len(t) > 2 and t.lower() not in STOP
    }


@dataclass(frozen=True, kw_only=True)
class ContextPlan:
    """forge/ContextPlan/v1 — deterministic progressive-routing output."""

    task: str
    level1_forges: int  # catalogs scanned (metadata only — no bodies read)
    level2_forge: str | None  # primary specialist
    level2_aux: list[str] = field(default_factory=list)
    level3_refs: list[str] = field(default_factory=list)
    budget_bytes: int = DEFAULT_L3_BUDGET
    est_level3_bytes: int = 0
    metrics: dict[str, int] = field(default_factory=dict)


def _score(terms: set[str], ref: ResourceRef) -> int:
    hay = " ".join(
        [
            ref.entry.id,
            ref.entry.kind,
            ref.entry.description or "",
            " ".join(ref.entry.tags or []),
            ref.entry.domain or "",
        ]
    ).lower()
    return sum(1 for t in terms if t in hay)


def plan_context(
    task: str,
    resolver: ResourceResolver,
    *,
    level3_budget: int = DEFAULT_L3_BUDGET,
    max_l3_refs: int = 12,
) -> ContextPlan:
    """Route ``task`` through L1→L2→L3 without loading resource bodies.

    Scoring is term-overlap on catalog metadata — deterministic, no
    embeddings (§10 contract). L2 picks the best-scoring forge plus
    auxiliaries with a non-zero score; L3 lists bounded retrieval refs.
    """
    terms = _terms(task)
    l1 = resolver.list()  # metadata-only scan — the L1 contract
    forge_scores: dict[str, int] = {}
    ref_scores: list[tuple[int, ResourceRef]] = []
    for ref in l1:
        if ref.entry.availability != "available":
            continue
        s = _score(terms, ref)
        if s <= 0:
            continue
        ref_scores.append((s, ref))
        forge_scores[ref.forge_id] = forge_scores.get(ref.forge_id, 0) + s

    ranked = sorted(
        forge_scores.items(), key=lambda kv: (-kv[1], kv[0])
    )[:MAX_L2_FORGES]
    primary = ranked[0][0] if ranked else None
    aux = [fid for fid, _ in ranked[1:]]

    selected = {fid for fid, _ in ranked}
    est = 0
    l3: list[str] = []
    for _s, ref in sorted(ref_scores, key=lambda rs: (-rs[0], rs[1].identity)):
        if len(l3) >= max_l3_refs:
            break
        if ref.forge_id not in selected:
            continue  # L3 only escalates resources of selected L2 forges
        # L3 stays inside the budget: size estimate via stat() — bodies
        # are NOT read here, only referenced for bounded retrieval.
        size = 0
        if ref.path is not None:
            try:
                size = ref.path.stat().st_size
            except OSError:
                size = 0
        if est + min(size, level3_budget) > level3_budget:
            continue
        l3.append(ref.identity)
        est += min(size, level3_budget)

    return ContextPlan(
        task=task,
        level1_forges=len({r.forge_id for r in l1}),
        level2_forge=primary,
        level2_aux=aux,
        level3_refs=l3,
        budget_bytes=level3_budget,
        est_level3_bytes=est,
        metrics={
            "l1_refs_scanned": len(l1),
            "l1_forge_count": len({r.forge_id for r in l1}),
            "l2_selected": len(ranked),
            "l3_refs": len(l3),
            "unavailable_skipped": sum(
                1 for r in l1 if r.entry.availability != "available"
            ),
        },
    )
