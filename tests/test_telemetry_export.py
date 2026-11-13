"""OTLP telemetry export: persisted run evidence -> ExportTraceServiceRequest.

Covers the Wave-W complement of ``theforge trace``: identity derivation
(deterministic sha256 ids), time anchoring (end-anchored to ``created_at``,
``run_id`` fallback, never invented), correlation grouping (orchestration
receipt as root, ``parent_run`` links) and the honesty surface — runs without
a telemetry artifact are named in ``skipped``, never synthesized.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pytest

from helpers import SPARK_ENTRY, SPARK_PLAN_ENTRY, make_workspace, write_file
from theforge import telemetry_export
from theforge.cli.main import main
from theforge.contracts.canonical import utc_now
from theforge.contracts.orchestration import (
    OrchestrationEntry,
    OrchestrationProvenance,
    OrchestrationReport,
)
from theforge.forger import Forger, PlanCommand, PlanExecutor
from theforge.forger.orchestrator import AskRequest
from theforge.orchestrate import persist_report
from theforge.registry import Registry
from theforge.runs import RunStore

TRACE_ID = re.compile(r"^[0-9a-f]{32}$")
SPAN_ID = re.compile(r"^[0-9a-f]{16}$")


def _ask(root: Path, forge: Path, **kwargs: Any):
    out = Forger(root, Registry(forge), RunStore(forge)).ask(
        AskRequest(intent="glue job", profile="balanced", **kwargs)
    )
    assert out.status == "ok"
    return out.run_id


def _spans(document: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        s
        for rs in document["resourceSpans"]
        for ss in rs["scopeSpans"]
        for s in ss["spans"]
    ]


def _attrs(span: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for item in span.get("attributes") or []:
        value = item["value"]
        out[item["key"]] = next(iter(value.values()))
    return out


def _resource_attrs(document: dict[str, Any], index: int = 0) -> dict[str, Any]:
    raw = document["resourceSpans"][index]["resource"]["attributes"]
    return {i["key"]: next(iter(i["value"].values())) for i in raw}


class TestSingleRun:
    def test_export_maps_the_local_trace(self, tmp_path: Path) -> None:
        forge = make_workspace(tmp_path, [SPARK_ENTRY])
        write_file(tmp_path, "jobs_glue.py", "x = 1")
        run_id = _ask(tmp_path, forge)
        document, summary = telemetry_export.build_otlp_request(forge, run_ids=[run_id])
        assert summary.runs_exported == [run_id] and summary.spans > 1
        spans = _spans(document)
        assert len(document["resourceSpans"]) == 1
        trace_ids = {s["traceId"] for s in spans}
        assert len(trace_ids) == 1 and TRACE_ID.match(next(iter(trace_ids)))
        root = next(s for s in spans if s["name"] == "theforge.run")
        assert SPAN_ID.match(root["spanId"]) and "parentSpanId" not in root
        assert _attrs(root)["theforge.run_id"] == run_id
        assert _attrs(root)["theforge.time_anchor"] == "created_at"
        names = {s["name"] for s in spans}
        assert "provider:fixture-spark" in names and "scan" in names
        inner = [s for s in spans if s["name"] != "theforge.run"]
        assert all(s["parentSpanId"] for s in inner)
        assert all(
            int(s["endTimeUnixNano"]) >= int(s["startTimeUnixNano"]) for s in spans
        )
        assert _resource_attrs(document)["service.name"] == "the-forge"
        assert _resource_attrs(document)["session.id"] == run_id

    def test_export_is_byte_deterministic(self, tmp_path: Path) -> None:
        forge = make_workspace(tmp_path, [SPARK_ENTRY])
        write_file(tmp_path, "jobs_glue.py", "x = 1")
        run_id = _ask(tmp_path, forge)
        first, _ = telemetry_export.build_otlp_request(forge, run_ids=[run_id])
        second, _ = telemetry_export.build_otlp_request(forge, run_ids=[run_id])
        assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)

    def test_missing_and_broken_runs_are_named_not_synthesized(
        self, tmp_path: Path
    ) -> None:
        forge = make_workspace(tmp_path, [SPARK_ENTRY])
        write_file(tmp_path, "jobs_glue.py", "x = 1")
        real = _ask(tmp_path, forge)
        document, summary = telemetry_export.build_otlp_request(
            forge, run_ids=[real, "20990101T000000Z-deadbeef"]
        )
        assert summary.skipped == {"20990101T000000Z-deadbeef": "unknown-run"}
        assert summary.runs_exported == [real]
        doc_ids = {
            _attrs(s).get("theforge.run_id") for s in _spans(document)
        } - {None}
        assert doc_ids == {real}  # the phantom run never enters the document


class TestCorrelation:
    def test_correlated_runs_share_one_trace(self, tmp_path: Path) -> None:
        forge = make_workspace(tmp_path, [SPARK_ENTRY])
        write_file(tmp_path, "jobs_glue.py", "x = 1")
        corr = "corr-unittest"
        a = _ask(tmp_path, forge, correlation_id=corr)
        b = _ask(tmp_path, forge, correlation_id=corr)
        document, summary = telemetry_export.build_otlp_request(
            forge, correlation_id=corr
        )
        assert sorted(summary.runs_exported) == sorted([a, b])
        assert len(document["resourceSpans"]) == 1
        trace_ids = {s["traceId"] for s in _spans(document)}
        assert len(trace_ids) == 1
        # no orchestration receipt persisted -> no fabricated root; the two
        # runs are honest siblings of the same correlation trace
        names = [s["name"] for s in _spans(document)]
        assert names.count("theforge.run") == 2
        assert "theforge.orchestrate" not in names
        assert _resource_attrs(document)["session.id"] == corr
        assert _resource_attrs(document)["theforge.correlation_id"] == corr

    def test_orchestration_receipt_becomes_the_root(self, tmp_path: Path) -> None:
        forge = make_workspace(tmp_path, [SPARK_ENTRY])
        write_file(tmp_path, "jobs_glue.py", "x = 1")
        corr = "corr-unittest-orch"
        _ask(tmp_path, forge, correlation_id=corr)
        _ask(tmp_path, forge, correlation_id=corr)
        report = OrchestrationReport(
            kind="run",
            intent="verify api result",
            correlation_id=corr,
            generated_at=utc_now(),
            plan_status="planned",
            entries=[
                OrchestrationEntry(
                    provider="fixture-spark",
                    capability="spark.performance",
                    status="completed",
                    delegation_stage="COMPLETED",
                    handoff_status="received",
                )
            ],
            provenance=OrchestrationProvenance(
                plan_sha256=hashlib.sha256(b"plan").hexdigest(),
                delegation_tasks=["task-1"],
            ),
        )
        persist_report(report, tmp_path)
        document, _ = telemetry_export.build_otlp_request(forge, correlation_id=corr)
        spans = _spans(document)
        root = next(s for s in spans if s["name"] == "theforge.orchestrate")
        root_attrs = _attrs(root)
        assert root_attrs["theforge.correlation_id"] == corr
        assert root_attrs["theforge.plan_sha256"] == hashlib.sha256(b"plan").hexdigest()
        assert root_attrs["theforge.delegation_tasks"] == 1
        assert (root.get("events") or [{}])[0]["name"] == "delegation.entry"
        runs = [s for s in spans if s["name"] == "theforge.run"]
        assert len(runs) == 2
        assert all(s["parentSpanId"] == root["spanId"] for s in runs)

    def test_parent_run_links_resolve_within_the_tree(self, tmp_path: Path) -> None:
        forge = make_workspace(tmp_path, [SPARK_PLAN_ENTRY])
        store = RunStore(forge)
        plan_file = tmp_path / "p.json"
        plan_file.write_text(
            json.dumps(
                {
                    "task_id": "corr",
                    "pattern": "pipeline",
                    "source": "file",
                    "profile": "max",
                    "nodes": [
                        {
                            "id": "n1",
                            "role": "standalone",
                            "provider": "fixture-spark",
                            "capability": "spark.performance",
                            "action": "diagnose",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        out = PlanExecutor(Forger(tmp_path, Registry(forge), store)).run(
            PlanCommand(intent="corr", profile="max", plan_file=plan_file, execute=True)
        )
        assert out.status == "ok"
        plan_telemetry = store.read_optional(out.run_id, "telemetry") or {}
        corr = plan_telemetry.get("correlation_id")
        assert corr == out.run_id  # the plan run is the tree root
        document, _ = telemetry_export.build_otlp_request(
            forge, correlation_id=str(corr)
        )
        spans = _spans(document)
        roots = {
            _attrs(s).get("theforge.run_id"): s
            for s in spans
            if _attrs(s).get("theforge.time_anchor")  # run roots only
        }
        plan_root = roots[out.run_id]
        node_runs = [rid for rid in roots if rid != out.run_id]
        assert node_runs, "the child node run must export its root span"
        child = roots[node_runs[0]]
        assert child["parentSpanId"] == plan_root["spanId"]
        expected = hashlib.sha256(
            f"theforge-run:{out.run_id}".encode()
        ).hexdigest()[:16]
        assert plan_root["spanId"] == expected


class TestSelection:
    def test_last_selects_newest_runs(self, tmp_path: Path) -> None:
        forge = make_workspace(tmp_path, [SPARK_ENTRY])
        write_file(tmp_path, "jobs_glue.py", "x = 1")
        a = _ask(tmp_path, forge)
        b = _ask(tmp_path, forge)
        document, summary = telemetry_export.build_otlp_request(forge, last=1)
        assert summary.runs_exported == [b]
        doc_runs = {
            _attrs(s).get("theforge.run_id") for s in _spans(document)
        } - {None}
        assert doc_runs == {b} and a not in doc_runs

    def test_last_orders_by_observed_creation_not_id_suffix(
        self, tmp_path: Path
    ) -> None:
        """Same-second run ids differ only in the random suffix — ``--last``
        must follow the observed ``created_at``, not lexicographic id order."""
        forge = tmp_path / ".forge"
        for rid, created in (
            ("20260101T000000Z-zzzzzzzz", "2026-01-01T00:00:00.000001Z"),
            ("20260101T000000Z-aaaaaaaa", "2026-01-01T00:00:00.000002Z"),
        ):
            run_dir = forge / "runs" / rid
            run_dir.mkdir(parents=True)
            (run_dir / "telemetry.json").write_text(
                json.dumps({"created_at": created, "spans": []}),
                encoding="utf-8",
            )
        _, summary = telemetry_export.build_otlp_request(forge, last=1)
        assert summary.runs_exported == ["20260101T000000Z-aaaaaaaa"]


class TestCli:
    def test_export_writes_deterministic_file(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        make_workspace(tmp_path, [SPARK_ENTRY])
        write_file(tmp_path, "jobs_glue.py", "x = 1")
        run_id = _ask(tmp_path, tmp_path / ".forge")
        out_file = tmp_path / "otlp.json"
        code = main(
            [
                "telemetry",
                "export",
                "--root",
                str(tmp_path),
                "--run",
                run_id,
                "--out",
                str(out_file),
                "--json",
            ]
        )
        assert code == 0
        receipt = json.loads(capsys.readouterr().out)
        assert receipt["spans"] > 1
        payload = json.loads(out_file.read_text(encoding="utf-8"))
        assert payload["resourceSpans"]
        assert receipt["sha256"] == hashlib.sha256(
            out_file.read_bytes()
        ).hexdigest()

    def test_no_selection_is_a_usage_error(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        make_workspace(tmp_path, [SPARK_ENTRY])
        code = main(
            [
                "telemetry",
                "export",
                "--root",
                str(tmp_path),
                "--out",
                str(tmp_path / "x.json"),
            ]
        )
        assert code == 2
        assert "selection" in capsys.readouterr().err
