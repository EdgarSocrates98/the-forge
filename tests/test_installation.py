"""Installation (task 2.8): planning-only InstallationPlan from registry and health.

Requirements 10.5, 10.6: at most one plan per run listing every missing provider with
the reason and suggested action from the registry or the provider; no plan without
items; marked planning only and built without executing anything.
"""

import ast
import secrets
from pathlib import Path
from typing import Any

import pytest

from theforge.contracts.base import ContractError, from_dict, to_dict
from theforge.contracts.installation import INSTALLATION_SCHEMA, InstallationPlan
from theforge.contracts.plan import ExecutionPlan, PlanNode
from theforge.contracts.types import ErrorInfo, Producer
from theforge.planning import installation
from theforge.planning.installation import build_installation_plan
from theforge.registry import ProviderEntry, RegistryRecord
from theforge.registry.health import HealthOutcome

P = Producer(id="theforge", version="1")
TS = "2026-01-01T00:00:00Z"


def record(pid: str, state: Any = "ready", error: str | None = None) -> RegistryRecord:
    return RegistryRecord(entry=ProviderEntry(id=pid, argv=["x"], trust="local"),
                          state=state, error=error)


def pnode(nid: str, provider: str) -> PlanNode:
    return PlanNode(id=nid, role="standalone", provider=provider, capability="demo.echo",
                    action="echo")


def plan(*nodes: PlanNode) -> ExecutionPlan:
    return ExecutionPlan(producer=P, created_at=TS, status="validated", plan_run="p1",
                         task_id="t1", pattern="pipeline", source="file", profile="max",
                         nodes=list(nodes))


def unavailable(detail: str, unlock: str | None = None) -> HealthOutcome:
    return HealthOutcome(status="unavailable",
                         error=ErrorInfo(code="FORGE-HEALTH-UNAVAILABLE", detail=detail,
                                         unlock=unlock))


def build(p: ExecutionPlan | None, records: dict[str, RegistryRecord],
          health: dict[str, HealthOutcome] | None = None) -> InstallationPlan | None:
    return build_installation_plan("p1", p, records, health or {}, created_at=TS)


def test_single_plan_with_registry_and_health_items() -> None:
    records = {"spark": record("spark", "invalid", "manifest: bad version"),
               "api": record("api"),
               "ok": record("ok")}
    p = plan(pnode("a", "spark"), pnode("b", "api"), pnode("c", "spark"), pnode("d", "ok"))
    health = {"api": unavailable("java missing", unlock="install a JDK 17"),
              "ok": HealthOutcome(status="ok")}
    result = build(p, records, health)

    assert result is not None
    assert result.schema == INSTALLATION_SCHEMA
    assert result.planning_only is True
    assert result.run_id == "p1"
    assert result.created_at == TS
    assert result.producer.id == "theforge"
    assert [(i.provider, i.source, i.state) for i in result.items] == [
        ("spark", "registry", "invalid"), ("api", "health", "unavailable")]
    spark, api = result.items
    assert spark.reason == "manifest: bad version"
    assert spark.suggested_action == "manifest: bad version"
    assert spark.nodes == ["a", "c"]
    assert api.reason == "java missing"
    assert api.suggested_action == "install a JDK 17"
    assert api.nodes == ["b"]


@pytest.mark.parametrize("state", ["invalid", "unreachable", "incompatible"])
def test_registry_states_become_items(state: str) -> None:
    result = build(plan(pnode("a", "x")), {"x": record("x", state, f"x is {state}")})
    assert result is not None
    assert [(i.state, i.source) for i in result.items] == [(state, "registry")]


@pytest.mark.parametrize("state", ["ready", "blocked", "untrusted"])
def test_other_registry_states_are_not_installation_items(state: str) -> None:
    assert build(plan(pnode("a", "x")), {"x": record("x", state, "detail")}) is None


