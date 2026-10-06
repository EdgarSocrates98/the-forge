"""Economy engine: RunBudget, bounded promotion, context ROI and provider history.

Wave H: every run that resolves a profile persists a ``budget`` artifact bound
into the receipt; explicitly requested profiles promote their elastic bounds one
step when measured complexity outranks them; routing consults the metrics store
as a secondary tie-break only — never ahead of trust, policy or capability.
"""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from helpers import CITE_ENTRY, SPARK_ENTRY, make_workspace, write_file
from test_router import API, SPARK, cap, record, task
from theforge.contracts import (
    ComplexityAssessment,
    ContractError,
    Producer,
    ProviderCapabilityPerformance,
    ProviderPerformance,
    RunBudget,
    from_dict,
    to_dict,
)
from theforge.contracts.canonical import sha256_of
from theforge.economy import resolve_budget
from theforge.forger.orchestrator import AskRequest, Forger
from theforge.forger.plan_executor import PlanCommand, PlanExecutor
from theforge.metrics import load_performance, record_performance
from theforge.profiles import PROFILES, profile_for
from theforge.registry import Registry
from theforge.routing import route
from theforge.runs import RunStore

P = Producer(id="theforge", version="0")


def _assessment(level: str, selected: str = "balanced",
                confidence: float = 0.9) -> ComplexityAssessment:
    return ComplexityAssessment(
        producer=P, created_at="t", task_id="t1", level=level, score=0.5,  # type: ignore[arg-type]
        confidence=confidence, requested_profile="economy",
        selected_profile=selected,  # type: ignore[arg-type]
        profile_reason="test", limitations=[])


def _entry(pid: str, cid: str, *, runs: int = 4, ok: int = 3, partial: int = 1,
           failed: int = 0, verified: int = 2, ms: float = 100.0
           ) -> ProviderCapabilityPerformance:
    return ProviderCapabilityPerformance(
        provider=pid, capability=cid, runs=runs, ok=ok, partial=partial,
        failed=failed, verified_runs=verified, evidence=8, artifacts=1,
        context_bytes=4096, files_sent=4, files_cited=2, duration_ms=ms * runs,
        updated_at="t")


def _perf(*entries: ProviderCapabilityPerformance) -> ProviderPerformance:
    return ProviderPerformance(producer=P, created_at="t", entries=list(entries))


# --- RunBudget -------------------------------------------------------------------


def test_budget_records_profile_bounds_verbatim() -> None:
    effective, budget = resolve_budget(profile_for("balanced"), run_id="run-1")
    assert effective is profile_for("balanced")
    assert budget.schema == "theforge/RunBudget/v1"
    assert budget.profile == "balanced"
    assert budget.context_bytes == PROFILES["balanced"].budget_bytes
    assert budget.provider_calls == PROFILES["balanced"].max_providers
    assert budget.adjustments == []


def test_budget_promotes_explicit_profile_one_step() -> None:
    effective, budget = resolve_budget(
        profile_for("economy"), run_id="run-1",
        assessment=_assessment("medium", selected="balanced"))
    assert effective.budget_bytes == PROFILES["balanced"].budget_bytes
    assert effective.max_files == PROFILES["balanced"].max_files
    assert effective.name == "economy"  # the requested name is kept; bounds promoted
    assert budget.profile == "economy"
    assert budget.context_bytes == PROFILES["balanced"].budget_bytes
    assert len(budget.adjustments) == 1 and "economy→balanced" in budget.adjustments[0]


def test_budget_promotion_is_bounded_to_one_step() -> None:
    # Even a ``critical`` assessment can only raise economy to balanced in one step.
    effective, budget = resolve_budget(
        profile_for("economy"), run_id="run-1",
        assessment=_assessment("critical", selected="max"))
    assert effective.budget_bytes == PROFILES["balanced"].budget_bytes
    assert effective.budget_bytes < PROFILES["max"].budget_bytes
    assert "economy→balanced" in budget.adjustments[0]


def test_budget_never_promotes_past_or_within_max() -> None:
    effective, budget = resolve_budget(
        profile_for("max"), run_id="run-1",
        assessment=_assessment("critical", selected="max"))
    assert effective is profile_for("max") and budget.adjustments == []


def test_budget_never_promotes_when_assessment_selects_equal_or_lower() -> None:
    for selected in ("economy", "balanced"):
        effective, budget = resolve_budget(
            profile_for("balanced"), run_id="run-1",
            assessment=_assessment("medium", selected=selected))
        assert effective is profile_for("balanced") and budget.adjustments == []


