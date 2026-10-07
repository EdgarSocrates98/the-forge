"""Cycle 4.1 context ROI and conservative experiment framework."""

import pytest

from theforge.adaptive import advance_experiment, build_context_roi, recommend_context_budget
from theforge.contracts import (
    ContextBudgetRecommendation,
    ContractError,
    ExecutionObservation,
    StrategyExperiment,
)
from theforge.meta import PRODUCER


def obs(
    run: str,
    *,
    provider: str = "spark",
    surface: str = "s1",
    family: str = "data.spark.performance",
    items: int | None = 10,
    cited: int | None = 1,
    bytes_: int | None = 1000,
    verified: str = "passed",
) -> ExecutionObservation:
    return ExecutionObservation(
        producer=PRODUCER,
        created_at="2026-10-07T00:00:00Z",
        run_id=run,
        provider=provider,
        capability="data.performance",
        task_family=family,
        surface_fingerprint=surface,
        status="ok",
        context_bytes=bytes_,
        context_items=items,
        context_items_cited=cited,
        verification=verified,  # type: ignore[arg-type]
    )


def test_roi_never_crosses_surface_or_family() -> None:
    observations = [
        obs("r1"),
        obs("r2"),
        obs("r3", surface="s2"),
        obs("r4", family="data.streaming"),
    ]
    roi = build_context_roi(
        observations,
        provider="spark",
        capability="data.performance",
        surface_fingerprint="s1",
        task_family="data.spark.performance",
    )
    assert roi.runs == 2
    assert roi.measured_runs == 2
    assert roi.delivered_items == 20
    assert roi.cited_items == 2
    assert roi.utilization_ratio == pytest.approx(0.1)
    assert roi.maturity == "cold"
    assert roi.delivered_runs == 2
    assert roi.verified_runs == 2


def test_unknown_measurements_remain_a_limitation() -> None:
    roi = build_context_roi(
        [obs("r1"), obs("r2", items=None, cited=None, bytes_=None), obs("r3")],
        provider="spark",
        capability="data.performance",
        surface_fingerprint="s1",
    )
    assert roi.runs == 3
    assert roi.measured_runs == 2
    assert roi.maturity == "warming"
    assert roi.limitations
    assert recommend_context_budget(roi, current_budget_bytes=200_000) is None


def test_roi_recommendation_is_advisory_and_conservative() -> None:
    roi = build_context_roi(
        [obs(f"r{i}") for i in range(8)],
        provider="spark",
        capability="data.performance",
        surface_fingerprint="s1",
    )
    rec = recommend_context_budget(roi, current_budget_bytes=200_000)
    assert rec is not None
    assert rec.advisory is True
    assert rec.suggested_budget_bytes == 100_000
    assert rec.maturity == "mature"
    assert any("causality is not inferred" in item for item in rec.basis)


def test_unverified_history_never_recommends_context_reduction() -> None:
    roi = build_context_roi(
        [
            obs("r1"),
            obs("r2"),
            obs("r3", verified="failed"),
            *[obs(f"r{i}") for i in range(4, 9)],
        ],
        provider="spark",
        capability="data.performance",
        surface_fingerprint="s1",
    )
    assert roi.maturity == "mature"
    assert roi.verified_runs < roi.runs
    assert recommend_context_budget(roi, current_budget_bytes=200_000) is None


def test_high_utilization_does_not_recommend_reduction() -> None:
    roi = build_context_roi(
        [obs(f"r{i}", cited=8) for i in range(8)],
        provider="spark",
        capability="data.performance",
        surface_fingerprint="s1",
    )
    assert recommend_context_budget(roi, current_budget_bytes=200_000) is None


def test_cold_history_never_recommends() -> None:
    roi = build_context_roi(
        [obs("r1"), obs("r2")],
        provider="spark",
        capability="data.performance",
        surface_fingerprint="s1",
    )
    assert recommend_context_budget(roi, current_budget_bytes=200_000) is None


def experiment(**over: object) -> StrategyExperiment:
    base = dict(
        producer=PRODUCER,
        created_at="t",
        experiment_id="exp-1",
        capability="data.performance",
        task_family="data.spark.performance",
        champion="spark-a",
        challenger="spark-b",
        champion_surface="sa",
        challenger_surface="sb",
        minimum_runs=4,
        minimum_verified_runs=3,
    )
    base.update(over)
    return StrategyExperiment(**base)  # type: ignore[arg-type]


def eval_obs(
    run: str,
    provider: str,
    surface: str,
    verified: str = "passed",
    created_at: str = "2026-10-07T13:00:00Z",
) -> ExecutionObservation:
    return ExecutionObservation(
        producer=PRODUCER,
        created_at=created_at,
        run_id=run,
        provider=provider,
        capability="data.performance",
        task_family="data.spark.performance",
        surface_fingerprint=surface,
        status="ok",
        context_bytes=1000 if provider == "spark-a" else 500,
        verification=verified,  # type: ignore[arg-type]
    )


