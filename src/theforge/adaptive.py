"""Context ROI aggregation and conservative strategy experiments."""

from dataclasses import replace
from statistics import median
from typing import Literal, cast

from theforge.contracts.adaptive import (
    ContextBudgetRecommendation,
    ContextROI,
    ExperimentState,
    HistoryMaturity,
    StrategyExperiment,
)
from theforge.contracts.canonical import utc_now
from theforge.contracts.observation import ExecutionObservation
from theforge.meta import PRODUCER


def _timestamp(value: str) -> datetime:
    """Parse the contract-validated ISO-8601 timestamp for temporal comparison."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _maturity(runs: int) -> HistoryMaturity:
    if runs <= 0:
        return "absent"
    if runs < 3:
        return "cold"
    if runs < 8:
        return "warming"
    return "mature"


def build_context_roi(
    observations: list[ExecutionObservation],
    *,
    provider: str,
    capability: str,
    surface_fingerprint: str,
    task_family: str | None = None,
) -> ContextROI:
    """Aggregate only comparable observations; never cross a surface boundary."""
    comparable = [
        item
        for item in observations
        if item.provider == provider
        and item.capability == capability
        and item.surface_fingerprint == surface_fingerprint
        and (task_family is None or item.task_family == task_family)
    ]
    measured = [
        item
        for item in comparable
        if item.context_bytes is not None
        and item.context_items is not None
        and item.context_items_cited is not None
    ]
    delivered_bytes = sum(item.context_bytes or 0 for item in measured)
    delivered_items = sum(item.context_items or 0 for item in measured)
    cited_items = sum(item.context_items_cited or 0 for item in measured)
    utilization = (cited_items / delivered_items) if delivered_items else None
    limitations: list[str] = []
    if task_family is None and comparable:
        limitations.append("task family is unscoped; comparable runs may span families")
    if len(measured) < len(comparable):
        limitations.append("some comparable runs lack complete context measurements")
    if not comparable:
        limitations.append("no comparable observations")

    return ContextROI(
        producer=PRODUCER,
        created_at=utc_now(),
        provider=provider,
        capability=capability,
        surface_fingerprint=surface_fingerprint,
        task_family=task_family,
        runs=len(comparable),
        measured_runs=len(measured),
        delivered_bytes=delivered_bytes,
        delivered_items=delivered_items,
        cited_items=cited_items,
        utilization_ratio=utilization,
        maturity=_maturity(len(comparable)),
        limitations=limitations,
    )


def recommend_context_budget(
    roi: ContextROI,
    *,
    current_budget_bytes: int,
    floor_ratio: float = 0.5,
) -> ContextBudgetRecommendation | None:
    """Return an advisory reduction only for warming/mature, measured history."""
    if roi.maturity not in ("warming", "mature"):
        return None
    if roi.utilization_ratio is None or roi.measured_runs < 3:
        return None
    if not 0 < floor_ratio < 1:
        raise ValueError("floor_ratio must be in (0,1)")
    if roi.utilization_ratio >= 0.5:
        return None

    target_ratio = max(floor_ratio, min(0.9, roi.utilization_ratio * 2.0))
    suggested = max(1, int(current_budget_bytes * target_ratio))
    if suggested >= current_budget_bytes:
        return None
    return ContextBudgetRecommendation(
        producer=PRODUCER,
        created_at=utc_now(),
        provider=roi.provider,
        capability=roi.capability,
        surface_fingerprint=roi.surface_fingerprint,
        task_family=roi.task_family,
        current_budget_bytes=current_budget_bytes,
        suggested_budget_bytes=suggested,
        maturity=cast(Literal["warming", "mature"], roi.maturity),
        basis=[
            f"{roi.measured_runs} measured comparable runs",
            f"context citation utilization {roi.utilization_ratio:.3f}",
            "advisory only; quality causality is not inferred",
        ],
    )


def advance_experiment(
    experiment: StrategyExperiment,
    evaluation: list[ExecutionObservation],
) -> StrategyExperiment:
    """Advance a shadow experiment without ever auto-promoting it.

    Eligibility is deliberately stronger than sample-count maturity:
    both arms must be observed, challenger verification/delivery must not
    regress, and at least one comparable economy metric must improve without
    another measured economy metric regressing. Missing measurements remain
    unresolved rather than becoming an invented win.
    """
    if experiment.state in ("promoted", "rejected", "stale", "cancelled"):
        return experiment

    scoped = [
        item
        for item in evaluation
        if item.capability == experiment.capability
        and (experiment.task_family is None or item.task_family == experiment.task_family)
        and (
            experiment.evaluation_after is None
            or _timestamp(item.created_at) > _timestamp(experiment.evaluation_after)
        )
    ]
    if any(
        item.provider == experiment.champion
        and item.surface_fingerprint not in (None, experiment.champion_surface)
        for item in scoped
    ) or any(
        item.provider == experiment.challenger
        and item.surface_fingerprint not in (None, experiment.challenger_surface)
        for item in scoped
    ):
        return replace(
            experiment,
            state="stale",
            reasons=[*experiment.reasons, "provider surface changed during experiment"],
        )

    champion = [
        item for item in scoped
        if item.provider == experiment.champion
        and item.surface_fingerprint == experiment.champion_surface
    ]
    challenger = [
        item for item in scoped
        if item.provider == experiment.challenger
        and item.surface_fingerprint == experiment.challenger_surface
    ]
    comparable = [*champion, *challenger]
    verified = sum(1 for item in comparable if item.verification == "passed")
    observations = len(comparable)
    state: ExperimentState = "observing"
    reasons = list(experiment.reasons)

    if observations == 0:
        state = "shadow"
    elif not champion or not challenger:
        reasons.append("both champion and challenger require observed evaluation runs")
    elif (
        observations >= experiment.minimum_runs
        and verified >= experiment.minimum_verified_runs
    ):
        champion_verified = sum(
            1 for item in champion if item.verification == "passed"
        ) / len(champion)
        challenger_verified = sum(
            1 for item in challenger if item.verification == "passed"
        ) / len(challenger)
        champion_delivered = sum(
            1 for item in champion if item.status in ("ok", "partial")
        ) / len(champion)
        challenger_delivered = sum(
            1 for item in challenger if item.status in ("ok", "partial")
        ) / len(challenger)

        if challenger_verified < champion_verified:
            reasons.append(
                "challenger verification rate is worse than champion"
            )
        elif challenger_delivered < champion_delivered:
            reasons.append(
                "challenger delivered-result rate is worse than champion"
            )
        else:
            improved: list[str] = []
            regressed: list[str] = []
            for metric in ("context_bytes", "wall_time_ms", "cost_usd"):
                champion_values = [
                    float(value)
                    for item in champion
                    if (value := getattr(item, metric)) is not None
                ]
                challenger_values = [
                    float(value)
                    for item in challenger
                    if (value := getattr(item, metric)) is not None
                ]
                if not champion_values or not challenger_values:
                    continue
                incumbent = float(median(champion_values))
                candidate = float(median(challenger_values))
                if candidate < incumbent:
                    improved.append(metric)
                elif candidate > incumbent:
                    regressed.append(metric)
            if regressed:
                reasons.append(
                    "challenger regresses measured economy axes: "
                    + ", ".join(regressed)
                )
            elif not improved:
                reasons.append(
                    "no measured economy improvement yet; keep experiment observing"
                )
            else:
                state = "eligible_for_review"
                reasons.append(
                    "quality gates held and challenger improved: "
                    + ", ".join(improved)
                    + "; operator review required"
                )

    return replace(
        experiment,
        state=state,
        observations=observations,
        verified_observations=verified,
        reasons=reasons,
    )

def comparative_context_median(
    observations: list[ExecutionObservation], provider: str
) -> float | None:
    """Return no number when the underlying context metric is unknown."""
    values = [
        item.context_bytes
        for item in observations
        if item.provider == provider and item.context_bytes is not None
    ]
    return float(median(values)) if values else None
