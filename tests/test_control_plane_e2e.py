"""E2E: task delegation to a real specialist checkout (FASE 13 Cenário A/D).

Executes the real argv path end-to-end — ``task run`` →
``resolve_command`` → subprocess against the sibling checkout — no
mocks. Where a checkout's deps are absent the honest outcome is
FAILED/BLOCKED with evidence, never a fabricated COMPLETED.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from theforge import delegation, specialists
from theforge.contracts.base import to_dict

WORKSPACE = Path(__file__).resolve().parents[2]


def _pyspark_project(tmp_path: Path) -> Path:
    (tmp_path / "jobs").mkdir()
    (tmp_path / "jobs" / "etl.py").write_text(
        "from pyspark.sql import SparkSession\n"
        "spark = SparkSession.builder.getOrCreate()\n"
        "df = spark.read.parquet('s3://bucket/in')\n"
        "df.groupBy('k').count().write.parquet('s3://bucket/out')\n",
        encoding="utf-8",
    )
    return tmp_path


def _aws_view() -> specialists.SpecialistView | None:
    views = specialists.collect(workspace_root=WORKSPACE, probe_cli=False)
    return next(
        (v for v in views if v.manifest is not None and v.lifecycle.provider == "spark-forge-aws"),
        None,
    )


@pytest.mark.skipif(
    not (WORKSPACE / "spark-forge-aws" / "forge.agentic.json").is_file(),
    reason="spark-forge-aws checkout with agentic manifest required",
)
def test_e2e_delegate_analyze_pyspark_to_aws_checkout(tmp_path):
    view = _aws_view()
    assert view is not None and view.manifest is not None
    wf = next(w for w in view.manifest.workflows if w.id == "analyze-pyspark")
    argv = specialists.resolve_command(wf.command, view=view, target=str(tmp_path))
    assert argv is not None, "could not resolve delegation argv for aws checkout"

    proj = _pyspark_project(tmp_path)
    argv = specialists.resolve_command(
        wf.command, view=view, target=str(proj / "jobs")
    )
    req = delegation.new_request(
        intent="analyze the pyspark pipeline",
        provider=view.lifecycle.provider,
        execution_mode=wf.mode,
        command=argv,
    )
    result = delegation.execute(req)
    # The checkout is pure-stdlib: a real analysis must COMPLETE with exit 0.
    assert result.stage == "COMPLETED", (
        f"stage={result.stage} stderr={result.stderr_tail[-3:] if result.stderr_tail else []}"
    )
    assert result.exit_code == 0
    assert result.elapsed_ms > 0
    payload = json.dumps(to_dict(result))
    assert payload  # result serializes to the contract


def test_host_agentic_never_reports_completed_without_execution():
    req = delegation.new_request(
        intent="use the glue specialist",
        provider="spark-forge-aws",
        execution_mode="HOST_AGENTIC",
        command=["echo", "x"],
    )
    result = delegation.execute(req)
    assert result.stage == "PREPARED" and result.exit_code is None


def test_e2e_missing_checkout_is_blocked_not_invented(tmp_path):
    """A provider whose CLI can't resolve gets BLOCKED, not fabricated."""
    view = specialists.SpecialistView(
        lifecycle=__import__("theforge.contracts.specialist", fromlist=["x"]).SpecialistLifecycle(
            provider="ghost-forge", installation_state="NOT_INSTALLED"
        ),
        manifest=None,
    )
    assert specialists.resolve_command(["{cli}", "doctor"], view=view) is None


def test_cli_subprocess_specialists_list():
    """The real CLI surface works: ``python -m theforge specialists list``."""
    env = {"PYTHONPATH": str(WORKSPACE / "the-forge" / "src")}
    import os

    proc = subprocess.run(
        [sys.executable, "-m", "theforge", "specialists", "list",
         "--root", str(WORKSPACE), "--json"],
        capture_output=True,
        text=True,
        env={**os.environ, **env},
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr[-300:]
    doc = json.loads(proc.stdout)
    assert doc["specialists"], "specialists list produced no rows"
    assert any(s["agentic_manifest"] for s in doc["specialists"])