def test_budget_promotion_never_widens_blast_radius() -> None:
    # Only elastic fields (context bytes, files, negotiation) promote — provider
    # count, wall time and parallelism stay at the requested profile's bounds.
    effective, _ = resolve_budget(
        profile_for("economy"), run_id="run-1",
        assessment=_assessment("critical", selected="max"))
    assert effective.max_providers == PROFILES["economy"].max_providers
    assert effective.execute_timeout_s == PROFILES["economy"].execute_timeout_s
    assert effective.verification == PROFILES["economy"].verification


def test_budget_plan_run_shape() -> None:
    _, budget = resolve_budget(profile_for("balanced"), run_id="plan-1",
                               plan_nodes=3)
    assert budget.provider_calls == 3 and budget.verification_calls == 3
    assert budget.max_parallelism == 4
    assert budget.semantic_calls == 1  # a non-economy plan may ask the planner once
    _, economy_budget = resolve_budget(profile_for("economy"), run_id="plan-2",
                                       plan_nodes=2)
    assert economy_budget.semantic_calls == 0


def test_budget_rejects_negative_bounds() -> None:
    with pytest.raises(ContractError):
        RunBudget(producer=P, created_at="t", run_id="r", profile="economy",
                  context_bytes=-1, max_files=1, provider_calls=1, semantic_calls=0,
                  verification_calls=0, wall_time_s=1.0, max_parallelism=1,
                  negotiation_rounds=0)


def test_budget_roundtrips_strict() -> None:
    _, budget = resolve_budget(profile_for("max"), run_id="run-1",
                               assessment=_assessment("high", selected="max"))
    assert from_dict(RunBudget, json.loads(json.dumps(to_dict(budget))),
                     strict=True) == budget


# --- metrics store -----------------------------------------------------------------


def test_metrics_absent_file_is_no_history(tmp_path: Path) -> None:
    perf, warning = load_performance(tmp_path)
    assert perf is None and warning is None


def test_metrics_record_and_merge(tmp_path: Path) -> None:
    assert record_performance(tmp_path, "p1", "x.y", status="ok", verified=True,
                              evidence=2, artifacts=1, context_bytes=100,
                              files_sent=2, files_cited=1, duration_ms=50.0) is None
    assert record_performance(tmp_path, "p1", "x.y", status="provider_failure",
                              verified=False, evidence=0, artifacts=0,
                              context_bytes=100, files_sent=2, files_cited=0,
                              duration_ms=10.0) is None
    perf, warning = load_performance(tmp_path)
    assert warning is None and perf is not None
    (entry,) = perf.entries
    assert entry.runs == 2 and entry.ok == 1 and entry.failed == 1
    assert entry.verified_runs == 1 and entry.evidence == 2
    assert entry.files_sent == 4 and entry.files_cited == 1
    assert entry.duration_ms == 60.0


def test_metrics_malformed_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / ".forge" / "metrics" / "provider-performance.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    perf, warning = load_performance(tmp_path)
    assert perf is None and warning is not None and "metrics:" in warning


def test_metrics_poisoned_counters_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / ".forge" / "metrics" / "provider-performance.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({
        "schema": "theforge/ProviderPerformance/v1",
        "producer": {"id": "x", "version": "1"}, "created_at": "t",
        "entries": [{"provider": "p", "capability": "c", "runs": 1, "ok": -5,
                     "partial": 0, "failed": 0, "verified_runs": 0, "evidence": 0,
                     "artifacts": 0, "context_bytes": 0, "files_sent": 0,
                     "files_cited": 0, "duration_ms": 0.0, "updated_at": "t"}],
    }), encoding="utf-8")
    perf, warning = load_performance(tmp_path)
    assert perf is None and warning is not None


def test_score_orders_verified_then_delivered_then_latency() -> None:
    perf = _perf(_entry("a", "x.y", verified=3),
                 _entry("b", "x.y", verified=1),
                 _entry("c", "x.y", ok=0, partial=0, failed=4, verified=0))
    assert perf.score("a", "x.y") > perf.score("b", "x.y")
    assert perf.score("b", "x.y") > perf.score("c", "x.y")
    assert perf.score("nobody", "x.y") == (0.0, 0.0, 0.0, 0)


# --- routing tie-break (H5) --------------------------------------------------------

# Two providers tied at rank 2 on *unshared* keyword+glob hits; aaa also matches a
# dependency shared by both, so it is dropped from the kept rank but keeps raw 3 —
# the rank-key tie is the only ambiguity left for measured history to decide.
_TIED_A = record("aaa-forge", [cap("a.thing", kw=("glue",), globs=("*glue*.py",),
                                 deps=("pyspark",))])
_TIED_B = record("bbb-forge", [cap("b.thing", kw=("spark",), globs=("*_job.py",),
                                 deps=("pyspark",))])
_TIED_FILES = ["x_glue.py", "y_job.py"]
_TIED_DEPS = {"pyspark"}


