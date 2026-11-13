"""ONDA 1.5 — anti-false-positive tests for the certification gate engine.

Each test targets a named failure mode from the master prompt:
- constant PASS without evidence
- FAIL converted to UNVERIFIED
- BLOCKED converted to PASS
- missing/empty artifact treated as success
- a single passing check passing a whole dimension
- ambiguous/empty plans counting as passed federation
- stale evidence (SHA drift) accepted as fresh
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from certify_gates import CheckResult, evaluate_gates, gates_report, verdict  # noqa: E402

TS = "2026-01-01T00:00:00+00:00"
REPO = "the-forge"
ALL_REPOS = (REPO, "forge-cli", "forge-portal", "forge-agent-bridge",
             "spark-forge-aws", "spark-forge-azure", "api-forge",
             "platform-forge", "product-forge", "code-atlas-forge",
             "forge-lens", "data-sentinel-forge", "api-sentinel-forge",
             "forge-doctor-api", "forge-doctor-data")


def _states(head: str = "abc123") -> dict:
    return {r: {"repo": r, "exists": True, "head": head,
                "version": "1.0.0", "tags": ["v1.0.0"],
                "index": {"pypi": "PUBLISHED"}} for r in ALL_REPOS}


def _scenario(status: str = "PASS", **over) -> dict:
    s = {"status": status, "steps": [{"check": "x", "ok": True}],
         "commands": ["cmd"], "environment": {}, "os": "Windows",
         "python": "3.11", "repo_shas": {r: "abc123" for r in ALL_REPOS},
         "versions": {REPO: "1.0.0"}, "evidence": {"k": "v"},
         "limitations": []}
    s.update(over)
    return s


def _full_e2e(status: str = "PASS") -> dict:
    names = ("context", "lifecycle", "security", "portal", "standalone",
             "mcp", "bridge",
             "A-aws", "B-azure", "C-api", "D-platform", "E-product",
             "F-doctors", "G-sentinels", "H-atlas", "I-lens",
             "federation-routed", "federation-delegated",
             "federation-multidomain", "federation-ambiguous",
             "federation-partial")
    sc = {n: _scenario(status) for n in names}
    sc["portal"]["steps"] = [{"call": "workspace_resources", "count": 10,
                              "ok": True}]
    sc["security"]["steps"] = [{"check": "a", "refused": True, "ok": True},
                               {"check": "b", "refused": True, "ok": True},
                               {"check": "c", "refused": True, "ok": True}]
    sc["federation-multidomain"]["evidence"] = {"correlation_id": "c1"}
    sc["federation-multidomain"]["steps"] = [
        {"check": "execute:spark-forge-aws", "ok": True},
        {"check": "execute:forge-doctor-api", "ok": True},
    ]
    sc["lifecycle"]["steps"] = [{"step": "I-install-apply"},
                                {"step": "J-install-uninstall",
                                 "user_file_preserved": True}]
    return {"scenarios": sc, "summary": {"PASS": len(names)}}


def _evidence(**over) -> dict:
    e = {"baseline": {"repos": {
                      r: {"exists": True, "has_manifest": True,
                          "role": "forge-protocol-provider",
                          "version": "1.0.0",
                          "resources": {"skills": 1}} for r in ALL_REPOS}},
         "inventory": {"repos": {
                      r: {"exists": True, "resource_total": 5,
                          "resources": {"skill": {
                              "count": 5,
                              "functional": {"units_verified": 5,
                                             "broken": [],
                                             "escaped": []}}}}
                      for r in ALL_REPOS}},
         "e2e": _full_e2e(),
         "lock": {"repos": {r: {"exists": True, "sha": "abc123",
                                "version": "1.0.0",
                                "manifest_checksums": {"m": "x"}}
                           for r in ALL_REPOS},
                  "adapters": {"theforge_sparkforge_aws": "1.0.0"},
                  "contracts": {"forge/v1": "1"}},
         "states": _states(),
         "ci_runs": {w: {"conclusion": "success", "ref": "main",
                         "sha": "abc123", "jobs": {"core": "success"}}
                     for w in ("ecosystem-real", "provider-surface-drift",
                               "release-compat")},
         "release_verify": {"checks": [
             {"package": "api-sentinel-forge==0.1.2", "source": "pypi",
              "status": "VERIFIED",
              "artifact": {"sha256_match": True}},
             {"package": "theforge-cli", "source": "npm",
              "status": "VERIFIED"}]},
         "timestamp": TS, "environment": {}}
    e.update(over)
    return e


def _gate(gates, gid):
    return next(g for g in gates if g.gate_id == gid)


# --- 1. no constant PASS: everything needs evidence -----------------------

def test_no_evidence_no_pass() -> None:
    """With empty evidence every gate must be UNVERIFIED/FAIL — never PASS."""
    gates = evaluate_gates({"e2e": {}, "baseline": {}, "states": {},
                            "ci_runs": {}, "timestamp": TS, "environment": {}})
    assert not any(g.status == "PASS" for g in gates)
    assert verdict(gates) != "PRODUCTION READY"


def test_full_evidence_all_pass() -> None:
    gates = evaluate_gates(_evidence())
    assert all(g.status == "PASS" for g in gates), \
        {g.gate_id: (g.status, g.block_reason) for g in gates}
    assert verdict(gates) == "PRODUCTION READY"


# --- 2. FAIL is never converted to UNVERIFIED ------------------------------

def test_fail_not_masked() -> None:
    e = _evidence()
    e["e2e"]["scenarios"]["security"]["status"] = "FAIL"
    gates = evaluate_gates(e)
    assert _gate(gates, "security_boundaries").status == "FAIL"
    assert verdict(gates) == "NOT READY"


def test_failed_inner_check_fails_gate() -> None:
    e = _evidence()
    e["e2e"]["scenarios"]["security"]["steps"][0]["refused"] = True
    e["e2e"]["scenarios"]["security"]["steps"][0]["ok"] = False
    gates = evaluate_gates(e)
    g = _gate(gates, "security_boundaries")
    assert g.status == "FAIL"
    assert verdict(gates) == "NOT READY"


# --- 3. missing artifact = evidence absence, not success -------------------

def test_missing_scenario_is_unverified_not_pass() -> None:
    e = _evidence()
    del e["e2e"]["scenarios"]["portal"]
    g = _gate(evaluate_gates(e), "portal_real_services")
    assert g.status == "UNVERIFIED"


def test_missing_baseline_repo_fails_resources() -> None:
    e = _evidence()
    e["inventory"] = {}
    g = _gate(evaluate_gates(e), "declared_resources")
    assert g.status in ("FAIL", "UNVERIFIED")
    assert g.status != "PASS"


def test_contracts_requires_provider_manifests_or_declared_role() -> None:
    e = _evidence()
    e["baseline"]["repos"][REPO]["has_manifest"] = False
    e["baseline"]["repos"][REPO]["role"] = None
    g = _gate(evaluate_gates(e), "contracts")
    assert g.status != "PASS"
    e = _evidence()
    e["baseline"]["repos"][REPO]["has_manifest"] = False
    g = _gate(evaluate_gates(e), "contracts")
    assert g.status != "PASS"
    e = _evidence()
    e["baseline"]["repos"][REPO]["has_manifest"] = False
    e["baseline"]["repos"][REPO]["role"] = None
    e["baseline"]["repos"][REPO]["role_justification"] = "installer CLI"
    g = _gate(evaluate_gates(e), "contracts")
    assert g.status == "PASS"


# --- 4. one check never passes a whole dimension ----------------------------

def test_partial_checks_do_not_pass_dimension() -> None:
    """4 of 5 federation sub-scenarios PASS -> dimension must NOT pass."""
    e = _evidence()
    e["e2e"]["scenarios"]["federation-partial"]["status"] = "FAIL"
    g = _gate(evaluate_gates(e), "federated_operations")
    assert g.status == "FAIL"


# --- 5. ambiguous/empty is not a passed federation --------------------------

def test_ambiguous_scenario_not_pass() -> None:
    e = _evidence()
    e["e2e"]["scenarios"]["federation-multidomain"]["status"] = "PASS"
    e["e2e"]["scenarios"]["federation-multidomain"]["steps"] = [
        {"check": "execute:spark-forge-aws", "ok": True}]
    g = _gate(evaluate_gates(e), "federated_operations")
    assert g.status == "FAIL"
    assert "federation:multi-exec" in g.block_reason


def test_correlation_required() -> None:
    e = _evidence()
    e["e2e"]["scenarios"]["federation-multidomain"]["evidence"] = {}
    g = _gate(evaluate_gates(e), "federated_operations")
    assert g.status == "FAIL"


# --- 6. stale evidence rejected --------------------------------------------

def test_lock_drift_fails_version_gate() -> None:
    e = _evidence()
    e["states"][REPO]["head"] = "different-sha"
    g = _gate(evaluate_gates(e), "final_versions_traceable")
    assert g.status == "FAIL"
    assert "lock:no-drift" in g.block_reason


def test_missing_lock_fails_version_gate() -> None:
    e = _evidence()
    e["lock"] = None
    g = _gate(evaluate_gates(e), "final_versions_traceable")
    assert g.status in ("FAIL", "UNVERIFIED")
    assert g.status != "PASS"


# --- 7. CI gate computed, never constant -------------------------------------

def test_ci_failure_blocks() -> None:
    e = _evidence()
    e["ci_runs"]["release-compat"]["conclusion"] = "failure"
    g = _gate(evaluate_gates(e), "ci_federated")
    assert g.status == "FAIL"
    assert verdict(evaluate_gates(e)) == "NOT READY"


def test_ci_absent_unverified() -> None:
    e = _evidence()
    e["ci_runs"] = {}
    g = _gate(evaluate_gates(e), "ci_federated")
    assert g.status == "FAIL"  # checks ran but found no evidence


# --- 8. index states --------------------------------------------------------

def test_not_published_blocks() -> None:
    e = _evidence()
    e["states"][REPO]["index"]["pypi"] = "NOT_PUBLISHED"
    g = _gate(evaluate_gates(e), "pypi_npm_publication")
    assert g.status == "FAIL"


def test_unverified_index_not_pass() -> None:
    e = _evidence()
    e["states"][REPO]["index"]["pypi"] = "UNVERIFIED"
    g = _gate(evaluate_gates(e), "pypi_npm_publication")
    assert g.status == "FAIL"


# --- 9. scenario evidence fields required ------------------------------------

def test_scenario_without_onda13_fields_fails() -> None:
    e = _evidence()
    e["e2e"]["scenarios"]["A-aws"] = {"status": "PASS", "steps": [{"ok": True}]}
    g = _gate(evaluate_gates(e), "specialists_standalone")
    assert g.status == "FAIL"
    assert "scenario:fields" in g.block_reason


def test_gate_result_model_fields() -> None:
    """GateResult carries the typed evidence model (Onda 1.2)."""
    gates = evaluate_gates(_evidence())
    g = gates[0]
    for attr in ("gate_id", "name", "scope", "required_checks", "status",
                 "acceptance_criteria", "provenance", "timestamp"):
        assert getattr(g, attr) is not None or attr == "block_reason"
    rep = gates_report(gates)
    assert rep["kind"] == "forge/certification-gates/1"
    assert "verdict" in rep and "dimensions" in rep


def test_check_result_shape() -> None:
    c = CheckResult("x", True)
    assert c.ok and c.id == "x"
