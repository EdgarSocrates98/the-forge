"""Deterministic task decomposition (cross-forge-foundation 2.3; requirements 2.1-2.7, 6.1).

The decomposer only reads ``RoutingDecision.candidates`` produced by ``route()``: the proof
task becomes ``n1`` (Spark) -> ``n2`` (API) with the fixture manifests and, through the Wave B
adapters' describe in ``--replay`` (packaged snapshot), exactly ``pyspark.static-analysis`` ->
``api.analyze``. Ambiguity, ``no_route``, the one-provider profile, per-repository targets and
order independence (hypothesis) are covered with fixture or synthetic manifests.
"""

import json
import shutil
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from helpers import API_ENTRY, PROVIDERS, SPARK_ENTRY, make_workspace, write_file
from theforge.context.git import GitState
from theforge.context.scan import WorkspaceScan, scan_workspace
from theforge.contracts import TaskSpec, from_dict
from theforge.contracts.context import GitSummary
from theforge.contracts.manifest import ForgeManifest
from theforge.contracts.workspace import WorkspaceDescriptor
from theforge.meta import PRODUCER
from theforge.planning.decompose import (
    INTENT_ORDER_RULE,
    Decomposition,
    decompose,
    decomposed_plan,
    decomposition_dependencies,
)
from theforge.profiles import ContextProfile, profile_for
from theforge.registry import ProviderEntry, Registry, RegistryRecord
from theforge.routing import route
from theforge.workspace import describe_workspace

REPO = Path(__file__).parents[1]
CROSS = REPO / "tests" / "fixtures" / "workspaces" / "cross"
NATIVE = REPO / "tests" / "fixtures" / "native"
PROOF_TASK = "Projete um pipeline Spark que produza dados para uma API"
TS = "2026-01-01T00:00:00Z"
MAX = profile_for("max")
BALANCED = profile_for("balanced")
CATALOG_HINT = ("revalidate the Wave B capability catalog (adapter signals); never add a "
                "domain rule to the core")


def _no_git(_: Path) -> GitState:
    return GitState(summary=GitSummary(available=False), changed=frozenset(),
                    limitations=("git: not available",))


def _fixture_record(name: str, pid: str) -> RegistryRecord:
    data = json.loads((PROVIDERS / name).read_text(encoding="utf-8"))
    return RegistryRecord(entry=ProviderEntry(id=pid, argv=["x"], trust="local"),
                          state="ready", manifest=from_dict(ForgeManifest, data),
                          manifest_sha256="0" * 64, protocol="forge/v1")


FIXTURE_RECORDS = {
    SPARK_ENTRY["id"]: _fixture_record("fixture-spark.json", SPARK_ENTRY["id"]),
    API_ENTRY["id"]: _fixture_record("fixture-api.json", API_ENTRY["id"]),
}


def _synthetic(pid: str, *caps: dict[str, Any]) -> RegistryRecord:
    capabilities = [{
        "id": c["id"], "actions": c.get("actions", ["run"]),
        "default_action": c.get("actions", ["run"])[0], "state": c.get("state", "supported"),
        "operation_class": "read_only",
        "signals": {"keywords": c.get("keywords", []), "file_globs": c.get("globs", []),
                    "dependencies": c.get("deps", [])},
    } for c in caps]
    manifest = from_dict(ForgeManifest, {
        "schema": "theforge/ForgeManifest/v1", "id": pid, "version": "1",
        "protocols": ["forge/v1"], "ops": ["describe", "health", "execute"],
        "capabilities": capabilities})
    return RegistryRecord(entry=ProviderEntry(id=pid, argv=["x"], trust="local"),
                          state="ready", manifest=manifest, manifest_sha256="0" * 64,
                          protocol="forge/v1")


def _cross(tmp_path: Path, *, repos: bool = True) -> Path:
    """The proof workspace with fake repositories (no git needed: git is read as absent)."""
    root = tmp_path / "cross"
    shutil.copytree(CROSS, root)
    if repos:
        for name in ("data-pipeline", "orders-api"):
            (root / name / ".git").mkdir()
    return root


def _task(root: Path, intent: str = PROOF_TASK, **kw: Any) -> TaskSpec:
    return TaskSpec(producer=PRODUCER, created_at=TS, id="t-proof", intent=intent,
                    workspace_root=str(root), **kw)


def _run(root: Path, records: dict[str, RegistryRecord], intent: str = PROOF_TASK,
         profile: ContextProfile = MAX, **kw: Any,
         ) -> tuple[Decomposition, WorkspaceDescriptor, WorkspaceScan]:
    scan = scan_workspace(root, [])
    descriptor = describe_workspace(root, list(records.values()), scan, git_reader=_no_git)
    task = _task(root, intent, **kw)
    decision = route(task, list(records.values()), scan.files,
                     decomposition_dependencies(root, descriptor))
    return decompose(task, decision, records, descriptor, scan, profile), descriptor, scan


