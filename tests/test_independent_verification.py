"""Cycle 3 Wave G: independent verification (``can_verify`` + the ``verify`` op).

Unit layer: ``select_verifier`` picks a distinct-identity provider that declares
``can_verify`` on ``<producer>/<capability>`` and the ``verify`` op — the
producer itself (same id or same argv) is never independent — and
``request_verdict`` maps envelope answers into the ``independent`` check
(verdicts, refusals, errors, malformed payloads, producer mismatches and
transport failures).
Integration layer: real ask runs with the fixture providers — a declared
verifier answering ``passed``/``failed`` (failure demotes the run to
``partial``), no verifier recorded as ``not_performed``, and a provider
verifying itself never counting as independent.
"""

import importlib.util
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from helpers import (
    PROVIDERS,
    SELFVERIFY_ENTRY,
    SPARK_ENTRY,
    VERIFIER_ENTRY,
    VERIFIER_FAIL_ENTRY,
    case_a,
    case_b,
    fixture_argv,
    make_workspace,
)
from theforge.contracts import (
    Capability,
    CapabilityRelations,
    ErrorInfo,
    ForgeManifest,
    Producer,
    Response,
)
from theforge.contracts.verification import VerificationResult
from theforge.forger import AskRequest, Forger
from theforge.forger.verification import (
    request_verdict,
    select_verifier,
)
from theforge.protocol import SubprocessTransport
from theforge.protocol.transport import TransportError
from theforge.registry import Registry
from theforge.registry.config import ProviderEntry
from theforge.registry.registry import RegistryRecord
from theforge.runs import RunStore


def _cap(cid: str, *, can_verify: tuple[str, ...] = ()) -> Capability:
    return Capability(id=cid, actions=["run"], default_action="run",
                      state="supported", operation_class="read_only",
                      relations=CapabilityRelations(can_verify=list(can_verify)))


def _manifest(pid: str, *caps: Capability, ops: list[str] | None = None
              ) -> ForgeManifest:
    return ForgeManifest(
        id=pid, version="0.1", protocols=["forge/v1"],
        ops=ops if ops is not None else ["describe", "health", "execute", "verify"],
        domains=[], capabilities=list(caps))


def _record(pid: str, manifest: ForgeManifest | None, *, argv: list[str] | None = None,
            trust: str = "local", state: str | None = None) -> RegistryRecord:
    return RegistryRecord(
        entry=ProviderEntry(id=pid, argv=argv if argv is not None else [pid],
                            trust=trust),
        state=state or ("ready" if manifest else "broken"), manifest=manifest)


def _forger(root: Path) -> tuple[Forger, RunStore]:
    forge = root / ".forge"
    store = RunStore(forge)
    return Forger(root, Registry(forge), store), store


# --- select_verifier -------------------------------------------------------------------------


def test_select_verifier_picks_declared_provider() -> None:
    producer = _record("prod-a", _manifest("prod-a", _cap("run.thing")))
    verifier = _record("verif-b", _manifest(
        "verif-b", _cap("audit.verify", can_verify=("prod-a/run.thing",))))
    other = _record("other-c", _manifest(
        "other-c", _cap("audit.verify", can_verify=("prod-a/other.cap",))))
    picked, reason = select_verifier([other, producer, verifier],
                                     producer=producer, capability="run.thing")
    assert reason == "" and picked is verifier


def test_select_verifier_needs_the_verify_op() -> None:
    producer = _record("prod-a", _manifest("prod-a", _cap("run.thing")))
    no_op = _record("verif-b",
                    _manifest("verif-b",
                              _cap("audit.verify", can_verify=("prod-a/run.thing",)),
                              ops=["describe", "health", "execute"]))
    picked, reason = select_verifier([producer, no_op], producer=producer,
                                     capability="run.thing")
    assert picked is None and "no provider declares can_verify" in reason


def test_select_verifier_reports_missing_capability() -> None:
    producer = _record("prod-a", _manifest("prod-a", _cap("run.thing")))
    picked, reason = select_verifier([producer], producer=producer,
                                     capability="run.thing")
    assert picked is None
    assert reason == ("no independent verifier for prod-a/run.thing: "
                      "no provider declares can_verify")


