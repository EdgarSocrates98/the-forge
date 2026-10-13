"""Tier-2 semantic planner: propose, then validate — the validator stays sovereign.

When the deterministic tiers cannot decompose (``ambiguous``), a provider whose
manifest declares a capability with ``proposes_plans: true`` may answer the
``plan`` op with ``purpose="proposal"``: a ``SemanticPlanProposal`` choosing only
among the routing-eligible ``options`` the core sent (C3, C5). The call runs on
the same hardened surface as ``request_estimate``: fresh cwd, minimal
environment, timeout and a ``producer`` check.

The proposal is never executed as received: ``proposal_plan`` maps it to an
``ExecutionPlan`` (``source="semantic"``) and ``check_plan`` applies the same
registry, structure and profile rules as any other plan (C4). Structural
problems of the proposal itself (duplicate refs, dangling dependencies, bad
node ids) become ``Codes.PLAN_INVALID`` violations before that. A failed or
unusable proposal yields a limitation, never a raised error: planning degrades
to the deterministic ``ambiguous`` outcome.
"""

from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Final

from theforge.contracts import ContractError, Producer, from_dict, to_dict
from theforge.contracts.canonical import utc_now
from theforge.contracts.codes import Codes
from theforge.contracts.integrity import check_producer
from theforge.contracts.manifest import Capability
from theforge.contracts.plan import (
    PLAN_NODE_ID,
    ExecutionPlan,
    NodeRole,
    PlanDependency,
    PlanNode,
    PlanRequest,
    PlanViolation,
    SemanticPlanNode,
    SemanticPlanOption,
    SemanticPlanProposal,
)
from theforge.contracts.routing import RoutingDecision
from theforge.contracts.task import TaskSpec
from theforge.contracts.types import PlanPattern
from theforge.meta import PRODUCER
from theforge.planning.validate import checked_plan
from theforge.protocol import SubprocessTransport, TransportError, TransportFactory
from theforge.registry.health import HEALTH_TIMEOUT
from theforge.registry.registry import RegistryRecord, provider_cwd
from theforge.routing.router import alias_note, deprecation_note
from theforge.security.redact import redact_text

if TYPE_CHECKING:
    from theforge.profiles import ContextProfile

__all__ = [
    "PROPOSAL_TIMEOUT",
    "options_of",
    "planner_capability",
    "proposal_plan",
    "request_proposal",
]

PROPOSAL_TIMEOUT: Final = HEALTH_TIMEOUT  # same budget as estimate/health (10 s)
_NO_PLANNER: Final = (
    "no provider declares a semantic-planning capability (capability proposes_plans)"
)


def _failed(detail: str) -> tuple[None, str]:
    return None, redact_text(f"proposal: {Codes.PLAN_ESTIMATE}: {detail}")


def planner_capability(
    records: Mapping[str, RegistryRecord],
    *,
    allow_unverified: bool = False,
) -> tuple[RegistryRecord, Capability] | None:
    """The deterministic planner pick: the first ready provider (id order) with a
    ``proposes_plans`` capability (capability id order), honoring trust gates."""
    for pid in sorted(records):
        record = records[pid]
        manifest = record.manifest
        if record.state != "ready" or manifest is None or "plan" not in manifest.ops:
            continue
        if record.entry.trust == "blocked":
            continue
        if record.entry.trust == "unverified" and not allow_unverified:
            continue
        for capability in sorted(manifest.capabilities, key=lambda c: c.id):
            if capability.proposes_plans:
                return record, capability
    return None


