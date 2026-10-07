"""ExecutionObservation store + GlobalEconomyReceipt (cycle 4, wave G)."""

import argparse
import json
from pathlib import Path

import pytest

from theforge.contracts import ContractError
from theforge.contracts.observation import (
    EXECUTION_OBSERVATION_SCHEMA,
    GLOBAL_AXES,
    EconomyAxis,
    ExecutionObservation,
    GlobalEconomyReceipt,
)
from theforge.contracts.performance import (
    ProviderCapabilityPerformance,
    ProviderPerformance,
)
from theforge.meta import PRODUCER
from theforge.observations import (
    MAX_OBSERVATIONS_BYTES,
    OBSERVATIONS_FILE,
    build_global_receipt,
    environment_fingerprint,
    load_observations,
    record_observation,
)


def obs(**kw: object) -> ExecutionObservation:
    base = dict(producer=PRODUCER, created_at="2026-01-01T00:00:00Z",
                run_id="r1", provider="echo-forge", capability="data.pipeline",
                status="ok")
    base.update(kw)
    return ExecutionObservation(**base)  # type: ignore[arg-type]


def perf_entry(provider: str, capability: str, runs: int,
               surface: str | None, updated: str
               ) -> ProviderCapabilityPerformance:
    return ProviderCapabilityPerformance(
        provider=provider, capability=capability, runs=runs,
        ok=runs, partial=0, failed=0, verified_runs=0, evidence=0,
        artifacts=0, context_bytes=0, files_sent=0, files_cited=0,
        duration_ms=0.0, surface=surface, updated_at=updated)


# ---------- contract ----------


class TestContract:
    def test_minimal_valid(self) -> None:
        assert obs().schema == EXECUTION_OBSERVATION_SCHEMA
        assert obs().task_family is None
        assert obs().verification == "not_performed"

    def test_required_fields(self) -> None:
        for field_name in ("run_id", "provider", "capability"):
            with pytest.raises(ContractError, match="must not be empty"):
                obs(**{field_name: ""})

    def test_negative_metric_rejected(self) -> None:
        with pytest.raises(ContractError, match="cannot be negative"):
            obs(tokens=-1)
        with pytest.raises(ContractError, match="cannot be negative"):
            obs(cost_usd=-0.01)

    def test_cited_cannot_exceed_items(self) -> None:
        with pytest.raises(ContractError, match="exceeds"):
            obs(context_items=2, context_items_cited=3)

    def test_wrong_schema_rejected(self) -> None:
        with pytest.raises(ContractError, match="unsupported schema"):
            obs(schema="theforge/ExecutionObservation/v0")  # type: ignore[call-arg]

    def test_axis_status_value_rules(self) -> None:
        EconomyAxis(status="observed", value=1.0)
        with pytest.raises(ContractError, match="requires a value"):
            EconomyAxis(status="observed")
        with pytest.raises(ContractError, match="cannot carry a value"):
            EconomyAxis(status="unresolved", value=1.0)
        with pytest.raises(ContractError, match="cannot carry a value"):
            EconomyAxis(status="conflict", value=2.0)

    def test_receipt_rejects_unknown_axis(self) -> None:
        with pytest.raises(ContractError, match="unknown axes"):
            GlobalEconomyReceipt(
                producer=PRODUCER, created_at="t", observations=1, runs=1,
                axes={"mystery": EconomyAxis(status="observed", value=1.0)})

    def test_receipt_runs_cannot_exceed_observations(self) -> None:
        with pytest.raises(ContractError, match="runs exceed"):
            GlobalEconomyReceipt(
                producer=PRODUCER, created_at="t", observations=1, runs=2)


# ---------- environment fingerprint ----------


class TestEnvironmentFingerprint:
    def test_stable_coarse_hex(self) -> None:
        fp = environment_fingerprint()
        assert isinstance(fp, str) and len(fp) == 16
        int(fp, 16)  # hex
        assert fp == environment_fingerprint()  # deterministic


# ---------- store ----------