def test_signal_tie_broken_by_measured_history() -> None:
    """A pure signal tie resolves to the strictly better measured history (H5)."""
    perf = _perf(_entry("aaa-forge", "a.thing", verified=4, ok=4, partial=0),
                 _entry("bbb-forge", "b.thing", verified=0, ok=0,
                        partial=1, failed=3))
    d = route(task("glue spark"), [_TIED_A, _TIED_B], _TIED_FILES, _TIED_DEPS,
              performance=perf)
    assert d.status == "routed" and d.selected[0].provider == "aaa-forge"
    assert any(n.startswith("performance-tie-break:") for n in d.limitations)


def test_signal_tie_without_history_stays_ambiguous() -> None:
    d = route(task("glue spark"), [_TIED_A, _TIED_B], _TIED_FILES, _TIED_DEPS,
              performance=_perf())
    assert d.status == "ambiguous" and d.selected == []
    d_none = route(task("glue spark"), [_TIED_A, _TIED_B], _TIED_FILES, _TIED_DEPS)
    assert d_none.status == "ambiguous"  # identical: no history, no opinion


def test_signal_tie_with_equal_history_stays_ambiguous() -> None:
    perf = _perf(_entry("aaa-forge", "a.thing"),
                 _entry("bbb-forge", "b.thing"))
    d = route(task("glue spark"), [_TIED_A, _TIED_B], _TIED_FILES, _TIED_DEPS,
              performance=perf)
    assert d.status == "ambiguous"


def test_history_decides_the_tied_pair_regardless_of_raw() -> None:
    """Raw presence equal among the tied pair is the same ambiguity — history
    resolves it, so the better history wins even when the other side matched
    as many signal groups."""
    perf = _perf(_entry("bbb-forge", "b.thing", verified=4, ok=4, partial=0),
                 _entry("aaa-forge", "a.thing", verified=0, ok=0,
                        partial=1, failed=3))
    d = route(task("glue spark"), [_TIED_A, _TIED_B], _TIED_FILES, _TIED_DEPS,
              performance=perf)
    assert d.status == "routed" and d.selected[0].provider == "bbb-forge"


def test_history_tie_among_winners_stays_ambiguous() -> None:
    """Two candidates sharing the best measured history: no unique winner."""
    same = dict(runs=4, ok=4, partial=0, failed=0, verified=4, ms=100.0)
    perf = _perf(_entry("aaa-forge", "a.thing", **same),
                 _entry("bbb-forge", "b.thing", **same))
    d = route(task("glue spark"), [_TIED_A, _TIED_B], _TIED_FILES, _TIED_DEPS,
              performance=perf)
    assert d.status == "ambiguous"


def test_history_never_rescues_below_min_signals() -> None:
    """A rank-1 tie is still too thin: history cannot waive MIN_SIGNAL_TYPES."""
    perf = _perf(_entry("api-forge", "api.contract", verified=4, ok=4, partial=0),
                 _entry("spark-forge", "spark.performance", verified=0, ok=0,
                        partial=1, failed=3))
    d = route(task("performance da api"), [SPARK, API], [], set(),
              performance=perf)
    assert d.status == "ambiguous"  # resolved tie, then blocked on signal floor


def test_history_never_overrides_trust() -> None:
    """H5: a lower-trust provider with a perfect history still loses (secondary only)."""
    caps = SPARK.manifest.capabilities if SPARK.manifest else []
    trusted = record("zzz-trusted", caps, trust="trusted")
    perf = _perf(_entry("spark-forge", "spark.performance", verified=4, ok=4,
                        partial=0))
    d = route(task("x", requested_capability="spark.performance"),
              [SPARK, trusted], [], set(), performance=perf)
    assert d.selected[0].provider == "zzz-trusted"  # trust dominates; history is a tie-break


def test_history_breaks_explicit_tie_within_same_trust() -> None:
    caps = SPARK.manifest.capabilities if SPARK.manifest else []
    other = record("zzz-forge", caps, trust="local")  # same trust as SPARK
    perf = _perf(_entry("zzz-forge", "spark.performance", verified=4, ok=4,
                        partial=0))
    d = route(task("x", requested_capability="spark.performance"),
              [SPARK, other], [], set(), performance=perf)
    assert d.selected[0].provider == "zzz-forge"  # history beats the bare id order
    plain = route(task("x", requested_capability="spark.performance"),
                  [SPARK, other], [], set())
    assert plain.selected[0].provider == "spark-forge"  # id order without history


# --- e2e -------------------------------------------------------------------------


def _forger(root: Path) -> Forger:
    forge = root / ".forge"
    return Forger(root, Registry(forge), RunStore(forge))


