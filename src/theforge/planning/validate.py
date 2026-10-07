"""Plan validation against the registry and the profile, and plan files (1.2, 1.3, 1.5, 1.6).

``check_plan`` = the structural violations of ``validate_plan_structure`` plus the
registry-dependent ones, all gathered at once: the same validation for a decomposed plan
and for a plan read from a file. ``load_plan_file`` only parses and normalizes; it never
rejects a plan for registry reasons (``check_plan`` reports them).
"""

import json
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any, Final

from theforge.contracts.base import ContractError, from_dict
from theforge.contracts.canonical import utc_now
from theforge.contracts.codes import Codes
from theforge.contracts.integrity import validate_plan_structure
from theforge.contracts.negotiation import (
    CapabilityNegotiationResult,
    CapabilityRequirement,
)
from theforge.contracts.plan import ExecutionPlan, PlanNode, PlanViolation
from theforge.contracts.types import BudgetProfile
from theforge.errors import UsageError
from theforge.meta import PRODUCER
from theforge.negotiation import negotiate
from theforge.profiles import ContextProfile
from theforge.registry import RegistryRecord
from theforge.routing.router import alias_note, deprecation_note

MAX_PLAN_FILE_BYTES: Final = 1024 * 1024


def check_plan(
    plan: ExecutionPlan,
    records: Mapping[str, RegistryRecord],
    profile: ContextProfile,
    requirement: CapabilityRequirement | None = None,
) -> list[PlanViolation]:
    """Every violation of ``plan``: structural first, then per node (declaration order)
    provider registered and ``ready``, capability resolved by ``ForgeManifest.resolve``
    (canonical id before alias) and not ``unsupported``, action offered; finally the
    distinct providers against ``profile.max_providers`` (1.2, 1.3, 1.5).

    ``requirement`` (cycle 4): a node whose capability is the demanded one is
    additionally negotiated — ``INCOMPATIBLE``/``UNRESOLVED``/``UNSUPPORTED``
    becomes a violation (hard gates bind pinned providers too, §91)."""
    violations = validate_plan_structure(plan)
    for node in plan.nodes:
        detail = _node_problem(node, records)
        if detail is not None:
            violations.append(
                PlanViolation(code=Codes.PLAN_CAPABILITY, node=node.id, detail=detail)
            )
    if requirement is not None:
        for node in plan.nodes:
            detail = _node_requirement_problem(node, requirement, records)
            if detail is not None:
                violations.append(
                    PlanViolation(code=Codes.PLAN_CAPABILITY, node=node.id, detail=detail)
                )
    providers = sorted({node.provider for node in plan.nodes})
    if len(providers) > profile.max_providers:
        violations.append(
            PlanViolation(
                code=Codes.PLAN_LIMIT,
                node=None,
                detail=f"plan uses {len(providers)} providers ({', '.join(providers)}); "
                f"profile {profile.name!r} allows {profile.max_providers}",
            )
        )
    return violations


def checked_plan(
    plan: ExecutionPlan,
    records: Mapping[str, RegistryRecord],
    profile: ContextProfile,
    requirement: CapabilityRequirement | None = None,
) -> ExecutionPlan:
    """``plan`` with ``status``/``violations`` set from ``check_plan`` (rejected <=> any);
    a ``PARTIAL`` negotiation on a requirement-matched node is noted as a plan
    limitation, not a violation — soft degradation is explicit, never hidden."""
    violations = check_plan(plan, records, profile, requirement=requirement)
    notes = (
        [
            note
            for node in plan.nodes
            if (note := _node_fit_note(node, requirement, records)) is not None
        ]
        if requirement is not None
        else []
    )
    return replace(
        plan,
        status="rejected" if violations else "validated",
        violations=violations,
        limitations=[*plan.limitations, *notes],
    )


def _node_problem(node: PlanNode, records: Mapping[str, RegistryRecord]) -> str | None:
    record = records.get(node.provider)
    if record is None:
        return f"node {node.id!r}: provider {node.provider!r} is not registered"
    if record.state != "ready" or record.manifest is None:
        return f"node {node.id!r}: provider {node.provider!r} is not ready ({record.state})"
    resolved = record.manifest.resolve(node.capability)
    if resolved is None:
        return (
            f"node {node.id!r}: provider {node.provider!r} does not declare capability "
            f"{node.capability!r}"
        )
    capability = resolved[0]
    if capability.state == "unsupported":
        return f"node {node.id!r}: capability {capability.id!r} of {node.provider!r} is unsupported"
    if node.action not in capability.actions:
        return (
            f"node {node.id!r}: capability {capability.id!r} of {node.provider!r} does "
            f"not offer action {node.action!r} (actions: {', '.join(capability.actions)})"
        )
    return None


