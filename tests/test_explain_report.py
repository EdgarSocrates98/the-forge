"""ExplainReport builder: every section of an ``ask`` run and of a plan run, sections not
recorded by older runs, raw artifacts for the Wave B/C text, and the published schema
(cross-forge-foundation 6.2)."""

import json
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from cross_workspace import CrossWorkspace, mounted_cross_workspace
from helpers import API_PLAN_ENTRY, SPARK_PLAN_ENTRY, bad_entry, make_workspace, write_file
from theforge.cli import render
from theforge.contracts import ExplainReport, to_dict
from theforge.contracts.explain import EXPLAIN_SCHEMA
from theforge.contracts.verification import ReproducibilityInfo
from theforge.explain import build_explain_report, verify_run_hashes
from theforge.forger import AskRequest, Forger, PlanCommand, PlanExecutor
from theforge.meta import PRODUCER
from theforge.registry import Registry
from theforge.runs import ARTIFACTS, RunStore

PROOF_TASK = "Projete um pipeline Spark que produza dados para uma API"
SCHEMA = json.loads((Path(__file__).resolve().parents[1] / "schemas"
                     / "ExplainReport.schema.json").read_text(encoding="utf-8"))


def _forger(root: Path, entries: list[dict[str, Any]]) -> tuple[Forger, RunStore]:
    forge = make_workspace(root, entries)
    store = RunStore(forge)
    return Forger(root, Registry(forge), store), store


def _echo_run(root: Path) -> tuple[RunStore, str]:
    forger, store = _forger(root, [])
    write_file(root, "notes.txt", "hello\n")
    out = forger.ask(AskRequest(intent="eco", capability="demo.echo"))
    assert out.status == "ok", out.error
    return store, out.run_id


def _rewrite(store: RunStore, run_id: str, name: str, change: Any) -> None:
    path = store.run_dir(run_id) / f"{name}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _snapshot(directory: Path) -> dict[str, tuple[bytes, int]]:
    return {str(p.relative_to(directory)): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in sorted(directory.rglob("*")) if p.is_file()}


def _valid(report: ExplainReport) -> dict[str, Any]:
    data = json.loads(json.dumps(to_dict(report)))
    errors = sorted(Draft202012Validator(SCHEMA).iter_errors(data), key=str)
    assert not errors, [e.message for e in errors]
    return data


@pytest.fixture
def cross() -> Iterator[CrossWorkspace]:
    with mounted_cross_workspace(git=True) as workspace:
        yield workspace


def test_ask_run_report_has_every_section(tmp_path: Path) -> None:
    store, run = _echo_run(tmp_path)
    report = build_explain_report(store, run)
    assert report.schema == EXPLAIN_SCHEMA and report.producer == PRODUCER
    assert (report.run_id, report.kind, report.status) == (run, "run", "ok")
    assert report.intent == "eco" and report.targets == ["."] and report.profile
    routing = report.routing
    assert routing is not None and routing.status == "routed"
    assert [(s.provider, s.capability) for s in routing.selected] == [
        ("echo-forge", "demo.echo")]
    assert routing.candidates and routing.reason and routing.confidence in ("high", "low")
    context = report.context
    assert context is not None and context.files >= 1 and context.budget_bytes > 0
    assert context.unmatched is not None and context.rounds == 0
    provider = report.provider
    assert provider is not None and provider.id == "echo-forge" and provider.version
    result = report.result
    assert result is not None and result.status == "ok"
    assert sum(result.evidence_by_epistemic.values()) >= 1
    assert result.duration_ms.kind in ("measured", "estimated", "unknown")
    assert report.risk is not None and report.risk["operation_class"]
    assert report.telemetry is not None and report.telemetry["run_id"] == run
    assert report.verification is not None
    assert report.reproducibility.level != "unknown" or report.reproducibility.reasons
    assert report.plan is None and report.error is None and report.error_family is None
    assert report.integrity == verify_run_hashes(store, run)
    assert report.integrity.divergences == []
    assert report.not_recorded == []
    for name in ("task", "routing", "context", "result", "risk", "telemetry",
                 "verification", "receipt"):
        assert report.artifacts[name] == store.read(run, name)
    _valid(report)


