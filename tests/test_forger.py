import json
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from helpers import API_ENTRY, SPARK_ENTRY, bad_entry, case_a, case_b, make_workspace, write_file
from theforge.contracts import (
    Candidate,
    Capability,
    Confidence,
    ErrorInfo,
    ForgeManifest,
    Response,
    RoutingDecision,
    Selection,
    Signals,
    TaskSpec,
)
from theforge.contracts.canonical import sha256_of, utc_now
from theforge.contracts.codes import Codes
from theforge.errors import UsageError
from theforge.forger import AskRequest, Forger
from theforge.meta import PRODUCER
from theforge.protocol import ProviderTransport, SubprocessTransport, TransportError
from theforge.registry import (
    HealthOutcome,
    ProviderEntry,
    Registry,
    RegistryRecord,
    RevalidationOutcome,
    fingerprint,
)
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
    # Negotiation rounds are optional; telemetry is written once the ask flow records it.
    for name in ARTIFACTS:
        if name.startswith("context-r") or name == "telemetry":
            continue
        assert store.read_optional(out.run_id, name) is not None
    receipt = out.receipt
    assert receipt.inputs.task_sha256 == sha256_of(store.read(out.run_id, "task"))
    assert receipt.inputs.routing_sha256 == sha256_of(store.read(out.run_id, "routing"))
    assert receipt.inputs.context_sha256 == sha256_of(store.read(out.run_id, "context"))
    assert receipt.result_sha256 == sha256_of(store.read(out.run_id, "result"))
    assert receipt.inputs.risk_sha256 == sha256_of(store.read(out.run_id, "risk"))
    assert receipt.provider is not None and receipt.provider.id == "fixture-spark"
    assert receipt.provider.trust == "local" and receipt.provider.manifest_sha256
    files = [f["path"] for f in store.read(out.run_id, "context")["files"]]
    # Context v2: the root dependency manifest is a relevance signal too (ranked after globs).
    assert files == ["jobs/orders_glue_job.py", "requirements.txt"]


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


def test_requested_capability_without_execute_op_is_refused_with_code(tmp_path: Path) -> None:
    """2.1: the only provider of the requested capability lacks execute -> specific code."""
    make_workspace(tmp_path, [bad_entry("no-execute-op", "bad-a")])
    out = forger(tmp_path).ask(AskRequest(intent="run it", capability="bad.thing"))
    assert out.status == "refused" and out.result is None
    assert out.error is not None and out.error.code == Codes.PROTO_OP_UNSUPPORTED
    assert "bad-a" in out.error.detail and "execute" in out.error.detail
    store = RunStore(tmp_path / ".forge")
    assert store.read(out.run_id, "receipt")["status"] == "refused"
    for artifact in ("context", "risk", "result"):  # refused before policy and execute
        assert store.read_optional(out.run_id, artifact) is None
    assert any("bad-a" in note and "execute" in note
               for note in store.read(out.run_id, "routing")["limitations"])


@pytest.mark.parametrize(("executing", "trust"), [
    ("ok", "unverified"),   # an executing declarer exists, unlockable by --allow-unverified
    ("describe-crash", "local"),  # an executing provider that is not ready (unreachable)
])
def test_op_unsupported_is_not_blamed_when_another_provider_may_execute(
    tmp_path: Path, executing: str, trust: str
) -> None:
    """2.1 refusal fires only when no other provider can be the one that executes."""
    make_workspace(tmp_path, [bad_entry(executing, "bad-exec", trust=trust),
                              bad_entry("no-execute-op", "bad-noexec")])
    out = forger(tmp_path).ask(AskRequest(intent="run it", capability="bad.thing"))
    assert out.status == "no_route" and out.error is None


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


