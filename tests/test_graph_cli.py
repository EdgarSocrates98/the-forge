"""``theforge graph`` (cycle-3 wave Q): the declared+observed capability graph over
the registry cache — read-only, no provider process starts. ``--ref`` restricts
the view to the edges touching a capability; JSON and text agree on the same
filtered subgraph. The explain additions of the same wave (``Complexity:``,
``Resolved:``, verifier identity, ``Graph:``/``Planner:`` in plan runs) are
covered here end to end.
"""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from cross_workspace import CrossWorkspace, mounted_cross_workspace
from helpers import (
    API_PLAN_ENTRY,
    RESOLVER_ENTRY,
    SPARK_B_ENTRY,
    SPARK_ENTRY,
    SPARK_PLAN_ENTRY,
    VERIFIER_ENTRY,
    case_a,
    make_workspace,
    write_file,
)
from theforge.cli.main import main

PROOF_TASK = "Projete um pipeline Spark que produza dados para uma API"


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    code = main(list(argv))
    out, err = capsys.readouterr()
    return code, out, err


@pytest.fixture
def cross() -> Iterator[CrossWorkspace]:
    with mounted_cross_workspace(git=True) as workspace:
        yield workspace


def _edge_kinds(data: dict) -> dict[str, list[tuple[str, str]]]:
    return {
        kind: sorted((e["source"], e["target"]) for e in data["edges"] if e["kind"] == kind)
        for kind in {e["kind"] for e in data["edges"]}
    }


def test_graph_lists_declared_and_observed_relations(
    cross: CrossWorkspace, capsys: pytest.CaptureFixture[str]
) -> None:
    make_workspace(cross.root, [SPARK_PLAN_ENTRY, API_PLAN_ENTRY])
    # An observed dependency inside a git repository: the pyspark technology
    # exists and fixture-spark's signals match it.
    write_file(cross.root, "data-pipeline/requirements.txt", "pyspark==3.5.1\n")
    root = str(cross.root)
    code, _, err = run(capsys, "registry", "refresh", "--root", root)
    assert code == 0, err
    code, out, err = run(capsys, "graph", "--root", root, "--json")
    assert code == 0, err
    data = json.loads(out)
    kinds = _edge_kinds(data)
    # Declared: manifests name domains, capabilities, actions and relations.
    assert ("provider:fixture-spark", "domain:data-engineering") in kinds["in_domain"]
    assert kinds["has_capability"] and kinds["has_action"]
    assert any(
        source == "capability:fixture-spark/spark.performance"
        for source, _ in kinds.get("produces", [])
    )
    # Observed: the dependency file names a technology the graph links back to
    # the capability whose signals matched it.
    uses = kinds.get("uses_technology", [])
    assert any(target == "technology:data-pipeline:pyspark" for _, target in uses), uses
    assert (
        "capability:fixture-spark/spark.performance",
        "technology:data-pipeline:pyspark",
    ) in kinds.get("relevant_to", [])
    # Every edge names its evidence and epistemic status.
    assert all(e["epistemic"] and e["evidence"] for e in data["edges"])
    code, out, _ = run(capsys, "graph", "--root", root)
    assert code == 0 and "Capability graph:" in out
    assert "produces:" in out and "(explicit:" in out and "(observed:" in out
    assert "Limitations:" in out