def test_experiment_is_shadow_without_observations() -> None:
    result = advance_experiment(experiment(), [])
    assert result.state == "shadow"
    assert result.operator_approval_required is True


def test_experiment_becomes_reviewable_but_never_auto_promotes() -> None:
    result = advance_experiment(
        experiment(),
        [
            eval_obs("r1", "spark-a", "sa"),
            eval_obs("r2", "spark-b", "sb"),
            eval_obs("r3", "spark-a", "sa"),
            eval_obs("r4", "spark-b", "sb"),
        ],
    )
    assert result.state == "eligible_for_review"
    assert result.verified_observations == 4
    assert result.state != "promoted"


def test_time_holdout_excludes_hypothesis_history() -> None:
    result = advance_experiment(
        experiment(
            evaluation_after="2026-10-07T12:00:00Z",
            minimum_runs=2,
            minimum_verified_runs=2,
        ),
        [
            eval_obs(
                "before",
                "spark-a",
                "sa",
                created_at="2026-10-07T11:59:59Z",
            ),
            eval_obs("after-a", "spark-a", "sa"),
            eval_obs("after-b", "spark-b", "sb"),
        ],
    )
    assert result.observations == 2
    assert result.verified_observations == 2
    assert result.state == "eligible_for_review"

def test_one_sided_history_never_becomes_reviewable() -> None:
    result = advance_experiment(
        experiment(minimum_runs=4, minimum_verified_runs=4),
        [
            eval_obs("r1", "spark-a", "sa"),
            eval_obs("r2", "spark-a", "sa"),
            eval_obs("r3", "spark-a", "sa"),
            eval_obs("r4", "spark-a", "sa"),
        ],
    )
    assert result.state == "observing"
    assert any("both champion and challenger" in reason for reason in result.reasons)


def test_challenger_quality_regression_blocks_review() -> None:
    result = advance_experiment(
        experiment(minimum_runs=4, minimum_verified_runs=3),
        [
            eval_obs("r1", "spark-a", "sa"),
            eval_obs("r2", "spark-a", "sa"),
            eval_obs("r3", "spark-b", "sb"),
            eval_obs("r4", "spark-b", "sb", verified="failed"),
        ],
    )
    assert result.state == "observing"
    assert any("verification rate is worse" in reason for reason in result.reasons)


def test_holdout_uses_temporal_not_lexical_ordering() -> None:
    result = advance_experiment(
        experiment(
            evaluation_after="2026-10-07T12:00:00Z",
            minimum_runs=2,
            minimum_verified_runs=2,
        ),
        [
            # 11:30 -01:00 == 12:30Z, so it is after the cutoff despite
            # the local clock string looking earlier than 12:00.
            eval_obs(
                "after-offset-a",
                "spark-a",
                "sa",
                created_at="2026-10-07T11:30:00-01:00",
            ),
            eval_obs(
                "after-offset-b",
                "spark-b",
                "sb",
                created_at="2026-10-07T11:31:00-01:00",
            ),
        ],
    )
    assert result.observations == 2
    assert result.state == "eligible_for_review"


def test_malformed_historical_timestamp_is_not_evaluation_evidence() -> None:
    result = advance_experiment(
        experiment(
            evaluation_after="2026-10-07T12:00:00Z",
            minimum_runs=2,
            minimum_verified_runs=2,
        ),
        [
            eval_obs("bad", "spark-a", "sa", created_at="not-a-time"),
            eval_obs("good-a", "spark-a", "sa"),
            eval_obs("good-b", "spark-b", "sb"),
        ],
    )
    assert result.observations == 2
    assert result.state == "eligible_for_review"


def test_surface_change_invalidates_experiment() -> None:
    result = advance_experiment(
        experiment(),
        [eval_obs("r1", "spark-b", "new-surface")],
    )
    assert result.state == "stale"
    assert "surface changed" in result.reasons[-1]


def test_experiment_requires_timezone_aware_holdout() -> None:
    with pytest.raises(ContractError, match="ISO-8601"):
        experiment(evaluation_after="2026-10-07T12:00:00")


def test_experiment_rejects_invalid_holdout_timestamps() -> None:
    with pytest.raises(ContractError, match="ISO-8601"):
        experiment(evaluation_after="not-a-time")
    with pytest.raises(ContractError, match="cannot precede"):
        experiment(
            discovery_before="2026-10-07T13:00:00Z",
            evaluation_after="2026-10-07T12:00:00Z",
        )


def test_experiment_requires_distinct_strategies() -> None:
    with pytest.raises(ContractError, match="must differ"):
        experiment(challenger="spark-a")


def test_recommendation_cannot_increase_budget() -> None:
    with pytest.raises(ContractError, match="reduce"):
        ContextBudgetRecommendation(
            producer=PRODUCER,
            created_at="t",
            provider="p",
            capability="c",
            surface_fingerprint="s",
            task_family=None,
            current_budget_bytes=100,
            suggested_budget_bytes=100,
            maturity="warming",
            basis=["x"],
        )