class TestStore:
    def test_absent_file_is_empty(self, tmp_path: Path) -> None:
        observations, warning = load_observations(tmp_path)
        assert observations == [] and warning is None

    def test_roundtrip(self, tmp_path: Path) -> None:
        assert record_observation(tmp_path, obs(tokens=10)) is None
        assert record_observation(tmp_path, obs(run_id="r2")) is None
        observations, warning = load_observations(tmp_path)
        assert warning is None
        assert [o.run_id for o in observations] == ["r1", "r2"]
        assert observations[0].tokens == 10

    def test_corrupt_lines_skipped_not_fatal(self, tmp_path: Path) -> None:
        record_observation(tmp_path, obs())
        path = tmp_path / ".forge" / "metrics" / OBSERVATIONS_FILE
        with path.open("a", encoding="utf-8") as handle:
            handle.write("{not json\n")
            handle.write('{"schema": "theforge/ExecutionObservation/v0"}\n')
        observations, warning = load_observations(tmp_path)
        assert len(observations) == 1
        assert warning is not None and "skipped 2" in warning

    def test_compaction_keeps_newest(self, tmp_path: Path,
                                     monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "theforge.observations.MAX_OBSERVATIONS_BYTES", 4 * 1024)
        big = "x" * 400
        warnings = []
        for i in range(60):
            warnings.append(record_observation(
                tmp_path, obs(run_id=f"r{i:03}", limitations=[big])))
        observations, _ = load_observations(tmp_path)
        assert observations[-1].run_id == "r059"
        assert len(observations) < 60
        assert any("compacted" in (w or "") for w in warnings)
        size = (tmp_path / ".forge" / "metrics" / OBSERVATIONS_FILE).stat().st_size
        assert size <= MAX_OBSERVATIONS_BYTES + 1024

    def test_record_never_raises(self, tmp_path: Path) -> None:
        marker = tmp_path / ".forge" / "metrics"
        marker.mkdir(parents=True)
        marker.chmod(0o555)
        try:
            warning = record_observation(tmp_path, obs())
            assert warning is None or isinstance(warning, str)
        finally:
            marker.chmod(0o755)


# ---------- global receipt ----------


def receipt_for(observations: list[ExecutionObservation],
                performance: ProviderPerformance | None = None
                ) -> GlobalEconomyReceipt:
    return build_global_receipt(observations, performance)