def _node_negotiation(
    node: PlanNode, requirement: CapabilityRequirement, records: Mapping[str, RegistryRecord]
) -> CapabilityNegotiationResult | None:
    """The requirement negotiated against the node's provider — only when the
    node's capability resolves to the demanded one (a per-capability demand
    never bleeds into unrelated nodes)."""
    record = records.get(node.provider)
    manifest = record.manifest if record is not None else None
    if manifest is None:
        return None
    node_resolved = manifest.resolve(node.capability)
    req_resolved = manifest.resolve(requirement.capability)
    if (
        node_resolved is None
        or req_resolved is None
        or record is None
        or node_resolved[0].id != req_resolved[0].id
    ):
        return None
    return negotiate(replace(requirement, capability=req_resolved[0].id), record)


def _node_requirement_problem(
    node: PlanNode, requirement: CapabilityRequirement, records: Mapping[str, RegistryRecord]
) -> str | None:
    result = _node_negotiation(node, requirement, records)
    if result is None or result.state in ("FULL", "PARTIAL"):
        return None
    detail = "; ".join([*result.policy_conflicts, *result.missing])
    return f"node {node.id!r}: requirement negotiates {result.state} on {node.provider!r}" + (
        f" ({detail})" if detail else ""
    )


def _node_fit_note(
    node: PlanNode, requirement: CapabilityRequirement | None, records: Mapping[str, RegistryRecord]
) -> str | None:
    if requirement is None:
        return None
    result = _node_negotiation(node, requirement, records)
    if result is None or result.state != "PARTIAL":
        return None
    return (
        f"requirement partial fit on node {node.id!r} ({node.provider}): "
        f"missing {', '.join(result.missing) or 'undeclared demands'}"
    )


def load_plan_file(
    path: Path,
    records: Mapping[str, RegistryRecord],
    *,
    plan_run: str,
    profile: BudgetProfile,
    created_at: str | None = None,
) -> ExecutionPlan:
    """Read a plan file (JSON, at most ``MAX_PLAN_FILE_BYTES``) strictly (1.6).

    ``plan_run``, ``producer``, ``created_at``, ``status``, ``violations`` and ``source``
    (``"file"``) come from the run (the file's values are replaced, and may be absent); the
    command-line ``profile`` wins over the file's, with a plan limitation when they differ.
    A node capability given by alias becomes the canonical id with the Wave B
    ``capability-alias`` note (and ``capability-deprecated`` when deprecated) in the node
    limitations; an unknown provider or capability is kept for ``check_plan`` to report.
    An unreadable or off-contract file raises ``UsageError`` with ``Codes.PLAN_FILE``.
    """
    data = _read_json(path)
    if not isinstance(data, dict):
        raise _file_error(path, f"expected a JSON object, got {type(data).__name__}")
    # Fields controlled by the run that reads the file (1.6).
    run_values: dict[str, Any] = {
        "plan_run": plan_run,
        "producer": {"id": PRODUCER.id, "version": PRODUCER.version},
        "created_at": created_at if created_at is not None else utc_now(),
        "status": "validated",
        "violations": [],
        "source": "file",
    }
    try:
        plan = from_dict(ExecutionPlan, {**data, **run_values}, strict=True)
    except ContractError as exc:
        raise _file_error(path, str(exc)) from exc
    limitations = list(plan.limitations)
    if plan.profile != profile:
        limitations.append(
            f"profile: plan file profile {plan.profile!r} overridden by "
            f"command line profile {profile!r}"
        )
    nodes = [_canonical_node(node, records) for node in plan.nodes]
    return replace(plan, profile=profile, nodes=nodes, limitations=limitations)


def _canonical_node(node: PlanNode, records: Mapping[str, RegistryRecord]) -> PlanNode:
    record = records.get(node.provider)
    manifest = record.manifest if record is not None else None
    resolved = manifest.resolve(node.capability) if manifest is not None else None
    if resolved is None:
        return node
    capability, via_alias = resolved
    notes = [alias_note(node.capability, capability, node.provider)] if via_alias else []
    deprecated = deprecation_note(capability, node.provider)
    if deprecated is not None:
        notes.append(deprecated)
    if not notes:
        return node
    return replace(node, capability=capability.id, limitations=[*node.limitations, *notes])


def _read_json(path: Path) -> Any:
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_PLAN_FILE_BYTES + 1)
    except OSError as exc:
        raise _file_error(path, f"unreadable ({exc.strerror or type(exc).__name__})") from exc
    if len(raw) > MAX_PLAN_FILE_BYTES:
        raise _file_error(path, f"exceeds {MAX_PLAN_FILE_BYTES} bytes")
    try:
        return json.loads(raw.decode("utf-8"))
    except (ValueError, RecursionError) as exc:
        raise _file_error(path, f"invalid JSON ({exc})") from exc


def _file_error(path: Path, detail: str) -> UsageError:
    return UsageError(f"plan file {path}: {detail}", code=Codes.PLAN_FILE)