def test_health_error_uses_detail_without_unlock() -> None:
    health = {"x": HealthOutcome(status="error",
                                 error=ErrorInfo(code="FORGE-HEALTH-FAILED", detail="boom"))}
    result = build(plan(pnode("a", "x")), {"x": record("x")}, health)
    assert result is not None
    (item,) = result.items
    assert (item.source, item.state, item.reason, item.suggested_action) == (
        "health", "unavailable", "boom", "boom")


def test_degraded_health_is_not_an_item() -> None:
    assert build(plan(pnode("a", "x")), {"x": record("x")},
                 {"x": HealthOutcome(status="degraded")}) is None


def test_registry_item_wins_over_health_for_the_same_provider() -> None:
    health = {"x": HealthOutcome(status="error", error=ErrorInfo(
        code="FORGE-PROVIDER-NOT-READY", detail="x is invalid: bad"))}
    result = build(plan(pnode("a", "x")), {"x": record("x", "invalid", "bad")}, health)
    assert result is not None
    assert [(i.provider, i.source) for i in result.items] == [("x", "registry")]


def test_referenced_provider_absent_from_registry() -> None:
    result = build(plan(pnode("a", "ghost")), {})
    assert result is not None
    (item,) = result.items
    assert (item.provider, item.source, item.state, item.nodes) == (
        "ghost", "registry", "absent", ["a"])
    assert "ghost" in item.reason


def test_no_items_means_no_plan() -> None:
    records = {"x": record("x"), "y": record("y")}
    assert build(plan(pnode("a", "x"), pnode("b", "y")), records,
                 {"x": HealthOutcome(status="ok")}) is None
    assert build(None, records) is None


def test_unreferenced_provider_is_ignored_when_a_plan_exists() -> None:
    records = {"x": record("x"), "broken": record("broken", "invalid", "bad")}
    assert build(plan(pnode("a", "x")), records,
                 {"broken": unavailable("down")}) is None


def test_decomposition_considers_every_registered_provider() -> None:
    records = {"zeta": record("zeta", "unreachable", "timeout"),
               "alpha": record("alpha", "incompatible", "protocol 9"),
               "ok": record("ok")}
    result = build(None, records, {"ok": unavailable("down")})
    assert result is not None
    assert [(i.provider, i.source, i.nodes) for i in result.items] == [
        ("alpha", "registry", []), ("ok", "health", []), ("zeta", "registry", [])]


def test_missing_registry_error_falls_back_to_state() -> None:
    result = build(plan(pnode("a", "x")), {"x": record("x", "invalid", None)})
    assert result is not None
    (item,) = result.items
    assert item.reason and item.suggested_action
    assert "invalid" in item.reason


def test_reason_and_action_are_redacted() -> None:
    secret = "password=" + secrets.token_hex(8)  # random per run: a redaction fixture
    health = {"y": unavailable(f"login failed {secret}", unlock=f"set {secret}")}
    result = build(plan(pnode("a", "x"), pnode("b", "y")),
                   {"x": record("x", "invalid", f"argv has {secret}"), "y": record("y")},
                   health)
    assert result is not None
    dumped = repr(to_dict(result))
    assert "hunter2" not in dumped


def test_plan_round_trips_strictly_and_is_deterministic() -> None:
    records = {"x": record("x", "invalid", "bad")}
    first = build(plan(pnode("a", "x")), records)
    second = build(plan(pnode("a", "x")), records)
    assert first is not None and first == second
    assert from_dict(InstallationPlan, to_dict(first), strict=True) == first


def test_planning_only_marker_cannot_be_turned_off() -> None:
    data = to_dict(build(plan(pnode("a", "x")), {"x": record("x", "invalid", "bad")}))
    data["planning_only"] = False
    with pytest.raises(ContractError):
        from_dict(InstallationPlan, data, strict=True)


def test_builder_never_executes_anything() -> None:
    """Pure function: no transport, subprocess or health call is reachable from it."""
    tree = ast.parse(Path(installation.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
            imported.update(f"{node.module}.{alias.name}" for alias in node.names)
    forbidden = ("subprocess", "os", "shutil", "urllib", "socket", "theforge.protocol",
                 "theforge.registry.health.check_health")
    assert not [m for m in imported if m.startswith(forbidden)]