def options_of(
    decision: RoutingDecision, records: Mapping[str, RegistryRecord]
) -> list[SemanticPlanOption]:
    """The routing-eligible set a proposal may pick from: every candidate that is
    not ``unsupported``, with its declared actions and relations (C5: the planner
    can only name what exists; the validator re-checks each choice anyway)."""
    options: dict[tuple[str, str], SemanticPlanOption] = {}
    for candidate in decision.candidates:
        if candidate.state == "unsupported":
            continue
        key = (candidate.provider, candidate.capability)
        if key in options:
            continue
        record = records.get(candidate.provider)
        resolved = (
            record.manifest.resolve(candidate.capability)
            if record is not None and record.manifest is not None
            else None
        )
        capability = resolved[0] if resolved is not None else None
        relations = capability.relations if capability is not None else None
        options[key] = SemanticPlanOption(
            provider=candidate.provider,
            capability=candidate.capability,
            actions=list(capability.actions) if capability is not None else [],
            state=candidate.state,
            produces=list(relations.produces) if relations else [],
            consumes=list(relations.consumes) if relations else [],
            requires=list(relations.requires) if relations else [],
            conflicts=list(relations.conflicts) if relations else [],
        )
    return [options[key] for key in sorted(options)]


def request_proposal(
    record: RegistryRecord,
    capability: Capability,
    task: TaskSpec,
    options: list[SemanticPlanOption],
    ambiguity: str,
    *,
    transport_factory: TransportFactory = SubprocessTransport,
    timeout: float = PROPOSAL_TIMEOUT,
    allow_unverified: bool = False,
) -> tuple[SemanticPlanProposal | None, str | None]:
    """``(proposal, None)`` on success, ``(None, limitation)`` otherwise; never raises."""
    manifest = record.manifest
    if record.state != "ready" or manifest is None:
        return _failed(f"{record.entry.id} is {record.state}: {record.error}")
    if "plan" not in manifest.ops:
        return _failed(f"{record.entry.id} does not declare op plan")
    if record.entry.trust == "blocked":
        return _failed(f"{Codes.PROVIDER_BLOCKED}: {record.entry.id} is blocked")
    if record.entry.trust == "unverified" and not allow_unverified:
        return _failed(
            f"{Codes.PROVIDER_UNTRUSTED}: {record.entry.id} is unverified and was not executed"
        )
    payload = to_dict(
        PlanRequest(
            task=task,
            capability=capability.id,
            action=capability.default_action,
            purpose="proposal",
            options=options,
            ambiguity=ambiguity,
        )
    )
    try:
        with provider_cwd() as cwd:
            response = transport_factory(record.entry.argv).call(
                "plan", payload, timeout=timeout, cwd=Path(cwd)
            )
    except TransportError as exc:
        return _failed(f"{exc.code}: {exc.detail}")
    violation = check_producer(
        response.producer,
        expected=Producer(id=record.entry.id, version=manifest.version),
        field="$.producer",
    )
    if violation is not None:
        return _failed(f"{violation.code}: {violation.detail}")
    if response.status != "ok":
        error = response.error
        detail = f"{error.code}: {error.detail}" if error is not None else "no error detail"
        return _failed(f"plan {response.status}: {detail}")
    try:
        proposal = from_dict(SemanticPlanProposal, response.payload, "$.payload")
    except ContractError as exc:
        return _failed(f"{Codes.PROTO_SCHEMA}: {exc}")
    if not isinstance(proposal, SemanticPlanProposal):
        return _failed(f"{Codes.PROTO_SCHEMA}: payload is not a SemanticPlanProposal")
    return proposal, None


