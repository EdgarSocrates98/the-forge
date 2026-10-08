"""Cycle 5 wave K/L: remote-execution trust model — deny-by-default policy
gate, fully-bound requests, and replay binding on receipts.
"""

from __future__ import annotations

import pytest

from theforge.contracts import ContractError, ExecutionTarget, TargetRequirement
from theforge.contracts.canonical import sha256_of, utc_now
from theforge.contracts.remote import RemoteExecutionReceipt
from theforge.meta import PRODUCER
from theforge.remote import (
    RemotePolicy,
    accept_receipt,
    build_request,
    evaluate_remote_policy,
    load_policy,
    request_sha256,
)

_HASH = sha256_of({"x": 1})


def _remote_target(**kw) -> ExecutionTarget:
    base = dict(
        id="ci", type="remote-forge", identity_ref="org-forge:ci",
        network="egress", trust="org-approved", health="healthy",
        data_classes=["public", "internal"],
    )
    base.update(kw)
    return ExecutionTarget(producer=PRODUCER, created_at=utc_now(), **base)


def _req(dc: str = "internal", locality: str = "local-or-remote") -> TargetRequirement:
    return TargetRequirement(data_classification=dc, locality=locality)


def _policy(**kw) -> RemotePolicy:
    base = dict(policy_ref="org-forge:policy/remote.v1", allowed_target_ids=["ci"])
    base.update(kw)
    return RemotePolicy(**base)


class TestPolicyGate:
    def test_deny_by_default_empty_allowlist(self) -> None:
        decision, reasons = evaluate_remote_policy(
            _remote_target(), _req(), RemotePolicy(policy_ref="p")
        )
        assert decision == "deny" and any("allowed_target_ids" in r for r in reasons)

    def test_allow_when_everything_holds(self) -> None:
        decision, reasons = evaluate_remote_policy(_remote_target(), _req(), _policy())
        assert decision == "allow" and reasons == []

    def test_verified_floor_for_remote_forge(self) -> None:
        t = _remote_target(trust="unverified")
        decision, reasons = evaluate_remote_policy(t, _req(), _policy())
        assert decision == "deny" and any("trust" in r for r in reasons)

    def test_a2a_promoted_only_by_policy(self) -> None:
        # a2a-agent trust is contract-capped at 'unverified' — the allowlist is
        # the promotion mechanism. A listed a2a target passes; an unlisted one
        # carries the promotion refusal on top of the allowlist refusal.
        kw = dict(id="a1", type="a2a-agent", identity_ref="a2a:x",
                  data_classes=["public"], trust="unverified")
        t = _remote_target(**kw)
        decision, _ = evaluate_remote_policy(t, _req("public"), _policy())
        assert decision == "deny"  # not in allowed_target_ids
        pol = _policy(allowed_target_ids=["a1"], allowed_identity_refs=["a2a:x"])
        assert evaluate_remote_policy(t, _req("public"), pol)[0] == "allow"
        pol2 = _policy(allowed_target_ids=["a1"])  # no identity pinning -> ok
        assert evaluate_remote_policy(t, _req("public"), pol2)[0] == "allow"

    def test_confidential_never_remote(self) -> None:
        for dc in ("confidential", "restricted", "unknown"):
            decision, reasons = evaluate_remote_policy(_remote_target(), _req(dc), _policy())
            assert decision == "deny", dc
            assert any("data_classification" in r for r in reasons)

    def test_policy_ceiling_public_only(self) -> None:
        pol = _policy(max_data_classification="public")
        assert evaluate_remote_policy(_remote_target(), _req("internal"), pol)[0] == "deny"
        assert evaluate_remote_policy(_remote_target(), _req("public"), pol)[0] == "allow"

    def test_locality_forbids_remote(self) -> None:
        for loc in ("local", "isolated"):
            assert evaluate_remote_policy(
                _remote_target(), _req(locality=loc), _policy()
            )[0] == "deny"

    def test_unhealthy_denied_when_required(self) -> None:
        t = _remote_target(health="degraded")
        assert evaluate_remote_policy(t, _req(), _policy())[0] == "deny"
        pol = _policy(require_healthy=False)
        assert evaluate_remote_policy(t, _req(), pol)[0] == "allow"


