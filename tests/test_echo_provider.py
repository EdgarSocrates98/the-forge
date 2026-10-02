"""Direct tests of the echo-forge handler: secret, size, escape and crash safety."""

import json
from pathlib import Path
from typing import Any

import pytest

from theforge.contracts import (
    ContextFile,
    ContextPack,
    ExecuteRequest,
    TaskSpec,
    to_dict,
)
from theforge.contracts.canonical import sha256_hex, utc_now
from theforge.meta import PRODUCER
from theforge.providers.echo import provider


def execute_body(root: Path, files: list[ContextFile], action: str = "echo",
                 capability: str = "demo.echo") -> bytes:
    task = TaskSpec(producer=PRODUCER, created_at=utc_now(), id="t1", intent="echo test",
                    workspace_root=str(root))
    pack = ContextPack(producer=PRODUCER, created_at=utc_now(), status="complete",
                       task_id="t1", provider_id="x", root=str(root), budget_bytes=1024,
                       files=files)
    payload = to_dict(ExecuteRequest(task=task, capability=capability, action=action,
                                     context=pack))
    return json.dumps({"protocol": "forge/v1", "kind": "Request", "op": "execute",
                       "request_id": "r_echo", "payload": payload}).encode()


def run(root: Path, path: str, content: bytes) -> dict[str, Any]:
    entry = ContextFile(path=path, sha256=sha256_hex(content), bytes=len(content))
    return provider.handle("execute", execute_body(root, [entry]))


def evidence_of(resp: dict[str, Any]) -> list[dict[str, Any]]:
    assert resp["status"] == "ok"
    evidence: list[dict[str, Any]] = resp["payload"]["evidence"]
    return evidence


def test_secret_file_is_never_read(tmp_path: Path) -> None:
    secret = b"API_KEY=super-secret-value"
    (tmp_path / ".env").write_bytes(secret)
    resp = run(tmp_path, ".env", secret)
    (ev,) = evidence_of(resp)
    assert ev["epistemic"] == "unresolved"
    assert ev["claim"] == "secret file not read"
    assert ev.get("hash") is None
    assert sha256_hex(secret) not in json.dumps(resp)


def test_oversized_file_is_unresolved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(provider, "MAX_READ_BYTES", 4)
    (tmp_path / "big.txt").write_bytes(b"0123456789")
    (ev,) = evidence_of(run(tmp_path, "big.txt", b"0123456789"))
    assert ev["epistemic"] == "unresolved"
    assert ev["claim"] == "file exceeds echo read limit"
    assert ev.get("hash") is None


def test_relative_escape_is_unresolved(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (tmp_path / "outside.txt").write_bytes(b"outside")
    (ev,) = evidence_of(run(root, "../outside.txt", b"outside"))
    assert ev["epistemic"] == "unresolved"
    assert ev.get("hash") is None


def test_absolute_path_outside_is_unresolved(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"outside")
    (ev,) = evidence_of(run(root, str(outside), b"outside"))
    assert ev["epistemic"] == "unresolved"
    assert ev.get("hash") is None


def test_internal_failure_returns_error_response(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("kaboom")

    monkeypatch.setattr(provider, "_execute", boom)
    resp = provider.handle("execute", execute_body(tmp_path, []))
    assert resp["status"] == "error"
    assert resp["request_id"] == "r_echo"
    assert resp["error"]["code"] == "ECHO-INTERNAL"
    assert "RuntimeError: kaboom" in resp["error"]["detail"]
