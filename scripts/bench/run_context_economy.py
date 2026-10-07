#!/usr/bin/env python3
"""Context-economy benchmark (Cycle 3.1, Phases 50-51). Stdlib only.

Two arms run over the same deterministic workspace through the real plan
execution path (``plan --from FILE --execute``), with the real adapters in
replay mode — the ``specialist-replay`` tier of docs/real-providers.md: real
adapter subprocess + real Forge Protocol envelopes + recorded native output.
Nothing about the specialist is invented, and no network is touched.

  direct   Spark Forge AWS and API Forge each receive the whole workspace — the
           pre-mesh baseline where every specialist rereads everything.
  mesh     Doctor Data scans the workspace once; Spark Forge AWS and API Forge
           receive a bounded context (their domain targets only) plus the
           doctor's evidence through the plan handoff.

Measured per arm from the run store (observable dimensions only):

  provider_calls   provider ``execute`` subprocess invocations
  files_scanned    sum(WorkspaceSummary.files_scanned) — scan work, packed or not
  context_files    ContextFile entries packed across all provider runs
  context_bytes    sum(ContextPack.used_bytes)
  handoff_bytes    handoff artifact bytes delivered to downstream nodes
  evidence_bytes   native/handoff.json bytes produced by doctor runs
  wall_ms          executor wall time (informative, never budgeted)

``model_calls`` and ``provider_tokens`` are emitted as ``null``: neither is
observable in an offline replay run, and unknown is not zero.

Usage: ``python scripts/bench/run_context_economy.py [--runs N] [--out PATH]``
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import tempfile
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Final

from run_bench import collect_origin
from workspace import generate_workspace

from theforge.contracts import ContextPack, from_dict
from theforge.forger import Forger, PlanCommand, PlanExecutor
from theforge.registry import Registry
from theforge.runs import RunStore
from theforge.state import init_workspace

SCHEMA: Final = "theforge-economy-bench/v1"
REPO: Final = Path(__file__).resolve().parents[2]
NATIVE: Final = REPO / "tests" / "fixtures" / "native"
WORKSPACE_FILES: Final = 400
SEED: Final = 0
PROFILE: Final = "max"
DEFAULT_RUNS: Final = 3

# Signal files added on top of the generated noise so every node has a real
# domain to look at (replay answers the recorded bundle either way; the shape
# keeps the scenario honest and reusable for a specialist-real variant).
DOMAIN_FILES: Final[Mapping[str, str]] = {
    "jobs/orders_glue_job.py": "df = spark.read.parquet('s3://b/orders')\n",
    "requirements.txt": "pyspark==3.5.1\n",
    "api/openapi.yaml": ("openapi: 3.0.0\ninfo:\n  title: Orders\n  version: 1.0.0\n"
                         "paths:\n  /orders:\n    get: {}\n"),
    "src/app.py": "from fastapi import FastAPI\n\napp = FastAPI()\n",
}

DIRECT_NODES: Final = (
    {"id": "n1", "role": "standalone", "provider": "spark-forge-aws",
     "capability": "pyspark.static-analysis", "action": "pyspark", "targets": ["."]},
    {"id": "n2", "role": "standalone", "provider": "api-forge",
     "capability": "api.analyze", "action": "analyze", "targets": ["."]},
)
MESH_NODES: Final = (
    {"id": "n1", "role": "producer", "provider": "forge-doctor-data",
     "capability": "data.scan", "action": "analyze", "targets": ["."]},
    {"id": "n2", "role": "consumer", "provider": "spark-forge-aws",
     "capability": "pyspark.static-analysis", "action": "pyspark",
     "targets": ["jobs", "requirements.txt"],
     "depends_on": [{"node": "n1", "epistemic": "explicit",
                     "evidence": "doctor observation feeds the engineer"}],
     "inputs": ["n1"]},
    {"id": "n3", "role": "consumer", "provider": "api-forge",
     "capability": "api.analyze", "action": "analyze",
     "targets": ["api", "src"],
     "depends_on": [{"node": "n1", "epistemic": "explicit",
                     "evidence": "doctor observation feeds the engineer"}],
     "inputs": ["n1"]},
)
ARMS: Final[Mapping[str, tuple[dict[str, Any], ...]]] = {
    "direct": DIRECT_NODES,
    "mesh": MESH_NODES,
}

# Observable metric keys (emitted in a fixed order; anything else is unknown).
METRICS: Final = ("provider_calls", "files_scanned", "context_files", "context_bytes",
                  "handoff_bytes", "evidence_bytes", "wall_ms")
UNMEASURABLE: Final = ("model_calls", "provider_tokens")


def _replay(adapter: str) -> list[str]:
    return [sys.executable, "-m", f"theforge_{adapter}", "--replay",
            str(NATIVE / adapter / "default")]


ENTRIES: Final = (
    {"id": "forge-doctor-data", "argv": _replay("doctordata"), "trust": "local"},
    {"id": "forge-doctor-api", "argv": _replay("doctorapi"), "trust": "local"},
    {"id": "spark-forge-aws", "argv": _replay("sparkforge_aws"), "trust": "local"},
    {"id": "api-forge", "argv": _replay("apiforge"), "trust": "local"},
)


@contextmanager
def _isolated_env(config_dir: Path, cache_dir: Path) -> Iterator[None]:
    """Point the user config/cache dirs at throwaway paths for this process."""
    saved = {name: os.environ.get(name)
             for name in ("THEFORGE_CONFIG_DIR", "THEFORGE_CACHE_DIR")}
    os.environ["THEFORGE_CONFIG_DIR"] = str(config_dir)
    os.environ["THEFORGE_CACHE_DIR"] = str(cache_dir)
    try:
        yield
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _write_providers(config_dir: Path) -> None:
    lines: list[str] = []
    for entry in ENTRIES:
        lines += ["[[providers]]", f"id = {json.dumps(entry['id'])}",
                  f"argv = {json.dumps(entry['argv'])}",
                  f"trust = {json.dumps(entry['trust'])}", ""]
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "providers.toml").write_text("\n".join(lines), encoding="utf-8")


def _seed_workspace(root: Path) -> None:
    generate_workspace(root, WORKSPACE_FILES, seed=SEED)
    for rel, text in DOMAIN_FILES.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")


def _write_plan(path: Path, nodes: tuple[dict[str, Any], ...]) -> Path:
    """Write the plan file *outside* the workspace so it never enters a scan."""
    path.write_text(json.dumps({"task_id": "economy-bench", "pattern": "pipeline",
                                "source": "file", "profile": PROFILE,
                                "nodes": list(nodes)}), encoding="utf-8")
    return path


def _collect(store: RunStore, plan_run: str) -> dict[str, Any]:
    """Observable economy metrics of the plan's provider runs, from artifacts."""
    receipts = {run_id: store.read(run_id, "receipt") for run_id in store.list_runs()}
    children = sorted(run_id for run_id, receipt in receipts.items()
                      if receipt.get("parent_run") == plan_run)
    node_of = {run_id: receipts[run_id].get("plan_node", "")
               for run_id in children}
    metrics: dict[str, Any] = {
        "provider_calls": len(children),
        "files_scanned": 0,
        "context_files": 0,
        "context_bytes": 0,
        "handoff_bytes": 0,
        "evidence_bytes": 0,
        "runs": [],
    }
    for run_id in children:
        pack = from_dict(ContextPack, store.read(run_id, "context"), strict=True)
        scanned = pack.workspace.files_scanned if pack.workspace is not None else 0
        handoff = store.read_optional(run_id, "handoff")
        handoff_bytes = (len(json.dumps(handoff, sort_keys=True).encode("utf-8"))
                         if handoff is not None else 0)
        evidence_bytes = 0
        for artifact in store.read(run_id, "result").get("artifacts", []):
            path = store.run_dir(run_id) / "work" / artifact["path"]
            if path.is_file():
                evidence_bytes += path.stat().st_size
        row = {"node": node_of[run_id],
               "provider": receipts[run_id].get("provider", {}).get("id", ""),
               "files_scanned": scanned,
               "context_files": len(pack.files),
               "context_bytes": pack.used_bytes,
               "handoff_bytes": handoff_bytes,
               "evidence_bytes": evidence_bytes}
        metrics["runs"].append(row)
        for key in ("files_scanned", "context_files", "context_bytes",
                    "handoff_bytes", "evidence_bytes"):
            metrics[key] += row[key]
    metrics["runs"].sort(key=lambda row: (row["node"], row["provider"]))
    return metrics


