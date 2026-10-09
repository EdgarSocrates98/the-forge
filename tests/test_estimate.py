"""Estimator (task 2.7): the `plan` op estimate and the stricter policy decision.

The `plan` op is called only on providers that declare it, on the same hardened surface as
describe/health (temporary cwd, minimal environment, timeout, `producer` checked). Absence
of the op and every failure become an unknown estimate with a limitation, never a planning
failure (10.1, 10.3); `verify` and `estimate` are never called (10.4). `stricter_decision`
keeps the most restrictive of two decisions: `deny` > `ask` > `allow` (10.2).
"""

import itertools
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from tests.helpers import PROVIDERS, bad_argv, fixture_argv

from theforge.contracts import (
    ErrorInfo,
    PolicyDecision,
    Producer,
    Response,
    TaskSpec,
    from_dict,
)
from theforge.contracts.canonical import utc_now
from theforge.contracts.codes import Codes
from theforge.contracts.manifest import ForgeManifest
from theforge.contracts.plan import PlanEstimate
from theforge.meta import PRODUCER
from theforge.planning.estimate import request_estimate, stricter_decision
from theforge.protocol import SubprocessTransport, TransportError
from theforge.registry import ProviderEntry, RegistryRecord

PREFIX = f"estimate: {Codes.PLAN_ESTIMATE}: "


def _manifest_from_file(name: str) -> ForgeManifest:
    data = json.loads((PROVIDERS / name).read_text(encoding="utf-8"))
    data.pop("estimate", None)
    return from_dict(ForgeManifest, data)


def _record(
    pid: str,
    argv: list[str],
    manifest: ForgeManifest,
    *,
    trust: str = "local",
    state: str = "ready",
) -> RegistryRecord:
    return RegistryRecord(
        entry=ProviderEntry(id=pid, argv=argv, trust=trust),  # type: ignore[arg-type]
        state=state,
        manifest=manifest,
    )  # type: ignore[arg-type]


def _fixture_record(name: str) -> RegistryRecord:
    manifest = _manifest_from_file(name)
    return _record(manifest.id, fixture_argv("fixture_forge.py", str(PROVIDERS / name)), manifest)


def _bad_record(mode: str) -> RegistryRecord:
    pid = "bad-forge"
    response = SubprocessTransport(bad_argv(mode, pid)).call("describe", {}, timeout=10.0)
    manifest = from_dict(ForgeManifest, response.payload)
    return _record(pid, bad_argv(mode, pid), manifest)


def _task() -> TaskSpec:
    return TaskSpec(
        producer=PRODUCER,
        created_at=utc_now(),
        id="t1",
        intent="spark job lento",
        workspace_root=".",
    )


def _decision(decision: str, rule: str = "r") -> PolicyDecision:
    return PolicyDecision(
        decision=decision,
        rule=rule,
        reason=f"{decision} reason",  # type: ignore[arg-type]
        approved=decision == "allow",
    )


class _SpyTransport:
    """Records each op; answers with a canned response or raises a canned error."""

    calls: list[tuple[str, dict[str, Any], float, Path | None]] = []

    def __init__(
        self,
        argv: Sequence[str],
        *,
        response: Response | None = None,
        error: TransportError | None = None,
    ) -> None:
        self.argv = list(argv)
        self.response = response
        self.error = error

    def call(
        self,
        op: str,
        payload: dict[str, Any],
        *,
        timeout: float,
        cwd: Path | None = None,
        check_protocol: bool = True,
    ) -> Response:
        _SpyTransport.calls.append((op, payload, timeout, cwd))
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


def _spy_factory(**kwargs: Any) -> Any:
    _SpyTransport.calls = []
    return lambda argv: _SpyTransport(argv, **kwargs)


def _ok_response(producer: Producer, payload: dict[str, Any]) -> Response:
    return Response(
        protocol="forge/v1",
        request_id="r1",
        op="plan",
        producer=producer,
        status="ok",
        payload=payload,
    )


# ---------------------------------------------------------------- request_estimate (10.1)


def test_fixture_with_plan_op_estimate_is_recorded() -> None:
    record = _fixture_record("fixture-spark-plan.json")
    estimate, limitation = request_estimate(
        record, _task(), "spark.performance", "diagnose", transport_factory=SubprocessTransport
    )
    assert limitation is None
    assert estimate == PlanEstimate(
        context_needed=["*_job.py", "requirements*.txt"],
        operation_class="read_only",
        expected_artifacts=[],
        unknowns=["input data volume"],
        limitations=[],
    )


