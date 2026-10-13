"""Forger: pinned provider, plan-node binding, stricter estimate, verification,
reproducibility and diagnostic of a single-provider run (cross-forge-foundation 4.1-4.3)."""

import secrets
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from helpers import SPARK_ENTRY, bad_entry, case_a, make_workspace, write_file
from theforge.contracts import ExecutionReceipt, Producer, Response, TaskSpec
from theforge.contracts.canonical import sha256_of, utc_now
from theforge.contracts.codes import Codes
from theforge.contracts.handoff import Handoff, HandoffItem, HandoffOrigin
from theforge.contracts.verification import VerificationResult
from theforge.forger import AskRequest, Forger, NodeBinding
from theforge.meta import PRODUCER
from theforge.planning.estimate import request_estimate
from theforge.protocol import ProviderTransport, SubprocessTransport
from theforge.registry import Registry
from theforge.runs import RunStore

# Random per run: a redaction fixture, not a credential.
REDACTION_PROBE = secrets.token_hex(12)


class _Spy:
    """Transport factory recording (provider id, op, payload) of every call it starts."""

    def __init__(self, fail_execute: str | None = None) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.fail_execute = fail_execute

    def __call__(self, argv: Sequence[str]) -> ProviderTransport:
        return _SpyTransport(self, argv)

    def ops(self, provider: str | None = None) -> list[str]:
        return [op for pid, op, _ in self.calls if provider is None or pid == provider]

    def payload(self, op: str) -> dict[str, Any]:
        return next(p for _, o, p in self.calls if o == op)


class _SpyTransport:
    def __init__(self, spy: _Spy, argv: Sequence[str]) -> None:
        self.spy, self.argv = spy, list(argv)
        self.inner = SubprocessTransport(argv)

    def call(
        self,
        op: str,
        payload: dict[str, Any],
        *,
        timeout: float,
        cwd: Path | None = None,
        check_protocol: bool = True,
    ) -> Response:
        self.spy.calls.append((self.argv[-1], op, payload))
        if op == "execute" and self.spy.fail_execute is not None:
            raise ValueError(self.spy.fail_execute)
        return self.inner.call(op, payload, timeout=timeout, cwd=cwd, check_protocol=check_protocol)


def _forger(root: Path, spy: _Spy | None = None) -> tuple[Forger, RunStore]:
    forge = root / ".forge"
    store = RunStore(forge)
    kwargs: dict[str, Any] = {"transport_factory": spy} if spy is not None else {}
    return Forger(root, Registry(forge), store, **kwargs), store


def _handoff(claim: str = "job reads s3://b/orders") -> Handoff:
    origin = HandoffOrigin(
        plan_run="plan-1",
        node="n1",
        run_id="run-n1",
        provider=Producer(id="fixture-api", version="0.0.1"),
    )
    return Handoff(
        producer=PRODUCER,
        created_at=utc_now(),
        plan_run="plan-1",
        target_node="n2",
        limitations=["handoff-input-missing: n0"],
        items=[
            HandoffItem(
                kind="evidence",
                id="e1",
                origin=origin,
                epistemic="observed",
                subject="job",
                claim=claim,
            )
        ],
    )


def _node(**kw: Any) -> NodeBinding:
    return NodeBinding(plan_run="plan-1", node="n2", pattern="pipeline", **kw)


# --- 4.1 pinned provider ---------------------------------------------------------------------


def test_pinned_unhealthy_provider_never_falls_back(tmp_path: Path) -> None:
    make_workspace(
        tmp_path,
        [bad_entry("unhealthy", "bad-a", trust="trusted"), bad_entry("ok", "bad-b", trust="local")],
    )
    spy = _Spy()
    forger, _ = _forger(tmp_path, spy)
    out = forger.ask(AskRequest(intent="run it", capability="bad.thing", provider="bad-a"))
    assert out.status == "provider_failure"
    assert out.error is not None and out.error.code == Codes.HEALTH_UNAVAILABLE
    assert "health" not in spy.ops("bad-b") and "execute" not in spy.ops()
    assert "pinned provider bad-a: fallback not attempted" in out.receipt.limitations
    assert out.receipt.reproducibility is not None
    assert out.receipt.reproducibility.level == "unknown"


def test_pinned_provider_replaces_the_routing_selection(tmp_path: Path) -> None:
    make_workspace(
        tmp_path,
        [bad_entry("ok", "bad-a", trust="trusted"), bad_entry("ok", "bad-b", trust="local")],
    )
    forger, store = _forger(tmp_path)
    out = forger.ask(AskRequest(intent="run it", capability="bad.thing", provider="bad-b"))
    assert out.status == "ok"
    assert out.decision.selected[0].provider == "bad-b"
    assert "pinned provider bad-b" in out.decision.reason
    assert store.read(out.run_id, "routing")["selected"][0]["provider"] == "bad-b"
    assert out.receipt.provider is not None and out.receipt.provider.id == "bad-b"


