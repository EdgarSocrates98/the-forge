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
  more qualified providers than ``profile.max_providers``, declared ``conflicts`` between
  qualified capabilities, a provider without a matched keyword nor a declared relation,
  two providers at the same position without a declared order, or a cycle in the declared
  relations. Nodes are ordered first by the ``capability-graph`` rule — declared
  ``requires`` and produces→consumes relations among the qualified capabilities — and the
  ``intent-order`` rule breaks the remaining ties: the smallest index, in
  ``normalize_tokens(intent)``, of the first token of a matched keyword; a linear pipeline
  where node *i* depends on (and takes the artifacts of) node *i-1*, the dependency
  ``inferred`` with its rule and evidence.

The rule is a proxy of the data flow (ADR 0018): ``plan --from FILE`` fixes the order
explicitly. Output depends only on content, never on the order of records, candidates or files.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal

from theforge.contracts.canonical import utc_now
from theforge.contracts.capability_graph import CapabilityGraph
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
# Ordering from declared capability-graph relations (requires / produces→consumes);
# stronger evidence than the intent-order keyword proxy (wave C, tier 1).
GRAPH_ORDER_RULE: Final = "capability-graph"

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
    task: TaskSpec,
    decision: RoutingDecision,
    records: Mapping[str, RegistryRecord],
    descriptor: WorkspaceDescriptor,
    scan: "WorkspaceScan",
    profile: ContextProfile,
    *,
    graph: CapabilityGraph | None = None,
) -> Decomposition:
    """Turn ``decision`` (``route()`` over ``task``) into plan nodes (2.1-2.7).

    ``graph`` is the plan run's ``CapabilityGraph``: declared ``requires`` and
    produces→consumes relations order the pipeline ahead of the intent-order
    keyword proxy (declared evidence beats heuristic); declared ``conflicts``
    between qualified capabilities are an ambiguity, not a pick.
    """
    decision = replace(decision, candidates=sorted(decision.candidates, key=_candidate_key))
    files = sorted(set(scan.files))
    best = _best_by_provider(decision.candidates)
    qualified = [tops for tops in best.values() if tops[0].rank_key[0] >= MIN_SIGNAL_TYPES]

    if task.requested_capability or profile.max_providers <= 1 or len(qualified) <= 1:
        limitations: tuple[str, ...] = ()
        if len(qualified) >= 2 and not task.requested_capability:
            limitations = (f"multi-provider decomposition not allowed by profile {profile.name!r}",)
        return _single(task, decision, records, descriptor, files, limitations)

    issue = _qualification_issue(qualified, profile)
    constraints, conflicts = _graph_constraints([tops[0] for tops in qualified], graph)
    if issue is None and conflicts:
        issue = f"declared capability conflicts: {'; '.join(conflicts)}"
    if issue is None:
        ordered, issue = _order(task, [tops[0] for tops in qualified], constraints)
    if issue is not None:
        return _ambiguous(decision, issue)
    nodes = _pipeline(
        task, ordered, records, descriptor, files, constraints, _reachability(constraints)
    )
    return Decomposition(
        status="planned",
        decision=_pipeline_decision(decision, nodes, records),
        nodes=nodes,
        pattern="pipeline",
        limitations=(),
    )


def decomposed_plan(
    decomposition: Decomposition,
    task: TaskSpec,
    records: Mapping[str, RegistryRecord],
    profile: ContextProfile,
    *,
    plan_run: str,
    created_at: str | None = None,
) -> ExecutionPlan:
    """The ``ExecutionPlan`` of a ``planned`` decomposition, validated by ``checked_plan``
    (the same validation as a plan file); any other status raises ``ValueError``."""
    if decomposition.status != "planned":
        raise ValueError(f"decomposition is {decomposition.status}, not planned")
    plan = ExecutionPlan(
        producer=PRODUCER,
        created_at=created_at if created_at is not None else utc_now(),
        status="validated",
        plan_run=plan_run,
        task_id=task.id,
        pattern=decomposition.pattern,
        source="decomposed",
        profile=profile.name,
        nodes=list(decomposition.nodes),
        limitations=list(decomposition.limitations),
    )
    return checked_plan(plan, records, profile)


