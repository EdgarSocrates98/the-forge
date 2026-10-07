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
from dataclasses import dataclass, replace

from theforge.contracts import (
    Candidate,
    Capability,
    CapabilityNegotiationResult,
    Confidence,
    MatchedSignals,
    ProviderPerformance,
    RoutingDecision,
    Selection,
    TaskSpec,
)
from theforge.contracts.canonical import utc_now
from theforge.contracts.types import TRUST_RANK, is_catch_all_glob
from theforge.errors import UsageError
from theforge.meta import PRODUCER
from theforge.negotiation import negotiate_all
from theforge.registry import RegistryRecord
from theforge.routing.signals import glob_matches, normalize_dep, normalize_tokens

MIN_SIGNAL_TYPES = 2
EXECUTE_OP = "execute"
LOW_CONFIDENCE_STATES = frozenset({"heuristic", "unresolved"})

_Groups = tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]  # deps, globs, keywords


def route(
    task: TaskSpec, records: Sequence[RegistryRecord], files: Sequence[str],
    dependencies: set[str], *, allow_unverified: bool = False,
    performance: ProviderPerformance | None = None,
) -> RoutingDecision:
    # Sort inputs so the decision depends only on content, never on discovery/fs order (3.1).
    allowed = sorted(
        (r for r in records if r.routable(allow_unverified)),
        key=lambda r: (r.entry.id, r.manifest_sha256 or ""),
    )
    routable = [r for r in allowed if _executes(r)]
    requested = task.requested_capability
    if requested is None and task.requirement is not None:
        requested = task.requirement.capability
    if requested:
        decision = _route_explicit(task, routable, requested,
                                   performance=performance)
    else:
        decision = _route_by_signals(task, routable, sorted(set(files)), dependencies,
                                     performance=performance)
    excluded = sorted({r.entry.id for r in allowed
                       if not _executes(r) and _relevant(r, task, decision)})
    if not excluded:
        return decision
    notes = [f"{pid}: not routable, manifest does not declare op {EXECUTE_OP!r}"
             for pid in excluded]
    return replace(decision, limitations=[*decision.limitations, *notes])


def resolve_action(task: TaskSpec, capability: Capability) -> str:
    action = task.requested_action or capability.default_action
    if action not in capability.actions:
        raise UsageError(f"action {action!r} is not offered by {capability.id} "
                         f"(actions: {', '.join(capability.actions)})")
    return action


def _relevant(record: RegistryRecord, task: TaskSpec, decision: RoutingDecision) -> bool:
    """Whether a provider excluded for lacking ``execute`` is worth a note: it declares the
    requested capability, or (signal path) nothing was routed and it might have matched."""
    requested = task.requested_capability or (
        task.requirement.capability if task.requirement is not None else None)
    if requested:
        manifest = record.manifest
        return manifest is not None and manifest.resolve(requested) is not None
    return decision.status != "routed"


def _executes(record: RegistryRecord) -> bool:
    """Capabilities of a provider whose manifest lacks ``execute`` are not routable (2.1)."""
    return record.manifest is not None and EXECUTE_OP in record.manifest.ops


def _decision(
    task: TaskSpec, *, status: str, reason: str, level: str,
    candidates: Sequence[Candidate] = (), selected: Sequence[Selection] = (),
    measured: Sequence[str] = (), unresolved: Sequence[str] = (),
    limitations: Sequence[str] = (),
    negotiation: Sequence[CapabilityNegotiationResult] = (),
) -> RoutingDecision:
    return RoutingDecision(
        producer=PRODUCER, created_at=utc_now(), status=status,  # type: ignore[arg-type]
        task_id=task.id, candidates=list(candidates), selected=list(selected),
        negotiation=list(negotiation), reason=reason,
        confidence=Confidence(level=level, measured_signals=list(measured),  # type: ignore[arg-type]
                              unresolved=list(unresolved)),
        limitations=list(limitations),
    )


def _state_confidence(capability: Capability) -> tuple[str, list[str]]:
    """A heuristic/unresolved selection is never high confidence (3.8)."""
    if capability.state in LOW_CONFIDENCE_STATES:
        return "low", [f"capability_state:{capability.state}"]
    return "high", []


