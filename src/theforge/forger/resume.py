"""Resume support for plan runs (Cycle 3 Wave F, F1/F2).

``theforge resume <plan_run>`` continues a plan run without repeating nodes whose
recorded outcome is still provably intact. Integrity is the point: a prior node is
reused only when every input it consumed still verifies —

* the recorded ``NodeOutcome`` had a valid status (``ok``/``partial``) and names a
  child run whose on-disk receipt still hashes to the recorded ``receipt_sha256``;
* the child run's own hash chain verifies end to end (``verify_run_hashes`` —
  task, context, result, handoff and verification all match what the receipt
  recorded; ``context`` integrity is exactly that link);
* the provider identity is unchanged: the registry entry's fingerprint today is
  the fingerprint the child receipt recorded, and the manifest hash matches;
* the dependencies are still satisfied and the handoff they would produce now —
  rebuilt with the original plan run and the recorded ``created_at`` — is byte
  identical to the one the child consumed (``inputs.handoff_sha256``), which also
  proves the upstream results are the same artifacts.

Any doubt re-executes the node; the reason is a plan limitation. Reused nodes
keep their original child ``run_id`` (evidence is not re-stamped) and surface
``reused``/``attempts=0`` on the recorded outcome.
"""

from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any, Final

from theforge.contracts.base import from_dict, to_dict
from theforge.contracts.canonical import sha256_of
from theforge.contracts.handoff import Handoff
from theforge.contracts.plan import (
    ExecutionPlan,
    NodeOutcome,
    NodeStatus,
    PlanNode,
)
from theforge.contracts.receipt import ExecutionReceipt
from theforge.contracts.result import ExecutionResult
from theforge.contracts.types import Producer
from theforge.contracts.verification import VerificationResult
from theforge.explain.hashcheck import verify_run_hashes
from theforge.planning.execution import NodeExecution, SourceResult
from theforge.planning.handoff import build_handoff
from theforge.registry.identity import fingerprint
from theforge.registry.registry import RegistryRecord
from theforge.runs.store import RunStore

__all__ = ["prior_outcomes", "reuse_execution"]

_VALID: Final = frozenset({"ok", "partial"})


def prior_outcomes(store: RunStore, run_id: str) -> dict[str, NodeOutcome]:
    """The per-node outcomes a prior plan run recorded.

    ``plan-result`` is authoritative; when the run died mid-plan it is absent and
    ``plan-state`` is the durable snapshot instead (``succeeded`` nodes become
    reusable candidates). Anything unreadable yields ``{}`` — resume then just
    re-executes every node.
    """
    result = store.read_optional(run_id, "plan-result")
    if result is not None:
        try:
            nodes = result.get("nodes") or []
            return {
                n["node"]: _outcome(n)
                for n in nodes
                if isinstance(n, dict) and isinstance(n.get("node"), str)
            }
        except (KeyError, TypeError):
            return {}
    state = store.read_optional(run_id, "plan-state")
    if state is None:
        return {}
    outcomes: dict[str, NodeOutcome] = {}
    for entry in state.get("nodes") or []:
        if not isinstance(entry, dict) or not isinstance(entry.get("node"), str):
            continue
        if entry.get("state") == "succeeded":
            # A crashed snapshot keeps no receipt hash; integrity is still proven
            # by the child's own chain plus the result hash below.
            outcomes[entry["node"]] = NodeOutcome(
                node=entry["node"],
                status="ok",
                run_id=entry.get("run_id"),
                result_sha256=entry.get("result_sha256"),
            )
    return outcomes


def _outcome(raw: dict[str, Any]) -> NodeOutcome:
    """A ``NodeOutcome`` re-read from a persisted plan-result node entry."""
    return from_dict(NodeOutcome, raw)


