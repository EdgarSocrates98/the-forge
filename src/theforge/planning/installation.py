"""Installation: the planning-only ``InstallationPlan`` of what is missing to run a plan.

Pure function over data already gathered by the caller (registry records and the health
outcome of each distinct provider, consulted once during planning): nothing is
downloaded, installed nor executed here (10.6). Items, in candidate order (10.5):

1. a candidate provider absent from the registry (state ``absent``) or whose registry
   state is ``invalid``, ``unreachable`` or ``incompatible`` -> ``source="registry"``,
   reason and action = the registry detail;
2. otherwise, a candidate whose health is ``unavailable`` or ``error`` ->
   ``source="health"``, ``state="unavailable"``, reason = ``error.detail``, action =
   ``error.unlock`` or else the detail.

Candidates are the providers referenced by the plan nodes (first-reference order, with
the referencing node ids) or, without a plan (decomposition), every registered provider
sorted by id. No item -> no plan, so a run holds at most one ``InstallationPlan``.
"""

from collections.abc import Mapping
from typing import Final

from theforge.contracts.base import from_dict, to_dict
from theforge.contracts.canonical import utc_now
from theforge.contracts.installation import InstallationItem, InstallationPlan
from theforge.contracts.plan import ExecutionPlan
from theforge.meta import PRODUCER
from theforge.registry.health import HealthOutcome
from theforge.registry.registry import RegistryRecord
from theforge.security.redact import redact

__all__ = ["ABSENT_STATE", "build_installation_plan"]

ABSENT_STATE: Final = "absent"  # referenced provider with no registry record
_REGISTRY_STATES: Final = frozenset({"invalid", "unreachable", "incompatible"})
_HEALTH_STATUSES: Final = frozenset({"unavailable", "error"})


def build_installation_plan(
    run_id: str,
    plan: ExecutionPlan | None,
    records: Mapping[str, RegistryRecord],
    health: Mapping[str, HealthOutcome],
    *,
    created_at: str | None = None,
) -> InstallationPlan | None:
    """The run's ``InstallationPlan``, already redacted, or ``None`` when nothing is missing."""
    items = [
        item
        for provider, nodes in _candidates(plan, records).items()
        if (item := _item(provider, nodes, records.get(provider), health.get(provider))) is not None
    ]
    if not items:
        return None
    built = InstallationPlan(
        producer=PRODUCER,
        created_at=created_at if created_at is not None else utc_now(),
        run_id=run_id,
        items=items,
    )
    return from_dict(InstallationPlan, redact(to_dict(built)), strict=True)


def _candidates(
    plan: ExecutionPlan | None, records: Mapping[str, RegistryRecord]
) -> dict[str, list[str]]:
    if plan is None:
        return {provider: [] for provider in sorted(records)}
    by_provider: dict[str, list[str]] = {}
    for node in plan.nodes:
        by_provider.setdefault(node.provider, []).append(node.id)
    return by_provider


def _item(
    provider: str, nodes: list[str], record: RegistryRecord | None, outcome: HealthOutcome | None
) -> InstallationItem | None:
    if record is None:
        detail = f"{provider} is not registered; add it to providers.toml"
        return InstallationItem(
            provider=provider,
            state=ABSENT_STATE,
            reason=detail,
            suggested_action=detail,
            source="registry",
            nodes=nodes,
        )
    if record.state in _REGISTRY_STATES:
        detail = record.error or f"{provider} is {record.state}"
        return InstallationItem(
            provider=provider,
            state=record.state,
            reason=detail,
            suggested_action=detail,
            source="registry",
            nodes=nodes,
        )
    if outcome is not None and outcome.status in _HEALTH_STATUSES:
        detail = outcome.error.detail if outcome.error else f"health {outcome.status}"
        action = (outcome.error.unlock if outcome.error else None) or detail
        return InstallationItem(
            provider=provider,
            state="unavailable",
            reason=detail,
            suggested_action=action,
            source="health",
            nodes=nodes,
        )
    return None