def _shape(decomposition: Decomposition) -> list[tuple[str, str, str, str]]:
    return [(n.id, n.provider, n.capability, n.action) for n in decomposition.nodes]


# --- proof task -------------------------------------------------------------------------


def test_proof_task_with_fixture_manifests(tmp_path: Path) -> None:
    root = _cross(tmp_path)
    result, _, _ = _run(root, FIXTURE_RECORDS)
    assert result.status == "planned", result.decision.reason
    assert result.pattern == "pipeline"
    assert _shape(result) == [("n1", "fixture-spark", "spark.performance", "diagnose"),
                              ("n2", "fixture-api", "api.contract", "review")]
    n1, n2 = result.nodes
    assert (n1.role, n2.role) == ("producer", "consumer")
    assert n1.depends_on == [] and n1.inputs == []
    assert n2.inputs == ["n1"]
    [dependency] = n2.depends_on
    assert (dependency.node, dependency.epistemic, dependency.rule) == (
        "n1", "inferred", INTENT_ORDER_RULE)
    assert dependency.evidence == "keyword 'spark'@3 < keyword 'api'@9"
    assert (n1.targets, n2.targets) == (["data-pipeline"], ["orders-api"])
    decision = result.decision
    assert decision.status == "routed" and decision.pattern == "pipeline"
    assert [(s.provider, s.capability, s.action, s.role) for s in decision.selected] == [
        ("fixture-spark", "spark.performance", "diagnose", "primary"),
        ("fixture-api", "api.contract", "review", "specialist")]
    assert decision.candidates  # preserved from route()
    plan = decomposed_plan(result, _task(root), FIXTURE_RECORDS, MAX, plan_run="p-1",
                           created_at=TS)
    assert plan.status == "validated", plan.violations
    assert (plan.source, plan.profile, plan.pattern, plan.task_id) == (
        "decomposed", "max", "pipeline", "t-proof")
    assert plan.nodes == list(result.nodes)


def test_decomposition_dependencies_union_root_and_repositories(tmp_path: Path) -> None:
    root = _cross(tmp_path)
    write_file(root, "requirements.txt", "rootdep==1\n")
    scan = scan_workspace(root, [])
    descriptor = describe_workspace(root, list(FIXTURE_RECORDS.values()), scan,
                                    git_reader=_no_git)
    assert decomposition_dependencies(root, descriptor) == {"rootdep", "pyspark", "fastapi"}


def test_decomposed_plan_refuses_unplanned_decomposition(tmp_path: Path) -> None:
    result, _, _ = _run(tmp_path, FIXTURE_RECORDS, intent="nothing relevant here")
    with pytest.raises(ValueError, match="no_route"):
        decomposed_plan(result, _task(tmp_path), FIXTURE_RECORDS, MAX, plan_run="p-1")


# --- proof task with the Wave B adapters' packaged manifests ----------------------------

WAVE_B = (("spark-forge", "theforge_sparkforge", NATIVE / "sparkforge" / "default",
           "pyspark.static-analysis"),
          ("api-forge", "theforge_apiforge", NATIVE / "apiforge" / "default", "api.analyze"))


@pytest.mark.integration
def test_proof_task_with_wave_b_adapter_manifests(tmp_path: Path) -> None:
    """Describe in ``--replay`` (``default`` scenario) uses the packaged manifest snapshot."""
    root = _cross(tmp_path)
    make_workspace(root, [{"id": pid, "argv": [sys.executable, "-m", module, "--replay",
                                                str(replay)], "trust": "local"}
                          for pid, module, replay, _ in WAVE_B])
    records = {r.entry.id: r for r in Registry(root / ".forge").records()}
    for pid, _, _, _ in WAVE_B:
        assert records[pid].state == "ready", (pid, records[pid].error)
    result, _, _ = _run(root, records)
    expected = [(pid, capability) for pid, _, _, capability in WAVE_B]
    got = [(n.provider, n.capability) for n in result.nodes]
    assert result.status == "planned" and got == expected, (
        f"proof task decomposed to {result.status} {got} ({result.decision.reason}); "
        f"expected {expected}: {CATALOG_HINT}")
    assert result.nodes[1].depends_on[0].rule == INTENT_ORDER_RULE
    plan = decomposed_plan(result, _task(root), records, MAX, plan_run="p-1", created_at=TS)
    assert plan.status == "validated", plan.violations


# --- one-provider profile ---------------------------------------------------------------