def _rec(pid: str, actions: tuple[str, ...], trust: str,
         cap_id: str = "bad.thing") -> RegistryRecord:
    cap = Capability(id=cap_id, actions=list(actions), default_action=actions[0],
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


# --- revalidation, final routing and same-capability fallback (task 3.6) ---------------------

class _ScriptedRegistry(Registry):
    """Registry whose revalidation answers from a script instead of describing again."""

    def __init__(self, forge_dir: Path, statuses: dict[str, str]) -> None:
        super().__init__(forge_dir)
        self.statuses = statuses
        self.revalidated: list[list[str]] = []
        self.invalidated: list[str] = []

    def revalidate(self, provider_ids: Sequence[str]) -> list[RevalidationOutcome]:
        self.revalidated.append(list(provider_ids))
        outcomes: list[RevalidationOutcome] = []
        for pid in provider_ids:
            status = self.statuses.get(pid, "fresh")
            record = self._in_use[pid]
            if status == "unreachable":
                record = replace(record, state="unreachable", manifest=None,
                                 manifest_sha256=None, protocol=None, error="gone")
            outcomes.append(RevalidationOutcome(status=status, record=record))  # type: ignore[arg-type]
        return outcomes

    def invalidate(self, provider_id: str) -> None:
        self.invalidated.append(provider_id)
        super().invalidate(provider_id)


class _CountingStore(RunStore):
    def __init__(self, forge_dir: Path) -> None:
        super().__init__(forge_dir)
        self.writes: list[str] = []

    def write(self, run_id: str, name: str, contract: Any) -> str:
        self.writes.append(name)
        return super().write(run_id, name, contract)


CASE_A_INTENT = "analise esse Glue Job porque está lento"


def test_revalidates_every_candidate_before_final_decision(tmp_path: Path) -> None:
    make_workspace(tmp_path, [SPARK_ENTRY, API_ENTRY])
    case_a(tmp_path)
    forge = tmp_path / ".forge"
    registry = _ScriptedRegistry(forge, {})
    store = _CountingStore(forge)
    out = Forger(tmp_path, registry, store).ask(AskRequest(intent=CASE_A_INTENT))
    assert out.status == "ok"
    assert registry.revalidated == [sorted({c.provider for c in out.decision.candidates})]
    assert registry.invalidated == []
    assert not any(lim.startswith("registry-") for lim in out.decision.limitations)
    assert store.writes.count("routing") == 1


def test_ambiguous_decision_is_revalidated(tmp_path: Path) -> None:
    make_workspace(tmp_path, [SPARK_ENTRY, API_ENTRY])
    registry = _ScriptedRegistry(tmp_path / ".forge", {})
    out = Forger(tmp_path, registry, RunStore(tmp_path / ".forge")).ask(
        AskRequest(intent="performance da api"))
    assert out.status == "ambiguous"
    assert registry.revalidated == [["fixture-api", "fixture-spark"]]


def test_second_divergence_is_manifest_changed(tmp_path: Path) -> None:
    make_workspace(tmp_path, [SPARK_ENTRY, API_ENTRY])
    case_a(tmp_path)
    forge = tmp_path / ".forge"
    registry = _ScriptedRegistry(forge, {"fixture-spark": "changed"})
    store = _CountingStore(forge)
    out = Forger(tmp_path, registry, store).ask(AskRequest(intent=CASE_A_INTENT))
    assert out.status == "provider_failure" and out.result is None
    assert out.error is not None and out.error.code == Codes.REGISTRY_MANIFEST_CHANGED
    assert "fixture-spark" in out.error.detail
    assert len(registry.revalidated) == 2  # route redone exactly once
    assert registry.invalidated == ["fixture-spark"]
    assert "registry-revalidated: fixture-spark" in out.decision.limitations
    assert store.writes.count("routing") == 1
    assert store.read_optional(out.run_id, "context") is None
    assert out.receipt.inputs.routing_sha256 == sha256_of(store.read(out.run_id, "routing"))
    assert store.read(out.run_id, "receipt")["status"] == "provider_failure"


def test_unreachable_candidate_is_removed_from_redone_decision(tmp_path: Path) -> None:
    make_workspace(tmp_path, [SPARK_ENTRY, API_ENTRY])
    write_file(tmp_path, "api/openapi.yaml", "openapi: 3.0.0\n")
    write_file(tmp_path, "jobs/orders_glue_job.py", "x = 1\n")
    forge = tmp_path / ".forge"
    # spark: *_job.py glob + glue/job keywords; api: openapi.yaml glob + api keyword.
    # 2 vs 2 types is a tie until fixture-api turns out unreachable.
    intent = "glue job da api"
    first = Forger(tmp_path, _ScriptedRegistry(forge, {}), RunStore(forge)).ask(
        AskRequest(intent=intent))
    assert first.status == "ambiguous"
    registry = _ScriptedRegistry(forge, {"fixture-api": "unreachable"})
    out = Forger(tmp_path, registry, RunStore(forge)).ask(AskRequest(intent=intent))
    assert "fixture-api" not in {c.provider for c in out.decision.candidates}
    assert "registry-unreachable: fixture-api" in out.decision.limitations
    assert out.status == "ok" and out.decision.selected[0].provider == "fixture-spark"
    assert registry.invalidated == []


def test_no_route_skips_revalidation(tmp_path: Path) -> None:
    make_workspace(tmp_path, [])
    registry = _ScriptedRegistry(tmp_path / ".forge", {})
    out = Forger(tmp_path, registry, RunStore(tmp_path / ".forge")).ask(
        AskRequest(intent="bom dia"))
    assert out.status == "no_route"
    assert registry.revalidated == []


def test_fallback_routing_written_once_with_fallbacks(tmp_path: Path) -> None:
    make_workspace(tmp_path, [bad_entry("unhealthy", "bad-a", trust="trusted"),
                              bad_entry("ok", "bad-b", trust="local")])
    forge = tmp_path / ".forge"
    store = _CountingStore(forge)
    out = Forger(tmp_path, Registry(forge), store).ask(
        AskRequest(intent="run it", capability="bad.thing"))
    assert out.status == "ok"
    assert store.writes.count("routing") == 1
    assert store.read(out.run_id, "routing")["fallbacks_used"] == [
        "bad-a:FORGE-HEALTH-UNAVAILABLE"]


def _cand(pid: str, cap: str, types: int) -> Candidate:
    return Candidate(provider=pid, capability=cap, rank_key=[types])


def _signal_decision(candidates: list[Candidate], action: str = "run") -> RoutingDecision:
    return RoutingDecision(
        producer=PRODUCER, created_at=utc_now(), status="routed", task_id="t1",
        candidates=candidates, reason="r", confidence=Confidence(level="high"),
        selected=[Selection(provider=candidates[0].provider,
                            capability=candidates[0].capability, action=action)])


def _signal_forger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, down: set[str]
) -> tuple[Forger, TaskSpec]:
    def fake_health(record: RegistryRecord, **_: object) -> HealthOutcome:
        if record.entry.id in down:
            return HealthOutcome(status="unavailable", error=ErrorInfo(code="X-DOWN", detail="d"))
        return HealthOutcome(status="ok")

    monkeypatch.setattr("theforge.forger.orchestrator.check_health", fake_health)
    task = TaskSpec(producer=PRODUCER, created_at=utc_now(), id="t1", intent="x",
                    workspace_root=str(tmp_path))
    forge = tmp_path / ".forge"
    return Forger(tmp_path, Registry(forge), RunStore(forge)), task