def reuse_execution(
    store: RunStore,
    plan: ExecutionPlan,
    node: PlanNode,
    prior: NodeOutcome | None,
    sources: Sequence[SourceResult],
    records: Mapping[str, RegistryRecord],
) -> tuple[NodeExecution | None, str | None]:
    """The re-hydrated ``NodeExecution`` of a resumable node, or ``(None, why)``.

    ``why`` is the invalidation reason for the plan's limitations.
    """
    if prior is None or prior.run_id is None:
        return None, "no prior outcome"
    if prior.status not in _VALID:
        return None, f"prior status {prior.status!r} has no valid result"
    child = prior.run_id
    receipt = store.read_optional(child, "receipt")
    if receipt is None:
        return None, "prior child run missing"
    if (
        store.persisted_sha256(child, "receipt") != prior.receipt_sha256
        and prior.receipt_sha256 is not None
    ):
        return None, "prior child receipt diverged"
    try:
        receipt_obj = store.read_contract(child, "receipt", ExecutionReceipt)
    except Exception:
        return None, "prior child receipt unreadable"
    if verify_run_hashes(store, child).divergences:
        return None, "prior child run integrity diverged"
    if receipt_obj.status not in _VALID:
        # The child receipt itself is the outcome truth — a ``plan-state``
        # fallback only knows "succeeded"; a diverging status is not reusable.
        return None, f"prior child receipt status {receipt_obj.status!r}"
    if prior.result_sha256 is not None and receipt_obj.result_sha256 != prior.result_sha256:
        return None, "prior child result diverged"
    identity = _provider_identity(receipt_obj, node, records)
    if identity is not None:
        return None, identity
    try:
        result = store.read_contract(child, "result", ExecutionResult)
    except Exception:
        return None, "prior child result unreadable"
    try:
        verification = (
            store.read_contract(child, "verification", VerificationResult)
            if receipt_obj.verification_sha256 is not None
            else None
        )
    except Exception:
        verification = None  # integrity of its hash already ran above
    handoff, note = _handoff_integrity(store, plan, node, sources, records, receipt_obj)
    if note is not None:
        return None, note
    status: NodeStatus = "ok" if receipt_obj.status == "ok" else "partial"
    outcome = replace(
        prior,
        status=status,
        reused=True,
        attempts=0,
        receipt_sha256=prior.receipt_sha256 or store.persisted_sha256(child, "receipt"),
    )
    provider = receipt_obj.provider
    return NodeExecution(
        node=node,
        outcome=outcome,
        result=result,
        handoff=handoff,
        verification=verification,
        reached_execute=False,
        provider=Producer(id=provider.id, version=provider.version) if provider else None,
    ), None


def _provider_identity(
    receipt: ExecutionReceipt, node: PlanNode, records: Mapping[str, RegistryRecord]
) -> str | None:
    """Provider mismatch reason, or None when the identity is unchanged (F2)."""
    provider = receipt.provider
    record = records.get(node.provider)
    if provider is None:
        return "prior run recorded no provider"
    if record is None:
        return f"provider {node.provider!r} is no longer registered"
    if provider.id != record.entry.id:
        return f"provider id {provider.id!r} != node provider {record.entry.id!r}"
    if (
        provider.fingerprint is not None
        and provider.fingerprint != fingerprint(record.entry).digest
    ):
        return "provider entry fingerprint changed"
    if (
        provider.manifest_sha256 is not None
        and record.manifest_sha256 is not None
        and provider.manifest_sha256 != record.manifest_sha256
    ):
        return "provider manifest changed"
    if (
        provider.surface_fingerprint is not None
        and record.surface is not None
        and provider.surface_fingerprint != record.surface.surface_fingerprint
    ):
        return "provider declared surface changed"
    return None


def _handoff_integrity(
    store: RunStore,
    plan: ExecutionPlan,
    node: PlanNode,
    sources: Sequence[SourceResult],
    records: Mapping[str, RegistryRecord],
    receipt: ExecutionReceipt,
) -> tuple[Handoff | None, str | None]:
    """The child's recorded handoff when it still rebuilds identically (F2).

    The handoff is rebuilt with the original ``plan.plan_run`` and the recorded
    ``created_at``, so identical inputs reproduce identical bytes; the result is
    compared against the ``handoff_sha256`` the child receipt recorded.
    """
    if not node.inputs:
        if receipt.inputs.handoff_sha256 is not None:
            return None, "prior run recorded a handoff but the node declares no inputs"
        return None, None
    delivered = store.read_optional(receipt.run_id, "handoff")
    if delivered is None:
        return None, "prior handoff artifact missing"
    try:
        delivered_obj = store.read_contract(receipt.run_id, "handoff", Handoff)
    except Exception:
        return None, "prior handoff artifact unreadable"
    rebuilt = build_handoff(
        plan.plan_run, node, sources, records=records, created_at=delivered_obj.created_at
    )
    if rebuilt is None:
        return None, "handoff would now be empty (upstream sources lost)"
    if sha256_of(to_dict(rebuilt)) != receipt.inputs.handoff_sha256:
        return None, "recomputed handoff differs from the recorded one"
    return delivered_obj, None