def test_stricter_estimate_from_bad_forge_is_read() -> None:
    record = _bad_record("plan-estimate-stricter")
    capability = record.manifest.capabilities[0]  # type: ignore[union-attr]
    estimate, limitation = request_estimate(
        record, _task(), capability.id, capability.actions[0], transport_factory=SubprocessTransport
    )
    assert limitation is None
    assert estimate is not None and estimate.operation_class == "local_mutation"


def test_request_carries_plan_request_and_runs_in_temporary_cwd() -> None:
    record = _fixture_record("fixture-spark-plan.json")
    producer = Producer(id=record.entry.id, version=record.manifest.version)  # type: ignore[union-attr]
    factory = _spy_factory(response=_ok_response(producer, {"operation_class": "read_only"}))
    task = _task()
    estimate, limitation = request_estimate(
        record, task, "spark.performance", "diagnose", transport_factory=factory, timeout=3.5
    )
    assert limitation is None and estimate is not None
    [(op, payload, timeout, cwd)] = _SpyTransport.calls
    assert op == "plan"
    assert timeout == 3.5
    assert payload["capability"] == "spark.performance" and payload["action"] == "diagnose"
    assert payload["task"]["id"] == task.id
    assert cwd is not None and cwd.resolve() != Path.cwd().resolve()
    assert not cwd.exists()  # temporary directory removed after the call


def test_open_schema_ignores_unknown_fields() -> None:
    record = _fixture_record("fixture-spark-plan.json")
    producer = Producer(id=record.entry.id, version=record.manifest.version)  # type: ignore[union-attr]
    factory = _spy_factory(
        response=_ok_response(producer, {"operation_class": "read_only", "future_field": 1})
    )
    estimate, limitation = request_estimate(
        record, _task(), "spark.performance", "diagnose", transport_factory=factory
    )
    assert limitation is None and estimate == PlanEstimate(operation_class="read_only")


# ------------------------------------------------------- unknown estimate + limitation (10.3)


def test_provider_without_plan_op_is_never_called() -> None:
    record = _fixture_record("fixture-spark.json")
    factory = _spy_factory(error=TransportError("X", "must not be called"))
    estimate, limitation = request_estimate(
        record, _task(), "spark.performance", "diagnose", transport_factory=factory
    )
    assert estimate is None
    assert limitation == "estimate: provider does not declare op plan"
    assert _SpyTransport.calls == []


def test_error_response_becomes_limitation() -> None:
    record = _bad_record("plan-error")
    capability = record.manifest.capabilities[0]  # type: ignore[union-attr]
    estimate, limitation = request_estimate(
        record, _task(), capability.id, capability.actions[0], transport_factory=SubprocessTransport
    )
    assert estimate is None
    assert limitation is not None and limitation.startswith(PREFIX)
    assert "BAD-PLAN-FAILED" in limitation and "cannot estimate" in limitation


def test_timeout_becomes_limitation() -> None:
    record = _fixture_record("fixture-spark-plan.json")
    sleeper = [sys.executable, "-c", "import time; time.sleep(30)"]
    record = _record(record.entry.id, sleeper, record.manifest)  # type: ignore[arg-type]
    estimate, limitation = request_estimate(
        record,
        _task(),
        "spark.performance",
        "diagnose",
        transport_factory=SubprocessTransport,
        timeout=1.0,
    )
    assert estimate is None
    assert limitation is not None and limitation.startswith(PREFIX)
    assert Codes.PROTO_TIMEOUT in limitation


def test_wrong_producer_becomes_limitation() -> None:
    record = _fixture_record("fixture-spark-plan.json")
    factory = _spy_factory(
        response=_ok_response(
            Producer(id="someone-else", version="0.0.1"), {"operation_class": "read_only"}
        )
    )
    estimate, limitation = request_estimate(
        record, _task(), "spark.performance", "diagnose", transport_factory=factory
    )
    assert estimate is None
    assert limitation is not None and limitation.startswith(PREFIX)
    assert "producer" in limitation


