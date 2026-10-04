"""Execution order of a plan and dependency blocking (3.1, 3.4).

Pure functions over the plan content: the same nodes and dependencies give the same
order whatever their declaration order.
"""

import heapq
from collections.abc import Mapping

from theforge.contracts.plan import ExecutionPlan


def topological_order(plan: ExecutionPlan) -> list[str]:
    """Node ids in dependency order (Kahn); ready nodes are taken by id (3.1).

    Dependencies on nodes absent from the plan are ignored (``validate_plan_structure``
    reports them); a cycle raises ``ValueError`` since a cyclic plan is never executed.
    """
    pending: dict[str, set[str]] = {node.id: set() for node in plan.nodes}
    for node in plan.nodes:
        pending[node.id].update(d.node for d in node.depends_on if d.node in pending)
    dependents: dict[str, list[str]] = {nid: [] for nid in pending}
    for nid, deps in pending.items():
        for dep in deps:
            dependents[dep].append(nid)
    ready = [nid for nid, deps in pending.items() if not deps]
    heapq.heapify(ready)
    order: list[str] = []
    while ready:
        done = heapq.heappop(ready)
        order.append(done)
        for nid in dependents[done]:
            pending[nid].discard(done)
            if not pending[nid]:
                heapq.heappush(ready, nid)
    if len(order) != len(pending):
        cyclic = sorted(set(pending) - set(order))
        raise ValueError(f"dependency cycle among: {', '.join(cyclic)}")
    return order


def blocked_by(node: str, plan: ExecutionPlan, failed: Mapping[str, str]) -> str | None:
    """The first ancestor of ``node``, in topological order, without a valid result (3.4).

    ``failed`` maps the nodes without a valid result (failed or skipped) to their status;
    ancestors are followed transitively through ``depends_on``. None when no ancestor
    failed (descendants and independent nodes never block).
    """
    deps = {n.id: [d.node for d in n.depends_on] for n in plan.nodes}
    ancestors: set[str] = set()
    stack = list(deps.get(node, []))
    while stack:
        current = stack.pop()
        if current in ancestors or current not in deps:
            continue
        ancestors.add(current)
        stack.extend(deps[current])
    return next((nid for nid in topological_order(plan)
                 if nid in ancestors and nid in failed), None)