def test_ask_persists_budget_bound_in_receipt(tmp_path: Path) -> None:
    make_workspace(tmp_path, [SPARK_ENTRY])
    write_file(tmp_path, "jobs_glue.py", "x = 1")
    out = _forger(tmp_path).ask(
        AskRequest(intent="analise esse glue job lento", profile="balanced"))
    assert out.status == "ok"
    inputs = out.receipt.inputs
    assert inputs.budget_sha256 is not None
    run_dir = tmp_path / ".forge" / "runs" / out.run_id
    budget = json.loads((run_dir / "budget.json").read_text(encoding="utf-8"))
    assert budget["schema"] == "theforge/RunBudget/v1"
    assert budget["profile"] == "balanced" and budget["adjustments"] == []
    assert sha256_of(budget) == inputs.budget_sha256


def test_ask_records_provider_performance(tmp_path: Path) -> None:
    make_workspace(tmp_path, [SPARK_ENTRY])
    write_file(tmp_path, "jobs_glue.py", "x = 1")
    out = _forger(tmp_path).ask(
        AskRequest(intent="analise esse glue job lento", profile="balanced"))
    assert out.status == "ok"
    perf, warning = load_performance(tmp_path)
    assert warning is None and perf is not None
    (entry,) = perf.entries
    assert entry.provider == "fixture-spark"
    assert entry.capability == "spark.performance"
    assert entry.runs == 1 and entry.ok == 1
    assert entry.context_bytes > 0 and entry.files_sent >= 1


def test_ask_telemetry_counts_context_roi(tmp_path: Path) -> None:
    make_workspace(tmp_path, [CITE_ENTRY])
    write_file(tmp_path, "note.cite.py", "x = 1")
    out = _forger(tmp_path).ask(
        AskRequest(intent="cite me", capability="spark.performance",
                   provider="fixture-cite", profile="balanced"))
    assert out.status == "ok"
    run_dir = tmp_path / ".forge" / "runs" / out.run_id
    tel = json.loads((run_dir / "telemetry.json").read_text(encoding="utf-8"))
    assert tel["files_cited"]["value"] == 1.0  # the provider cited the sent file
    assert tel["evidence_returned"]["value"] >= 1.0
    assert tel["findings_returned"]["value"] == 1.0


def test_ask_failed_run_records_zero_roi(tmp_path: Path) -> None:
    make_workspace(tmp_path, [SPARK_ENTRY])
    out = _forger(tmp_path).ask(AskRequest(intent="nothing matches this",
                                           profile="balanced"))
    run_dir = tmp_path / ".forge" / "runs" / out.run_id
    tel = json.loads((run_dir / "telemetry.json").read_text(encoding="utf-8"))
    # no_route never reaches execution: the ROI counters are measured zeros.
    assert tel["files_cited"]["value"] == 0.0
    assert tel["evidence_returned"]["value"] == 0.0


def test_ask_promoted_budget_persists_assessment_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An economy request whose measured complexity selects balanced promotes once."""
    import theforge.forger.orchestrator as orchestrator

    make_workspace(tmp_path, [SPARK_ENTRY])
    write_file(tmp_path, "jobs_glue.py", "x = 1")
    high = _assessment("critical", selected="max")
    real = orchestrator.assess
    monkeypatch.setattr(orchestrator, "assess",
                        lambda inputs, config: replace(
                            real(inputs, config), level="critical",
                            selected_profile=high.selected_profile))
    out = _forger(tmp_path).ask(
        AskRequest(intent="analise esse glue job lento", profile="economy"))
    assert out.status == "ok"
    run_dir = tmp_path / ".forge" / "runs" / out.run_id
    budget = json.loads((run_dir / "budget.json").read_text(encoding="utf-8"))
    assert budget["profile"] == "economy"  # requested name kept
    assert budget["context_bytes"] == PROFILES["balanced"].budget_bytes
    assert any("economy→balanced" in n for n in budget["adjustments"])
    # the promotion's evidence — the assessment — is persisted and receipt-bound
    assert out.receipt.inputs.complexity_sha256 is not None
    assert any("promotion" in n for n in out.receipt.limitations)


def test_plan_run_persists_budget(tmp_path: Path) -> None:
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
    out = executor.run(PlanCommand(intent="budget spec", profile="balanced",
                                   plan_file=plan_file, execute=True))
    assert out.result is not None
    run_dir = tmp_path / ".forge" / "runs" / out.run_id
    budget = json.loads((run_dir / "budget.json").read_text(encoding="utf-8"))
    assert budget["profile"] == "balanced"
    assert budget["provider_calls"] == 1 and budget["max_parallelism"] == 4
    assert budget["adjustments"] == []  # plan runs record; nodes promote on their own
    receipt = json.loads((run_dir / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["inputs"]["budget_sha256"] == sha256_of(budget)
