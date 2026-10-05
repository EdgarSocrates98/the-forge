"""TelemetryRecorder: phases, counters and the RunTelemetry it builds (task 3.5)."""

import json
from collections.abc import Iterator

import pytest

from theforge.context.verify import NOT_REVERIFIED_LIMITATION, DriftReport
from theforge.contracts.base import from_dict, to_dict
from theforge.contracts.telemetry import RunTelemetry
from theforge.contracts.types import Metric
from theforge.forger.telemetry import (
    COUNTERS,
    PHASES,
    REVALIDATION_UNDECLARED_LIMITATION,
    TelemetryRecorder,
)
from theforge.profiles import profile_for

ALL_METRICS = (
    "scan_ms", "routing_ms", "context_ms", "provider_ms",
    "files_scanned", "files_selected", "files_hashed", "bytes_hashed",
    "cache_hits", "cache_misses", "context_bytes",
    "providers_executed", "fallbacks_used", "negotiation_rounds",
)


class FakeClock:
    """Each call returns the next tick; a phase spans two consecutive calls."""

    def __init__(self, *ticks: float) -> None:
        self._ticks: Iterator[float] = iter(ticks)

    def __call__(self) -> float:
        return next(self._ticks)


def _recorder(profile: str = "balanced", *ticks: float) -> TelemetryRecorder:
    return TelemetryRecorder("run-1", profile_for(profile),  # type: ignore[arg-type]
                             clock=FakeClock(*ticks), now=lambda: "2026-10-04T00:00:00.000000Z")


def _roundtrip(telemetry: RunTelemetry) -> RunTelemetry:
    data = json.loads(json.dumps(to_dict(telemetry)))
    return from_dict(RunTelemetry, data, strict=True)


def test_closed_names_match_the_contract() -> None:
    assert PHASES == ("scan", "routing", "context", "provider")
    assert set(COUNTERS) | {f"{p}_ms" for p in PHASES} == set(ALL_METRICS)


def test_run_interrupted_before_context_has_later_phases_unknown() -> None:
    rec = _recorder("economy", 0.0, 0.010, 0.010, 0.0125)
    with rec.phase("scan"):
        pass
    rec.count("files_scanned", 42)
    with rec.phase("routing"):
        pass

    tel = rec.build()

    assert tel.scan_ms == Metric(value=10.0, kind="measured")
    assert tel.routing_ms == Metric(value=2.5, kind="measured")
    assert tel.files_scanned == Metric(value=42.0, kind="measured")
    for name in ("context_ms", "provider_ms", "files_selected", "files_hashed",
                 "bytes_hashed", "cache_hits", "cache_misses", "context_bytes",
                 "providers_executed", "fallbacks_used", "negotiation_rounds"):
        assert getattr(tel, name) == Metric(kind="unknown"), name
    assert tel.unknowns == sorted(set(ALL_METRICS) - {"scan_ms", "routing_ms", "files_scanned"})
    assert tel.provider_revalidation is None
    assert tel.verification_performed is None
    assert tel.context_drift == []
    assert tel.profile.name == "economy"
    assert tel.profile.effective_tiers == []
    assert tel.run_id == "run-1"
    assert tel.created_at == "2026-10-04T00:00:00.000000Z"
    assert _roundtrip(tel) == tel


