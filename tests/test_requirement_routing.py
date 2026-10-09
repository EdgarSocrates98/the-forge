"""Cycle 4 Wave B — requirement-driven fit selection in routing/planning.

Gate: two providers declaring the same capability are distinguished by fit —
``negotiate_all`` orders FULL > PARTIAL > rejected, hard gates exclude, and the
decision persists every negotiation result so explain can say why (§14, §89-91).
"""

import json
from pathlib import Path

import pytest

from helpers import PROVIDERS, SPARK_ENTRY, fixture_argv, make_workspace
from theforge.contracts import (
    Capability,
    CapabilityOffer,
    CapabilityRequirement,
    ContractError,
    ForgeManifest,
    Signals,
    TaskSpec,
)
from theforge.contracts.base import to_dict
from theforge.contracts.canonical import utc_now
from theforge.contracts.manifest import ExecutionInfo
from theforge.contracts.plan import ExecutionPlan, PlanNode
from theforge.forger import AskRequest, Forger
from theforge.meta import PRODUCER
from theforge.planning.validate import check_plan, checked_plan
from theforge.profiles import profile_for
from theforge.registry import ProviderEntry, Registry, RegistryRecord
from theforge.routing import route
from theforge.runs import RunStore


def cap(
    cid: str,
    *,
    actions: tuple[str, ...] = ("run",),
    offer: CapabilityOffer | None = None,
    op: str = "read_only",
    aliases: tuple[str, ...] = (),
) -> Capability:
    return Capability(
        id=cid,
        actions=list(actions),
        default_action=actions[0],
        state="supported",
        operation_class=op,
        signals=Signals(keywords=["data"]),
        aliases=list(aliases),
        offer=offer,
    )


def record(
    pid: str, caps: list[Capability], trust: str = "local", execution: ExecutionInfo | None = None
) -> RegistryRecord:
    manifest = ForgeManifest(
        id=pid,
        version="1",
        protocols=["forge/v1"],
        ops=["describe", "health", "execute"],
        capabilities=list(caps),
        execution=execution or ExecutionInfo(),
    )
    return RegistryRecord(
        entry=ProviderEntry(id=pid, argv=["x"], trust=trust),
        state="ready",
        manifest=manifest,
        manifest_sha256="0" * 64,
        protocol="forge/v1",
    )


def task(intent: str = "analyze the data", **kw: object) -> TaskSpec:
    return TaskSpec(
        producer=PRODUCER, created_at=utc_now(), id="t1", intent=intent, workspace_root="/ws", **kw
    )


def req(capability: str = "data.pipeline", **kw: object) -> CapabilityRequirement:
    return CapabilityRequirement(capability=capability, **kw)


RICH = CapabilityOffer(
    technologies=["spark", "kafka"],
    produces_evidence=["finding", "graph-reference"],
    produces_artifact_types=["report/json"],
)
NET_ONLY = ExecutionInfo(offline=False, requires_network=True)


def test_requirement_distinguishes_fit_full_over_partial() -> None:
    """Proof 1: two providers, same capability, different offers — fit decides."""
    rich = record("rich-forge", [cap("data.pipeline", offer=RICH)])
    poor = record("poor-forge", [cap("data.pipeline")])  # legacy: no offer
    requirement = req(technologies=["spark", "kafka"], required_evidence=["finding"])
    decision = route(task(requirement=requirement), [poor, rich], [], set())
    assert decision.status == "routed"
    assert decision.selected[0].provider == "rich-forge"
    states = {r.provider: r.state for r in decision.negotiation}
    assert states == {"rich-forge": "FULL", "poor-forge": "PARTIAL"}


def test_requirement_hard_gate_excludes_incompatible() -> None:
    """A hard gate failure is never ranked back in (§9/§90)."""
    online = record("net-forge", [cap("data.pipeline")], execution=NET_ONLY)
    local = record("local-forge", [cap("data.pipeline")])
    decision = route(task(requirement=req(offline_required=True)), [online, local], [], set())
    assert decision.status == "routed"
    assert decision.selected[0].provider == "local-forge"
    by_provider = {r.provider: r for r in decision.negotiation}
    assert by_provider["net-forge"].state == "INCOMPATIBLE"
    assert by_provider["net-forge"].policy_conflicts == ["runtime:offline_required"]
    assert all(c.provider != "net-forge" for c in decision.candidates)


