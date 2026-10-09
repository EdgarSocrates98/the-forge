"""Cross-provider economy aggregation for a plan run (Wave F / Phase 21).

``compose_economy`` collects the ``ProviderEconomyReceipt`` each node result
carried and rolls them up deterministically. Totals sum only compatible
values: ``not_applicable`` contributes nothing, one ``unresolved`` contributor
blocks that metric's sum, and two receipts reporting the same native run with
different values are a named ``conflict`` — never a silent average, and never
a zero standing in for unknown.
"""

from collections.abc import Sequence

from theforge.contracts.canonical import utc_now
from theforge.contracts.economy import (
    ECONOMY_METRICS,
    EconomyMetric,
    EconomyRollup,
    NodeEconomy,
    ProviderEconomyReceipt,
)
from theforge.meta import PRODUCER
from theforge.planning.execution import NodeExecution

__all__ = ["compose_economy"]


def compose_economy(
    plan_run: str, executions: Sequence[NodeExecution], *, created_at: str | None = None
) -> EconomyRollup | None:
    """The plan run's ``EconomyRollup``, or None when no node reported economy.

    ``receipts`` keeps each reporting node's provider accounting verbatim, in
    plan order; ``totals`` aggregates each metric under the never-silent rules.
    """
    receipts = [
        NodeEconomy(node=e.node.id, receipt=e.result.provider_economy)
        for e in executions
        if e.result is not None and e.result.provider_economy is not None
    ]
    if not receipts:
        return None
    conflicts = _conflicts(receipts)
    limitations: list[str] = []
    totals = {name: _total(name, receipts, conflicts, limitations) for name in ECONOMY_METRICS}
    return EconomyRollup(
        producer=PRODUCER,
        created_at=created_at or utc_now(),
        plan_run=plan_run,
        receipts=receipts,
        totals=totals,
        conflicts=conflicts,
        limitations=limitations,
    )


def _conflicts(receipts: Sequence[NodeEconomy]) -> list[str]:
    """Receipts that cite the same native ``(provider, run)`` but disagree.

    A shared native-run ref means the accounting describes one underlying run:
    differing measured/estimated values for the same metric cannot both be
    right — the conflict is named, and that metric stays unresolved.
    """
    by_run: dict[tuple[str, str], list[ProviderEconomyReceipt]] = {}
    for entry in receipts:
        receipt = entry.receipt
        if receipt.run:
            by_run.setdefault((receipt.provider, receipt.run), []).append(receipt)
    conflicts: list[str] = []
    for (provider, run), group in sorted(by_run.items()):
        if len(group) < 2:
            continue
        for name in ECONOMY_METRICS:
            values = {
                getattr(receipt, name).value
                for receipt in group
                if getattr(receipt, name).status in ("measured", "estimated")
            }
            if len(values) > 1:
                conflicts.append(
                    f"{provider} run {run}: conflicting {name} "
                    f"({', '.join(str(v) for v in sorted(values))})"
                )
    return conflicts


def _total(
    name: str, receipts: Sequence[NodeEconomy], conflicts: Sequence[str], limitations: list[str]
) -> EconomyMetric:
    """One metric rolled up: sum compatible values; unresolved blocks the sum."""
    measured = [
        entry
        for entry in receipts
        if getattr(entry.receipt, name).status in ("measured", "estimated")
    ]
    blocked = [
        entry.node for entry in receipts if getattr(entry.receipt, name).status == "unresolved"
    ]
    conflicted = any(name in conflict for conflict in conflicts)
    if not measured:
        # Nobody measured it — everything is not_applicable and/or unresolved.
        return EconomyMetric(status="unresolved" if blocked or conflicted else "not_applicable")
    if blocked or conflicted:
        why = (
            f"unresolved for node(s) {', '.join(blocked)}"
            if blocked
            else "conflicting sources (see conflicts)"
        )
        limitations.append(f"{name}: not summed — {why}")
        return EconomyMetric(status="unresolved")
    return EconomyMetric(
        value=sum(getattr(entry.receipt, name).value or 0.0 for entry in measured),
        status=(
            "measured"
            if all(getattr(entry.receipt, name).status == "measured" for entry in measured)
            else "estimated"
        ),
    )
