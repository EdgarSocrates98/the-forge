"""DecisionRecord composition for ``debate`` plans (Cycle 3 Wave E, E3/E4).

A debate is expensive and rare — never the default: proposer nodes (independent)
run their bounded proposal, the referee node depends on all of them and receives
their handoff, and the core composes an auditable ``DecisionRecord`` from the
executions. The referee's choice is a documented convention, verifiable by the
core: evidence ``id="decision"`` whose ``claim`` is the chosen proposer's node id
(and whose ``subject`` may carry the rationale). The core never invents the
choice — an absent or invalid decision yields ``chosen="unresolved"`` with the
reason in limitations.
"""

from collections.abc import Sequence
from typing import Final, Literal

from theforge.contracts.canonical import utc_now
from theforge.contracts.plan import (
    DecisionOption,
    DecisionRecord,
    ExecutionPlan,
    PlanNode,
)
from theforge.contracts.task import TaskSpec
from theforge.meta import PRODUCER
from theforge.planning.execution import NodeExecution

__all__ = ["DECISION_EVIDENCE_ID", "compose_decision"]

# The referee declares its choice through evidence with this id (claim = option node).
DECISION_EVIDENCE_ID: Final = "decision"


def compose_decision(
    task: TaskSpec,
    plan: ExecutionPlan,
    executions: Sequence[NodeExecution],
    *,
    created_at: str | None = None,
) -> DecisionRecord:
    """The ``DecisionRecord`` of a debate plan, composed deterministically.

    Options are the proposer nodes in plan order; ``evidence`` names the items the
    referee received (``<node>:<item-id>``); ``tradeoffs`` are the proposer
    findings (``<node>: <id>: <title>``). ``chosen`` is the referee's
    ``decision`` evidence claim when it names a proposer; else ``unresolved``.
    """
    by_id = {e.node.id: e for e in executions}
    proposers = [n for n in plan.nodes if n.role == "proposer"]
    referee_node = next((n for n in plan.nodes if n.role == "referee"), None)

    options = [_option(by_id.get(n.id), n) for n in proposers]
    referee = by_id.get(referee_node.id) if referee_node is not None else None

    evidence: list[str] = []
    if referee is not None and referee.handoff is not None:
        evidence = sorted(
            {
                f"{item.origin.node}:{item.id}"
                for item in referee.handoff.items
                if item.origin.node in {o.node for o in options}
            }
        )

    tradeoffs = sorted(
        f"{e.node.id}: {f.id}: {f.title}"
        for e in executions
        if e.node.role == "proposer" and e.result is not None
        for f in e.result.findings
    )

    limitations: list[str] = []
    unknowns: list[str] = []
    chosen, rationale = "unresolved", ""
    if referee_node is None:
        limitations.append("debate: no referee node in the plan")
    elif referee is None or referee.result is None:
        status = referee.outcome.status if referee is not None else "no execution"
        limitations.append(f"debate: referee did not produce a valid result ({status})")
        unknowns.append("no option was chosen: the referee did not run")
    else:
        declared = [e for e in referee.result.evidence if e.id == DECISION_EVIDENCE_ID]
        if not declared:
            limitations.append(
                f"debate: referee did not declare a decision (evidence id {DECISION_EVIDENCE_ID!r})"
            )
            unknowns.append("no option was chosen: the referee declared none")
        else:
            declared.sort(key=lambda e: (e.claim, e.subject))
            pick = declared[0]
            if pick.claim in {o.node for o in options}:
                chosen, rationale = pick.claim, pick.subject
            else:
                limitations.append(
                    f"debate: referee chose {pick.claim!r}, which is not a proposer node"
                )
                unknowns.append(f"no valid option was chosen: referee named {pick.claim!r}")
    confidence: Literal["high", "low", "unknown"] = (
        "high"
        if chosen != "unresolved" and referee is not None and referee.outcome.status == "ok"
        else "low"
        if chosen != "unresolved"
        else "unknown"
    )
    return DecisionRecord(
        producer=PRODUCER,
        created_at=created_at if created_at is not None else utc_now(),
        plan_run=plan.plan_run,
        referee=referee_node.id if referee_node else "",
        question=task.intent,
        options=options,
        evidence=evidence,
        tradeoffs=tradeoffs,
        chosen=chosen,
        rejected=[o.node for o in options if o.node != chosen] if chosen != "unresolved" else [],
        rationale=rationale,
        confidence=confidence,
        unknowns=unknowns,
        limitations=limitations,
    )


def _option(execution: NodeExecution | None, node: PlanNode) -> DecisionOption:
    status = execution.outcome.status if execution is not None else "skipped"
    run_id = execution.outcome.run_id if execution is not None else None
    claim, position, evidence, risks = "", "", [], []
    if execution is not None and execution.result is not None:
        result = execution.result
        claim = (
            f"status={execution.outcome.status} capability={node.capability} action={node.action}"
        )
        if result.findings:
            position = result.findings[0].title
        evidence = [e.id for e in result.evidence]
        risks = [
            f"{f.id}: {f.title}" for f in result.findings if f.severity in ("high", "critical")
        ]
    return DecisionOption(
        node=node.id,
        provider=node.provider,
        capability=node.capability,
        status=status,
        run_id=run_id,
        claim=claim,
        position=position,
        evidence=evidence,
        risks=risks,
    )
