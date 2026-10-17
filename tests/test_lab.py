"""Forge Lab collector tests (cyc9-01, ADR-0060, §9.11 guardrails).

The harness itself is under test: declaration parsing, argv guardrails,
mode gating, receipt validation and honest statuses — all offline with
fake lab checkouts. No real specialist lab is invoked.
"""

import json
import sys
from pathlib import Path

import pytest

from theforge.contracts.types import Producer
from theforge.lab import (
    LabError,
    collect,
    load_lab_decl,
    write_report,
)

PRODUCER = Producer(id="theforge", version="test")


def _repo(tmp_path: Path, name: str, lab: object) -> Path:
    repo = tmp_path / name
    repo.mkdir()
    forge_json = {"forge_id": name, "package": name.replace("-", "_")}
    if lab is not ...:
        forge_json["lab"] = lab
    (repo / "forge.json").write_text(json.dumps(forge_json), encoding="utf-8")
    return repo


FAKE_LAB = """\
import json, sys, pathlib
receipt = pathlib.Path(sys.argv[sys.argv.index("--result-out") + 1])
receipt.parent.mkdir(parents=True, exist_ok=True)
receipt.write_text(json.dumps({
    "schema": "forge/BenchmarkResult/v1",
    "suite": "fake-suite",
    "forge": "fake-forge",
    "mode": "A",
    "created_at": "2026-10-15T21:00:00Z",
    "producer": {"id": "fake-forge", "version": "0.1.0"},
    "external": False,
    "results": [{"scenario_id": "s-1", "verdict": "pass",
                 "metrics": {"precision": {"value": 1.0, "unit": "ratio"}},
                 "duration_ms": 1}],
}))
"""

DECL = {
    "command": ["{python}", "fake_lab.py", "--result-out", "{receipt}"],
    "receipt": ".forge/lab-result.json",
    "modes": ["A"],
    "suite": "fake-suite",
    "timeout_s": 30,
}


def test_load_decl_absent_vs_none(tmp_path):
    undeclared = _repo(tmp_path, "no-lab", ...)
    assert load_lab_decl("no-lab", undeclared, sys.executable) is None
    declared_none = _repo(tmp_path, "lab-off", False)
    assert load_lab_decl("lab-off", declared_none, sys.executable) == "none"


def test_load_decl_rejects_escape_and_bad_token(tmp_path):
    bad = _repo(tmp_path, "bad-esc", {**DECL, "receipt": "../out.json"})
    with pytest.raises(LabError, match="escapes"):
        load_lab_decl("bad-esc", bad, sys.executable)
    bad2 = _repo(tmp_path, "bad-tok", {**DECL, "command": ["{python}", "{evil}"]})
    with pytest.raises(LabError, match="template"):
        load_lab_decl("bad-tok", bad2, sys.executable)
    bad3 = _repo(tmp_path, "bad-cmd", {**DECL, "command": []})
    with pytest.raises(LabError, match="argv"):
        load_lab_decl("bad-cmd", bad3, sys.executable)


def test_collect_ok_with_fake_lab(tmp_path):
    repo = _repo(tmp_path, "fake-forge", DECL)
    (repo / "fake_lab.py").write_text(FAKE_LAB, encoding="utf-8")
    outcomes, interrupted = collect(manifests=[], repos=(repo,), mode="A", repeats=1)
    assert not interrupted
    (out,) = outcomes
    assert out.status == "ok"
    assert out.runs[0].results[0].verdict == "pass"
    assert out.runs[0].forge == "fake-forge"


def test_collect_honest_statuses(tmp_path):
    undeclared = _repo(tmp_path, "no-lab", ...)
    none = _repo(tmp_path, "lab-off", False)
    wrong_mode = _repo(tmp_path, "mode-b-only", {**DECL, "modes": ["B"]})
    outcomes, _ = collect(manifests=[], repos=(undeclared, none, wrong_mode), mode="A")
    status = {o.forge_id: o.status for o in outcomes}
    assert status == {
        "no-lab": "undeclared",
        "lab-off": "none",
        "mode-b-only": "unsupported-mode",
    }


