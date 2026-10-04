"""HandoffBuilder: the structured handoff a plan node receives from its declared inputs.

Only the valid results of the nodes in ``target.inputs`` contribute (4.3). Each source
yields its decision (outcome), findings, evidence (original epistemic status) and
artifact references (path + sha256): never file content nor the provider's full output
(4.1, 4.2). Items follow a deterministic priority and are cut, as a prefix, when the
item or canonical-byte limit is reached (4.4). Every item is redacted before it is
measured, so the returned handoff is already the redacted one that is delivered and
persisted (4.5).
"""

from collections.abc import Callable, Sequence
from typing import Any, Final

from theforge.contracts.base import from_dict, to_dict
from theforge.contracts.canonical import canonical_json, utc_now
from theforge.contracts.handoff import Handoff, HandoffItem, HandoffOrigin
from theforge.contracts.integrity import validate_handoff
from theforge.contracts.plan import PlanNode
from theforge.contracts.result import Evidence, Finding
from theforge.contracts.types import MAX_CLAIM_CHARS, MAX_HANDOFF_BYTES, MAX_HANDOFF_ITEMS
from theforge.meta import PRODUCER
from theforge.planning.execution import SourceResult
from theforge.security.redact import REDACTED, redact, redact_text

__all__ = ["TRUNCATION_MARKER", "build_handoff"]

TRUNCATION_MARKER: Final = "…[truncated]"
# Node statuses whose result may be handed off (a result exists only for these).
_VALID_STATUSES: Final = frozenset({"ok", "partial"})
_SEVERITY_RANK: Final = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
_EPISTEMIC_RANK: Final = {"confirmed": 0, "observed": 1, "inferred": 2, "proposed": 3,
                          "unresolved": 4}
_MAX_CLAIM_ATTEMPTS: Final = 8


def build_handoff(plan_run: str, target: PlanNode, sources: Sequence[SourceResult], *,
                  created_at: str | None = None) -> Handoff | None:
    """Handoff for ``target`` from its declared inputs; ``None`` if it declares none.

    ``sources`` may hold results of any node: only those named in ``target.inputs``
    with a valid status are used, in the order of ``inputs`` (the sequence order is
    irrelevant). A declared input without a valid source is recorded as the limitation
    ``handoff-input-missing: <node>``. Two sources for the same node are a caller bug.
    """
    if not target.inputs:
        return None
    by_node: dict[str, SourceResult] = {}
    for src in sources:
        if src.node in by_node:
            raise ValueError(f"handoff for {target.id!r}: duplicate source for node {src.node!r}")
        by_node[src.node] = src

    limitations: list[str] = []
    candidates: list[HandoffItem] = []
    for node in target.inputs:
        found = by_node.get(node)
        if found is None or found.status not in _VALID_STATUSES:
            limitations.append(f"handoff-input-missing: {node}")
            continue
        candidates.extend(_redacted(item) for item in _source_items(plan_run, found))

    stamp = created_at if created_at is not None else utc_now()

    def make(items: list[HandoffItem], dropped: int) -> Handoff:
        notes = list(limitations)
        if dropped:
            notes.append(f"handoff-truncated: dropped {dropped} items")
        return Handoff(producer=PRODUCER, created_at=stamp, plan_run=plan_run,
                       target_node=target.id, items=items, truncated=dropped > 0,
                       dropped=dropped, limitations=notes)

    kept = _prefix_within_limits(candidates, make)
    handoff = make(kept, len(candidates) - len(kept))
    # Final pass over the whole contract (top-level strings included) and strict reread:
    # the items are already redacted, so this is the delivered == persisted fixed point.
    handoff = from_dict(Handoff, redact(to_dict(handoff)), strict=True)
    validate_handoff(handoff)
    return handoff