def test_routing_signals_come_from_the_selected_candidate(tmp_path: Path) -> None:
    store, run = _echo_run(tmp_path)

    def matched(data: dict[str, Any]) -> None:
        data["candidates"][0]["matched"] = {"keywords": ["eco"], "file_globs": ["*.txt"]}
        data["limitations"] = ["capability-alias: 'echo' resolved to 'demo.echo' (echo)",
                               "something else"]

    _rewrite(store, run, "routing", matched)
    routing = build_explain_report(store, run).routing
    assert routing is not None
    assert routing.signals == ["file_globs:*.txt", "keywords:eco"]
    assert routing.notes == ["capability-alias: 'echo' resolved to 'demo.echo' (echo)"]


def test_artifacts_keep_the_wave_b_c_text_unchanged(tmp_path: Path) -> None:
    store, run = _echo_run(tmp_path)
    legacy: dict[str, Any] = {"run_id": run}
    for name in ARTIFACTS:
        legacy[name] = store.read_optional(run, name)
    report = build_explain_report(store, run)
    rebuilt = {"run_id": report.run_id, **report.artifacts}
    text = render.explain(rebuilt)
    assert text == render.explain(legacy)
    for heading in render.EXPLAIN_CONTEXT_SECTIONS:
        assert heading in text


def test_failed_run_has_error_with_family_and_no_result(tmp_path: Path) -> None:
    forger, store = _forger(tmp_path, [bad_entry("crash", "bad-a")])
    out = forger.ask(AskRequest(intent="run it", capability="bad.thing"))
    assert out.status == "provider_failure"
    report = build_explain_report(store, out.run_id)
    assert report.status == "provider_failure"
    assert report.error is not None and report.error.code == "FORGE-PROTO-EXIT"
    assert report.error_family == "protocol"
    assert report.result is None and "result" in report.not_recorded
    _valid(report)


def test_older_run_lists_not_recorded_sections_and_unknown_reproducibility(
        tmp_path: Path) -> None:
    store, run = _echo_run(tmp_path)

    def older(data: dict[str, Any]) -> None:
        for key in ("telemetry_sha256", "verification_sha256", "reproducibility"):
            data.pop(key, None)
        data["inputs"].pop("risk_sha256", None)

    _rewrite(store, run, "receipt", older)
    for name in ("telemetry", "verification", "risk"):
        (store.run_dir(run) / f"{name}.json").unlink()
    report = build_explain_report(store, run)
    assert report.reproducibility == ReproducibilityInfo(level="unknown",
                                                         reasons=["not recorded"])
    assert report.telemetry is None and report.verification is None and report.risk is None
    assert set(report.not_recorded) == {"risk", "telemetry", "verification",
                                        "reproducibility"}
    assert report.integrity.divergences == []
    assert report.routing is not None and report.result is not None
    _valid(report)


def test_unreadable_and_tampered_artifacts_still_produce_a_report(tmp_path: Path) -> None:
    store, run = _echo_run(tmp_path)
    _rewrite(store, run, "result", lambda d: d.update(status="partial"))
    (store.run_dir(run) / "context.json").write_text("{not json", encoding="utf-8")
    report = build_explain_report(store, run)
    kinds = {(d.artifact, d.kind) for d in report.integrity.divergences}
    assert kinds == {("result", "modified"), ("context", "unreadable")}
    assert report.result is not None and report.result.status == "partial"
    assert report.context is None and "context" in report.not_recorded
    assert "context" not in report.artifacts
    assert "explain-unreadable: context" in report.limitations
    _valid(report)


def test_artifacts_are_redacted(tmp_path: Path) -> None:
    store, run = _echo_run(tmp_path)
    secret = "sk-" + "A" * 30
    _rewrite(store, run, "task", lambda d: d.update(intent=f"eco {secret}"))
    report = build_explain_report(store, run)
    assert secret not in json.dumps(to_dict(report))


def test_unknown_or_invalid_run(tmp_path: Path) -> None:
    store, _ = _echo_run(tmp_path)
    with pytest.raises(LookupError):
        build_explain_report(store, "20260101T000000Z-deadbeef")
    with pytest.raises(ValueError):
        build_explain_report(store, "../escape")


