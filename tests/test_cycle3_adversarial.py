"""Cycle 3 Wave S — adversarial cases the spec names that the per-wave suites
do not already pin down:

- a semantic proposal whose dependencies form a cycle is rejected by the same
  ``check_plan`` that validates every plan (planner reasoning never bypasses
  structural validation);
- a timeout in one parallel node fails only that branch — independent nodes
  still finish and dependents are ``skipped``;
- resuming a plan that ended ``partial`` reuses the proven nodes and
  re-executes the failed ones;
- a tampered ``handoff`` artifact on disk makes the consumer node re-execute —
  reuse is by verified identity, not by file presence.

Already pinned elsewhere (kept out of this file on purpose): invented
provider/capability/over-budget proposals, malformed/unavailable resolver,
refusals and transport failures in ``test_hybrid_planner.py``,
``test_semantic_routing.py``, ``test_protocol_adversarial.py``; secrets and
huge/duplicated payloads in ``test_handoff.py``; poisoned metrics in
``test_economy.py``; same-identity verifiers in
``test_independent_verification.py``.
"""

import json
from pathlib import Path
from typing import Any

from helpers import (
    API_PLAN_ENTRY,
    SPARK_PLAN_ENTRY,
    bad_entry,
    make_workspace,
)
from theforge.contracts import SemanticPlanProposal, from_dict
from theforge.contracts.codes import Codes
from theforge.contracts.receipt import ExecutionReceipt
from theforge.forger import Forger, PlanCommand, PlanExecutor
from theforge.planning.propose import proposal_plan
from theforge.profiles import PROFILES
from theforge.registry import Registry
from theforge.runs import RunStore

MAX = PROFILES["max"]


def _executor(
    root: Path,
    entries: list[dict[str, Any]],
    **forger_kw: Any,
) -> tuple[PlanExecutor, RunStore]:
    forge = make_workspace(root, entries)
    store = RunStore(forge)
    return PlanExecutor(Forger(root, Registry(forge), store, **forger_kw)), store


def _node(
    nid: str, provider: str, capability: str, action: str, *deps: str, role: str = "standalone"
) -> dict[str, Any]:
    node: dict[str, Any] = {
        "id": nid,
        "role": role,
        "provider": provider,
        "capability": capability,
        "action": action,
    }
    if deps:
        node["depends_on"] = [
            {"node": d, "epistemic": "explicit", "evidence": "plan file"} for d in deps
        ]
        node["inputs"] = list(deps)
    return node


def _plan_file(path: Path, nodes: list[dict[str, Any]], pattern: str) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema": "theforge/ExecutionPlan/v1",
                "task_id": "t",
                "producer": {"id": "theforge", "version": "0"},
                "created_at": "2026-01-01T00:00:00Z",
                "status": "draft",
                "pattern": pattern,
                "profile": "max",
                "violations": [],
                "source": "file",
                "nodes": nodes,
            }
        ),
        encoding="utf-8",
    )
    return path


# --- semantic planner: a proposal that closes a cycle is rejected -------------


def test_semantic_proposal_with_a_cycle_is_rejected(tmp_path: Path) -> None:
    proposal = from_dict(
        SemanticPlanProposal,
        {
            "schema": "theforge/SemanticPlanProposal/v1",
            "nodes": [
                {
                    "ref": "n1",
                    "provider": "fixture-spark",
                    "capability": "spark.performance",
                    "action": "diagnose",
                    "depends_on": ["n2"],
                    "inputs": ["n2"],
                },
                {
                    "ref": "n2",
                    "provider": "fixture-api",
                    "capability": "api.contract",
                    "action": "review",
                    "depends_on": ["n1"],
                    "inputs": ["n1"],
                },
            ],
            "rationale": "each consumes the other",
            "confidence": "medium",
        },
    )
    from test_hybrid_planner import _options_records, _task

    plan = proposal_plan(
        proposal, _task(), _options_records(), MAX, plan_run="p-1", planner="fixture-planner"
    )
    assert plan.status == "rejected"
    assert any(v.code == Codes.PLAN_INVALID and "cycle" in v.detail for v in plan.violations)


# --- parallel: a timeout kills only that branch -------------------------------


