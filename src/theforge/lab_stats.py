"""Deterministic statistics for repeated lab runs (§9.7, spec cyc9-02).

Median + dispersion for repeated measurements — never invented: with one
sample there is no spread to report, with zero measured samples the
summary says so honestly. stdlib-only, no randomness.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median, quantiles

from theforge.contracts.benchmark import BenchmarkResult, MetricValue


@dataclass(frozen=True, kw_only=True)
class MetricSummary:
    """Dispersion summary of one metric across repeated runs."""

    name: str
    n: int  # runs that reported the metric at all
    measured: int  # runs whose datum is state=measured
    states: dict[str, int]  # state -> count
    median: float | None = None
    mad: float | None = None  # median absolute deviation
    iqr: float | None = None  # interquartile range (n >= 4 for quantiles)
    min: float | None = None
    max: float | None = None


def numeric_values(metric: MetricValue) -> float | None:
    """A metric's numeric payload, or ``None`` when absent/non-numeric —
    strings and unmeasured states are never coerced to 0."""
    if not metric.measured or metric.value is None:
        return None
    if isinstance(metric.value, bool):
        return None
    if isinstance(metric.value, (int, float)):
        return float(metric.value)
    return None


def summarize(name: str, metrics: list[MetricValue]) -> MetricSummary:
    """Summarize one metric across repeated scenario results."""
    states: dict[str, int] = {}
    values: list[float] = []
    for m in metrics:
        states[m.state] = states.get(m.state, 0) + 1
        v = numeric_values(m)
        if v is not None:
            values.append(v)
    if not values:
        return MetricSummary(name=name, n=len(metrics), measured=0, states=states)
    med = median(values)
    mad = median([abs(v - med) for v in values]) if len(values) > 1 else 0.0
    iqr = quantiles(values, n=4)[2] - quantiles(values, n=4)[0] if len(values) >= 4 else None
    return MetricSummary(
        name=name,
        n=len(metrics),
        measured=len(values),
        states=states,
        median=med,
        mad=mad,
        iqr=iqr,
        min=min(values),
        max=max(values),
    )


def scenario_metrics(runs: list[BenchmarkResult], scenario_id: str) -> dict[str, list[MetricValue]]:
    """Group a scenario's metrics across repeated receipts by metric name."""
    grouped: dict[str, list[MetricValue]] = {}
    for run in runs:
        for res in run.results:
            if res.scenario_id != scenario_id:
                continue
            for name, metric in res.metrics.items():
                grouped.setdefault(name, []).append(metric)
    return grouped
