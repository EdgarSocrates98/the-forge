"""lf-0024 perf regression gate — measured baseline + a stated band.

The baseline is a REAL artifact (``docs/graph/perf-baseline.json``) produced
by ``scripts/graph_perf.py`` replaying the verbatim studio ``<script>`` in the
node harness. This test re-measures the smallest fixture live and fails only
when a metric regresses beyond the stated band:

- **Band: 3×** on wall-clock-style numbers (load_ms, settle_ms, tick_ms.mean).
  Rationale, measured not guessed: the same run observed ~14 ms tick mean on
  a quiet dev box and ~17 ms on a loaded CI box (~1.2×); 3× leaves headroom
  for noisy shared runners while still catching an asymptotic regression
  (e.g. force law going quadratic, slicing removed).
- **Structural assertions are exact, not banded**: the run must settle with
  zero non-finite coordinates and zero nodes outside the 10k world boundary —
  those are correctness, not performance.
- FPS is NOT asserted: the headless node harness has no compositor. The
  per-tick sim cost is the honest proxy (see docs/graph/perf-report.md).

Skipped sizes: see the baseline JSON ``error``/``skipped`` rows (e.g. the
10000-node ``--mode full`` run that hit the 900 s harness timeout) — they are
recorded there, not re-attempted here.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from scripts import graph_perf

REPO = Path(__file__).resolve().parent.parent
BASELINE = REPO / "docs" / "graph" / "perf-baseline.json"
FIXTURES = REPO.parent / "spark-forge-aws" / "tests" / "graph" / "fixtures"

REGRESSION_BAND = 3.0  # loaded-CI allowance; see module docstring


def _baseline_row(size: int, mode: str) -> dict:
    doc = json.loads(BASELINE.read_text(encoding="utf-8"))
    for r in doc["runs"]:
        if r.get("size") == size and r.get("mode") == mode and "error" not in r:
            return r
    pytest.skip(f"no successful baseline row for size={size} mode={mode}")


@pytest.mark.skipif(shutil.which("node") is None, reason="node harness requires node")
@pytest.mark.skipif(not FIXTURES.is_dir(), reason="sibling fixture repo absent")
@pytest.mark.skipif(not BASELINE.is_file(), reason="perf baseline not committed")
def test_perf_100_regression_band():
    base = _baseline_row(100, "full")
    fx = FIXTURES / "graph_100_chain.json"
    if not fx.is_file():
        pytest.skip("100-node fixture absent")

    row = graph_perf.measure(fx, node=shutil.which("node"), ticks=1200, mode="", timeout=180)

    # correctness — exact, unbanded
    assert row.get("error") is None, row.get("error")
    assert row["settled"] is True, "sim never settled inside the tick budget"
    assert row["non_finite"] == 0
    assert row["outside_10k"] == 0

    # performance — the stated 3× band, both sides reported
    checks = {
        "load_ms": (row["load_ms"], base["load_ms"]),
        "settle_ms": (row["settle_ms"], base["settle_ms"]),
        "tick_ms.mean": (row["tick_ms"]["mean"], base["tick_ms"]["mean"]),
    }
    for name, (now, ref) in checks.items():
        assert now <= ref * REGRESSION_BAND, (
            f"{name} regressed beyond {REGRESSION_BAND}x baseline: "
            f"now={now} baseline={ref} (see docs/graph/perf-baseline.json)"
        )


def test_perf_baseline_artifact_is_honest():
    """The committed baseline is machine-readable, per-size, and records
    failures/skips rather than hiding them."""
    doc = json.loads(BASELINE.read_text(encoding="utf-8"))
    sizes = {r["size"] for r in doc["runs"]}
    assert sizes >= {100, 500, 1000, 3000}, sizes
    for r in doc["runs"]:
        if "error" in r or "skipped" in r:
            continue  # recorded, not hidden — exactly what the spec asks
        for key in ("load_ms", "settle_ms", "tick_ms", "heap_mb", "cpu_ms"):
            assert key in r, f"baseline row missing {key}: {r.get('size')}"
        assert r["non_finite"] == 0
        assert "fps" not in r, "no compositor in the node harness — no FPS may be claimed"
