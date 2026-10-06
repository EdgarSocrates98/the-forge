"""Cross-forge run benchmark (Cycle 3, Wave P). Stdlib only; never part of the
offline test suite nor of the PR gate.

Usage::

    python scripts/bench/run_runs_bench.py [--quick] [--runs N] [--out PATH] [--check BUDGETS]
    python scripts/bench/run_runs_bench.py --results PATH --check BUDGETS
    python scripts/bench/run_runs_bench.py --budgets-from BASELINE [--factor F] [--out PATH]

Where ``run_bench.py`` measures the platform's inner steps on synthetic
workspaces, this benchmark measures whole *runs* through the real orchestration
surface: the fixture providers are real subprocesses speaking Forge Protocol v1
(the same argv the conformance kit certifies), so every case crosses routing,
risk assessment, context, transport, verification, persistence and receipt.
Offline and credential-free by construction — the fixtures replay declared
behaviour, which is exactly what an isolated benchmark needs; whether the *real*
SparkForge/APIForge behave the same is covered by the opt-in real-provider suite
(docs/real-providers.md), a different measurement.

Cases (every one asserts its expected status — a wrong outcome fails the run):

    single_spark       ask routed to fixture-spark (verifier present)
    single_api         ask routed to fixture-api
    pipeline           plan: spark node -> api node (cross-provider handoff)
    ambiguous          ask tied between fixture-spark and fixture-spark-b
    high_risk          ask pinned to a destructive capability: policy refuses
    semantic_fallback  the ambiguous ask, resolved by fixture-resolver (Wave K)
    parallel           plan: two independent nodes + one dependent, real threads
    debate             plan: two proposers + referee, DecisionRecord persisted

Per case the report records the median and p90 wall time of the run call
(``time.perf_counter_ns``; an untimed priming repetition warms the registry
cache) plus the run metrics the wave asks for, read back from the persisted
artifacts of the run and its children:

    context_bytes       ``context_bytes`` counter of every run of the case
    provider_calls      ``providers_executed`` counters (plan root + nodes)
    semantic_calls      planner + resolver calls this run
    handoff_bytes       bytes of every persisted ``handoff`` artifact
    verification_calls  ``verification`` spans of every run of the case
    status              the outcome status (asserted equal to the expectation)

Everything lives under a temporary directory: workspaces, provider config and
caches, ``.forge`` state. ``THEFORGE_CONFIG_DIR``/``THEFORGE_CACHE_DIR`` point
there while measuring. The only other output is ``--out``.

Output (stdout or ``--out``)::

    {"schema": "theforge-bench-runs/v1",
     "origin": {...},                      # same shape as theforge-bench/v1
     "cases": {name: {"median_ms", "p90_ms", "runs", "status", "expect",
                      "nodes", "metrics": {context_bytes, provider_calls,
                      semantic_calls, handoff_bytes, verification_calls}}}}

``--check``/``--budgets-from`` work exactly like run_bench's: budgets compare
the case medians.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import run_bench
from run_bench import (
    Measurement,
    _isolated_env,
    budgets_document,
    collect_origin,
    compare_budgets,
    load_budgets,
    measure,
    missing_budgets,
)

from theforge.contracts.types import BudgetProfile
from theforge.forger import (
    AskOutcome,
    AskRequest,
    Forger,
    PlanCommand,
    PlanExecutor,
    PlanOutcome,
)
from theforge.registry import Registry
from theforge.runs import RunStore
from theforge.state import init_workspace

SCHEMA: Final = "theforge-bench-runs/v1"
FIXTURES: Final = run_bench.FIXTURE_PROVIDERS
FIXTURE_SCRIPT: Final = FIXTURES / "fixture_forge.py"
DEFAULT_RUNS: Final = 5
QUICK_RUNS: Final = 2

METRIC_KEYS: Final = ("context_bytes", "provider_calls", "semantic_calls",
                      "handoff_bytes", "verification_calls")

# Deterministic per-case workspaces: the smallest content whose signals route
# the intent the way the case needs (file globs and dependencies, like the
# fixtures' declared signals).
SPARK_WS: Final = {
    "jobs/orders_glue_job.py": "df = spark.read.parquet('s3://b/orders')\n",
    "requirements.txt": "pyspark==3.5.1\n",
}
API_WS: Final = {
    "api/openapi.yaml": "openapi: 3.0.0\ninfo:\n  title: Orders\n"
                        "  version: 1.0.0\npaths: {}\n",
}
MIXED_WS: Final = {**SPARK_WS, **API_WS}


@dataclass(frozen=True, kw_only=True)
class Case:
    """One benchmark scenario: provider manifests, workspace content and the run."""
    name: str
    providers: tuple[str, ...]  # manifest file stems under tests/fixtures/providers
    workspace: Mapping[str, str]
    intent: str = ""
    plan: tuple[str, list[dict[str, Any]]] | None = None  # (pattern, nodes)
    capability: str | None = None
    profile: BudgetProfile = "balanced"
    expect: str = "ok"


@dataclass(frozen=True, kw_only=True)
class CaseResult:
    name: str
    median_ms: float
    p90_ms: float
    runs: int
    status: str  # last repetition's outcome (every repetition asserts it)
    expect: str
    nodes: int  # run dirs aggregated: 1 for ask, 1 + executed nodes for plans
    metrics: Mapping[str, int]


def _node(nid: str, provider: str, capability: str, action: str,
          *deps: str, role: str = "standalone") -> dict[str, Any]:
    """A plan-file node (the same shape the plan docs and tests use)."""
    node: dict[str, Any] = {"id": nid, "role": role, "provider": provider,
                            "capability": capability, "action": action}
    if deps:
        node["depends_on"] = [{"node": d, "epistemic": "explicit",
                               "evidence": "plan file"} for d in deps]
        node["inputs"] = list(deps)
    return node


SPARK_INTENT: Final = "diagnose the slow spark glue job"
API_INTENT: Final = "review the api contract"

CASES: Final[tuple[Case, ...]] = (
    Case(name="single_spark", providers=("fixture-spark", "fixture-verifier"),
         workspace=SPARK_WS, intent=SPARK_INTENT),
    Case(name="single_api", providers=("fixture-api", "fixture-verifier"),
         workspace=API_WS, intent=API_INTENT),
    Case(name="pipeline", providers=("fixture-spark-plan", "fixture-api-plan",
                                     "fixture-verifier"),
         workspace=MIXED_WS, intent="spark findings feeding a contract review",
         plan=("pipeline", [
             _node("n1", "fixture-spark", "spark.performance", "diagnose"),
             _node("n2", "fixture-api", "api.contract", "review", "n1")]),
         profile="max"),
    Case(name="ambiguous", providers=("fixture-spark", "fixture-spark-b"),
         workspace=SPARK_WS, intent=SPARK_INTENT, expect="ambiguous"),
    Case(name="high_risk", providers=("fixture-risky",), workspace=MIXED_WS,
         intent="drop the staging datasets", capability="data.destroy",
         expect="refused"),
    Case(name="semantic_fallback",
         providers=("fixture-spark", "fixture-spark-b", "fixture-resolver"),
         workspace=SPARK_WS, intent=SPARK_INTENT),
    Case(name="parallel", providers=("fixture-spark-plan", "fixture-api-plan",
                                     "fixture-verifier"),
         workspace=MIXED_WS, intent="spark and api checks, then a join review",
         plan=("parallel", [
             _node("n1", "fixture-spark", "spark.performance", "diagnose"),
             _node("n2", "fixture-api", "api.contract", "review"),
             _node("top", "fixture-api", "api.contract", "lint", "n1", "n2")]),
         profile="max"),
    Case(name="debate", providers=("fixture-spark-debate", "fixture-api-debate",
                                   "fixture-referee"),
         workspace=MIXED_WS,
         intent="should this transformation live in the Spark pipeline or the API?",
         plan=("debate", [
             _node("n1", "fixture-spark", "spark.performance", "diagnose",
                   role="proposer"),
             _node("n2", "fixture-api", "api.contract", "review", role="proposer"),
             _node("ref", "fixture-referee", "judge.decide", "decide", "n1", "n2",
                   role="referee")]),
         profile="max"),
)


# --- setup -----------------------------------------------------------------------------------

def _write_providers(config_dir: Path, stems: tuple[str, ...]) -> None:
    """``providers.toml`` for the case's manifests (id read from each manifest)."""
    lines: list[str] = []
    for stem in stems:
        manifest = FIXTURES / f"{stem}.json"
        pid = json.loads(manifest.read_text(encoding="utf-8"))["id"]
        argv = [sys.executable, str(FIXTURE_SCRIPT), str(manifest)]
        lines += ["[[providers]]", f"id = {json.dumps(pid)}",
                  f"argv = {json.dumps(argv)}", 'trust = "local"', ""]
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "providers.toml").write_text("\n".join(lines), encoding="utf-8")