def test_balanced_routes_one_node_with_profile_limitation(tmp_path: Path) -> None:
    root = _cross(tmp_path)
    # No API keyword: Spark matches 3 signal types, the API 2 (both qualify); route() picks
    # Spark, and the one-provider profile turns that decision into a single ``route`` node.
    result, _, _ = _run(root, FIXTURE_RECORDS, intent="Projete um pipeline Spark",
                        profile=BALANCED)
    assert result.status == "planned" and result.pattern == "route"
    assert _shape(result) == [("n1", "fixture-spark", "spark.performance", "diagnose")]
    assert result.nodes[0].role == "standalone" and result.nodes[0].depends_on == []
    assert result.nodes[0].targets == ["data-pipeline"]
    assert result.limitations == (
        "multi-provider decomposition not allowed by profile 'balanced'",)
    assert result.decision.pattern == "route" and len(result.decision.selected) == 1
    plan = decomposed_plan(result, _task(root), FIXTURE_RECORDS, BALANCED, plan_run="p-1")
    assert plan.status == "validated", plan.violations


def test_balanced_keeps_the_ambiguous_decision(tmp_path: Path) -> None:
    root = _cross(tmp_path)
    result, _, _ = _run(root, FIXTURE_RECORDS, profile=BALANCED)
    assert result.status == "ambiguous" and result.nodes == ()
    assert result.decision.status == "ambiguous"
    assert "multi-provider decomposition not allowed by profile 'balanced'" in (
        result.limitations)


def test_single_qualified_provider_gives_a_route_node_without_limitation(
        tmp_path: Path) -> None:
    root = _cross(tmp_path)
    shutil.rmtree(root / "orders-api")
    result, _, _ = _run(root, FIXTURE_RECORDS, intent="Projete um pipeline Spark")
    assert result.status == "planned" and result.pattern == "route"
    assert _shape(result) == [("n1", "fixture-spark", "spark.performance", "diagnose")]
    assert result.limitations == ()


def test_requested_capability_gives_one_route_node_even_under_max(tmp_path: Path) -> None:
    root = _cross(tmp_path)
    result, _, _ = _run(root, FIXTURE_RECORDS, requested_capability="api.contract")
    assert result.status == "planned" and result.pattern == "route"
    assert [(n.provider, n.capability, n.role) for n in result.nodes] == [
        ("fixture-api", "api.contract", "standalone")]
    assert result.limitations == ()


# --- ambiguity and no_route --------------------------------------------------------------


def test_missing_keyword_is_ambiguous(tmp_path: Path) -> None:
    root = _cross(tmp_path)
    result, _, _ = _run(root, FIXTURE_RECORDS, intent="Projete um pipeline Spark")
    assert result.status == "ambiguous" and result.nodes == ()
    assert result.decision.status == "ambiguous" and result.decision.selected == []
    assert "cannot order fixture-api" in result.decision.reason


def test_equal_positions_are_ambiguous(tmp_path: Path) -> None:
    records = {
        "alpha": _synthetic("alpha", {"id": "alpha.run", "keywords": ["data"],
                                      "globs": ["*.alpha"]}),
        "beta": _synthetic("beta", {"id": "beta.run", "keywords": ["data lake"],
                                    "globs": ["*.beta"]}),
    }
    write_file(tmp_path, "x.alpha")
    write_file(tmp_path, "y.beta")
    result, _, _ = _run(tmp_path, records, intent="analyze the data lake")
    assert result.status == "ambiguous"
    assert "same position" in result.decision.reason
    assert "alpha" in result.decision.reason and "beta" in result.decision.reason


def test_tied_best_capabilities_of_one_provider_are_ambiguous(tmp_path: Path) -> None:
    records = {
        "alpha": _synthetic("alpha", {"id": "alpha.one", "keywords": ["alpha"],
                                      "globs": ["*.alpha"]},
                            {"id": "alpha.two", "keywords": ["alpha"], "globs": ["*.alpha"]}),
        "beta": _synthetic("beta", {"id": "beta.run", "keywords": ["beta"],
                                    "globs": ["*.beta"]}),
    }
    write_file(tmp_path, "x.alpha")
    write_file(tmp_path, "y.beta")
    result, _, _ = _run(tmp_path, records, intent="alpha then beta")
    assert result.status == "ambiguous"
    assert "alpha.one" in result.decision.reason and "alpha.two" in result.decision.reason


def test_more_qualified_providers_than_the_profile_allows_is_ambiguous(
        tmp_path: Path) -> None:
    names = ("alpha", "beta", "gamma")
    records = {n: _synthetic(n, {"id": f"{n}.run", "keywords": [n], "globs": [f"*.{n}"]})
               for n in names}
    for n in names:
        write_file(tmp_path, f"x.{n}")
    two = replace(MAX, max_providers=2)
    result, _, _ = _run(tmp_path, records, intent="alpha beta gamma", profile=two)
    assert result.status == "ambiguous"
    assert "3 qualified providers" in result.decision.reason
    ordered, _, _ = _run(tmp_path, records, intent="gamma alpha beta")
    assert [n.provider for n in ordered.nodes] == ["gamma", "alpha", "beta"]
    assert [n.role for n in ordered.nodes] == ["producer", "consumer", "consumer"]
    assert ordered.nodes[2].depends_on[0].node == "n2" and ordered.nodes[2].inputs == ["n2"]


