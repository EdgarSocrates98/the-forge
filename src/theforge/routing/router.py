"""Deterministic routing: explicit capability or ranked declared signals. Never guesses."""

from collections.abc import Sequence

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
from theforge.contracts.types import TRUST_RANK
from theforge.errors import UsageError
from theforge.meta import PRODUCER
from theforge.registry import RegistryRecord
from theforge.routing.signals import (
    glob_matches,
    keyword_matches,
    normalize_dep,
    normalize_tokens,
)

MIN_SIGNAL_TYPES = 2


def route(
    task: TaskSpec, records: Sequence[RegistryRecord], files: list[str],
    dependencies: set[str], *, allow_unverified: bool = False,
) -> RoutingDecision:
    routable = [r for r in records if r.routable(allow_unverified)]
    if task.requested_capability:
        return _route_explicit(task, routable, task.requested_capability)
    return _route_by_signals(task, routable, files, dependencies)


def resolve_action(task: TaskSpec, capability: Capability) -> str:
    action = task.requested_action or capability.default_action
    if action not in capability.actions:
        raise UsageError(f"action {action!r} is not offered by {capability.id} "
                         f"(actions: {', '.join(capability.actions)})")
    return action


def _decision(
    task: TaskSpec, *, status: str, reason: str, level: str,
    candidates: Sequence[Candidate] = (), selected: Sequence[Selection] = (),
    measured: Sequence[str] = (), unresolved: Sequence[str] = (),
) -> RoutingDecision:
    return RoutingDecision(
        producer=PRODUCER, created_at=utc_now(), status=status,  # type: ignore[arg-type]
        task_id=task.id, candidates=list(candidates), selected=list(selected), reason=reason,
        confidence=Confidence(level=level, measured_signals=list(measured),  # type: ignore[arg-type]
                              unresolved=list(unresolved)),
    )


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
    candidates = [Candidate(provider=r.entry.id, capability=cap_id,
                            rank_key=[TRUST_RANK[r.entry.trust]]) for r, _ in matches]
    reason = f"requested capability {cap_id}"
    if len(matches) > 1:
        reason += f"; {len(matches)} providers declare it, tie-break by trust then id"
    return _decision(task, status="routed", level="high", reason=reason, candidates=candidates,
                     selected=[Selection(provider=record.entry.id, capability=cap_id,
                                         action=action)],
                     measured=["requested_capability"])


def _route_by_signals(
    task: TaskSpec, routable: list[RegistryRecord], files: list[str], dependencies: set[str],
) -> RoutingDecision:
    intent = set(normalize_tokens(task.intent))
    scored: list[tuple[Candidate, Capability]] = []
    for record in routable:
        if record.manifest is None:
            continue
        for capability in record.manifest.capabilities:
            if capability.state == "unsupported":
                continue
            signals = capability.signals
            deps = sorted({normalize_dep(d) for d in signals.dependencies} & dependencies)
            globs = glob_matches(files, signals.file_globs)
            kws = keyword_matches(intent, signals.keywords)
            types = sum(1 for hits in (deps, globs, kws) if hits)
            if types == 0:
                continue
            candidate = Candidate(
                provider=record.entry.id, capability=capability.id,
                matched=MatchedSignals(dependencies=deps, file_globs=globs, keywords=kws),
                rank_key=[types, len(deps), len(globs), len(kws)],
            )
            scored.append((candidate, capability))
    scored.sort(key=lambda s: ([-k for k in s[0].rank_key], s[0].provider, s[0].capability))
    candidates = [s[0] for s in scored]
    if not scored:
        return _decision(task, status="no_route", level="low",
                         reason="no capability matched any signal", unresolved=["intent"])
    top, capability = scored[0]
    measured = _measured(top.matched)
    issue: str | None = None
    if len(scored) > 1 and scored[1][0].rank_key == top.rank_key:
        other = scored[1][0]
        issue = (f"tie between {top.provider}/{top.capability} and "
                 f"{other.provider}/{other.capability} at rank {top.rank_key}")
    elif top.rank_key[0] < MIN_SIGNAL_TYPES:
        issue = (f"only {top.rank_key[0]} signal type matched for "
                 f"{top.provider}/{top.capability} (need {MIN_SIGNAL_TYPES})")
    if issue is not None:
        return _decision(task, status="ambiguous", level="low", reason=f"ambiguous: {issue}",
                         candidates=candidates, measured=measured, unresolved=[issue])
    action = resolve_action(task, capability)
    reason = (f"{top.provider} {top.capability} matched {top.rank_key[0]} signal types "
              f"({'; '.join(measured)})")
    return _decision(task, status="routed", level="high", reason=reason, candidates=candidates,
                     selected=[Selection(provider=top.provider, capability=top.capability,
                                         action=action)],
                     measured=measured)


def _measured(matched: MatchedSignals) -> list[str]:
    groups = (("dependencies", matched.dependencies), ("file_globs", matched.file_globs),
              ("keywords", matched.keywords))
    return [f"{name}:{','.join(hits)}" for name, hits in groups if hits]
