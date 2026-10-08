"""Remote-execution trust model (Cycle 5, Waves K/L).

There is deliberately **no transport here**: remote execution is never
"ssh and run". This module implements the policy layer the contracts bind to:

- ``RemotePolicy`` — an explicit, deny-by-default allowlist (the only way a
  request gets ``policy_decision="allow"``); policy is monotonic, per the
  in-toto principle: nothing the caller omits can turn deny into allow.
- ``evaluate_remote_policy`` — deterministic gate; records every refusal
  reason. Trust floors differ by target type: ``remote-forge`` needs
  ``verified``, ``a2a-agent`` needs ``org-approved`` (§87 — an external A2A
  agent can never promote itself).
- ``build_request`` — assembles a fully-bound ``RemoteExecutionRequest``;
  raises ``ContractError`` unless the gate allowed.
- ``accept_receipt`` — replay binding: the receipt must hash-bind the exact
  request, echo the same target/provider/identity, and cover every expected
  artifact; violations are returned, never swallowed.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Literal

from theforge.contracts.base import ContractError, to_dict
from theforge.contracts.canonical import sha256_of, utc_now
from theforge.contracts.remote import RemoteExecutionReceipt, RemoteExecutionRequest
from theforge.contracts.targets import (
    ExecutionTarget,
    TargetRequirement,
)
from theforge.meta import PRODUCER

__all__ = [
    "POLICY_FILE",
    "RemotePolicy",
    "accept_receipt",
    "build_request",
    "evaluate_remote_policy",
    "load_policy",
    "request_sha256",
]

POLICY_FILE: Final = "remote-policy.toml"

_REMOTE_TYPES: Final = frozenset({"remote-forge", "a2a-agent"})
_TRUST_RANK: Final = {"unverified": 0, "verified": 1, "org-approved": 2}
# Trust floor per remote target type (§87): an A2A agent is external by
# definition — only org policy promotes it. remote-forge needs an identity
# that some verification step established.
_MIN_TRUST: Final = {"remote-forge": "verified", "a2a-agent": "org-approved"}


@dataclass(frozen=True, kw_only=True)
class RemotePolicy:
    """Deny-by-default remote policy. Empty ``allowed_target_ids`` = deny all.

    ``policy_ref`` is the auditable identity of the policy that decided —
    an allowed request cannot exist without it (the contract enforces).
    """

    policy_ref: str = ""
    allowed_target_ids: list[str] = field(default_factory=list)
    allowed_identity_refs: list[str] = field(default_factory=list)
    max_data_classification: Literal["public", "internal"] = "internal"
    require_healthy: bool = True


def load_policy(path: Path | None) -> RemotePolicy:
    """Optional ``remote-policy.toml``; absent file = deny-all policy."""
    if path is None or not path.is_file():
        return RemotePolicy(policy_ref="", allowed_target_ids=[])
    import tomllib

    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    pol = raw.get("remote", raw).get("policy", raw.get("policy", {}))
    return RemotePolicy(
        policy_ref=str(pol.get("policy_ref", "")),
        allowed_target_ids=sorted(str(i) for i in pol.get("allowed_target_ids", [])),
        allowed_identity_refs=sorted(
            str(i) for i in pol.get("allowed_identity_refs", [])
        ),
        max_data_classification=pol.get("max_data_classification", "internal"),
        require_healthy=bool(pol.get("require_healthy", True)),
    )


def evaluate_remote_policy(
    target: ExecutionTarget,
    requirement: TargetRequirement,
    policy: RemotePolicy,
) -> tuple[Literal["allow", "deny"], list[str]]:
    """Deterministic, monotonic gate. Deny unless every condition holds."""
    reasons: list[str] = []
    if target.type not in _REMOTE_TYPES:
        reasons.append(f"type {target.type!r} is not remote")
    if target.id not in policy.allowed_target_ids:
        reasons.append(f"target {target.id!r} not in allowed_target_ids")
    if (
        policy.allowed_identity_refs
        and target.identity_ref not in policy.allowed_identity_refs
    ):
        reasons.append(f"identity {target.identity_ref!r} not in allowed_identity_refs")
    if target.network != "egress":
        reasons.append("remote target without egress network")
    if policy.require_healthy and target.health != "healthy":
        reasons.append(f"health {target.health!r} (policy requires healthy)")
    floor = _MIN_TRUST.get(target.type, "org-approved")
    if target.type == "a2a-agent":
        # Contract-capped at 'unverified': org promotion is expressed by the
        # policy allowlist + identity pinning, not by the target record.
        if target.id not in policy.allowed_target_ids or (
            policy.allowed_identity_refs
            and target.identity_ref not in policy.allowed_identity_refs
        ):
            reasons.append("a2a-agent requires explicit org promotion in policy")
    elif _TRUST_RANK[target.trust] < _TRUST_RANK[floor]:
        reasons.append(f"trust {target.trust!r} below required {floor!r}")
    if not target.admits(requirement.data_classification):
        reasons.append(
            f"data_classification {requirement.data_classification!r} not admitted"
        )
    # Remote ceiling: only public/internal can ever leave the boundary, and the
    # policy can lower it further (e.g. public-only).
    _CLASS_RANK = {"public": 0, "internal": 1}
    if requirement.data_classification not in _CLASS_RANK or _CLASS_RANK[
        requirement.data_classification
    ] > _CLASS_RANK[policy.max_data_classification]:
        reasons.append(
            f"data_classification {requirement.data_classification!r} exceeds "
            f"policy ceiling {policy.max_data_classification!r}"
        )
    if requirement.locality == "local" or requirement.locality == "isolated":
        reasons.append(f"locality {requirement.locality!r} forbids remote")
    return ("deny" if reasons else "allow"), sorted(set(reasons))


def request_sha256(request: RemoteExecutionRequest) -> str:
    """Canonical hash of the request — the replay binding receipts must match."""
    return sha256_of(to_dict(request))


def build_request(
    *,
    target: ExecutionTarget,
    requirement: TargetRequirement,
    policy: RemotePolicy,
    task_sha256: str,
    context_sha256: str,
    budget_sha256: str,
    provider: str,
    surface_fingerprint: str,
    expected_artifacts: Sequence[str] = (),
) -> RemoteExecutionRequest:
    """A fully-bound request, or ``ContractError`` with the deny reasons."""
    decision, reasons = evaluate_remote_policy(target, requirement, policy)
    if decision == "deny":
        raise ContractError(
            f"remote request denied for target {target.id!r}: " + "; ".join(reasons)
        )
    return RemoteExecutionRequest(
        producer=PRODUCER,
        created_at=utc_now(),
        task_sha256=task_sha256,
        context_sha256=context_sha256,
        budget_sha256=budget_sha256,
        provider=provider,
        surface_fingerprint=surface_fingerprint,
        target_id=target.id,
        target_identity_ref=target.identity_ref or "",
        policy_decision="allow",
        policy_ref=policy.policy_ref,
        data_classification=requirement.data_classification,
        expected_artifacts=sorted(expected_artifacts),
    )


def accept_receipt(
    receipt: RemoteExecutionReceipt, request: RemoteExecutionRequest
) -> list[str]:
    """Replay binding check: every mismatch is a violation, never silent."""
    violations: list[str] = []
    if receipt.request_sha256 != request_sha256(request):
        violations.append("receipt does not bind this request (request_sha256)")
    for field_name, r_val, q_val in (
        ("target_id", receipt.target_id, request.target_id),
        ("target_identity_ref", receipt.target_identity_ref, request.target_identity_ref),
        ("provider", receipt.provider, request.provider),
    ):
        if r_val != q_val:
            violations.append(f"{field_name} mismatch: {r_val!r} != {q_val!r}")
    missing = [a for a in request.expected_artifacts if a not in receipt.output_hashes]
    if missing:
        violations.append(f"expected artifacts missing from outputs: {missing}")
    if receipt.verification is None:
        violations.append("no target-side verification ref recorded")
    return sorted(violations)
