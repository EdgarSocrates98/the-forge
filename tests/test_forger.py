import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from helpers import API_ENTRY, SPARK_ENTRY, bad_entry, case_a, case_b, make_workspace, write_file
from theforge.contracts import (
    Capability,
    ErrorInfo,
    ForgeManifest,
    Response,
    RoutingDecision,
    Signals,
    TaskSpec,
)
from theforge.contracts.canonical import sha256_of, utc_now
from theforge.errors import UsageError
from theforge.forger import AskRequest, Forger
from theforge.meta import PRODUCER
from theforge.protocol import ProviderTransport, SubprocessTransport
from theforge.registry import HealthOutcome, ProviderEntry, Registry, RegistryRecord
from theforge.routing import route
from theforge.runs import ARTIFACTS, RunStore


def forger(root: Path, allow_unverified: bool = False, **kw: float) -> Forger:
    forge = root / ".forge"
    return Forger(root, Registry(forge, allow_unverified=allow_unverified), RunStore(forge), **kw)


def test_case_a_end_to_end(tmp_path: Path) -> None:
    make_workspace(tmp_path, [SPARK_ENTRY, API_ENTRY])
    case_a(tmp_path)
    out = forger(tmp_path).ask(AskRequest(intent="analise esse Glue Job porque está lento"))
    assert out.status == "ok"
    assert out.decision.selected[0].provider == "fixture-spark"
    assert out.result is not None
    assert out.result.metrics.duration_ms.kind == "measured"
    assert out.result.metrics.tokens.kind == "unknown"
    store = RunStore(tmp_path / ".forge")
    for name in ARTIFACTS:
        assert store.read_optional(out.run_id, name) is not None
    receipt = out.receipt
    assert receipt.inputs.task_sha256 == sha256_of(store.read(out.run_id, "task"))
    assert receipt.inputs.routing_sha256 == sha256_of(store.read(out.run_id, "routing"))
    assert receipt.inputs.context_sha256 == sha256_of(store.read(out.run_id, "context"))
    assert receipt.result_sha256 == sha256_of(store.read(out.run_id, "result"))
    assert receipt.provider is not None and receipt.provider.id == "fixture-spark"
    assert receipt.provider.trust == "local" and receipt.provider.manifest_sha256
    files = [f["path"] for f in store.read(out.run_id, "context")["files"]]
    assert files == ["jobs/orders_glue_job.py"]


def test_case_b_routes_to_api(tmp_path: Path) -> None:
    make_workspace(tmp_path, [SPARK_ENTRY, API_ENTRY])
    case_b(tmp_path)
    out = forger(tmp_path).ask(AskRequest(intent="avalie esse contrato OpenAPI",
                                          targets=["api"]))
    assert out.status == "ok"
    assert (out.decision.selected[0].provider, out.decision.selected[0].action) == \
        ("fixture-api", "review")


def test_ambiguous_writes_receipt_only(tmp_path: Path) -> None:
    make_workspace(tmp_path, [SPARK_ENTRY, API_ENTRY])
    out = forger(tmp_path).ask(AskRequest(intent="performance da api"))
    store = RunStore(tmp_path / ".forge")
    assert out.status == "ambiguous" and out.receipt.status == "ambiguous"
    assert store.read_optional(out.run_id, "context") is None
    assert store.read_optional(out.run_id, "result") is None
    assert store.read_optional(out.run_id, "receipt") is not None


def test_no_route(tmp_path: Path) -> None:
    make_workspace(tmp_path, [])
    assert forger(tmp_path).ask(AskRequest(intent="bom dia")).status == "no_route"


def test_echo_explicit_capability_confirms_hashes(tmp_path: Path) -> None:
    make_workspace(tmp_path, [])
    write_file(tmp_path, "notes.txt", "hello\n")
    out = forger(tmp_path).ask(AskRequest(intent="eco", capability="demo.echo"))
    assert out.status == "ok" and out.result is not None
    assert [e.epistemic for e in out.result.evidence] == ["confirmed"]


def test_refused_is_reported(tmp_path: Path) -> None:
    make_workspace(tmp_path, [bad_entry("refuse", "bad-a")])
    out = forger(tmp_path).ask(AskRequest(intent="run it", capability="bad.thing"))
    assert out.status == "refused" and out.receipt.status == "refused"
    assert out.error is not None and out.error.code == "BAD-REFUSED"
    assert out.error.unlock == "try another capability"