def _run_arm(workspace: Path, nodes: tuple[dict[str, Any], ...]) -> tuple[dict[str, Any], int]:
    """One arm repetition: returns (collected metrics, wall time in ms)."""
    init_workspace(workspace)
    forge_dir = workspace / ".forge"
    plan = _write_plan(workspace.parent / f"{workspace.name}-plan.json", nodes)
    store = RunStore(forge_dir)
    executor = PlanExecutor(Forger(workspace, Registry(forge_dir), store))
    start = time.perf_counter_ns()
    out = executor.run(PlanCommand(intent="context economy bench", profile=PROFILE,
                                   plan_file=plan, execute=True))
    wall_ms = (time.perf_counter_ns() - start) // 1_000_000
    if out.status != "ok":
        raise RuntimeError(f"bench arm failed: status={out.status!r} "
                           f"error={getattr(out, 'error', None)!r}")
    return _collect(store, out.run_id), wall_ms


def run_arm(base: Path, name: str, nodes: tuple[dict[str, Any], ...],
            runs: int) -> dict[str, Any]:
    """``runs`` repetitions of one arm; byte metrics are deterministic, wall_ms
    is the median. Each repetition gets a fresh workspace copy of the seed."""
    walls: list[int] = []
    collected: dict[str, Any] = {}
    for iteration in range(runs):
        workspace = base / f"{name}-{iteration}"
        _seed_workspace(workspace)
        collected, wall = _run_arm(workspace, nodes)
        walls.append(wall)
    entry = {key: collected[key] for key in METRICS if key != "wall_ms"}
    entry["wall_ms"] = round(statistics.median(walls), 3)
    entry["runs"] = collected["runs"]
    for key in UNMEASURABLE:
        entry[key] = None
    return entry