# --- qualification ---------------------------------------------------------------------------


def _candidate_key(candidate: Candidate) -> tuple[int, str, str]:
    return (
        -(candidate.rank_key[0] if candidate.rank_key else 0),
        candidate.provider,
        candidate.capability,
    )


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
            return (
                f"tie between best capabilities of {tops[0].provider}: "
                f"{', '.join(c.capability for c in tops)} at rank {tops[0].rank_key}"
            )
    if len(qualified) > profile.max_providers:
        return (
            f"{len(qualified)} qualified providers "
            f"({', '.join(tops[0].provider for tops in qualified)}); profile "
            f"{profile.name!r} allows {profile.max_providers}"
        )
    return None


_CapKey = tuple[str, str]  # (provider, capability)


def _cap_ref(node_id: str) -> _CapKey | None:
    """``capability:<provider>/<capability>`` -> ``(provider, capability)``."""
    kind, _, key = node_id.partition(":")
    if kind != "capability" or "/" not in key:
        return None
    provider, _, capability = key.partition("/")
    return (provider, capability)


def _graph_constraints(
    best: list[Candidate],
    graph: CapabilityGraph | None,
) -> tuple[dict[tuple[_CapKey, _CapKey], str], list[str]]:
    """Ordering evidence among the qualified capabilities: ``requires`` (the
    required capability first) and produces→consumes chains over declared
    artifact types; plus declared ``conflicts`` pairs (returned separately)."""
    if graph is None:
        return {}, []
    caps = {(c.provider, c.capability) for c in best}
    produces: dict[str, list[_CapKey]] = {}
    consumes: dict[str, list[_CapKey]] = {}
    order: dict[tuple[_CapKey, _CapKey], str] = {}
    conflicts: list[str] = []
    for edge in graph.edges:
        if edge.kind == "produces" or edge.kind == "consumes":
            src, _, artifact = edge.target.partition(":")
            cap = _cap_ref(edge.source)
            if src != "artifact_type" or cap is None or cap not in caps:
                continue
            (produces if edge.kind == "produces" else consumes).setdefault(artifact, []).append(cap)
        elif edge.kind in ("requires", "conflicts"):
            src_cap, dst_cap = _cap_ref(edge.source), _cap_ref(edge.target)
            if src_cap not in caps or dst_cap not in caps or src_cap == dst_cap:
                continue
            if edge.kind == "conflicts":
                conflicts.append(
                    f"{src_cap[0]}/{src_cap[1]} conflicts with "
                    f"{dst_cap[0]}/{dst_cap[1]} ({edge.evidence})"
                )
            else:
                order.setdefault((dst_cap, src_cap), edge.evidence)
    for artifact, makers in produces.items():
        for maker in makers:
            for user in consumes.get(artifact, []):
                if maker != user:
                    order.setdefault(
                        (maker, user),
                        f"{maker[0]}/{maker[1]} produces {artifact} consumed "
                        f"by {user[0]}/{user[1]}",
                    )
    return order, conflicts


def _reachability(constraints: dict[tuple[_CapKey, _CapKey], str]) -> set[tuple[_CapKey, _CapKey]]:
    """Transitive closure of the declared ordering pairs."""
    reach = set(constraints)
    changed = True
    while changed:
        changed = False
        for a, b in list(reach):
            for c, d in list(reach):
                if b == c and (a, d) not in reach:
                    reach.add((a, d))
                    changed = True
    return reach


