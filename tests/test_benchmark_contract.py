"""forge/Benchmark*/v1 contract validation (cyc9-01, ADR-0060).

The aggregator validates receipts strictly — a malformed result is an
error, never silently certified. Mirrors the strictness contract of
``forge/EcosystemCompatibility/v1`` (cyc8-01).
"""

from pathlib import Path

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


# --- cyc9-02: explicit unmeasured states, judge declaration, subject ---


@pytest.mark.parametrize(
    "metric,state",
    [
        ({"state": "not_available"}, "not_available"),
        ({"state": "not_applicable", "unit": "usd"}, "not_applicable"),
    ],
)
def test_metric_unmeasured_states(metric, state):
    doc = {
        **RESULT,
        "results": [
            {"scenario_id": "x-ok", "verdict": "pass", "metrics": {"tokens": metric}},
        ],
    }
    result = parse_result(doc, strict=True)
    m = result.results[0].metrics["tokens"]
    assert m.state == state
    assert m.value is None
    assert not m.measured


@pytest.mark.parametrize(
    "metric",
    [
        {"state": "measured"},  # measured without value
        {},  # defaults to measured, no value
        {"value": None},  # explicit null still defaults to measured
        {"state": "not_available", "value": 0},  # unmeasured must not carry a value
        {"state": "bogus", "value": 1},  # unknown state
    ],
)
def test_metric_state_value_invariant(metric):
    doc = {
        **RESULT,
        "results": [
            {"scenario_id": "x-ok", "verdict": "pass", "metrics": {"tokens": metric}},
        ],
    }
    with pytest.raises(ContractError):
        parse_result(doc, strict=True)


def test_judge_declaration_roundtrip():
    doc = {
        **RESULT,
        "results": [
            {
                "scenario_id": "x-ok",
                "verdict": "pass",
                "judge": {
                    "model": "judge-7b",
                    "rubric": "evals/rubrics/diagnosis-v2.md",
                    "human_validated_samples": 40,
                    "limitations": ["single-domain rubric"],
                },
            }
        ],
    }
    result = parse_result(doc, strict=True)
    judge = result.results[0].judge
    assert judge is not None
    assert judge.model == "judge-7b"
    assert judge.human_validated_samples == 40


@pytest.mark.parametrize(
    "judge",
    [
        {"rubric": "r.md"},  # model required
        {"model": "m"},  # rubric required
        {"model": "m", "rubric": "r", "human_validated_samples": -1},
    ],
)
def test_judge_declaration_rejects(judge):
    doc = {
        **RESULT,
        "results": [{"scenario_id": "x-ok", "verdict": "pass", "judge": judge}],
    }
    with pytest.raises(ContractError):
        parse_result(doc, strict=True)


def test_subject_field_roundtrip():
    doc = {**RESULT, "subject": "model-foo-1.2"}
    result = parse_result(doc, strict=True)
    assert result.subject == "model-foo-1.2"
    assert parse_result(RESULT, strict=True).subject is None


def test_standard_metric_directions():
    from theforge.contracts.benchmark import metric_direction

    assert metric_direction("precision") == "higher_better"
    assert metric_direction("duration_ms") == "lower_better"
    assert metric_direction("precision.api") == "higher_better"  # dotted suffix
    assert metric_direction("exotic_metric") is None  # never gates


# --- cyc9-03: MultiForgeScenario ---

MF_SCENARIO = {
    "schema": "forge/MultiForgeScenario/v1",
    "id": "api-doctor",
    "title": "diagnosis + remediation",
    "intent": "doctor diagnoses; api plans",
    "participants": ["forge-doctor-api", "api-forge"],
    "expected": {"participants_present": True, "min_labs_ok": 0},
}


def test_multiforge_scenario_roundtrip():
    from theforge.contracts.benchmark import parse_multiforge_scenario

    sc = parse_multiforge_scenario(MF_SCENARIO, strict=True)
    assert sc.id == "api-doctor"
    assert sc.participants == ["forge-doctor-api", "api-forge"]


@pytest.mark.parametrize(
    "patch,match",
    [
        ({"schema": "forge/MultiForgeScenario/v0"}, "unsupported schema"),
        ({"id": "Bad_Id"}, "bad id"),
        ({"participants": ["only-one"]}, "at least 2"),
        ({"participants": ["a-forge", "a-forge"]}, "duplicate"),
        ({"participants": ["ok-forge", "Bad_Id"]}, "bad participant id"),
        ({"ground_truth": "/abs/gt.json"}, "relative path"),
        ({"ground_truth": "../gt.json"}, "must not escape"),
    ],
)
def test_multiforge_scenario_rejects(patch, match):
    from theforge.contracts.benchmark import parse_multiforge_scenario

    doc = {**MF_SCENARIO, **patch}
    with pytest.raises(ContractError, match=match):
        parse_multiforge_scenario(doc, strict=True)


def test_multiforge_library_parses_strict():
    """Every versioned scenario in labs/multiforge/ is contract-valid."""
    from theforge.contracts.benchmark import load_multiforge_scenario

    root = Path(__file__).resolve().parents[1] / "labs" / "multiforge"
    files = sorted(p for p in root.glob("*.json") if p.name != "suite.json")
    assert len(files) >= 7, "cyc9-03 requires the §9.3 scenario set"
    for f in files:
        sc = load_multiforge_scenario(f)
        assert sc.id == f.stem
        assert len(sc.participants) >= 2
