"""Regression gate + repeat statistics (cyc9-02).

The gate compares against a real baseline — tolerances come from the
policy or the observed baseline spread, never invented. Unmeasured is
never zero; unknown metrics never gate.
"""

import pytest

from theforge.contracts.base import ContractError
from theforge.contracts.benchmark import BenchmarkResult, MetricValue, parse_result
from theforge.lab_gate import GatePolicy, GateRule, evaluate, parse_policy
from theforge.lab_stats import summarize

PRODUCER = {"id": "theforge", "version": "0.5.0"}


def _result(
    *,
    scenario: str = "sc-1",
    verdict: str = "pass",
    metrics: dict | None = None,
    forge: str = "the-forge",
    suite: str = "core",
    subject: str | None = None,
) -> BenchmarkResult:
    return parse_result(
        {
            "schema": "forge/BenchmarkResult/v1",
            "suite": suite,
            "forge": forge,
            "mode": "A",
            "created_at": "2026-10-15T21:00:00Z",
            "producer": PRODUCER,
            "subject": subject,
            "results": [
                {
                    "scenario_id": scenario,
                    "verdict": verdict,
                    "metrics": metrics or {},
                }
            ],
        },
        strict=True,
    )


def _m(v) -> dict:
    return {"value": v}


# --- lab_stats ---


def test_summarize_median_and_spread():
    ms = [MetricValue(value=v) for v in (10.0, 12.0, 11.0)]
    s = summarize("duration_ms", ms)
    assert s.median == 11.0
    assert s.measured == 3
    assert s.min == 10.0 and s.max == 12.0
    assert s.mad == pytest.approx(1.0)


def test_summarize_single_run_no_fake_spread():
    s = summarize("x", [MetricValue(value=7.0)])
    assert s.median == 7.0
    assert s.mad == 0.0
    assert s.iqr is None


def test_summarize_unmeasured_never_zero():
    s = summarize(
        "tokens",
        [MetricValue(state="not_available"), MetricValue(state="not_applicable")],
    )
    assert s.median is None
    assert s.measured == 0
    assert s.states == {"not_available": 1, "not_applicable": 1}


def test_summarize_bool_never_numeric():
    s = summarize("x", [MetricValue(value=True)])
    assert s.median is None  # bool is not a measurement


# --- gate: verdict pairing ---


def test_gate_pass_on_identical_runs():
    base = _result(metrics={"precision": _m(1.0)})
    cur = _result(metrics={"precision": _m(1.0)})
    report = evaluate([cur], [base])
    assert report["verdict"] == "pass"
    assert report["scenarios"][0]["verdict"] == "pass"


def test_gate_fails_on_quality_regression():
    base = _result(metrics={"precision": _m(1.0)})
    cur = _result(metrics={"precision": _m(0.7)})
    report = evaluate([cur], [base])
    assert report["verdict"] == "fail"
    m = report["scenarios"][0]["metrics"][0]
    assert m["verdict"] == "regression"
    assert m["baseline"] == 1.0 and m["current"] == 0.7


def test_gate_verdict_degradation_is_regression():
    base = _result(verdict="pass")
    cur = _result(verdict="fail")
    report = evaluate([cur], [base])
    assert report["verdict"] == "fail"
    assert report["scenarios"][0]["verdict"] == "regression"


def test_gate_baseline_never_passed_is_honest():
    base = _result(verdict="fail")
    cur = _result(verdict="pass")
    report = evaluate([cur], [base])
    assert report["scenarios"][0]["verdict"] == "no-baseline"
    assert report["verdict"] == "pass"  # cannot regress


def test_gate_improvement_reported_not_gated():
    base = _result(metrics={"recall": _m(0.5)})
    cur = _result(metrics={"recall": _m(0.9)})
    report = evaluate([cur], [base])
    assert report["verdict"] == "pass"
    assert report["scenarios"][0]["verdict"] == "improvement"


# --- gate: tolerances calibrated, not invented ---


def test_gate_baseline_spread_becomes_tolerance():
    base1 = _result(metrics={"duration_ms": _m(100)})
    base2 = _result(metrics={"duration_ms": _m(120)})  # spread = 20
    cur = _result(metrics={"duration_ms": _m(115)})
    report = evaluate([cur], [base1, base2])
    m = report["scenarios"][0]["metrics"][0]
    assert m["tolerance"] == 20
    assert m["verdict"] == "pass"  # inside observed spread


