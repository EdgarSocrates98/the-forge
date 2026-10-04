"""End-to-end adversarial providers: integrity gates before and after execute (1.1-1.7)
and every bad_forge attack through the complete orchestrator (2.1-2.6, 2.8)."""

import ast
import json
import os
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from helpers import (
    PROVIDERS,
    bad_argv,
    bad_entry,
    force_kill,
    make_workspace,
    pid_alive,
    wait_gone,
)
from theforge.contracts import ContextPack, ExecutionReceipt, Response
from theforge.contracts.codes import Codes
from theforge.contracts.integrity import validate_receipt
from theforge.forger import AskRequest, Forger, orchestrator
from theforge.protocol import SubprocessTransport
from theforge.registry import Registry
from theforge.runs import RunStore


def _forger(root: Path) -> Forger:
    forge = root / ".forge"
    return Forger(root, Registry(forge), RunStore(forge))


@pytest.mark.parametrize(("mode", "code", "needle"), [
    ("dup-evidence", Codes.RESULT_DUP_EVIDENCE, "'e1'"),
    ("dup-finding", Codes.RESULT_DUP_FINDING, "'f1'"),
    ("dangling-ref", Codes.RESULT_DANGLING_EVIDENCE, "'e-missing'"),
    ("artifact-absolute", Codes.RESULT_ARTIFACT_PATH, "/etc/passwd"),
    ("artifact-traversal", Codes.RESULT_ARTIFACT_PATH, "escape.txt"),
    ("bad-hash", Codes.PROTO_SCHEMA, "hash"),
    ("bad-artifact-hash", Codes.PROTO_SCHEMA, "sha256"),
    ("bad-timestamp", Codes.PROTO_SCHEMA, "yesterday"),
    ("wrong-producer", Codes.PROTO_PRODUCER, "someone-else"),
    ("wrong-version-producer", Codes.PROTO_PRODUCER, "9.9.9"),
    ("execute-wrong-envelope-producer", Codes.PROTO_PRODUCER, "someone-else"),
])
def test_invalid_result_is_provider_failure_without_result_artifact(
    tmp_path: Path, mode: str, code: str, needle: str
) -> None:
    make_workspace(tmp_path, [bad_entry(mode, "bad-a")])
    out = _forger(tmp_path).ask(AskRequest(intent="run it", capability="bad.thing"))
    assert out.status == "provider_failure" and out.result is None
    assert out.error is not None and out.error.code == code
    assert needle in out.error.detail
    store = RunStore(tmp_path / ".forge")
    assert store.read_optional(out.run_id, "result") is None
    receipt = store.read(out.run_id, "receipt")
    assert receipt["status"] == "provider_failure"
    assert receipt["result_sha256"] is None
    assert receipt["error"]["code"] == code
    assert store.read_optional(out.run_id, "context") is not None  # it ran


def test_valid_result_still_succeeds(tmp_path: Path) -> None:
    make_workspace(tmp_path, [bad_entry("ok", "bad-a")])
    out = _forger(tmp_path).ask(AskRequest(intent="run it", capability="bad.thing"))
    assert out.status == "ok" and out.result is not None
    assert RunStore(tmp_path / ".forge").read_optional(out.run_id, "result") is not None


def test_inconsistent_context_pack_is_internal_error_and_nothing_is_sent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = orchestrator.build_context_pack

    def inflated(*args: Any, **kwargs: Any) -> ContextPack:
        pack = real(*args, **kwargs)
        return replace(pack, used_bytes=pack.used_bytes + 1)

    sent: list[str] = []

    class _Recorder:
        def __init__(self, argv: Sequence[str]) -> None:
            self.inner = SubprocessTransport(argv)

        def call(self, op: str, payload: dict[str, Any], *, timeout: float,
                 cwd: Path | None = None, check_protocol: bool = True) -> Response:
            sent.append(op)
            return self.inner.call(op, payload, timeout=timeout, cwd=cwd,
                                   check_protocol=check_protocol)

    monkeypatch.setattr(orchestrator, "build_context_pack", inflated)
    make_workspace(tmp_path, [bad_entry("ok", "bad-a")])
    forge = tmp_path / ".forge"
    forger_ = Forger(tmp_path, Registry(forge), RunStore(forge), transport_factory=_Recorder)
    out = forger_.ask(AskRequest(intent="run it", capability="bad.thing"))
    assert out.status == "provider_failure" and out.result is None
    assert out.error is not None and out.error.code == Codes.INTERNAL
    assert Codes.CONTEXT_BYTES in out.error.detail
    assert "health" in sent and "execute" not in sent
    store = RunStore(forge)
    assert store.read_optional(out.run_id, "context") is None
    assert store.read_optional(out.run_id, "result") is None
    receipt = store.read(out.run_id, "receipt")
    assert receipt["status"] == "provider_failure"
    assert receipt["inputs"]["context_sha256"] is None
    assert receipt["error"]["code"] == Codes.INTERNAL


