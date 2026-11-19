"""Progressive context routing (Onda 08): L1 metadata → L2 specialist → L3 deep.

The pipeline is deterministic and offline: a task description is scored
against catalog metadata (already-loaded L1), the best specialists become
L2 selections, and only their *relevant* resources escalate to L3 retrieval
refs — bounded by an explicit byte budget. Adding Forges to the machine
must not inflate per-task context (§14.7): L1 cost grows with catalog
size, L2/L3 stay budget-capped.

Cycle 16.1 (§8.3–§8.4) — the plan also carries *selection evidence*: which
metadata terms matched each forge, the score of every candidate, a closed
``confidence`` and an explicit ``disambiguation``. A tie at the top is
``ambiguous`` — the candidates are reported, never a silent pick (routing
determinism: ties resolve by ``forge_id`` for *ordering*, but the plan
must say so instead of presenting an arbitrary winner). No field depends
on install order, discovery order or timestamps.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .resources import ResourceRef, ResourceResolver

STOP = {
    "a",
    "o",
    "e",
    "de",
    "da",
    "do",
    "em",
    "um",
    "uma",
    "para",
    "com",
    "the",
    "to",
    "of",
    "in",
    "and",
    "or",
    "for",
    "on",
    "an",
    "is",
}
DEFAULT_L2_BUDGET = 16_000
DEFAULT_L3_BUDGET = 8_000
MAX_L2_FORGES = 3

SELECTION_STATES = ("selected", "ambiguous", "no_match")
CONFIDENCE_LEVELS = ("high", "medium", "low")


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
    # --- §8.3 selection evidence (additive — older readers ignore it) ---
    selection: str = "no_match"  # SELECTION_STATES
    confidence: str | None = None  # CONFIDENCE_LEVELS, None when no_match
    evidence: dict[str, list[str]] = field(default_factory=dict)  # forge → matched terms
    forge_scores: dict[str, int] = field(default_factory=dict)
    # runner-ups + why-not, deterministic order
    alternatives: list[dict[str, Any]] = field(default_factory=list)
    disambiguation: str = ""


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


def _matched_terms(terms: set[str], ref: ResourceRef) -> set[str]:
    """The scoring terms that actually matched this ref's metadata — the
    deterministic evidence behind the score (§8.3)."""
    hay = " ".join(
        [
            ref.entry.id,
            ref.entry.kind,
            ref.entry.description or "",
            " ".join(ref.entry.tags or []),
            ref.entry.domain or "",
        ]
    ).lower()
    return {t for t in terms if t in hay}


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
    A tie at the top makes the plan ``ambiguous``: candidates are still
    reported (with the deterministic order recorded in ``disambiguation``)
    but no arbitrary winner is named — §8.4 forbids first-install wins.
    """
    if level3_budget < 0:
        raise ValueError(f"level3_budget must be >= 0, got {level3_budget}")
    terms = _terms(task)
    l1 = resolver.list()  # metadata-only scan — the L1 contract
    forge_scores: dict[str, int] = {}
    forge_terms: dict[str, set[str]] = {}
    ref_scores: list[tuple[int, ResourceRef]] = []
    for ref in l1:
        if ref.entry.availability != "available":
            continue
        s = _score(terms, ref)
        if s <= 0:
            continue
        ref_scores.append((s, ref))
        forge_scores[ref.forge_id] = forge_scores.get(ref.forge_id, 0) + s
        forge_terms.setdefault(ref.forge_id, set()).update(_matched_terms(terms, ref))

    ranked = sorted(forge_scores.items(), key=lambda kv: (-kv[1], kv[0]))[:MAX_L2_FORGES]
    # §8.3/§8.4 — a tie at the top is declared ambiguous, never an arbitrary
    # first pick. The deterministic (score, forge_id) order still decides
    # which candidates appear, and the plan says that is all it is.
    tied_top = [fid for fid, s in ranked if ranked and s == ranked[0][1]]
    ambiguous = len(tied_top) > 1
    if not ranked:
        selection = "no_match"
        primary = None
        aux: list[str] = []
        confidence = None
        disambiguation = "no catalog metadata matched the task terms"
    elif ambiguous:
        selection = "ambiguous"
        primary = None
        aux = [fid for fid, _ in ranked]
        confidence = "low"
        disambiguation = (
            f"{len(tied_top)} forges tie at score {ranked[0][1]} "
            f"({', '.join(tied_top)}) — declared ambiguous; listed in "
            "deterministic forge_id order, never install order. "
            "Disambiguate with more specific terms (platform, service, "
            "artifact type) or an explicit target."
        )
    else:
        selection = "selected"
        primary = ranked[0][0]
        aux = [fid for fid, _ in ranked[1:]]
        second = ranked[1][1] if len(ranked) > 1 else 0
        confidence = "high" if ranked[0][1] >= max(2, 2 * second) else "medium"
        disambiguation = (
            f"{primary} outscored the next candidate {ranked[0][1]}:{second} on metadata terms"
            if len(ranked) > 1
            else f"{primary} is the only forge with matching metadata"
        )

    # §8.4 — ambiguity is a question back to the caller, not a selection:
    # nothing escalates to L3 until the tie is disambiguated.
    selected = set() if ambiguous else {fid for fid, _ in ranked}
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

    alternatives = [
        {
            "forge_id": fid,
            "score": score,
            "reason": (
                "tied at the top — ambiguity declared, no arbitrary winner"
                if ambiguous and score == ranked[0][1]
                else "lower metadata score than the selected forge"
            ),
        }
        for fid, score in ranked
        if fid != primary
    ]

    return ContextPlan(
        task=task,
        level1_forges=len({r.forge_id for r in l1}),
        level2_forge=primary,
        level2_aux=aux,
        level3_refs=l3,
        budget_bytes=level3_budget,
        est_level3_bytes=est,
        selection=selection,
        confidence=confidence,
        evidence={fid: sorted(ts) for fid, ts in sorted(forge_terms.items())},
        forge_scores=dict(sorted(forge_scores.items())),
        alternatives=alternatives,
        disambiguation=disambiguation,
        metrics={
            "l1_refs_scanned": len(l1),
            "l1_forge_count": len({r.forge_id for r in l1}),
            "l2_selected": len(ranked),
            "l3_refs": len(l3),
            # §8.7 — discovery is a metadata scan; nothing was read to
            # produce this plan. The counters make that visible instead
            # of implying a retrieval that never happened.
            "discovered_refs": len(l1),
            "retrieved_refs": 0,
            "unavailable_skipped": sum(1 for r in l1 if r.entry.availability != "available"),
        },
    )
