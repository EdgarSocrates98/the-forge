"""Workspace, graph, verification, installation, explain and diagnostic contracts (task 1.3)."""

from typing import Any

import pytest

from theforge.contracts import ContractError, GitSummary, Producer, from_dict, to_dict
from theforge.contracts.diagnostic import DIAGNOSTIC_SCHEMA, Diagnostic, DiagnosticFrame
from theforge.contracts.explain import EXPLAIN_SCHEMA, ExplainReport
from theforge.contracts.graph import GRAPH_SCHEMA, GraphEdge, WorkspaceGraph
from theforge.contracts.installation import INSTALLATION_SCHEMA, InstallationPlan
from theforge.contracts.verification import (
    VERIFICATION_SCHEMA,
    VerificationCheck,
    VerificationResult,
)
from theforge.contracts.workspace import (
    WORKSPACE_GIT_BUDGET_S,
    WORKSPACE_SCHEMA,
    Technology,
    WorkspaceDescriptor,
)

P = {"id": "theforge", "version": "1"}
TS = "2026-01-01T00:00:00Z"
SHA = "b" * 64


def roundtrip(cls: type[Any], data: dict[str, Any]) -> Any:
    obj = from_dict(cls, data, strict=True)
    assert from_dict(cls, to_dict(obj), strict=True) == obj
    return obj


# --- workspace descriptor ---------------------------------------------------------------


def descriptor_dict(**overrides: Any) -> dict[str, Any]:
    git = {
        "available": True,
        "branch": None,
        "head": "c" * 40,
        "detached": True,
        "dirty": True,
        "changed_files": 3,
        "state": ["rebase"],
    }
    data: dict[str, Any] = {
        "producer": P,
        "created_at": TS,
        "root": "/ws",
        "repositories": [
            {"path": ".", "dependency_files": [], "limitations": ["not a git repository"]},
            {
                "path": "data-pipeline",
                "git": git,
                "dependency_files": ["data-pipeline/requirements.txt"],
            },
            {"path": "orders-api", "limitations": ["git-budget-exhausted"]},
        ],
        "paths": ["data-pipeline", "data-pipeline/requirements.txt", "orders-api"],
        "technologies": [
            {
                "name": "pyspark",
                "repository": "data-pipeline",
                "source": "dependency_manifest",
                "evidence": "data-pipeline/requirements.txt",
                "matched_by": ["spark/pyspark.x"],
            },
            {
                "name": "api",
                "repository": "orders-api",
                "source": "provider_signal",
                "evidence": "orders-api/openapi.yaml",
            },
        ],
        "relations": [
            {
                "source": ".",
                "target": "data-pipeline",
                "kind": "contains",
                "epistemic": "observed",
                "evidence": "data-pipeline/.git",
            },
            {
                "source": "orders-api",
                "target": "data-pipeline",
                "kind": "depends_on",
                "epistemic": "explicit",
                "evidence": ".forge/config/workspace.toml",
            },
        ],
    }
    data.update(overrides)
    return data


def test_workspace_descriptor_rereads_strictly_with_wave_c_git_summary() -> None:
    descriptor = roundtrip(WorkspaceDescriptor, descriptor_dict())
    assert descriptor.schema == WORKSPACE_SCHEMA
    git = descriptor.repositories[1].git
    assert isinstance(git, GitSummary)  # embedded Wave C type, fields not redeclared
    assert git.detached is True and git.changed_files == 3
    assert descriptor.repositories[2].git is None
    assert WORKSPACE_GIT_BUDGET_S == 20.0


def test_workspace_descriptor_rejects_unknown_fields_and_schema() -> None:
    with pytest.raises(ContractError, match="schema"):
        from_dict(WorkspaceDescriptor, descriptor_dict(schema="x"), strict=True)
    bad = descriptor_dict()
    bad["repositories"][1]["git"]["remote"] = "x"
    with pytest.raises(ContractError, match="unknown field"):
        from_dict(WorkspaceDescriptor, bad, strict=True)


def test_technology_and_relation_require_evidence() -> None:
    with pytest.raises(ContractError, match="evidence"):
        Technology(name="x", repository=".", source="provider_signal", evidence="")
    bad = descriptor_dict()
    bad["relations"][0]["evidence"] = " "
    with pytest.raises(ContractError, match="evidence"):
        from_dict(WorkspaceDescriptor, bad, strict=True)
    bad = descriptor_dict()
    bad["relations"][1]["epistemic"] = "inferred"
    with pytest.raises(ContractError, match="epistemic"):
        from_dict(WorkspaceDescriptor, bad, strict=True)


# --- graph ------------------------------------------------------------------------------


def graph_dict(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "producer": P,
        "created_at": TS,
        "plan_run": "p1",
        "nodes": [
            {"id": "workspace:.", "kind": "workspace"},
            {"id": "plan_node:spark", "kind": "plan_node", "label": "spark"},
            {"id": "plan_node:api", "kind": "plan_node"},
        ],
        "edges": [
            {
                "source": "plan_node:spark",
                "target": "plan_node:api",
                "kind": "depends_on",
                "epistemic": "inferred",
                "rule": "intent-order",
                "evidence": "keyword order",
            },
            {
                "source": "workspace:.",
                "target": "plan_node:spark",
                "kind": "contains",
                "epistemic": "explicit",
                "evidence": "plan file",
            },
        ],
    }
    data.update(overrides)
    return data