# --- full-orchestrator sweep over every bad_forge mode (task 4.1) ---------------------------

# mode -> (outcome, error code or None). Every mode runs registry + router + revalidation +
# health + policy + execute with ``capability="bad.thing"`` (explicit path). Describe-level
# attacks leave the provider (or the capability) out of routing, so they end in ``no_route``
# before any execute process is started.
SWEEP: dict[str, tuple[str, str | None]] = {
    # tolerated: the attack does not change a valid outcome
    "ok": ("ok", None),
    "no-op": ("ok", None),
    "duplicate-protocols": ("ok", None),
    "health-cwd-probe": ("ok", None),
    "describe-catch-all-glob": ("ok", None),  # only the greedy capability is excluded
    "describe-off-taxonomy": ("ok", None),  # only the off-taxonomy capability is excluded
    "stderr-flood": ("ok", None),
    "exit-leave-grandchild": ("ok", None),
    "env-probe-full": ("ok", None),
    "excerpts": ("ok", None),  # the capability declares excerpt support (context v2)
    # context negotiation (default profile balanced: at most 1 round)
    "context-request": ("ok", None),  # one round; the requested file is simply missing
    "tokens-measured": ("ok", None),  # the provider's token count is kept as reported
    # context drift (default profile balanced: conditional re-verification) -> partial
    "drift-report": ("partial", None),  # Evidence.hash differs from the pack item
    "mutate-context": ("partial", None),  # the provider changes the file it confirmed
    # describe-level: provider or capability is not routable
    "describe-crash": ("no_route", None),
    "invalid-manifest": ("no_route", None),
    "wrong-major": ("no_route", None),
    "malformed-protocols": ("no_route", None),
    "describe-wrong-producer": ("no_route", None),
    "describe-only-catch-all-glob": ("no_route", None),
    "describe-too-many-capabilities": ("no_route", None),
    "capability-spam": ("no_route", None),
    "keyword-spam": ("no_route", None),
    "wide-glob": ("no_route", None),
    "describe-bad-version": ("no_route", None),
    "describe-only-off-taxonomy": ("no_route", None),
    "describe-colliding-alias": ("no_route", None),
    "describe-refused": ("no_route", None),
    "no-execute-op": ("refused", Codes.PROTO_OP_UNSUPPORTED),
    # the manifest embeds the per-call temporary cwd, so it differs on every describe: the
    # revalidation before routing sees it change twice and refuses an unstable registry
    "describe-cwd-probe": ("provider_failure", Codes.REGISTRY_MANIFEST_CHANGED),
    # health
    "unhealthy": ("provider_failure", Codes.HEALTH_UNAVAILABLE),
    "health-wrong-producer": ("provider_failure", Codes.PROTO_PRODUCER),
    # policy
    "mutating": ("refused", Codes.POLICY_APPROVAL_REQUIRED),
    "destructive": ("refused", Codes.POLICY_DENIED),
    # execute: transport and envelope
    "timeout": ("provider_failure", Codes.PROTO_TIMEOUT),
    "no-read": ("provider_failure", Codes.PROTO_TIMEOUT),
    "spawn-grandchild-timeout": ("provider_failure", Codes.PROTO_TIMEOUT),
    "crash": ("provider_failure", Codes.PROTO_EXIT),
    "stderr-flood-crash": ("provider_failure", Codes.PROTO_EXIT),
    "garbage": ("provider_failure", Codes.PROTO_NOT_JSON),
    "oversize": ("provider_failure", Codes.PROTO_OVERSIZE),
    "wrong-op": ("provider_failure", Codes.PROTO_OP_MISMATCH),
    "wrong-kind": ("provider_failure", Codes.PROTO_SCHEMA),  # kind is Literal["Response"]
    "mismatch": ("provider_failure", Codes.PROTO_MISMATCH),
    "bad-envelope": ("provider_failure", Codes.PROTO_SCHEMA),
    "unknown-status": ("provider_failure", Codes.PROTO_SCHEMA),
    "refuse": ("refused", "BAD-REFUSED"),
    # execute: result contract and integrity
    "bad-result": ("provider_failure", Codes.PROTO_SCHEMA),
    "env-probe": ("provider_failure", Codes.PROTO_SCHEMA),
    "cwd-probe": ("provider_failure", Codes.PROTO_SCHEMA),
    "bad-timestamp": ("provider_failure", Codes.PROTO_SCHEMA),
    "bad-hash": ("provider_failure", Codes.PROTO_SCHEMA),
    "bad-artifact-hash": ("provider_failure", Codes.PROTO_SCHEMA),
    "wrong-producer": ("provider_failure", Codes.PROTO_PRODUCER),
    "wrong-version-producer": ("provider_failure", Codes.PROTO_PRODUCER),
    "execute-wrong-envelope-producer": ("provider_failure", Codes.PROTO_PRODUCER),
    "dup-evidence": ("provider_failure", Codes.RESULT_DUP_EVIDENCE),
    "dup-finding": ("provider_failure", Codes.RESULT_DUP_FINDING),
    "dangling-ref": ("provider_failure", Codes.RESULT_DANGLING_EVIDENCE),
    "artifact-absolute": ("provider_failure", Codes.RESULT_ARTIFACT_PATH),
    "artifact-traversal": ("provider_failure", Codes.RESULT_ARTIFACT_PATH),
    # execute: context negotiation (8.4)
    "context-request-loop": ("provider_failure", Codes.CONTEXT_REQUEST_LIMIT),
    "context-request-undeclared": ("provider_failure", Codes.CONTEXT_REQUEST_UNSUPPORTED),
    "context-request-invalid": ("provider_failure", Codes.CONTEXT_REQUEST_INVALID),
    # cross-forge-foundation fixtures: a single ``ask`` never calls the ``plan`` op nor sends
    # a handoff, so these answer as a valid run. artifact-tamper stays ``ok`` until artifact
    # re-verification (cross-forge-foundation 3.x/4.x) makes it ``partial``.
    "plan-error": ("ok", None),
    "plan-estimate-stricter": ("ok", None),
    "handoff-accept": ("ok", None),
    "artifact-tamper": ("ok", None),
    "internal-crash": ("provider_failure", Codes.PROTO_EXIT),  # unhandled exception, exit 1
}