def test_requirement_all_incompatible_is_no_route_with_reason() -> None:
    online = record("net-forge", [cap("data.pipeline")], execution=NET_ONLY)
    decision = route(task(requirement=req(offline_required=True)), [online], [], set())
    assert decision.status == "no_route"
    assert "INCOMPATIBLE" in decision.reason
    assert decision.negotiation[0].provider == "net-forge"


def test_requirement_partial_winner_routes_low_confidence() -> None:
    """Only offerless declarer: gates pass, demands stay unknown → PARTIAL."""
    bare = record("bare-forge", [cap("data.pipeline")])
    requirement = req(required_evidence=["finding"], technologies=["kafka"])
    decision = route(task(requirement=requirement), [bare], [], set())
    assert decision.status == "routed"
    assert decision.selected[0].provider == "bare-forge"
    assert decision.confidence.level == "low"
    assert decision.negotiation[0].state == "PARTIAL"
    assert decision.negotiation[0].missing


def test_requirement_operation_class_ceiling_gate() -> None:
    mutator = record("mut-forge", [cap("data.pipeline", op="local_mutation")])
    decision = route(
        task(requirement=req(operation_class_ceiling="read_only")), [mutator], [], set()
    )
    assert decision.status == "no_route"
    assert decision.negotiation[0].state == "INCOMPATIBLE"
    assert "operation_class" in decision.negotiation[0].policy_conflicts[0]


def test_no_requirement_keeps_legacy_selection_and_empty_negotiation() -> None:
    """Backward compat (§114): no requirement → trust/history/id, no results."""
    a = record("a-forge", [cap("data.pipeline")])
    b = record("b-forge", [cap("data.pipeline")])
    decision = route(task(requested_capability="data.pipeline"), [a, b], [], set())
    assert decision.status == "routed"
    assert decision.negotiation == []


def test_requirement_routes_through_an_alias() -> None:
    """An alias demand resolves to the canonical id and is still negotiated."""
    aliased = cap("data.mesh", aliases=("shared.name",))
    b = record("b-forge", [aliased])
    decision = route(task(requirement=req("shared.name")), [b], [], set())
    assert decision.status == "routed"
    assert decision.selected[0].provider == "b-forge"
    assert decision.selected[0].capability == "data.mesh"
    assert decision.negotiation[0].capability == "data.mesh"


def test_alias_divergence_stays_ambiguous_under_requirement() -> None:
    """Same alias resolving to different capabilities is ambiguity, not fit."""
    a = record("a-forge", [cap("data.pipeline", aliases=("shared.name",))])
    b = record("b-forge", [cap("data.mesh", aliases=("shared.name",))])
    decision = route(task(requirement=req("shared.name")), [a, b], [], set())
    assert decision.status == "ambiguous"
    assert "different capabilities" in decision.reason


def test_taskspec_requirement_capability_mismatch_is_a_contract_error() -> None:
    with pytest.raises(ContractError):
        task(requested_capability="a.b", requirement=req("c.d"))


def test_negotiation_results_are_serializable_on_the_decision() -> None:
    rich = record("rich-forge", [cap("data.pipeline", offer=RICH)])
    decision = route(task(requirement=req(technologies=["kafka"])), [rich], [], set())
    data = to_dict(decision)
    assert data["negotiation"][0]["schema"] == "theforge/CapabilityNegotiationResult/v1"
    json.dumps(data)  # canonical JSON-serializable


# --- requirement in planning (check_plan) -----------------------------------------------------


def _plan(provider: str, capability: str = "data.pipeline", action: str = "run") -> ExecutionPlan:
    return ExecutionPlan(
        producer=PRODUCER,
        created_at=utc_now(),
        task_id="t",
        plan_run="r",
        profile="max",
        source="file",
        status="validated",
        pattern="route",
        nodes=[
            PlanNode(
                id="n1", provider=provider, role="primary", capability=capability, action=action
            )
        ],
    )


