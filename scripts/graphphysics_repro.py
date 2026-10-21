#!/usr/bin/env python3
"""lf-0020 P0 reproduction harness — runs the REAL Graph Studio physics headlessly.

The reported defect: ``<forge> graph ui`` on ~3.000 elements opens the studio,
nodes appear inside their initial ±300px random box, then space out violently
and disappear. This harness proves (or refutes) the numeric-instability
hypothesis *with the production code*, not a re-implementation of it:

1. ``extract_script`` pulls the inline ``<script>`` out of
   ``theforge.graphstudio.STUDIO_HTML`` — the same regex used by
   ``tests/test_graphstudio.py::test_studio_inline_script_parses``.
2. ``build_harness`` wraps that verbatim script in a generated ``.mjs``: a
   deterministic ``Math.random``, minimal DOM stubs (canvas 2-D context,
   ``document.getElementById``, ``requestAnimationFrame`` captured into a
   slot instead of scheduled) and a ``fetch`` that serves the fixture JSON
   through the studio's real ``/api/graphs`` + ``/api/graph/<id>`` path —
   so the same ``loadGraph`` → ``tick`` → ``draw`` chain the browser runs
   is what executes.
3. node runs the file; the driver drains ``loadGraphs()`` then replays the
   RAF chain synchronously for N ticks, sampling coordinate sanity.

The report records, per run: non-finite coordinate count (``NaN``/``±Infinity``
in ``x``, ``y``, ``vx``, ``vy``), max |coord|, fraction of nodes outside a
10.000 px viewport box, per-tick wall-time, the first tick the blow-up is
detected, and a sample of surviving positions.

Requires ``node`` on PATH (or ``--node``). Read-only: nothing under ``src/``,
no vendored ``_graphstudio.py`` and no fixture is modified.

    python scripts/graphphysics_repro.py \
        --fixture ../spark-forge-aws/tests/graph/fixtures/graph_3000_chain.json \
        --ticks 600 --out report.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]

# Same extraction pattern as tests/test_graphstudio.py::test_studio_inline_script_parses.
_SCRIPT_RE = re.compile(r"<script>(.*)</script>", re.DOTALL)

# Blow-up verdict thresholds. A coordinate is "gone" for the viewer well before
# Infinity: the canvas maps world→screen with no fit-to-view, so |x| past a few
# viewport widths is already invisible. 1e6 is the "exploded" line.
VIEWPORT_HALF_PX = 5000  # nodes past ±5000 are outside a 10.000 px box
EXPLODED_COORD = 1e6

HARNESS_PREAMBLE = """\
// --- lf-0020 headless harness: deterministic DOM/RAF stubs (generated) ---
import {readFileSync} from 'node:fs';
const __fixturePath = process.argv[2];
const __TICKS = __TICKS__;
const __SAMPLE_EVERY = __SAMPLE_EVERY__;
const __VIEWPORT = __VIEWPORT__;
const __doc = JSON.parse(readFileSync(__fixturePath, 'utf8'));

// Deterministic Math.random (mulberry32) — the studio places nodes with
// Math.random(); pinning it makes the whole run byte-reproducible.
let __seed = 1;
Math.random = function () {
  __seed |= 0; __seed = (__seed + 0x6D2B79F5) | 0;
  let t = Math.imul(__seed ^ (__seed >>> 15), 1 | __seed);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
};

