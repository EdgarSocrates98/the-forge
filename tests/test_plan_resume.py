"""Cycle 3 Wave F: durable plan state, resume and retry.

Unit layer: the ``RetryPolicy`` loader/backoff and the ``PlanState`` contract.
Integration layer: real plan runs with the fixture providers — ``plan-state``
persistence and receipt binding, ``resume`` reusing intact nodes (F2: child hash
chain, provider identity, recomputed handoff), crash recovery from the state
snapshot, and the retry policy driving a flaky provider's second attempt.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from helpers import (
    API_PLAN_ENTRY,
    FLAKY_ENTRY,
    SPARK_PLAN_ENTRY,
    make_workspace,
)
from theforge.contracts.base import ContractError, from_dict, to_dict
from theforge.contracts.codes import Codes
from theforge.contracts.plan import PlanNodeState, PlanState
from theforge.contracts.receipt import ExecutionReceipt
from theforge.contracts.telemetry import RunTelemetry
from theforge.contracts.types import Producer
from theforge.errors import UsageError
from theforge.forger import AskRequest, Forger, PlanCommand, PlanExecutor
from theforge.planning.retry import (
    MAX_ATTEMPTS,
    RetryPolicy,
    load_retry_config,
    retry_backoff,
    retryable,
)
from theforge.registry import Registry
from theforge.runs import RunStore

P = Producer(id="theforge", version="1")
TS = "2026-01-01T00:00:00Z"
SHA = "a" * 64


def _executor(root: Path, entries: list[dict[str, Any]]) -> tuple[PlanExecutor, RunStore]:
    forge = make_workspace(root, entries)
    store = RunStore(forge)
    return PlanExecutor(Forger(root, Registry(forge), store)), store


def _node(nid: str, provider: str, capability: str, action: str,
          *deps: str) -> dict[str, Any]:
    node: dict[str, Any] = {"id": nid, "role": "standalone", "provider": provider,
                            "capability": capability, "action": action}
    if deps:
        node["depends_on"] = [{"node": d, "epistemic": "explicit",
                               "evidence": "plan file"} for d in deps]
        node["inputs"] = list(deps)
    return node


def _plan_file(path: Path, nodes: list[dict[str, Any]], pattern: str = "pipeline") -> Path:
    path.write_text(json.dumps({"task_id": "from-file", "pattern": pattern,
                                "source": "file", "profile": "max", "nodes": nodes}),
                    encoding="utf-8")
    return path


def _two_node_plan(tmp_path: Path) -> Path:
    return _plan_file(tmp_path / "plan.json", [
        _node("n1", "fixture-spark", "spark.performance", "diagnose"),
        _node("n2", "fixture-api", "api.contract", "review", "n1")])


def _run(executor: PlanExecutor, plan_file: Path, **kw: Any) -> Any:
    return executor.run(PlanCommand(intent="resume spec", profile="max",
                                    plan_file=plan_file, execute=True, **kw))


def _retry_toml(root: Path, max_attempts: int = 3) -> None:
    config = root / ".forge" / "config"
    config.mkdir(parents=True, exist_ok=True)
    (config / "retry.toml").write_text(
        f"[retry]\nmax_attempts = {max_attempts}\n"
        "backoff_seconds = 0\nbackoff_cap_seconds = 0\n", encoding="utf-8")


# --- retry policy (unit) -------------------------------------------------------


def test_retry_defaults_never_retry() -> None:
    policy = RetryPolicy()
    assert policy.max_attempts == 1 and policy.source == "defaults"
    assert retryable(policy, Codes.PROTO_TIMEOUT)  # eligible code, but attempts=1


def test_retryable_only_listed_codes() -> None:
    policy = RetryPolicy(max_attempts=3,
                         retryable_codes=frozenset({Codes.PROTO_EXIT}))
    assert retryable(policy, Codes.PROTO_EXIT)
    assert not retryable(policy, Codes.PROTO_TIMEOUT)
    assert not retryable(policy, Codes.PLAN_INVALID)
    assert not retryable(policy, None)


def test_retry_backoff_is_exponential_and_capped() -> None:
    policy = RetryPolicy(max_attempts=MAX_ATTEMPTS, backoff_seconds=0.5,
                         backoff_cap_seconds=2.0)
    assert retry_backoff(policy, 1) == 0.5
    assert retry_backoff(policy, 2) == 1.0
    assert retry_backoff(policy, 9) == 2.0


def test_retry_config_merges_user_then_project(tmp_path: Path) -> None:
    user = tmp_path / "user"
    project = tmp_path / "ws" / ".forge"
    (user).mkdir(parents=True)
    (project / "config").mkdir(parents=True)
    (user / "retry.toml").write_text(
        "[retry]\nmax_attempts = 2\nbackoff_seconds = 1.5\n", encoding="utf-8")
    (project / "config" / "retry.toml").write_text(
        "[retry]\nmax_attempts = 4\n", encoding="utf-8")
    warnings: list[str] = []
    policy = load_retry_config(user_dir=user, forge_dir=project, warnings=warnings)
    assert policy.max_attempts == 4 and policy.backoff_seconds == 1.5
    assert policy.source == "project" and warnings == []


def test_retry_config_malformed_values_warn_and_never_raise(tmp_path: Path) -> None:
    user = tmp_path / "user"
    project = tmp_path / "ws" / ".forge"
    (project / "config").mkdir(parents=True)
    (project / "config" / "retry.toml").write_text(
        "[retry]\nmax_attempts = 99\nbackoff_seconds = -1\nretryable_codes = 5\n",
        encoding="utf-8")
    warnings: list[str] = []
    policy = load_retry_config(user_dir=user, forge_dir=project, warnings=warnings)
    assert policy == RetryPolicy()  # every key rejected, defaults kept
    assert len(warnings) == 3


# --- PlanState contract (unit) -------------------------------------------------


def test_plan_state_contract_round_trip_and_schema_guard() -> None:
    state = PlanState(producer=P, created_at=TS, plan_run="p1", run_state="running",
                      nodes=[PlanNodeState(node="n1", state="succeeded", run_id="r1",
                                           result_sha256=SHA, attempts=1)])
    data = to_dict(state)
    assert data["schema"] == "theforge/PlanState/v1"
    parsed = from_dict(PlanState, data)
    assert parsed == state
    with pytest.raises(ContractError, match="unsupported schema"):
        from_dict(PlanState, {**data, "schema": "other/v9"})


# --- plan-state persistence (integration) ---------------------------------------


def test_plan_state_is_persisted_and_bound_in_the_receipt(tmp_path: Path) -> None:
    executor, store = _executor(tmp_path, [SPARK_PLAN_ENTRY, API_PLAN_ENTRY])
    out = _run(executor, _two_node_plan(tmp_path))
    assert out.status == "ok"
    state = store.read(out.run_id, "plan-state")
    assert state["schema"] == "theforge/PlanState/v1"
    assert state["run_state"] == "completed" and state["plan_run"] == out.run_id
    states = {n["node"]: n["state"] for n in state["nodes"]}
    assert states == {"n1": "succeeded", "n2": "succeeded"}
    receipt = store.read_contract(out.run_id, "receipt", ExecutionReceipt)
    assert receipt.plan is not None
    assert receipt.plan.plan_state_sha256 == store.persisted_sha256(
        out.run_id, "plan-state")


# --- resume (integration) -------------------------------------------------------


def test_resume_reuses_every_intact_node(tmp_path: Path) -> None:
    executor, store = _executor(tmp_path, [SPARK_PLAN_ENTRY, API_PLAN_ENTRY])
    first = _run(executor, _two_node_plan(tmp_path))
    assert first.status == "ok" and first.result is not None

    out = executor.run(PlanCommand(intent="resume spec", profile="max",
                                   execute=True, resume_run=first.run_id))
    assert out.status == "ok" and out.result is not None
    prior = {n.node: n for n in first.result.nodes}
    for node in out.result.nodes:
        assert node.reused and node.attempts == 0
        assert node.run_id == prior[node.node].run_id  # evidence is not re-stamped
        assert node.result_sha256 == prior[node.node].result_sha256

    # Identical inputs: the task and plan hashes are byte-identical across runs.
    assert store.persisted_sha256(out.run_id, "task") == \
        store.persisted_sha256(first.run_id, "task")
    assert store.persisted_sha256(out.run_id, "plan") == \
        store.persisted_sha256(first.run_id, "plan")

    receipt = store.read_contract(out.run_id, "receipt", ExecutionReceipt)
    assert receipt.resumed_from == first.run_id
    assert any("reused 2 of 2" in n for n in receipt.limitations)
    state = store.read(out.run_id, "plan-state")
    assert state["resumed_from"] == first.run_id


def test_resume_re_executes_a_tampered_node(tmp_path: Path) -> None:
    executor, store = _executor(tmp_path, [SPARK_PLAN_ENTRY, API_PLAN_ENTRY])
    first = _run(executor, _two_node_plan(tmp_path))
    assert first.status == "ok" and first.result is not None
    n1_run = first.result.nodes[0].run_id
    assert n1_run is not None
    (store.run_dir(n1_run) / "result.json").unlink()  # tamper: artifact goes missing

    out = executor.run(PlanCommand(intent="resume spec", profile="max",
                                   execute=True, resume_run=first.run_id))
    assert out.result is not None
    nodes = {n.node: n for n in out.result.nodes}
    assert not nodes["n1"].reused and nodes["n1"].attempts == 1
    assert nodes["n1"].run_id != n1_run  # a fresh child run produced a new result
    # n2 depends on n1: its recorded handoff cannot be reproduced (new upstream
    # run id inside the handoff), so it re-executes too — integrity over reuse.
    assert not nodes["n2"].reused
    receipt = store.read_contract(out.run_id, "receipt", ExecutionReceipt)
    assert any("resume: node n1 re-executed" in n for n in receipt.limitations)


def test_resume_after_crash_uses_the_plan_state_snapshot(tmp_path: Path) -> None:
    executor, store = _executor(tmp_path, [SPARK_PLAN_ENTRY, API_PLAN_ENTRY])
    plan_file = _two_node_plan(tmp_path)
    armed = {"v": True}
    real_run_node = PlanExecutor._run_node

    def crash_once(self: PlanExecutor, trace: Any, plan: Any, node: Any,
                   sources: Any, levels: Any, parent: Any = None) -> Any:
        if node.id == "n2" and armed["v"]:
            armed["v"] = False
            raise RuntimeError("simulated crash")
        return real_run_node(self, trace, plan, node, sources, levels, parent=parent)

    executor._run_node = crash_once.__get__(executor)  # type: ignore[method-assign]
    first = executor.run(PlanCommand(intent="resume spec", profile="max",
                                   plan_file=plan_file, execute=True))
    assert first.status == "provider_failure"
    # The crash left a running-state snapshot: n1 succeeded, n2 never recorded.
    assert store.read_optional(first.run_id, "plan-result") is None
    state = store.read(first.run_id, "plan-state")
    assert state["run_state"] == "running"

    out = executor.run(PlanCommand(intent="resume spec", profile="max",
                                   execute=True, resume_run=first.run_id))
    assert out.status == "ok" and out.result is not None
    nodes = {n.node: n for n in out.result.nodes}
    assert nodes["n1"].reused and nodes["n1"].attempts == 0
    assert nodes["n2"].status == "ok" and not nodes["n2"].reused
    assert nodes["n2"].run_id is not None
    # n2's handoff was rebuilt against the reused n1 — identical to what a
    # straight run would deliver (same upstream evidence, original plan_run).
    assert store.read_optional(nodes["n2"].run_id, "handoff") is not None


def test_resume_of_an_unknown_or_non_plan_run_is_a_usage_error(
        tmp_path: Path) -> None:
    executor, store = _executor(tmp_path, [SPARK_PLAN_ENTRY])
    with pytest.raises(UsageError, match="unknown run"):
        executor.run(PlanCommand(intent="x", execute=True,
                                 resume_run="20990101T000000Z-deadbeef"))
    # A completed single-provider run has a task but no plan.
    ask = executor.forger.ask(AskRequest(intent="spark diagnose"))
    assert ask.run_id
    with pytest.raises(UsageError, match="no resumable plan"):
        executor.run(PlanCommand(intent="x", execute=True, resume_run=ask.run_id))


def test_resume_revalidates_the_plan_against_the_registry(tmp_path: Path) -> None:
    executor, store = _executor(tmp_path, [SPARK_PLAN_ENTRY, API_PLAN_ENTRY])
    first = _run(executor, _two_node_plan(tmp_path))
    assert first.status == "ok"
    # The provider the plan pinned is gone: revalidation must refuse, not reuse.
    (tmp_path / ".forge" / "config").mkdir(parents=True, exist_ok=True)
    from helpers import write_providers
    write_providers(tmp_path / ".forge", [SPARK_PLAN_ENTRY])
    executor = PlanExecutor(Forger(tmp_path, Registry(tmp_path / ".forge"), store))
    out = executor.run(PlanCommand(intent="resume spec", execute=True,
                                   resume_run=first.run_id))
    assert out.status == "refused" and out.error is not None
    assert out.error.code == Codes.PLAN_CAPABILITY


# --- retry (integration) --------------------------------------------------------


def test_retry_policy_drives_a_second_attempt(tmp_path: Path) -> None:
    executor, store = _executor(tmp_path, [FLAKY_ENTRY])
    _retry_toml(tmp_path)  # max_attempts = 3, zero backoff
    plan_file = _plan_file(tmp_path / "plan.json", [
        _node("flaky", "fixture-flaky", "flaky.thing", "run")])
    out = _run(executor, plan_file)
    assert out.status == "ok" and out.result is not None
    node = out.result.nodes[0]
    assert node.status == "ok" and node.attempts == 2  # exit 3, then success
    # Each attempt is a real, receipted child run — the failed one is auditable.
    assert node.receipt_sha256 == store.persisted_sha256(node.run_id, "receipt")
    receipt = store.read_contract(out.run_id, "receipt", ExecutionReceipt)
    assert any("node flaky: retried 1x (attempt runs:" in n
               for n in receipt.limitations)
    telemetry = store.read_contract(out.run_id, "telemetry", RunTelemetry)
    assert telemetry.providers_executed.value == 2
    budget = store.read(out.run_id, "budget")
    assert budget["provider_calls"] == 3
    assert any("retry reserve" in item for item in budget["adjustments"])


def test_retry_is_off_by_default(tmp_path: Path) -> None:
    executor, _ = _executor(tmp_path, [FLAKY_ENTRY])
    plan_file = _plan_file(tmp_path / "plan.json", [
        _node("flaky", "fixture-flaky", "flaky.thing", "run")])
    out = _run(executor, plan_file)
    assert out.result is not None
    node = out.result.nodes[0]
    assert node.status == "provider_failure" and node.attempts == 1
    assert node.error is not None and node.error.code == Codes.PROTO_EXIT


def test_retry_never_retries_a_refusal(tmp_path: Path) -> None:
    from helpers import bad_entry
    executor, _ = _executor(tmp_path, [bad_entry("refuse", "bad-r")])
    _retry_toml(tmp_path, max_attempts=MAX_ATTEMPTS)
    plan_file = _plan_file(tmp_path / "plan.json", [
        _node("bad", "bad-r", "bad.thing", "run")])
    out = _run(executor, plan_file)
    assert out.result is not None
    node = out.result.nodes[0]
    assert node.status == "refused" and node.attempts == 1
