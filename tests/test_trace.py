"""Local trace spans: the run's what-happened record (Cycle 3 Wave J).

``RunTelemetry.spans`` is the local trace — phases and explicit spans recorded
with start order, durations, parent links and an error marker. ``theforge
trace`` renders the tree; ``explain`` keeps answering *why*.
"""

import json
from collections.abc import Iterator
from pathlib import Path
from threading import Thread

import pytest

from helpers import SPARK_ENTRY, make_workspace, write_file
from theforge.cli.main import main
from theforge.contracts.base import ContractError, from_dict, to_dict
from theforge.contracts.telemetry import (
    MAX_SPANS,
    SPAN_ATTRS_MAX,
    NativeTrace,
    RunTelemetry,
    Span,
)
from theforge.contracts.types import Producer
from theforge.forger.orchestrator import AskRequest, Forger
from theforge.forger.plan_executor import PlanCommand, PlanExecutor
from theforge.forger.telemetry import TelemetryRecorder
from theforge.profiles import profile_for
from theforge.registry import Registry
from theforge.runs import RunStore

P = Producer(id="theforge", version="0")


class FakeClock:
    """Each call returns the next tick; a span costs exactly two calls."""

    def __init__(self, *ticks: float) -> None:
        self._ticks: Iterator[float] = iter(ticks)

    def __call__(self) -> float:
        return next(self._ticks)


def _recorder(*ticks: float) -> TelemetryRecorder:
    return TelemetryRecorder("run-1", profile_for("balanced"),
                             clock=FakeClock(*ticks), now=lambda: "t")


def _span(**kw: object) -> Span:
    base: dict[str, object] = {"id": "s1", "name": "routing",
                               "start_ms": 0.0, "duration_ms": 1.0}
    base.update(kw)
    return Span(**base)  # type: ignore[arg-type]


def _telemetry(spans: list[Span]) -> RunTelemetry:
    from theforge.contracts.telemetry import ProfileSnapshot
    p = profile_for("balanced")
    return RunTelemetry(
        producer=P, created_at="t", run_id="r", profile=ProfileSnapshot(
            name=p.name, budget_bytes=p.budget_bytes, max_files=p.max_files,
            tiers=list(p.tiers), effective_tiers=[],
            negotiation_rounds=p.negotiation_rounds, max_providers=p.max_providers,
            fallback=p.fallback, verification=p.verification,
            execute_timeout_s=p.execute_timeout_s),
        spans=spans)


# --- Span contract -----------------------------------------------------------


def test_span_rejects_bad_name() -> None:
    with pytest.raises(ContractError):
        _span(name="")
    with pytest.raises(ContractError):
        _span(name="x" * 81)


def test_span_rejects_negative_times() -> None:
    with pytest.raises(ContractError):
        _span(start_ms=-1.0)
    with pytest.raises(ContractError):
        _span(duration_ms=-0.5)


def test_span_attributes_bounded() -> None:
    with pytest.raises(ContractError):
        _span(attributes={f"k{i}": "v" for i in range(SPAN_ATTRS_MAX + 1)})
    with pytest.raises(ContractError):
        _span(attributes={"k": "v" * 121})


def test_telemetry_rejects_duplicate_span_ids() -> None:
    with pytest.raises(ContractError):
        _telemetry([_span(id="s1"), _span(id="s1")])


def test_telemetry_rejects_forward_or_unknown_parent() -> None:
    with pytest.raises(ContractError):
        _telemetry([_span(id="s1", parent="s2"), _span(id="s2")])
    with pytest.raises(ContractError):
        _telemetry([_span(id="s1", parent="ghost")])


def test_telemetry_caps_spans() -> None:
    spans = [_span(id=f"s{i}") for i in range(1, MAX_SPANS + 2)]
    with pytest.raises(ContractError):
        _telemetry(spans)


def test_telemetry_without_spans_still_parses() -> None:
    """Pre-Wave-J telemetry artifacts have no ``spans`` — additive field."""
    data = to_dict(_telemetry([]))
    del data["spans"]
    assert from_dict(RunTelemetry, data, strict=True).spans == []




# --- provider trace federation -------------------------------------------------


def test_native_trace_is_an_opaque_bounded_provider_reference() -> None:
    trace = NativeTrace(
        ref="agentops:run-123",
        summary="critical path: inspect -> reason -> verify",
        critical_path=["inspect", "reason", "verify"],
    )
    assert trace.ref == "agentops:run-123"
    assert trace.critical_path[-1] == "verify"


@pytest.mark.parametrize(
    "ref",
    [
        "file:///etc/passwd",
        "https://evil.example/trace",
        "data:text/plain,prompt",
        "javascript:alert(1)",
        "C:\\\\temp\\\\trace.json",
        "agentops:../secret",
        "forge:run/1",
        "theforge:run/1",
    ],
)
def test_native_trace_ref_never_becomes_a_dereferenceable_path_or_url(ref: str) -> None:
    with pytest.raises(ContractError):
        NativeTrace(ref=ref)


def test_native_trace_summary_and_critical_path_are_bounded() -> None:
    with pytest.raises(ContractError):
        NativeTrace(ref="agentops:r", summary="x" * 241)
    with pytest.raises(ContractError):
        NativeTrace(ref="agentops:r", critical_path=["x"] * 33)
    with pytest.raises(ContractError):
        NativeTrace(ref="agentops:r", critical_path=["x" * 121])


# --- recorder ----------------------------------------------------------------