def _write_workspace(root: Path, files: Mapping[str, str]) -> None:
    init_workspace(root)
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")


def _write_plan(path: Path, pattern: str, nodes: list[dict[str, Any]],
                profile: str) -> Path:
    path.write_text(json.dumps({"task_id": "bench", "pattern": pattern,
                                "source": "file", "profile": profile,
                                "nodes": nodes}), encoding="utf-8")
    return path


# --- run metrics (read back from the persisted artifacts) -------------------------------------

def _counter(telemetry: Mapping[str, Any], name: str) -> int:
    metric = telemetry.get(name)
    value = metric.get("value") if isinstance(metric, dict) else None
    return int(value) if isinstance(value, (int, float)) else 0


def collect_metrics(store: RunStore, run_id: str) -> tuple[dict[str, int], int]:
    """Aggregate the run metrics of a run and its plan-node children.

    Every number is read from what the run persisted — the same artifacts
    ``explain`` and ``trace`` consume — never from the live objects. Returns
    (metrics, number of run dirs aggregated).
    """
    run_ids = [run_id]
    plan_result = store.read_optional(run_id, "plan-result")
    if plan_result is not None:
        run_ids.extend(str(node["run_id"]) for node in plan_result.get("nodes") or []
                       if node.get("run_id"))
    metrics = dict.fromkeys(METRIC_KEYS, 0)
    for rid in run_ids:
        telemetry = store.read_optional(rid, "telemetry")
        if telemetry is not None:
            metrics["context_bytes"] += _counter(telemetry, "context_bytes")
            metrics["provider_calls"] += _counter(telemetry, "providers_executed")
            metrics["semantic_calls"] += (
                _counter(telemetry, "semantic_planner_calls")
                + _counter(telemetry, "semantic_resolver_calls"))
            metrics["verification_calls"] += sum(
                1 for span in telemetry.get("spans") or []
                if isinstance(span, dict) and span.get("name") == "verification")
        handoff = store.run_dir(rid) / "handoff.json"
        if handoff.is_file():
            metrics["handoff_bytes"] += handoff.stat().st_size
    return metrics, len(run_ids)