def test_complete_run_has_every_metric_measured() -> None:
    # scan, routing, context, provider round 1, provider round 2
    rec = _recorder("max", 0.0, 0.001, 1.0, 1.002, 2.0, 2.003, 3.0, 3.1, 4.0, 4.0005)
    with rec.phase("scan"):
        pass
    with rec.phase("routing"):
        pass
    with rec.phase("context"):
        pass
    with rec.phase("provider"):
        pass
    with rec.phase("provider"):
        pass
    for name, value in (("files_scanned", 10), ("files_selected", 3), ("files_hashed", 2),
                        ("bytes_hashed", 900), ("cache_hits", 1), ("cache_misses", 2),
                        ("context_bytes", 1200), ("providers_executed", 1),
                        ("fallbacks_used", 0), ("negotiation_rounds", 1)):
        rec.count(name, value)
    rec.set_effective_tiers(["requested", "metadata", "reference"])
    rec.set_revalidation("hash")
    rec.set_drift(DriftReport(drifted=("a.py", "b.py"), checked=3, level="strong",
                              limitations=()))

    tel = rec.build()

    for name in ALL_METRICS:
        assert getattr(tel, name).kind == "measured", name
    assert tel.unknowns == []
    assert tel.scan_ms.value == 1.0
    assert tel.routing_ms.value == 2.0
    assert tel.context_ms.value == 3.0
    assert tel.provider_ms.value == 100.5  # sum of both execution rounds
    assert tel.fallbacks_used == Metric(value=0.0, kind="measured")
    assert tel.profile.effective_tiers == ["metadata", "reference", "requested"]
    assert tel.profile.tiers == ["metadata", "reference", "excerpt", "requested"]
    assert tel.profile.max_providers == 4
    assert tel.profile.verification == "strong"
    assert tel.provider_revalidation == "hash"
    assert tel.verification_performed == "strong"
    assert tel.context_drift == ["a.py", "b.py"]
    assert tel.limitations == []
    assert _roundtrip(tel) == tel


def test_plan_run_shape_scan_routing_and_many_providers() -> None:
    rec = _recorder("max", 0.0, 0.004, 0.004, 0.005)
    with rec.phase("scan"):
        pass
    with rec.phase("routing"):
        pass
    rec.count("files_scanned", 7)
    rec.count("providers_executed", 3)

    tel = rec.build()

    assert tel.providers_executed == Metric(value=3.0, kind="measured")
    assert tel.scan_ms.kind == tel.routing_ms.kind == "measured"
    assert tel.context_ms.kind == tel.provider_ms.kind == "unknown"
    assert tel.profile.effective_tiers == []
    assert tel.provider_revalidation is None
    assert _roundtrip(tel) == tel


def test_counters_accumulate() -> None:
    rec = _recorder()
    rec.count("providers_executed", 1)
    rec.count("providers_executed", 1)
    rec.count("fallbacks_used", 0)
    tel = rec.build()
    assert tel.providers_executed.value == 2.0
    assert tel.fallbacks_used == Metric(value=0.0, kind="measured")


def test_phase_is_measured_even_when_it_raises() -> None:
    rec = _recorder("balanced", 0.0, 0.25)
    with pytest.raises(RuntimeError), rec.phase("provider"):
        raise RuntimeError("provider crashed")
    assert rec.build().provider_ms == Metric(value=250.0, kind="measured")


def test_phase_duration_rounded_to_three_places() -> None:
    rec = _recorder("balanced", 0.0, 0.0123456789)
    with rec.phase("scan"):
        pass
    assert rec.build().scan_ms.value == 12.346


def test_undeclared_revalidation_records_limitation_once() -> None:
    rec = _recorder()
    rec.set_revalidation(None)
    rec.set_revalidation(None)
    tel = rec.build()
    assert tel.provider_revalidation == "undeclared"
    assert tel.limitations == [REVALIDATION_UNDECLARED_LIMITATION]


def test_drift_limitations_and_notes_go_into_telemetry() -> None:
    rec = _recorder("economy")
    rec.note("git: not a repository")
    rec.set_drift(DriftReport(drifted=(), checked=0, level="minimal",
                              limitations=(NOT_REVERIFIED_LIMITATION,)))
    tel = rec.build()
    assert tel.verification_performed == "minimal"
    assert tel.context_drift == []
    assert tel.limitations == ["git: not a repository", NOT_REVERIFIED_LIMITATION]


def test_rejects_unknown_names_and_invalid_values() -> None:
    rec = _recorder()
    with pytest.raises(ValueError):
        rec.count("tokens", 1)
    with pytest.raises(ValueError):
        rec.count("scan_ms", 1)
    with pytest.raises(ValueError):
        rec.count("files_scanned", -1)
    with pytest.raises(ValueError), rec.phase("verify"):  # type: ignore[arg-type]
        pass
    with pytest.raises(ValueError):
        rec.set_effective_tiers(["whole-repo"])


def test_build_is_repeatable_and_independent() -> None:
    rec = _recorder()
    rec.note("x")
    first = rec.build()
    first.limitations.append("mutated")
    assert rec.build().limitations == ["x"]