class TestRequestBuild:
    def test_denied_raises_with_reasons(self) -> None:
        with pytest.raises(ContractError, match="remote request denied"):
            build_request(
                target=_remote_target(), requirement=_req(),
                policy=RemotePolicy(policy_ref="p"),
                task_sha256=_HASH, context_sha256=_HASH, budget_sha256=_HASH,
                provider="p", surface_fingerprint="fp",
            )

    def test_allowed_request_is_fully_bound(self) -> None:
        req = build_request(
            target=_remote_target(), requirement=_req("internal"),
            policy=_policy(),
            task_sha256=_HASH, context_sha256=_HASH, budget_sha256=_HASH,
            provider="sparkforge_aws", surface_fingerprint="fp1",
            expected_artifacts=["report.v1", "log.v1"],
        )
        assert req.policy_decision == "allow"
        assert req.policy_ref == "org-forge:policy/remote.v1"
        assert req.target_identity_ref == "org-forge:ci"
        assert req.expected_artifacts == ["log.v1", "report.v1"]  # sorted
        assert request_sha256(req) == sha256_of(
            __import__("theforge.contracts.base", fromlist=["to_dict"]).to_dict(req)
        )


class TestReceiptBinding:
    def _pair(self):
        target = _remote_target()
        req = build_request(
            target=target, requirement=_req(), policy=_policy(),
            task_sha256=_HASH, context_sha256=_HASH, budget_sha256=_HASH,
            provider="p", surface_fingerprint="fp",
            expected_artifacts=["out.v1"],
        )
        receipt = RemoteExecutionReceipt(
            producer=PRODUCER, created_at=utc_now(),
            request_sha256=request_sha256(req), execution_id="ex1",
            target_id=target.id, target_identity_ref=target.identity_ref,
            provider="p",
            input_hashes={"task": _HASH}, output_hashes={"out.v1": _HASH},
            verification="attest:1",
        )
        return req, receipt

    def test_clean_receipt_accepted(self) -> None:
        req, receipt = self._pair()
        assert accept_receipt(receipt, req) == []

    def test_tampered_request_hash(self) -> None:
        import dataclasses

        req, receipt = self._pair()
        bad = dataclasses.replace(receipt, request_sha256=sha256_of({"other": 1}))
        assert any("request_sha256" in x for x in accept_receipt(bad, req))

    def test_wrong_target_or_provider(self) -> None:
        import dataclasses

        req, receipt = self._pair()
        wrong_target = dataclasses.replace(receipt, target_id="other")
        wrong_provider = dataclasses.replace(receipt, provider="other")
        assert any("target_id mismatch" in x for x in accept_receipt(wrong_target, req))
        assert any("provider mismatch" in x for x in accept_receipt(wrong_provider, req))

    def test_missing_expected_artifact(self) -> None:
        import dataclasses

        req, receipt = self._pair()
        r2 = dataclasses.replace(receipt, output_hashes={"unrelated": _HASH})
        assert any("expected artifacts missing" in x for x in accept_receipt(r2, req))

    def test_no_verification_is_violation(self) -> None:
        import dataclasses

        req, receipt = self._pair()
        r2 = dataclasses.replace(receipt, verification=None)
        assert any("verification" in x for x in accept_receipt(r2, req))


class TestPolicyLoad:
    def test_absent_file_denies_all(self, tmp_path) -> None:
        pol = load_policy(tmp_path / "nope.toml")
        assert pol.allowed_target_ids == []

    def test_toml_roundtrip(self, tmp_path) -> None:
        p = tmp_path / "remote-policy.toml"
        p.write_text(
            '[remote.policy]\npolicy_ref = "org-forge:p1"\n'
            'allowed_target_ids = ["ci"]\nmax_data_classification = "public"\n',
            encoding="utf-8",
        )
        pol = load_policy(p)
        assert pol.policy_ref == "org-forge:p1"
        assert pol.allowed_target_ids == ["ci"]
        assert pol.max_data_classification == "public"
