"""forge/Benchmark*/v1 contract validation (cyc9-01, ADR-0060).

The aggregator validates receipts strictly — a malformed result is an
error, never silently certified. Mirrors the strictness contract of
``forge/EcosystemCompatibility/v1`` (cyc8-01).
"""

import pytest

from theforge.contracts.base import ContractError
from theforge.contracts.benchmark import (
    parse_result,
    parse_suite,
)

PRODUCER = {"id": "forge-doctor-api", "version": "0.2.0"}

SUITE = {
    "schema": "forge/BenchmarkSuite/v1",
    "id": "doctor-api-core",
    "owner_forge": "forge-doctor-api",
    "created_at": "2026-10-15",
    "source": "labs/suite.json",
    "mode": "A",
    "scenarios": [
        {"id": "broken-auth", "path": "labs/broken-auth", "sha256": "a" * 64},
        {"id": "missing-rate-limit", "path": "labs/missing-rate-limit"},
    ],
}

RESULT = {
    "schema": "forge/BenchmarkResult/v1",
    "suite": "doctor-api-core",
    "forge": "forge-doctor-api",
    "mode": "A",
    "created_at": "2026-10-15T21:00:00Z",
    "producer": PRODUCER,
    "external": False,
    "results": [
        {
            "scenario_id": "broken-auth",
            "verdict": "pass",
            "metrics": {"precision": {"value": 1.0, "unit": "ratio"}},
            "duration_ms": 120,
            "evidence_ref": "factory/runs/lab-001.json",
        },
        {
            "scenario_id": "missing-rate-limit",
            "verdict": "fail",
            "metrics": {"fp_count": {"value": 2}},
        },
    ],
}


def test_suite_roundtrip_strict():
    suite = parse_suite(SUITE, strict=True)
    assert suite.id == "doctor-api-core"
    assert suite.scenarios[0].sha256 == "a" * 64
    assert suite.scenarios[1].mode == "A"


def test_result_roundtrip_strict():
    result = parse_result(RESULT, strict=True)
    assert result.mode == "A"
    assert result.results[0].metrics["precision"].value == 1.0
    assert result.results[0].metrics["precision"].unit == "ratio"
    assert result.results[1].metrics["fp_count"].unit == ""


@pytest.mark.parametrize(
    "patch,match",
    [
        ({"schema": "forge/BenchmarkSuite/v0"}, "unsupported schema"),
        ({"id": "Bad_Id"}, "bad suite id"),
        ({"owner_forge": "Forge"}, "bad owner_forge"),
        ({"created_at": "15/10/2026"}, "ISO date"),
        ({"source": "/abs/suite.json"}, "relative path"),
        ({"source": "../suite.json"}, "must not escape"),
        ({"scenarios": []}, "must not be empty"),
        ({"scenarios": [SUITE["scenarios"][0], SUITE["scenarios"][0]]}, "duplicate"),
    ],
)
def test_suite_rejects(patch, match):
    doc = {**SUITE, **patch}
    with pytest.raises(ContractError, match=match):
        parse_suite(doc, strict=True)


@pytest.mark.parametrize(
    "scenario,match",
    [
        ({"id": "bad_id", "path": "labs/x"}, "bad scenario id"),
        ({"id": "x", "path": "/etc/passwd"}, "relative path"),
        ({"id": "x", "path": "../escape"}, "must not escape"),
        ({"id": "x", "path": "C:/win"}, "relative path"),
        ({"id": "x", "path": "labs/x", "sha256": "deadbeef"}, "64-hex"),
    ],
)
def test_scenario_path_guardrails(scenario, match):
    doc = {**SUITE, "scenarios": [scenario]}
    with pytest.raises(ContractError, match=match):
        parse_suite(doc, strict=True)


def test_mode_c_scenario_needs_mode_c_suite():
    doc = {
        **SUITE,
        "scenarios": [{"id": "live", "path": "labs/live", "mode": "C"}],
    }
    with pytest.raises(ContractError, match="mode C"):
        parse_suite(doc, strict=True)


@pytest.mark.parametrize(
    "patch,match",
    [
        ({"schema": "forge/BenchmarkResult/v0"}, "unsupported schema"),
        ({"suite": "Bad"}, "bad suite id"),
        ({"forge": "bad_id"}, "bad forge id"),
        ({"created_at": "2026-10-15"}, "ISO timestamp"),
        ({"mode": "C", "external": False}, "external=False"),
        ({"mode": "A", "external": True}, "external=True"),
        ({"mode": "D"}, "expected one of"),
    ],
)
def test_result_rejects(patch, match):
    doc = {**RESULT, **patch}
    if doc.get("mode") == "C":
        doc.setdefault("results", [])
    with pytest.raises(ContractError, match=match):
        parse_result(doc, strict=True)


def test_result_duplicate_scenarios_rejected():
    doc = {**RESULT, "results": [RESULT["results"][0], RESULT["results"][0]]}
    with pytest.raises(ContractError, match="duplicate"):
        parse_result(doc, strict=True)


@pytest.mark.parametrize(
    "result_row,match",
    [
        ({"scenario_id": "bad_id", "verdict": "pass"}, "bad scenario id"),
        ({"scenario_id": "x", "verdict": "pass", "duration_ms": -1}, ">= 0"),
        (
            {"scenario_id": "x", "verdict": "pass", "metrics": {"Bad Metric": {"value": 1}}},
            "bad metric name",
        ),
        (
            {
                "scenario_id": "x",
                "verdict": "pass",
                "evidence_ref": "/abs/receipt.json",
            },
            "relative path",
        ),
        (
            {
                "scenario_id": "x",
                "verdict": "pass",
                "evidence_ref": "../receipt.json",
            },
            "must not escape",
        ),
        ({"scenario_id": "x", "verdict": "maybe"}, "expected one of"),
    ],
)
def test_scenario_result_rejects(result_row, match):
    doc = {**RESULT, "results": [result_row]}
    with pytest.raises(ContractError, match=match):
        parse_result(doc, strict=True)


def test_evidence_ref_accepts_locator_uri():
    doc = {
        **RESULT,
        "results": [
            {"scenario_id": "x-ok", "verdict": "pass", "evidence_ref": "ctx://lab/run-1"},
        ],
    }
    result = parse_result(doc, strict=True)
    assert result.results[0].evidence_ref == "ctx://lab/run-1"


def test_metric_value_types():
    doc = {
        **RESULT,
        "results": [
            {
                "scenario_id": "x-ok",
                "verdict": "pass",
                "metrics": {
                    "count": {"value": 3},
                    "ratio": {"value": 0.5, "unit": "ratio"},
                    "label": {"value": "p95"},
                },
            }
        ],
    }
    result = parse_result(doc, strict=True)
    assert result.results[0].metrics["count"].value == 3
    assert result.results[0].metrics["label"].value == "p95"
