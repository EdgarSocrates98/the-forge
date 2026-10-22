"""lf-0038 (install-2.0 §7): evals taxonomy, §7.2 ops, §7.3 security, §7.4 flow."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from theforge import evals as fevals
from theforge.errors import UsageError

ROOT = Path(__file__).resolve().parents[1]


# --- §7.1: classified inventory -------------------------------------------------


def test_catalog_covers_all_four_kinds():
    kinds = {row["kind"] for row in fevals.catalog()}
    assert kinds == {
        "developer",
        "runtime-decision",
        "output-verification",
        "host-conformance",
    }
    counts = {}
    for row in fevals.catalog():
        counts[row["kind"]] = counts.get(row["kind"], 0) + 1
    assert counts["developer"] >= 2
    assert all(counts[k] >= 1 for k in kinds)


def test_manifest_suites_validate_as_context_entries():
    from theforge import _forgecontext as fctx

    entries = fevals.manifest_suites()
    assert {e["kind"] for e in entries} == set(fctx.EVAL_KINDS)
    problems: list[str] = []
    for i, entry in enumerate(entries):
        fctx._eval_suite(entry, problems, f"$.eval_suites[{i}]")
    assert problems == []


def test_context_manifest_carries_evals_and_ops(tmp_path):
    from theforge import _forgecontext as fctx
    from theforge import _installkit as kit
    from theforge.install.service import _context_manifest, _spec

    ctx = kit.InstallContext(
        spec=_spec(),
        scope="project",
        root=tmp_path,
        state_dir=tmp_path / ".forge/install",
        profile="recommended",
        hosts=(),
        dry_run=True,
        options={},
    )
    manifest = _context_manifest(ctx)
    assert fctx.validate_manifest(manifest) == []
    ops = manifest["discovery"]["ops"]
    for op in (
        "evals.list",
        "evals.describe",
        "evals.run",
        "evals.result",
        "verification.plan",
        "verification.run",
    ):
        assert op in ops, f"missing op {op}"
    declared = {c["id"] for c in manifest["discovery"]["commands"]}
    assert set(ops.values()) <= declared
    kinds = {s["kind"] for s in manifest["eval_suites"]}
    assert kinds == set(fctx.EVAL_KINDS)
    assert manifest["capabilities"]["evals"]["count"] == len(manifest["eval_suites"])


# --- §7.3: security ---------------------------------------------------------------

_SECRET = "expected-agent-must-never-leak-7f3a9b"


def _sealed_suite(tmp_path: Path) -> fevals.EvalSuite:
    sealed = tmp_path / "holdout.json"
    sealed.write_text(json.dumps({"cases": [{"expected": _SECRET}]}), encoding="utf-8")
    return fevals.EvalSuite(
        id="synthetic-holdout",
        kind="developer",
        description="synthetic suite with a sealed holdout file",
        argv=("{python}", "-c", "print('ok')"),
        environment="real",
        holdouts=("holdout.json",),
        baselines=("holdout.json",),
    )


def test_holdout_answers_never_exposed(tmp_path, monkeypatch):
    """§7.3: an agent-facing describe/catalog call exposes count + sha256 of a
    holdout — never the expected answers themselves."""
    suite = _sealed_suite(tmp_path)
    monkeypatch.setattr(fevals, "SUITES", (*fevals.SUITES, suite))
    doc = fevals.describe("synthetic-holdout", root=tmp_path)
    blob = json.dumps(doc)
    assert _SECRET not in blob
    assert doc["holdouts"]["count"] == 1
    assert doc["holdouts"]["content"].startswith("sealed")
    resolved = doc["holdouts"]["resolved"]
    assert resolved and len(resolved[0]["sha256"]) == 64
    # catalog rows are metadata-only — no content field at all
    row = next(r for r in fevals.catalog() if r["id"] == "synthetic-holdout")
    assert _SECRET not in json.dumps(row)


def test_describe_unknown_suite_refused():
    with pytest.raises(UsageError):
        fevals.describe("no-such-suite")


def test_baselines_hash_recorded(tmp_path, monkeypatch):
    """File inputs land in the receipt as path + sha256 — tamper-evident."""
    baseline = tmp_path / "base.jsonl"
    baseline.write_text("{}\n", encoding="utf-8")
    suite = fevals.EvalSuite(
        id="synthetic-baseline",
        kind="runtime-decision",
        description="synthetic suite with a file input",
        argv=("{python}", "-c", "import sys; sys.exit(0)"),
        environment="real",
        inputs=("baseline",),
    )
    monkeypatch.setattr(fevals, "SUITES", (*fevals.SUITES, suite))
    receipt = fevals.run_suite(tmp_path, "synthetic-baseline", inputs={"baseline": str(baseline)})
    assert receipt["verdict"] == "pass"
    import hashlib

    assert receipt["inputs_recorded"]["baseline"]["sha256"] == hashlib.sha256(
        baseline.read_bytes()
    ).hexdigest()
    # tamper: rewriting the file yields a different recorded digest on re-run
    baseline.write_text('{"tampered": true}\n', encoding="utf-8")
    receipt2 = fevals.run_suite(
        tmp_path, "synthetic-baseline", inputs={"baseline": str(baseline)}
    )
    assert (
        receipt2["inputs_recorded"]["baseline"]["sha256"]
        != receipt["inputs_recorded"]["baseline"]["sha256"]
    )


def test_missing_inputs_blocked_not_skipped(tmp_path):
    receipt = fevals.run_suite(tmp_path, "lab-gate")
    assert receipt["verdict"] == "blocked"
    assert sorted(receipt["unresolved"]) == ["input:baseline", "input:results"]
    assert "argv" not in receipt  # never executed


def test_simulated_marker(tmp_path):
    row = next(r for r in fevals.catalog() if r["id"] == "lab-collect")
    assert row["environment"] == "simulated"
    doc = fevals.describe("lab-collect", root=tmp_path)
    assert doc["proof_note"].startswith("simulated")


# --- §7.4: plan → run → evidence --------------------------------------------------


def test_plan_selects_by_triggers_and_never_executes(tmp_path):
    doc = fevals.plan(["src/theforge/evals.py"], risk="low")
    assert doc["schema"] == fevals.PLAN_SCHEMA
    selected = {s["suite"] for s in doc["selected"]}
    assert "unit-tests" in selected  # src/** trigger
    assert "lab-gate" not in selected  # no triggers; not selected at low
    assert (tmp_path / ".forge").exists() is False  # plan writes nothing
    for s in doc["selected"]:
        if s["missing_inputs"]:
            assert s["status"] == "blocked"


def test_plan_empty_selection_escalates(tmp_path):
    doc = fevals.plan(["README.nomatch"], risk="micro")
    assert any("escalated" in r for r in doc["reasons"])
    assert len(doc["selected"]) == len(fevals.SUITES)


def test_run_plan_explicit_verdicts(tmp_path, monkeypatch):
    ok = fevals.EvalSuite(
        id="t-ok",
        kind="developer",
        description="passes",
        argv=("{python}", "-c", "print('ok')"),
        environment="real",
    )
    bad = fevals.EvalSuite(
        id="t-fail",
        kind="developer",
        description="fails",
        argv=("{python}", "-c", "import sys; sys.exit(3)"),
        environment="real",
    )
    needy = fevals.EvalSuite(
        id="t-needy",
        kind="developer",
        description="needs input",
        argv=("{python}", "-c", "print('{arg}')"),
        environment="real",
        inputs=("arg",),
    )
    monkeypatch.setattr(fevals, "SUITES", (ok, bad, needy))
    plan_doc = fevals.plan(["x"], risk="high")
    doc = fevals.run_plan(tmp_path, plan_doc)
    assert doc["verdict"] == "fail"
    verdicts = {r["suite"]: r["verdict"] for r in doc["results"]}
    assert verdicts == {"t-ok": "pass", "t-fail": "fail", "t-needy": "blocked"}
    # evidence persisted + readable via evals.result
    again = fevals.result(tmp_path, doc["receipt_id"])
    assert again["verdict"] == "fail"
    assert "inconclusive" in json.dumps(doc) or "blocked" in json.dumps(doc)


def test_run_plan_rejects_foreign_doc(tmp_path):
    with pytest.raises(UsageError):
        fevals.run_plan(tmp_path, {"schema": "theforge/SomethingElse/v1"})


def test_result_refuses_traversal(tmp_path):
    with pytest.raises(UsageError):
        fevals.result(tmp_path, "../escape")
    with pytest.raises(UsageError):
        fevals.result(tmp_path, "nonexistent")