def test_fallback_never_crosses_capability_or_takes_weak_candidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    records = {"a": _rec("a", ("run",), "trusted"),
               "b": _rec("b", ("run",), "local", cap_id="other.cap"),
               "c": _rec("c", ("run",), "local")}
    decision = _signal_decision([_cand("a", "bad.thing", 3), _cand("b", "other.cap", 2),
                                 _cand("c", "bad.thing", 1)])
    forge_, task = _signal_forger(tmp_path, monkeypatch, {"a"})
    final, record, error = forge_._select_healthy(task, decision, records)
    assert record is None
    assert error is not None and error.code == "X-DOWN"
    assert final.fallbacks_used == ["a:X-DOWN"]
    assert final.selected[0].provider == "a"


def test_fallback_takes_strong_same_capability_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    records = {"a": _rec("a", ("run",), "trusted"),
               "b": _rec("b", ("run",), "local", cap_id="other.cap"),
               "d": _rec("d", ("run",), "local")}
    decision = _signal_decision([_cand("a", "bad.thing", 3), _cand("b", "other.cap", 2),
                                 _cand("d", "bad.thing", 2)])
    forge_, task = _signal_forger(tmp_path, monkeypatch, {"a"})
    final, record, _ = forge_._select_healthy(task, decision, records)
    assert record is not None and record.entry.id == "d"
    assert final.selected[0] == Selection(provider="d", capability="bad.thing", action="run")
    assert final.fallbacks_used == ["a:X-DOWN"]


