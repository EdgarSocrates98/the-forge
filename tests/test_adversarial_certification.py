"""Onda 11 — adversarial certification fixtures.

Every mutation below tampers with ONE piece of the otherwise-valid
evidence bundle (``_evidence`` from ``test_certify_gates``). The honest
certifier must NEVER emit ``PRODUCTION READY`` on tampered evidence —
each case asserts ``verdict(...) != 'PRODUCTION READY'`` and names the
gate expected to catch the tamper.

30 fixtures. Adding a gate? Add the adversarial case that breaks it.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from certify_gates import evaluate_gates, verdict  # noqa: E402
from tests.test_certify_gates import REPO, _evidence  # noqa: E402

M = Callable[[dict], None]


def _del(key: str) -> M:
    return lambda e: e.pop(key, None)


def _scenario(name: str, **patch: object) -> M:
    def m(e: dict) -> None:
        e["e2e"]["scenarios"].setdefault(name, {"status": "PASS",
                                                "steps": [{"ok": True}]})
        e["e2e"]["scenarios"][name].update(patch)
    return m


def _drop_scenario(name: str) -> M:
    return lambda e: e["e2e"]["scenarios"].pop(name, None)


def _step_ok_false(name: str) -> M:
    return _scenario(name, steps=[{"check": "tampered", "ok": False}])


def _repo_field(field: str, value: object) -> M:
    return lambda e: e["baseline"]["repos"][REPO].update({field: value})


def _inv_field(field: str, value: object) -> M:
    return lambda e: e["inventory"]["repos"][REPO].update({field: value})


def _drop_inv_repo() -> M:
    return lambda e: e["inventory"]["repos"].pop(REPO, None)


def _drift() -> M:
    return lambda e: e["states"][REPO].update({"head": "deadbeef" * 5})


def _ci(conclusion: str | None) -> M:
    def m(e: dict) -> None:
        if conclusion is None:
            e["ci_runs"] = {}
        else:
            for w in e["ci_runs"]:
                e["ci_runs"][w]["conclusion"] = conclusion
    return m


def _index(state: str) -> M:
    return lambda e: e["states"][REPO].update(
        {"index": {"pypi": state}})


def _summary_lie() -> M:
    """Summary claims all-PASS while a scenario is FAIL — honesty check."""
    def m(e: dict) -> None:
        e["e2e"]["scenarios"]["A-aws"]["status"] = "FAIL"
        e["e2e"]["summary"] = {"PASS": len(e["e2e"]["scenarios"])}
    return m


def _no_steps() -> M:
    return _scenario("federation-routed", steps=[])


def _single_exec() -> M:
    return _scenario("federation-multidomain",
                     steps=[{"check": "execute:a", "ok": True}])


def _no_correlation() -> M:
    return _scenario("federation-multidomain", evidence={})


ADVERSARIAL: list[tuple[str, M, str]] = [
    # --- artifact absence (never vacuous PASS) ---
    ("baseline-deleted", _del("baseline"), "contracts"),
    ("baseline-empty", lambda e: e["baseline"].update({"repos": {}}),
     "contracts"),
    ("e2e-deleted", _del("e2e"), "federated_operations"),
    ("lock-deleted", _del("lock"), "final_versions_traceable"),
    ("inventory-deleted", _del("inventory"), "declared_resources"),
    ("ci-deleted", _ci(None), "ci_federated"),
    # --- manifest/role tampering ---
    ("provider-manifest-removed", _repo_field("has_manifest", False),
     "contracts"),
    ("role-and-manifest-removed",
     lambda e: e["baseline"]["repos"][REPO].update(
         {"has_manifest": False, "role": None,
          "role_justification": None}), "contracts"),
    # --- scenario tampering ---
    ("context-scenario-fail", _scenario("context", status="FAIL"),
     "contracts"),
    ("context-steps-empty", _scenario("context", steps=[]), "contracts"),
    ("lifecycle-missing", _drop_scenario("lifecycle"), "install_lifecycle"),
    ("lifecycle-fail", _scenario("lifecycle", status="FAIL"),
     "install_lifecycle"),
    ("lifecycle-inner-step-fail", _step_ok_false("lifecycle"),
     "install_lifecycle"),
    ("routed-missing", _drop_scenario("federation-routed"),
     "federated_operations"),
    ("routed-no-steps", _no_steps(), "federated_operations"),
    ("delegated-fail", _scenario("federation-delegated", status="FAIL"),
     "federated_operations"),
    ("multidomain-single-exec", _single_exec(), "federated_operations"),
    ("multidomain-no-correlation", _no_correlation(),
     "federated_operations"),
    ("ambiguous-fail", _scenario("federation-ambiguous", status="FAIL"),
     "federated_operations"),
    ("partial-missing", _drop_scenario("federation-partial"),
     "federated_operations"),
    # --- security/portal/domain ---
    ("security-missing", _drop_scenario("security"), "security_boundaries"),
    ("security-inner-fail", _step_ok_false("security"),
     "security_boundaries"),
    ("portal-missing", _drop_scenario("portal"), "portal_real_services"),
    ("portal-fail", _scenario("portal", status="FAIL"),
     "portal_real_services"),
    ("domain-aws-fail", _scenario("A-aws", status="FAIL"),
     "specialists_standalone"),
    # --- inventory tampering ---
    ("repo-resources-zeroed", _inv_field("resource_total", 0),
     "declared_resources"),
    ("repo-inventory-missing", _drop_inv_repo(), "declared_resources"),
    # --- lock/version drift ---
    ("lock-sha-drift", _drift(), "final_versions_traceable"),
    ("lock-repo-dropped",
     lambda e: e["lock"]["repos"].pop(REPO, None),
     "final_versions_traceable"),
    # --- CI/index ---
    ("ci-failure", _ci("failure"), "ci_federated"),
    ("ci-cancelled", _ci("cancelled"), "ci_federated"),
    ("index-not-published", _index("NOT_PUBLISHED"),
     "pypi_npm_publication"),
    ("index-unverified", _index("UNVERIFIED"), "pypi_npm_publication"),
    # --- Onda 2 extension: SHA binding, jobs, lock completeness ---
    ("e2e-stale-sha",
     lambda e: [s["repo_shas"].update({"forge-cli": "deadbeef"})
                for s in e["e2e"]["scenarios"].values()],
     "final_versions_traceable"),
    ("e2e-repo-unrecorded",
     lambda e: [s["repo_shas"].pop("forge-lens", None)
                for s in e["e2e"]["scenarios"].values()],
     "final_versions_traceable"),
    ("ci-wrong-sha",
     lambda e: e["ci_runs"]["ecosystem-real"].update(
         {"sha": "notthelockedsha"}), "ci_federated"),
    ("ci-job-failed",
     lambda e: e["ci_runs"]["release-compat"]["jobs"].update(
         {"core": "failure"}), "ci_federated"),
    ("ci-jobs-absent",
     lambda e: e["ci_runs"]["ecosystem-real"].update({"jobs": {}}),
     "ci_federated"),
    ("lock-adapters-emptied",
     lambda e: e["lock"].update({"adapters": {}}),
     "final_versions_traceable"),
    ("lock-contracts-removed",
     lambda e: e["lock"].pop("contracts", None),
     "final_versions_traceable"),
    ("lock-entry-fields-stripped",
     lambda e: e["lock"]["repos"][REPO].pop("manifest_checksums", None),
     "final_versions_traceable"),
    ("lock-14-of-15",
     lambda e: e["lock"]["repos"].pop("forge-doctor-data", None),
     "final_versions_traceable"),
    ("version-trinity-diverged",
     lambda e: e["baseline"]["repos"][REPO].update(
         {"version": "9.9.9"}), "final_versions_traceable"),
    ("state-version-removed",
     lambda e: e["states"]["forge-portal"].pop("version", None),
     "final_versions_traceable"),
    ("resources-broken-unit",
     lambda e: e["inventory"]["repos"][REPO]["resources"]["skill"]
         ["functional"].update({"broken": ["skill/x (0 bytes)"]}),
     "declared_resources"),
    ("resources-symlink-escape",
     lambda e: e["inventory"]["repos"][REPO]["resources"]["skill"]
         ["functional"].update({"escaped": ["skills/../etc"]}),
     "declared_resources"),
    ("resources-no-functional-pass",
     lambda e: e["inventory"]["repos"][REPO]["resources"]["skill"]
         .pop("functional", None),
     "declared_resources"),
    ("release-verify-absent", _del("release_verify"),
     "pypi_npm_publication"),
    ("release-install-failed",
     lambda e: e["release_verify"]["checks"][0].update(
         {"status": "FAILED"}), "pypi_npm_publication"),
    ("release-checksum-mismatch",
     lambda e: e["release_verify"]["checks"][0]["artifact"].update(
         {"sha256_match": False}), "pypi_npm_publication"),
    # --- honesty ---
    ("summary-lies-pass", _summary_lie(), "specialists_standalone"),
]


@pytest.mark.parametrize("name,mutate,gate_id", ADVERSARIAL,
                         ids=[a[0] for a in ADVERSARIAL])
def test_adversarial_blocks_production_ready(
        name: str, mutate: M, gate_id: str) -> None:
    e = _evidence()
    assert verdict(evaluate_gates(e)) == "PRODUCTION READY"  # sanity
    mutate(e)
    gates = evaluate_gates(e)
    assert verdict(gates) != "PRODUCTION READY", (
        f"adversarial '{name}' did NOT block PRODUCTION READY")
    g = next((x for x in gates if x.gate_id == gate_id), None)
    assert g is not None and g.status != "PASS", (
        f"expected gate '{gate_id}' to catch '{name}', got {g}")


def test_adversarial_count_is_at_least_45() -> None:
    """Onda 2 demands ≥45 named negative cases."""
    assert len(ADVERSARIAL) >= 45


def test_pristine_bundle_passes() -> None:
    """The untouched bundle must pass — guards against over-blocking."""
    assert verdict(evaluate_gates(_evidence())) == "PRODUCTION READY"