def alias_note(requested: str, capability: Capability, provider: str) -> str:
    """The ``capability-alias`` note of an alias resolved to its canonical id (5.5).

    Single source of the text, shared with plan files (``planning.validate``)."""
    return f"capability-alias: {requested!r} resolved to {capability.id!r} ({provider})"


def deprecation_note(capability: Capability, provider: str) -> str | None:
    """The ``capability-deprecated`` note of ``capability`` (5.5); None if not deprecated."""
    if not capability.deprecated:
        return None
    successor = (f"replaced_by {capability.replaced_by!r}" if capability.replaced_by
                 else "no replacement declared")
    return f"capability-deprecated: {capability.id!r} ({provider}) is deprecated; {successor}"


def _deprecation_notes(declared: Sequence[tuple[str, Capability]]) -> list[str]:
    """``capability-deprecated`` notes for (provider, capability) pairs (5.5); no weight."""
    return [note for provider, capability in declared
            if (note := deprecation_note(capability, provider)) is not None]


def _overlap_notes(declared: Sequence[tuple[str, Capability]], suffix: str = "") -> list[str]:
    """``capability-overlap`` notes: a capability id declared by 2+ providers (5.4)."""
    by_id: dict[str, set[str]] = {}
    for provider, capability in declared:
        by_id.setdefault(capability.id, set()).add(provider)
    return [f"capability-overlap: {cid!r} declared by {', '.join(sorted(providers))}{suffix}"
            for cid, providers in by_id.items() if len(providers) > 1]


def _perf_desc(performance: ProviderPerformance | None, record: RegistryRecord,
               capability: str) -> tuple[float, ...]:
    """Negated measured-history key: sorts ascending within a larger sort key (H5).

    Scoped by the record's surface fingerprint: history recorded against another
    surface simply does not apply (a changed surface never silently inherits it).
    """
    if performance is None:
        return (0.0,)
    surface = record.surface.surface_fingerprint if record.surface else None
    return tuple(-v for v in performance.score(record.entry.id, capability, surface))


def _route_explicit(
    task: TaskSpec, routable: list[RegistryRecord], requested: str, *,
    performance: ProviderPerformance | None = None,
) -> RoutingDecision:
    """Canonical declarers first; only when none exists, alias declarers (5.5). Within the
    group the tie-break is trust, then measured history, then id. Selections and candidates
    carry the canonical id."""
    canonical: list[tuple[RegistryRecord, Capability]] = []
    aliased: list[tuple[RegistryRecord, Capability]] = []
    for record in routable:
        resolved = record.manifest.resolve(requested) if record.manifest else None
        if resolved is None or resolved[0].state == "unsupported":
            continue
        (aliased if resolved[1] else canonical).append((record, resolved[0]))
    matches = canonical or aliased
    if not matches:
        return _decision(task, status="no_route", level="low",
                         reason=f"no routable provider declares capability {requested}",
                         unresolved=[f"capability:{requested}"])
    if task.requirement is not None:
        return _route_by_requirement(task, matches, requested,
                                     performance=performance)
    # Trust dominates; measured history only orders equals, then id (H5).
    matches.sort(key=lambda m: (TRUST_RANK[m[0].entry.trust],
                                _perf_desc(performance, m[0], m[1].id),
                                m[0].entry.id))
    candidates = [Candidate(provider=r.entry.id, capability=c.id, state=c.state,
                            rank_key=[TRUST_RANK[r.entry.trust]]) for r, c in matches]
    declared = [(r.entry.id, c) for r, c in matches]
    notes = [alias_note(requested, c, provider) for provider, c in declared if not canonical]
    targets = sorted({c.id for _, c in matches})
    if len(targets) > 1:
        # Only alias groups can diverge: providers naming different capabilities by one
        # alias is ambiguity, never a trust tie-break between unrelated capabilities.
        issue = (f"capability-alias: {requested!r} resolves to different capabilities: "
                 f"{', '.join(targets)}")
        return _decision(task, status="ambiguous", level="low", reason=f"ambiguous: {issue}",
                         candidates=candidates, measured=["requested_capability"],
                         unresolved=[issue], limitations=sorted(set(notes)))
    record, capability = matches[0]
    action = resolve_action(task, capability)
    reason = f"requested capability {requested}"
    if len(matches) > 1:
        reason += (f"; {len(matches)} providers declare it, tie-break by trust, "
                   "measured history, then id")
    notes += _deprecation_notes(declared)
    notes += _overlap_notes(declared, "; tie-break trust, history, id")
    level, unresolved = _state_confidence(capability)
    return _decision(task, status="routed", level=level, reason=reason, candidates=candidates,
                     selected=[Selection(provider=record.entry.id, capability=capability.id,
                                         action=action)],
                     measured=["requested_capability"], unresolved=unresolved,
                     limitations=sorted(set(notes)))


