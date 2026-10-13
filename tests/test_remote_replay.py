"""Cycle 5.1 §29 — replay-attack regressions for remote receipts.

Replay protection is structural: ``request_sha256`` binds the receipt to the
exact request (task + context + budget + provider + surface + target +
classification). There is no separate nonce field — the request hash is the
nonce-equivalent, and ``accept_receipt`` never silently ignores a mismatch.
"""

from __future__ import annotations

import dataclasses

from theforge.contracts import ExecutionTarget, TargetRequirement
from theforge.contracts.canonical import sha256_of, utc_now
from theforge.contracts.remote import RemoteExecutionReceipt
from theforge.meta import PRODUCER
from theforge.remote import RemotePolicy, accept_receipt, build_request, request_sha256

_HASH_A = sha256_of({"a": 1})
_HASH_B = sha256_of({"b": 2})


def _target(**kw) -> ExecutionTarget:
    base = dict(
        id="ci",
        type="remote-forge",
        identity_ref="org-forge:ci",
        network="egress",
        trust="org-approved",
        health="healthy",
        data_classes=["public", "internal"],
    )
    base.update(kw)
    return ExecutionTarget(producer=PRODUCER, created_at=utc_now(), **base)


def _request(**kw):
    base = dict(
        target=_target(),
        requirement=TargetRequirement(data_classification="internal", locality="local-or-remote"),
        policy=RemotePolicy(policy_ref="org-forge:policy/remote.v1", allowed_target_ids=["ci"]),
        task_sha256=_HASH_A,
        context_sha256=_HASH_A,
        budget_sha256=_HASH_A,
        provider="sparkforge_aws",
        surface_fingerprint="fp-stable",
        expected_artifacts=["out.v1"],
    )
    base.update(kw)
    return build_request(**base)


def _receipt_for(req, **kw) -> RemoteExecutionReceipt:
    base = dict(
        producer=PRODUCER,
        created_at=utc_now(),
        request_sha256=request_sha256(req),
        execution_id="ex1",
        target_id=req.target_id,
        target_identity_ref=req.target_identity_ref,
        provider=req.provider,
        input_hashes={"task": _HASH_A},
        output_hashes={"out.v1": _HASH_A},
        verification="attest:1",
    )
    base.update(kw)
    return RemoteExecutionReceipt(**base)


def test_same_receipt_reused_for_different_task() -> None:
    """Receipt from run A cannot satisfy run B: task hash differs."""
    req_a = _request()
    receipt = _receipt_for(req_a)
    req_b = _request(context_sha256=_HASH_B)  # new run, new context
    violations = accept_receipt(receipt, req_b)
    assert violations, "receipt for a different request must be rejected"


def test_same_receipt_reused_same_task_different_budget() -> None:
    """Same task but different budget → different request hash → reject."""
    req_a = _request()
    receipt = _receipt_for(req_a)
    req_b = _request(budget_sha256=_HASH_B)
    assert accept_receipt(receipt, req_b)


def test_receipt_for_capability_a_not_valid_for_b() -> None:
    """A receipt bound to provider A cannot be presented for provider B."""
    req_a = _request(provider="apiforge")
    receipt = _receipt_for(req_a)
    req_b = _request(provider="sparkforge_aws")
    violations = accept_receipt(receipt, req_b)
    assert violations


def test_receipt_against_changed_surface() -> None:
    """Surface drift invalidates the request binding."""
    req_a = _request()
    receipt = _receipt_for(req_a)
    req_b = _request(surface_fingerprint="fp-drifted")
    assert accept_receipt(receipt, req_b)


def test_receipt_echoing_hash_but_wrong_target_identity() -> None:
    """An attacker who knows the request hash still cannot forge identity."""
    req = _request()
    receipt = _receipt_for(req, target_identity_ref="org-forge:attacker")
    violations = accept_receipt(receipt, req)
    assert violations


def test_receipt_echoing_hash_but_wrong_provider() -> None:
    req = _request()
    receipt = _receipt_for(req, provider="attacker-provider")
    assert accept_receipt(receipt, req)


def test_receipt_missing_expected_artifact() -> None:
    req = _request()
    receipt = _receipt_for(req, output_hashes={"other.v1": _HASH_A})
    assert accept_receipt(receipt, req)


def test_receipt_without_verification_reference() -> None:
    req = _request()
    receipt = _receipt_for(req, verification=None)
    assert accept_receipt(receipt, req)


def test_clean_receipt_accepted() -> None:
    """Baseline: a correctly bound receipt is accepted (no violations)."""
    req = _request()
    assert accept_receipt(_receipt_for(req), req) == []


def test_request_fields_are_immutable() -> None:
    """The contract is frozen — no in-place tampering."""
    req = _request()
    mutated = dataclasses.replace(req, provider="attacker")
    assert request_sha256(mutated) != request_sha256(req)