# --- the procedure ---------------------------------------------------------------------------

def run_case(case: Case, tmp: Path, runs: int, log: Callable[[str], None]) -> CaseResult:
    """Prime once, then time ``runs`` repetitions; metrics of the last repetition.

    Every repetition gets a fresh workspace (setup, untimed — the run_bench
    discipline): without it, the project-intel and provider-performance history
    of repetition N-1 would feed the routing of repetition N, so e.g. an
    ambiguous routing could be resolved by history instead of the resolver and
    the metrics would vary between reps. The registry describe cache lives
    outside the workspace and stays warm — that is the steady state.
    """
    root = tmp / case.name / "ws"
    config_dir = tmp / case.name / "config"
    cache_dir = tmp / case.name / "cache"
    _write_providers(config_dir, case.providers)
    plan_file = (_write_plan(tmp / case.name / "plan.json", *case.plan,
                             profile=case.profile)
                 if case.plan is not None else None)

    def setup() -> None:
        if root.exists():
            shutil.rmtree(root)
        _write_workspace(root, case.workspace)

    def once() -> tuple[str, dict[str, int], int]:
        forge = root / ".forge"
        store = RunStore(forge)
        forger = Forger(root, Registry(forge), store)
        outcome: PlanOutcome | AskOutcome
        if plan_file is not None:
            outcome = PlanExecutor(forger).run(PlanCommand(
                intent=case.intent, profile=case.profile, plan_file=plan_file,
                execute=True))
        else:
            outcome = forger.ask(AskRequest(
                intent=case.intent, capability=case.capability,
                profile=case.profile))
        status, run_id, error = outcome.status, outcome.run_id, outcome.error
        if status != case.expect:
            raise RuntimeError(
                f"{case.name}: outcome {status!r}, expected {case.expect!r}"
                + (f" ({error.code}: {error.detail})" if error else ""))
        metrics, nodes = collect_metrics(store, run_id)
        return status, metrics, nodes

    with _isolated_env(config_dir, cache_dir):
        setup()
        once()  # untimed priming: warms the registry describe cache, validates status
        last: dict[str, tuple[str, dict[str, int], int]] = {}
        timing = measure(case.name, lambda: last.update(rep=once()), runs,
                         setup=setup)
    status, metrics, nodes = last["rep"]
    result = CaseResult(name=case.name, median_ms=timing.median_ms,
                        p90_ms=timing.p90_ms, runs=timing.runs, status=status,
                        expect=case.expect, nodes=nodes, metrics=metrics)
    log(f"{case.name}: median {result.median_ms} ms, status {status}, "
        f"metrics {dict(metrics)}")
    return result


def run_procedure(tmp: Path, runs: int,
                  log: Callable[[str], None]) -> dict[str, CaseResult]:
    return {case.name: run_case(case, tmp, runs, log) for case in CASES}


# --- output, budgets -------------------------------------------------------------------------

