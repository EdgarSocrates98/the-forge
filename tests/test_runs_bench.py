"""Wave P cross-forge run benchmark: case coverage, output format, budget
comparison — and two real fixture runs so the metric extraction is exercised
against persisted artifacts, not just the shape.
"""

import importlib
import json
from pathlib import Path
from types import ModuleType

import pytest

BENCH = Path(__file__).parents[1] / "scripts" / "bench"


@pytest.fixture
def bench(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.syspath_prepend(str(BENCH))
    return importlib.import_module("run_runs_bench")


def _case(bench: ModuleType, name: str, **over: object) -> ModuleType:
    import dataclasses

    return dataclasses.replace(next(c for c in bench.CASES if c.name == name), **over)


# --- coverage and shape (no runs) --------------------------------------------------------------


def test_cases_cover_the_wave_p_list(bench: ModuleType) -> None:
    assert {c.name for c in bench.CASES} == {
        "single_spark",
        "single_api",
        "pipeline",
        "ambiguous",
        "high_risk",
        "semantic_fallback",
        "parallel",
        "debate",
    }


def test_every_case_declares_its_expected_status(bench: ModuleType) -> None:
    expected = {
        "single_spark": "ok",
        "single_api": "ok",
        "pipeline": "ok",
        "ambiguous": "ambiguous",
        "high_risk": "refused",
        "semantic_fallback": "ok",
        "parallel": "ok",
        "debate": "ok",
    }
    assert {c.name: c.expect for c in bench.CASES} == expected


def test_report_format(bench: ModuleType) -> None:
    result = bench.CaseResult(
        name="single_spark",
        median_ms=1.5,
        p90_ms=2.0,
        runs=3,
        status="ok",
        expect="ok",
        nodes=1,
        metrics={k: 0 for k in bench.METRIC_KEYS},
    )
    report = bench.build_report({"single_spark": result}, {"machine": "m", "git_head": "abc"})
    assert report["schema"] == "theforge-bench-runs/v1"
    entry = report["cases"]["single_spark"]
    assert (entry["median_ms"], entry["p90_ms"], entry["runs"]) == (1.5, 2.0, 3)
    assert entry["status"] == "ok" and entry["expect"] == "ok" and entry["nodes"] == 1
    assert set(entry["metrics"]) == set(bench.METRIC_KEYS)


def test_load_results_roundtrip(bench: ModuleType, tmp_path: Path) -> None:
    result = bench.CaseResult(
        name="parallel",
        median_ms=9.5,
        p90_ms=10.0,
        runs=2,
        status="ok",
        expect="ok",
        nodes=4,
        metrics={k: 1 for k in bench.METRIC_KEYS},
    )
    path = tmp_path / "runs.json"
    path.write_text(json.dumps(bench.build_report({"parallel": result}, {})))
    loaded = bench.load_results(path)
    assert loaded["parallel"].median_ms == 9.5 and loaded["parallel"].runs == 2


def test_load_results_rejects_the_other_schema(bench: ModuleType, tmp_path: Path) -> None:
    path = tmp_path / "wrong.json"
    path.write_text(json.dumps({"schema": "theforge-bench/v1", "results": {}}))
    with pytest.raises(ValueError, match="unsupported schema"):
        bench.load_results(path)


def test_derive_budgets_from_a_runs_report(bench: ModuleType, tmp_path: Path) -> None:
    result = bench.CaseResult(
        name="single_api",
        median_ms=100.0,
        p90_ms=110.0,
        runs=5,
        status="ok",
        expect="ok",
        nodes=1,
        metrics={k: 0 for k in bench.METRIC_KEYS},
    )
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(bench.build_report({"single_api": result}, {"git_head": "abc123"})))
    budgets = bench.derive_runs_budgets(path, 1.5)
    assert budgets["single_api"].budget_ms == 150.0
    assert budgets["single_api"].baseline_ms == 100.0


# --- real fixture runs (persisted artifacts drive the metrics) ---------------------------------


def test_single_spark_case_metrics(bench: ModuleType, tmp_path: Path) -> None:
    result = bench.run_case(_case(bench, "single_spark"), tmp_path, 1, lambda s: None)
    assert result.status == "ok" and result.nodes == 1
    m = result.metrics
    assert m["provider_calls"] == 1 and m["verification_calls"] == 1
    assert m["context_bytes"] > 0 and m["handoff_bytes"] == 0
    assert m["semantic_calls"] == 0


def test_ambiguous_case_stays_ambiguous_and_untouched(bench: ModuleType, tmp_path: Path) -> None:
    result = bench.run_case(_case(bench, "ambiguous"), tmp_path, 1, lambda s: None)
    assert result.status == "ambiguous"
    assert result.metrics == {k: 0 for k in bench.METRIC_KEYS}


def test_a_wrong_status_fails_the_case(bench: ModuleType, tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="expected 'ambiguous'"):
        bench.run_case(
            _case(bench, "single_spark", expect="ambiguous"), tmp_path, 1, lambda s: None
        )


def test_metrics_of_a_plan_case_aggregate_the_children(bench: ModuleType, tmp_path: Path) -> None:
    result = bench.run_case(_case(bench, "pipeline"), tmp_path, 1, lambda s: None)
    assert result.status == "ok" and result.nodes == 3  # root + 2 node runs
    m = result.metrics
    # n1 execute + n2 execute (+ the plan-op estimates on the root run)
    assert m["provider_calls"] >= 2 and m["verification_calls"] == 2
    assert m["handoff_bytes"] > 0  # n2 received n1's handoff
