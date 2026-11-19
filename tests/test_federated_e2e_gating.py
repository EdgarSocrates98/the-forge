"""Negative tests for the fail-closed scenario gate (cycle 16.1.1 §4.1).

Before this wave, ``compute_gating`` only treated FAIL/ERROR as blocking:
a required scenario left UNVERIFIED/BLOCKED/SKIPPED — or emitted with no
verdict at all — silently exited 0, an undeclared scenario key went
unchecked, and ``I-offline`` was a ``check(True)`` placeholder. These
tests pin the closed semantics: required scenarios must prove PASS,
required-but-inconclusive lands in ``unverified_reasons`` (distinct list,
equally fatal to certification), undeclared keys and not-run required
scenarios are blocking, and optional scenarios may be inconclusive
without blocking — but never with a FAIL.
"""

from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest
import scripts.federated_e2e as fe


def _passing_scenarios() -> dict:
    return {s["id"]: {"verdict": "PASS"} for s in fe.SCENARIOS if s.get("required", True)}


def _ok_evals() -> dict:
    return {
        "routing": [{"task": t, "ok": True} for _s, t, _a in fe.ROUTING_EVALS]
        + [{"task": "zzzqxkvbnm wqkfj", "ok": True}],
        "resources": [
            {"case": "right-resource", "ok": True},
            {"case": "nonexistent", "ok": True},
            {"case": "manifest-poisoning-traversal", "ok": True},
        ],
    }


def _receipt(scenarios: dict | None = None, evals: dict | None = None) -> dict:
    """A certification-clean receipt: every required scenario PASS and
    every required eval ok — the baseline that must produce PASS."""
    return {
        "scenarios": _passing_scenarios() if scenarios is None else scenarios,
        "evals": _ok_evals() if evals is None else evals,
    }


# ---------------------------------------------------------------------------
# inventory — the declaration IS the contract
# ---------------------------------------------------------------------------


def test_inventory_declares_every_emitted_scenario() -> None:
    emitted = {
        *fe.SCENARIO_FORGES,
        "G-all",
        "H-no-git",
        "I-offline",
        "J-partial-failure",
        "K-resource-discovery",
        "L-portal-cli",
        "M-upgrade",
        "N-uninstall",
        "O-context-economy",
    }
    assert set(fe.SCENARIO_SPEC) == emitted
    assert len(fe.SCENARIOS) == len(fe.SCENARIO_SPEC)  # no duplicate ids


def test_optional_scenarios_carry_justification() -> None:
    optional = [s for s in fe.SCENARIOS if not s.get("required", True)]
    assert optional  # L-portal-cli — environment-dependent
    for s in optional:
        assert str(s.get("not_applicable") or s.get("optional") or "").strip()


def test_verdict_helpers_partition_inconclusive() -> None:
    assert fe.is_unverified("UNVERIFIED") and fe.is_unverified("skipped")
    assert not fe.is_unverified("PASS") and not fe.is_unverified("FAIL")


# ---------------------------------------------------------------------------
# gate semantics — required scenarios must prove PASS
# ---------------------------------------------------------------------------


def test_clean_receipt_certifies_pass() -> None:
    rep = fe.gate_report(_receipt())
    assert rep["certification_verdict"] == "PASS"
    assert rep["blocking_reasons"] == []
    assert rep["unverified_reasons"] == []
    assert rep["required_coverage"]["passed"] == rep["required_coverage"]["required"] > 0


def test_required_scenario_fail_blocks() -> None:
    rc = _receipt()
    rc["scenarios"]["A-aws-standalone"] = {"verdict": "FAIL"}
    rep = fe.gate_report(rc)
    assert "scenario:A-aws-standalone:FAIL" in rep["blocking_reasons"]
    assert rep["certification_verdict"] == "FAIL"
    assert rep["required_coverage"]["failed"] == 1


@pytest.mark.parametrize("verdict", ["UNVERIFIED", "BLOCKED", "SKIPPED", "NOT_APPLICABLE"])
def test_required_inconclusive_prevents_pass_via_unverified(verdict: str) -> None:
    """Inconclusive ≠ disproof: it lands in unverified_reasons, not
    blocking_reasons — and is equally fatal to certification."""
    rc = _receipt()
    rc["scenarios"]["G-all"] = {"verdict": verdict}
    rep = fe.gate_report(rc)
    assert rep["certification_verdict"] == "FAIL"
    assert not any("G-all" in r for r in rep["blocking_reasons"])
    assert any("G-all" in r for r in rep["unverified_reasons"])
    assert rep["required_coverage"]["inconclusive"] == 1