@pytest.mark.parametrize(
    ("mode", "code"),
    [("crash", "FORGE-PROTO-EXIT"), ("garbage", "FORGE-PROTO-NOT-JSON"),
     ("oversize", "FORGE-PROTO-OVERSIZE"), ("mismatch", "FORGE-PROTO-MISMATCH"),
     ("bad-result", "FORGE-PROTO-SCHEMA")],
)
def test_provider_failures_never_succeed(tmp_path: Path, mode: str, code: str) -> None:
    make_workspace(tmp_path, [bad_entry(mode, "bad-a")])
    out = forger(tmp_path).ask(AskRequest(intent="run it", capability="bad.thing"))
    assert out.status == "provider_failure" and out.result is None
    assert out.error is not None and out.error.code == code
    store = RunStore(tmp_path / ".forge")
    assert store.read(out.run_id, "receipt")["status"] == "provider_failure"
    assert store.read_optional(out.run_id, "result") is None


def test_timeout(tmp_path: Path) -> None:
    make_workspace(tmp_path, [bad_entry("timeout", "bad-a")])
    out = forger(tmp_path, execute_timeout=1.5).ask(
        AskRequest(intent="run it", capability="bad.thing"))
    assert out.error is not None and out.error.code == "FORGE-PROTO-TIMEOUT"


def test_unhealthy_primary_falls_back(tmp_path: Path) -> None:
    make_workspace(tmp_path, [bad_entry("unhealthy", "bad-a", trust="trusted"),
                              bad_entry("ok", "bad-b", trust="local")])
    out = forger(tmp_path).ask(AskRequest(intent="run it", capability="bad.thing"))
    assert out.status == "ok"
    assert out.decision.selected[0].provider == "bad-b"
    assert out.decision.fallbacks_used == ["bad-a:FORGE-HEALTH-UNAVAILABLE"]


def test_all_unhealthy_is_provider_failure(tmp_path: Path) -> None:
    make_workspace(tmp_path, [bad_entry("unhealthy", "bad-a")])
    out = forger(tmp_path).ask(AskRequest(intent="run it", capability="bad.thing"))
    assert out.status == "provider_failure"
    assert out.error is not None and out.error.code == "FORGE-HEALTH-UNAVAILABLE"


def test_incompatible_provider_not_routed(tmp_path: Path) -> None:
    make_workspace(tmp_path, [bad_entry("wrong-major", "bad-a")])
    out = forger(tmp_path).ask(AskRequest(intent="run it", capability="bad.thing"))
    assert out.status == "no_route"


def test_unverified_requires_opt_in(tmp_path: Path) -> None:
    make_workspace(tmp_path, [bad_entry("ok", "bad-a", trust="unverified")])
    request = AskRequest(intent="run it", capability="bad.thing")
    assert forger(tmp_path).ask(request).status == "no_route"
    opted = AskRequest(intent="run it", capability="bad.thing", allow_unverified=True)
    assert forger(tmp_path, allow_unverified=True).ask(opted).status == "ok"


def test_secrets_never_persisted(tmp_path: Path) -> None:
    make_workspace(tmp_path, [])
    write_file(tmp_path, ".env", "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEY\n")
    write_file(tmp_path, "notes.txt", "token=abc123secretvalue\n")
    out = forger(tmp_path).ask(AskRequest(intent="eco password=hunter2xyz"))
    assert out.status == "ok"
    blob = "".join(p.read_text(encoding="utf-8")
                   for p in (tmp_path / ".forge" / "runs").rglob("*.json"))
    for secret in ("hunter2xyz", "abc123secretvalue", "wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEY"):
        assert secret not in blob


def _receipt_files(root: Path) -> list[Path]:
    return sorted((root / ".forge" / "runs").rglob("receipt.json"))


def test_invalid_action_writes_receipt_and_reraises(tmp_path: Path) -> None:
    make_workspace(tmp_path, [])
    with pytest.raises(UsageError):
        forger(tmp_path).ask(AskRequest(intent="eco", capability="demo.echo", action="nope"))
    receipts = _receipt_files(tmp_path)
    assert len(receipts) == 1
    data = json.loads(receipts[0].read_text(encoding="utf-8"))
    assert data["status"] == "no_route"
    assert data["error"]["code"] == "FORGE-USAGE"