def _source_items(plan_run: str, src: SourceResult) -> list[HandoffItem]:
    """Items of one source in priority order: decision, findings, evidence, artifacts."""
    origin = HandoffOrigin(plan_run=plan_run, node=src.node, run_id=src.run_id,
                           provider=src.provider)
    res = src.result
    items = [HandoffItem(
        kind="decision", id="outcome", origin=origin, epistemic="observed", subject=src.node,
        claim=_claim(f"status={src.status} capability={src.capability} action={src.action}"),
    )]

    findings = sorted(res.findings, key=lambda f: (_SEVERITY_RANK[f.severity], f.id))
    items.extend(_finding_item(origin, f) for f in findings)

    position: dict[str, int] = {}  # first reference by a finding, in finding priority
    for f in findings:
        for eid in f.evidence_ids:
            position.setdefault(eid, len(position))
    referenced = sorted((e for e in res.evidence if e.id in position),
                        key=lambda e: (position[e.id], *_evidence_key(e)))
    rest = sorted((e for e in res.evidence if e.id not in position), key=_evidence_key)
    ordered = referenced + rest
    items.extend(_evidence_item(origin, e) for e in ordered)

    for artifact in sorted(res.artifacts, key=lambda a: (a.path, a.sha256)):
        items.append(HandoffItem(kind="artifact", id=artifact.path, origin=origin,
                                 hash=artifact.sha256))
    return items


def _evidence_key(e: Evidence) -> tuple[int, str, str, str]:
    return (_EPISTEMIC_RANK[e.epistemic], e.id, e.subject, e.claim)


def _finding_item(origin: HandoffOrigin, finding: Finding) -> HandoffItem:
    return HandoffItem(kind="finding", id=finding.id, origin=origin,
                       claim=_claim(finding.title), severity=finding.severity,
                       evidence_ids=list(finding.evidence_ids))


def _evidence_item(origin: HandoffOrigin, evidence: Evidence) -> HandoffItem:
    # The epistemic status is copied verbatim: the handoff never upgrades it.
    return HandoffItem(kind="evidence", id=evidence.id, origin=origin,
                       epistemic=evidence.epistemic, subject=evidence.subject,
                       claim=_claim(evidence.claim), location=evidence.location,
                       hash=evidence.hash)


def _claim(text: str) -> str:
    """Redacted claim within ``MAX_CLAIM_CHARS`` that is a fixed point of redaction.

    Redaction comes first so a cut can never split a secret past its pattern; the cut
    text is re-redacted until stable. Fallback: the bare redaction marker.
    """
    value = redact_text(text)
    for _ in range(_MAX_CLAIM_ATTEMPTS):
        if len(value) <= MAX_CLAIM_CHARS and redact_text(value) == value:
            return value
        if len(value) > MAX_CLAIM_CHARS:
            value = value[:MAX_CLAIM_CHARS - len(TRUNCATION_MARKER)] + TRUNCATION_MARKER
        value = redact_text(value)
    return REDACTED


def _redacted(item: HandoffItem) -> HandoffItem:
    return from_dict(HandoffItem, redact(to_dict(item)), strict=True)


def _size(data: Any) -> int:
    return len(canonical_json(data).encode("utf-8"))


def _prefix_within_limits(candidates: list[HandoffItem],
                          make: Callable[[list[HandoffItem], int], Handoff]) -> list[HandoffItem]:
    """Longest prefix of ``candidates`` within the item and canonical-byte limits.

    The envelope is measured at its worst case (every candidate dropped), so adding the
    truncation note later can never push the handoff over ``MAX_HANDOFF_BYTES``.
    """
    envelope = max(_size(to_dict(make([], 0))), _size(to_dict(make([], len(candidates)))))
    budget = MAX_HANDOFF_BYTES - envelope
    kept: list[HandoffItem] = []
    used = 0
    for item in candidates:
        if len(kept) >= MAX_HANDOFF_ITEMS:
            break
        cost = _size(to_dict(item)) + (1 if kept else 0)  # "," between array elements
        if used + cost > budget:
            break
        kept.append(item)
        used += cost
    return kept
