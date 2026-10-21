#!/usr/bin/env python3
"""lf-0024 perf harness — machine-readable per-size metrics for Graph Studio.

Runs the REAL studio ``<script>`` headlessly (same stubs/driver model as
``graphphysics_repro.py``) over ForgeGraphView/v1 fixture graphs and emits a
JSON report per fixture: load time, settle time, per-frame tick cost, V8 heap
and process CPU.

Honesty contract (reviewer checklist):

- ``load_ms`` is module-eval → ``G.nodes`` populated: JSON parse, model
  assembly, cluster rollup when the mode picks overview, first tick
  scheduling. It is NOT a browser page load (no network, no CSSOM).
- ``settle_ms``/``tick_ms`` are the RAF-replayed force loop, synchronous —
  there is no compositor and no display here, so no FPS is claimed; the
  honest proxy is per-frame simulation cost.
- ``heap_mb`` is V8 ``process.memoryUsage()`` — JS heap + RSS of the node
  harness, not a browser tab's memory.
- ``cpu_ms`` is whole-process ``process.cpuUsage()`` (user+system).
- ``settled: false`` means the tick budget ran out — recorded, never
  presented as a pass.

    python scripts/graph_perf.py \
        --sizes 100 500 1000 3000 5000 10000 25000 \
        --full 3000 --full 10000 \
        --out docs/graph/perf-baseline.json \
        --md docs/graph/perf-report.md
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURES_DIR = REPO.parent / "spark-forge-aws" / "tests" / "graph" / "fixtures"

sys.path.insert(0, str(REPO / "scripts"))
from graphphysics_repro import VIEWPORT_HALF_PX, build_harness, extract_script, run_harness  # noqa: E402

PERF_DRIVER = """\
try {
  const __m0 = process.memoryUsage().heapUsed;
  const __c0 = process.cpuUsage();
  const __t0 = Date.now();
  const __deadline = __t0 + 120000;
  while (!G.nodes.length) {
    if (Date.now() > __deadline) throw new Error('fixture graph never loaded');
    await new Promise((r) => setTimeout(r, 1));
  }
  const __loadMs = Date.now() - __t0;
  const __mLoad = process.memoryUsage().heapUsed;
  const __m = '__MODE__';
  if (__m && typeof setMode === 'function') setMode(__m);
  const __s0 = Date.now();
  const __tickMs = [];
  let ran = 0;
  const __lt = () => (typeof lticks !== 'undefined' ? lticks : ran);
  const __CAP = __TICKS * 64;
  while (__raf && ran < __CAP && __lt() < __TICKS && !settled) {
    const cb = __raf; __raf = null;
    const t = process.hrtime.bigint();
    cb();
    __tickMs.push(Number(process.hrtime.bigint() - t) / 1e6);
    ran++;
  }
  const __settleMs = Date.now() - __s0;
  const __c1 = process.cpuUsage(__c0);
  const __mem = process.memoryUsage();
  __tickMs.sort((a, b) => a - b);
  const pct = (p) =>
    __tickMs.length ? __tickMs[Math.min(__tickMs.length - 1, Math.floor(p * __tickMs.length))] : 0;
  const mean = __tickMs.reduce((a, b) => a + b, 0) / Math.max(ran, 1);
  let nf = 0, mx = 0, out = 0;
  for (const a of G.nodes) {
    if (![a.x, a.y, a.vx, a.vy].every(Number.isFinite)) { nf++; continue; }
    const c = Math.max(Math.abs(a.x), Math.abs(a.y));
    if (c > mx) mx = c;
    if (Math.abs(a.x) > __VIEWPORT || Math.abs(a.y) > __VIEWPORT) out++;
  }
  const r2 = (x) => Math.round(x * 100) / 100;
  process.stdout.write(JSON.stringify({
    fixture: __fixturePath,
    graph_id: (__doc.descriptor || {}).graph_id || null,
    requested_mode: __m || null,
    mode: (typeof mode !== 'undefined') ? mode : null,
    nodes: G.nodes.length,
    edges: G.edges.length,
    edges_dropped: (__doc.edges || []).length - G.edges.length,
    render_nodes: R.nodes.length,
    render_edges: R.edges.length,
    clusters: clusters ? clusters.length : 0,
    draw: drawMeta,
    load_ms: __loadMs,
    settle_ms: __settleMs,
    settled: !!settled,
    logical_ticks: __lt(),
    raf_frames: ran,
    resets,
    tick_ms: {
      mean: r2(mean), p50: r2(pct(0.5)), p95: r2(pct(0.95)),
      max: r2(__tickMs.length ? __tickMs[__tickMs.length - 1] : 0),
    },
    heap_mb: {
      t0: r2(__m0 / 1048576), after_load: r2(__mLoad / 1048576),
      end: r2(__mem.heapUsed / 1048576), rss_end: r2(__mem.rss / 1048576),
    },
    cpu_ms: {user: r2(__c1.user / 1000), system: r2(__c1.system / 1000)},
    non_finite: nf, max_abs_coord: Math.round(mx), outside_10k: out,
    notice: document.getElementById('notice').textContent || '',
    err: document.getElementById('err').textContent || '',
  }) + '\\n');
} catch (e) {
  process.stdout.write(JSON.stringify({error: String(e && e.stack || e)}) + '\\n');
  process.exitCode = 1;
}
"""


def pick_fixture(fixtures_dir: Path, size: int, topology: str | None) -> Path | None:
    """``graph_{size}_{topology}.json`` if present, else the alphabetically
    first fixture at that size — the report records which ran."""
    cands = sorted(fixtures_dir.glob(f"graph_{size}_*.json"))
    if not cands:
        return None
    if topology:
        for c in cands:
            if c.stem == f"graph_{size}_{topology}":
                return c
    return cands[0]


def measure(
    fixture: Path,
    *,
    node: str,
    ticks: int,
    mode: str,
    timeout: int,
) -> dict[str, Any]:
    harness = build_harness(
        extract_script(),
        ticks=ticks,
        sample_every=25,
        viewport=VIEWPORT_HALF_PX,
        driver=PERF_DRIVER,
        mode=mode,
    )
    try:
        report = run_harness(fixture, harness, node=node, timeout=timeout)
    except subprocess.TimeoutExpired:
        report = {
            "error": f"harness timeout ({timeout}s) — recorded, not hidden",
            "requested_mode": mode or None,
        }
    report["fixture_name"] = fixture.name
    report["ticks_requested"] = ticks
    report["fixture_bytes"] = fixture.stat().st_size
    return report


def run_matrix(
    fixtures_dir: Path,
    sizes: list[int],
    *,
    topology: str | None,
    full: list[int],
    node: str,
    ticks: int,
    timeout: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    plan: list[tuple[Path, str]] = []
    for size in sizes:
        fx = pick_fixture(fixtures_dir, size, topology)
        if fx is None:
            rows.append({"size": size, "skipped": f"no graph_{size}_*.json in {fixtures_dir}"})
            continue
        plan.append((fx, ""))
        if size in full:
            plan.append((fx, "full"))
    for fx, mode in plan:
        row = measure(fx, node=node, ticks=ticks, mode=mode, timeout=timeout)
        row["size"] = int(fx.stem.split("_")[1])
        rows.append(row)
    return rows


def _md_table(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| size | fixture | mode | nodes→drawn | load ms | settle ms | lticks "
        "| tick ms mean | tick ms p95 | heap MB end | rss MB end "
        "| cpu ms u+s | settled |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|",
    ]
    for r in rows:
        if "skipped" in r:
            lines.append(
                f"| {r['size']} | — | — | — | — | — | — | — | — | — "
                f"| — | — | skipped: {r['skipped']} |"
            )
            continue
        if "error" in r:
            lines.append(
                f"| {r.get('size', '?')} | {r.get('fixture_name', '?')} "
                f"| {r.get('requested_mode') or 'default'} | — | — | — | — "
                f"| — | — | — | — | — | ERROR |"
            )
            continue
        cpu = r["cpu_ms"]
        heap = r["heap_mb"]
        tk = r["tick_ms"]
        lines.append(
            f"| {r['size']} | `{r['fixture_name']}` | {r['mode']} "
            f"| {r['render_nodes']}/{r['nodes']} | {r['load_ms']} | {r['settle_ms']} "
            f"| {r['logical_ticks']} | {tk['mean']} | {tk['p95']} | {heap['end']} "
            f"| {heap['rss_end']} | {cpu['user'] + cpu['system']} | {r['settled']} |"
        )
    return "\n".join(lines)


def write_markdown(rows: list[dict[str, Any]], meta: dict[str, Any], path: Path) -> None:
    ok = [r for r in rows if "error" not in r and "skipped" not in r]
    body = [
        "# Graph Studio perf baseline (lf-0024)",
        "",
        "Measured numbers — NOT targets and NOT SLAs. Everything below came out of",
        "`scripts/graph_perf.py` replaying the real studio `<script>` under node",
        f"{meta['node_version']} on {meta['platform']}, headless DOM/RAF stubs.",
        "",
        "## Reading the columns honestly",
        "",
        "- **load ms**: module-eval → `G.nodes` populated (JSON parse, model",
        "  assembly, cluster rollup when overview is picked). No network/CSSOM —",
        "  it is not a browser page load.",
        "- **settle ms / tick ms**: synchronous RAF replay of the force loop.",
        "  No compositor exists in this harness → **no FPS is claimed**; the",
        "  honest proxy is per-frame simulation cost (a browser frame budget is",
        "  16.7 ms — tick ms well under that means the sim is not the bottleneck).",
        "- **heap MB**: V8 `process.memoryUsage()` of the node harness, not a tab.",
        "- **cpu ms**: whole-process `process.cpuUsage()` (user+system).",
        "- **settled=false** means the tick budget ran out — recorded, not hidden.",
        "",
        "## Matrix",
        "",
        _md_table(rows),
        "",
        "## Environment",
        "",
        f"- generated_at: {meta['generated_at']}",
        f"- node: {meta['node_version']} · platform: {meta['platform']}",
        f"- ticks budget: {meta['ticks']} logical ticks (×64 RAF cap)",
        f"- script sha256: `{meta['extracted_script_sha256']}`",
        "",
        f"Machine-readable rows: `{meta['json_name']}` in the same directory.",
        "",
    ]
    flags = [r for r in ok if not r["settled"] or r["non_finite"] or r["err"]]
    if flags:
        body += [
            "## Flags",
            "",
            *[f"- `{r['fixture_name']}` mode={r['mode']}: settled={r['settled']} "
              f"non_finite={r['non_finite']} err={r['err']!r} notice={r['notice']!r}"
              for r in flags],
            "",
        ]
    else:
        body += ["## Flags", "", "- none — every run settled finite with no error surface.", ""]
    path.write_text("\n".join(body), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--fixtures-dir", type=Path, default=DEFAULT_FIXTURES_DIR)
    p.add_argument(
        "--sizes", type=int, nargs="*",
        default=[100, 500, 1000, 3000, 5000, 10000, 25000],
    )
    p.add_argument(
        "--topology", default=None,
        help="preferred topology per size (fallback: first alphabetical)",
    )
    p.add_argument(
        "--full", type=int, nargs="*", default=[],
        help="also run these sizes in --mode full",
    )
    p.add_argument(
        "--fixture", type=Path, nargs="*", default=None,
        help="explicit fixture paths (overrides --sizes)",
    )
    p.add_argument("--mode", default="", choices=("", "overview", "explore", "full"))
    p.add_argument("--ticks", type=int, default=1200)
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("--node", default=None)
    p.add_argument("--out", type=Path, default=None, help="write the JSON baseline here")
    p.add_argument("--md", type=Path, default=None, help="write the markdown report here")
    args = p.parse_args(argv)

    node = args.node or shutil.which("node")
    if node is None:
        print("error: node not found on PATH", file=sys.stderr)
        return 2

    if args.fixture:
        rows = [
            measure(fx, node=node, ticks=args.ticks, mode=args.mode, timeout=args.timeout)
            for fx in args.fixture
        ]
        for r, fx in zip(rows, args.fixture, strict=True):
            r["size"] = (
                int(fx.stem.split("_")[1]) if fx.stem.split("_")[1].isdigit() else 0
            )
    else:
        rows = run_matrix(
            args.fixtures_dir,
            args.sizes,
            topology=args.topology,
            full=args.full,
            node=node,
            ticks=args.ticks,
            timeout=args.timeout,
        )

    node_version = subprocess.run(
        [node, "--version"], capture_output=True, text=True
    ).stdout.strip()
    meta = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "node_version": node_version,
        "platform": f"{platform.system()} {platform.machine()}",
        "ticks": args.ticks,
        "extracted_script_sha256": (
            __import__("hashlib").sha256(extract_script().encode()).hexdigest()
        ),
        "json_name": args.out.name if args.out else "perf-baseline.json",
    }
    doc = {"tool": "graph_perf.py (lf-0024)", **meta, "runs": rows}
    blob = json.dumps(doc, indent=1, ensure_ascii=False) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(blob, encoding="utf-8")
    if args.md:
        args.md.parent.mkdir(parents=True, exist_ok=True)
        write_markdown(rows, meta, args.md)
    print(blob)
    return 1 if any("error" in r for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
