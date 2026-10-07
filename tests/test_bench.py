"""Benchmark procedure (11.1, 11.4): synthetic workspace generator, output format and budget
comparison. Nothing here measures time; the benchmark itself never runs in the offline suite.
"""

import importlib
import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

from theforge.context import scan_workspace

BENCH = Path(__file__).parents[1] / "scripts" / "bench"
EXTENSIONS = {".md", ".txt", ".py", ".json"}


@pytest.fixture
def bench(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.syspath_prepend(str(BENCH))
    return importlib.import_module("run_bench")


@pytest.fixture
def workspace(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.syspath_prepend(str(BENCH))
    return importlib.import_module("workspace")


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


# --- generator -------------------------------------------------------------------------------


def test_generator_writes_exactly_the_requested_count(
    workspace: ModuleType, tmp_path: Path
) -> None:
    workspace.generate_workspace(tmp_path / "ws", 50)
    files = _snapshot(tmp_path / "ws")
    assert len(files) == 50
    assert {Path(rel).suffix for rel in files} == EXTENSIONS  # the mix covers every kind


def test_generator_is_deterministic_for_a_seed(workspace: ModuleType, tmp_path: Path) -> None:
    workspace.generate_workspace(tmp_path / "a", 50, seed=7)
    workspace.generate_workspace(tmp_path / "b", 50, seed=7)
    workspace.generate_workspace(tmp_path / "c", 50, seed=8)
    a, b, c = (_snapshot(tmp_path / name) for name in "abc")
    assert a == b
    assert a != c


def test_generator_sizes_are_fixed_and_content_is_lf(workspace: ModuleType, tmp_path: Path) -> None:
    workspace.generate_workspace(tmp_path / "ws", 50)
    for rel, data in _snapshot(tmp_path / "ws").items():
        assert len(data) in workspace.SIZES, rel
        assert b"\r" not in data, rel


def test_generated_files_are_all_scan_candidates(workspace: ModuleType, tmp_path: Path) -> None:
    root = tmp_path / "ws"
    workspace.generate_workspace(root, 50)
    scan = scan_workspace(root, ["."])
    assert len(scan.files) == 50
    assert scan.excluded == []  # no secret-like names, nothing outside the root


def test_generator_refuses_a_non_empty_root(workspace: ModuleType, tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    (root / "keep.txt").write_text("user data", encoding="utf-8")
    with pytest.raises(ValueError, match="not empty"):
        workspace.generate_workspace(root, 5)
    assert _snapshot(root) == {"keep.txt": b"user data"}


def test_generator_rejects_a_non_positive_count(workspace: ModuleType, tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        workspace.generate_workspace(tmp_path / "ws", 0)


# --- measurement summary (no clock) ----------------------------------------------------------


def test_summary_median_and_p90_from_samples(bench: ModuleType) -> None:
    samples_ns = [n * 1_000_000 for n in (5, 1, 4, 2, 3, 10, 6, 9, 7, 8)]
    m = bench.summarize("x", samples_ns)
    assert (m.name, m.runs, m.median_ms, m.p90_ms) == ("x", 10, 5.5, 9.0)


def test_measure_calls_setup_and_fn_once_per_run(bench: ModuleType) -> None:
    calls: list[str] = []
    m = bench.measure("x", lambda: calls.append("fn"), 3, setup=lambda: calls.append("setup"))
    assert calls == ["setup", "fn"] * 3
    assert m.runs == 3
    assert 0 <= m.median_ms <= m.p90_ms


def test_measure_requires_at_least_one_run(bench: ModuleType) -> None:
    with pytest.raises(ValueError):
        bench.measure("x", lambda: None, 0)


# --- output format ---------------------------------------------------------------------------


def test_measurement_names_cover_the_procedure(bench: ModuleType) -> None:
    assert bench.MEASUREMENTS == (
        "cli_startup",
        "registry_cold",
        "registry_warm",
        "scan_1k",
        "scan_10k",
        "routing_10k",
        "context_1k_cold",
        "context_1k_warm",
        "context_10k_cold",
        "context_10k_warm",
        "persist_run",
        "graph_build",
        "graph_refresh_warm",
        "plan_validate",
        "replay_verify",
        "explain_build",
    )


def test_every_measurement_has_a_committed_budget(bench: ModuleType) -> None:
    """Wave W: the budgets file covers every measurement of the procedure."""
    budgets = bench.load_budgets(BENCH / "budgets.json")
    missing = bench.missing_budgets(
        {
            name: bench.Measurement(name=name, median_ms=1.0, p90_ms=1.0, runs=1)
            for name in bench.MEASUREMENTS
        },
        budgets,
    )
    assert missing == []


def test_report_format(bench: ModuleType) -> None:
    results = {"scan_1k": bench.Measurement(name="scan_1k", median_ms=1.5, p90_ms=2.0, runs=5)}
    report = bench.build_report(results, bench.collect_origin())
    assert report["schema"] == "theforge-bench/v1"
    assert set(report["origin"]) == {
        "machine",
        "os",
        "python",
        "date",
        "forge_version",
        "git_head",
        "git_dirty",
    }
    assert report["origin"]["git_dirty"] in (True, False, None)
    assert all(
        isinstance(report["origin"][k], str)
        for k in ("machine", "os", "python", "date", "forge_version")
    )
    assert report["results"] == {"scan_1k": {"median_ms": 1.5, "p90_ms": 2.0, "runs": 5}}
    assert json.loads(json.dumps(report)) == report


def test_report_round_trips_through_load_results(bench: ModuleType, tmp_path: Path) -> None:
    results = {
        "persist_run": bench.Measurement(name="persist_run", median_ms=3.0, p90_ms=4.0, runs=3)
    }
    path = tmp_path / "bench.json"
    path.write_text(
        json.dumps(bench.build_report(results, bench.collect_origin())), encoding="utf-8"
    )
    assert bench.load_results(path) == results


def test_load_results_rejects_another_schema(bench: ModuleType, tmp_path: Path) -> None:
    path = tmp_path / "bench.json"
    path.write_text(
        json.dumps({"schema": "other/v1", "origin": {}, "results": {}}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="schema"):
        bench.load_results(path)


# --- budgets ---------------------------------------------------------------------------------


def _budgets_file(path: Path, budgets: dict[str, float]) -> Path:
    path.write_text(
        json.dumps(
            {
                name: {
                    "budget_ms": value,
                    "baseline_ms": value / 1.5,
                    "factor": 1.5,
                    "origin": "baseline.json",
                }
                for name, value in budgets.items()
            }
        ),
        encoding="utf-8",
    )
    return path


def test_load_budgets(bench: ModuleType, tmp_path: Path) -> None:
    budgets = bench.load_budgets(_budgets_file(tmp_path / "b.json", {"scan_1k": 30.0}))
    assert budgets == {
        "scan_1k": bench.Budget(
            budget_ms=30.0, baseline_ms=20.0, factor=1.5, origin="baseline.json"
        )
    }


def test_compare_budgets_reports_only_medians_above_budget(bench: ModuleType) -> None:
    def m(name: str, median: float) -> object:
        return bench.Measurement(name=name, median_ms=median, p90_ms=median * 2, runs=3)

    def b(budget: float) -> object:
        return bench.Budget(budget_ms=budget, baseline_ms=budget / 1.5, factor=1.5, origin="o")

    results = {
        "over": m("over", 31.0),
        "equal": m("equal", 30.0),
        "under": m("under", 1.0),
        "unbudgeted": m("unbudgeted", 999.0),
    }
    budgets = {"over": b(30.0), "equal": b(30.0), "under": b(30.0), "unmeasured": b(1.0)}
    regressions = bench.compare_budgets(results, budgets)
    assert regressions == [bench.Regression(name="over", median_ms=31.0, budget_ms=30.0)]
    assert bench.missing_budgets(results, budgets) == ["unbudgeted"]


def _results_file(bench: ModuleType, path: Path, medians: dict[str, float]) -> Path:
    results = {
        n: bench.Measurement(name=n, median_ms=v, p90_ms=v, runs=3) for n, v in medians.items()
    }
    path.write_text(
        json.dumps(bench.build_report(results, bench.collect_origin())), encoding="utf-8"
    )
    return path


def test_check_exits_non_zero_on_regression(
    bench: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    results = _results_file(bench, tmp_path / "r.json", {"scan_1k": 50.0, "scan_10k": 1.0})
    budgets = _budgets_file(tmp_path / "b.json", {"scan_1k": 30.0})
    code = bench.main(["--results", str(results), "--check", str(budgets)])
    out = capsys.readouterr().out
    assert code == 1
    assert "REGRESSION scan_1k" in out
    assert "scan_10k: no budget" in out


def test_check_exits_zero_within_budget(
    bench: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    results = _results_file(bench, tmp_path / "r.json", {"scan_1k": 10.0})
    budgets = _budgets_file(tmp_path / "b.json", {"scan_1k": 30.0})
    assert bench.main(["--results", str(results), "--check", str(budgets)]) == 0
    assert "REGRESSION" not in capsys.readouterr().out


def test_results_without_check_is_a_usage_error(bench: ModuleType, tmp_path: Path) -> None:
    results = _results_file(bench, tmp_path / "r.json", {"scan_1k": 10.0})
    with pytest.raises(SystemExit) as excinfo:
        bench.main(["--results", str(results)])
    assert excinfo.value.code == 2


def test_origin_records_a_dirty_worktree(
    bench: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_git(stdout: str, code: int = 0) -> Callable[..., object]:
        return lambda *args: subprocess.CompletedProcess(["git", *args], code, stdout, "")

    monkeypatch.setattr(bench, "_git", fake_git(" M scripts/bench/run_bench.py\n"))
    assert bench.collect_origin()["git_dirty"] is True
    monkeypatch.setattr(bench, "_git", fake_git(""))
    assert bench.collect_origin()["git_dirty"] is False
    monkeypatch.setattr(bench, "_git", fake_git("", code=128))
    assert bench.collect_origin()["git_dirty"] is None
    monkeypatch.setattr(bench, "_git", lambda *args: None)
    assert bench.collect_origin()["git_dirty"] is None


# --- context cold/warm and hash stats --------------------------------------------------------


def test_report_carries_hashing_and_round_trips(bench: ModuleType, tmp_path: Path) -> None:
    hashing = {"files_hashed": 0, "bytes_hashed": 0, "cache_hits": 7, "cache_misses": 0}
    results = {
        "context_1k_warm": bench.Measurement(
            name="context_1k_warm", median_ms=2.0, p90_ms=3.0, runs=3, hashing=hashing
        ),
        "scan_1k": bench.Measurement(name="scan_1k", median_ms=1.0, p90_ms=1.0, runs=3),
    }
    report = bench.build_report(results, bench.collect_origin())
    assert report["results"]["context_1k_warm"]["hashing"] == hashing
    assert "hashing" not in report["results"]["scan_1k"]
    path = tmp_path / "bench.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    assert bench.load_results(path) == results


def test_warm_context_reuses_every_whole_file_and_matches_cold(
    bench: ModuleType, workspace: ModuleType, tmp_path: Path
) -> None:
    root = tmp_path / "ws"
    workspace.generate_workspace(root, 50)
    bench._backdate(root)  # past the racy window, as the procedure does
    scan = scan_workspace(root, ["."])
    task = bench._task(root, bench.ROUTING_INTENT)
    cache = tmp_path / "fingerprints"
    cold = bench.context_step(task, scan, cache, enabled=False)
    bench.context_step(task, scan, cache, enabled=True)  # prime
    warm = bench.context_step(task, scan, cache, enabled=True)
    references = sum(1 for f in warm[0].files if f.tier == "reference")
    assert references > 0
    assert bench.hashing_of(cold[1])["cache_hits"] == 0
    assert cold[1].files_hashed == len(cold[0].files)
    assert bench.hashing_of(warm[1]) == {
        "files_hashed": len(warm[0].files) - references,
        "bytes_hashed": warm[1].bytes_hashed,
        "cache_hits": references,
        "cache_misses": 0,
    }
    bench.check_context_cache("50", cold, warm)  # does not raise


def test_check_context_cache_rejects_a_warm_re_read(bench: ModuleType) -> None:
    from types import SimpleNamespace

    from theforge.context.fingerprints import HashStats

    pack = SimpleNamespace(
        files=[SimpleNamespace(tier="reference")] * 2, excluded=[], used_bytes=10
    )
    cold = (pack, HashStats(files_hashed=2, bytes_hashed=10, misses=2))
    bench.check_context_cache("x", cold, (pack, HashStats(hits=2)))
    with pytest.raises(RuntimeError, match="re-read 1 whole file"):
        bench.check_context_cache(
            "x", cold, (pack, HashStats(files_hashed=1, bytes_hashed=5, hits=1, misses=1))
        )
    other = SimpleNamespace(files=pack.files, excluded=[], used_bytes=11)
    with pytest.raises(RuntimeError, match="differs from the cold pack"):
        bench.check_context_cache("x", cold, (other, HashStats(hits=2)))


# --- budgets derived from the baseline -------------------------------------------------------


def _baseline(bench: ModuleType, path: Path, medians: dict[str, float]) -> Path:
    results = {
        n: bench.Measurement(name=n, median_ms=v, p90_ms=v, runs=10) for n, v in medians.items()
    }
    origin = {**bench.collect_origin(), "git_head": "abc123"}
    path.write_text(json.dumps(bench.build_report(results, origin)), encoding="utf-8")
    return path


def test_derive_budgets_records_value_baseline_factor_and_origin(
    bench: ModuleType, tmp_path: Path
) -> None:
    baseline = _baseline(bench, tmp_path / "baseline.json", {"scan_1k": 10.0, "x": 1.2345})
    budgets = bench.derive_budgets(baseline)
    origin = f"{baseline.as_posix()} @ abc123"
    assert budgets == {
        "scan_1k": bench.Budget(budget_ms=15.0, baseline_ms=10.0, factor=1.5, origin=origin),
        "x": bench.Budget(budget_ms=1.852, baseline_ms=1.2345, factor=1.5, origin=origin),
    }
    assert bench.derive_budgets(baseline, 2.0)["scan_1k"].budget_ms == 20.0
    with pytest.raises(ValueError, match="factor"):
        bench.derive_budgets(baseline, 0.5)


def test_budgets_from_cli_writes_a_file_check_accepts(
    bench: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    baseline = _baseline(bench, tmp_path / "baseline.json", {"scan_1k": 10.0})
    out = tmp_path / "budgets.json"
    assert bench.main(["--budgets-from", str(baseline), "--out", str(out)]) == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert set(doc["scan_1k"]) == {"budget_ms", "baseline_ms", "factor", "origin"}
    assert bench.load_budgets(out) == bench.derive_budgets(baseline)
    results = _results_file(bench, tmp_path / "r.json", {"scan_1k": 15.5})
    assert bench.main(["--results", str(results), "--check", str(out)]) == 1
    assert "REGRESSION scan_1k: median 15.5 ms > budget 15.0 ms" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        bench.main(["--budgets-from", str(baseline), "--check", str(out)])