class _ExplodingTransport:
    def __init__(self, inner: ProviderTransport) -> None:
        self.inner = inner

    def call(self, op: str, payload: dict[str, Any], *, timeout: float,
             cwd: Path | None = None, check_protocol: bool = True) -> Response:
        if op == "execute":
            raise ValueError("boom")
        return self.inner.call(op, payload, timeout=timeout, cwd=cwd,
                               check_protocol=check_protocol)


def test_unexpected_exception_becomes_provider_failure(tmp_path: Path) -> None:
    make_workspace(tmp_path, [bad_entry("ok", "bad-a")])

    def factory(argv: Sequence[str]) -> ProviderTransport:
        return _ExplodingTransport(SubprocessTransport(argv))

    forge = tmp_path / ".forge"
    forger_ = Forger(tmp_path, Registry(forge), RunStore(forge), transport_factory=factory)
    out = forger_.ask(AskRequest(intent="run it", capability="bad.thing"))
    assert out.status == "provider_failure" and out.result is None
    assert out.error is not None and out.error.code == "FORGE-INTERNAL"
    assert out.error.detail == "ValueError: boom"
    store = RunStore(forge)
    assert store.read(out.run_id, "receipt")["status"] == "provider_failure"
    assert store.read_optional(out.run_id, "result") is None


def test_wrong_producer_is_rejected(tmp_path: Path) -> None:
    make_workspace(tmp_path, [bad_entry("wrong-producer", "bad-a")])
    out = forger(tmp_path).ask(AskRequest(intent="run it", capability="bad.thing"))
    assert out.status == "provider_failure" and out.result is None
    assert out.error is not None and out.error.code == "FORGE-PROTO-PRODUCER"
    store = RunStore(tmp_path / ".forge")
    assert store.read_optional(out.run_id, "result") is None
    assert store.read(out.run_id, "receipt")["status"] == "provider_failure"


def _rec(pid: str, actions: tuple[str, ...], trust: str) -> RegistryRecord:
    cap = Capability(id="bad.thing", actions=list(actions), default_action=actions[0],
                     state="supported", operation_class="read_only",
                     signals=Signals(keywords=["bad"]))
    manifest = ForgeManifest(id=pid, version="1", protocols=["forge/v1"],
                             ops=["describe", "health", "execute"], capabilities=[cap])
    return RegistryRecord(entry=ProviderEntry(id=pid, argv=["x"], trust=trust), state="ready",
                          manifest=manifest, manifest_sha256="0" * 64, protocol="forge/v1")


def _fallback_setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, action: str | None
) -> tuple[Forger, TaskSpec, RoutingDecision, dict[str, RegistryRecord]]:
    records = {"a": _rec("a", ("run", "other"), "trusted"), "b": _rec("b", ("run",), "local")}
    task = TaskSpec(producer=PRODUCER, created_at=utc_now(), id="t1", intent="x",
                    workspace_root=str(tmp_path), requested_capability="bad.thing",
                    requested_action=action)
    decision = route(task, list(records.values()), [], set())
    assert decision.selected[0].provider == "a"

    def fake_health(record: RegistryRecord, **_: object) -> HealthOutcome:
        if record.entry.id == "a":
            return HealthOutcome(status="unavailable", error=ErrorInfo(code="X-DOWN", detail="d"))
        return HealthOutcome(status="ok")

    monkeypatch.setattr("theforge.forger.orchestrator.check_health", fake_health)
    forge = tmp_path / ".forge"
    return Forger(tmp_path, Registry(forge), RunStore(forge)), task, decision, records


def test_fallback_skips_candidate_lacking_requested_action(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    forge_, task, decision, records = _fallback_setup(tmp_path, monkeypatch, "other")
    _, record, error = forge_._select_healthy(task, decision, records)
    assert record is None
    assert error is not None and error.code == "X-DOWN"


def test_fallback_substitutes_default_action_when_none_requested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    forge_, task, decision, records = _fallback_setup(tmp_path, monkeypatch, None)
    switched, record, _ = forge_._select_healthy(task, decision, records)
    assert record is not None and record.entry.id == "b"
    assert switched.selected[0].action == "run"