def test_unroutable_pinned_provider_is_no_route(tmp_path: Path) -> None:
    make_workspace(tmp_path, [bad_entry("ok", "bad-a")])
    spy = _Spy()
    forger, _ = _forger(tmp_path, spy)
    out = forger.ask(AskRequest(intent="run it", capability="bad.thing", provider="ghost"))
    assert out.status == "no_route"
    assert out.decision.reason == "pinned provider ghost is not routable for bad.thing"
    assert spy.ops() == []  # nothing was spawned, not even health


# --- 4.1 plan node binding and replay link ---------------------------------------------------


def test_node_handoff_is_persisted_delivered_and_hashed(tmp_path: Path) -> None:
    make_workspace(tmp_path, [SPARK_ENTRY])
    case_a(tmp_path)
    spy = _Spy()
    forger, store = _forger(tmp_path, spy)
    out = forger.ask(
        AskRequest(
            intent="analise o job",
            capability="spark.performance",
            node=_node(handoff=_handoff(f"key token={REDACTION_PROBE}")),
        )
    )
    assert out.status == "ok" and out.result is not None
    persisted = store.read(out.run_id, "handoff")
    assert REDACTION_PROBE not in str(persisted)
    assert spy.payload("execute")["handoff"] == persisted  # delivered == persisted (4.6)
    assert out.receipt.inputs.handoff_sha256 == sha256_of(persisted)
    assert (out.receipt.parent_run, out.receipt.plan_node) == ("plan-1", "n2")
    task = store.read_contract(out.run_id, "task", TaskSpec)
    assert task.constraints["plan"] == {"run": "plan-1", "node": "n2"}
    assert store.read(out.run_id, "routing")["pattern"] == "pipeline"
    assert "received 1 handoff items" in [e.claim for e in out.result.evidence]
    # fixture-spark does not declare accepts_handoff (4.7); handoff notes reach the receipt
    assert "handoff-use-undeclared: fixture-spark/spark.performance" in out.receipt.limitations
    assert "handoff-input-missing: n0" in out.receipt.limitations


def test_declared_handoff_consumer_has_no_undeclared_limitation(tmp_path: Path) -> None:
    make_workspace(tmp_path, [bad_entry("handoff-accept", "bad-h")])
    forger, _ = _forger(tmp_path)
    out = forger.ask(
        AskRequest(intent="run it", capability="bad.thing", node=_node(handoff=_handoff()))
    )
    assert out.status == "ok" and out.result is not None
    assert "handoff-items=1" in out.result.limitations
    assert not [n for n in out.receipt.limitations if n.startswith("handoff-use-undeclared")]


def test_replay_link_is_recorded_in_the_receipt(tmp_path: Path) -> None:
    make_workspace(tmp_path, [])
    write_file(tmp_path, "notes.txt", "hello\n")
    forger, store = _forger(tmp_path)
    out = forger.ask(AskRequest(intent="eco", capability="demo.echo", replay_of="run-orig"))
    assert out.status == "ok" and out.receipt.replay_of == "run-orig"
    assert store.read(out.run_id, "receipt")["replay_of"] == "run-orig"


def test_plain_ask_has_no_binding_fields(tmp_path: Path) -> None:
    make_workspace(tmp_path, [SPARK_ENTRY])
    case_a(tmp_path)
    spy = _Spy()
    forger, store = _forger(tmp_path, spy)
    out = forger.ask(AskRequest(intent="analise esse Glue Job porque está lento"))
    assert out.status == "ok"
    receipt = out.receipt
    assert (receipt.parent_run, receipt.plan_node, receipt.replay_of) == (None, None, None)
    assert receipt.inputs.handoff_sha256 is None
    assert store.read_optional(out.run_id, "handoff") is None
    assert spy.payload("execute")["handoff"] is None
    assert store.read(out.run_id, "routing")["pattern"] == "route"
    assert store.read(out.run_id, "task")["constraints"] == {}


# --- 4.2 stricter estimate -------------------------------------------------------------------


def _estimate_class(tmp_path: Path, pid: str) -> str | None:
    record = next(r for r in Registry(tmp_path / ".forge").records() if r.entry.id == pid)
    task = TaskSpec(
        producer=PRODUCER,
        created_at=utc_now(),
        id="est",
        intent="run it",
        workspace_root=str(tmp_path),
    )
    estimate, limitation = request_estimate(record, task, "bad.thing", "run")
    assert limitation is None and estimate is not None
    return estimate.operation_class


def test_stricter_estimate_requires_approval_for_a_read_only_capability(tmp_path: Path) -> None:
    make_workspace(tmp_path, [bad_entry("plan-estimate-stricter", "bad-s", trust="local")])
    estimated = _estimate_class(tmp_path, "bad-s")
    assert estimated == "local_mutation"
    spy = _Spy()
    forger, store = _forger(tmp_path, spy)
    node = _node(estimate_class=estimated)
    out = forger.ask(AskRequest(intent="run it", capability="bad.thing", node=node))
    assert out.status == "refused"
    assert out.error is not None and out.error.code == Codes.POLICY_APPROVAL_REQUIRED
    assert "execute" not in spy.ops()
    note = "operation-class: estimate local_mutation stricter than declared read_only"
    risk = store.read(out.run_id, "risk")
    assert risk["operation_class"] == "local_mutation" and note in risk["limitations"]
    assert risk["policy"]["decision"] == "ask"
    assert note in out.receipt.limitations
    assert out.receipt.reproducibility is not None
    assert out.receipt.reproducibility.level == "unknown"  # refused before execute
    approved = forger.ask(
        AskRequest(
            intent="run it", capability="bad.thing", node=node, approvals=frozenset({"bad.thing"})
        )
    )
    assert approved.status == "ok"


