"""Synthesizer: the deterministic synthesis of an executed plan (requirements 5.1-5.4).

The synthesis only restates the structured outputs of the nodes: one entry per node in
the effective execution order (provider, capability, action, status, run, findings
copied with their original ids, evidence counted by its original epistemic status), the
handoffs delivered between nodes, the nodes without a valid result with their reason,
and the limitations and unknowns of each node prefixed by its id. It never creates a
finding, never changes an epistemic status and uses no LLM. Redaction happens when the
plan result that carries it is persisted (5.5).
"""

import copy
from collections.abc import Sequence
from typing import Final

from theforge.contracts.plan import (
    ExecutionPlan,
    Synthesis,
    SynthesisHandoff,
    SynthesisNode,
)
from theforge.planning.execution import NodeExecution

__all__ = ["synthesize"]

# Node statuses that carry a valid result.
_VALID_STATUSES: Final = frozenset({"ok", "partial"})


def synthesize(plan: ExecutionPlan, executions: Sequence[NodeExecution]) -> Synthesis:
    """Synthesis of ``executions``, given in the effective execution order of ``plan``.

    Every plan node must have exactly one execution (a skipped node included); an
    execution of a node outside the plan, a duplicate or a missing node is a caller bug
    (``ValueError``).
    """
    plan_ids = {n.id for n in plan.nodes}
    seen: set[str] = set()
    for execution in executions:
        nid = execution.node.id
        if nid not in plan_ids:
            raise ValueError(f"synthesis: execution of node {nid!r} not in the plan")
        if nid in seen:
            raise ValueError(f"synthesis: duplicate execution of node {nid!r}")
        seen.add(nid)
    missing = sorted(plan_ids - seen)
    if missing:
        raise ValueError(f"synthesis: plan nodes without execution: {', '.join(missing)}")

    nodes: list[SynthesisNode] = []
    handoffs: list[SynthesisHandoff] = []
    failures: list[str] = []
    limitations: list[str] = []
    unknowns: list[str] = []
    for execution in executions:
        nodes.append(_node(execution))
        handoffs.extend(_handoffs(execution))
        failure = _failure(execution)
        if failure is not None:
            failures.append(failure)
        limitations.extend(_prefixed(execution.node.id, _node_limitations(execution)))
        if execution.result is not None:
            unknowns.extend(_prefixed(execution.node.id, execution.result.unknowns))
    return Synthesis(
        nodes=nodes,
        handoffs=handoffs,
        failures=failures,
        limitations=limitations,
        unknowns=unknowns,
    )


def _node(execution: NodeExecution) -> SynthesisNode:
    node, outcome, result = execution.node, execution.outcome, execution.result
    counts: dict[str, int] = {}
    findings = []
    if result is not None:
        for evidence in result.evidence:
            # Counted under its original status: the synthesis never upgrades it.
            counts[evidence.epistemic] = counts.get(evidence.epistemic, 0) + 1
        findings = copy.deepcopy(list(result.findings))
    return SynthesisNode(
        node=node.id,
        provider=node.provider,
        capability=node.capability,
        action=node.action,
        status=outcome.status,
        run_id=outcome.run_id,
        findings=findings,
        evidence_by_epistemic={k: counts[k] for k in sorted(counts)},
    )


def _handoffs(execution: NodeExecution) -> list[SynthesisHandoff]:
    """One entry per declared input of a node that received a handoff (0 items if none)."""
    handoff = execution.handoff
    if handoff is None:
        return []
    per_source: dict[str, int] = {}
    for item in handoff.items:
        per_source[item.origin.node] = per_source.get(item.origin.node, 0) + 1
    return [
        SynthesisHandoff(
            source=source,
            target=execution.node.id,
            items=per_source.get(source, 0),
            truncated=handoff.truncated,
        )
        for source in execution.node.inputs
    ]


def _failure(execution: NodeExecution) -> str | None:
    """``"<node>: <status> <code>: <detail>"`` for a node without a valid result."""
    outcome = execution.outcome
    if outcome.status in _VALID_STATUSES and execution.result is not None:
        return None
    prefix = f"{outcome.node}: {outcome.status}"
    if outcome.error is not None:
        return f"{prefix} {outcome.error.code}: {outcome.error.detail}"
    if outcome.status == "skipped" and outcome.blocked_by is not None:
        return f"{prefix}: blocked by {outcome.blocked_by}"
    return f"{prefix}: no valid result"


def _node_limitations(execution: NodeExecution) -> list[str]:
    """Plan-node notes, then the delivered handoff's, then the result's; deduplicated."""
    notes = list(execution.node.limitations)
    if execution.handoff is not None:
        notes.extend(execution.handoff.limitations)
    if execution.result is not None:
        notes.extend(execution.result.limitations)
    return list(dict.fromkeys(notes))


def _prefixed(node: str, notes: Sequence[str]) -> list[str]:
    return [f"{node}: {note}" for note in dict.fromkeys(notes)]
