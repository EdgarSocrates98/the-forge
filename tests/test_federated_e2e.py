"""Fail-closed certification of ``scripts/federated_e2e.py`` (cycle 16.1 §5.1).

Before this wave, evals were counted in the summary but never influenced
the exit code — a required eval could fail, never run, or contradict
itself and the gate still exited 0. These tests pin the new behavior:
required evals gate the exit code, optional evals don't, every blocking
reason lands on the receipt, and runner/receipt errors are blocking
outcomes, never silent passes.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import scripts.federated_e2e as fe

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "federated_e2e.py"

# ---------------------------------------------------------------------------
# fixture — a minimal workspace covering every scenario's forge set
# ---------------------------------------------------------------------------

_FORGE_RESOURCES: dict[str, list[dict]] = {
    "spark-forge-aws": [
        {
            "id": "skill-spark-tuning",
            "kind": "skill",
            "location": "skills/spark/SKILL.md",
            "tags": ["glue", "emr", "spark", "job", "oom", "shuffle", "skew"],
            "availability": "available",
        },
    ],
    "data-sentinel-forge": [
        {
            "id": "rule-quarantine",
            "kind": "rule",
            "location": "rules/quarantine.yaml",
            "tags": ["data", "quality", "quarantine", "validation", "rules"],
            "availability": "available",
        },
    ],
    "the-forge": [
        {
            "id": "kb-routing",
            "kind": "knowledge",
            "location": "knowledge/routing.md",
            "tags": ["control", "plane", "routing"],
            "availability": "available",
        },
    ],
    "forge-doctor-data": [
        {
            "id": "eval-doctor",
            "kind": "eval",
            "location": "evals/doc.yaml",
            "tags": ["doctor", "diagnostics"],
            "availability": "available",
        },
    ],
    "code-atlas-forge": [
        {
            "id": "agent-indexer",
            "kind": "agent",
            "location": "agents/indexer.md",
            "tags": ["index", "codebase", "symbols", "call", "graph"],
            "availability": "available",
        },
    ],
    "api-forge": [
        {
            "id": "contract-openapi",
            "kind": "contract",
            "location": "contracts/openapi.yaml",
            "tags": ["openapi", "contract", "breaking", "change", "rest", "api"],
            "availability": "available",
        },
    ],
    "api-sentinel-forge": [
        {
            "id": "kb-incidents",
            "kind": "knowledge",
            "location": "knowledge/incidents.md",
            "tags": ["sentinel", "reliability", "incident"],
            "availability": "available",
        },
    ],
    "forge-doctor-api": [
        {
            "id": "eval-doctor-api",
            "kind": "eval",
            "location": "evals/api.yaml",
            "tags": ["doctor", "api", "diagnostics"],
            "availability": "available",
        },
    ],
    "product-forge": [
        {
            "id": "kb-product",
            "kind": "knowledge",
            "location": "knowledge/pm.md",
            "tags": ["product", "intelligence", "dashboard"],
            "availability": "available",
        },
    ],
    "forge-agent-bridge": [
        {
            "id": "agent-bridge",
            "kind": "agent",
            "location": "agents/bridge.md",
            "tags": ["bridge", "handoff"],
            "availability": "available",
        },
    ],
    "platform-forge": [
        {
            "id": "skill-finops",
            "kind": "skill",
            "location": "skills/finops/SKILL.md",
            "tags": ["platform", "finops"],
            "availability": "available",
        },
    ],
    "spark-forge-azure": [
        {
            "id": "skill-azure-spark",
            "kind": "skill",
            "location": "skills/azure/SKILL.md",
            "tags": ["databricks", "synapse", "adls", "fabric", "spark", "job", "azure"],
            "availability": "available",
        },
    ],
}


def _build_workspace(ws: Path, *, git_init: bool = False) -> Path:
    ws.mkdir(parents=True, exist_ok=True)
    for fid, resources in _FORGE_RESOURCES.items():
        d = ws / fid
        d.mkdir(parents=True)
        (d / "forge.json").write_text(json.dumps({"forge_id": fid}), encoding="utf-8")
        (d / "forge.agentic.json").write_text(
            json.dumps(
                {
                    "schema": "forge/SpecialistAgenticManifest/v1",
                    "id": fid,
                    "version": "1.0.0",
                    "resources": resources,
                }
            ),
            encoding="utf-8",
        )
        for r in resources:
            p = d / str(r["location"])
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(f"# {fid} {r['id']}\n", encoding="utf-8")
    if git_init and shutil.which("git"):
        repo = ws / "the-forge"
        env = {
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t",
            "PATH": os.environ.get("PATH", ""),
        }
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True, env=env)
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True, env=env)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=repo, check=True, env=env)
    return ws


# ---------------------------------------------------------------------------
# eval_state — the per-check classifier
# ---------------------------------------------------------------------------


def test_eval_state_closed_outcomes() -> None:
    assert fe.eval_state({"ok": True}) == ("ok", "")
    assert fe.eval_state({"ok": False}) == ("failed", "ok=false")
    assert fe.eval_state({"ok": False, "error": "boom"}) == ("failed", "boom")
    assert fe.eval_state({"verdict": "SKIPPED", "reason": "empty"}) == ("not-run", "empty")
    assert fe.eval_state({"verdict": "UNVERIFIED"}) == ("not-run", "UNVERIFIED")
    assert fe.eval_state({}) == ("invalid", "no result field")


def test_eval_state_contradictory() -> None:
    state, _ = fe.eval_state({"ok": True, "error": "late failure"})
    assert state == "contradictory"
    state, _ = fe.eval_state({"ok": True, "verdict": "FAIL"})
    assert state == "contradictory"


# ---------------------------------------------------------------------------
# compute_gating — scenarios + evals both gate the exit code
# ---------------------------------------------------------------------------


def _receipt(scenarios: dict | None = None, evals: dict | None = None) -> dict:
    return {
        "scenarios": scenarios or {},
        "evals": evals or {"routing": [], "resources": []},
    }


def test_gating_clean_receipt_has_no_reasons() -> None:
    rc = _receipt(
        scenarios={"S1": {"verdict": "PASS"}},
        evals={
            "routing": [{"task": t, "ok": True} for _s, t, _a in fe.ROUTING_EVALS]
            + [{"task": "zzzqxkvbnm wqkfj", "ok": True}],
            "resources": [
                {"case": "right-resource", "ok": True},
                {"case": "nonexistent", "ok": True},
                {"case": "manifest-poisoning-traversal", "ok": True},
            ],
        },
    )
    assert fe.compute_gating(rc) == []


def test_gating_failed_eval_blocks() -> None:
    rc = _receipt(
        evals={
            "routing": [{"task": fe.ROUTING_EVALS[0][1], "ok": False}],
            "resources": [],
        }
    )
    reasons = fe.compute_gating(rc)
    assert any(r.startswith("eval-failed:routing:") for r in reasons)
    # every other expected required eval is also a not-run blocking reason
    assert sum(r.startswith("eval-not-run:") for r in reasons) >= 5


def test_gating_missing_eval_blocks_as_not_run() -> None:
    rc = _receipt(evals={"routing": [], "resources": []})
    reasons = fe.compute_gating(rc)
    expected_missing = len(fe.EXPECTED_ROUTING_EVALS) + len(fe.EXPECTED_RESOURCE_EVALS)
    not_run = [r for r in reasons if r.startswith("eval-not-run:")]
    assert len(not_run) == expected_missing


def test_gating_contradictory_eval_blocks() -> None:
    rc = _receipt(
        evals={
            "routing": [{"task": fe.ROUTING_EVALS[0][1], "ok": True, "error": "late"}],
            "resources": [],
        }
    )
    assert any(r.startswith("eval-contradictory:") for r in fe.compute_gating(rc))


def test_gating_optional_eval_failure_not_blocking() -> None:
    rc = _receipt(
        evals={
            "routing": [{"task": t, "ok": True} for _s, t, _a in fe.ROUTING_EVALS]
            + [{"task": "zzzqxkvbnm wqkfj", "ok": True}]
            + [{"task": "probe", "ok": False, "required": False}],
            "resources": [
                {"case": "right-resource", "ok": True},
                {"case": "nonexistent", "ok": True},
                {"case": "manifest-poisoning-traversal", "ok": True},
            ],
        }
    )
    assert fe.compute_gating(rc) == []


def test_gating_failed_scenario_and_missing_verdict_block() -> None:
    rc = _receipt(
        scenarios={"S1": {"verdict": "FAIL"}, "S2": {}},
        evals={
            "routing": [{"task": t, "ok": True} for _s, t, _a in fe.ROUTING_EVALS]
            + [{"task": "zzzqxkvbnm wqkfj", "ok": True}],
            "resources": [
                {"case": "right-resource", "ok": True},
                {"case": "nonexistent", "ok": True},
                {"case": "manifest-poisoning-traversal", "ok": True},
            ],
        },
    )
    reasons = fe.compute_gating(rc)
    assert "scenario:S1:FAIL" in reasons
    assert "scenario:S2:missing-verdict" in reasons


def test_finalize_evals_normalizes_entries() -> None:
    rc = _receipt(evals={"routing": [{"task": "x", "ok": True}], "resources": []})
    fe.finalize_evals(rc)
    entry = rc["evals"]["routing"][0]
    assert entry["id"] == "routing:x"
    assert entry["required"] is True
    assert entry["state"] == "ok"
    assert entry["verdict"] == "PASS"


# ---------------------------------------------------------------------------
# end-to-end — real workspaces, real exit codes
# ---------------------------------------------------------------------------


def test_full_run_exit_zero_with_sha_binding(tmp_path: Path) -> None:
    ws = _build_workspace(tmp_path / "forjas", git_init=True)
    out = tmp_path / "receipt.json"
    rc = fe.main(["--workspace", str(ws), "--out", str(out)])
    receipt = json.loads(out.read_text(encoding="utf-8"))
    assert rc == 0, receipt["gating"]["blocking_reasons"]
    assert receipt["gating"]["blocking_reasons"] == []
    assert receipt["gating"]["required_evals"] > 0
    # SHA↔evidence binding (§5.6): captured live, equals rev-parse HEAD.
    if shutil.which("git"):
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ws / "the-forge",
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert receipt["tested_commit"]["sha"] == head
        assert receipt["repo_shas"]["the-forge"] == head
    for entries in receipt["evals"].values():
        for e in entries:
            assert "required" in e and "state" in e and "id" in e


def _sabotage_routing_eval(ws: Path) -> None:
    """Strip every routing term from spark-forge-aws's catalog — the
    required routing eval for B-aws-full can then hit no forge."""
    manifest = json.loads(
        (ws / "spark-forge-aws" / "forge.agentic.json").read_text(encoding="utf-8")
    )
    manifest["resources"] = [
        {
            "id": "skill-misc",
            "kind": "skill",
            "location": "skills/misc/SKILL.md",
            "tags": ["unrelated"],
            "availability": "available",
        }
    ]
    (ws / "spark-forge-aws" / "forge.agentic.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    p = ws / "spark-forge-aws" / "skills" / "misc" / "SKILL.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("# misc\n", encoding="utf-8")


def test_deliberate_eval_failure_fails_closed(tmp_path: Path) -> None:
    ws = _build_workspace(tmp_path / "forjas")
    _sabotage_routing_eval(ws)
    out = tmp_path / "receipt.json"
    rc = fe.main(["--workspace", str(ws), "--out", str(out)])
    receipt = json.loads(out.read_text(encoding="utf-8"))
    assert rc == 1
    assert any(
        r.startswith("eval-failed:routing:") or r.startswith("eval-not-run:routing:")
        for r in receipt["gating"]["blocking_reasons"]
    )


def test_runner_exception_is_blocking_outcome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = _build_workspace(tmp_path / "forjas")

    def _boom(*a: object, **kw: object) -> dict:
        raise RuntimeError("injected runner failure")

    monkeypatch.setattr(fe, "scenario_subset", _boom)
    out = tmp_path / "receipt.json"
    rc = fe.main(["--workspace", str(ws), "--out", str(out)])
    assert rc == 2
    receipt = json.loads(out.read_text(encoding="utf-8"))
    assert receipt["runner_error"]["type"] == "RuntimeError"
    assert any("runner-error" in r for r in receipt["gating"]["blocking_reasons"])


def test_receipt_write_error_fails_closed(tmp_path: Path) -> None:
    ws = _build_workspace(tmp_path / "forjas")
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x", encoding="utf-8")
    # --out under a regular file: mkdir/write both fail → blocking.
    rc = fe.main(["--workspace", str(ws), "--out", str(blocker / "receipt.json")])
    assert rc == 2


def test_receipt_validation_rejects_corrupt(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    errors = fe._validate_receipt(bad)
    assert errors and errors[0].startswith("receipt-unreadable")
    good = tmp_path / "good.json"
    good.write_text(json.dumps({"schema": "forge/FederatedE2E/v1"}), encoding="utf-8")
    errors = fe._validate_receipt(good)
    assert any("missing" in e for e in errors)


def test_subprocess_exit_code_propagates(tmp_path: Path) -> None:
    """CI consumption: `python scripts/federated_e2e.py` must exit nonzero —
    the same code `main()` computes."""
    ws = _build_workspace(tmp_path / "forjas")
    _sabotage_routing_eval(ws)
    out = tmp_path / "receipt.json"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--workspace", str(ws), "--out", str(out)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1, proc.stderr[-500:]
