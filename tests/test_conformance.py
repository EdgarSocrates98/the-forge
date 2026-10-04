"""Forge Protocol v1 conformance suite, parametrized by provider argv.

To certify a new provider, add its argv to PROVIDER_ARGVS.
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from helpers import FIXTURES, PROVIDERS, fixture_argv
from theforge.contracts import (
    ContextPack,
    ExecuteRequest,
    ExecutionResult,
    ForgeManifest,
    HealthReport,
    Producer,
    Response,
    TaskSpec,
    from_dict,
    to_dict,
)
from theforge.contracts.canonical import sha256_hex, utc_now
from theforge.contracts.integrity import check_producer, check_timestamp, validate_result
from theforge.contracts.types import SHA256_RE
from theforge.meta import PRODUCER

PROVIDER_ARGVS = {
    "echo-forge": [sys.executable, "-m", "theforge.providers.echo"],
    "fixture-spark": fixture_argv("fixture_forge.py", str(PROVIDERS / "fixture-spark.json")),
    "fixture-api": fixture_argv("fixture_forge.py", str(PROVIDERS / "fixture-api.json")),
    # Real adapters in replay mode (healthy `default` scenario): no network, no credentials and
    # no sibling repos; execute with an empty or non-matching context takes the "no input" path.
    "spark-forge-replay": [sys.executable, "-m", "theforge_sparkforge", "--replay",
                           str(FIXTURES / "native" / "sparkforge" / "default")],
    "api-forge-replay": [sys.executable, "-m", "theforge_apiforge", "--replay",
                         str(FIXTURES / "native" / "apiforge" / "default")],
}
pytestmark = pytest.mark.parametrize(
    "argv", list(PROVIDER_ARGVS.values()), ids=list(PROVIDER_ARGVS))


def raw(argv: list[str], op: str, body: bytes) -> tuple[int, dict[str, Any]]:
    proc = subprocess.run([*argv, op], input=body, capture_output=True, timeout=30)
    return proc.returncode, json.loads(proc.stdout.decode("utf-8"))


def request(op: str, payload: dict[str, Any] | None = None, protocol: str = "forge/v1") -> bytes:
    return json.dumps({"protocol": protocol, "kind": "Request", "op": op,
                       "request_id": "r_conformance", "payload": payload or {}}).encode()


def manifest_of(argv: list[str]) -> ForgeManifest:
    _, data = raw(argv, "describe", request("describe"))
    return from_dict(ForgeManifest, data["payload"])


def execute_payload(root: Path, capability: str, action: str) -> dict[str, Any]:
    task = TaskSpec(producer=PRODUCER, created_at=utc_now(), id="t1", intent="conformance",
                    workspace_root=str(root))
    pack = ContextPack(producer=PRODUCER, created_at=utc_now(), status="complete",
                       task_id="t1", provider_id="x", root=str(root), budget_bytes=1024)
    return to_dict(ExecuteRequest(task=task, capability=capability, action=action, context=pack))


def test_describe_returns_valid_manifest(argv: list[str]) -> None:
    code, data = raw(argv, "describe", request("describe"))
    assert code == 0
    resp = from_dict(Response, data)
    assert resp.status == "ok"
    assert resp.request_id == "r_conformance"
    assert resp.protocol == "forge/v1"
    manifest = from_dict(ForgeManifest, resp.payload)
    assert "forge/v1" in manifest.protocols
    assert {"describe", "health", "execute"} <= set(manifest.ops)
    assert resp.producer.id == manifest.id


def test_health(argv: list[str]) -> None:
    code, data = raw(argv, "health", request("health"))
    resp = from_dict(Response, data)
    assert code == 0 and resp.status == "ok"
    assert from_dict(HealthReport, resp.payload).status in ("ok", "degraded")


def test_execute_every_capability(argv: list[str], tmp_path: Path) -> None:
    for cap in manifest_of(argv).capabilities:
        body = request("execute", execute_payload(tmp_path, cap.id, cap.default_action))
        code, data = raw(argv, "execute", body)
        resp = from_dict(Response, data)
        assert code == 0 and resp.status in ("ok", "partial")
        assert from_dict(ExecutionResult, resp.payload).producer.id == resp.producer.id


def test_unsupported_capability_is_refused(argv: list[str], tmp_path: Path) -> None:
    body = request("execute", execute_payload(tmp_path, "zzz.unknown", "run"))
    code, data = raw(argv, "execute", body)
    resp = from_dict(Response, data)
    assert code == 0 and resp.status == "refused"
    assert resp.error is not None and resp.error.code


def test_unsupported_action_is_refused(argv: list[str], tmp_path: Path) -> None:
    cap = manifest_of(argv).capabilities[0]
    body = request("execute", execute_payload(tmp_path, cap.id, "zzz-not-an-action"))
    code, data = raw(argv, "execute", body)
    resp = from_dict(Response, data)
    assert code == 0 and resp.status == "refused"
    assert resp.error is not None and resp.error.code


def test_execute_with_incompatible_protocol_is_refused(argv: list[str], tmp_path: Path) -> None:
    cap = manifest_of(argv).capabilities[0]
    body = request("execute", execute_payload(tmp_path, cap.id, cap.default_action),
                   protocol="forge/v9")
    code, data = raw(argv, "execute", body)
    assert code == 0 and from_dict(Response, data).status == "refused"


def test_execute_finding_evidence_ids_resolve(argv: list[str], tmp_path: Path) -> None:
    for cap in manifest_of(argv).capabilities:
        body = request("execute", execute_payload(tmp_path, cap.id, cap.default_action))
        _, data = raw(argv, "execute", body)
        result = from_dict(ExecutionResult, from_dict(Response, data).payload)
        known = {e.id for e in result.evidence}
        for finding in result.findings:
            assert set(finding.evidence_ids) <= known


def test_invalid_request_yields_error_response(argv: list[str]) -> None:
    code, data = raw(argv, "execute", b"{not json")
    resp = from_dict(Response, data)
    assert code == 0 and resp.status in ("error", "refused") and resp.error is not None


def test_unknown_op_is_refused(argv: list[str]) -> None:
    code, data = raw(argv, "teleport", request("teleport"))
    assert code == 0 and from_dict(Response, data).status == "refused"


def test_incompatible_protocol_is_refused(argv: list[str]) -> None:
    code, data = raw(argv, "health", request("health", protocol="forge/v9"))
    assert code == 0 and from_dict(Response, data).status == "refused"


def test_echo_confirms_context_hashes(argv: list[str], tmp_path: Path) -> None:
    if argv != PROVIDER_ARGVS["echo-forge"]:
        pytest.skip("echo-forge specific")
    from theforge.contracts import ContextFile
    from theforge.contracts.canonical import sha256_hex

    (tmp_path / "notes.txt").write_bytes(b"hello")
    payload = execute_payload(tmp_path, "demo.echo", "echo")
    payload["context"]["files"] = [to_dict(ContextFile(
        path="notes.txt", sha256=sha256_hex(b"hello"), bytes=5))]
    _, data = raw(argv, "execute", request("execute", payload))
    result = from_dict(ExecutionResult, data["payload"])
    assert [e.epistemic for e in result.evidence] == ["confirmed"]


def _expected(argv: list[str]) -> Producer:
    manifest = manifest_of(argv)
    return Producer(id=manifest.id, version=manifest.version)


def test_every_response_echoes_requested_op(argv: list[str], tmp_path: Path) -> None:
    cap = manifest_of(argv).capabilities[0]
    calls = [
        ("describe", request("describe")),
        ("health", request("health")),
        ("execute", request("execute", execute_payload(tmp_path, cap.id, cap.default_action))),
        ("execute", request("execute", execute_payload(tmp_path, "zzz.unknown", "run"))),
        ("health", request("health", protocol="forge/v9")),
        ("teleport", request("teleport")),
    ]
    for op, body in calls:
        _, data = raw(argv, op, body)
        assert from_dict(Response, data).op == op, (op, data)


def test_describe_and_health_producer_matches_manifest(argv: list[str]) -> None:
    expected = _expected(argv)
    for op in ("describe", "health"):
        _, data = raw(argv, op, request(op))
        resp = from_dict(Response, data)
        assert check_producer(resp.producer, expected=expected, field="producer") is None


def test_execute_result_passes_integrity(argv: list[str], tmp_path: Path) -> None:
    from theforge.contracts import ContextFile

    expected = _expected(argv)
    (tmp_path / "notes.md").write_bytes(b"hello")
    for cap in manifest_of(argv).capabilities:
        payload = execute_payload(tmp_path, cap.id, cap.default_action)
        payload["context"]["files"] = [to_dict(ContextFile(
            path="notes.md", sha256=sha256_hex(b"hello"), bytes=5))]
        _, data = raw(argv, "execute", request("execute", payload))
        resp = from_dict(Response, data)
        assert check_producer(resp.producer, expected=expected, field="producer") is None
        result = from_dict(ExecutionResult, resp.payload)
        validate_result(result, expected=expected)
        assert check_timestamp(result.created_at, field="created_at") is None
        for evidence in result.evidence:
            assert check_producer(evidence.producer, expected=expected, field="e") is None
            assert evidence.hash is None or SHA256_RE.fullmatch(evidence.hash)
