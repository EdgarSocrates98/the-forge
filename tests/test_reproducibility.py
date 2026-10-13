"""Reproducibility level of a run and of a plan (task 3.2, requirements 14.1-14.3)."""

from dataclasses import replace
from typing import Any

import pytest

from theforge.context.verify import DriftReport
from theforge.contracts.manifest import ExecutionInfo
from theforge.contracts.types import Producer, Reproducibility
from theforge.contracts.verification import (
    ReproducibilityInfo,
    VerificationCheck,
    VerificationResult,
)
from theforge.forger.reproducibility import assess_run, combine_levels
from theforge.providers.echo.provider import MANIFEST as ECHO

SHA = "a" * 64
CAPABILITY = ECHO.capabilities[0]


def _verification(forge: str = "passed") -> VerificationResult:
    return VerificationResult(
        producer=Producer(id="theforge", version="0"),
        created_at="2026-10-04T00:00:00Z",
        run_id="run-1",
        self_report=VerificationCheck(status="reported"),
        provider_evidence=VerificationCheck(status="reported"),
        forge=VerificationCheck(status=forge),  # type: ignore[arg-type]
        independent=VerificationCheck(status="not_performed"),
    )


def _drift(level: str = "conditional", drifted: tuple[str, ...] = ()) -> DriftReport:
    return DriftReport(
        drifted=drifted,
        checked=1,
        level=level,  # type: ignore[arg-type]
        limitations=(),
    )


def _assess(**overrides: Any) -> ReproducibilityInfo:
    kwargs: dict[str, Any] = {
        "executed": True,
        "manifest": ECHO,
        "capability": CAPABILITY,
        "fingerprint": SHA,
        "context_sha256": SHA,
        "drift": _drift(),
        "verification": _verification(),
        "status": "ok",
        "upstream": (),
    }
    kwargs.update(overrides)
    return assess_run(**kwargs)


def _with_execution(**fields: Any) -> Any:
    return replace(ECHO, execution=replace(ECHO.execution, **fields))


def test_all_conditions_met_is_reproducible() -> None:
    info = _assess()
    assert info.level == "reproducible"
    assert info.reasons


@pytest.mark.parametrize("status", ["no_route", "ambiguous", "refused", "planned"])
def test_no_provider_execution_is_unknown(status: str) -> None:
    info = _assess(executed=False, status=status)
    assert info.level == "unknown"
    assert info.reasons


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"manifest": _with_execution(requires_network=True)}, "network"),
        ({"manifest": _with_execution(offline=False)}, "offline"),
        ({"manifest": _with_execution(local=False)}, "local"),
        ({"capability": replace(CAPABILITY, operation_class="external_read")}, "external_read"),
        (
            {"capability": replace(CAPABILITY, operation_class="external_mutation")},
            "external_mutation",
        ),
        ({"capability": replace(CAPABILITY, operation_class="destructive")}, "destructive"),
        ({"drift": _drift(drifted=("a.txt",))}, "a.txt"),
        ({"upstream": ("reproducible", "non_reproducible")}, "handoff"),
    ],
)
def test_each_external_or_divergent_condition_is_non_reproducible(
    overrides: dict[str, Any], expected: str
) -> None:
    info = _assess(**overrides)
    assert info.level == "non_reproducible"
    assert any(expected in reason for reason in info.reasons), info.reasons


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"manifest": _with_execution(deterministic=None)}, "deterministic"),
        ({"manifest": _with_execution(deterministic=False)}, "deterministic"),
        ({"capability": replace(CAPABILITY, operation_class="local_mutation")}, "local_mutation"),
        ({"fingerprint": None}, "fingerprint"),
        ({"context_sha256": None}, "context hash"),
        ({"drift": None}, "context verification"),
        ({"drift": _drift(level="minimal")}, "minimal"),
        ({"verification": None}, "verification"),
        ({"verification": _verification("failed")}, "failed"),
        ({"verification": _verification("not_performed")}, "not_performed"),
        ({"status": "partial"}, "partial"),
        ({"upstream": ("reproducible", "partially_reproducible")}, "handoff"),
        ({"upstream": ("unknown",)}, "handoff"),
        ({"manifest": None}, "manifest"),
        ({"capability": None}, "capability"),
    ],
)
def test_each_unmet_condition_is_partially_reproducible(
    overrides: dict[str, Any], expected: str
) -> None:
    info = _assess(**overrides)
    assert info.level == "partially_reproducible"
    assert any(expected in reason for reason in info.reasons), info.reasons


def test_undeclared_determinism_is_never_reproducible() -> None:
    manifest = _with_execution(deterministic=None)
    assert ExecutionInfo().deterministic is None
    assert _assess(manifest=manifest).level != "reproducible"


def test_every_unmet_condition_is_a_reason() -> None:
    info = _assess(
        fingerprint=None,
        context_sha256=None,
        status="partial",
        manifest=_with_execution(deterministic=None),
    )
    assert info.level == "partially_reproducible"
    text = " | ".join(info.reasons)
    for expected in ("fingerprint", "context hash", "partial", "deterministic"):
        assert expected in text


def test_external_and_divergent_reasons_accumulate() -> None:
    info = _assess(
        manifest=_with_execution(requires_network=True),
        drift=_drift(drifted=("b.txt",)),
        fingerprint=None,
    )
    assert info.level == "non_reproducible"
    text = " | ".join(info.reasons)
    assert "network" in text and "b.txt" in text


def _info(level: Reproducibility, *reasons: str) -> ReproducibilityInfo:
    return ReproducibilityInfo(level=level, reasons=list(reasons))


@pytest.mark.parametrize(
    ("levels", "expected"),
    [
        ((), "unknown"),
        (("reproducible",), "reproducible"),
        (("reproducible", "reproducible"), "reproducible"),
        (("reproducible", "partially_reproducible"), "partially_reproducible"),
        (("partially_reproducible", "unknown"), "unknown"),
        (("reproducible", "unknown", "non_reproducible"), "non_reproducible"),
        (("non_reproducible", "reproducible"), "non_reproducible"),
    ],
)
def test_combine_levels_takes_the_least_reproducible(
    levels: tuple[Reproducibility, ...], expected: Reproducibility
) -> None:
    combined = combine_levels([_info(level, f"r-{i}") for i, level in enumerate(levels)])
    assert combined.level == expected
    assert combined.reasons


def test_combine_levels_keeps_node_reasons_in_order_without_duplicates() -> None:
    combined = combine_levels(
        [_info("reproducible", "x"), _info("partially_reproducible", "y", "x")]
    )
    assert combined.reasons == ["x", "y"]