def test_gate_beyond_spread_regresses():
    base1 = _result(metrics={"duration_ms": _m(100)})
    base2 = _result(metrics={"duration_ms": _m(120)})
    cur = _result(metrics={"duration_ms": _m(150)})
    report = evaluate([cur], [base1, base2])
    assert report["verdict"] == "fail"


def test_gate_single_run_baseline_is_exact():
    base = _result(metrics={"false_positives": _m(2)})
    cur = _result(metrics={"false_positives": _m(3)})
    report = evaluate([cur], [base])
    m = report["scenarios"][0]["metrics"][0]
    assert m["tolerance"] == 0.0
    assert m["verdict"] == "regression"


def test_gate_policy_explicit_tolerance_wins():
    base1 = _result(metrics={"duration_ms": _m(100)})
    base2 = _result(metrics={"duration_ms": _m(120)})  # spread 20
    cur = _result(metrics={"duration_ms": _m(160)})
    policy = parse_policy(
        {
            "schema": "forge/LabGatePolicy/v1",
            "id": "loose",
            "metrics": {"duration_ms": {"abs_tolerance": 100}},
        }
    )
    report = evaluate([cur], [base1, base2], policy)
    assert report["scenarios"][0]["metrics"][0]["tolerance"] == 100
    assert report["verdict"] == "pass"


# --- gate: honest states ---


def test_gate_unmeasured_never_gates():
    base = _result(metrics={"tokens": {"state": "not_available"}})
    cur = _result(metrics={"tokens": _m(500)})
    report = evaluate([cur], [base])
    m = report["scenarios"][0]["metrics"][0]
    assert m["verdict"] == "unmeasured"
    assert report["verdict"] == "pass"


def test_gate_unknown_metric_never_gates():
    base = _result(metrics={"exotic_metric": _m(1)})
    cur = _result(metrics={"exotic_metric": _m(999)})
    report = evaluate([cur], [base])
    m = report["scenarios"][0]["metrics"][0]
    assert m["verdict"] == "unknown"
    assert report["verdict"] == "pass"  # reported, not gated


def test_gate_subject_mismatch_never_pairs():
    base = _result(metrics={"precision": _m(0.5)}, subject="model-a")
    cur = _result(metrics={"precision": _m(0.1)}, subject="model-b")
    report = evaluate([cur], [base])
    assert report["scenarios"][0]["verdict"] == "no-baseline"
    assert report["verdict"] == "pass"  # model variation ≠ infra variation


def test_gate_repeated_current_aggregates_by_median():
    base = _result(metrics={"precision": _m(0.9)})
    cur1 = _result(metrics={"precision": _m(0.88)})
    cur2 = _result(metrics={"precision": _m(0.9)})
    report = evaluate([cur1, cur2], [base])
    m = report["scenarios"][0]["metrics"][0]
    assert m["current"] == pytest.approx(0.89)
    assert m["verdict"] == "regression"  # median 0.89 < 0.9, tol 0


def test_gate_policy_unknown_metric_requires_direction():
    with pytest.raises(ContractError, match="explicit direction"):
        parse_policy(
            {
                "schema": "forge/LabGatePolicy/v1",
                "id": "bad",
                "metrics": {"exotic": {"abs_tolerance": 1}},
            }
        )


def test_gate_policy_unknown_metric_with_direction_ok():
    policy = parse_policy(
        {
            "schema": "forge/LabGatePolicy/v1",
            "id": "ext",
            "metrics": {"exotic": {"direction": "lower_better"}},
        }
    )
    assert policy.rule_for("exotic").direction == "lower_better"


def test_gate_string_metrics_equal_direction():
    policy = GatePolicy(
        id="t",
        metrics={"config_hash": GateRule(direction="equal")},
    )
    base = _result(metrics={"config_hash": _m("abc")})
    cur_ok = _result(metrics={"config_hash": _m("abc")})
    cur_bad = _result(metrics={"config_hash": _m("def")})
    assert evaluate([cur_ok], [base], policy)["verdict"] == "pass"
    assert evaluate([cur_bad], [base], policy)["verdict"] == "fail"
