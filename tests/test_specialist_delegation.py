"""lf-0028: theforge/SpecialistDelegation/v1 contract + chain-control tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from theforge.contracts import (
    SPECIALIST_DELEGATION_SCHEMA,
    ContractError,
    SpecialistDelegation,
    from_dict,
    to_dict,
)
from theforge.contracts.specialist_delegation import DELEGATION_FAILURES, DELEGATION_RISKS

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"


def _doc(**over):
    doc = {
        "schema": "theforge/SpecialistDelegation/v1",
        "consumer": "spark-forge-aws",
        "specialists": [
            {
                "provider": "data-sentinel",
                "optional": True,
                "intents": ["runtime-failure", "glue-investigation"],
            },
            {
                "provider": "forge-doctor-data",
                "optional": True,
                "intents": ["static-analysis"],
            },
        ],
        "policy": {
            "discovery": "runtime",
            "execution": "governed",
            "preserve_evidence": True,
            "fallback": "native-analysis",
        },
    }
    doc.update(over)
    return doc


def _chain(**over):
    chain = {
        "correlation_id": "corr-abc-1",
        "delegation_depth": 1,
        "visited_providers": ["spark-forge-aws", "data-sentinel"],
        "max_hops": 4,
        "timeout_budget_s": 300,
        "cancellation_token": "cancel-abc-1",
        "cancelled": False,
    }
    chain.update(over)
    return chain


def test_valid_document_parses_and_roundtrips():
    delegation = from_dict(SpecialistDelegation, _doc(chain=_chain()))
    assert delegation.consumer == "spark-forge-aws"
    assert delegation.specialists[0].provider == "data-sentinel"
    assert delegation.specialists[0].optional is True
    assert delegation.specialists[0].intents == ["runtime-failure", "glue-investigation"]
    assert delegation.policy.execution == "governed"
    assert delegation.policy.fallback == "native-analysis"
    assert delegation.chain is not None
    assert delegation.chain.correlation_id == "corr-abc-1"
    assert delegation.chain.visited_providers == ["spark-forge-aws", "data-sentinel"]
    assert from_dict(SpecialistDelegation, to_dict(delegation)) == delegation


def test_spec_example_shape_is_accepted():
    """The §5 yaml example, translated to JSON, parses unchanged."""
    doc = _doc()
    delegation = from_dict(SpecialistDelegation, doc)
    assert delegation.policy.discovery == "runtime"
    assert delegation.policy.preserve_evidence is True


def test_schema_pinned_to_theforge_namespace():
    assert SPECIALIST_DELEGATION_SCHEMA == "theforge/SpecialistDelegation/v1"
    with pytest.raises(ContractError):
        from_dict(SpecialistDelegation, _doc(schema="forge/SpecialistDelegation/v1"))


def test_consumer_must_be_provider_id():
    with pytest.raises(ContractError):
        from_dict(SpecialistDelegation, _doc(consumer="Spark Forge"))


def test_duplicate_specialists_rejected():
    doc = _doc()
    doc["specialists"].append({"provider": "data-sentinel"})
    with pytest.raises(ContractError):
        from_dict(SpecialistDelegation, doc)


def test_intent_slugs_are_closed_shape():
    doc = _doc(specialists=[{"provider": "p-one", "intents": ["Runtime Failure"]}])
    with pytest.raises(ContractError):
        from_dict(SpecialistDelegation, doc)


def test_policy_vocabularies_are_closed():
    with pytest.raises(ContractError):
        from_dict(SpecialistDelegation, _doc(policy={"discovery": "telepathy"}))
    with pytest.raises(ContractError):
        from_dict(SpecialistDelegation, _doc(policy={"execution": "yolo"}))


def test_fallback_must_be_slug_not_instruction():
    """The fallback names a degrading path — a sentence is not a name."""
    with pytest.raises(ContractError):
        from_dict(
            SpecialistDelegation,
            _doc(policy={"fallback": "run rm -rf / --no-preserve-root"}),
        )


# --- chain control -----------------------------------------------------------


def test_chain_defaults_when_absent():
    delegation = from_dict(SpecialistDelegation, _doc())
    assert delegation.chain is None


def test_chain_rejects_depth_beyond_max_hops():
    with pytest.raises(ContractError):
        from_dict(
            SpecialistDelegation,
            _doc(chain=_chain(delegation_depth=5, max_hops=4)),
        )


def test_chain_rejects_revisit_at_parse():
    """A chain document cannot even *encode* a cycle."""
    with pytest.raises(ContractError):
        from_dict(
            SpecialistDelegation,
            _doc(
                chain=_chain(
                    delegation_depth=2,
                    visited_providers=["spark-forge-aws", "data-sentinel", "data-sentinel"],
                )
            ),
        )


def test_chain_visited_count_must_match_depth():
    with pytest.raises(ContractError):
        from_dict(
            SpecialistDelegation,
            _doc(chain=_chain(delegation_depth=2, visited_providers=["spark-forge-aws"])),
        )
    with pytest.raises(ContractError):
        from_dict(
            SpecialistDelegation,
            _doc(chain=_chain(delegation_depth=1, visited_providers=[])),
        )


def test_chain_rejects_bad_ids_and_budgets():
    with pytest.raises(ContractError):
        from_dict(SpecialistDelegation, _doc(chain=_chain(correlation_id="has space")))
    with pytest.raises(ContractError):
        from_dict(SpecialistDelegation, _doc(chain=_chain(timeout_budget_s=0)))
    with pytest.raises(ContractError):
        from_dict(SpecialistDelegation, _doc(chain=_chain(max_hops=0)))


def test_cancelled_requires_cancellation_token():
    with pytest.raises(ContractError):
        from_dict(
            SpecialistDelegation,
            _doc(chain=_chain(cancelled=True, cancellation_token="")),
        )


def test_failure_taxonomy_covers_the_spec_list():
    """PHASE 14 "Distinguir" list plus the three chain refusals — closed set."""
    required = {
        "provider-absent",
        "version-incompatible",
        "capability-absent",
        "invalid-input",
        "permission-denied",
        "timeout",
        "runtime-error",
        "invalid-output",
        "insufficient-evidence",
        "policy-refusal",
    }
    chain = {"cycle-detected", "budget-exhausted", "cancelled"}
    assert required <= set(DELEGATION_FAILURES)
    assert chain <= set(DELEGATION_FAILURES)


def test_risk_vocabulary_is_the_six_spec_levels():
    assert set(DELEGATION_RISKS) == {
        "LOCAL_READ",
        "LOCAL_WRITE",
        "EXTERNAL_READ",
        "EXTERNAL_WRITE",
        "DESTRUCTIVE",
        "COST_BEARING",
    }


def test_generated_schema_file_exists_and_matches_shape():
    schema_path = SCHEMAS_DIR / "SpecialistDelegation.schema.json"
    assert schema_path.is_file(), "run python -m theforge.contracts.schema schemas"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    props = schema["properties"]
    assert props["consumer"]["pattern"] == r"^[a-z][a-z0-9-]*$"
    chain_variants = props["chain"]["anyOf"]  # DelegationChain | None
    chain = next(v for v in chain_variants if v.get("type") == "object")["properties"]
    assert "correlation_id" in chain and "visited_providers" in chain
    assert "delegation_depth" in chain and "max_hops" in chain
    assert "timeout_budget_s" in chain and "cancellation_token" in chain
    policy = props["policy"]["properties"]
    assert policy["discovery"]["enum"] == ["runtime", "declared", "off"]
    assert policy["execution"]["enum"] == ["governed", "manual", "forbidden"]