def test_graph_rereads_strictly() -> None:
    graph = roundtrip(WorkspaceGraph, graph_dict())
    assert graph.schema == GRAPH_SCHEMA and graph.truncated is False
    assert graph.edges[0].rule == "intent-order"


def test_graph_edge_without_evidence_is_rejected() -> None:
    with pytest.raises(ContractError, match="evidence"):
        GraphEdge(source="a", target="b", kind="uses", epistemic="observed", evidence="")
    data = graph_dict()
    data["edges"][1]["evidence"] = ""
    with pytest.raises(ContractError, match="evidence"):
        from_dict(WorkspaceGraph, data, strict=True)


def test_inferred_graph_edge_without_rule_is_rejected() -> None:
    with pytest.raises(ContractError, match="rule"):
        GraphEdge(source="a", target="b", kind="depends_on", epistemic="inferred", evidence="e")
    data = graph_dict()
    del data["edges"][0]["rule"]
    with pytest.raises(ContractError, match="rule"):
        from_dict(WorkspaceGraph, data, strict=True)


def test_non_inferred_graph_edge_must_not_carry_a_rule() -> None:
    with pytest.raises(ContractError, match="rule"):
        GraphEdge(source="a", target="b", kind="uses", epistemic="explicit", evidence="e", rule="r")


# --- verification -----------------------------------------------------------------------


def verification_dict(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "producer": P,
        "created_at": TS,
        "run_id": "r1",
        "self_report": {"status": "reported", "details": ["status=ok"]},
        "provider_evidence": {"status": "reported", "basis": ["3 evidence items"]},
        "forge": {
            "status": "passed",
            "basis": ["result-integrity", "context-reverification:conditional"],
        },
        "independent": {"status": "not_performed"},
    }
    data.update(overrides)
    return data


def test_verification_rereads_strictly() -> None:
    result = roundtrip(VerificationResult, verification_dict(limitations=["l"]))
    assert result.schema == VERIFICATION_SCHEMA
    assert result.independent == VerificationCheck(status="not_performed")


@pytest.mark.parametrize("level", ["self_report", "provider_evidence"])
@pytest.mark.parametrize("status", ["passed", "failed"])
def test_provider_levels_can_never_be_verification(level: str, status: str) -> None:
    with pytest.raises(ContractError, match=level):
        from_dict(VerificationResult, verification_dict(**{level: {"status": status}}), strict=True)


@pytest.mark.parametrize("level", ["forge", "independent"])
def test_forge_levels_are_never_self_reported(level: str) -> None:
    with pytest.raises(ContractError, match=level):
        from_dict(
            VerificationResult, verification_dict(**{level: {"status": "reported"}}), strict=True
        )


def test_verification_rejects_wrong_schema() -> None:
    with pytest.raises(ContractError, match="schema"):
        from_dict(VerificationResult, verification_dict(schema="x"), strict=True)


# --- installation -----------------------------------------------------------------------


def installation_dict(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "producer": P,
        "created_at": TS,
        "run_id": "p1",
        "items": [
            {
                "provider": "spark",
                "state": "unavailable",
                "reason": "jvm missing",
                "suggested_action": "install java",
                "source": "health",
                "nodes": ["spark"],
            }
        ],
    }
    data.update(overrides)
    return data


def test_installation_plan_is_planning_only_and_rereads_strictly() -> None:
    plan = roundtrip(InstallationPlan, installation_dict())
    assert plan.schema == INSTALLATION_SCHEMA and plan.planning_only is True
    with pytest.raises(ContractError, match="planning_only"):
        from_dict(InstallationPlan, installation_dict(planning_only=False), strict=True)


def test_installation_plan_without_items_is_rejected() -> None:
    with pytest.raises(ContractError, match="items"):
        from_dict(InstallationPlan, installation_dict(items=[]), strict=True)
    with pytest.raises(ContractError, match="items"):
        InstallationPlan(producer=Producer(id="theforge", version="1"), created_at=TS, run_id="p1")


# --- explain ----------------------------------------------------------------------------


PLAN = {
    "producer": P,
    "created_at": TS,
    "status": "validated",
    "plan_run": "p1",
    "task_id": "t1",
    "pattern": "route",
    "source": "file",
    "profile": "economy",
    "nodes": [
        {
            "id": "a",
            "role": "standalone",
            "provider": "demo",
            "capability": "demo.echo",
            "action": "echo",
        }
    ],
}