def _route_by_requirement(
    task: TaskSpec, matches: list[tuple[RegistryRecord, Capability]], requested: str, *,
    performance: ProviderPerformance | None = None,
) -> RoutingDecision:
    """Fit selection (cycle 4): declarers negotiated against ``task.requirement``.

    ``negotiate_all`` already orders by state → dimensions → history →
    fingerprint → id; only FULL/PARTIAL offers are selectable — a hard-gate
    failure (INCOMPATIBLE) is never ranked back in, and the full result set
    rides on ``decision.negotiation`` so explain can say *why* (§14).
    """
    requirement = task.requirement
    assert requirement is not None  # caller guarantees
    by_provider = {r.entry.id: (r, c) for r, c in matches}
    results = negotiate_all(requirement, [r for r, _ in matches],
                            performance=performance)
    declared = [(r.entry.id, c) for r, c in matches]
    notes = _deprecation_notes(declared) + _overlap_notes(
        declared, "; ranked by negotiation fit")
    viable = [res for res in results if res.state in ("FULL", "PARTIAL")]
    dim_rank = {"none": 0, "unknown": 1, "partial": 2, "full": 3, "not_applicable": 4}

    def rank_key(res: CapabilityNegotiationResult) -> list[int]:
        order = {"INCOMPATIBLE": 0, "UNRESOLVED": 1, "UNSUPPORTED": 2,
                 "PARTIAL": 3, "FULL": 4}[res.state]
        hist = {"absent": 0, "stale": 0, "cold": 1, "warming": 2, "mature": 3}[res.history]
        return [order, *(dim_rank[v] for v in res.dimensions.values()), hist]

    candidates = [
        Candidate(provider=res.provider,
                  capability=res.capability or requirement.capability,
                  state=(by_provider[res.provider][1].state
                         if res.provider in by_provider else "supported"),
                  rank_key=rank_key(res))
        for res in viable]
    targets = {res.capability for res in viable}
    if len(targets) > 1:
        # Same alias-divergence rule as the plain explicit path: providers
        # resolving the request to different capabilities is ambiguity, never
        # a fit tie-break between unrelated capabilities.
        issue = (f"capability-alias: {requested!r} resolves to different "
                 f"capabilities: {', '.join(sorted(t for t in targets if t))}")
        return _decision(task, status="ambiguous", level="low",
                         reason=f"ambiguous: {issue}",
                         candidates=candidates, measured=["requested_capability"],
                         unresolved=[issue], limitations=sorted(set(notes)),
                         negotiation=results)
    if not viable:
        top = results[0]
        conflicts = top.policy_conflicts + top.missing
        detail = f"; best {top.provider} is {top.state}" + (
            f" ({', '.join(conflicts)})" if conflicts else "")
        return _decision(
            task, status="no_route", level="low",
            reason=f"no provider fits requirement for {requested!r}{detail}",
            unresolved=[f"capability:{requested}"],
            limitations=sorted(set(notes)), negotiation=results)
    top = viable[0]
    record, capability = by_provider[top.provider]
    action = resolve_action(task, capability)
    reason = (f"requested capability {requested}; {len(matches)} declarer(s) negotiated, "
              f"best fit {top.state}")
    if len(viable) > 1:
        reason += f" over {viable[1].provider} ({viable[1].state})"
    if top.state == "PARTIAL":
        notes.append(f"partial fit: {top.provider} missing "
                     f"{', '.join(top.missing) or 'undeclared demands'}")
    level, unresolved = _state_confidence(capability)
    if top.state == "PARTIAL":
        level = "low"
        unresolved = [*unresolved, *top.missing]
    return _decision(task, status="routed", level=level, reason=reason,
                     candidates=candidates, measured=["requested_capability"],
                     selected=[Selection(provider=record.entry.id,
                                         capability=capability.id, action=action)],
                     unresolved=unresolved, limitations=sorted(set(notes)),
                     negotiation=results)


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
    task: TaskSpec, routable: list[RegistryRecord], files: list[str],
    dependencies: set[str], *, performance: ProviderPerformance | None = None,
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
    declared = [(item.record.entry.id, item.capability) for item in scoring]
    limitations = sorted({f"non-discriminating signal '{signal}' shared by all candidates"
                          for group in shared for signal in group}
                         | set(_deprecation_notes(declared)) | set(_overlap_notes(declared)))
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
    tied = [r for r in ranked if r[0].rank_key == ranked[0][0].rank_key]
    decided: set[tuple[str, str]] = set()
    if len(tied) > 1 and performance is not None:
        # A signal tie is the only place measured history may speak (H5): one
        # candidate strictly ahead resolves it — including the raw-presence
        # equality, which is the *same* ambiguity signals could not decide. Equal
        # or absent history stays ambiguous; the floor and any non-tied rival
        # with equal raw presence still block. History is scoped to each
        # record's surface fingerprint — a changed surface inherits nothing.
        def _surface(r: tuple[Candidate, _Scored]) -> str | None:
            surface = r[1].record.surface
            return surface.surface_fingerprint if surface else None

        best = max(performance.score(r[0].provider, r[0].capability, _surface(r))
                   for r in tied)
        winners = [r for r in tied
                   if performance.score(r[0].provider, r[0].capability, _surface(r))
                   == best]
        if best > (0.0, 0.0, 0.0, 0) and len(winners) == 1:
            winner = winners[0]
            ranked = [winner, *[r for r in ranked if r is not winner]]
            loser = next(r for r in tied if r is not winner)
            limitations.append(
                f"performance-tie-break: {winner[0].provider}/"
                f"{winner[0].capability} preferred over {loser[0].provider}/"
                f"{loser[0].capability} on measured history")
            decided = {(r[0].provider, r[0].capability) for r in tied}
    candidates = [c for c, _ in ranked]
    top, top_scored = ranked[0]
    measured = _measured(top.matched)
    issue = _ambiguity(ranked, decided=decided)
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


