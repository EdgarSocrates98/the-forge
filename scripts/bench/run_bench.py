"""The Forge benchmark procedure (requirements 11.1, 11.4). Stdlib only; never part of the
offline test suite nor of the PR gate.

Usage::

    python scripts/bench/run_bench.py [--quick] [--runs N] [--out PATH] [--check BUDGETS]
    python scripts/bench/run_bench.py --results PATH --check BUDGETS
    python scripts/bench/run_bench.py --budgets-from BASELINE [--factor F] [--out PATH]

Each measurement is the median and p90 (nearest rank) of N repetitions timed with
``time.perf_counter_ns``; ``setup`` work (fresh cache directories, priming) is never timed.
Measurements: ``cli_startup`` (``python -m theforge --help`` in a subprocess),
``registry_cold``/``registry_warm`` (echo + the test fixture providers, empty then populated
cache), ``scan_1k``/``scan_10k``, ``routing_10k``, ``context_{1k,10k}_{cold,warm}`` and
``persist_run`` (writing ``task``, ``routing``, ``context``, ``result``, ``telemetry`` and
``receipt`` of a real echo run).

``context_*`` times the context step of a run without git (the synthetic workspaces are not
repositories): open a ``FingerprintStore``, ``build_context_pack`` with the ``balanced``
profile, save the store. ``cold`` has the fingerprint cache disabled (every selected file is
read and hashed); ``warm`` reuses a cache populated by an untimed priming run. Their output
carries ``hashing`` (``files_hashed``, ``bytes_hashed``, ``cache_hits``, ``cache_misses`` of
one repetition), and the procedure fails unless the warm pack re-read no whole file (no cache
miss, one hit per ``reference`` item) and equals the cold pack. Generated files are back-dated
past the cache's racy window so the priming run can record them.

Everything is written under a temporary directory: the synthetic workspaces
(``workspace.py``, fixed seed), the provider config and every cache. ``THEFORGE_CONFIG_DIR``
and ``THEFORGE_CACHE_DIR`` point there while measuring, so the user's configuration and
caches are never read or touched. The only other output is ``--out``.

Output (stdout or ``--out``)::

    {"schema": "theforge-bench/v1",
     "origin": {"machine", "os", "python", "date", "forge_version", "git_head",
                "git_dirty"},
     "results": {name: {"median_ms", "p90_ms", "runs", "hashing"?}}}

``--check BUDGETS`` compares every median with ``{name: {budget_ms, baseline_ms, factor,
origin}}``, prints each regression (and each measurement without a budget as ``no budget``)
and exits 1 when any median is above its budget. ``--results PATH`` checks an existing
results file instead of measuring. ``--budgets-from BASELINE`` derives that budgets file from
a results file: ``budget_ms = factor x median`` (``--factor``, default 1.5), recording the
baseline median, the factor and the baseline's origin (file and HEAD).
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
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from workspace import generate_workspace

from theforge.capability_graph import build_capability_graph
from theforge.context import WorkspaceScan, build_context_pack, scan_workspace
from theforge.context.fingerprints import RACY_WINDOW_NS, FingerprintStore, HashStats
from theforge.contracts import (
    ContextPack,
    ExecutionReceipt,
    ExecutionResult,
    RoutingDecision,
    RunTelemetry,
    TaskSpec,
)
from theforge.contracts.base import to_dict
from theforge.contracts.canonical import sha256_of, utc_now
from theforge.contracts.memory import EngineeringMemoryEntry
from theforge.contracts.observation import ExecutionObservation
from theforge.contracts.plan import ExecutionPlan, PlanDependency, PlanNode
from theforge.contracts.remote import RemoteExecutionReceipt
from theforge.contracts.targets import ExecutionTarget, TargetRequirement
from theforge.contracts.telemetry import ProfileSnapshot
from theforge.contracts.types import BudgetProfile
from theforge.explain import build_explain_report, verify_run_hashes
from theforge.forger import AskRequest, Forger
from theforge.intel import refresh_intel
from theforge.memory import MemoryQuery, memory_pack, record_entry
from theforge.meta import PRODUCER, VERSION
from theforge.observations import record_observation
from theforge.planning.validate import check_plan
from theforge.profiles import PROFILES
from theforge.providers.echo.provider import DOC_GLOBS
from theforge.registry import Registry
from theforge.remote import RemotePolicy, accept_receipt, build_request
from theforge.routing import route
from theforge.routing.signals import workspace_dependencies
from theforge.runs import RunStore, new_run_id
from theforge.simulation import simulate_plan
from theforge.state import init_workspace
from theforge.targets import builtin_local, negotiate_target
from theforge.workspace.describe import describe_workspace

SCHEMA: Final = "theforge-bench/v1"
REPO: Final = Path(__file__).resolve().parents[2]
FIXTURE_PROVIDERS: Final = REPO / "tests" / "fixtures" / "providers"
MEASUREMENTS: Final = (
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
    # Cycle 3 surfaces (Wave W): the capability graph build, the warm incremental
    # refresh that feeds it, plan validation, replay verification and explain.
    "graph_build",
    "graph_refresh_warm",
    "plan_validate",
    "replay_verify",
    "explain_build",
    # Cycle 5.1 hot paths (§39): memory retrieval, plan simulation, target
    # negotiation, remote receipt binding, observation write.
    "memory_pack",
    "plan_simulate",
    "target_negotiate",
    "receipt_validate",
    "observation_write",
)
DEFAULT_RUNS: Final = 10
QUICK_RUNS: Final = 3
SEED: Final = 0
PROFILE: Final[BudgetProfile] = "balanced"
ROUTING_INTENT: Final = "inspect the notes and documents"
PERSISTED: Final = ("task", "routing", "context", "result", "telemetry", "receipt")
DEFAULT_FACTOR: Final = 1.5
HASHING_KEYS: Final = ("files_hashed", "bytes_hashed", "cache_hits", "cache_misses")


@dataclass(frozen=True, kw_only=True)
class Measurement:
    name: str
    median_ms: float
    p90_ms: float
    runs: int
    hashing: Mapping[str, int] | None = None  # context_* only: hash stats of one repetition


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
    return Measurement(
        name=name, median_ms=round(statistics.median(ms), 3), p90_ms=round(p90, 3), runs=len(ms)
    )


def measure(
    name: str, fn: Callable[[], object], runs: int, *, setup: Callable[[], object] | None = None
) -> Measurement:
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
        return subprocess.run(
            ["git", *args], cwd=REPO, capture_output=True, text=True, timeout=10, check=False
        )
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


def _result_entry(m: Measurement) -> dict[str, Any]:
    entry: dict[str, Any] = {"median_ms": m.median_ms, "p90_ms": m.p90_ms, "runs": m.runs}
    if m.hashing is not None:
        entry["hashing"] = dict(m.hashing)
    return entry


def build_report(
    results: Mapping[str, Measurement], origin: Mapping[str, str | bool | None]
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "origin": dict(origin),
        "results": {name: _result_entry(m) for name, m in results.items()},
    }


def _load_object(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return data


def _load_report(path: Path) -> dict[str, Any]:
    data = _load_object(path)
    if data.get("schema") != SCHEMA:
        raise ValueError(f"{path}: unsupported schema {data.get('schema')!r}, expected {SCHEMA!r}")
    return data


def load_results(path: Path) -> dict[str, Measurement]:
    return {
        name: Measurement(
            name=name,
            median_ms=float(r["median_ms"]),
            p90_ms=float(r["p90_ms"]),
            runs=int(r["runs"]),
            hashing=(
                {k: int(v) for k, v in r["hashing"].items()}
                if r.get("hashing") is not None
                else None
            ),
        )
        for name, r in _load_report(path)["results"].items()
    }


def derive_budgets(baseline: Path, factor: float = DEFAULT_FACTOR) -> dict[str, Budget]:
    """One budget per baseline measurement: ``factor`` x its median, with the origin."""
    if not factor >= 1.0:
        raise ValueError(f"factor must be >= 1.0, got {factor}")
    head = _load_report(baseline).get("origin", {}).get("git_head") or "unknown HEAD"
    origin = f"{baseline.as_posix()} @ {head}"
    return {
        name: Budget(
            budget_ms=round(m.median_ms * factor, 3),
            baseline_ms=m.median_ms,
            factor=factor,
            origin=origin,
        )
        for name, m in load_results(baseline).items()
    }


def budgets_document(budgets: Mapping[str, Budget]) -> dict[str, Any]:
    return {
        name: {
            "budget_ms": b.budget_ms,
            "baseline_ms": b.baseline_ms,
            "factor": b.factor,
            "origin": b.origin,
        }
        for name, b in budgets.items()
    }


def load_budgets(path: Path) -> dict[str, Budget]:
    return {
        name: Budget(
            budget_ms=float(b["budget_ms"]),
            baseline_ms=float(b["baseline_ms"]),
            factor=float(b["factor"]),
            origin=str(b["origin"]),
        )
        for name, b in _load_object(path).items()
    }


def compare_budgets(
    results: Mapping[str, Measurement], budgets: Mapping[str, Budget]
) -> list[Regression]:
    """Every measurement whose median is above its budget (unbudgeted ones are skipped)."""
    return [
        Regression(name=name, median_ms=m.median_ms, budget_ms=budgets[name].budget_ms)
        for name, m in results.items()
        if name in budgets and m.median_ms > budgets[name].budget_ms
    ]


def missing_budgets(results: Mapping[str, Measurement], budgets: Mapping[str, Budget]) -> list[str]:
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
        lines += [
            "[[providers]]",
            f"id = {json.dumps(pid)}",
            f"argv = {json.dumps(argv)}",
            'trust = "local"',
            "",
        ]
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "providers.toml").write_text("\n".join(lines), encoding="utf-8")


def _task(root: Path, intent: str) -> TaskSpec:
    return TaskSpec(
        producer=PRODUCER,
        created_at=utc_now(),
        id=new_run_id(),
        intent=intent,
        workspace_root=str(root),
        budget_profile=PROFILE,
    )


def _scan(root: Path, expected: int) -> WorkspaceScan:
    scan = scan_workspace(root, ["."])
    if len(scan.files) != expected:
        raise RuntimeError(f"scan of {root} found {len(scan.files)} files, expected {expected}")
    return scan


def _telemetry(run_id: str) -> RunTelemetry:
    p = PROFILES[PROFILE]
    snapshot = ProfileSnapshot(
        name=p.name,
        budget_bytes=p.budget_bytes,
        max_files=p.max_files,
        tiers=sorted(p.tiers),
        effective_tiers=[],
        negotiation_rounds=p.negotiation_rounds,
        max_providers=p.max_providers,
        fallback=p.fallback,
        verification=p.verification,
        execute_timeout_s=p.execute_timeout_s,
    )
    return RunTelemetry(producer=PRODUCER, created_at=utc_now(), run_id=run_id, profile=snapshot)


def _recorded_run(
    root: Path,
    registry: Registry,
) -> tuple[RunStore, str, dict[str, object]]:
    """One real echo run; returns its store, run id and the artifacts ``persist_run`` rewrites."""
    root.mkdir(parents=True)
    init_workspace(root)
    (root / "notes.md").write_text("# Notes\n\nbenchmark run\n", encoding="utf-8")
    store = RunStore(root / ".forge")
    outcome = Forger(root, registry, store).ask(
        AskRequest(intent="echo the notes", capability="demo.echo", profile=PROFILE)
    )
    if outcome.status != "ok":
        raise RuntimeError(f"echo run for persist_run ended {outcome.status}: {outcome.error}")
    run = outcome.run_id
    types: dict[str, type] = {
        "task": TaskSpec,
        "routing": RoutingDecision,
        "context": ContextPack,
        "result": ExecutionResult,
        "receipt": ExecutionReceipt,
    }
    artifacts: dict[str, object] = {
        name: store.read_contract(run, name, cls) for name, cls in types.items()
    }
    artifacts["telemetry"] = _telemetry(run)  # the Forger does not write telemetry yet
    return store, run, artifacts


def _backdate(root: Path) -> None:
    """Move every file's mtime past the fingerprint cache's racy window (untimed setup)."""
    past = time.time_ns() - 10 * RACY_WINDOW_NS
    for path in root.rglob("*"):
        if path.is_file():
            os.utime(path, ns=(past, past))


def context_step(
    task: TaskSpec, scan: WorkspaceScan, cache_dir: Path, *, enabled: bool
) -> tuple[ContextPack, HashStats]:
    """The context step of a run without git: open the store, build the pack, save."""
    store = FingerprintStore(scan.root, cache_dir=cache_dir, enabled=enabled)
    pack = build_context_pack(task, "echo-forge", list(DOC_GLOBS), scan, fingerprints=store)
    store.save()
    if store.warnings:
        raise RuntimeError("fingerprint cache: " + "; ".join(store.warnings))
    return pack, store.stats


def hashing_of(stats: HashStats) -> dict[str, int]:
    return {
        "files_hashed": stats.files_hashed,
        "bytes_hashed": stats.bytes_hashed,
        "cache_hits": stats.hits,
        "cache_misses": stats.misses,
    }


def check_context_cache(
    label: str, cold: tuple[ContextPack, HashStats], warm: tuple[ContextPack, HashStats]
) -> None:
    """The warm pack equals the cold one and re-read no whole file (11.x, 5.1)."""
    (cold_pack, cold_stats), (warm_pack, warm_stats) = cold, warm
    references = sum(1 for f in warm_pack.files if f.tier == "reference")
    problems: list[str] = []
    if cold_stats.hits:
        problems.append(f"cold run reused {cold_stats.hits} fingerprint(s)")
    if references == 0:
        problems.append("the pack has no reference item: nothing to reuse")
    if warm_stats.misses:
        problems.append(f"warm run re-read {warm_stats.misses} whole file(s)")
    if warm_stats.hits != references:
        problems.append(f"warm run hit {warm_stats.hits} for {references} reference item(s)")
    excerpts = len(warm_pack.files) - references  # line ranges are never cached
    if warm_stats.files_hashed != excerpts:
        problems.append(
            f"warm run hashed {warm_stats.files_hashed} file(s) for {excerpts} excerpt(s)"
        )
    if (warm_pack.files, warm_pack.excluded, warm_pack.used_bytes) != (
        cold_pack.files,
        cold_pack.excluded,
        cold_pack.used_bytes,
    ):
        problems.append("warm pack differs from the cold pack")
    if problems:
        raise RuntimeError(f"context_{label}: " + "; ".join(problems))


def run_procedure(tmp: Path, runs: int, log: Callable[[str], None]) -> dict[str, Measurement]:
    config_dir, cache_root = tmp / "config", tmp / "cache"
    _write_providers(config_dir)
    results: dict[str, Measurement] = {}

    def record(
        name: str, fn: Callable[[], object], *, setup: Callable[[], object] | None = None
    ) -> None:
        results[name] = measure(name, fn, runs, setup=setup)
        log(f"{name}: median {results[name].median_ms} ms, p90 {results[name].p90_ms} ms")

    with _isolated_env(config_dir, cache_root / "env"):
        env = dict(os.environ)
        record(
            "cli_startup",
            lambda: subprocess.run(
                [sys.executable, "-m", "theforge", "--help"],
                env=env,
                capture_output=True,
                check=True,
                timeout=60,
            ),
        )

        cold_dirs = iter(cache_root / f"cold-{i}" for i in range(runs))
        cold: list[Path] = []
        record(
            "registry_cold",
            lambda: Registry(None, user_dir=config_dir, cache_dir=cold[-1]).records(),
            setup=lambda: cold.append(next(cold_dirs)),
        )
        warm = Registry(None, user_dir=config_dir, cache_dir=cache_root / "warm")
        records = warm.records()
        if any(r.manifest is None for r in records):
            raise RuntimeError(
                "a benchmark provider failed to describe: "
                + ", ".join(r.entry.id for r in records if r.manifest is None)
            )
        record(
            "registry_warm",
            lambda: Registry(None, user_dir=config_dir, cache_dir=cache_root / "warm").records(),
        )

        ws: dict[str, Path] = {}
        for label, count in (("1k", 1_000), ("10k", 10_000)):
            ws[label] = tmp / f"ws-{label}"
            generate_workspace(ws[label], count, seed=SEED)
            _backdate(ws[label])

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
            fp_dir = tmp / f"fingerprints-{label}"  # outside the workspace, per root
            last: dict[str, tuple[ContextPack, HashStats]] = {}
            for mode, enabled in (("cold", False), ("warm", True)):
                if enabled:
                    context_step(task, scan, fp_dir, enabled=True)  # prime the cache, untimed

                def step(
                    task: TaskSpec = task,
                    scan: WorkspaceScan = scan,
                    fp_dir: Path = fp_dir,
                    enabled: bool = enabled,
                    mode: str = mode,
                    last: dict[str, tuple[ContextPack, HashStats]] = last,
                ) -> None:
                    last[mode] = context_step(task, scan, fp_dir, enabled=enabled)

                name = f"context_{label}_{mode}"
                record(name, step)
                results[name] = replace(results[name], hashing=hashing_of(last[mode][1]))
                log(f"{name}: {results[name].hashing}")
            check_context_cache(label, last["cold"], last["warm"])

        store, run_id, artifacts = _recorded_run(tmp / "ws-run", warm)

        def persist() -> None:
            run_id = new_run_id()
            store.create(run_id)
            for name in PERSISTED:
                store.write(run_id, name, artifacts[name])

        record("persist_run", persist)

        # --- Cycle 3 surfaces (Wave W) ---------------------------------------------------
        # The capability graph build over the big workspace's descriptor, the warm
        # incremental refresh that feeds it (intel snapshot reuse), plan validation,
        # replay verification and explain — all deterministic paths; the semantic
        # planner is measured separately by run_runs_bench.py (semantic_calls).
        descriptor = describe_workspace(ws["10k"], list(records), scans["10k"])
        record("graph_build", lambda: build_capability_graph(list(records), descriptor))

        intel_root = tmp / "ws-intel"
        generate_workspace(intel_root, 1_000, seed=SEED)
        init_workspace(intel_root)
        intel_scan = _scan(intel_root, 1_000)
        refresh_intel(intel_root, intel_scan, list(records))  # prime the snapshot, untimed
        record("graph_refresh_warm", lambda: refresh_intel(intel_root, intel_scan, list(records)))

        plan = ExecutionPlan(
            producer=PRODUCER,
            created_at=utc_now(),
            status="validated",
            plan_run="bench-plan",
            task_id="bench-task",
            pattern="pipeline",
            source="file",
            profile="max",
            nodes=[
                PlanNode(
                    id=f"n{i}",
                    role="standalone",
                    provider="echo-forge",
                    capability="demo.echo",
                    action="echo",
                    depends_on=[
                        PlanDependency(node=f"n{i - 1}", epistemic="explicit", evidence="bench")
                    ]
                    if i
                    else [],
                )
                for i in range(32)
            ],
        )
        record(
            "plan_validate",
            lambda: check_plan(plan, {r.entry.id: r for r in records}, PROFILES["max"]),
        )

        record("replay_verify", lambda: verify_run_hashes(store, run_id))
        record("explain_build", lambda: build_explain_report(store, run_id))

        # --- Cycle 5 surfaces (5.1 §39) --------------------------------------------------
        # Memory retrieval over a seeded store (seeding is untimed setup; the
        # corpus is fixed: 240 entries, queries scoped by capability+family).
        mem_root = tmp / "ws-memory"
        mem_root.mkdir()
        init_workspace(mem_root)

        def _mem_entry(i: int) -> EngineeringMemoryEntry:
            stub = EngineeringMemoryEntry(
                producer=PRODUCER,
                created_at=utc_now(),
                id="0" * 64,
                kind="failure" if i % 3 else "resolution",
                scope="project",
                workspace=str(mem_root),
                subject=f"bench entry {i:04d}",
                claim=f"provider bench-{i % 4} observation {i:04d}",
                epistemic="observed",
                provider=f"bench-{i % 4}",
                capability="check.plan" if i % 2 else "other.step",
                task_family="audit",
                source_refs=[f"run:bench-{i:04d}"],
                tags=["bench"],
            )
            return replace(stub, id=sha256_of({"s": stub.subject, "c": stub.claim}))

        for i in range(240):
            problem = record_entry(mem_root, _mem_entry(i))
            if problem is not None:
                raise RuntimeError(f"memory seed failed: {problem}")
        mem_query = MemoryQuery(capability="check.plan", task_family="audit")
        record("memory_pack", lambda: memory_pack(mem_root, mem_query))

        # Plan simulation over the same 32-node plan validated above.
        record("plan_simulate", lambda: simulate_plan(plan, {r.entry.id: r for r in records}))

        # Target negotiation: provider × declared targets (local + remote mix).
        bench_targets = [
            builtin_local(),
            ExecutionTarget(
                producer=PRODUCER,
                created_at=utc_now(),
                id="remote-bench",
                type="remote-forge",
                trust="verified",
                network="egress",
                identity_ref="did:example:remote-bench",
                data_classes=["public"],
                health="healthy",
            ),
            ExecutionTarget(
                producer=PRODUCER,
                created_at=utc_now(),
                id="isolated-bench",
                type="isolated-local",
                trust="org-approved",
                network="none",
                data_classes=["public", "internal", "confidential"],
                health="healthy",
            ),
        ]
        record(
            "target_negotiate",
            lambda: negotiate_target(
                "echo-forge",
                "demo.echo",
                TargetRequirement(data_classification="internal", locality="local-or-remote"),
                bench_targets,
            ),
        )

        # Remote receipt binding validation (request built against the allowlisted
        # bench target; receipt checked by accept_receipt).
        remote_policy = RemotePolicy(policy_ref="bench", allowed_target_ids=["remote-bench"])
        remote_req = build_request(
            target=bench_targets[1],
            requirement=TargetRequirement(data_classification="public", locality="local-or-remote"),
            policy=remote_policy,
            task_sha256="1" * 64,
            context_sha256="2" * 64,
            budget_sha256="3" * 64,
            provider="echo-forge",
            surface_fingerprint="a" * 64,
            expected_artifacts=["report.v1"],
        )
        remote_receipt = RemoteExecutionReceipt(
            producer=PRODUCER,
            created_at=utc_now(),
            request_sha256=sha256_of(to_dict(remote_req)),
            execution_id="bench-exec",
            target_id="remote-bench",
            target_identity_ref="did:example:remote-bench",
            provider="echo-forge",
            input_hashes={"task": "1" * 64},
            output_hashes={"report.v1": "4" * 64},
            verification="bench-verifier:ok",
        )
        record("receipt_validate", lambda: accept_receipt(remote_receipt, remote_req))

        # Observation append to the store's JSONL (bounded writes).
        obs_root = tmp / "ws-obs"
        obs_root.mkdir()
        init_workspace(obs_root)
        obs = ExecutionObservation(
            producer=PRODUCER,
            created_at=utc_now(),
            run_id="bench-run",
            provider="echo-forge",
            capability="demo.echo",
            status="ok",
            profile=PROFILE,
            context_bytes=125440,
        )
        record("observation_write", lambda: record_observation(obs_root, obs))
    return {name: results[name] for name in MEASUREMENTS}


# --- command line ----------------------------------------------------------------------------


def _emit(document: Mapping[str, Any], out: Path | None) -> None:
    text = json.dumps(document, indent=2) + "\n"
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8", newline="\n")
    else:
        sys.stdout.write(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="The Forge benchmark (baseline and budgets).")
    parser.add_argument(
        "--quick",
        action="store_true",
        help=f"{QUICK_RUNS} repetitions per measurement (default {DEFAULT_RUNS})",
    )
    parser.add_argument("--runs", type=int, help="repetitions per measurement")
    parser.add_argument("--out", type=Path, help="write the results JSON here (else stdout)")
    parser.add_argument("--check", type=Path, help="budgets JSON; exit 1 on any regression")
    parser.add_argument(
        "--results", type=Path, help="check this results JSON instead of measuring (needs --check)"
    )
    parser.add_argument(
        "--budgets-from",
        type=Path,
        metavar="BASELINE",
        help="write budgets derived from this results JSON instead of measuring",
    )
    parser.add_argument(
        "--factor",
        type=float,
        default=DEFAULT_FACTOR,
        help=f"budget = factor x baseline median (default {DEFAULT_FACTOR})",
    )
    args = parser.parse_args(argv)
    if args.budgets_from is not None:
        if args.results is not None or args.check is not None:
            parser.error("--budgets-from cannot be combined with --results or --check")
        try:
            budgets = derive_budgets(args.budgets_from, args.factor)
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
    with tempfile.TemporaryDirectory(prefix="theforge-bench-", ignore_cleanup_errors=True) as tmp:
        results = run_procedure(Path(tmp), runs, lambda line: print(line, file=sys.stderr))
    _emit(build_report(results, collect_origin()), args.out)
    return _check(results, load_budgets(args.check)) if args.check is not None else 0


if __name__ == "__main__":
    sys.exit(main())