def build_report(arms: Mapping[str, Mapping[str, Any]],
                 origin: Mapping[str, Any]) -> dict[str, Any]:
    comparison: dict[str, Any] = {}
    for key in METRICS:
        pair = {name: arms[name][key] for name in ARMS}
        entry: dict[str, Any] = dict(pair)
        if all(isinstance(v, (int, float)) for v in pair.values()):
            entry["mesh_minus_direct"] = round(pair["mesh"] - pair["direct"], 3)
        comparison[key] = entry
    return {
        "schema": SCHEMA,
        "origin": dict(origin),
        "provider_mode": "specialist-replay",
        "workspace_files": WORKSPACE_FILES + len(DOMAIN_FILES),
        "arms": {name: dict(arms[name]) for name in ARMS},
        "comparison": comparison,
        "unmeasurable": list(UNMEASURABLE),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS,
                        help="repetitions per arm (wall_ms median; bytes are deterministic)")
    parser.add_argument("--out", type=Path, default=None,
                        help="write the JSON report here (default: stdout)")
    args = parser.parse_args(argv)
    if args.runs < 1:
        parser.error("--runs must be >= 1")

    for module in ("theforge_doctordata", "theforge_doctorapi",
                   "theforge_sparkforge_aws", "theforge_apiforge"):
        try:
            __import__(module)
        except ImportError:
            print(f"error: {module} is not importable; install the adapters "
                  f"(pip install -e adapters/*)", file=sys.stderr)
            return 2

    with tempfile.TemporaryDirectory(prefix="theforge-economy-") as tmp:
        base = Path(tmp)
        config_dir, cache_dir = base / "config", base / "cache"
        with _isolated_env(config_dir, cache_dir):
            _write_providers(config_dir)
            arms = {name: run_arm(base, name, nodes, args.runs)
                    for name, nodes in ARMS.items()}
    report = build_report(arms, collect_origin())
    text = json.dumps(report, indent=2, sort_keys=False) + "\n"
    if args.out is None:
        sys.stdout.write(text)
    else:
        args.out.write_text(text, encoding="utf-8")
        print(f"report written to {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