def test_span_records_start_order_and_attrs() -> None:
    # t0=0.0 (first span's start), span s1: 0.0→0.5, span s2: 0.6→0.9
    rec = _recorder(0.0, 0.5, 0.6, 0.9)
    with rec.span("routing") as first:
        first.attrs["outcome"] = "routed"
    with rec.span("verification", parent="s1"):
        pass
    spans = rec.build().spans
    assert [s.id for s in spans] == ["s1", "s2"]
    assert spans[0].name == "routing" and spans[0].start_ms == 0.0
    assert spans[0].duration_ms == 500.0
    assert spans[0].attributes == {"outcome": "routed"}
    assert spans[1].parent == "s1" and spans[1].duration_ms == 300.0


def test_span_marks_error_when_the_block_raises() -> None:
    rec = _recorder(0.0, 0.1)
    with pytest.raises(RuntimeError), rec.span("provider:x"):
        raise RuntimeError("boom")
    (span,) = rec.build().spans
    assert span.status == "error" and span.duration_ms == 100.0


def test_phase_also_records_a_span() -> None:
    rec = _recorder(0.0, 0.250)
    with rec.phase("scan"):
        pass
    tel = rec.build()
    assert tel.scan_ms.value == 250.0  # the metric still accumulates
    (span,) = tel.spans
    assert span.name == "scan" and span.duration_ms == 250.0


def test_phase_span_name_overrides_the_display() -> None:
    rec = _recorder(0.0, 0.1)
    with rec.phase("provider", span_name="provider:p1", capability="c",
                   action="a", round="0"):
        pass
    (span,) = rec.build().spans
    assert span.name == "provider:p1"
    assert span.attributes == {"capability": "c", "action": "a", "round": "0"}


def test_spans_from_concurrent_workers_get_unique_ids() -> None:
    rec = _recorder(*[i / 1000.0 for i in range(64)])

    def work() -> None:
        with rec.span("node:x"):
            pass

    threads = [Thread(target=work) for _ in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    spans = rec.build().spans
    assert len({s.id for s in spans}) == 16
    assert [int(s.id[1:]) for s in spans] == list(range(1, 17))


def test_invalid_span_name_fails_fast() -> None:
    rec = _recorder()
    with pytest.raises(ValueError), rec.span("x" * 81):
        pass


# --- theforge trace (J3) -------------------------------------------------------


def _run_cli(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    code = main(list(argv))
    out, err = capsys.readouterr()
    return code, out, err


def test_ask_run_trace_shows_the_stages(tmp_path: Path) -> None:
    make_workspace(tmp_path, [SPARK_ENTRY])
    write_file(tmp_path, "jobs_glue.py", "x = 1")
    forge = tmp_path / ".forge"
    out = Forger(tmp_path, Registry(forge), RunStore(forge)).ask(
        AskRequest(intent="analise esse glue job lento", profile="balanced"))
    assert out.status == "ok"
    telemetry = RunStore(forge).read_contract(out.run_id, "telemetry", RunTelemetry)
    names = [s.name for s in telemetry.spans]
    assert names[0] == "scan" and names[-1] == "synthesis"
    assert any(n.startswith("provider:fixture-spark") for n in names)
    assert "verification" in names and "planning" in names


def test_trace_command_renders_the_tree(tmp_path: Path,
                                        capsys: pytest.CaptureFixture[str]) -> None:
    make_workspace(tmp_path, [SPARK_ENTRY])
    write_file(tmp_path, "jobs_glue.py", "x = 1")
    forge = tmp_path / ".forge"
    out = Forger(tmp_path, Registry(forge), RunStore(forge)).ask(
        AskRequest(intent="glue job", profile="balanced"))
    code, text, _ = _run_cli(capsys, "trace", out.run_id, "--root", str(tmp_path))
    assert code == 0
    assert f"trace {out.run_id}" in text and "ok" in text
    assert "provider:fixture-spark" in text and "capability=spark.performance" in text
    code, text, _ = _run_cli(capsys, "trace", out.run_id, "--root", str(tmp_path),
                           "--json")
    assert code == 0
    spans = json.loads(text)["spans"]
    assert spans and all(s["id"].startswith("s") for s in spans)


def test_plan_run_traces_each_node(tmp_path: Path,
                                   capsys: pytest.CaptureFixture[str]) -> None:
    forge = make_workspace(tmp_path, [SPARK_ENTRY])
    store = RunStore(forge)
    executor = PlanExecutor(Forger(tmp_path, Registry(forge), store))
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps({
        "task_id": "from-file", "pattern": "pipeline", "source": "file",
        "profile": "balanced",
        "nodes": [{"id": "n1", "role": "standalone", "provider": "fixture-spark",
                   "capability": "spark.performance", "action": "diagnose"}],
    }), encoding="utf-8")
    out = executor.run(PlanCommand(intent="spec", profile="balanced",
                                   plan_file=plan_file, execute=True))
    assert out.result is not None
    telemetry = store.read_contract(out.run_id, "telemetry", RunTelemetry)
    node = next(s for s in telemetry.spans if s.name == "node:n1")
    assert node.attributes["provider"] == "fixture-spark"
    assert node.attributes["outcome"] == "ok"
    handoff = next(s for s in telemetry.spans if s.name == "handoff")
    assert handoff.parent == node.id  # the handoff belongs to its node
    code, text, _ = _run_cli(capsys, "trace", out.run_id, "--root", str(tmp_path))
    assert code == 0 and "node:n1" in text and "└─" in text or "├─" in text


def test_trace_unknown_run_is_usage_error(capsys: pytest.CaptureFixture[str],
                                          tmp_path: Path) -> None:
    make_workspace(tmp_path, [SPARK_ENTRY])
    code, _, _ = _run_cli(capsys, "trace", "20200101T000000Z-deadbeef",
                          "--root", str(tmp_path))
    assert code == 2