def test_fallback_requires_the_resolved_action(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    records = {"a": _rec("a", ("other", "run"), "trusted"), "b": _rec("b", ("run",), "local")}
    decision = _signal_decision([_cand("a", "bad.thing", 3), _cand("b", "bad.thing", 2)],
                                action="other")
    forge_, task = _signal_forger(tmp_path, monkeypatch, {"a"})
    final, record, _ = forge_._select_healthy(task, decision, records)
    assert record is None
    assert final.fallbacks_used == ["a:X-DOWN"]


def test_selected_provider_without_execute_op_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_workspace(tmp_path, [])
    base = _rec("n", ("run",), "trusted")
    assert base.manifest is not None
    no_exec = replace(base, manifest=replace(base.manifest, ops=["describe", "health"]))

    class _Fixed(Registry):
        def records(self, *, persist: bool = True) -> list[RegistryRecord]:
            self._in_use = {"n": no_exec}
            return [no_exec]

        def revalidate(self, provider_ids: Sequence[str]) -> list[RevalidationOutcome]:
            return [RevalidationOutcome(status="fresh", record=no_exec) for _ in provider_ids]

    def fake_route(task: TaskSpec, *_: object, **__: object) -> RoutingDecision:
        return RoutingDecision(
            producer=PRODUCER, created_at=utc_now(), status="routed", task_id=task.id,
            candidates=[_cand("n", "bad.thing", 1)], reason="forced",
            confidence=Confidence(level="high"),
            selected=[Selection(provider="n", capability="bad.thing", action="run")])

    def boom_factory(argv: Sequence[str]) -> ProviderTransport:
        raise AssertionError("no process may start")

    monkeypatch.setattr("theforge.forger.orchestrator.route", fake_route)
    monkeypatch.setattr("theforge.forger.orchestrator.check_health",
                        lambda record, **_: HealthOutcome(status="ok"))
    forge = tmp_path / ".forge"
    out = Forger(tmp_path, _Fixed(forge), RunStore(forge),
                 transport_factory=boom_factory).ask(
        AskRequest(intent="x", capability="bad.thing"))
    assert out.status == "refused" and out.result is None
    assert out.error is not None and out.error.code == Codes.PROTO_OP_UNSUPPORTED
    assert RunStore(forge).read_optional(out.run_id, "context") is None


# --- policy, risk and provider identity (task 3.7) --------------------------------------------

class _OpRecorder:
    """Transport factory that records every op started, so tests can prove no execute ran."""

    def __init__(self) -> None:
        self.ops: list[str] = []

    def __call__(self, argv: Sequence[str]) -> ProviderTransport:
        return _RecordingTransport(self.ops, argv)


class _RecordingTransport:
    def __init__(self, ops: list[str], argv: Sequence[str]) -> None:
        self.ops = ops
        self.inner = SubprocessTransport(argv)

    def call(self, op: str, payload: dict[str, Any], *, timeout: float,
             cwd: Path | None = None, check_protocol: bool = True) -> Response:
        self.ops.append(op)
        return self.inner.call(op, payload, timeout=timeout, cwd=cwd,
                               check_protocol=check_protocol)


def _policy_forger(tmp_path: Path) -> tuple[Forger, _OpRecorder, RunStore]:
    forge = tmp_path / ".forge"
    recorder = _OpRecorder()
    store = RunStore(forge)
    return Forger(tmp_path, Registry(forge), store, transport_factory=recorder), recorder, store


def test_local_mutation_with_local_trust_is_refused_without_approval(tmp_path: Path) -> None:
    make_workspace(tmp_path, [bad_entry("mutating", "bad-m", trust="local")])
    forger_, recorder, store = _policy_forger(tmp_path)
    out = forger_.ask(AskRequest(intent="run it", capability="bad.thing"))
    assert out.status == "refused" and out.result is None
    assert out.error is not None and out.error.code == Codes.POLICY_APPROVAL_REQUIRED
    assert out.error.unlock == "--approve bad.thing"
    assert "execute" not in recorder.ops
    risk = store.read(out.run_id, "risk")
    assert risk["policy"]["decision"] == "ask" and risk["policy"]["approved"] is False
    assert risk["operation_class"] == "local_mutation"
    assert risk["dimensions"]["local_mutation"] == "yes"
    assert store.read_optional(out.run_id, "context") is None
    assert store.read_optional(out.run_id, "result") is None
    assert out.receipt.status == "refused"
    assert out.receipt.inputs.risk_sha256 == sha256_of(risk)
    assert store.read(out.run_id, "receipt")["error"]["unlock"] == "--approve bad.thing"


def test_local_mutation_with_local_trust_runs_with_approval(tmp_path: Path) -> None:
    make_workspace(tmp_path, [bad_entry("mutating", "bad-m", trust="local")])
    forger_, recorder, store = _policy_forger(tmp_path)
    out = forger_.ask(AskRequest(intent="run it", capability="bad.thing",
                                 approvals=frozenset({"bad.thing"})))
    assert out.status == "ok" and out.result is not None
    assert "execute" in recorder.ops
    risk = store.read(out.run_id, "risk")
    assert risk["policy"]["decision"] == "allow" and risk["policy"]["approved"] is True
    assert out.receipt.inputs.risk_sha256 == sha256_of(risk)


def test_approval_for_another_capability_does_not_unlock(tmp_path: Path) -> None:
    make_workspace(tmp_path, [bad_entry("mutating", "bad-m", trust="local")])
    forger_, recorder, _ = _policy_forger(tmp_path)
    out = forger_.ask(AskRequest(intent="run it", capability="bad.thing",
                                 approvals=frozenset({"demo.echo"})))
    assert out.status == "refused"
    assert out.error is not None and out.error.code == Codes.POLICY_APPROVAL_REQUIRED
    assert "execute" not in recorder.ops


def test_local_mutation_with_trusted_provider_is_allowed(tmp_path: Path) -> None:
    make_workspace(tmp_path, [bad_entry("mutating", "bad-m", trust="trusted")])
    forger_, _, store = _policy_forger(tmp_path)
    out = forger_.ask(AskRequest(intent="run it", capability="bad.thing"))
    assert out.status == "ok"
    policy = store.read(out.run_id, "risk")["policy"]
    assert policy["decision"] == "allow" and policy["approved"] is False
    assert policy["rule"] == "default.local_mutation.trusted"


def test_destructive_is_denied_even_with_approval(tmp_path: Path) -> None:
    make_workspace(tmp_path, [bad_entry("destructive", "bad-d", trust="trusted")])
    forger_, recorder, store = _policy_forger(tmp_path)
    out = forger_.ask(AskRequest(intent="run it", capability="bad.thing",
                                 approvals=frozenset({"bad.thing"})))
    assert out.status == "refused" and out.result is None
    assert out.error is not None and out.error.code == Codes.POLICY_DENIED
    assert "destructive" in out.error.detail
    assert "execute" not in recorder.ops
    risk = store.read(out.run_id, "risk")
    assert risk["policy"]["decision"] == "deny"
    assert store.read_optional(out.run_id, "context") is None
    assert out.receipt.inputs.risk_sha256 == sha256_of(risk)


def test_read_only_echo_receipt_records_identity_and_risk(tmp_path: Path) -> None:
    make_workspace(tmp_path, [])
    write_file(tmp_path, "notes.txt", "hello\n")
    forge = tmp_path / ".forge"
    registry = Registry(forge)
    out = Forger(tmp_path, registry, RunStore(forge)).ask(
        AskRequest(intent="eco", capability="demo.echo"))
    assert out.status == "ok"
    store = RunStore(forge)
    risk = store.read(out.run_id, "risk")
    assert risk["policy"]["decision"] == "allow"
    assert risk["policy"]["rule"] == "default.read_only"
    provider = out.receipt.provider
    assert provider is not None
    expected = fingerprint(registry.get(provider.id).entry)
    assert provider.fingerprint == expected.digest
    assert provider.executable == expected.executable
    assert provider.observed_version == provider.version
    assert out.receipt.inputs.risk_sha256 == sha256_of(risk)
    persisted = store.read(out.run_id, "receipt")
    assert persisted["inputs"]["risk_sha256"] == sha256_of(risk)
    assert persisted["provider"]["fingerprint"] == expected.digest


def test_project_policy_can_tighten_read_only(tmp_path: Path) -> None:
    make_workspace(tmp_path, [])
    write_file(tmp_path, ".forge/config/policy.toml", '[rules]\nread_only = "deny"\n')
    forger_, recorder, store = _policy_forger(tmp_path)
    out = forger_.ask(AskRequest(intent="eco", capability="demo.echo"))
    assert out.status == "refused"
    assert out.error is not None and out.error.code == Codes.POLICY_DENIED
    assert store.read(out.run_id, "risk")["policy"]["rule"] == "project.read_only"
    assert "execute" not in recorder.ops


def test_user_policy_can_loosen_local_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_dir = tmp_path / "user"
    write_file(user_dir, "policy.toml", '[rules]\n"local_mutation.local" = "allow"\n')
    monkeypatch.setenv("THEFORGE_CONFIG_DIR", str(user_dir))
    ws = tmp_path / "ws"
    make_workspace(ws, [bad_entry("mutating", "bad-m", trust="local")])
    forger_, _, store = _policy_forger(ws)
    out = forger_.ask(AskRequest(intent="run it", capability="bad.thing"))
    assert out.status == "ok"
    assert store.read(out.run_id, "risk")["policy"]["rule"] == "user.local_mutation.local"


def test_policy_warnings_become_receipt_limitations(tmp_path: Path) -> None:
    make_workspace(tmp_path, [])
    write_file(tmp_path, ".forge/config/policy.toml", '[rules]\nread_only = "bogus"\n')
    forger_, _, _ = _policy_forger(tmp_path)
    out = forger_.ask(AskRequest(intent="eco", capability="demo.echo"))
    assert out.status == "ok"
    assert any("policy" in lim and "bogus" in lim for lim in out.receipt.limitations)


# --- aliases, deprecation and overlap in persisted decisions (task 2.2) -----------------------

def _alias_rec(pid: str, cap_id: str, trust: str, *, aliases: Sequence[str] = (),
               deprecated: bool = False, replaced_by: str | None = None,
               execute: bool = True) -> RegistryRecord:
    base = _rec(pid, ("run",), trust, cap_id=cap_id)
    assert base.manifest is not None
    capability = replace(base.manifest.capabilities[0], aliases=list(aliases),
                         deprecated=deprecated, replaced_by=replaced_by)
    ops = ["describe", "health", "execute"] if execute else ["describe", "health"]
    return replace(base, manifest=replace(base.manifest, capabilities=[capability], ops=ops))


def _fixed_forger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fixed: list[RegistryRecord]
) -> Forger:
    """A Forger over a fixed registry whose execute always fails at the transport, so the
    routing decision is persisted without any provider process."""
    make_workspace(tmp_path, [])

    class _Fixed(Registry):
        def records(self, *, persist: bool = True) -> list[RegistryRecord]:
            self._in_use = {r.entry.id: r for r in fixed}
            return list(fixed)

        def revalidate(self, provider_ids: Sequence[str]) -> list[RevalidationOutcome]:
            by_id = {r.entry.id: r for r in fixed}
            return [RevalidationOutcome(status="fresh", record=by_id[p]) for p in provider_ids]

    class _Down:
        def call(self, op: str, payload: dict[str, Any], **_: object) -> Response:
            raise TransportError(Codes.PROTO_EXIT, "down")

    monkeypatch.setattr("theforge.forger.orchestrator.check_health",
                        lambda record, **_: HealthOutcome(status="ok"))
    forge = tmp_path / ".forge"
    return Forger(tmp_path, _Fixed(forge), RunStore(forge),
                  transport_factory=lambda argv: _Down())  # type: ignore[arg-type,return-value]