def test_required_scenario_missing_verdict_is_unverified() -> None:
    rc = _receipt()
    rc["scenarios"]["I-offline"] = {"checks": []}
    rep = fe.gate_report(rc)
    assert rep["certification_verdict"] == "FAIL"
    assert "scenario:I-offline:missing-verdict" in rep["unverified_reasons"]


def test_required_scenario_absent_from_receipt_blocks_not_run() -> None:
    rc = _receipt()
    del rc["scenarios"]["M-upgrade"]
    rep = fe.gate_report(rc)
    assert "scenario-not-run:M-upgrade" in rep["blocking_reasons"]
    assert rep["certification_verdict"] == "FAIL"


def test_unknown_verdict_string_blocks() -> None:
    rc = _receipt()
    rc["scenarios"]["H-no-git"] = {"verdict": "PASSED-WITH-COMMENTS"}
    rep = fe.gate_report(rc)
    assert rep["certification_verdict"] == "FAIL"
    assert any("scenario:H-no-git:invalid-verdict:" in r for r in rep["blocking_reasons"])


def test_undeclared_scenario_key_blocks() -> None:
    rc = _receipt()
    rc["scenarios"]["ZZ-never-declared"] = {"verdict": "PASS"}
    rep = fe.gate_report(rc)
    assert rep["certification_verdict"] == "FAIL"
    assert "scenario-undeclared:ZZ-never-declared" in rep["blocking_reasons"]


def test_empty_scenarios_never_certifies() -> None:
    """Zero scenarios is a harness gap, not a pass: every required
    scenario is scenario-not-run and coverage is honestly zero."""
    rep = fe.gate_report(_receipt(scenarios={}))
    cov = rep["required_coverage"]
    assert rep["certification_verdict"] == "FAIL"
    assert cov["inconclusive"] == cov["required"] > 0
    not_run = [r for r in rep["blocking_reasons"] if r.startswith("scenario-not-run:")]
    assert len(not_run) == cov["required"]


def test_optional_scenario_may_be_inconclusive() -> None:
    rc = _receipt()
    rc["scenarios"]["L-portal-cli"] = {"verdict": "UNVERIFIED", "reason": "no portal"}
    rep = fe.gate_report(rc)
    assert rep["certification_verdict"] == "PASS"
    assert rep["unverified_reasons"] == []


def test_optional_scenario_fail_still_blocks() -> None:
    """Optionality forgives inconclusion, never disproof."""
    rc = _receipt()
    rc["scenarios"]["L-portal-cli"] = {"verdict": "FAIL"}
    rep = fe.gate_report(rc)
    assert rep["certification_verdict"] == "FAIL"
    assert "scenario:L-portal-cli:FAIL" in rep["blocking_reasons"]


def test_optional_scenario_absent_is_fine() -> None:
    rc = _receipt()
    assert "L-portal-cli" not in rc["scenarios"]  # not in the required baseline
    rep = fe.gate_report(rc)
    assert rep["certification_verdict"] == "PASS"


def test_scenario_with_zero_checks_is_inconclusive_not_pass() -> None:
    """The F-01 defect shape: a required scenario that produced zero
    checks becomes UNVERIFIED and must prevent certification."""
    rc = _receipt()
    # mimic the verdict-assignment loop: no checks → UNVERIFIED
    rc["scenarios"]["K-resource-discovery"] = {"checks": [], "verdict": "UNVERIFIED"}
    rep = fe.gate_report(rc)
    assert rep["certification_verdict"] == "FAIL"
    assert rep["blocking_reasons"] == []
    assert rep["unverified_reasons"]


# ---------------------------------------------------------------------------
# evals stay fail-closed through the same report
# ---------------------------------------------------------------------------


def test_required_eval_not_run_blocks() -> None:
    rep = fe.gate_report(_receipt(evals={"routing": [], "resources": []}))
    assert rep["certification_verdict"] == "FAIL"
    assert any(r.startswith("eval-not-run:") for r in rep["blocking_reasons"])


def test_required_eval_failed_blocks() -> None:
    evals = _ok_evals()
    evals["routing"][0]["ok"] = False
    rep = fe.gate_report(_receipt(evals=evals))
    assert rep["certification_verdict"] == "FAIL"
    assert any(r.startswith("eval-failed:") for r in rep["blocking_reasons"])


# ---------------------------------------------------------------------------
# I-offline — the instrumented proof, honest both ways
# ---------------------------------------------------------------------------