# Registry state that keeps each describe-level attacker out of routing. no-execute-op is not
# here: it stays ``ready`` and the explicit request is refused with PROTO_OP_UNSUPPORTED (2.1).
NO_ROUTE_STATE = {
    "describe-crash": "unreachable",
    "invalid-manifest": "invalid",
    "wrong-major": "incompatible",
    "malformed-protocols": "incompatible",
    "describe-wrong-producer": "invalid",
    "describe-only-catch-all-glob": "invalid",
    "describe-too-many-capabilities": "invalid",
    "capability-spam": "invalid",
    "keyword-spam": "invalid",
    "wide-glob": "invalid",
    "describe-bad-version": "invalid",
    "describe-only-off-taxonomy": "invalid",
    "describe-colliding-alias": "invalid",
    "describe-refused": "invalid",
}
GRANDCHILD_MODES = ("spawn-grandchild-timeout", "exit-leave-grandchild")
# Modes that act on the ContextPack items: their workspace gets one *.txt file to cover.
CONTEXT_FILE_MODES = ("drift-report", "mutate-context")
MODE_TABLES = ("INTEGRITY_MODES", "OPERATION_CLASSES", "MANIFEST_PROTOCOLS", "REQUEST_MODES")


def _bad_forge_modes() -> set[str]:
    """Every mode string bad_forge.py compares against, plus the keys (or items) of its
    mode tables."""
    tree = ast.parse((PROVIDERS / "bad_forge.py").read_text(encoding="utf-8"))
    modes: set[str] = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Compare) and isinstance(node.left, ast.Name)
                and node.left.id == "mode"):
            modes |= {c.value for comp in node.comparators for c in ast.walk(comp)
                      if isinstance(c, ast.Constant) and isinstance(c.value, str)}
        if (isinstance(node, ast.Assign) and isinstance(node.value, (ast.Dict, ast.Tuple))
                and any(isinstance(t, ast.Name) and t.id in MODE_TABLES for t in node.targets)):
            keys = (node.value.keys if isinstance(node.value, ast.Dict)
                    else node.value.elts)  # a tuple table lists the modes themselves
            modes |= {k.value for k in keys
                      if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    return modes


def test_sweep_covers_every_bad_forge_mode() -> None:
    modes = _bad_forge_modes()
    assert modes - set(SWEEP) == set()
    assert set(SWEEP) - {"ok"} - modes == set()
    assert {m for m, (status, _) in SWEEP.items() if status == "no_route"} == set(NO_ROUTE_STATE)


@pytest.mark.parametrize(("mode", "expected"), sorted(SWEEP.items()), ids=sorted(SWEEP))
def test_every_mode_through_the_full_forger(
    tmp_path: Path, mode: str, expected: tuple[str, str | None]
) -> None:
    status, code = expected
    make_workspace(tmp_path, [bad_entry(mode, "bad-a")])
    if mode in CONTEXT_FILE_MODES:
        (tmp_path / "notes.txt").write_text("hello\n", encoding="utf-8")
    forge = tmp_path / ".forge"
    store = RunStore(forge)
    grandchild = 0
    try:
        out = Forger(tmp_path, Registry(forge), store, execute_timeout=3).ask(
            AskRequest(intent="run it", capability="bad.thing"))
        if mode in GRANDCHILD_MODES:
            marker = store.work_dir(out.run_id) / "grandchild.pid"
            assert marker.is_file(), "provider did not publish its grandchild PID"
            grandchild = int(marker.read_text(encoding="utf-8"))
            assert wait_gone(grandchild), f"grandchild {grandchild} survived the run"
        observed = (out.status, out.error.code if out.error else None)
        assert observed == (status, code), out.error.detail if out.error else out.decision.reason
        receipt = store.read_contract(out.run_id, "receipt", ExecutionReceipt)
        validate_receipt(receipt, result_sha256=store.persisted_sha256(out.run_id, "result"))
        assert receipt.status == status
        if status in ("ok", "partial"):
            assert out.result is not None and receipt.result_sha256 is not None
        else:
            assert out.result is None and receipt.result_sha256 is None
            assert store.read_optional(out.run_id, "result") is None
        if status == "no_route":
            assert store.read_optional(out.run_id, "context") is None  # never executed
            assert "bad.thing" in out.decision.reason
            states = {r.entry.id: r.state for r in Registry(forge).records()}
            assert states["bad-a"] == NO_ROUTE_STATE[mode]
    finally:
        if grandchild and pid_alive(grandchild):
            force_kill(grandchild)


def _probe_env() -> dict[str, str]:
    env = {"PROBE_MARKER": "1"}
    if sys.platform == "win32":  # Python needs SYSTEMROOT to start on Windows
        env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", r"C:\Windows")
    return env


@pytest.mark.parametrize("op", ["describe", "health", "execute"])
def test_env_probe_full_reports_received_environment_in_every_op(op: str) -> None:
    proc = subprocess.run([*bad_argv("env-probe-full"), op], input="{}", env=_probe_env(),
                          capture_output=True, text=True, timeout=30, check=True)
    payload = json.loads(proc.stdout)["payload"]
    lines = ([c["name"] for c in payload["checks"]] if op == "health"
             else payload["limitations"])
    names = {line.removeprefix("env:") for line in lines if line.startswith("env:")}
    assert "PROBE_MARKER" in names
    assert "SOME_UNSET_VARIABLE" not in names


def test_env_probe_full_execute_result_is_valid_through_the_forger(tmp_path: Path) -> None:
    make_workspace(tmp_path, [bad_entry("env-probe-full", "bad-a")])
    out = _forger(tmp_path).ask(AskRequest(intent="run it", capability="bad.thing"))
    assert out.status == "ok" and out.result is not None
    assert any(item.startswith("env:") for item in out.result.limitations)