def _order(
    task: TaskSpec,
    best: list[Candidate],
    constraints: dict[tuple[_CapKey, _CapKey], str],
) -> tuple[list[_Ordered], str | None]:
    """Topological order over ``constraints`` (graph rule); unconstrained ties fall
    back to ``intent-order``. A consecutive pair with no declared relation needs
    both keywords at distinct intent positions, else the decomposition is
    ambiguous (a tier-2 trigger)."""
    tokens = normalize_tokens(task.intent)
    positions: dict[_CapKey, tuple[int, str] | None] = {}
    for candidate in best:
        located = sorted(
            (tokens.index(k.split(" ")[0]), k)
            for k in candidate.matched.keywords
            if k.split(" ")[0] in tokens
        )
        positions[(candidate.provider, candidate.capability)] = located[0] if located else None
    constrained = {key for pair in constraints for key in pair}
    for candidate in best:
        key = (candidate.provider, candidate.capability)
        if positions[key] is None and key not in constrained:
            return [], (
                f"cannot order {candidate.provider}: no keyword of "
                f"{candidate.capability} matched the intent"
            )
    ordered, cycle = _topological(best, positions, constraints)
    if cycle is not None:
        return [], cycle
    reach = _reachability(constraints)
    for first, second in zip(ordered, ordered[1:], strict=False):
        a = (first.candidate.provider, first.candidate.capability)
        b = (second.candidate.provider, second.candidate.capability)
        if (a, b) in reach:
            continue  # declared relations already fix a before b
        if not first.keyword or not second.keyword:
            return [], (
                f"cannot order {first.candidate.provider} and "
                f"{second.candidate.provider}: no declared relation and a "
                "matched keyword is missing"
            )
        if first.position == second.position:
            return [], (
                f"cannot order {first.candidate.provider} and "
                f"{second.candidate.provider}: keywords '{first.keyword}' and "
                f"'{second.keyword}' start at the same position {first.position}"
            )
    return ordered, None


def _topological(
    best: list[Candidate],
    positions: dict[_CapKey, tuple[int, str] | None],
    constraints: dict[tuple[_CapKey, _CapKey], str],
) -> tuple[list[_Ordered], str | None]:
    """Kahn over ``constraints``; the ready set ordered by (intent position, provider)."""
    candidates = {(c.provider, c.capability): c for c in best}
    incoming: dict[_CapKey, set[_CapKey]] = {key: set() for key in candidates}
    for before, after in constraints:
        incoming[after].add(before)

    def _ready_key(k: _CapKey) -> tuple[int, str]:
        located = positions[k]
        return (located[0] if located is not None else 1 << 30, k[0])

    ordered: list[_Ordered] = []
    while incoming:
        ready = sorted(k for k, deps in incoming.items() if not deps)
        if not ready:
            cycle = ", ".join(f"{p}/{c}" for p, c in sorted(incoming))
            return [], f"conflicting dependency evidence: cycle involving {cycle}"
        key = min(ready, key=_ready_key)
        located = positions[key]
        ordered.append(_Ordered(candidates[key], *(located or (0, ""))))
        del incoming[key]
        for deps in incoming.values():
            deps.discard(key)
    return ordered, None


# --- nodes -----------------------------------------------------------------------------------


def _capability(
    records: Mapping[str, RegistryRecord], provider: str, capability: str
) -> Capability | None:
    record = records.get(provider)
    resolved = record.manifest.resolve(capability) if record and record.manifest else None
    return resolved[0] if resolved is not None else None


def _action(task: TaskSpec, capability: Capability) -> str:
    requested = task.requested_action
    return (
        requested if requested and requested in capability.actions else (capability.default_action)
    )


def _targets(
    task: TaskSpec, candidate: Candidate | None, descriptor: WorkspaceDescriptor, files: list[str]
) -> list[str]:
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
        found.update(
            t.repository
            for t in descriptor.technologies
            if t.source == "dependency_manifest" and t.name in deps
        )
    if not found:
        return list(task.targets)
    return sorted(found, key=lambda p: () if p == "." else tuple(p.split("/")))


