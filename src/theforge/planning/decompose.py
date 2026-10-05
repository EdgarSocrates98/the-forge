"""Decomposer: deterministic task -> plan, without domain rules and without LLM (2.1-2.7, 6.1).

Input: the ``RoutingDecision`` of ``route()`` over the task (signal path), computed with the
full workspace scan and ``decomposition_dependencies`` (root plus each repository of the
descriptor). Only ``decision.candidates`` are read; nothing here knows any provider domain.

- Per provider, the best capability is the one with the highest ``rank_key[0]`` (discriminating
  signal types). A provider qualifies when that rank reaches ``MIN_SIGNAL_TYPES``.
- One-provider profile, an explicitly requested capability, or at most one qualified provider:
  the decision itself becomes one ``route`` node (``routed``), or the decomposition keeps the
  decision's ``ambiguous``/``no_route``; with two or more qualified providers and a profile
  limited to one, the plan records ``multi-provider decomposition not allowed by profile``.
- Otherwise (``ambiguous`` on each failure): a tie between best capabilities of one provider,
  more qualified providers than ``profile.max_providers``, a provider without a matched keyword
  or two providers at the same position. Nodes are ordered by the ``intent-order`` rule: the
  smallest index, in ``normalize_tokens(intent)``, of the first token of a matched keyword; a
  linear pipeline where node *i* depends on (and takes the artifacts of) node *i-1*, the
  dependency ``inferred`` with the rule and its keyword evidence.

The rule is a proxy of the data flow (ADR 0018): ``plan --from FILE`` fixes the order
explicitly. Output depends only on content, never on the order of records, candidates or files.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal

from theforge.contracts.canonical import utc_now
from theforge.contracts.manifest import Capability
from theforge.contracts.plan import ExecutionPlan, NodeRole, PlanDependency, PlanNode
from theforge.contracts.routing import Candidate, Confidence, RoutingDecision, Selection
from theforge.contracts.task import TaskSpec
from theforge.contracts.types import PlanPattern
from theforge.contracts.workspace import WorkspaceDescriptor
from theforge.meta import PRODUCER
from theforge.planning.validate import checked_plan
from theforge.profiles import ContextProfile
from theforge.registry import RegistryRecord
from theforge.routing.router import LOW_CONFIDENCE_STATES, MIN_SIGNAL_TYPES
from theforge.routing.signals import glob_matches, normalize_tokens, workspace_dependencies
from theforge.workspace.describe import repository_of

if TYPE_CHECKING:  # the design's import direction lists no runtime ``context`` import here
    from theforge.context.scan import WorkspaceScan

__all__ = [
    "INTENT_ORDER_RULE",
    "Decomposition",
    "decompose",
    "decomposed_plan",
    "decomposition_dependencies",
]

INTENT_ORDER_RULE: Final = "intent-order"

DecompositionStatus = Literal["planned", "ambiguous", "no_route"]


@dataclass(frozen=True, kw_only=True)
class Decomposition:
    status: DecompositionStatus
    decision: RoutingDecision  # recorded as the ``routing`` artifact of the plan run
    nodes: tuple[PlanNode, ...]  # empty unless planned
    pattern: PlanPattern
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class _Ordered:
    candidate: Candidate
    position: int
    keyword: str


def decomposition_dependencies(root: Path, descriptor: WorkspaceDescriptor) -> set[str]:
    """The routing dependencies of a decomposition: those of ``root`` plus each repository."""
    names = workspace_dependencies(root)
    for repository in descriptor.repositories:
        if repository.path != ".":
            names |= workspace_dependencies(root.joinpath(*repository.path.split("/")))
    return names


def decompose(
    task: TaskSpec, decision: RoutingDecision, records: Mapping[str, RegistryRecord],
    descriptor: WorkspaceDescriptor, scan: "WorkspaceScan", profile: ContextProfile,
) -> Decomposition:
    """Turn ``decision`` (``route()`` over ``task``) into plan nodes (2.1-2.7)."""
    decision = replace(decision, candidates=sorted(decision.candidates, key=_candidate_key))
    files = sorted(set(scan.files))
    best = _best_by_provider(decision.candidates)
    qualified = [tops for tops in best.values() if tops[0].rank_key[0] >= MIN_SIGNAL_TYPES]

    if task.requested_capability or profile.max_providers <= 1 or len(qualified) <= 1:
        limitations: tuple[str, ...] = ()
        if len(qualified) >= 2 and not task.requested_capability:
            limitations = (f"multi-provider decomposition not allowed by profile "
                           f"{profile.name!r}",)
        return _single(task, decision, records, descriptor, files, limitations)

    issue = _qualification_issue(qualified, profile)
    if issue is None:
        ordered, issue = _order(task, [tops[0] for tops in qualified])
    if issue is not None:
        return _ambiguous(decision, issue)
    nodes = _pipeline(task, ordered, records, descriptor, files)
    return Decomposition(status="planned", decision=_pipeline_decision(decision, nodes, records),
                         nodes=nodes, pattern="pipeline", limitations=())


def decomposed_plan(
    decomposition: Decomposition, task: TaskSpec, records: Mapping[str, RegistryRecord],
    profile: ContextProfile, *, plan_run: str, created_at: str | None = None,
) -> ExecutionPlan:
    """The ``ExecutionPlan`` of a ``planned`` decomposition, validated by ``checked_plan``
    (the same validation as a plan file); any other status raises ``ValueError``."""
    if decomposition.status != "planned":
        raise ValueError(f"decomposition is {decomposition.status}, not planned")
    plan = ExecutionPlan(
        producer=PRODUCER, created_at=created_at if created_at is not None else utc_now(),
        status="validated", plan_run=plan_run, task_id=task.id,
        pattern=decomposition.pattern, source="decomposed", profile=profile.name,
        nodes=list(decomposition.nodes), limitations=list(decomposition.limitations))
    return checked_plan(plan, records, profile)


# --- qualification ---------------------------------------------------------------------------

def _candidate_key(candidate: Candidate) -> tuple[int, str, str]:
    return (-(candidate.rank_key[0] if candidate.rank_key else 0), candidate.provider,
            candidate.capability)


def _best_by_provider(candidates: Sequence[Candidate]) -> dict[str, list[Candidate]]:
    """Per provider (id order), its candidates tied at the highest ``rank_key[0]``."""
    groups: dict[str, list[Candidate]] = {}
    for candidate in candidates:  # already sorted: rank desc, then provider, capability
        if not candidate.rank_key or candidate.state == "unsupported":
            continue
        tops = groups.setdefault(candidate.provider, [])
        if not tops or tops[0].rank_key[0] == candidate.rank_key[0]:
            tops.append(candidate)
    return dict(sorted(groups.items()))


def _qualification_issue(qualified: list[list[Candidate]], profile: ContextProfile) -> str | None:
    for tops in qualified:
        if len(tops) > 1:
            return (f"tie between best capabilities of {tops[0].provider}: "
                    f"{', '.join(c.capability for c in tops)} at rank {tops[0].rank_key}")
    if len(qualified) > profile.max_providers:
        return (f"{len(qualified)} qualified providers "
                f"({', '.join(tops[0].provider for tops in qualified)}); profile "
                f"{profile.name!r} allows {profile.max_providers}")
    return None


def _order(task: TaskSpec, best: list[Candidate]) -> tuple[list[_Ordered], str | None]:
    """``intent-order``: by the position of the first token of the first matched keyword."""
    tokens = normalize_tokens(task.intent)
    ordered: list[_Ordered] = []
    for candidate in best:
        located = sorted((tokens.index(k.split(" ")[0]), k) for k in candidate.matched.keywords
                         if k.split(" ")[0] in tokens)
        if not located:
            return [], (f"cannot order {candidate.provider}: no keyword of "
                        f"{candidate.capability} matched the intent")
        ordered.append(_Ordered(candidate, *located[0]))
    ordered.sort(key=lambda o: (o.position, o.candidate.provider))
    for first, second in zip(ordered, ordered[1:], strict=False):
        if first.position == second.position:
            return [], (f"cannot order {first.candidate.provider} and "
                        f"{second.candidate.provider}: keywords '{first.keyword}' and "
                        f"'{second.keyword}' start at the same position {first.position}")
    return ordered, None


# --- nodes -----------------------------------------------------------------------------------

def _capability(records: Mapping[str, RegistryRecord], provider: str,
                capability: str) -> Capability | None:
    record = records.get(provider)
    resolved = record.manifest.resolve(capability) if record and record.manifest else None
    return resolved[0] if resolved is not None else None


def _action(task: TaskSpec, capability: Capability) -> str:
    requested = task.requested_action
    return requested if requested and requested in capability.actions else (
        capability.default_action)


def _targets(task: TaskSpec, candidate: Candidate | None, descriptor: WorkspaceDescriptor,
             files: list[str]) -> list[str]:
    """Repositories where the candidate's (discriminating) globs or dependencies matched;
    none -> ``task.targets``."""
    found: set[str] = set()
    if candidate is not None:
        globs = candidate.matched.file_globs
        for file in files:
            if globs and glob_matches([file], globs):
                owner = repository_of(descriptor, file)
                if owner is not None:
                    found.add(owner)
        deps = set(candidate.matched.dependencies)
        found.update(t.repository for t in descriptor.technologies
                     if t.source == "dependency_manifest" and t.name in deps)
    if not found:
        return list(task.targets)
    return sorted(found, key=lambda p: () if p == "." else tuple(p.split("/")))


def _pipeline(task: TaskSpec, ordered: list[_Ordered], records: Mapping[str, RegistryRecord],
              descriptor: WorkspaceDescriptor, files: list[str]) -> tuple[PlanNode, ...]:
    nodes: list[PlanNode] = []
    for index, item in enumerate(ordered):
        candidate = item.candidate
        capability = _capability(records, candidate.provider, candidate.capability)
        action = _action(task, capability) if capability is not None else ""
        depends_on: list[PlanDependency] = []
        role: NodeRole = "producer"
        if index:
            previous = ordered[index - 1]
            role = "consumer"
            depends_on = [PlanDependency(
                node=f"n{index}", epistemic="inferred", rule=INTENT_ORDER_RULE,
                evidence=(f"keyword '{previous.keyword}'@{previous.position} < "
                          f"keyword '{item.keyword}'@{item.position}"))]
        nodes.append(PlanNode(
            id=f"n{index + 1}", role=role, provider=candidate.provider,
            capability=candidate.capability, action=action,
            targets=_targets(task, candidate, descriptor, files), depends_on=depends_on,
            inputs=[d.node for d in depends_on]))
    return tuple(nodes)


def _pipeline_decision(decision: RoutingDecision, nodes: tuple[PlanNode, ...],
                       records: Mapping[str, RegistryRecord]) -> RoutingDecision:
    selected = [Selection(provider=n.provider, capability=n.capability, action=n.action,
                          role="primary" if i == 0 else "specialist")
                for i, n in enumerate(nodes)]
    low = sorted({f"capability_state:{c.state}" for n in nodes
                  if (c := _capability(records, n.provider, n.capability)) is not None
                  and c.state in LOW_CONFIDENCE_STATES})
    chain = " -> ".join(f"{n.provider}/{n.capability}" for n in nodes)
    return replace(
        decision, status="routed", pattern="pipeline", selected=selected,
        reason=f"decomposed into {len(nodes)} nodes by rule {INTENT_ORDER_RULE}: {chain}",
        confidence=Confidence(level="low" if low else "high",
                              measured_signals=list(decision.confidence.measured_signals),
                              unresolved=low))


def _single(task: TaskSpec, decision: RoutingDecision, records: Mapping[str, RegistryRecord],
            descriptor: WorkspaceDescriptor, files: list[str],
            limitations: tuple[str, ...]) -> Decomposition:
    if decision.status != "routed":
        return Decomposition(status=decision.status, decision=decision, nodes=(),
                             pattern="route", limitations=limitations)
    selection = decision.selected[0]
    candidate = next((c for c in decision.candidates if c.provider == selection.provider
                      and c.capability == selection.capability), None)
    node = PlanNode(id="n1", role="standalone", provider=selection.provider,
                    capability=selection.capability, action=selection.action,
                    targets=_targets(task, candidate, descriptor, files))
    return Decomposition(status="planned", decision=replace(decision, pattern="route"),
                         nodes=(node,), pattern="route", limitations=limitations)


def _ambiguous(decision: RoutingDecision, issue: str) -> Decomposition:
    ambiguous = replace(
        decision, status="ambiguous", pattern="pipeline", selected=[],
        reason=f"ambiguous: {issue}",
        confidence=Confidence(level="low",
                              measured_signals=list(decision.confidence.measured_signals),
                              unresolved=[issue]))
    return Decomposition(status="ambiguous", decision=ambiguous, nodes=(), pattern="pipeline",
                         limitations=())