class TestGlobalReceipt:
    def test_empty_is_not_applicable(self) -> None:
        receipt = receipt_for([])
        assert receipt.observations == 0 and receipt.runs == 0
        assert set(receipt.axes) == set(GLOBAL_AXES)
        assert all(a.status == "not_applicable" for a in receipt.axes.values())

    def test_fully_measured_axis_is_observed_sum(self) -> None:
        receipt = receipt_for([
            obs(run_id="r1", tokens=100, wall_time_ms=10.0),
            obs(run_id="r2", tokens=50, wall_time_ms=20.0, provider="b-forge"),
        ])
        assert receipt.axes["tokens"].status == "observed"
        assert receipt.axes["tokens"].value == 150
        assert receipt.axes["tokens"].coverage == 2
        assert receipt.axes["wall_time_ms"].value == 30.0
        assert receipt.axes["cost_usd"].status == "unresolved"
        assert receipt.axes["cost_usd"].missing == 2

    def test_partial_coverage_is_unresolved_never_partial_sum(self) -> None:
        receipt = receipt_for([obs(run_id="r1", tokens=10), obs(run_id="r2")])
        axis = receipt.axes["tokens"]
        assert axis.status == "unresolved"
        assert axis.value is None  # partial sums are never shown as numbers
        assert axis.coverage == 1 and axis.missing == 1

    def test_duplicate_identical_observations_count_once(self) -> None:
        receipt = receipt_for([obs(tokens=5), obs(tokens=5)])
        assert receipt.observations == 1
        assert receipt.axes["tokens"].value == 5
        assert receipt.conflicts == []

    def test_conflicting_observations_are_preserved(self) -> None:
        receipt = receipt_for([
            obs(tokens=100, wall_time_ms=5.0),
            obs(tokens=300, wall_time_ms=5.0),
        ])
        assert receipt.axes["tokens"].status == "conflict"
        assert receipt.axes["tokens"].value is None
        assert any("tokens: 100.0 vs 300.0" in c for c in receipt.conflicts)
        # Untouched axes still aggregate normally.
        assert receipt.axes["wall_time_ms"].status == "observed"

    def test_conflicting_status_is_reported(self) -> None:
        receipt = receipt_for([obs(), obs(status="partial")])
        assert any("status:" in c for c in receipt.conflicts)

    def test_task_families_sorted_distinct(self) -> None:
        receipt = receipt_for([
            obs(run_id="r1", task_family="data.migration"),
            obs(run_id="r2", task_family="data.audit"),
            obs(run_id="r3"),
        ])
        assert receipt.task_families == ["data.audit", "data.migration"]

    def test_maturity_from_performance_store(self) -> None:
        performance = ProviderPerformance(
            producer=PRODUCER, created_at="t", entries=[
                perf_entry("p1", "data.pipeline", 10, "s-new",
                           "2026-01-02T00:00:00Z"),
                perf_entry("p1", "data.pipeline", 8, "s-old",
                           "2026-01-01T00:00:00Z"),
            ])
        receipt = receipt_for([obs()], performance)
        assert receipt.maturity["p1/data.pipeline@s-new"] == "mature"
        assert receipt.maturity["p1/data.pipeline@s-old"] == "stale"

    def test_maturity_states_by_runs(self) -> None:
        performance = ProviderPerformance(
            producer=PRODUCER, created_at="t", entries=[
                perf_entry("p1", "c1", 1, "s", "2026-01-01T00:00:00Z"),
                perf_entry("p2", "c1", 4, "s", "2026-01-01T00:00:00Z"),
            ])
        receipt = receipt_for([obs()], performance)
        assert receipt.maturity["p1/c1@s"] == "cold"
        assert receipt.maturity["p2/c1@s"] == "warming"

    def test_limitations_merged_distinct(self) -> None:
        receipt = receipt_for([
            obs(run_id="r1", limitations=["a", "b"]),
            obs(run_id="r2", limitations=["b", "c"]),
        ])
        assert receipt.limitations == ["a", "b", "c"]

    def test_deterministic_order(self) -> None:
        many = [obs(run_id=f"r{i}", tokens=i) for i in range(5)]
        a = receipt_for(list(reversed(many)))
        b = receipt_for(many)
        assert a.axes["tokens"].value == b.axes["tokens"].value
        assert a.conflicts == b.conflicts

    def test_serialization_roundtrip(self) -> None:
        from theforge.contracts.base import from_dict, to_dict
        receipt = receipt_for([obs(tokens=7, task_family="data.audit")])
        again = from_dict(GlobalEconomyReceipt, to_dict(receipt), strict=True)
        assert again == receipt


# ---------- end-to-end: a real ask run writes an observation ----------