def _pipeline(
    task: TaskSpec,
    ordered: list[_Ordered],
    records: Mapping[str, RegistryRecord],
    descriptor: WorkspaceDescriptor,
    files: list[str],
    constraints: dict[tuple[_CapKey, _CapKey], str],
    reach: set[tuple[_CapKey, _CapKey]],
) -> tuple[PlanNode, ...]:
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
            before = (previous.candidate.provider, previous.candidate.capability)
            after = (candidate.provider, candidate.capability)
            if (before, after) in constraints:
                rule, evidence = GRAPH_ORDER_RULE, constraints[(before, after)]
            elif (before, after) in reach:
                rule, evidence = (
                    GRAPH_ORDER_RULE,
                    f"{before[0]}/{before[1]} precedes {after[0]}/{after[1]} "
                    "via declared relations",
                )
            else:
                rule = INTENT_ORDER_RULE
                evidence = (
                    f"keyword '{previous.keyword}'@{previous.position} < "
                    f"keyword '{item.keyword}'@{item.position}"
                )
            depends_on = [
                PlanDependency(node=f"n{index}", epistemic="inferred", rule=rule, evidence=evidence)
            ]
        nodes.append(
            PlanNode(
                id=f"n{index + 1}",
                role=role,
                provider=candidate.provider,
                capability=candidate.capability,
                action=action,
                targets=_targets(task, candidate, descriptor, files),
                depends_on=depends_on,
                inputs=[d.node for d in depends_on],
            )
        )
    return tuple(nodes)


def _pipeline_decision(
    decision: RoutingDecision, nodes: tuple[PlanNode, ...], records: Mapping[str, RegistryRecord]
) -> RoutingDecision:
    selected = [
        Selection(
            provider=n.provider,
            capability=n.capability,
            action=n.action,
            role="primary" if i == 0 else "specialist",
        )
        for i, n in enumerate(nodes)
    ]
    low = sorted(
        {
            f"capability_state:{c.state}"
            for n in nodes
            if (c := _capability(records, n.provider, n.capability)) is not None
            and c.state in LOW_CONFIDENCE_STATES
        }
    )
    chain = " -> ".join(f"{n.provider}/{n.capability}" for n in nodes)
    return replace(
        decision,
        status="routed",
        pattern="pipeline",
        selected=selected,
        reason=f"decomposed into {len(nodes)} nodes by rule {INTENT_ORDER_RULE}: {chain}",
        confidence=Confidence(
            level="low" if low else "high",
            measured_signals=list(decision.confidence.measured_signals),
            unresolved=low,
        ),
    )


def _single(
    task: TaskSpec,
    decision: RoutingDecision,
    records: Mapping[str, RegistryRecord],
    descriptor: WorkspaceDescriptor,
    files: list[str],
    limitations: tuple[str, ...],
) -> Decomposition:
    if decision.status != "routed":
        return Decomposition(
            status=decision.status,
            decision=decision,
            nodes=(),
            pattern="route",
            limitations=limitations,
        )
    selection = decision.selected[0]
    candidate = next(
        (
            c
            for c in decision.candidates
            if c.provider == selection.provider and c.capability == selection.capability
        ),
        None,
    )
    node = PlanNode(
        id="n1",
        role="standalone",
        provider=selection.provider,
        capability=selection.capability,
        action=selection.action,
        targets=_targets(task, candidate, descriptor, files),
    )
    return Decomposition(
        status="planned",
        decision=replace(decision, pattern="route"),
        nodes=(node,),
        pattern="route",
        limitations=limitations,
    )


def _ambiguous(decision: RoutingDecision, issue: str) -> Decomposition:
    ambiguous = replace(
        decision,
        status="ambiguous",
        pattern="pipeline",
        selected=[],
        reason=f"ambiguous: {issue}",
        confidence=Confidence(
            level="low",
            measured_signals=list(decision.confidence.measured_signals),
            unresolved=[issue],
        ),
    )
    return Decomposition(
        status="ambiguous", decision=ambiguous, nodes=(), pattern="pipeline", limitations=()
    )
