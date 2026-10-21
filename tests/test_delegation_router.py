"""lf-0028: deterministic delegation routing — justified plans, named refusals,
ambiguity never guessed, cycles refused (PHASE 3)."""

from __future__ import annotations

import dataclasses

from theforge import delegation_governance as gov
from theforge.contracts import (
    SpecialistCapability,
    SpecialistDelegation,
    from_dict,
)
from theforge.delegation_router import plan_delegation
from theforge.discovery import SpecialistDiscovery


def _manifest(provider: str, capabilities: list[dict]) -> SpecialistCapability:
    return from_dict(
        SpecialistCapability,
        {
            "specialist": {"id": provider, "version": "1.0.0"},
            "capabilities": capabilities,
        },
    )


def _entry(
    provider: str,
    state: str = "VERIFIED",
    capabilities: list[dict] | None = None,
    *,
    manifest: bool = True,
) -> SpecialistDiscovery:
    caps = (
        capabilities
        if capabilities is not None
        else [
            {
                "id": f"{provider.split('-')[0]}.analyze",
                "risk": "read_only",
                "external_cost": "none",
            }
        ]
    )
    return SpecialistDiscovery(
        forge_id=provider,
        state=state,  # type: ignore[arg-type]
        version="1.0.0",
        capability_manifest=_manifest(provider, caps) if manifest else None,
    )


def _delegation(**over) -> SpecialistDelegation:
    doc = {
        "consumer": "spark-forge-aws",
        "specialists": [
            {"provider": "data-sentinel", "intents": ["runtime-failure"]},
            {"provider": "forge-doctor-data", "intents": ["static-analysis"]},
        ],
        "policy": {"discovery": "runtime", "execution": "governed"},
    }
    doc.update(over)
    return from_dict(SpecialistDelegation, doc)


# --- happy path -----------------------------------------------------------------


def test_plans_a_justified_pick_for_the_matched_intent():
    plan = plan_delegation(
        "diagnose the spark runtime failure",
        _delegation(),
        [
            _entry(
                "data-sentinel",
                capabilities=[
                    {
                        "id": "sentinel.log-analyze",
                        "description": "runtime failure log analysis",
                        "risk": "read_only",
                        "external_cost": "none",
                        "entrypoint": ["{cli}", "analyze", "{target}"],
                    }
                ],
            ),
            _entry("forge-doctor-data"),
        ],
    )
    assert plan.status == "planned"
    assert len(plan.picks) == 1
    pick = plan.picks[0]
    assert pick.provider == "data-sentinel"
    assert pick.capability == "sentinel.log-analyze"
    assert pick.risks == ("LOCAL_READ",)
    # every pick is justified, never anonymous
    assert any("runtime-failure" in j for j in pick.justification)
    assert any("risk gate" in j for j in pick.justification)
    # the unmatched specialist is a limitation note, not a pick
    assert any("forge-doctor-data" in lim for lim in plan.limitations)


def test_never_fans_out_to_all_declared_specialists():
    plan = plan_delegation(
        "runtime failure in the glue job",
        _delegation(),
        [_entry("data-sentinel"), _entry("forge-doctor-data")],
    )
    assert [p.provider for p in plan.picks] == ["data-sentinel"]


def test_two_distinct_intents_yield_two_justified_picks():
    plan = plan_delegation(
        "check runtime failure and static analysis",
        _delegation(),
        [_entry("data-sentinel"), _entry("forge-doctor-data")],
    )
    assert plan.status == "planned"
    assert {p.provider for p in plan.picks} == {"data-sentinel", "forge-doctor-data"}


# --- named refusals ----------------------------------------------------------------


def test_absent_provider_is_provider_absent():
    plan = plan_delegation("runtime failure", _delegation(), [_entry("forge-doctor-data")])
    assert plan.status == "unavailable"
    refusal = next(r for r in plan.refusals if r.provider == "data-sentinel")
    assert refusal.code == "provider-absent"


def test_unverified_states_map_to_named_codes():
    plan = plan_delegation(
        "runtime failure and static analysis",
        _delegation(),
        [
            _entry("data-sentinel", state="INCOMPATIBLE"),
            _entry("forge-doctor-data", state="UNTRUSTED"),
        ],
    )
    codes = {r.provider: r.code for r in plan.refusals}
    assert codes["data-sentinel"] == "version-incompatible"
    assert codes["forge-doctor-data"] == "permission-denied"
    assert plan.status == "refused"


def test_discovered_but_not_verified_is_provider_absent():
    plan = plan_delegation(
        "runtime failure", _delegation(), [_entry("data-sentinel", state="DISCOVERED")]
    )
    assert plan.refusals[0].code == "provider-absent"
    assert "DISCOVERED" in plan.refusals[0].detail


def test_verified_without_manifest_is_capability_absent():
    plan = plan_delegation(
        "runtime failure", _delegation(), [_entry("data-sentinel", manifest=False)]
    )
    assert plan.refusals[0].code == "capability-absent"


