"""Negotiation v2: requirement -> per-provider dimensional result, never a score."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from theforge.contracts import (
    Capability,
    CapabilityNegotiationResult,
    CapabilityOffer,
    CapabilityRequirement,
    ContractError,
    ForgeManifest,
    ProviderPerformance,
    Signals,
    from_dict,
    to_dict,
)
from theforge.contracts.performance import ProviderCapabilityPerformance
from theforge.contracts.types import Producer
from theforge.negotiation import feature_satisfied, maturity, negotiate, negotiate_all
from theforge.registry import ProviderEntry, RegistryRecord

REPO = Path(__file__).parents[1]


def cap(
    cid: str,
    *,
    actions=("run",),
    op="read_only",
    state="supported",
    offer: CapabilityOffer | None = None,
    produces=(),
    handoff=False,
) -> Capability:
    return Capability(
        id=cid,
        actions=list(actions),
        default_action=actions[0],
        state=state,
        operation_class=op,
        signals=Signals(keywords=["x"]),
        offer=offer,
        accepts_handoff=handoff,
        relations=__import__("theforge.contracts.manifest", fromlist=["x"]).CapabilityRelations(
            produces=list(produces)
        ),
    )


def record(
    pid: str, caps, *, trust="local", state="ready", manifest=True, protocols=("forge/v1",)
) -> RegistryRecord:
    m = (
        ForgeManifest(
            id=pid,
            version="1",
            protocols=list(protocols),
            ops=["describe", "health", "execute"],
            capabilities=list(caps),
        )
        if manifest
        else None
    )
    return RegistryRecord(
        entry=ProviderEntry(id=pid, argv=["x"], trust=trust),
        state=state,
        manifest=m,
        manifest_sha256="0" * 64 if m else None,
        protocol="forge/v1" if m else None,
    )


def req(capability: str, **kw) -> CapabilityRequirement:
    return CapabilityRequirement(capability=capability, **kw)


# --- contract surface -------------------------------------------------------


def test_requirement_minimal_and_defaults() -> None:
    r = req("data.streaming.analysis")
    assert r.schema == "theforge/CapabilityRequirement/v1"
    assert r.network_allowed and r.mutation_allowed and not r.offline_required


def test_requirement_rejects_bad_fields() -> None:
    with pytest.raises(ContractError):
        req("data.x", protocol_features=["handoff"])  # missing /vN
    with pytest.raises(ContractError):
        req("data.x", task_family="UPPER CASE")


def test_offer_roundtrip_and_validation() -> None:
    o = from_dict(
        CapabilityOffer, {"technologies": ["kafka"], "offline": True, "features": ["handoff/v1"]}
    )
    assert o.technologies == ["kafka"] and o.offline
    with pytest.raises(ContractError):
        from_dict(CapabilityOffer, {"features": ["not-a-feature-id"]})


def test_manifest_offer_is_additive() -> None:
    m = from_dict(
        ForgeManifest,
        {
            "id": "p",
            "version": "1",
            "protocols": ["forge/v1"],
            "ops": ["describe", "health", "execute"],
            "capabilities": [
                {
                    "id": "a.b",
                    "actions": ["x"],
                    "default_action": "x",
                    "state": "supported",
                    "operation_class": "read_only",
                }
            ],
        },
    )
    assert m.capabilities[0].offer is None  # legacy mode
    m2 = from_dict(
        ForgeManifest,
        {
            "id": "p",
            "version": "1",
            "protocols": ["forge/v1"],
            "ops": ["describe", "health", "execute"],
            "capabilities": [
                {
                    "id": "a.b",
                    "actions": ["x"],
                    "default_action": "x",
                    "state": "supported",
                    "operation_class": "read_only",
                    "offer": {"technologies": ["kafka"]},
                }
            ],
        },
    )
    assert m2.capabilities[0].offer.technologies == ["kafka"]


# --- engine states ----------------------------------------------------------


def test_full_match_with_rich_offer() -> None:
    offer = CapabilityOffer(
        technologies=["kafka", "spark-structured-streaming"],
        produces_evidence=["finding", "source-reference"],
        offline=True,
    )
    r = record(
        "data-forge",
        [
            cap(
                "data.streaming.analysis",
                actions=("inspect", "diagnose"),
                offer=offer,
                produces=("finding",),
            )
        ],
    )
    res = negotiate(
        req(
            "data.streaming.analysis",
            required_actions=["inspect"],
            technologies=["kafka"],
            required_evidence=["finding"],
            offline_required=True,
            mutation_allowed=False,
        ),
        r,
    )
    assert res.state == "FULL" and res.capability == "data.streaming.analysis"
    assert res.dimensions["technology_match"] == "full"
    assert res.dimensions["evidence_match"] == "full"
    assert res.dimensions["runtime_match"] == "full"


def test_legacy_mode_is_partial_never_full() -> None:
    r = record("legacy", [cap("data.scan", actions=("scan",))])
    res = negotiate(
        req(
            "data.scan",
            technologies=["kafka"],
            required_evidence=["finding"],
            offline_required=True,
        ),
        r,
    )
    assert res.state == "PARTIAL"
    assert "undeclared:technology_match" in res.missing
    assert res.dimensions["technology_match"] == "unknown"


def test_unsupported_capability_absent() -> None:
    res = negotiate(req("api.contract"), record("p", [cap("data.scan")]))
    assert res.state == "UNSUPPORTED" and res.capability is None


def test_unresolved_without_manifest() -> None:
    res = negotiate(req("a.b"), record("p", [], manifest=False, state="invalid"))
    assert res.state == "UNRESOLVED" and "manifest" in res.missing


@pytest.mark.parametrize(
    "kw,conflict",
    [
        ({"minimum_trust": "trusted"}, "trust:local"),
        ({"operation_class_ceiling": "read_only"}, "operation_class:local_mutation>read_only"),
        ({"mutation_allowed": False}, "mutation:local_mutation"),
    ],
)
def test_policy_gates(kw, conflict) -> None:
    r = record("p", [cap("a.b", op="local_mutation")])
    res = negotiate(req("a.b", **kw), r)
    assert res.state == "INCOMPATIBLE" and conflict in res.policy_conflicts


def test_blocked_trust_always_incompatible() -> None:
    r = record("p", [cap("a.b")], trust="blocked")
    assert negotiate(req("a.b"), r).state == "INCOMPATIBLE"


def test_protocol_gate() -> None:
    r = record("p", [cap("a.b")], protocols=("other/v9",))
    res = negotiate(req("a.b"), r)
    assert res.state == "INCOMPATIBLE" and "protocol:forge/v1" in res.missing


def test_technology_gate_declared_and_missing() -> None:
    offer = CapabilityOffer(technologies=["spark"])
    r = record("p", [cap("a.b", offer=offer)])
    res = negotiate(req("a.b", technologies=["kafka"]), r)
    assert res.state == "INCOMPATIBLE" and "technology:kafka" in res.missing


def test_evidence_gate_declared_and_missing() -> None:
    offer = CapabilityOffer(produces_evidence=["finding"])
    r = record("p", [cap("a.b", offer=offer)])
    res = negotiate(req("a.b", required_evidence=["runtime-observation"]), r)
    assert res.state == "INCOMPATIBLE" and "evidence:runtime-observation" in res.missing


def test_runtime_gate_offline() -> None:
    m = ForgeManifest(
        id="net",
        version="1",
        protocols=["forge/v1"],
        ops=["describe", "health", "execute"],
        capabilities=[cap("a.b")],
        execution=__import__("theforge.contracts.manifest", fromlist=["x"]).ExecutionInfo(
            offline=False, requires_network=True
        ),
    )
    rec = RegistryRecord(
        entry=ProviderEntry(id="net", argv=["x"], trust="local"),
        state="ready",
        manifest=m,
        manifest_sha256="0" * 64,
        protocol="forge/v1",
    )
    res = negotiate(req("a.b", offline_required=True), rec)
    assert res.state == "INCOMPATIBLE"
    assert "runtime:offline_required" in res.policy_conflicts


def test_required_feature_missing_is_incompatible() -> None:
    r = record("p", [cap("a.b")])
    res = negotiate(req("a.b", protocol_features=["delta/v1"]), r)
    assert res.state == "INCOMPATIBLE" and "feature:delta/v1" in res.missing


def test_feature_versioning_higher_major_satisfies() -> None:
    assert feature_satisfied({"handoff/v2"}, "handoff/v1")
    assert not feature_satisfied({"handoff/v1"}, "handoff/v2")
    assert feature_satisfied({"delta/v1"}, "delta/v1")


def test_handoff_flag_via_implied_feature() -> None:
    r = record("p", [cap("a.b", handoff=True)])
    res = negotiate(req("a.b", handoff_required=True), r)
    assert res.dimensions["feature_match"] == "full" and res.state == "FULL"


def test_required_actions() -> None:
    offer = CapabilityOffer()
    r = record("p", [cap("a.b", actions=("scan", "fix"), offer=offer)])
    ok = negotiate(req("a.b", required_actions=["scan"]), r)
    assert ok.state in ("FULL", "PARTIAL")  # actions satisfied
    # required actions missing from the capability is a soft gap
    res = negotiate(req("a.b", required_actions=["scan", "audit"]), r)
    assert "partial" in (res.dimensions["capability_match"],) or res.state == "PARTIAL"


# --- history / maturity -----------------------------------------------------


def _perf(provider: str, cap_id: str, runs: int, surface: str | None) -> ProviderPerformance:
    e = ProviderCapabilityPerformance(
        provider=provider,
        capability=cap_id,
        runs=runs,
        surface=surface,
        ok=runs,
        partial=0,
        failed=0,
        verified_runs=runs,
        evidence=runs,
        artifacts=runs,
        context_bytes=100 * runs,
        files_sent=runs,
        files_cited=runs,
        duration_ms=10.0 * runs,
        updated_at="t",
    )
    return ProviderPerformance(
        producer=Producer(id="theforge", version="0"), created_at="t", entries=[e]
    )


def test_maturity_ladder() -> None:
    assert maturity(None, "p", "a.b", "s") == "absent"
    assert maturity(_perf("p", "a.b", 1, "s"), "p", "a.b", "s") == "cold"
    assert maturity(_perf("p", "a.b", 3, "s"), "p", "a.b", "s") == "warming"
    assert maturity(_perf("p", "a.b", 9, "s"), "p", "a.b", "s") == "mature"


def test_surface_change_stales_history() -> None:
    perf = _perf("p", "a.b", 20, "oldsurface")
    assert maturity(perf, "p", "a.b", "newsurface") == "stale"
    assert maturity(perf, "p", "a.b", "oldsurface") == "mature"


# --- ranking ----------------------------------------------------------------


def test_negotiate_all_orders_by_state_then_dimensions() -> None:
    rich = record("rich", [cap("a.b", offer=CapabilityOffer(technologies=["t"]))])
    poor = record("poor", [cap("a.b")])  # legacy: technology unknown
    nosuch = record("none", [cap("z.z")])
    res = negotiate_all(req("a.b", technologies=["t"]), [nosuch, poor, rich])
    assert [r.provider for r in res] == ["rich", "poor", "none"]
    assert res[0].state == "FULL" and res[1].state == "PARTIAL" and res[2].state == "UNSUPPORTED"


def test_deterministic_sort_is_input_order_independent() -> None:
    a = record("a", [cap("a.b")])
    b = record("b", [cap("a.b")])
    assert [r.provider for r in negotiate_all(req("a.b"), [a, b])] == ["a", "b"]
    assert [r.provider for r in negotiate_all(req("a.b"), [b, a])] == ["a", "b"]


def test_result_serializes_closed() -> None:
    res = negotiate(req("a.b"), record("p", [cap("a.b")]))
    data = to_dict(res)
    back = from_dict(CapabilityNegotiationResult, data, strict=True)
    assert back.state == res.state and back.provider == res.provider


# --- CLI --------------------------------------------------------------------


def test_cli_negotiate(tmp_path: Path) -> None:
    req_file = tmp_path / "req.json"
    req_file.write_text(json.dumps(to_dict(req("a.b"))), "utf-8")
    env_dir = REPO / "tests" / "fixtures" / "workspaces" / "api"
    out = subprocess.run(
        [
            sys.executable,
            "-m",
            "theforge",
            "capabilities",
            "negotiate",
            "--requirement",
            str(req_file),
            "--root",
            str(env_dir),
            "--json",
        ],
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0, out.stderr
    data = json.loads(out.stdout)
    assert data["requirement"]["capability"] == "a.b"
    assert all(
        r["state"] in ("FULL", "PARTIAL", "UNSUPPORTED", "INCOMPATIBLE", "UNRESOLVED")
        for r in data["results"]
    )