def test_check_plan_rejects_node_with_incompatible_requirement() -> None:
    """Requirement into planning: a pinned node failing hard gates is a violation."""
    online = record("net-forge", [cap("data.pipeline")], execution=NET_ONLY)
    violations = check_plan(
        _plan("net-forge"),
        {"net-forge": online},
        profile_for("max"),
        requirement=req(offline_required=True),
    )
    assert any("INCOMPATIBLE" in v.detail for v in violations)


def test_check_plan_notes_partial_fit_as_plan_limitation() -> None:
    bare = record("bare-forge", [cap("data.pipeline")])
    checked = checked_plan(
        _plan("bare-forge"),
        {"bare-forge": bare},
        profile_for("max"),
        requirement=req(required_evidence=["finding"]),
    )
    assert checked.status == "validated"
    assert any("partial fit" in note for note in checked.limitations)


def test_check_plan_ignores_nodes_of_other_capabilities() -> None:
    """A per-capability demand never bleeds into unrelated nodes."""
    api = record("api-forge", [cap("api.contract")])
    violations = check_plan(
        _plan("api-forge", "api.contract"),
        {"api-forge": api},
        profile_for("max"),
        requirement=req(offline_required=True),
    )
    assert violations == []


# --- end-to-end through Forger ----------------------------------------------------------------

NET_ENTRY = {
    "id": "fixture-spark-net",
    "argv": fixture_argv("fixture_forge.py", str(PROVIDERS / "fixture-spark-net.json")),
    "trust": "local",
}


def _forger(root: Path) -> Forger:
    forge = root / ".forge"
    return Forger(root, Registry(forge), RunStore(forge))


def test_ask_with_requirement_negotiates_and_persists_results(tmp_path: Path) -> None:
    make_workspace(tmp_path, [SPARK_ENTRY])
    requirement = CapabilityRequirement(
        capability="spark.performance", required_actions=["diagnose"]
    )
    out = _forger(tmp_path).ask(
        AskRequest(
            intent="diagnose this job", capability="spark.performance", requirement=requirement
        )
    )
    assert out.status == "ok"
    assert out.decision.selected[0].provider == "fixture-spark"
    assert [r.state for r in out.decision.negotiation] == ["FULL"]
    store = RunStore(tmp_path / ".forge")
    persisted = store.read_optional(out.run_id, "routing")
    assert persisted["negotiation"][0]["provider"] == "fixture-spark"


def test_ask_use_pins_a_fit_provider(tmp_path: Path) -> None:
    spark_b = dict(
        SPARK_ENTRY,
        id="fixture-spark-b",
        argv=fixture_argv("fixture_forge.py", str(PROVIDERS / "fixture-spark-b.json")),
    )
    make_workspace(tmp_path, [SPARK_ENTRY, spark_b])
    requirement = CapabilityRequirement(capability="spark.performance")
    out = _forger(tmp_path).ask(
        AskRequest(intent="diagnose this job", requirement=requirement, provider="fixture-spark-b")
    )
    assert out.status == "ok"
    assert out.decision.selected[0].provider == "fixture-spark-b"
    assert "pinned provider fixture-spark-b" in out.decision.reason


def test_ask_use_cannot_override_a_hard_gate(tmp_path: Path) -> None:
    """§91: --use never overrides policy/runtime incompatibility."""
    make_workspace(tmp_path, [SPARK_ENTRY, NET_ENTRY])
    requirement = CapabilityRequirement(capability="spark.performance", offline_required=True)
    out = _forger(tmp_path).ask(
        AskRequest(
            intent="diagnose this job", requirement=requirement, provider="fixture-spark-net"
        )
    )
    assert out.status == "no_route"
    assert "fixture-spark-net" in out.decision.reason
    assert "INCOMPATIBLE" in out.decision.reason
    assert out.result is None  # nothing executed


def test_ask_requirement_mismatch_with_capability_is_a_contract_error(tmp_path: Path) -> None:
    make_workspace(tmp_path, [SPARK_ENTRY])
    with pytest.raises(ContractError):
        _forger(tmp_path).ask(
            AskRequest(
                intent="x",
                capability="api.contract",
                requirement=CapabilityRequirement(capability="spark.performance"),
            )
        )