def test_producer_is_never_its_own_independent_verifier() -> None:
    """A provider whose capability can_verify its sibling stays self-verification."""
    manifest = _manifest("prod-a", _cap("run.thing"),
                         _cap("audit.verify", can_verify=("prod-a/run.thing",)))
    producer = _record("prod-a", manifest)
    picked, reason = select_verifier([producer], producer=producer,
                                     capability="run.thing")
    assert picked is None and "same identity" in reason


def test_same_argv_under_another_id_is_not_independent() -> None:
    producer = _record("prod-a", _manifest("prod-a", _cap("run.thing")),
                       argv=["same", "argv"])
    clone = _record("clone-b", _manifest(
        "clone-b", _cap("audit.verify", can_verify=("prod-a/run.thing",))),
        argv=["same", "argv"])
    picked, reason = select_verifier([producer, clone], producer=producer,
                                     capability="run.thing")
    assert picked is None and "clone-b: same identity" in reason


def test_blocked_and_unverified_verifiers_are_rejected() -> None:
    producer = _record("prod-a", _manifest("prod-a", _cap("run.thing")))
    blocked = _record("verif-b", _manifest(
        "verif-b", _cap("audit.verify", can_verify=("prod-a/run.thing",))),
        trust="blocked")
    picked, reason = select_verifier([producer, blocked], producer=producer,
                                     capability="run.thing")
    assert picked is None and "verif-b: blocked" in reason
    unverified = _record("verif-u", _manifest(
        "verif-u", _cap("audit.verify", can_verify=("prod-a/run.thing",))),
        trust="unverified")
    picked, reason = select_verifier([producer, unverified], producer=producer,
                                     capability="run.thing")
    assert picked is None and "verif-u: unverified" in reason
    picked, _ = select_verifier([producer, unverified], producer=producer,
                                capability="run.thing", allow_unverified=True)
    assert picked is unverified


def test_broken_records_and_sorted_pick() -> None:
    producer = _record("prod-a", _manifest("prod-a", _cap("run.thing")))
    broken = _record("verif-a", None)
    second = _record("verif-z", _manifest(
        "verif-z", _cap("audit.verify", can_verify=("prod-a/run.thing",))))
    first = _record("verif-b", _manifest(
        "verif-b", _cap("audit.verify", can_verify=("prod-a/run.thing",))))
    picked, _ = select_verifier([second, broken, first], producer=producer,
                                capability="run.thing")
    assert picked is first  # deterministic: lowest id among eligible candidates


# --- request_verdict -------------------------------------------------------------------------


class _FakeTransport:
    def __init__(self, response: Response | None = None,
                 error: TransportError | None = None) -> None:
        self.response = response
        self.error = error
        self.requests: list[dict[str, Any]] = []

    def __call__(self, argv: Sequence[str]) -> "_FakeTransport":
        return self

    def call(self, op: str, payload: dict[str, Any], *, timeout: float,
             cwd: Path | None = None, check_protocol: bool = True) -> Response:
        self.requests.append({"op": op, "payload": payload})
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


def _verifier() -> RegistryRecord:
    return _record("verif-b", _manifest(
        "verif-b", _cap("audit.verify", can_verify=("prod-a/run.thing",))))


def _verify_response(payload: dict[str, Any], *, pid: str = "verif-b",
                     status: str = "ok", error: dict[str, Any] | None = None
                     ) -> Response:
    return Response(request_id="r", op="verify", producer=Producer(id=pid, version="0.1"),
                    status=status, payload=payload,
                    error=ErrorInfo(**error) if error is not None else None)


def _verdict_args() -> dict[str, Any]:
    from theforge.contracts import ExecutionResult, TaskSpec
    task = TaskSpec(producer=Producer(id="theforge", version="1"),
                    created_at="2026-01-01T00:00:00Z", id="run-1", intent="run it",
                    workspace_root="/w", targets=["."], budget_profile="balanced")
    result = ExecutionResult(producer=Producer(id="prod-a", version="0.1"),
                             created_at="2026-01-01T00:00:00Z", status="ok")
    return {"run_id": "run-1", "task": task, "capability": "run.thing",
            "action": "run", "result": result}