def test_graph_ref_filters_both_representations(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    make_workspace(tmp_path, [SPARK_ENTRY, SPARK_B_ENTRY])
    case_a(tmp_path)
    root = str(tmp_path)
    run(capsys, "registry", "refresh", "--root", root)
    code, out, _ = run(capsys, "graph", "--root", root, "--json")
    full = json.loads(out)
    # Bare capability ref: the subgraph of both providers' spark.performance.
    code, out, _ = run(capsys, "graph", "--root", root, "--ref", "spark.performance", "--json")
    assert code == 0
    narrowed = json.loads(out)
    assert narrowed["ref"] == "spark.performance"
    assert 0 < len(narrowed["edges"]) < len(full["edges"])
    assert {e["source"] for e in narrowed["edges"]} | {e["target"] for e in narrowed["edges"]} == {
        n["id"] for n in narrowed["nodes"]
    }
    caps = {n["id"] for n in narrowed["nodes"] if n["kind"] == "capability"}
    assert caps == {
        "capability:fixture-spark/spark.performance",
        "capability:fixture-spark-b/spark.performance",
    }
    # Qualified ref: one provider only.
    code, out, _ = run(
        capsys, "graph", "--root", root, "--ref", "fixture-spark/spark.performance", "--json"
    )
    assert {n["id"] for n in json.loads(out)["nodes"] if n["kind"] == "capability"} == {
        "capability:fixture-spark/spark.performance"
    }
    code, out, _ = run(capsys, "graph", "--root", root, "--ref", "spark.performance")
    assert code == 0 and "ref spark.performance" in out
    assert "fixture-api" not in out


def test_graph_never_starts_a_provider_process(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Configured but uncached providers surface as limitations, not nodes: if the
    command described them, the manifests would be in the graph instead."""
    make_workspace(tmp_path, [SPARK_ENTRY])
    root = str(tmp_path)
    code, out, err = run(capsys, "graph", "--root", root, "--json")
    assert code == 0, err
    data = json.loads(out)
    assert not any(n["kind"] == "provider" and "fixture-spark" in n["id"] for n in data["nodes"])
    assert any(
        "fixture-spark" in line and "no cached manifest" in line for line in data["limitations"]
    )


def test_graph_without_providers_is_empty_not_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A workspace without ``.forge`` (or without any registry entry) has no
    capability graph — an empty read-only view, like ``workspace show``."""
    code, out, err = run(capsys, "graph", "--root", str(tmp_path))
    assert code == 0, err
    assert "Capability graph:" in out


# --- explain additions (same wave) -----------------------------------------------------------


def test_explain_plan_run_shows_complexity_and_graph_summary(
    cross: CrossWorkspace, capsys: pytest.CaptureFixture[str]
) -> None:
    make_workspace(cross.root, [SPARK_PLAN_ENTRY, API_PLAN_ENTRY])
    root = str(cross.root)
    code, out, err = run(capsys, "plan", PROOF_TASK, "--execute", "--root", root, "--json")
    assert code == 0, err
    data = json.loads(out)
    # cmd_plan payload: the persisted artifacts ride along for tooling.
    assert data["complexity"]["schema"].endswith("/v1")
    assert data["budget"]["profile"] == data["complexity"]["selected_profile"]
    assert data["capability_graph"]["nodes"] and data["capability_graph"]["edges"]
    code, out, _ = run(capsys, "explain", data["run_id"], "--root", root)
    assert code == 0
    complexity = data["complexity"]
    expected = (
        f"Complexity:  {complexity['level']} score={complexity['score']:.2f} "
        f"confidence={complexity['confidence']:.2f}"
    )
    assert expected in out and complexity["profile_reason"] in out
    assert "Graph:       " in out and "the declared+observed relations" in out


def test_explain_shows_the_semantic_resolution_and_verifier_identity(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    make_workspace(tmp_path, [SPARK_ENTRY, SPARK_B_ENTRY, RESOLVER_ENTRY, VERIFIER_ENTRY])
    case_a(tmp_path)
    root = str(tmp_path)
    code, out, err = run(
        capsys,
        "ask",
        "diagnose the slow spark glue job",
        "--profile",
        "balanced",
        "--root",
        root,
        "--json",
    )
    assert code == 0, err
    run_id = json.loads(out)["run_id"]
    code, out, _ = run(capsys, "explain", run_id, "--root", root)
    assert code == 0
    assert "Resolved:    semantically -> fixture-spark/spark.performance:" in out
    assert "rationale:" in out and "alternatives: fixture-spark-b" in out
    assert "independent=passed (fixture-verifier)" in out


def test_graph_mesh_view_lists_domain_roles(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Cycle 3.1 Phase 83: ``--mesh`` projects the graph into DOMAIN →
    observe/engineer/verify, derived only from declared relations."""
    from helpers import API_DOMAIN_ENTRY, SPARK_DOMAIN_ENTRY, VERIFIER_ENTRY

    make_workspace(tmp_path, [SPARK_ENTRY, SPARK_DOMAIN_ENTRY, API_DOMAIN_ENTRY, VERIFIER_ENTRY])
    case_a(tmp_path)
    root = str(tmp_path)
    code, _, err = run(capsys, "registry", "refresh", "--root", root)
    assert code == 0, err
    code, out, err = run(capsys, "graph", "--mesh", "--root", root, "--json")
    assert code == 0, err
    mesh = json.loads(out)["mesh"]
    assert mesh["domains"] == [
        {
            "domain": "spark",
            "observe": ["fixture-spark-domain/spark.performance"],
            "engineer": ["fixture-api-domain/api.contract"],
            "verify": [],
        }
    ]
    # The verifier's edge targets a provider outside the mesh — named, never
    # dropped silently.
    assert mesh["unplaced_verify"] == [
        "fixture-verifier/audit.verify -> fixture-spark/spark.performance"
    ]

    code, out, _ = run(capsys, "graph", "--mesh", "--root", root)
    assert code == 0
    assert "DOMAIN: spark" in out and "observe:" in out
    assert "fixture-spark-domain/spark.performance" in out
    assert "Unplaced verify:" in out