def _ambiguity(ranked: list[tuple[Candidate, _Scored]], *,
               decided: set[tuple[str, str]] | None = None) -> str | None:
    """``decided``: (provider, capability) pairs whose rank/raw tie was resolved by
    measured history — they no longer flag the tie or the raw-presence clause."""
    decided = decided or set()
    top, top_scored = ranked[0]
    if not decided and len(ranked) > 1 and ranked[1][0].rank_key == top.rank_key:
        other = ranked[1][0]
        return (f"tie between {top.provider}/{top.capability} and "
                f"{other.provider}/{other.capability} at rank {top.rank_key}")
    if top.rank_key[0] < MIN_SIGNAL_TYPES:
        noun = "type" if top.rank_key[0] == 1 else "types"
        return (f"only {top.rank_key[0]} signal {noun} matched for "
                f"{top.provider}/{top.capability} (need {MIN_SIGNAL_TYPES})")
    rival = next((c for c, s in ranked[1:]
                  if s.raw_types >= top_scored.raw_types
                  and (c.provider, c.capability) not in decided), None)
    if rival is not None:
        return (f"tie between {top.provider}/{top.capability} and "
                f"{rival.provider}/{rival.capability} at raw presence "
                f"[{top_scored.raw_types}]; shared signals alone cannot decide")
    return None


def _measured(matched: MatchedSignals) -> list[str]:
    groups = (("dependencies", matched.dependencies), ("file_globs", matched.file_globs),
              ("keywords", matched.keywords))
    return [f"{name}:{','.join(hits)}" for name, hits in groups if hits]