class TestE2E:
    def test_ask_run_records_observation(self, tmp_path: Path) -> None:
        from helpers import API_ENTRY, SPARK_ENTRY, case_a, make_workspace
        from theforge.contracts.negotiation import CapabilityRequirement
        from theforge.forger import AskRequest, Forger
        from theforge.registry import Registry
        from theforge.runs import RunStore

        make_workspace(tmp_path, [SPARK_ENTRY, API_ENTRY])
        case_a(tmp_path)
        forge = tmp_path / ".forge"
        requirement = CapabilityRequirement(
            id="req-1", capability="spark.performance",
            task_family="data.migration")
        out = Forger(tmp_path, Registry(forge), RunStore(forge)).ask(
            AskRequest(intent="analise esse glue job lento",
                       requirement=requirement))
        assert out.status == "ok"

        observations, warning = load_observations(tmp_path)
        assert warning is None and len(observations) == 1
        recorded = observations[0]
        assert recorded.run_id == out.run_id
        assert recorded.provider == "fixture-spark"
        assert recorded.capability == "spark.performance"
        assert recorded.status == "ok"
        assert recorded.task_family == "data.migration"
        assert recorded.surface_fingerprint
        assert recorded.environment_fingerprint
        assert recorded.profile is not None
        assert recorded.provider_calls == 1
        assert recorded.semantic_calls == 0
        assert recorded.context_bytes is not None
        assert recorded.context_bytes > 0
        assert recorded.wall_time_ms is not None
        assert recorded.wall_time_ms >= 0
        assert recorded.verification == "passed"

    def test_economy_report_cli(self, tmp_path: Path) -> None:
        from theforge.cli.commands import cmd_economy_report

        record_observation(tmp_path, obs(tokens=10, wall_time_ms=3.0))
        cmd_economy_report(_args_at(tmp_path, json_=False))
        cmd_economy_report(_args_at(tmp_path, json_=True))

    def test_economy_report_exposes_context_roi_and_advisory(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from theforge.cli.commands import cmd_economy_report

        for i in range(8):
            record_observation(
                tmp_path,
                obs(
                    run_id=f"roi-{i}",
                    task_family="data.audit",
                    surface_fingerprint="surface-a",
                    profile="balanced",
                    context_bytes=1_000,
                    context_items=10,
                    context_items_cited=1,
                    verification="passed",
                ),
            )
        assert cmd_economy_report(_args_at(tmp_path, json_=True)) == 0
        payload = json.loads(capsys.readouterr().out)
        (row,) = payload["context_roi"]
        assert row["roi"]["maturity"] == "mature"
        assert row["roi"]["utilization_ratio"] == pytest.approx(0.1)
        recommendation = row["recommendation"]
        assert recommendation is not None
        assert recommendation["advisory"] is True
        assert recommendation["current_budget_bytes"] == 262_144
        assert recommendation["suggested_budget_bytes"] == 131_072

    def test_economy_report_does_not_mix_profiles_for_roi_advice(
            self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        from theforge.cli.commands import cmd_economy_report

        base = dict(
            task_family="data.audit",
            surface_fingerprint="surface-1",
            context_bytes=100,
            context_items=10,
            context_items_cited=1,
            verification="passed",
        )
        for index, profile in enumerate(
            [
                "economy",
                "balanced",
                "economy",
                "balanced",
                "economy",
                "balanced",
                "economy",
                "balanced",
            ]
        ):
            record_observation(
                tmp_path,
                obs(run_id=f"mixed-{index}", profile=profile, **base),
            )
        cmd_economy_report(_args_at(tmp_path, json_=True))
        payload = json.loads(capsys.readouterr().out)
        rows = payload["context_roi"]
        assert len(rows) == 1
        assert rows[0]["recommendation"] is None
        assert "one known profile" in rows[0]["recommendation_limitation"]


    def test_discovery_report_carries_economy(self, tmp_path: Path) -> None:
        from theforge.contracts.negotiation import CapabilityRequirement
        from theforge.registry.discovery import discover
        from theforge.registry.sources import SourceSpec

        document = tmp_path / "reg.json"
        document.write_text(json.dumps({
            "schema": "theforge/RegistryDocument/v1",
            "registry": {"id": "feed", "name": "Feed",
                         "url": "https://reg.example"},
            "produced_at": "2026-01-01T00:00:00Z",
            "entries": [],
        }), encoding="utf-8")
        spec = SourceSpec(id="feed", kind="local-file", enabled=True,
                          path=str(document))
        report = discover(
            CapabilityRequirement(id="r", capability="data.pipeline"),
            [], specs=[spec], forge_dir=tmp_path)
        assert report.registry_calls == 1
        assert report.metadata_bytes == document.stat().st_size
        assert report.network_ms is None  # local-file reads pay no latency


def _args_at(root: Path, *, json_: bool) -> argparse.Namespace:
    return argparse.Namespace(root=str(root), json=json_)