def proposal_plan(
    proposal: SemanticPlanProposal,
    task: TaskSpec,
    records: Mapping[str, RegistryRecord],
    profile: "ContextProfile",
    *,
    plan_run: str,
    planner: str,
    created_at: str | None = None,
) -> ExecutionPlan:
    """The ``ExecutionPlan`` (``source="semantic"``) of a proposal, validated by
    ``check_plan`` — invalid structure and unknown providers/capabilities/actions
    are violations, never silently repaired (C4, C5)."""
    early: list[PlanViolation] = []
    refs = [node.ref for node in proposal.nodes]
    for dup in sorted({ref for ref in refs if refs.count(ref) > 1}):
        early.append(
            PlanViolation(
                code=Codes.PLAN_INVALID, node=None, detail=f"proposal: duplicate node ref {dup!r}"
            )
        )
    known = set(refs)
    # Dependencies: node.depends_on plus the dependencies[] edges, deduplicated,
    # each edge's declared rationale kept as the PlanDependency evidence.
    edges: dict[str, dict[str, str]] = {ref: {} for ref in known}
    for node in proposal.nodes:
        for dep in node.depends_on:
            edges.setdefault(node.ref, {})[dep] = node.rationale
    for edge in proposal.dependencies:
        if edge.node not in known:
            early.append(
                PlanViolation(
                    code=Codes.PLAN_INVALID,
                    node=None,
                    detail=f"proposal: dependency node {edge.node!r} has no node",
                )
            )
            continue
        edges.setdefault(edge.node, {})[edge.depends_on] = edge.rationale
    for ref in sorted(edges):
        for missing in sorted(set(edges[ref]) - known):
            early.append(
                PlanViolation(
                    code=Codes.PLAN_INVALID,
                    node=ref,
                    detail=f"proposal: node {ref!r} depends on unknown ref {missing!r}",
                )
            )

    nodes: list[PlanNode] = []
    for node in proposal.nodes:
        if not PLAN_NODE_ID.match(node.ref):
            early.append(
                PlanViolation(
                    code=Codes.PLAN_INVALID,
                    node=node.ref,
                    detail=f"proposal: node ref {node.ref!r} is not a valid plan node id",
                )
            )
        provider = records.get(node.provider)
        resolved = (
            provider.manifest.resolve(node.capability)
            if provider is not None and provider.manifest is not None
            else None
        )
        notes: list[str] = []
        capability = node.capability
        if resolved is not None:
            capability, via_alias = resolved[0].id, resolved[1]
            if via_alias:
                notes.append(alias_note(node.capability, resolved[0], node.provider))
            deprecated = deprecation_note(resolved[0], node.provider)
            if deprecated is not None:
                notes.append(deprecated)
        depends = [
            PlanDependency(
                node=dep,
                epistemic="explicit",
                evidence=(f"semantic proposal by {planner}: {rationale or 'declared'}"),
            )
            for dep, rationale in sorted(edges.get(node.ref, {}).items())
        ]
        nodes.append(
            PlanNode(
                id=node.ref,
                role=node.role or _role(node, edges),
                provider=node.provider,
                capability=capability,
                action=node.action,
                targets=list(node.targets),
                depends_on=depends,
                inputs=list(node.inputs),  # verbatim: the structural validator reports
                limitations=notes,
            )
        )  # inputs outside depends_on; no silent repair
    limitations = [
        f"plan proposed by semantic planner {planner}",
        *proposal.limitations,
        *(f"assumption: {a}" for a in proposal.assumptions),
    ]
    if proposal.confidence is not None and proposal.confidence != "high":
        limitations.append(f"planner confidence: {proposal.confidence}")
    for alternative in proposal.alternatives:
        limitations.append(f"alternative considered: {alternative}")
    plan = ExecutionPlan(
        producer=PRODUCER,
        created_at=created_at if created_at is not None else utc_now(),
        status="validated",
        plan_run=plan_run,
        task_id=task.id,
        pattern=proposal.pattern or _pattern(nodes, edges),
        source="semantic",
        profile=profile.name,
        nodes=nodes,
        limitations=limitations,
        unknowns=list(proposal.unknowns),
    )
    checked = checked_plan(plan, records, profile)
    if not early:
        return checked
    return replace(checked, status="rejected", violations=[*early, *checked.violations])


def _role(node: SemanticPlanNode, edges: dict[str, dict[str, str]]) -> NodeRole:
    if len(edges) <= 1 and not any(edges.values()):
        return "standalone"
    return "consumer" if edges.get(node.ref) else "producer"


def _pattern(nodes: list[PlanNode], edges: dict[str, dict[str, str]]) -> PlanPattern:
    if len(nodes) <= 1:
        return "route"
    return "pipeline" if any(edges.values()) else "parallel"
