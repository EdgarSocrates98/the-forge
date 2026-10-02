"""Deterministic routing: explicit capability or declared-signal presence. Never guesses.

Signal path (cycle 2): the decision uses only ``types_matched``, the number of signal types
(dependency, file glob, keyword) with at least one *discriminating* hit, so declaring more
signals never raises a score. Per-type hits are normalized, deduplicated and kept in
``MatchedSignals`` for explanation only; they never break ties.

Non-discriminating signals: when two or more providers scored, a signal (same normalized
dependency, glob or keyword) matched by *all* of them does not count for ``types_matched`` and
is recorded in ``limitations``. With a single scoring provider nothing is non-discriminating.
Removing shared signals may only add ambiguity, never pick a winner: the selected candidate
must also be the unique top by raw presence (shared signals included). Otherwise a provider
that copies another's signals and adds generic extras would win by deflating it.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from theforge.contracts import (
    Candidate,
    Capability,
    Confidence,
    MatchedSignals,
    RoutingDecision,
    Selection,
    TaskSpec,
)
from theforge.contracts.canonical import utc_now
from theforge.contracts.types import TRUST_RANK, is_catch_all_glob
from theforge.errors import UsageError
from theforge.meta import PRODUCER
from theforge.registry import RegistryRecord
from theforge.routing.signals import glob_matches, normalize_dep, normalize_tokens

MIN_SIGNAL_TYPES = 2
EXECUTE_OP = "execute"
LOW_CONFIDENCE_STATES = frozenset({"heuristic", "unresolved"})

_Groups = tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]  # deps, globs, keywords


def route(
    task: TaskSpec, records: Sequence[RegistryRecord], files: Sequence[str],
    dependencies: set[str], *, allow_unverified: bool = False,
) -> RoutingDecision:
    # Sort inputs so the decision depends only on content, never on discovery/fs order (3.1).
    routable = sorted(
        (r for r in records if r.routable(allow_unverified) and _executes(r)),
        key=lambda r: (r.entry.id, r.manifest_sha256 or ""),
    )
    if task.requested_capability:
        return _route_explicit(task, routable, task.requested_capability)
    return _route_by_signals(task, routable, sorted(set(files)), dependencies)


def resolve_action(task: TaskSpec, capability: Capability) -> str:
    action = task.requested_action or capability.default_action
    if action not in capability.actions:
        raise UsageError(f"action {action!r} is not offered by {capability.id} "
                         f"(actions: {', '.join(capability.actions)})")
    return action


def _executes(record: RegistryRecord) -> bool:
    """Capabilities of a provider whose manifest lacks ``execute`` are not routable (2.1)."""
    return record.manifest is not None and EXECUTE_OP in record.manifest.ops


def _decision(
    task: TaskSpec, *, status: str, reason: str, level: str,
    candidates: Sequence[Candidate] = (), selected: Sequence[Selection] = (),
    measured: Sequence[str] = (), unresolved: Sequence[str] = (),
    limitations: Sequence[str] = (),
) -> RoutingDecision:
    return RoutingDecision(
        producer=PRODUCER, created_at=utc_now(), status=status,  # type: ignore[arg-type]
        task_id=task.id, candidates=list(candidates), selected=list(selected), reason=reason,
        confidence=Confidence(level=level, measured_signals=list(measured),  # type: ignore[arg-type]
                              unresolved=list(unresolved)),
        limitations=list(limitations),
    )


def _state_confidence(capability: Capability) -> tuple[str, list[str]]:
    """A heuristic/unresolved selection is never high confidence (3.8)."""
    if capability.state in LOW_CONFIDENCE_STATES:
        return "low", [f"capability_state:{capability.state}"]
    return "high", []


def _route_explicit(
    task: TaskSpec, routable: list[RegistryRecord], cap_id: str
) -> RoutingDecision:
    matches: list[tuple[RegistryRecord, Capability]] = []
    for record in routable:
        capability = record.manifest.capability(cap_id) if record.manifest else None
        if capability is not None and capability.state != "unsupported":
            matches.append((record, capability))
    if not matches:
        return _decision(task, status="no_route", level="low",
                         reason=f"no routable provider declares capability {cap_id}",
                         unresolved=[f"capability:{cap_id}"])
    matches.sort(key=lambda m: (TRUST_RANK[m[0].entry.trust], m[0].entry.id))
    record, capability = matches[0]
    action = resolve_action(task, capability)
    candidates = [Candidate(provider=r.entry.id, capability=cap_id, state=c.state,
                            rank_key=[TRUST_RANK[r.entry.trust]]) for r, c in matches]
    reason = f"requested capability {cap_id}"
    if len(matches) > 1:
        reason += f"; {len(matches)} providers declare it, tie-break by trust then id"
    level, unresolved = _state_confidence(capability)
    return _decision(task, status="routed", level=level, reason=reason, candidates=candidates,
                     selected=[Selection(provider=record.entry.id, capability=cap_id,
                                         action=action)],
                     measured=["requested_capability"], unresolved=unresolved)


@dataclass(frozen=True)
class _Scored:
    record: RegistryRecord
    capability: Capability
    hits: _Groups

    @property
    def raw_types(self) -> int:
        return sum(1 for group in self.hits if group)


def _keyword_hits(intent: set[str], keywords: Sequence[str]) -> tuple[str, ...]:
    normalized = {" ".join(tokens) for k in keywords if (tokens := normalize_tokens(k))}
    return tuple(sorted(k for k in normalized if all(t in intent for t in k.split(" "))))


def _signal_hits(
    capability: Capability, intent: set[str], files: list[str], dependencies: set[str],
) -> _Groups:
    signals = capability.signals
    deps = tuple(sorted({normalize_dep(d) for d in signals.dependencies} & dependencies))
    # Catch-all globs are rejected by manifest limits; ignored here defensively.
    globs = sorted({g for g in signals.file_globs if not is_catch_all_glob(g)})
    return deps, tuple(glob_matches(files, globs)), _keyword_hits(intent, signals.keywords)


def _shared_signals(scoring: list[_Scored]) -> list[set[str]]:
    """Per type, the signals matched by every scoring provider.

    The rule is between providers: it applies only when 2+ distinct providers scored, and a
    provider matches a signal when any of its scoring capabilities does. Capabilities of one
    provider sharing a glob (e.g. echo's ``*.txt``) never neutralize each other.
    """
    by_provider: dict[str, list[set[str]]] = {}
    for item in scoring:
        groups = by_provider.setdefault(item.record.entry.id, [set(), set(), set()])
        for i, hits in enumerate(item.hits):
            groups[i].update(hits)
    if len(by_provider) < 2:
        return [set(), set(), set()]
    providers = list(by_provider.values())
    return [set.intersection(*(groups[i] for groups in providers)) for i in range(3)]


def _route_by_signals(
    task: TaskSpec, routable: list[RegistryRecord], files: list[str], dependencies: set[str],
) -> RoutingDecision:
    intent = set(normalize_tokens(task.intent))
    scoring: list[_Scored] = []
    for record in routable:
        capabilities = record.manifest.capabilities if record.manifest else []
        for capability in sorted(capabilities, key=lambda c: c.id):
            if capability.state == "unsupported":
                continue
            hits = _signal_hits(capability, intent, files, dependencies)
            if any(hits):
                scoring.append(_Scored(record, capability, hits))
    if not scoring:
        return _decision(task, status="no_route", level="low",
                         reason="no capability matched any signal", unresolved=["intent"])

    shared = _shared_signals(scoring)
    limitations = sorted({f"non-discriminating signal '{signal}' shared by all candidates"
                          for group in shared for signal in group})
    ranked: list[tuple[Candidate, _Scored]] = []
    for item in scoring:
        kept = [[s for s in group if s not in shared[i]] for i, group in enumerate(item.hits)]
        candidate = Candidate(
            provider=item.record.entry.id, capability=item.capability.id,
            matched=MatchedSignals(dependencies=kept[0], file_globs=kept[1], keywords=kept[2]),
            rank_key=[sum(1 for group in kept if group)], state=item.capability.state,
        )
        ranked.append((candidate, item))
    ranked.sort(key=lambda r: (-r[0].rank_key[0], r[0].provider, r[0].capability))
    candidates = [c for c, _ in ranked]
    top, top_scored = ranked[0]
    measured = _measured(top.matched)
    issue = _ambiguity(ranked)
    if issue is not None:
        return _decision(task, status="ambiguous", level="low", reason=f"ambiguous: {issue}",
                         candidates=candidates, measured=measured, unresolved=[issue],
                         limitations=limitations)
    action = resolve_action(task, top_scored.capability)
    reason = (f"{top.provider} {top.capability} matched {top.rank_key[0]} signal types "
              f"({'; '.join(measured)})")
    level, unresolved = _state_confidence(top_scored.capability)
    return _decision(task, status="routed", level=level, reason=reason, candidates=candidates,
                     selected=[Selection(provider=top.provider, capability=top.capability,
                                         action=action)],
                     measured=measured, unresolved=unresolved, limitations=limitations)


def _ambiguity(ranked: list[tuple[Candidate, _Scored]]) -> str | None:
    top, top_scored = ranked[0]
    if len(ranked) > 1 and ranked[1][0].rank_key == top.rank_key:
        other = ranked[1][0]
        return (f"tie between {top.provider}/{top.capability} and "
                f"{other.provider}/{other.capability} at rank {top.rank_key}")
    if top.rank_key[0] < MIN_SIGNAL_TYPES:
        noun = "type" if top.rank_key[0] == 1 else "types"
        return (f"only {top.rank_key[0]} signal {noun} matched for "
                f"{top.provider}/{top.capability} (need {MIN_SIGNAL_TYPES})")
    rival = next((c for c, s in ranked[1:] if s.raw_types >= top_scored.raw_types), None)
    if rival is not None:
        return (f"tie between {top.provider}/{top.capability} and "
                f"{rival.provider}/{rival.capability} at raw presence "
                f"[{top_scored.raw_types}]; shared signals alone cannot decide")
    return None


def _measured(matched: MatchedSignals) -> list[str]:
    groups = (("dependencies", matched.dependencies), ("file_globs", matched.file_globs),
              ("keywords", matched.keywords))
    return [f"{name}:{','.join(hits)}" for name, hits in groups if hits]