def _persisted(tmp_path: Path, run_id: str) -> dict[str, Any]:
    routing: dict[str, Any] = RunStore(tmp_path / ".forge").read(run_id, "routing")
    return routing


def test_persisted_explicit_decision_resolves_alias_and_prefers_canonical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    canon = _alias_rec("canon", "data.quality", "local")
    aliased = _alias_rec("aliased", "data.checks", "trusted", aliases=["data.quality"])
    out = _fixed_forger(tmp_path, monkeypatch, [aliased, canon]).ask(
        AskRequest(intent="x", capability="data.quality"))
    routing = _persisted(tmp_path, out.run_id)
    assert routing["selected"][0]["provider"] == "canon"
    assert routing["selected"][0]["capability"] == "data.quality"

    alias_only = _fixed_forger(tmp_path / "w2", monkeypatch, [aliased]).ask(
        AskRequest(intent="x", capability="data.quality"))
    routing = _persisted(tmp_path / "w2", alias_only.run_id)
    selected = routing["selected"][0]
    assert (selected["provider"], selected["capability"]) == ("aliased", "data.checks")
    assert "capability-alias: 'data.quality' resolved to 'data.checks' (aliased)" \
        in routing["limitations"]
    task = RunStore(tmp_path / "w2" / ".forge").read(alias_only.run_id, "task")
    assert task["requested_capability"] == "data.quality"