def test_parallel_node_timeout_fails_only_that_branch(tmp_path: Path) -> None:
    executor, _store = _executor(
        tmp_path, [SPARK_PLAN_ENTRY, bad_entry("timeout", "bad-forge")], execute_timeout=3
    )
    plan_file = _plan_file(
        tmp_path / "plan.json",
        [
            _node("slow", "bad-forge", "bad.thing", "run"),
            _node("spark", "fixture-spark", "spark.performance", "diagnose"),
            _node("downstream", "fixture-spark", "spark.performance", "optimize", "slow"),
        ],
        "parallel",
    )
    out = executor.run(
        PlanCommand(intent="parallel timeout spec", plan_file=plan_file, execute=True)
    )
    assert out.result is not None
    nodes = {n.node: n for n in out.result.nodes}
    # The timed-out node is a provider failure; the independent node finished.
    assert nodes["slow"].status == "provider_failure"
    assert nodes["slow"].error is not None
    assert nodes["slow"].error.code == Codes.PROTO_TIMEOUT
    assert nodes["spark"].status == "ok"
    # The dependent never ran — and says exactly why.
    assert nodes["downstream"].status == "skipped"
    assert nodes["downstream"].blocked_by == "slow"
    assert out.status == "partial"


# --- resume: after ``partial`` and after a tampered handoff -------------------


def test_resume_after_a_partial_plan(tmp_path: Path) -> None:
    executor, store = _executor(tmp_path, [SPARK_PLAN_ENTRY, bad_entry("crash", "bad-crash")])
    plan_file = _plan_file(
        tmp_path / "plan.json",
        [
            _node("good", "fixture-spark", "spark.performance", "diagnose"),
            _node("doomed", "bad-crash", "bad.thing", "run"),
        ],
        "parallel",
    )
    first = executor.run(PlanCommand(intent="resume spec", plan_file=plan_file, execute=True))
    assert first.status == "partial" and first.result is not None
    assert {n.node: n.status for n in first.result.nodes} == {
        "good": "ok",
        "doomed": "provider_failure",
    }
    good_run = {n.node: n for n in first.result.nodes}["good"].run_id

    out = executor.run(PlanCommand(intent="resume spec", execute=True, resume_run=first.run_id))
    assert out.result is not None
    nodes = {n.node: n for n in out.result.nodes}
    # The proven node is re-hydrated verbatim; the failed one ran again.
    assert nodes["good"].reused and nodes["good"].attempts == 0
    assert nodes["good"].run_id == good_run
    assert not nodes["doomed"].reused and nodes["doomed"].attempts == 1
    assert nodes["doomed"].status == "provider_failure"  # still crashes
    assert out.status == "partial"
    receipt = store.read_contract(out.run_id, "receipt", ExecutionReceipt)
    assert any("resume: node doomed re-executed" in n for n in receipt.limitations)


def test_tampered_handoff_re_executes_the_consumer(tmp_path: Path) -> None:
    executor, store = _executor(tmp_path, [SPARK_PLAN_ENTRY, API_PLAN_ENTRY])
    plan_file = _plan_file(
        tmp_path / "plan.json",
        [
            _node("n1", "fixture-spark", "spark.performance", "diagnose", role="producer"),
            _node("n2", "fixture-api", "api.contract", "review", "n1", role="consumer"),
        ],
        "pipeline",
    )
    first = executor.run(PlanCommand(intent="resume spec", plan_file=plan_file, execute=True))
    assert first.status == "ok" and first.result is not None
    n2_run = first.result.nodes[1].run_id
    assert n2_run is not None
    # Tamper the recorded handoff: valid JSON, changed content — the hash the
    # receipt recorded no longer matches what is on disk.
    handoff_path = store.run_dir(n2_run) / "handoff.json"
    payload = json.loads(handoff_path.read_text(encoding="utf-8"))
    payload["items"][0]["claim"] = "rewritten upstream claim"
    handoff_path.write_text(json.dumps(payload), encoding="utf-8")

    out = executor.run(PlanCommand(intent="resume spec", execute=True, resume_run=first.run_id))
    assert out.result is not None
    nodes = {n.node: n for n in out.result.nodes}
    assert nodes["n1"].reused and nodes["n1"].attempts == 0
    assert not nodes["n2"].reused and nodes["n2"].attempts == 1
    receipt = store.read_contract(out.run_id, "receipt", ExecutionReceipt)
    assert any("resume: node n2 re-executed" in n for n in receipt.limitations)