def test_off_contract_payload_becomes_limitation() -> None:
    record = _fixture_record("fixture-spark-plan.json")
    producer = Producer(id=record.entry.id, version=record.manifest.version)  # type: ignore[union-attr]
    factory = _spy_factory(response=_ok_response(producer, {"operation_class": "nuke"}))
    estimate, limitation = request_estimate(
        record, _task(), "spark.performance", "diagnose", transport_factory=factory
    )
    assert estimate is None
    assert limitation is not None and limitation.startswith(PREFIX)
    assert Codes.PROTO_SCHEMA in limitation


def test_secret_in_provider_error_is_redacted() -> None:
    record = _fixture_record("fixture-spark-plan.json")
    producer = Producer(id=record.entry.id, version=record.manifest.version)  # type: ignore[union-attr]
    factory = _spy_factory(
        response=Response(
            protocol="forge/v1",
            request_id="r1",
            op="plan",
            producer=producer,
            status="error",
            payload={},
            error=ErrorInfo(code="X-FAIL", detail="token=supersecretvalue123"),
        )
    )
    _, limitation = request_estimate(
        record, _task(), "spark.performance", "diagnose", transport_factory=factory
    )
    assert limitation is not None and "supersecretvalue123" not in limitation


@pytest.mark.parametrize(
    ("trust", "state"), [("blocked", "ready"), ("unverified", "ready"), ("local", "invalid")]
)
def test_untrusted_or_not_ready_provider_is_not_called(trust: str, state: str) -> None:
    base = _fixture_record("fixture-spark-plan.json")
    record = _record(
        base.entry.id,
        base.entry.argv,
        base.manifest,  # type: ignore[arg-type]
        trust=trust,
        state=state,
    )
    factory = _spy_factory(error=TransportError("X", "must not be called"))
    estimate, limitation = request_estimate(
        record, _task(), "spark.performance", "diagnose", transport_factory=factory
    )
    assert estimate is None
    assert limitation is not None and limitation.startswith(PREFIX)
    assert _SpyTransport.calls == []


def test_unverified_provider_runs_with_explicit_consent() -> None:
    base = _fixture_record("fixture-spark-plan.json")
    record = _record(
        base.entry.id,
        base.entry.argv,
        base.manifest,  # type: ignore[arg-type]
        trust="unverified",
    )
    estimate, limitation = request_estimate(
        record,
        _task(),
        "spark.performance",
        "diagnose",
        transport_factory=SubprocessTransport,
        allow_unverified=True,
    )
    assert limitation is None and estimate is not None


def test_reserved_ops_are_never_called() -> None:
    """Only `plan` crosses the wire, whatever the outcome (10.4)."""
    record = _fixture_record("fixture-spark-plan.json")
    producer = Producer(id=record.entry.id, version=record.manifest.version)  # type: ignore[union-attr]
    ops: list[str] = []
    outcomes: list[dict[str, Any]] = [
        {"response": _ok_response(producer, {})},
        {"error": TransportError(Codes.PROTO_TIMEOUT, "slow")},
    ]
    for outcome in outcomes:
        request_estimate(
            record,
            _task(),
            "spark.performance",
            "diagnose",
            transport_factory=_spy_factory(**outcome),
        )
        ops += [call[0] for call in _SpyTransport.calls]
    assert ops == ["plan", "plan"]
    source = Path(sys.modules[request_estimate.__module__].__file__ or "").read_text(
        encoding="utf-8"
    )
    assert '"verify"' not in source and '"estimate"' not in source


# ------------------------------------------------------------ stricter_decision (10.2)


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("allow", "allow", "allow"),
        ("allow", "ask", "ask"),
        ("allow", "deny", "deny"),
        ("ask", "allow", "ask"),
        ("ask", "ask", "ask"),
        ("ask", "deny", "deny"),
        ("deny", "allow", "deny"),
        ("deny", "ask", "deny"),
        ("deny", "deny", "deny"),
    ],
)
def test_stricter_decision_order(a: str, b: str, expected: str) -> None:
    assert stricter_decision(_decision(a, "first"), _decision(b, "second")).decision == expected


def test_stricter_decision_returns_one_of_the_inputs_and_prefers_first_on_tie() -> None:
    first, second = _decision("ask", "first"), _decision("ask", "second")
    assert stricter_decision(first, second) is first
    for a, b in itertools.product(["allow", "ask", "deny"], repeat=2):
        da, db = _decision(a, "a"), _decision(b, "b")
        assert stricter_decision(da, db) in (da, db)