def build_report(results: Mapping[str, CaseResult],
                 origin: Mapping[str, str | bool | None]) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "origin": dict(origin),
        "cases": {
            name: {
                "median_ms": r.median_ms, "p90_ms": r.p90_ms, "runs": r.runs,
                "status": r.status, "expect": r.expect, "nodes": r.nodes,
                "metrics": dict(r.metrics),
            }
            for name, r in results.items()
        },
    }


def _load_report(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a JSON object")
    if data.get("schema") != SCHEMA:
        raise ValueError(f"{path}: unsupported schema {data.get('schema')!r}, "
                         f"expected {SCHEMA!r}")
    return data


def load_results(path: Path) -> dict[str, Measurement]:
    """Case medians as run_bench ``Measurement`` — budgets compare wall time."""
    return {name: Measurement(name=name, median_ms=float(r["median_ms"]),
                              p90_ms=float(r["p90_ms"]), runs=int(r["runs"]))
            for name, r in _load_report(path)["cases"].items()}


def derive_runs_budgets(baseline: Path, factor: float) -> dict[str, run_bench.Budget]:
    """``derive_budgets`` for this schema (run_bench's loader rejects it)."""
    if not factor >= 1.0:
        raise ValueError(f"factor must be >= 1.0, got {factor}")
    head = _load_report(baseline).get("origin", {}).get("git_head") or "unknown HEAD"
    origin = f"{baseline.as_posix()} @ {head}"
    return {name: run_bench.Budget(budget_ms=round(m.median_ms * factor, 3),
                                   baseline_ms=m.median_ms, factor=factor,
                                   origin=origin)
            for name, m in load_results(baseline).items()}


def _as_measurements(results: Mapping[str, CaseResult]) -> dict[str, Measurement]:
    return {name: Measurement(name=name, median_ms=r.median_ms, p90_ms=r.p90_ms,
                              runs=r.runs)
            for name, r in results.items()}


def _check(results: Mapping[str, Measurement],
           budgets: Mapping[str, run_bench.Budget]) -> int:
    regressions = compare_budgets(results, budgets)
    for r in regressions:
        print(f"REGRESSION {r.name}: median {r.median_ms} ms > budget {r.budget_ms} ms")
    for name in missing_budgets(results, budgets):
        print(f"{name}: no budget")
    print(f"{len(regressions)} regression(s) in {len(results)} case(s)")
    return 1 if regressions else 0


def _emit(document: Mapping[str, Any], out: Path | None) -> None:
    text = json.dumps(document, indent=2) + "\n"
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8", newline="\n")
    else:
        sys.stdout.write(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="The Forge cross-forge run benchmark (whole runs, real protocol).")
    parser.add_argument("--quick", action="store_true",
                        help=f"{QUICK_RUNS} repetitions per case "
                             f"(default {DEFAULT_RUNS})")
    parser.add_argument("--runs", type=int, help="repetitions per case")
    parser.add_argument("--out", type=Path, help="write the results JSON here (else stdout)")
    parser.add_argument("--check", type=Path, help="budgets JSON; exit 1 on any regression")
    parser.add_argument("--results", type=Path,
                        help="check this results JSON instead of measuring (needs --check)")
    parser.add_argument("--budgets-from", type=Path, metavar="BASELINE",
                        help="write budgets derived from this results JSON instead of measuring")
    parser.add_argument("--factor", type=float, default=run_bench.DEFAULT_FACTOR,
                        help=f"budget = factor x baseline median "
                             f"(default {run_bench.DEFAULT_FACTOR})")
    args = parser.parse_args(argv)
    if args.budgets_from is not None:
        if args.results is not None or args.check is not None:
            parser.error("--budgets-from cannot be combined with --results or --check")
        try:
            budgets = derive_runs_budgets(args.budgets_from, args.factor)
        except ValueError as exc:
            parser.error(str(exc))
        _emit(budgets_document(budgets), args.out)
        return 0
    if args.results is not None:
        if args.check is None:
            parser.error("--results requires --check")
        return _check(load_results(args.results), load_budgets(args.check))

    runs = args.runs or (QUICK_RUNS if args.quick else DEFAULT_RUNS)
    if runs < 1:
        parser.error("--runs must be >= 1")
    start = time.perf_counter_ns()
    with tempfile.TemporaryDirectory(prefix="theforge-runs-bench-",
                                     ignore_cleanup_errors=True) as tmp:
        results = run_procedure(Path(tmp), runs,
                                lambda line: print(line, file=sys.stderr))
    elapsed = (time.perf_counter_ns() - start) / 1_000_000
    print(f"8 cases, {runs} timed repetition(s) each, {elapsed / 1000:.1f}s total",
          file=sys.stderr)
    _emit(build_report(results, collect_origin()), args.out)
    return (_check(_as_measurements(results), load_budgets(args.check))
            if args.check is not None else 0)


if __name__ == "__main__":
    sys.exit(main())