def test_collect_receipt_forge_mismatch_invalid(tmp_path):
    repo = _repo(tmp_path, "other-forge", DECL)
    (repo / "fake_lab.py").write_text(FAKE_LAB, encoding="utf-8")
    outcomes, _ = collect(manifests=[], repos=(repo,), mode="A")
    (out,) = outcomes
    assert out.status == "invalid"
    assert "forge" in out.detail


def test_collect_exit_nonzero(tmp_path):
    repo = _repo(tmp_path, "crash-lab", DECL)
    (repo / "fake_lab.py").write_text("import sys; sys.exit(2)\n", encoding="utf-8")
    outcomes, _ = collect(manifests=[], repos=(repo,), mode="A")
    (out,) = outcomes
    assert out.status == "exit"
    assert "exit:2" in out.detail


def test_mode_c_requires_explicit_optin(tmp_path):
    repo = _repo(tmp_path, "c-lab", {**DECL, "modes": ["C"]})
    with pytest.raises(LabError, match="--allow-external"):
        collect(manifests=[], repos=(repo,), mode="C")


def test_guardrail_bounds(tmp_path):
    repo = _repo(tmp_path, "g-lab", DECL)
    with pytest.raises(LabError, match="repeats"):
        collect(manifests=[], repos=(repo,), repeats=99)
    with pytest.raises(LabError, match="jobs"):
        collect(manifests=[], repos=(repo,), jobs=99)
    with pytest.raises(LabError, match="timeout"):
        collect(manifests=[], repos=(repo,), timeout_s=99999)
    with pytest.raises(LabError, match="mode"):
        collect(manifests=[], repos=(repo,), mode="Z")


def test_write_report_persists_md_and_jsonl(tmp_path):
    repo = _repo(tmp_path, "fake-forge", DECL)
    (repo / "fake_lab.py").write_text(FAKE_LAB, encoding="utf-8")
    skipped = _repo(tmp_path, "no-lab", ...)
    outcomes, interrupted = collect(manifests=[], repos=(repo, skipped), mode="A")
    data = write_report(
        root=tmp_path,
        mode="A",
        outcomes=outcomes,
        producer=PRODUCER,
        out=tmp_path / "bench",
        guardrails={"mode": "A"},
        interrupted=interrupted,
    )
    md = Path(data["report"])
    jsonl = Path(data["results_jsonl"])
    assert md.is_file() and jsonl.is_file()
    text = md.read_text(encoding="utf-8")
    assert "fake-forge" in text and "no-lab" in text
    assert "undeclared" in text  # honest skip, not hidden
    assert data["summary"] == {
        "ran": 1,
        "skipped": 1,
        "blocked": 0,
        "failed": 0,
        "states": {"PASS": 1, "SKIPPED": 1},
        "scenarios": 1,
        "interrupted": False,
    }
    receipt = json.loads(jsonl.read_text(encoding="utf-8").splitlines()[0])
    assert receipt["schema"] == "forge/BenchmarkResult/v1"


def test_env_sanitized_no_credentials(tmp_path):
    """A lab subprocess never inherits API keys (§9.11)."""
    repo = _repo(
        tmp_path,
        "env-lab",
        {
            **DECL,
            "command": ["{python}", "env_lab.py", "{receipt}"],
        },
    )
    (repo / "env_lab.py").write_text(
        "import os, sys, pathlib, json\n"
        "receipt = pathlib.Path(sys.argv[1])\n"
        "receipt.parent.mkdir(parents=True, exist_ok=True)\n"
        "leak = os.environ.get('OPENAI_API_KEY') or os.environ.get('AWS_SECRET_ACCESS_KEY')\n"
        "receipt.write_text(json.dumps({'leak': leak}))\n",
        encoding="utf-8",
    )
    import os

    from theforge.lab import _run_one, load_lab_decl

    decl = load_lab_decl("env-lab", repo, sys.executable)
    saved = os.environ.get("OPENAI_API_KEY")
    os.environ["OPENAI_API_KEY"] = "sk-test-should-not-propagate"
    try:
        _run_one(decl, "A", 0, external=False)
    finally:
        if saved is None:
            os.environ.pop("OPENAI_API_KEY", None)
        else:
            os.environ["OPENAI_API_KEY"] = saved
    leaked = json.loads((repo / ".forge/lab-result.json").read_text())
    assert leaked["leak"] is None