def test_verdict_passed_maps_into_the_check() -> None:
    transport = _FakeTransport(_verify_response(
        {"status": "passed", "details": ["recomputed ok"], "basis": ["replay"]}))
    check = request_verdict(_verifier(), transport_factory=transport, **_verdict_args())
    assert check.status == "passed"
    assert check.basis == ["verifier:verif-b", "replay"]
    assert check.details == ["recomputed ok"]
    assert transport.requests[0]["op"] == "verify"
    assert transport.requests[0]["payload"]["capability"] == "run.thing"


def test_verdict_failed_maps_into_the_check() -> None:
    transport = _FakeTransport(_verify_response(
        {"status": "failed", "details": ["evidence does not reproduce"]}))
    check = request_verdict(_verifier(), transport_factory=transport, **_verdict_args())
    assert check.status == "failed"
    assert check.basis == ["verifier:verif-b"]


def test_refused_and_error_are_not_verdicts() -> None:
    transport = _FakeTransport(_verify_response(
        {}, status="refused",
        error={"code": "X", "detail": "cannot judge", "field": None, "unlock": None}))
    check = request_verdict(_verifier(), transport_factory=transport, **_verdict_args())
    assert check.status == "not_performed"
    assert "verifier refused: X: cannot judge" in check.details[0]
    transport = _FakeTransport(_verify_response(
        {}, status="error",
        error={"code": "Y", "detail": "crashed", "field": None, "unlock": None}))
    check = request_verdict(_verifier(), transport_factory=transport, **_verdict_args())
    assert check.status == "not_performed"
    assert "verifier error: Y: crashed" in check.details[0]


def test_malformed_verdict_is_not_performed() -> None:
    transport = _FakeTransport(_verify_response({"status": "bogus"}))
    check = request_verdict(_verifier(), transport_factory=transport, **_verdict_args())
    assert check.status == "not_performed"
    assert check.details[0].startswith("malformed verdict:")


def test_producer_mismatch_is_not_performed() -> None:
    transport = _FakeTransport(_verify_response({"status": "passed"}, pid="impostor"))
    check = request_verdict(_verifier(), transport_factory=transport, **_verdict_args())
    assert check.status == "not_performed"
    assert check.details[0].startswith("verifier response:")


def test_transport_failure_is_not_performed() -> None:
    transport = _FakeTransport(error=TransportError(code="FORGE-PROTO-TIMEOUT",
                                                    detail="timed out"))
    check = request_verdict(_verifier(), transport_factory=transport, **_verdict_args())
    assert check.status == "not_performed"
    assert "verify call failed: FORGE-PROTO-TIMEOUT" in check.details[0]


# --- real runs --------------------------------------------------------------------------------


def test_declared_verifier_passes_the_run(tmp_path: Path) -> None:
    make_workspace(tmp_path, [SPARK_ENTRY, VERIFIER_ENTRY])
    case_a(tmp_path)
    forger, store = _forger(tmp_path)
    out = forger.ask(AskRequest(intent="analise esse Glue Job porque está lento"))
    assert out.status == "ok" and out.verification is not None
    check = out.verification.independent
    assert check.status == "passed"
    assert check.basis[0] == "verifier:fixture-verifier"
    assert "verifier replayed the declared checks" in check.details
    persisted = store.read_contract(out.run_id, "verification", VerificationResult)
    assert persisted.independent == check
    # G4: a passed verdict never upgrades the producer's evidence epistemic.
    assert out.result is not None
    assert {e.epistemic for e in out.result.evidence} == {"observed"}


def test_failed_verdict_demotes_the_run(tmp_path: Path) -> None:
    make_workspace(tmp_path, [SPARK_ENTRY, VERIFIER_FAIL_ENTRY])
    case_a(tmp_path)
    forger, _ = _forger(tmp_path)
    out = forger.ask(AskRequest(intent="analise esse Glue Job porque está lento"))
    assert out.verification is not None
    assert out.verification.independent.status == "failed"
    assert out.verification.independent.basis[0] == "verifier:fixture-verifier-fail"
    assert out.status == "partial"
    assert out.result is not None
    assert any("independent verification failed: fixture-verifier-fail" in note
               for note in out.result.limitations)