def test_persisted_explicit_decision_notes_deprecation_and_overlap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = _alias_rec("a", "data.quality", "trusted", deprecated=True, replaced_by="data.q2")
    b = _alias_rec("b", "data.quality", "local")
    out = _fixed_forger(tmp_path, monkeypatch, [a, b]).ask(
        AskRequest(intent="x", capability="data.quality"))
    routing = _persisted(tmp_path, out.run_id)
    assert routing["confidence"]["level"] == "high"
    assert "capability-deprecated: 'data.quality' (a) is deprecated; replaced_by 'data.q2'" \
        in routing["limitations"]
    assert "capability-overlap: 'data.quality' declared by a, b; tie-break trust then id" \
        in routing["limitations"]


def test_persisted_signal_decision_notes_overlap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = _alias_rec("a", "bad.thing", "trusted")
    b = _alias_rec("b", "bad.thing", "local", deprecated=True)
    out = _fixed_forger(tmp_path, monkeypatch, [a, b]).ask(AskRequest(intent="bad"))
    routing = _persisted(tmp_path, out.run_id)
    assert out.status == "ambiguous"
    assert "capability-overlap: 'bad.thing' declared by a, b" in routing["limitations"]
    assert "capability-deprecated: 'bad.thing' (b) is deprecated; no replacement declared" \
        in routing["limitations"]


def test_alias_requested_without_execute_is_refused_with_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """2.1 refusal also covers a capability requested by its alias."""
    no_exec = _alias_rec("aliased", "data.checks", "local", aliases=["data.quality"],
                         execute=False)
    out = _fixed_forger(tmp_path, monkeypatch, [no_exec]).ask(
        AskRequest(intent="x", capability="data.quality"))
    assert out.status == "refused" and out.result is None
    assert out.error is not None and out.error.code == Codes.PROTO_OP_UNSUPPORTED
    assert "aliased" in out.error.detail
