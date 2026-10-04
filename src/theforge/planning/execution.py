"""In-memory values of a plan execution (never persisted directly).

Shared by the handoff builder, the synthesizer, the graph builder and the plan
executor; what is persisted are the contracts they produce.
"""

from dataclasses import dataclass

from theforge.contracts.handoff import Handoff
from theforge.contracts.plan import NodeOutcome, NodeStatus, PlanNode
from theforge.contracts.result import ExecutionResult
from theforge.contracts.types import Producer


@dataclass(frozen=True, kw_only=True)
class NodeExecution:
    node: PlanNode
    outcome: NodeOutcome
    result: ExecutionResult | None  # re-read from the child run; None without a valid result
    handoff: Handoff | None  # handoff delivered to the node
    provider: Producer | None  # id and version of the provider that ran the node


@dataclass(frozen=True, kw_only=True)
class SourceResult:
    """A valid result of a node declared in another node's ``inputs`` (handoff source)."""

    node: str
    run_id: str
    provider: Producer
    status: NodeStatus
    capability: str
    action: str
    result: ExecutionResult