def test_no_declared_verifier_records_not_performed(tmp_path: Path) -> None:
    make_workspace(tmp_path, [SPARK_ENTRY])
    case_a(tmp_path)
    forger, _ = _forger(tmp_path)
    out = forger.ask(AskRequest(intent="analise esse Glue Job porque está lento"))
    assert out.status == "ok" and out.verification is not None
    check = out.verification.independent
    assert check.status == "not_performed"
    assert check.details == [
        "no independent verifier for fixture-spark/spark.performance: "
        "no provider declares can_verify"]


def test_provider_verifying_itself_is_not_independent(tmp_path: Path) -> None:
    make_workspace(tmp_path, [SELFVERIFY_ENTRY])
    forger, _ = _forger(tmp_path)
    out = forger.ask(AskRequest(intent="selfverify thing",
                                capability="self.thing",
                                provider="fixture-selfverify"))
    assert out.status == "ok" and out.verification is not None
    check = out.verification.independent
    assert check.status == "not_performed"
    assert "fixture-selfverify: same identity as the producer" in check.details[0]


def test_plan_node_runs_independent_verification(tmp_path: Path) -> None:
    """Plan nodes go through ``ask``: the verify op covers them for free."""
    import json

    from helpers import SPARK_PLAN_ENTRY
    from theforge.forger import PlanCommand, PlanExecutor

    make_workspace(tmp_path, [SPARK_PLAN_ENTRY, VERIFIER_ENTRY])
    case_a(tmp_path)
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps({
        "task_id": "from-file", "pattern": "pipeline", "source": "file",
        "profile": "max",
        "nodes": [{"id": "n1", "role": "standalone",
                   "provider": "fixture-spark",
                   "capability": "spark.performance", "action": "diagnose"}],
        }), encoding="utf-8")
    store = RunStore(tmp_path / ".forge")
    executor = PlanExecutor(Forger(tmp_path, Registry(tmp_path / ".forge"), store))
    out = executor.run(PlanCommand(intent="otimize o job", profile="max",
                                   plan_file=plan_file, execute=True))
    assert out.status == "ok" and out.result is not None
    child = next(n.run_id for n in out.result.nodes if n.node == "n1")
    assert child is not None
    persisted = store.read_contract(child, "verification", VerificationResult)
    assert persisted.independent.status == "passed"
    assert persisted.independent.basis[0] == "verifier:fixture-verifier"


def test_verify_payload_is_bounded_and_redacted(tmp_path: Path) -> None:
    """The verifier receives the persisted result + task — never workspace files."""
    make_workspace(tmp_path, [SPARK_ENTRY, VERIFIER_ENTRY])
    case_a(tmp_path)
    requests: list[dict[str, Any]] = []

    class _Spy(SubprocessTransport):
        def call(self, op: str, payload: dict[str, Any], *, timeout: float,
                 cwd: Path | None = None, check_protocol: bool = True) -> Response:
            requests.append({"op": op, "payload": payload})
            return super().call(op, payload, timeout=timeout, cwd=cwd,
                                check_protocol=check_protocol)

    forge = tmp_path / ".forge"
    store = RunStore(forge)
    forger = Forger(tmp_path, Registry(forge), store, transport_factory=_Spy)
    out = forger.ask(AskRequest(intent="analise esse Glue Job porque está lento"))
    assert out.status == "ok"
    verify = next(r for r in requests if r["op"] == "verify")
    payload = verify["payload"]
    assert payload["capability"] == "spark.performance"
    assert payload["run_id"] == out.run_id
    assert payload["result"]["producer"]["id"] == "fixture-spark"
    assert payload["handoff"] is None


# --- real Doctor adapters in --replay (cycle 3.1 wave E) -------------------------------------