def test_nothing_qualifies_is_no_route(tmp_path: Path) -> None:
    result, _, _ = _run(tmp_path, FIXTURE_RECORDS, intent="write a poem")
    assert result.status == "no_route" and result.nodes == ()
    assert result.decision.status == "no_route"


def test_below_minimum_signal_types_does_not_qualify(tmp_path: Path) -> None:
    # Keywords only (no files, no dependencies): one signal type per provider.
    result, _, _ = _run(tmp_path, FIXTURE_RECORDS)
    assert result.status == "ambiguous" and result.nodes == ()


# --- targets -------------------------------------------------------------------------------


def test_targets_fall_back_to_task_targets_without_repositories(tmp_path: Path) -> None:
    root = _cross(tmp_path, repos=False)
    write_file(root, "requirements.txt", "pyspark\nfastapi\n")
    scan = scan_workspace(root, [])
    descriptor = describe_workspace(root, list(FIXTURE_RECORDS.values()), scan,
                                    git_reader=_no_git)
    task = _task(root, targets=["data-pipeline", "orders-api"])
    decision = route(task, list(FIXTURE_RECORDS.values()), scan.files,
                     decomposition_dependencies(root, descriptor))
    result = decompose(task, decision, FIXTURE_RECORDS, descriptor, scan, MAX)
    assert result.status == "planned"
    assert [n.targets for n in result.nodes] == [["data-pipeline", "orders-api"]] * 2


def test_targets_include_repositories_matched_by_dependencies(tmp_path: Path) -> None:
    root = _cross(tmp_path)
    (root / "shared" / ".git").mkdir(parents=True)
    write_file(root, "shared/requirements.txt", "pyspark\n")
    result, _, _ = _run(root, FIXTURE_RECORDS)
    assert result.nodes[0].targets == ["data-pipeline", "shared"]
    assert result.nodes[1].targets == ["orders-api"]


def test_requested_action_applies_only_where_offered(tmp_path: Path) -> None:
    records = {
        "alpha": _synthetic("alpha", {"id": "alpha.run", "keywords": ["alpha"],
                                      "globs": ["*.alpha"], "actions": ["run", "lint"]}),
        "beta": _synthetic("beta", {"id": "beta.run", "keywords": ["beta"],
                                    "globs": ["*.beta"]}),
    }
    write_file(tmp_path, "x.alpha")
    write_file(tmp_path, "y.beta")
    scan = scan_workspace(tmp_path, [])
    descriptor = describe_workspace(tmp_path, list(records.values()), scan, git_reader=_no_git)
    task = _task(tmp_path, "alpha then beta", requested_action="lint")
    decision = route(task, list(records.values()), scan.files, set())
    result = decompose(task, decision, records, descriptor, scan, MAX)
    assert [n.action for n in result.nodes] == ["lint", "run"]


# --- determinism ---------------------------------------------------------------------------


def _comparable(decomposition: Decomposition) -> Any:
    return (decomposition.status, decomposition.pattern, decomposition.nodes,
            decomposition.limitations, replace(decomposition.decision, created_at=TS))


@pytest.fixture(scope="module")
def proof_inputs(tmp_path_factory: pytest.TempPathFactory) -> Any:
    root = _cross(tmp_path_factory.mktemp("perm"))
    scan = scan_workspace(root, [])
    descriptor = describe_workspace(root, list(FIXTURE_RECORDS.values()), scan,
                                    git_reader=_no_git)
    task = _task(root)
    decision = route(task, list(FIXTURE_RECORDS.values()), scan.files,
                     decomposition_dependencies(root, descriptor))
    baseline = decompose(task, decision, FIXTURE_RECORDS, descriptor, scan, MAX)
    return task, decision, descriptor, scan, baseline


@settings(max_examples=30, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(data=st.data())
def test_same_plan_for_any_permutation(proof_inputs: Any, data: st.DataObject) -> None:
    task, decision, descriptor, scan, baseline = proof_inputs
    assert baseline.status == "planned"
    keys = data.draw(st.permutations(sorted(FIXTURE_RECORDS)))
    records = {k: FIXTURE_RECORDS[k] for k in keys}
    candidates = data.draw(st.permutations(decision.candidates))
    files = data.draw(st.permutations(scan.files))
    permuted = decompose(task, replace(decision, candidates=list(candidates)), records,
                         descriptor, replace(scan, files=list(files)), MAX)
    assert _comparable(permuted) == _comparable(baseline)