// Canvas 2-D context: every method a no-op, every property settable.
const __ctx = new Proxy({}, {
  get: (o, k) => (k in o ? o[k] : () => {}),
  set: (o, k, v) => { o[k] = v; return true; },
});
const __rect = {width: 1600, height: 900, left: 0, top: 0, right: 1600, bottom: 900, x: 0, y: 0};
function __el(id) {
  return {id, innerHTML: '', textContent: '', value: '', dataset: {}, style: {}, children: [],
    appendChild(c) { this.children.push(c); },
    querySelectorAll: () => [], addEventListener: () => {},
    getBoundingClientRect: () => __rect};
}
const __els = {};
__els['cv'] = Object.assign(__el('cv'), {width: 0, height: 0, getContext: () => __ctx});
globalThis.document = {
  getElementById: (id) => (__els[id] ??= __el(id)),
  createElement: (t) => __el(t),
  onkeydown: null,
};
globalThis.devicePixelRatio = 1;
globalThis.localStorage = {getItem: () => null, setItem: () => {}, removeItem: () => {}};
// The RAF queue is a single slot: the driver replays it synchronously.
let __raf = null;
let __rafCount = 0;
globalThis.requestAnimationFrame = (cb) => { __raf = cb; __rafCount++; return __rafCount; };
globalThis.cancelAnimationFrame = (id) => { __raf = null; };
globalThis.window = globalThis; // the studio installs window.onresize
// fetch serves the fixture through the studio's real endpoints.
globalThis.fetch = async (url) => {
  if (url === '/api/graphs') return {json: async () => ({graphs: [__doc.descriptor]})};
  if (String(url).startsWith('/api/graph/')) return {json: async () => __doc};
  return {json: async () => ({}), ok: false, status: 404};
};
// --- end of stubs; verbatim studio <script> follows ---
"""

HARNESS_DRIVER = """\
// --- lf-0020 driver: drain loadGraphs(), then replay the RAF chain ---
function __stats() {
  let nf = 0, out = 0, mx = 0, mv = 0;
  for (const a of G.nodes) {
    if (![a.x, a.y, a.vx, a.vy].every(Number.isFinite)) { nf++; continue; }
    const c = Math.max(Math.abs(a.x), Math.abs(a.y));
    const v = Math.abs(a.vx) + Math.abs(a.vy);
    if (c > mx) mx = c;
    if (v > mv) mv = v;
    if (Math.abs(a.x) > __VIEWPORT || Math.abs(a.y) > __VIEWPORT) out++;
  }
  return {non_finite: nf, max_abs_coord: mx, max_abs_speed: mv, outside_10k: out};
}
try {
  const __deadline = Date.now() + 15000;
  while (!G.nodes.length) {
    if (Date.now() > __deadline) throw new Error('fixture graph never loaded');
    await new Promise((r) => setTimeout(r, 1));
  }
  // lf-0022: an optional mode override is applied right after load — the
  // pending RAF chain just continues on the new render set.
  const __m = '__MODE__';
  if (__m && typeof setMode === 'function') setMode(__m);
  const __wall0 = Date.now();
  const __samples = [{tick: 0, ...__stats()}];
  const __tickMs = [];
  let ran = 0, firstBlow = -1;
  // lf-0022: a logical tick may span several RAF frames (SIM_MS slicing), so
  // __TICKS counts LOGICAL ticks (the studio's lticks counter) — the RAF cap
  // of 64× only bounds pathological slowness, never convergence.
  const __lt = () => (typeof lticks !== 'undefined' ? lticks : ran);
  const __RAF_CAP = __TICKS * 64;
  while (__raf && ran < __RAF_CAP && __lt() < __TICKS && !settled) {
    const cb = __raf; __raf = null;
    const t0 = process.hrtime.bigint();
    cb();
    __tickMs.push(Number(process.hrtime.bigint() - t0) / 1e6);
    ran++;
    const s = __stats();
    if (firstBlow < 0 && (s.non_finite > 0 || s.max_abs_coord > 1e9)) firstBlow = ran;
    // Once diverging, sample every tick — that tail IS the evidence.
    if (ran % __SAMPLE_EVERY === 0 || firstBlow > 0) __samples.push({tick: ran, ...s});
    // Stop when NaN/Inf is recorded, or cap the post-blow tail at 30 ticks.
    if (firstBlow > 0 && (s.non_finite > 0 || ran >= firstBlow + 30)) break;
  }
  const __total = __tickMs.reduce((a, b) => a + b, 0);
  const __lticks = __lt();
  // lf-0021: a loop that stops because the layout converged (alpha decayed or
  // every node quiet) is NOT starvation — only an unexpected stop counts.
  const __settled = (typeof settled !== 'undefined') ? settled : false;
  const __report = {
    fixture: __fixturePath,
    graph_id: __doc.descriptor.graph_id,
    nodes: G.nodes.length,
    edges: G.edges.length,
    edges_dropped: (__doc.edges || []).length - G.edges.length,
    mode: (typeof mode !== 'undefined') ? mode : null,
    render_nodes: (typeof R !== 'undefined') ? R.nodes.length : null,
    render_edges: (typeof R !== 'undefined') ? R.edges.length : null,
    clusters: (typeof clusters !== 'undefined' && clusters) ? clusters.length : null,
    notice: document.getElementById('notice').textContent || '',
    raf_frames: ran,
    logical_ticks: __lticks,
    ticks_completed: __lticks + 1, // back-compat: logical ticks replayed +1
    first_blow_tick: firstBlow,
    raf_starved: ran < __RAF_CAP && !__raf && !__settled,
    settled: __settled,
    resets: (typeof resets !== 'undefined') ? resets : null,
    generation: (typeof gen !== 'undefined') ? gen : null,
    raf_requests: __rafCount,
    final: __stats(),
    samples: __samples,
    tick_ms: {
      total: Math.round(__total * 100) / 100,
      mean: Math.round((__total / Math.max(ran, 1)) * 100) / 100,
      max: Math.round(Math.max(...__tickMs, 0) * 100) / 100,
    },
    wall_ms: Date.now() - __wall0,
    positions_sample: G.nodes.filter((a) => Number.isFinite(a.x) && Number.isFinite(a.y))
      .slice(0, 20).map((a) => ({id: a.id, x: Math.round(a.x), y: Math.round(a.y)})),
  };
  process.stdout.write(JSON.stringify(__report) + '\\n');
} catch (e) {
  process.stdout.write(JSON.stringify({error: String(e && e.stack || e)}) + '\\n');
  process.exitCode = 1;
}
"""


def extract_script() -> str:
    """The studio's inline ``<script>``, verbatim — the code under test."""
    try:
        from theforge.graphstudio import STUDIO_HTML
    except ModuleNotFoundError:  # running from a checkout without the package installed
        sys.path.insert(0, str(REPO / "src"))
        from theforge.graphstudio import STUDIO_HTML
    match = _SCRIPT_RE.search(STUDIO_HTML)
    if not match:
        raise RuntimeError("STUDIO_HTML has no inline <script>")
    return match.group(1)