def test_report_writes_nothing_and_starts_no_provider(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store, run = _echo_run(tmp_path)
    before = _snapshot(store.runs_dir)

    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("explain must never start a process")

    monkeypatch.setattr(subprocess, "Popen", refuse)
    build_explain_report(store, run)
    assert _snapshot(store.runs_dir) == before


def test_plan_run_report_has_plan_nodes_handoffs_and_plan_telemetry(
        cross: CrossWorkspace) -> None:
    forger, store = _forger(cross.root, [SPARK_PLAN_ENTRY, API_PLAN_ENTRY])
    out = PlanExecutor(forger).run(PlanCommand(intent=PROOF_TASK, profile="max",
                                               execute=True))
    assert out.status == "ok", out.error
    before = _snapshot(store.runs_dir)
    report = build_explain_report(store, out.run_id)
    assert (report.kind, report.status, report.intent) == ("plan", "ok", PROOF_TASK)
    assert report.profile == "max"
    plan = report.plan
    assert plan is not None and len(plan.plan.nodes) == 2
    assert plan.result is not None and plan.workspace_descriptor is not None
    assert plan.global_stop is not None
    assert plan.global_stop.run_id == out.run_id
    assert plan.global_stop.action in ("stop_sufficient_evidence", "stop_no_expected_gain")
    assert [n.status for n in plan.result.nodes] == ["ok", "ok"]
    assert all(n.run_id for n in plan.result.nodes)
    assert plan.result.synthesis.handoffs
    assert report.telemetry is not None and report.telemetry["run_id"] == out.run_id
    assert report.reproducibility.level != "unknown" or report.reproducibility.reasons
    assert report.provider is None and report.result is None and report.context is None
    assert {
        "graph",
        "plan",
        "plan-result",
        "workspace-descriptor",
        "global-stop",
        "telemetry",
        "receipt",
    } <= set(report.artifacts)
    assert report.integrity.divergences == []
    assert any("/receipt" in name for name in report.integrity.checked)
    assert "provider" not in report.not_recorded and "result" not in report.not_recorded
    assert "plan" not in report.not_recorded
    _valid(report)
    text = render.explain_report(to_dict(report))
    assert "Telemetry:   profile=max" in text
    assert "Global stop:" in text
    assert "information_gain=" in text
    node_run = plan.result.nodes[1].run_id
    assert node_run is not None
    node = build_explain_report(store, node_run)
    assert node.parent_run == out.run_id and node.kind == "run"
    assert "handoff" in node.artifacts
    _valid(node)
    assert _snapshot(store.runs_dir) == before


def test_planned_only_plan_run_lists_plan_result_as_not_recorded(
        cross: CrossWorkspace) -> None:
    forger, store = _forger(cross.root, [SPARK_PLAN_ENTRY, API_PLAN_ENTRY])
    out = PlanExecutor(forger).run(PlanCommand(intent=PROOF_TASK, profile="max"))
    assert out.status == "planned", out.error
    report = build_explain_report(store, out.run_id)
    assert report.kind == "plan" and report.status == "planned"
    assert report.plan is not None and report.plan.result is None
    assert "plan-result" in report.not_recorded
    assert report.integrity.divergences == []
    _valid(report)


def test_refused_plan_run_surfaces_the_installation_items(tmp_path: Path) -> None:
    """A plan refused for an invalid provider: the explain report carries the installation
    section verbatim, checks its recorded hash and writes nothing (cross-forge 6.1/6.2)."""
    forger, store = _forger(tmp_path, [bad_entry("invalid-manifest", "bad-i"),
                                       SPARK_PLAN_ENTRY])
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps({
        "task_id": "from-file", "pattern": "pipeline", "source": "file",
        "profile": "max",
        "nodes": [
            {"id": "n1", "role": "standalone", "provider": "fixture-spark",
             "capability": "spark.performance", "action": "diagnose"},
            {"id": "n2", "role": "consumer", "provider": "bad-i",
             "capability": "bad.thing", "action": "run",
             "depends_on": [{"node": "n1", "epistemic": "explicit",
                             "evidence": "plan file"}],
             "inputs": ["n1"]}]}), encoding="utf-8")
    out = PlanExecutor(forger).run(PlanCommand(intent="spark then invalid",
                                               profile="max", plan_file=plan_file,
                                               execute=True))
    assert out.status == "refused"
    before = _snapshot(store.runs_dir)
    report = build_explain_report(store, out.run_id)
    assert (report.kind, report.status) == ("plan", "refused")
    assert report.error is not None and report.error_family is not None
    plan = report.plan
    assert plan is not None and plan.result is None
    installation = plan.installation
    assert installation is not None and installation.planning_only is True
    (item,) = installation.items
    assert (item.provider, item.state, item.source, item.nodes) == (
        "bad-i", "invalid", "registry", ["n2"])
    assert item.reason
    assert report.artifacts["installation"] == store.read(out.run_id, "installation")
    assert "installation" in report.integrity.checked
    assert report.integrity.divergences == []
    assert "plan-result" in report.not_recorded
    _valid(report)
    assert _snapshot(store.runs_dir) == before
