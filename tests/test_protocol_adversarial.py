"""End-to-end adversarial providers: integrity gates before and after execute (1.1-1.7)."""

from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from helpers import bad_entry, make_workspace
from theforge.contracts import ContextPack, Response
from theforge.contracts.codes import Codes
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