def test_forbidden_policy_refuses_the_whole_plan():
    plan = plan_delegation(
        "runtime failure",
        _delegation(policy={"execution": "forbidden"}),
        [_entry("data-sentinel")],
    )
    assert plan.status == "refused" and plan.refusals[0].code == "policy-refusal"
    assert not plan.picks


# --- risk gate ---------------------------------------------------------------------


def test_cost_bearing_capability_is_gated_out_without_authorization():
    plan = plan_delegation(
        "runtime failure",
        _delegation(),
        [
            _entry(
                "data-sentinel",
                capabilities=[
                    {
                        "id": "sentinel.glue-diagnose",
                        "description": "runtime failure diagnosis",
                        "risk": "external_read",
                        "external_cost": "metered",
                    }
                ],
            )
        ],
    )
    assert plan.status == "refused"
    refusal = next(r for r in plan.refusals if r.provider == "data-sentinel")
    assert refusal.code == "policy-refusal"
    assert not plan.picks


def test_authorized_risks_allow_the_pick():
    plan = plan_delegation(
        "runtime failure",
        _delegation(),
        [
            _entry(
                "data-sentinel",
                capabilities=[
                    {
                        "id": "sentinel.glue-diagnose",
                        "description": "runtime failure diagnosis",
                        "risk": "external_read",
                        "external_cost": "metered",
                    }
                ],
            )
        ],
        authorized_risks={"EXTERNAL_READ", "COST_BEARING"},
    )
    assert plan.status == "planned"
    assert plan.picks[0].risks == ("EXTERNAL_READ", "COST_BEARING")


# --- ambiguity ----------------------------------------------------------------------


def test_same_intent_two_providers_is_ambiguous_never_a_guess():
    plan = plan_delegation(
        "runtime failure",
        _delegation(
            specialists=[
                {"provider": "data-sentinel", "intents": ["runtime-failure"]},
                {"provider": "sentinel-copy", "intents": ["runtime-failure"]},
            ]
        ),
        [_entry("data-sentinel"), _entry("sentinel-copy")],
    )
    assert plan.status == "ambiguous"
    assert any("claimed by both" in u for u in plan.unknowns)


def test_capability_tie_is_ambiguous_not_arbitrary():
    plan = plan_delegation(
        "log analysis",
        _delegation(
            specialists=[
                {"provider": "data-sentinel", "intents": ["log-analysis"]},
                {"provider": "forge-doctor-data", "intents": ["static-analysis"]},
            ]
        ),
        [
            _entry(
                "data-sentinel",
                capabilities=[
                    {"id": "sentinel.log-analysis", "description": "log analysis"},
                    {"id": "sentinel.log-inspect", "description": "log analysis"},
                ],
            )
        ],
    )
    assert plan.status == "ambiguous"
    refusal = next(r for r in plan.refusals if r.provider == "data-sentinel")
    assert refusal.code == "insufficient-evidence"


def test_no_capability_match_is_a_refusal_not_a_pick():
    plan = plan_delegation(
        "runtime failure",
        _delegation(),
        [
            _entry(
                "data-sentinel",
                capabilities=[
                    {"id": "sentinel.a", "description": "unrelated"},
                    {"id": "sentinel.b", "description": "also unrelated"},
                ],
            )
        ],
    )
    refusal = next(r for r in plan.refusals if r.provider == "data-sentinel")
    assert refusal.code == "insufficient-evidence"


# --- cycle prevention through the plan path ------------------------------------------


def test_visited_provider_in_chain_is_refused_cycle_detected():
    delegation = gov.start_chain(_delegation(), correlation_id="c-1")
    delegation = gov.admit_hop(delegation, "data-sentinel")  # type: ignore[assignment]
    plan = plan_delegation("runtime failure", delegation, [_entry("data-sentinel")])
    refusal = next(r for r in plan.refusals if r.provider == "data-sentinel")
    assert refusal.code == "cycle-detected"


def test_exhausted_chain_refuses_the_plan():
    delegation = gov.start_chain(_delegation(), correlation_id="c-1", max_hops=1)
    delegation = gov.admit_hop(delegation, "data-sentinel")  # type: ignore[assignment]
    plan = plan_delegation("runtime failure", delegation, [_entry("data-sentinel")])
    assert plan.status == "refused" and plan.refusals[0].code == "budget-exhausted"


def test_cancelled_chain_refuses_the_plan():
    delegation = gov.start_chain(_delegation(), correlation_id="c-1", cancellation_token="tok")
    delegation = dataclasses.replace(
        delegation, chain=dataclasses.replace(delegation.chain, cancelled=True)
    )
    plan = plan_delegation("runtime failure", delegation, [_entry("data-sentinel")])
    assert plan.status == "refused" and plan.refusals[0].code == "cancelled"


# --- determinism ---------------------------------------------------------------------


def test_planning_is_deterministic_regardless_of_input_order():
    discovered = [_entry("data-sentinel"), _entry("forge-doctor-data")]
    a = plan_delegation("runtime failure and static analysis", _delegation(), discovered)
    b = plan_delegation(
        "runtime failure and static analysis", _delegation(), list(reversed(discovered))
    )
    assert a == b