def test_without_estimate_the_policy_decision_is_unchanged(tmp_path: Path) -> None:
    make_workspace(tmp_path, [bad_entry("plan-estimate-stricter", "bad-s", trust="local")])
    forger, store = _forger(tmp_path)
    for node in (None, _node(), _node(estimate_class="read_only")):
        out = forger.ask(AskRequest(intent="run it", capability="bad.thing", node=node))
        assert out.status == "ok"
        risk = store.read(out.run_id, "risk")
        assert risk["operation_class"] == "read_only" and risk["policy"]["decision"] == "allow"
        assert not [n for n in out.receipt.limitations if n.startswith("operation-class:")]


# --- 4.3 verification, reproducibility, diagnostic ---------------------------------------------


def test_ok_run_links_its_verification_to_the_receipt(tmp_path: Path) -> None:
    make_workspace(tmp_path, [SPARK_ENTRY])
    case_a(tmp_path)
    forger, store = _forger(tmp_path)
    out = forger.ask(AskRequest(intent="analise esse Glue Job porque está lento"))
    assert out.status == "ok" and out.verification is not None
    persisted = store.read_contract(out.run_id, "verification", VerificationResult)
    assert persisted == out.verification
    assert out.receipt.verification_sha256 == sha256_of(store.read(out.run_id, "verification"))
    assert persisted.self_report.status == "reported"
    assert persisted.self_report.details == ["provider status: ok"]
    assert persisted.forge.status == "passed"
    assert persisted.independent.status == "not_performed"


def test_tampered_artifact_makes_the_run_partial(tmp_path: Path) -> None:
    make_workspace(tmp_path, [bad_entry("artifact-tamper", "bad-t")])
    forger, store = _forger(tmp_path)
    out = forger.ask(AskRequest(intent="run it", capability="bad.thing"))
    note = f"{Codes.RESULT_ARTIFACT_HASH}: out/report.txt"
    assert out.status == "partial" and out.result is not None
    assert out.result.status == "partial" and note in out.result.limitations
    assert note in out.receipt.limitations
    assert out.verification is not None and out.verification.forge.status == "failed"
    assert out.verification.self_report.details == ["provider status: ok"]
    assert store.read(out.run_id, "result")["status"] == "partial"
    assert out.receipt.reproducibility is not None
    assert out.receipt.reproducibility.level == "partially_reproducible"


def test_echo_run_is_reproducible(tmp_path: Path) -> None:
    make_workspace(tmp_path, [])
    write_file(tmp_path, "notes.txt", "hello\n")
    forger, store = _forger(tmp_path)
    out = forger.ask(AskRequest(intent="eco", capability="demo.echo", profile="balanced"))
    assert out.status == "ok"
    info = out.receipt.reproducibility
    assert info is not None and info.level == "reproducible", info
    receipt = store.read_contract(out.run_id, "receipt", ExecutionReceipt)
    assert receipt.reproducibility == info


def test_fixture_without_determinism_is_partially_reproducible(tmp_path: Path) -> None:
    make_workspace(tmp_path, [SPARK_ENTRY])
    case_a(tmp_path)
    forger, _ = _forger(tmp_path)
    out = forger.ask(AskRequest(intent="analise esse Glue Job porque está lento"))
    info = out.receipt.reproducibility
    assert info is not None and info.level == "partially_reproducible"
    assert "provider does not declare deterministic execution" in info.reasons


def test_internal_error_diagnostic_is_persisted_only_with_debug(tmp_path: Path) -> None:
    make_workspace(tmp_path, [bad_entry("ok", "bad-a")])
    for debug in (False, True):
        forger, store = _forger(tmp_path, _Spy(fail_execute=f"boom token={REDACTION_PROBE}"))
        out = forger.ask(AskRequest(intent="run it", capability="bad.thing", debug=debug))
        assert out.status == "provider_failure"
        assert out.error is not None and out.error.code == Codes.INTERNAL
        diagnostic = out.diagnostic
        assert diagnostic is not None and diagnostic.code == Codes.INTERNAL
        assert diagnostic.stage == "execute" and diagnostic.error_type == "ValueError"
        assert REDACTION_PROBE not in diagnostic.message
        persisted = store.read_optional(out.run_id, "diagnostic")
        if debug:
            assert persisted is not None and REDACTION_PROBE not in str(persisted)
            assert persisted["frames"] and all(
                f["module"].startswith("theforge") for f in persisted["frames"]
            )
        else:
            assert persisted is None
        assert store.read_optional(out.run_id, "receipt") is not None
        assert store.read_optional(out.run_id, "telemetry") is not None