def build_harness(
    script: str,
    *,
    ticks: int,
    sample_every: int,
    viewport: int,
    driver: str | None = None,
    mode: str = "",
) -> str:
    """Prelude + verbatim studio script + driver, as one ``.mjs`` source.

    ``driver`` replaces the default tick-replay driver — tests that need to
    poke studio internals (double ``loadGraph``, poisoned nodes, thrown
    exceptions) compose their own and get the same stubs/preamble.
    ``mode`` (lf-0022) is applied through ``setMode`` right after load.
    """
    preamble = (
        HARNESS_PREAMBLE.replace("__TICKS__", str(ticks))
        .replace("__SAMPLE_EVERY__", str(sample_every))
        .replace("__VIEWPORT__", str(viewport))
    )
    harness = preamble + script + (driver if driver is not None else HARNESS_DRIVER)
    return harness.replace("__MODE__", mode)


def run_harness(
    fixture: Path, harness: str, *, node: str = "node", timeout: int = 900
) -> dict[str, Any]:
    """Write ``harness`` to a temp ``.mjs``, run it under node, return the
    parsed stdout JSON (raw — no verdict computed)."""
    with tempfile.TemporaryDirectory(prefix="graphrepro-") as td:
        mjs = Path(td) / "graphrepro.mjs"
        mjs.write_text(harness, encoding="utf-8")
        proc = subprocess.run(
            [node, str(mjs), str(fixture)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    try:
        report: dict[str, Any] = json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        report = {"error": "no JSON report on stdout", "stdout": proc.stdout[:2000]}
    if proc.returncode != 0 or "error" in report:
        report.setdefault("error", proc.stderr[:2000] or f"node exited {proc.returncode}")
    return report


def _verdict(report: dict[str, Any]) -> tuple[str, str]:
    final = report.get("final", {})
    non_finite = final.get("non_finite", 0)
    max_coord = final.get("max_abs_coord", 0)
    outside = final.get("outside_10k", 0)
    nodes = report.get("nodes", 0)
    blow = report.get("first_blow_tick", -1)
    if non_finite:
        return (
            "REPRODUCED",
            f"{non_finite}/{nodes} nodes reached NaN/±Infinity — "
            f"ctx.arc(NaN) draws nothing, the reported disappearance",
        )
    if max_coord >= EXPLODED_COORD or (nodes and outside / nodes > 0.9):
        return (
            "REPRODUCED",
            f"coordinates exploded (max |coord|={max_coord:.3g}, "
            f"{outside}/{nodes} outside a 10.000 px box) — nothing left on canvas",
        )
    if blow >= 0:
        return ("BLOWING-UP", f"divergence detected at tick {blow}, still finite")
    return ("STABLE", "coordinates stayed finite and inside reach — not reproduced")


def _candidate_causes(report: dict[str, Any]) -> list[dict[str, str]]:
    """Verdict per §0.1 candidate cause, from what THIS run actually observed.

    Values: ``proven`` (observed in the report), ``ruled_out`` (instrumented
    and absent) or ``unmeasured`` (the headless harness cannot see it).
    """
    final = report.get("final", {})
    nodes = report.get("nodes", 0)
    causes: list[tuple[str, str, str]] = [
        (
            "numeric instability — NaN/±Infinity coordinates",
            "proven" if final.get("non_finite", 0) else "ruled_out",
            f"non_finite={final.get('non_finite', 0)}/{nodes}",
        ),
        (
            "extreme coordinates — vertices carried off-world",
            "proven" if final.get("max_abs_coord", 0) >= EXPLODED_COORD else "ruled_out",
            f"max_abs_coord={final.get('max_abs_coord', 0):.3g}",
        ),
        (
            "vertices off-viewport under the fixed camera (no fit-to-view)",
            "proven" if nodes and final.get("outside_10k", 0) / nodes > 0.5 else "ruled_out",
            f"outside_10k={final.get('outside_10k', 0)}/{nodes}",
        ),
        (
            "main-thread saturation (tick slower than one 16.6 ms frame)",
            "proven" if report.get("tick_ms", {}).get("mean", 0) > 16.6 else "ruled_out",
            f"mean_tick_ms={report.get('tick_ms', {}).get('mean', 0)}",
        ),
        (
            "requestAnimationFrame interruption (loop stopped scheduling)",
            "proven" if report.get("raf_starved") else "ruled_out",
            f"raf_starved={report.get('raf_starved')}",
        ),
        (
            "unhandled JavaScript errors",
            "proven" if "error" in report else "ruled_out",
            report.get("error", "no exception reached the driver"),
        ),
        (
            "progressive vertex expansion",
            "unmeasured",
            "headless run has no observer; max_abs_coord samples cover the same effect",
        ),
        (
            "layout re-initialization",
            "unmeasured",
            "single load per run; RAF-stacking across loadGraph() calls not replayed",
        ),
        (
            "canvas outside visible area / resize / context loss",
            "unmeasured",
            "no real DOM or compositor in the node harness",
        ),
        ("memory limits", "unmeasured", "not instrumented"),
    ]
    return [{"cause": c, "verdict": v, "evidence": e} for c, v, e in causes]


def run(
    fixture: Path,
    *,
    ticks: int = 600,
    node: str = "node",
    timeout: int = 900,
    sample_every: int = 25,
    mode: str = "",
) -> dict[str, Any]:
    """Build the harness, run it under node on ``fixture``, return the report."""
    script = extract_script()
    harness = build_harness(
        script,
        ticks=ticks,
        sample_every=sample_every,
        viewport=VIEWPORT_HALF_PX,
        mode=mode,
    )
    report = run_harness(fixture, harness, node=node, timeout=timeout)
    if "error" in report:
        report["verdict"] = "HARNESS-ERROR"
        report["verdict_reason"] = "node run failed — see error"
    else:
        report["verdict"], report["verdict_reason"] = _verdict(report)
        report["candidate_causes"] = _candidate_causes(report)
    report["ticks_requested"] = ticks
    report["fixture_bytes"] = fixture.stat().st_size
    report["extracted_script_sha256"] = hashlib.sha256(script.encode()).hexdigest()
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fixture", type=Path, required=True, help="ForgeGraphView/v1 JSON")
    parser.add_argument("--ticks", type=int, default=600)
    parser.add_argument("--out", type=Path, default=None, help="write the JSON report here")
    parser.add_argument("--node", default=None, help="path to node (default: PATH lookup)")
    parser.add_argument("--timeout", type=int, default=900, help="node timeout, seconds")
    parser.add_argument("--sample-every", type=int, default=25)
    parser.add_argument(
        "--mode",
        default="",
        choices=("", "overview", "explore", "full"),
        help="lf-0022: force a scale mode right after load (default: studio's pick)",
    )
    args = parser.parse_args(argv)

    node = args.node or shutil.which("node")
    if node is None:
        print("error: node not found on PATH — install node or pass --node", file=sys.stderr)
        return 2
    if not args.fixture.is_file():
        print(f"error: fixture not found: {args.fixture}", file=sys.stderr)
        return 2

    version = subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip()
    report = run(
        args.fixture,
        ticks=args.ticks,
        node=node,
        timeout=args.timeout,
        sample_every=args.sample_every,
        mode=args.mode,
    )
    report["node_version"] = version
    blob = json.dumps(report, indent=1, ensure_ascii=False) + "\n"
    if args.out:
        args.out.write_text(blob, encoding="utf-8")
    print(blob)
    return 0 if report.get("verdict") != "HARNESS-ERROR" else 1


if __name__ == "__main__":
    sys.exit(main())
