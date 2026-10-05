"""Cycle 3 wave C: the hybrid planner — deterministic tiers first, a semantic
planner only when they cannot decide, and the validator sovereign over whatever
it proposes (C1-C5).

- Tier 0/1 (``decompose``): declared capability-graph relations (``requires``,
  produces→consumes) order the pipeline ahead of the intent-order keyword
  proxy; declared ``conflicts`` and relation cycles are ambiguities, never picks.
- Tier 2 (``planning.propose`` + ``PlanExecutor._semantic``): a provider whose
  capability declares ``proposes_plans`` answers the ``plan`` op with
  ``purpose="proposal"``; the proposal is materialized into an ``ExecutionPlan``
  (``source="semantic"``) and re-validated by ``check_plan`` — invented
  providers/capabilities/actions are violations, not repairs.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from helpers import (
    API_ENTRY,
    API_PLAN_ENTRY,
    PLANNER_ENTRY,
    PROVIDERS,
    SPARK_ENTRY,
    SPARK_PLAN_ENTRY,
    make_workspace,
    write_file,
)
from theforge.capability_graph import build_capability_graph
from theforge.context.scan import scan_workspace
from theforge.contracts import (
    ErrorInfo,
    ExecutionReceipt,
    ForgeManifest,
    Producer,
    SemanticPlanProposal,
    TaskSpec,
    from_dict,
)
from theforge.contracts.envelope import Response
from theforge.contracts.routing import Candidate, Confidence, RoutingDecision
from theforge.forger import Forger, PlanCommand, PlanExecutor
from theforge.meta import PRODUCER
from theforge.planning.decompose import (
    GRAPH_ORDER_RULE,
    INTENT_ORDER_RULE,
    decompose,
    decomposition_dependencies,
)
from theforge.planning.propose import (
    options_of,
    planner_capability,
    proposal_plan,
    request_proposal,
)
from theforge.profiles import profile_for
from theforge.registry import ProviderEntry, Registry, RegistryRecord
from theforge.routing import route
from theforge.runs import RunStore
from theforge.workspace import describe_workspace

MAX = profile_for("max")
ECONOMY = profile_for("economy")
TS = "2026-01-01T00:00:00Z"


def _record(name: str, pid: str, *, trust: str = "local") -> RegistryRecord:
    data = json.loads((PROVIDERS / name).read_text(encoding="utf-8"))
    data.pop("estimate", None)
    data.pop("proposal", None)
    return RegistryRecord(
        entry=ProviderEntry(id=pid, argv=["x"], trust=trust), state="ready",
        manifest=from_dict(ForgeManifest, data), manifest_sha256="0" * 64,
        protocol="forge/v1")


def _synthetic(pid: str, *caps: dict[str, Any]) -> RegistryRecord:
    capabilities = [{
        "id": c["id"], "actions": c.get("actions", ["run"]),
        "default_action": c.get("actions", ["run"])[0], "state": c.get("state", "supported"),
        "operation_class": "read_only",
        "signals": {"keywords": c.get("keywords", []), "file_globs": c.get("globs", []),
                    "dependencies": c.get("deps", [])},
        **({"relations": c["relations"]} if "relations" in c else {}),
        **({"proposes_plans": True} if c.get("planner") else {}),
    } for c in caps]
    manifest = from_dict(ForgeManifest, {
        "schema": "theforge/ForgeManifest/v1", "id": pid, "version": "1",
        "protocols": ["forge/v1"], "ops": ["describe", "health", "execute", "plan"],
        "capabilities": capabilities})
    return RegistryRecord(entry=ProviderEntry(id=pid, argv=["x"], trust="local"),
                          state="ready", manifest=manifest)


def _decompose(root: Path, records: dict[str, RegistryRecord], intent: str,
               *, graph: bool = True, profile=MAX):
    scan = scan_workspace(root, [])
    descriptor = describe_workspace(root, list(records.values()), scan)
    task = TaskSpec(producer=PRODUCER, created_at=TS, id="t", intent=intent,
                    workspace_root=str(root))
    decision = route(task, list(records.values()), scan.files,
                     decomposition_dependencies(root, descriptor))
    cap_graph = (build_capability_graph(records, descriptor, run_id="t")
                 if graph else None)
    return decompose(task, decision, records, descriptor, scan, profile,
                     graph=cap_graph)


# --- tier 1: capability-graph ordering ------------------------------------------------------


def test_graph_order_beats_intent_position(tmp_path: Path) -> None:
    """api's keyword comes first but spark produces what api consumes: the
    declared relation orders the pipeline (spark -> api), not the proxy."""
    records = {"fixture-spark": _record("fixture-spark-plan.json", "fixture-spark"),
               "fixture-api": _record("fixture-api-plan.json", "fixture-api")}
    write_file(tmp_path, "requirements.txt", "pyspark\nfastapi\n")
    write_file(tmp_path, "jobs/x_glue_job.py", "")
    write_file(tmp_path, "openapi.yaml", "openapi: 3.0.0\n")
    result = _decompose(tmp_path, records, "revise a api usando spark")
    assert result.status == "planned", result.decision.reason
    assert [(n.provider, n.role) for n in result.nodes] == [
        ("fixture-spark", "producer"), ("fixture-api", "consumer")]
    [dep] = result.nodes[1].depends_on
    assert dep.rule == GRAPH_ORDER_RULE
    assert "produces spark.analysis-report" in dep.evidence


def test_without_graph_intent_order_rules(tmp_path: Path) -> None:
    """Same inputs, no graph: the intent-order proxy gives api first."""
    records = {"fixture-spark": _record("fixture-spark-plan.json", "fixture-spark"),
               "fixture-api": _record("fixture-api-plan.json", "fixture-api")}
    write_file(tmp_path, "requirements.txt", "pyspark\nfastapi\n")
    write_file(tmp_path, "jobs/x_glue_job.py", "")
    write_file(tmp_path, "openapi.yaml", "openapi: 3.0.0\n")
    result = _decompose(tmp_path, records, "revise a api usando spark", graph=False)
    assert result.status == "planned", result.decision.reason
    assert result.nodes[0].provider == "fixture-api"
    assert result.nodes[1].depends_on[0].rule == INTENT_ORDER_RULE


def test_requires_relation_orders_regardless_of_keywords(tmp_path: Path) -> None:
    records = {
        "alpha": _synthetic("alpha", {"id": "alpha.run", "keywords": ["deploy"],
                                      "globs": ["*.alpha"],
                                      "relations": {"requires": ["beta/beta.prepare"]}}),
        "beta": _synthetic("beta", {"id": "beta.prepare", "keywords": ["prepare"],
                                    "globs": ["*.beta"]}),
    }
    write_file(tmp_path, "x.alpha")
    write_file(tmp_path, "y.beta")
    result = _decompose(tmp_path, records, "deploy after prepare")
    assert result.status == "planned", result.decision.reason
    assert [n.provider for n in result.nodes] == ["beta", "alpha"]
    assert result.nodes[1].depends_on[0].rule == GRAPH_ORDER_RULE


def test_declared_conflicts_are_ambiguous(tmp_path: Path) -> None:
    records = {
        "alpha": _synthetic("alpha", {"id": "alpha.run", "keywords": ["alpha"],
                                      "globs": ["*.alpha"],
                                      "relations": {"conflicts": ["beta/beta.run"]}}),
        "beta": _synthetic("beta", {"id": "beta.run", "keywords": ["beta"],
                                    "globs": ["*.beta"]}),
    }
    write_file(tmp_path, "x.alpha")
    write_file(tmp_path, "y.beta")
    result = _decompose(tmp_path, records, "alpha then beta")
    assert result.status == "ambiguous"
    assert "conflicts" in result.decision.reason


def test_relation_cycle_is_ambiguous(tmp_path: Path) -> None:
    records = {
        "alpha": _synthetic("alpha", {"id": "alpha.run", "keywords": ["alpha"],
                                      "globs": ["*.alpha"],
                                      "relations": {"requires": ["beta/beta.run"]}}),
        "beta": _synthetic("beta", {"id": "beta.run", "keywords": ["beta"],
                                    "globs": ["*.beta"],
                                    "relations": {"requires": ["alpha/alpha.run"]}}),
    }
    write_file(tmp_path, "x.alpha")
    write_file(tmp_path, "y.beta")
    result = _decompose(tmp_path, records, "alpha then beta")
    assert result.status == "ambiguous"
    assert "cycle" in result.decision.reason


def test_keywordless_candidates_ordered_by_declared_relations(tmp_path: Path) -> None:
    """No keyword matched at all (qualified by dependencies/globs): the declared
    produces→consumes chain still orders them — previously ambiguous."""
    records = {"fixture-spark": _record("fixture-spark-plan.json", "fixture-spark"),
               "fixture-api": _record("fixture-api-plan.json", "fixture-api")}
    write_file(tmp_path, "requirements.txt", "pyspark\nfastapi\n")
    write_file(tmp_path, "jobs/x_glue_job.py", "")
    write_file(tmp_path, "openapi.yaml", "openapi: 3.0.0\n")
    without_graph = _decompose(tmp_path, records, "melhore o projeto", graph=False)
    assert without_graph.status == "ambiguous"  # the tier-2 trigger
    with_graph = _decompose(tmp_path, records, "melhore o projeto")
    assert with_graph.status == "planned", with_graph.decision.reason
    assert [n.provider for n in with_graph.nodes] == ["fixture-spark", "fixture-api"]


# --- tier 2: planner selection ---------------------------------------------------------------


def _task(intent: str = "x") -> TaskSpec:
    return TaskSpec(producer=PRODUCER, created_at=TS, id="t", intent=intent,
                    workspace_root=".")


def test_planner_capability_picks_declaring_capability() -> None:
    planner = _synthetic("zz-planner", {"id": "planner.compose", "planner": True})
    plain = _synthetic("aa-plain", {"id": "plain.run"})
    records = {"zz-planner": planner, "aa-plain": plain}
    picked = planner_capability(records)
    assert picked is not None
    record, capability = picked
    assert record.entry.id == "zz-planner" and capability.id == "planner.compose"


def test_planner_capability_none_without_declaration() -> None:
    assert planner_capability({"a": _synthetic("a", {"id": "a.x"})}) is None


def test_planner_capability_skips_broken_blocked_unverified() -> None:
    planner = _synthetic("planner", {"id": "planner.compose", "planner": True})
    broken = RegistryRecord(
        entry=ProviderEntry(id="broken", argv=["x"], trust="local"),
        state="broken", manifest=None)
    records = {"planner": planner, "broken": broken}
    assert planner_capability(records) is not None
    untrusted = _synthetic("unv", {"id": "u.compose", "planner": True})
    untrusted = RegistryRecord(
        entry=ProviderEntry(id="unv", argv=["x"], trust="unverified"),
        state="ready", manifest=untrusted.manifest)
    assert planner_capability({"unv": untrusted}) is None
    assert planner_capability({"unv": untrusted}, allow_unverified=True) is not None


# --- tier 2: request/response ---------------------------------------------------------------


class _FakeTransport:
    """Answers the ``plan`` op with a canned payload; records the request."""

    def __init__(self, response: Response) -> None:
        self.response = response
        self.requests: list[dict[str, Any]] = []

    def __call__(self, argv: Sequence[str]) -> _FakeTransport:
        return self

    def call(self, op: str, payload: dict[str, Any], *, timeout: float,
             cwd: Path | None = None, check_protocol: bool = True) -> Response:
        self.requests.append({"op": op, "payload": payload})
        return self.response


def _response(payload: dict[str, Any], *, pid: str = "planner",
              version: str = "1", status: str = "ok",
              error: dict[str, Any] | None = None) -> Response:
    return Response(request_id="r", op="plan",
                    producer=Producer(id=pid, version=version),
                    status=status, payload=payload,  # type: ignore[arg-type]
                    error=from_dict(ErrorInfo, error) if error else None)


def _planner_record() -> RegistryRecord:
    return _synthetic("planner", {"id": "planner.compose", "planner": True})


def test_request_proposal_sends_purpose_and_options() -> None:
    proposal = {"schema": "theforge/SemanticPlanProposal/v1", "nodes": []}
    transport = _FakeTransport(_response(proposal))
    record = _planner_record()
    capability = record.manifest.capabilities[0]
    got, note = request_proposal(record, capability, _task(), [], "tie",
                                 transport_factory=transport)
    assert note is None and isinstance(got, SemanticPlanProposal)
    request = transport.requests[0]
    assert request["op"] == "plan"
    assert request["payload"]["purpose"] == "proposal"
    assert request["payload"]["capability"] == "planner.compose"
    assert request["payload"]["ambiguity"] == "tie"


def test_request_proposal_refusal_is_a_limitation() -> None:
    transport = _FakeTransport(_response(
        {}, status="refused",
        error={"code": "X-NOPE", "detail": "cannot", "field": None, "unlock": None}))
    record = _planner_record()
    got, note = request_proposal(record, record.manifest.capabilities[0], _task(),
                                 [], "x", transport_factory=transport)
    assert got is None and note is not None and "X-NOPE" in note


def test_request_proposal_malformed_payload_is_a_limitation() -> None:
    transport = _FakeTransport(_response({"schema": "other/Schema/v9"}))
    record = _planner_record()
    got, note = request_proposal(record, record.manifest.capabilities[0], _task(),
                                 [], "x", transport_factory=transport)
    assert got is None and note is not None


def test_request_proposal_wrong_producer_is_a_limitation() -> None:
    transport = _FakeTransport(_response(
        {"schema": "theforge/SemanticPlanProposal/v1", "nodes": []}, pid="other"))
    record = _planner_record()
    got, note = request_proposal(record, record.manifest.capabilities[0], _task(),
                                 [], "x", transport_factory=transport)
    assert got is None and note is not None


# --- tier 2: proposal -> validated plan -----------------------------------------------------


def _options_records() -> dict[str, RegistryRecord]:
    return {"fixture-spark": _record("fixture-spark-plan.json", "fixture-spark"),
            "fixture-api": _record("fixture-api-plan.json", "fixture-api")}


def _proposal(**kw: Any) -> SemanticPlanProposal:
    base: dict[str, Any] = {
        "schema": "theforge/SemanticPlanProposal/v1",
        "nodes": [
            {"ref": "n1", "provider": "fixture-spark",
             "capability": "spark.performance", "action": "diagnose",
             "rationale": "produces the analysis"},
            {"ref": "n2", "provider": "fixture-api", "capability": "api.contract",
             "action": "review", "depends_on": ["n1"], "inputs": ["n1"],
             "rationale": "consumes it"},
        ],
        "rationale": "data flows spark -> api",
        "confidence": "medium",
        "assumptions": ["the analysis exists"],
        "unknowns": ["contract version"],
    }
    return from_dict(SemanticPlanProposal, {**base, **kw})


def test_proposal_plan_validates_and_binds(tmp_path: Path) -> None:
    plan = proposal_plan(_proposal(), _task(), _options_records(), MAX,
                         plan_run="p-1", planner="fixture-planner")
    assert plan.status == "validated", plan.violations
    assert plan.source == "semantic" and plan.pattern == "pipeline"
    assert [(n.id, n.provider, n.role) for n in plan.nodes] == [
        ("n1", "fixture-spark", "producer"), ("n2", "fixture-api", "consumer")]
    [dep] = plan.nodes[1].depends_on
    assert dep.epistemic == "explicit"
    assert "semantic proposal by fixture-planner" in dep.evidence
    assert "plan proposed by semantic planner fixture-planner" in plan.limitations
    assert "assumption: the analysis exists" in plan.limitations
    assert "planner confidence: medium" in plan.limitations
    assert plan.unknowns == ["contract version"]


def test_proposal_plan_rejects_invented_provider() -> None:
    plan = proposal_plan(
        _proposal(nodes=[{"ref": "n1", "provider": "ghost-forge",
                          "capability": "x.y", "action": "run"}]),
        _task(), _options_records(), MAX, plan_run="p-1", planner="fixture-planner")
    assert plan.status == "rejected"
    assert any("ghost-forge" in v.detail for v in plan.violations)


def test_proposal_plan_rejects_invented_capability_and_action() -> None:
    plan = proposal_plan(
        _proposal(nodes=[{"ref": "n1", "provider": "fixture-spark",
                          "capability": "spark.invented", "action": "diagnose"}]),
        _task(), _options_records(), MAX, plan_run="p-1", planner="fixture-planner")
    assert plan.status == "rejected"
    assert any("spark.invented" in v.detail for v in plan.violations)
    plan = proposal_plan(
        _proposal(nodes=[{"ref": "n1", "provider": "fixture-spark",
                          "capability": "spark.performance", "action": "explode"}]),
        _task(), _options_records(), MAX, plan_run="p-1", planner="fixture-planner")
    assert plan.status == "rejected"
    assert any("explode" in v.detail for v in plan.violations)


def test_proposal_plan_rejects_dup_refs_and_dangling_dependencies() -> None:
    dup = _proposal(nodes=[
        {"ref": "n1", "provider": "fixture-spark", "capability": "spark.performance",
         "action": "diagnose"},
        {"ref": "n1", "provider": "fixture-api", "capability": "api.contract",
         "action": "review"}])
    plan = proposal_plan(dup, _task(), _options_records(), MAX,
                         plan_run="p-1", planner="fixture-planner")
    assert plan.status == "rejected"
    assert any("duplicate node ref" in v.detail for v in plan.violations)
    dangling = _proposal(nodes=[
        {"ref": "n1", "provider": "fixture-spark", "capability": "spark.performance",
         "action": "diagnose", "depends_on": ["ghost"]}])
    plan = proposal_plan(dangling, _task(), _options_records(), MAX,
                         plan_run="p-1", planner="fixture-planner")
    assert plan.status == "rejected"
    assert any("unknown ref 'ghost'" in v.detail for v in plan.violations)


def test_proposal_plan_rejects_over_profile_provider_limit() -> None:
    plan = proposal_plan(_proposal(), _task(), _options_records(), ECONOMY,
                         plan_run="p-1", planner="fixture-planner")
    assert plan.status == "rejected"
    assert any("2 providers" in v.detail for v in plan.violations)


def test_proposal_plan_empty_is_rejected() -> None:
    plan = proposal_plan(_proposal(nodes=[]), _task(), _options_records(), MAX,
                         plan_run="p-1", planner="fixture-planner")
    assert plan.status == "rejected" and plan.violations


def test_options_of_lists_eligible_candidates() -> None:
    decision = RoutingDecision(
        producer=PRODUCER, created_at=TS, task_id="t", status="ambiguous",
        reason="x", confidence=Confidence(level="low"), candidates=[
            Candidate(provider="fixture-api", capability="api.contract"),
            Candidate(provider="fixture-spark", capability="spark.performance"),
        ])
    options = options_of(decision, _options_records())
    assert [(o.provider, o.capability) for o in options] == [
        ("fixture-api", "api.contract"), ("fixture-spark", "spark.performance")]
    api = options[0]
    assert api.actions == ["review", "lint"]
    assert api.consumes == ["spark.analysis-report"]
    assert api.conflicts == []


# --- end to end ------------------------------------------------------------------------------


def _ambiguous_workspace(root: Path) -> None:
    """Both fixtures qualify via dependencies/globs only — no keyword of the
    intent matches, so the deterministic tiers cannot order them."""
    write_file(root, "requirements.txt", "pyspark\nfastapi\n")
    write_file(root, "jobs/x_glue_job.py", "")
    write_file(root, "openapi.yaml", "openapi: 3.0.0\n")


def test_plan_run_uses_semantic_proposal_when_ambiguous(tmp_path: Path) -> None:
    forge = make_workspace(tmp_path,
                           [SPARK_ENTRY, API_ENTRY, PLANNER_ENTRY])
    _ambiguous_workspace(tmp_path)
    store = RunStore(forge)
    out = PlanExecutor(Forger(tmp_path, Registry(forge), store)).run(
        PlanCommand(intent="melhore o projeto", profile="max"))
    assert out.status == "planned", out.error
    plan = out.plan
    assert plan is not None and plan.source == "semantic" and plan.status == "validated"
    assert [(n.provider, n.role) for n in plan.nodes] == [
        ("fixture-spark", "producer"), ("fixture-api", "consumer")]
    assert any("fixture-planner" in lim for lim in plan.limitations)
    proposal = store.read_contract(
        out.run_id, "semantic-proposal", SemanticPlanProposal)
    receipt = store.read_contract(out.run_id, "receipt", ExecutionReceipt)
    assert receipt.plan is not None
    assert receipt.plan.semantic_proposal_sha256 == store.persisted_sha256(
        out.run_id, "semantic-proposal")
    assert proposal.nodes[0].provider == "fixture-spark"
    routing = store.read(out.run_id, "routing")
    assert routing["status"] == "routed"
    assert "semantic plan proposed by fixture-planner" in routing["reason"]


def test_plan_run_ambiguous_without_planner(tmp_path: Path) -> None:
    forge = make_workspace(tmp_path, [SPARK_ENTRY, API_ENTRY])
    _ambiguous_workspace(tmp_path)
    store = RunStore(forge)
    out = PlanExecutor(Forger(tmp_path, Registry(forge), store)).run(
        PlanCommand(intent="melhore o projeto", profile="max"))
    assert out.status == "ambiguous" and out.plan is None
    receipt = store.read_contract(out.run_id, "receipt", ExecutionReceipt)
    assert any("semantic-planning" in lim for lim in receipt.limitations)
    assert store.read_optional(out.run_id, "semantic-proposal") is None


def test_semantic_planner_disabled_under_economy(tmp_path: Path) -> None:
    forge = make_workspace(tmp_path,
                           [SPARK_ENTRY, API_ENTRY, PLANNER_ENTRY])
    _ambiguous_workspace(tmp_path)
    store = RunStore(forge)
    out = PlanExecutor(Forger(tmp_path, Registry(forge), store)).run(
        PlanCommand(intent="melhore o projeto", profile="economy"))
    assert out.status == "ambiguous"
    receipt = store.read_contract(out.run_id, "receipt", ExecutionReceipt)
    assert any("disabled by profile 'economy'" in lim for lim in receipt.limitations)


def test_tier1_graph_orders_plan_run(tmp_path: Path) -> None:
    """e2e: api's keyword precedes spark's but the declared produces→consumes
    relation fixes spark -> api."""
    forge = make_workspace(tmp_path, [SPARK_PLAN_ENTRY, API_PLAN_ENTRY])
    write_file(tmp_path, "requirements.txt", "pyspark\nfastapi\n")
    write_file(tmp_path, "jobs/x_glue_job.py", "")
    write_file(tmp_path, "openapi.yaml", "openapi: 3.0.0\n")
    store = RunStore(forge)
    out = PlanExecutor(Forger(tmp_path, Registry(forge), store)).run(
        PlanCommand(intent="revise a api usando spark", profile="max"))
    assert out.status == "planned", out.error
    assert out.plan is not None and out.plan.source == "decomposed"
    assert [n.provider for n in out.plan.nodes] == ["fixture-spark", "fixture-api"]
    assert out.plan.nodes[1].depends_on[0].rule == GRAPH_ORDER_RULE