def explain_dict(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "producer": P,
        "created_at": TS,
        "run_id": "r1",
        "kind": "run",
        "status": "ok",
        "intent": "x",
        "targets": ["."],
        "profile": "balanced",
        "routing": {
            "status": "routed",
            "pattern": "route",
            "reason": "r",
            "confidence": "high",
            "signals": ["keyword:x"],
            "candidates": [{"provider": "demo", "capability": "demo.echo"}],
            "selected": [{"provider": "demo", "capability": "demo.echo", "action": "echo"}],
            "fallbacks": [],
            "notes": ["capability-alias: a -> demo.echo"],
        },
        "context": {
            "budget_bytes": 10,
            "used_bytes": 5,
            "files": 1,
            "excluded": 0,
            "truncated": False,
            "tier_bytes": {"reference": 5},
            "rounds": 0,
            "unmatched": 2,
            "git": {"available": False},
            "drift": ["a.py"],
        },
        "provider": {"id": "demo", "version": "1", "trust": "builtin"},
        "result": {
            "status": "ok",
            "findings": [{"id": "f1", "title": "t"}],
            "evidence_by_epistemic": {"observed": 1},
            "artifacts": 0,
            "duration_ms": {"value": 3.0, "kind": "measured"},
        },
        "risk": {"anything": 1},
        "telemetry": {"phases": {}},
        "verification": verification_dict(),
        "reproducibility": {"level": "unknown", "reasons": ["recorded before Wave D"]},
        "integrity": {
            "checked": ["task", "result"],
            "divergences": [
                {
                    "artifact": "work/out.json",
                    "kind": "modified",
                    "expected": SHA,
                    "actual": "c" * 64,
                }
            ],
            "unrecorded": ["telemetry"],
        },
        "not_recorded": ["verification"],
        "artifacts": {"task": {"id": "t1"}, "context-r1": {"round": 1}},
    }
    data.update(overrides)
    return data


def test_explain_report_rereads_strictly() -> None:
    report = roundtrip(ExplainReport, explain_dict())
    assert report.schema == EXPLAIN_SCHEMA
    assert report.integrity.divergences[0].kind == "modified"
    assert report.routing is not None and report.routing.notes == [
        "capability-alias: a -> demo.echo"
    ]
    assert report.artifacts["context-r1"] == {"round": 1}


def test_minimal_plan_explain_report_rereads_strictly() -> None:
    report = roundtrip(
        ExplainReport,
        {
            "producer": P,
            "created_at": TS,
            "run_id": "p1",
            "kind": "plan",
            "status": None,
            "reproducibility": {"level": "unknown"},
            "integrity": {},
            "plan": {
                "plan": PLAN,
                "installation": installation_dict(),
                "workspace_descriptor": descriptor_dict(),
            },
        },
    )
    assert report.plan is not None and report.plan.result is None
    assert report.routing is None and report.integrity.checked == []


def test_explain_report_rejects_wrong_schema_and_unknown_kind() -> None:
    with pytest.raises(ContractError, match="schema"):
        from_dict(ExplainReport, explain_dict(schema="theforge/ExplainReport/v2"), strict=True)
    with pytest.raises(ContractError, match="kind"):
        from_dict(ExplainReport, explain_dict(kind="node"), strict=True)
    bad = explain_dict()
    bad["integrity"]["divergences"][0]["kind"] = "tampered"
    with pytest.raises(ContractError, match="kind"):
        from_dict(ExplainReport, bad, strict=True)


# --- diagnostic -------------------------------------------------------------------------


def diagnostic_dict(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "producer": P,
        "created_at": TS,
        "stage": "cli:plan",
        "code": "FORGE-PLAN-FILE",
        "family": "plan",
        "error_type": "UsageError",
        "message": "plan file unreadable",
        "causes": [{"type": "OSError", "message": "no such file"}],
        "frames": [
            {"module": "theforge.cli.main", "function": "main", "line": 10},
            {"module": "theforge", "function": "<module>", "line": 1},
        ],
    }
    data.update(overrides)
    return data


def test_diagnostic_rereads_strictly() -> None:
    diagnostic = roundtrip(Diagnostic, diagnostic_dict())
    assert diagnostic.schema == DIAGNOSTIC_SCHEMA
    native = roundtrip(Diagnostic, diagnostic_dict(code="AF-PARSE", family=None))
    assert native.family is None


def test_diagnostic_family_must_match_the_code() -> None:
    with pytest.raises(ContractError, match="family"):
        from_dict(Diagnostic, diagnostic_dict(family="internal"), strict=True)
    with pytest.raises(ContractError, match="family"):
        from_dict(Diagnostic, diagnostic_dict(code="AF-PARSE", family="provider"), strict=True)


def test_diagnostic_frames_are_theforge_only_and_carry_no_locals() -> None:
    with pytest.raises(ContractError, match="module"):
        DiagnosticFrame(module="json.decoder", function="decode", line=1)
    with pytest.raises(ContractError, match="module"):
        DiagnosticFrame(module="theforgex.evil", function="f", line=1)
    bad = diagnostic_dict()
    bad["frames"][0]["locals"] = {"secret": "x"}
    with pytest.raises(ContractError, match="unknown field"):
        from_dict(Diagnostic, bad, strict=True)