DOCTOR_FIXTURES = Path(__file__).parent / "fixtures" / "native"
# Producer fixtures that stand in under the real provider ids, so the Doctors'
# declared can_verify refs resolve: spark-forge-aws/pyspark.static-analysis is
# audited by forge-doctor-data, api-forge/api.analyze by forge-doctor-api.
SPARKFORGE_ENTRY = {
    "id": "spark-forge-aws",
    "argv": fixture_argv("fixture_forge.py",
                         str(PROVIDERS / "fixture-sparkforge-aws.json")),
    "trust": "local",
}
SPARKFORGE_HASH_ENTRY = {
    "id": "spark-forge-aws",
    "argv": fixture_argv("fixture_forge.py",
                         str(PROVIDERS / "fixture-sparkforge-aws-hash.json")),
    "trust": "local",
}
APIFORGE_ENTRY = {
    "id": "api-forge",
    "argv": fixture_argv("fixture_forge.py",
                         str(PROVIDERS / "fixture-apiforge.json")),
    "trust": "local",
}
DOCTORDATA_ENTRY = {
    "id": "forge-doctor-data",
    "argv": [sys.executable, "-m", "theforge_doctordata", "--replay",
             str(DOCTOR_FIXTURES / "doctordata" / "default")],
    "trust": "local",
}
DOCTORAPI_ENTRY = {
    "id": "forge-doctor-api",
    "argv": [sys.executable, "-m", "theforge_doctorapi", "--replay",
             str(DOCTOR_FIXTURES / "doctorapi" / "default")],
    "trust": "local",
}
HAS_DOCTORDATA = importlib.util.find_spec("theforge_doctordata") is not None
HAS_DOCTORAPI = importlib.util.find_spec("theforge_doctorapi") is not None


@pytest.mark.skipif(not HAS_DOCTORDATA,
                    reason="theforge_doctordata adapter is not installed")
def test_real_doctor_data_verifies_a_spark_run(tmp_path: Path) -> None:
    """Phase 14/16: Spark Forge AWS run -> Doctor Data ``verify`` op -> passed."""
    make_workspace(tmp_path, [SPARKFORGE_ENTRY, DOCTORDATA_ENTRY])
    case_a(tmp_path)
    forger, store = _forger(tmp_path)
    out = forger.ask(AskRequest(
        intent="analise esse Glue Job porque está lento", provider="spark-forge-aws",
        capability="pyspark.static-analysis", action="pyspark"))
    assert out.status == "ok" and out.verification is not None
    check = out.verification.independent
    assert check.status == "passed"
    assert check.basis == ["verifier:forge-doctor-data",
                           "forge-doctor-data/coherence-audit"]
    assert "result-coherence: passed" in check.details
    persisted = store.read_contract(out.run_id, "verification", VerificationResult)
    assert persisted.independent == check


@pytest.mark.skipif(not HAS_DOCTORDATA,
                    reason="theforge_doctordata adapter is not installed")
def test_real_doctor_data_fails_unverifiable_evidence(tmp_path: Path) -> None:
    """The Doctor catches what the contract allows but no one can re-hash."""
    make_workspace(tmp_path, [SPARKFORGE_HASH_ENTRY, DOCTORDATA_ENTRY])
    case_a(tmp_path)
    forger, _ = _forger(tmp_path)
    out = forger.ask(AskRequest(
        intent="analise esse Glue Job porque está lento", provider="spark-forge-aws",
        capability="pyspark.static-analysis", action="pyspark"))
    assert out.verification is not None
    check = out.verification.independent
    assert check.status == "failed"
    assert check.basis[0] == "verifier:forge-doctor-data"
    assert any("hash without location" in detail for detail in check.details)
    assert out.status == "partial"  # an independent failure demotes the run
    assert out.result is not None
    assert any("independent verification failed: forge-doctor-data" in note
               for note in out.result.limitations)


@pytest.mark.skipif(not HAS_DOCTORAPI,
                    reason="theforge_doctorapi adapter is not installed")
def test_real_doctor_api_verifies_an_api_run(tmp_path: Path) -> None:
    """Phase 14/16: API Forge run -> Doctor API ``verify`` op -> passed."""
    make_workspace(tmp_path, [APIFORGE_ENTRY, DOCTORAPI_ENTRY])
    case_b(tmp_path)
    forger, store = _forger(tmp_path)
    out = forger.ask(AskRequest(
        intent="analyze this api contract", provider="api-forge",
        capability="api.analyze", action="analyze"))
    assert out.status == "ok" and out.verification is not None
    check = out.verification.independent
    assert check.status == "passed"
    assert check.basis == ["verifier:forge-doctor-api",
                           "forge-doctor-api/coherence-audit"]
    persisted = store.read_contract(out.run_id, "verification", VerificationResult)
    assert persisted.independent == check