def _mini_workspace(root: Path) -> Path:
    forge = root / "demo-forge"
    forge.mkdir(parents=True)
    (forge / "forge.agentic.json").write_text(
        json.dumps(
            {
                "schema": "forge/SpecialistAgenticManifest/v1",
                "id": "demo-forge",
                "version": "1.0.0",
                "resources": [
                    {
                        "id": "skill-demo",
                        "kind": "skill",
                        "location": "skills/demo/SKILL.md",
                        "tags": ["spark", "tuning"],
                        "availability": "available",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    body = forge / "skills" / "demo" / "SKILL.md"
    body.parent.mkdir(parents=True)
    body.write_bytes(b"# demo\n")
    return root


def test_offline_scenario_proves_zero_attempts(tmp_path: Path) -> None:
    before = socket.socket
    result = fe.offline_scenario(_mini_workspace(tmp_path / "ws"))
    # the block restores the socket surface it borrowed — always
    assert socket.socket is before
    assert result["outbound_attempts"] == []
    by_label = {c["check"]: c["ok"] for c in result["checks"]}
    assert by_label == {
        "net-block-intercepts": True,
        "offline-discovery": True,
        "offline-list": True,
        "offline-get": True,
        "offline-plan": True,
        "zero-outbound-attempts": True,
    }
    assert result["blocked_surface"] == [
        "socket.socket",
        "socket.create_connection",
        "socket.getaddrinfo",
    ]
    # honest boundary is declared, not implied
    assert "NOT claimed offline" in result["evidence"]


def test_offline_scenario_records_and_fails_on_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The recorder is not decorative: an op that dials is caught,
    logged and turns checks red."""
    _mini_workspace(tmp_path / "ws")

    def _dialer(root: Path) -> object:
        socket.create_connection(("203.0.113.1", 443))
        raise AssertionError("unreachable — the exploder must fire first")

    monkeypatch.setattr(fe, "resolver_for", _dialer)
    result = fe.offline_scenario(tmp_path / "ws")
    by_label = {c["check"]: c["ok"] for c in result["checks"]}
    assert by_label["net-block-intercepts"] is True  # block still proven live
    assert by_label["offline-discovery"] is False
    assert by_label["zero-outbound-attempts"] is False
    assert result["outbound_attempts"] != []


# ---------------------------------------------------------------------------
# runner crash + receipt read-back — schema-valid, nonzero, honest
# ---------------------------------------------------------------------------


def test_runner_crash_receipt_is_schema_valid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()

    def _boom(*a: object, **kw: object) -> dict:
        raise RuntimeError("injected runner failure")

    monkeypatch.setattr(fe, "scenario_subset", _boom)
    out = tmp_path / "receipt.json"
    rc = fe.main(["--workspace", str(ws), "--out", str(out)])
    assert rc == 2
    assert fe._validate_receipt(out) == []  # crash receipt honors the contract
    receipt = json.loads(out.read_text(encoding="utf-8"))
    assert receipt["certification_verdict"] == "FAIL"
    reasons = receipt["gating"]["blocking_reasons"]
    assert any(r.startswith("runner-error:") for r in reasons)
    # every required scenario honestly not-run — coverage is not zeroed
    cov = receipt["gating"]["required_coverage"]
    assert cov["inconclusive"] == cov["required"] > 0
    assert sum(r.startswith("scenario-not-run:") for r in reasons) == cov["required"]


def test_validate_receipt_missing_key(tmp_path: Path) -> None:
    doc = {
        "schema": "forge/FederatedE2E/v1",
        "scenarios": {},
        "evals": {},
        "summary": {},
        "gating": {},
    }
    p = tmp_path / "r.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    assert fe._validate_receipt(p) == ["receipt-invalid: missing 'certification_verdict'"]


def test_validate_receipt_wrong_schema(tmp_path: Path) -> None:
    p = tmp_path / "r.json"
    p.write_text(json.dumps({"schema": "forge/Other/v1"}), encoding="utf-8")
    assert any("schema" in e for e in fe._validate_receipt(p))


def test_validate_receipt_non_object(tmp_path: Path) -> None:
    p = tmp_path / "r.json"
    p.write_text("[1, 2, 3]", encoding="utf-8")
    errors = fe._validate_receipt(p)
    assert errors == ["receipt-unreadable: top level is not an object"]


def test_validate_receipt_missing_file(tmp_path: Path) -> None:
    errors = fe._validate_receipt(tmp_path / "nope.json")
    assert errors and errors[0].startswith("receipt-unreadable")
