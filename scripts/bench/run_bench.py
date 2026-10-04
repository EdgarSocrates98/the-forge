"""The Forge benchmark procedure (requirements 11.1, 11.4). Stdlib only; never part of the
offline test suite nor of the PR gate.

Usage::

    python scripts/bench/run_bench.py [--quick] [--runs N] [--out PATH] [--check BUDGETS]
    python scripts/bench/run_bench.py --results PATH --check BUDGETS

Each measurement is the median and p90 (nearest rank) of N repetitions timed with
``time.perf_counter_ns``; ``setup`` work (fresh cache directories, priming) is never timed.
Measurements: ``cli_startup`` (``python -m theforge --help`` in a subprocess),
``registry_cold``/``registry_warm`` (echo + the test fixture providers, empty then populated
cache), ``scan_1k``/``scan_10k``, ``routing_10k``, ``context_{1k,10k}_{cold,warm}``
(``build_context_pack`` with the ``balanced`` profile; until the fingerprint cache exists
``warm`` only differs from ``cold`` by an untimed priming call) and ``persist_run`` (writing
``task``, ``routing``, ``context``, ``result``, ``telemetry`` and ``receipt`` of a real echo run).

Everything is written under a temporary directory: the synthetic workspaces
(``workspace.py``, fixed seed), the provider config and every cache. ``THEFORGE_CONFIG_DIR``
and ``THEFORGE_CACHE_DIR`` point there while measuring, so the user's configuration and
caches are never read or touched. The only other output is ``--out``.

Output (stdout or ``--out``)::

    {"schema": "theforge-bench/v1",
     "origin": {"machine", "os", "python", "date", "forge_version", "git_head",
                "git_dirty"},
     "results": {name: {"median_ms", "p90_ms", "runs"}}}

``--check BUDGETS`` compares every median with ``{name: {budget_ms, baseline_ms, factor,
origin}}``, prints each regression (and each measurement without a budget as ``no budget``)
and exits 1 when any median is above its budget. ``--results PATH`` checks an existing
results file instead of measuring.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from workspace import generate_workspace

from theforge.context import WorkspaceScan, build_context_pack, scan_workspace
from theforge.contracts import (
    ContextPack,
    ExecutionReceipt,
    ExecutionResult,
    RoutingDecision,
    RunTelemetry,
    TaskSpec,
)
from theforge.contracts.canonical import utc_now
from theforge.contracts.telemetry import ProfileSnapshot
from theforge.contracts.types import BudgetProfile
from theforge.forger import AskRequest, Forger
from theforge.meta import PRODUCER, VERSION
from theforge.profiles import PROFILES
from theforge.providers.echo.provider import DOC_GLOBS
from theforge.registry import Registry
from theforge.routing import route
from theforge.routing.signals import workspace_dependencies
from theforge.runs import RunStore, new_run_id
from theforge.state import init_workspace

SCHEMA: Final = "theforge-bench/v1"
REPO: Final = Path(__file__).resolve().parents[2]
FIXTURE_PROVIDERS: Final = REPO / "tests" / "fixtures" / "providers"
MEASUREMENTS: Final = (
    "cli_startup", "registry_cold", "registry_warm", "scan_1k", "scan_10k", "routing_10k",
    "context_1k_cold", "context_1k_warm", "context_10k_cold", "context_10k_warm",
    "persist_run",
)
DEFAULT_RUNS: Final = 10
QUICK_RUNS: Final = 3
SEED: Final = 0
PROFILE: Final[BudgetProfile] = "balanced"
ROUTING_INTENT: Final = "inspect the notes and documents"
PERSISTED: Final = ("task", "routing", "context", "result", "telemetry", "receipt")


@dataclass(frozen=True, kw_only=True)
class Measurement:
    name: str
    median_ms: float
    p90_ms: float
    runs: int


@dataclass(frozen=True, kw_only=True)
class Budget:
    budget_ms: float
    baseline_ms: float
    factor: float
    origin: str


@dataclass(frozen=True, kw_only=True)
class Regression:
    name: str
    median_ms: float
    budget_ms: float


# --- measuring -------------------------------------------------------------------------------

def summarize(name: str, samples_ns: list[int]) -> Measurement:
    """Median and nearest-rank p90 of ``samples_ns``, in milliseconds (3 decimals)."""
    if not samples_ns:
        raise ValueError("at least one sample is required")
    ms = sorted(s / 1_000_000 for s in samples_ns)
    p90 = ms[math.ceil(0.9 * len(ms)) - 1]
    return Measurement(name=name, median_ms=round(statistics.median(ms), 3),
                       p90_ms=round(p90, 3), runs=len(ms))


def measure(name: str, fn: Callable[[], object], runs: int, *,
            setup: Callable[[], object] | None = None) -> Measurement:
    """Time ``fn`` ``runs`` times; ``setup`` runs before each repetition and is not timed."""
    if runs < 1:
        raise ValueError(f"runs must be >= 1, got {runs}")
    samples: list[int] = []
    for _ in range(runs):
        if setup is not None:
            setup()
        start = time.perf_counter_ns()
        fn()
        samples.append(time.perf_counter_ns() - start)
    return summarize(name, samples)


# --- output, budgets -------------------------------------------------------------------------

def _git(*args: str) -> subprocess.CompletedProcess[str] | None:
    """Run a read-only git command in the repository; ``None`` when git is unavailable."""
    try:
        return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True,
                              timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return None


def _git_head() -> str | None:
    done = _git("rev-parse", "HEAD")
    if done is None:
        return None
    head = done.stdout.strip()
    return head if done.returncode == 0 and head else None


def _git_dirty() -> bool | None:
    """Whether the worktree has uncommitted changes (``None`` when git cannot tell)."""
    done = _git("status", "--porcelain")
    if done is None or done.returncode != 0:
        return None
    return bool(done.stdout.strip())


def collect_origin() -> dict[str, str | bool | None]:
    """Where and when the measurement was taken (no host name or user data)."""
    return {
        "machine": f"{platform.machine() or 'unknown'}; {os.cpu_count() or '?'} cpus; "
                   f"{platform.processor() or 'unknown cpu'}",
        "os": platform.platform(),
        "python": f"{platform.python_implementation()} {platform.python_version()}",
        "date": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "forge_version": VERSION,
        "git_head": _git_head(),
        "git_dirty": _git_dirty(),
    }


def build_report(results: Mapping[str, Measurement],
                 origin: Mapping[str, str | bool | None]) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "origin": dict(origin),
        "results": {name: {"median_ms": m.median_ms, "p90_ms": m.p90_ms, "runs": m.runs}
                    for name, m in results.items()},
    }


def _load_object(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return data


def load_results(path: Path) -> dict[str, Measurement]:
    data = _load_object(path)
    if data.get("schema") != SCHEMA:
        raise ValueError(f"{path}: unsupported schema {data.get('schema')!r}, "
                         f"expected {SCHEMA!r}")
    return {name: Measurement(name=name, median_ms=float(r["median_ms"]),
                              p90_ms=float(r["p90_ms"]), runs=int(r["runs"]))
            for name, r in data["results"].items()}


def load_budgets(path: Path) -> dict[str, Budget]:
    return {name: Budget(budget_ms=float(b["budget_ms"]), baseline_ms=float(b["baseline_ms"]),
                         factor=float(b["factor"]), origin=str(b["origin"]))
            for name, b in _load_object(path).items()}


def compare_budgets(results: Mapping[str, Measurement],
                    budgets: Mapping[str, Budget]) -> list[Regression]:
    """Every measurement whose median is above its budget (unbudgeted ones are skipped)."""
    return [Regression(name=name, median_ms=m.median_ms, budget_ms=budgets[name].budget_ms)
            for name, m in results.items()
            if name in budgets and m.median_ms > budgets[name].budget_ms]


def missing_budgets(results: Mapping[str, Measurement],
                    budgets: Mapping[str, Budget]) -> list[str]:
    return [name for name in results if name not in budgets]


def _check(results: Mapping[str, Measurement], budgets: Mapping[str, Budget]) -> int:
    regressions = compare_budgets(results, budgets)
    for r in regressions:
        print(f"REGRESSION {r.name}: median {r.median_ms} ms > budget {r.budget_ms} ms")
    for name in missing_budgets(results, budgets):
        print(f"{name}: no budget")
    print(f"{len(regressions)} regression(s) in {len(results)} measurement(s)")
    return 1 if regressions else 0


# --- the procedure ---------------------------------------------------------------------------

@contextlib.contextmanager
def _isolated_env(config_dir: Path, cache_dir: Path) -> Iterator[None]:
    saved = {k: os.environ.get(k) for k in ("THEFORGE_CONFIG_DIR", "THEFORGE_CACHE_DIR")}
    os.environ["THEFORGE_CONFIG_DIR"] = str(config_dir)
    os.environ["THEFORGE_CACHE_DIR"] = str(cache_dir)
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _write_providers(config_dir: Path) -> None:
    script = FIXTURE_PROVIDERS / "fixture_forge.py"
    if not script.is_file():
        raise SystemExit(f"fixture providers not found under {FIXTURE_PROVIDERS}")
    lines: list[str] = []
    for pid in ("fixture-spark", "fixture-api"):
        argv = [sys.executable, str(script), str(FIXTURE_PROVIDERS / f"{pid}.json")]
        lines += ["[[providers]]", f"id = {json.dumps(pid)}", f"argv = {json.dumps(argv)}",
                  'trust = "local"', ""]
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "providers.toml").write_text("\n".join(lines), encoding="utf-8")


def _task(root: Path, intent: str) -> TaskSpec:
    return TaskSpec(producer=PRODUCER, created_at=utc_now(), id=new_run_id(), intent=intent,
                    workspace_root=str(root), budget_profile=PROFILE)


def _scan(root: Path, expected: int) -> WorkspaceScan:
    scan = scan_workspace(root, ["."])
    if len(scan.files) != expected:
        raise RuntimeError(f"scan of {root} found {len(scan.files)} files, expected {expected}")
    return scan


def _telemetry(run_id: str) -> RunTelemetry:
    p = PROFILES[PROFILE]
    snapshot = ProfileSnapshot(
        name=p.name, budget_bytes=p.budget_bytes, max_files=p.max_files, tiers=sorted(p.tiers),
        effective_tiers=[], negotiation_rounds=p.negotiation_rounds,
        max_providers=p.max_providers, fallback=p.fallback, verification=p.verification,
        execute_timeout_s=p.execute_timeout_s)
    return RunTelemetry(producer=PRODUCER, created_at=utc_now(), run_id=run_id,
                        profile=snapshot)


def _recorded_run(root: Path, registry: Registry) -> tuple[RunStore, dict[str, object]]:
    """One real echo run; returns its store and the artifacts ``persist_run`` rewrites."""
    root.mkdir(parents=True)
    init_workspace(root)
    (root / "notes.md").write_text("# Notes\n\nbenchmark run\n", encoding="utf-8")
    store = RunStore(root / ".forge")
    outcome = Forger(root, registry, store).ask(
        AskRequest(intent="echo the notes", capability="demo.echo", profile=PROFILE))
    if outcome.status != "ok":
        raise RuntimeError(f"echo run for persist_run ended {outcome.status}: {outcome.error}")
    run = outcome.run_id
    types: dict[str, type] = {"task": TaskSpec, "routing": RoutingDecision,
                              "context": ContextPack, "result": ExecutionResult,
                              "receipt": ExecutionReceipt}
    artifacts: dict[str, object] = {name: store.read_contract(run, name, cls)
                                    for name, cls in types.items()}
    artifacts["telemetry"] = _telemetry(run)  # the Forger does not write telemetry yet
    return store, artifacts


def run_procedure(tmp: Path, runs: int, log: Callable[[str], None]) -> dict[str, Measurement]:
    config_dir, cache_root = tmp / "config", tmp / "cache"
    _write_providers(config_dir)
    results: dict[str, Measurement] = {}

    def record(name: str, fn: Callable[[], object], *,
               setup: Callable[[], object] | None = None) -> None:
        results[name] = measure(name, fn, runs, setup=setup)
        log(f"{name}: median {results[name].median_ms} ms, p90 {results[name].p90_ms} ms")

    with _isolated_env(config_dir, cache_root / "env"):
        env = dict(os.environ)
        record("cli_startup", lambda: subprocess.run(
            [sys.executable, "-m", "theforge", "--help"], env=env, capture_output=True,
            check=True, timeout=60))

        cold_dirs = iter(cache_root / f"cold-{i}" for i in range(runs))
        cold: list[Path] = []
        record("registry_cold",
               lambda: Registry(None, user_dir=config_dir, cache_dir=cold[-1]).records(),
               setup=lambda: cold.append(next(cold_dirs)))
        warm = Registry(None, user_dir=config_dir, cache_dir=cache_root / "warm")
        records = warm.records()
        if any(r.manifest is None for r in records):
            raise RuntimeError("a benchmark provider failed to describe: "
                               + ", ".join(r.entry.id for r in records if r.manifest is None))
        record("registry_warm",
               lambda: Registry(None, user_dir=config_dir,
                                cache_dir=cache_root / "warm").records())

        ws: dict[str, Path] = {}
        for label, count in (("1k", 1_000), ("10k", 10_000)):
            ws[label] = tmp / f"ws-{label}"
            generate_workspace(ws[label], count, seed=SEED)

            def scan_once(root: Path = ws[label]) -> WorkspaceScan:
                return scan_workspace(root, ["."])

            record(f"scan_{label}", scan_once)
        scans = {"1k": _scan(ws["1k"], 1_000), "10k": _scan(ws["10k"], 10_000)}

        task_10k = _task(ws["10k"], ROUTING_INTENT)
        deps = workspace_dependencies(ws["10k"])
        record("routing_10k", lambda: route(task_10k, records, scans["10k"].files, deps))

        for label in ("1k", "10k"):
            task = _task(ws[label], ROUTING_INTENT)
            scan = scans[label]

            def pack(task: TaskSpec = task, scan: WorkspaceScan = scan) -> ContextPack:
                return build_context_pack(task, "echo-forge", list(DOC_GLOBS), scan)

            record(f"context_{label}_cold", pack)
            pack()  # prime: with the fingerprint cache this populates it (untimed)
            record(f"context_{label}_warm", pack)

        store, artifacts = _recorded_run(tmp / "ws-run", warm)

        def persist() -> None:
            run_id = new_run_id()
            store.create(run_id)
            for name in PERSISTED:
                store.write(run_id, name, artifacts[name])

        record("persist_run", persist)
    return {name: results[name] for name in MEASUREMENTS}


# --- command line ----------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="The Forge benchmark (baseline and budgets).")
    parser.add_argument("--quick", action="store_true",
                        help=f"{QUICK_RUNS} repetitions per measurement "
                             f"(default {DEFAULT_RUNS})")
    parser.add_argument("--runs", type=int, help="repetitions per measurement")
    parser.add_argument("--out", type=Path, help="write the results JSON here (else stdout)")
    parser.add_argument("--check", type=Path, help="budgets JSON; exit 1 on any regression")
    parser.add_argument("--results", type=Path,
                        help="check this results JSON instead of measuring (needs --check)")
    args = parser.parse_args(argv)
    if args.results is not None:
        if args.check is None:
            parser.error("--results requires --check")
        return _check(load_results(args.results), load_budgets(args.check))

    runs = args.runs or (QUICK_RUNS if args.quick else DEFAULT_RUNS)
    if runs < 1:
        parser.error("--runs must be >= 1")
    with tempfile.TemporaryDirectory(prefix="theforge-bench-",
                                     ignore_cleanup_errors=True) as tmp:
        results = run_procedure(Path(tmp), runs, lambda line: print(line, file=sys.stderr))
    text = json.dumps(build_report(results, collect_origin()), indent=2) + "\n"
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8", newline="\n")
    else:
        sys.stdout.write(text)
    return _check(results, load_budgets(args.check)) if args.check is not None else 0


if __name__ == "__main__":
    sys.exit(main())
