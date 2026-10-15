"""Regression gate for lab results (§9.10, spec cyc9-02).

Compares current ``forge/BenchmarkResult/v1`` receipts against a real
baseline — never against invented thresholds:

- tolerance comes from the gate policy when declared, else from the
  observed baseline spread (max-min across repeated baseline runs),
  else 0 — "more tolerance than measured" is a human decision recorded
  in a versioned policy file, not a silent default;
- unmeasured metrics (``not_available``/``not_applicable``/absent on
  either side) are reported ``unmeasured`` — never zero, never gated;
- metric names outside the §9.5 taxonomy and without a policy entry are
  ``unknown`` — reported, never silently passing or failing;
- baseline and current pair by (forge, suite, scenario, subject) —
  subject mismatch means model variation would masquerade as infra
  variation, so the pair is ``no-baseline``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from statistics import median
from typing import Any, Literal

from theforge.contracts.base import ContractError, from_dict
from theforge.contracts.benchmark import (
    STANDARD_METRICS,
    BenchmarkResult,
    MetricValue,
    metric_direction,
)
from theforge.lab_stats import numeric_values

GATE_POLICY_SCHEMA = "forge/LabGatePolicy/v1"
POLICY_ID_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$", re.ASCII)

GateVerdict = Literal[
    "pass",
    "regression",
    "improvement",
    "changed",
    "unmeasured",
    "unknown",
    "informative",
    "no-baseline",
]


@dataclass(frozen=True, kw_only=True)
class GateRule:
    """Per-metric tolerance. ``None`` tolerances mean "calibrate from the
    baseline spread"; an explicit number is a recorded human decision."""

    direction: str | None = None  # defaults to the §9.5 taxonomy
    rel_tolerance: float | None = None  # fraction of |baseline|
    abs_tolerance: float | None = None


@dataclass(frozen=True, kw_only=True)
class GatePolicy:
    """``forge/LabGatePolicy/v1`` — versioned regression policy."""

    schema: str = GATE_POLICY_SCHEMA
    id: str = "default"
    defaults: GateRule = field(default_factory=GateRule)
    metrics: dict[str, GateRule] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.schema != GATE_POLICY_SCHEMA:
            raise ContractError(f"gate policy: unsupported schema {self.schema!r}")
        if not POLICY_ID_RE.fullmatch(self.id):
            raise ContractError(f"gate policy: bad id {self.id!r}")
        for name in self.metrics:
            if metric_direction(name) is None and self.metrics[name].direction is None:
                raise ContractError(
                    f"gate policy: {name!r} needs an explicit direction — "
                    "it is outside the §9.5 taxonomy"
                )
        for rule in (self.defaults, *self.metrics.values()):
            for t in (rule.rel_tolerance, rule.abs_tolerance):
                if t is not None and t < 0:
                    raise ContractError("gate policy: tolerances must be >= 0")

    def rule_for(self, name: str) -> GateRule:
        return self.metrics.get(name, self.defaults)


def parse_policy(data: Any) -> GatePolicy:
    return from_dict(GatePolicy, data, strict=True)


DEFAULT_POLICY = GatePolicy()


@dataclass(frozen=True, kw_only=True)
class MetricVerdict:
    name: str
    verdict: GateVerdict
    baseline: float | str | None = None
    current: float | str | None = None
    tolerance: float | None = None
    direction: str | None = None


@dataclass(frozen=True, kw_only=True)
class ScenarioVerdict:
    scenario_id: str
    verdict: GateVerdict  # worst of metric verdicts / verdict compare
    metrics: list[MetricVerdict] = field(default_factory=list)
    detail: str = ""


_WORST = {
    "pass": 0,
    "improvement": 0,
    "informative": 0,
    "changed": 1,
    "unknown": 1,
    "unmeasured": 1,
    "no-baseline": 1,
    "regression": 2,
}


def _spread(values: list[float]) -> float:
    return max(values) - min(values) if len(values) > 1 else 0.0


def _agg_metrics(
    results: list[tuple[BenchmarkResult, Any]],
) -> dict[str, list[MetricValue]]:
    grouped: dict[str, list[MetricValue]] = {}
    for _run, res in results:
        for name, m in res.metrics.items():
            grouped.setdefault(name, []).append(m)
    return grouped


def _compare_metric(
    name: str,
    base_metrics: list[MetricValue],
    cur_metrics: list[MetricValue],
    policy: GatePolicy,
) -> MetricVerdict:
    rule = policy.rule_for(name)
    direction = rule.direction or metric_direction(name)
    base_num = [v for v in (numeric_values(m) for m in base_metrics) if v is not None]
    cur_num = [v for v in (numeric_values(m) for m in cur_metrics) if v is not None]

    if not base_metrics or not cur_metrics:
        return MetricVerdict(name=name, verdict="unmeasured", direction=direction or "unknown")
    if not base_num or not cur_num:
        # non-numeric payloads: exact-string comparison only when the
        # metric is declared ``equal`` — otherwise we cannot gate it
        base_str = [m.value for m in base_metrics if m.measured and m.value is not None]
        cur_str = [m.value for m in cur_metrics if m.measured and m.value is not None]
        if not base_str or not cur_str:
            return MetricVerdict(name=name, verdict="unmeasured", direction=direction or "unknown")
        b, c = base_str[0], cur_str[0]
        if direction == "equal":
            return MetricVerdict(
                name=name,
                verdict="pass" if b == c else "regression",
                baseline=b,
                current=c,
                direction=direction,
            )
        return MetricVerdict(
            name=name,
            verdict="changed" if b != c else "pass",
            baseline=b,
            current=c,
            direction=direction or "unknown",
        )

    if direction is None:
        return MetricVerdict(
            name=name,
            verdict="unknown",
            baseline=median(base_num),
            current=median(cur_num),
        )

    b, c = median(base_num), median(cur_num)
    # tolerance: explicit policy > observed baseline spread > 0
    tol = rule.abs_tolerance
    if tol is None and rule.rel_tolerance is not None:
        tol = abs(b) * rule.rel_tolerance
    if tol is None:
        tol = _spread(base_num)

    delta = c - b
    if direction == "informative":
        verdict: GateVerdict = "informative"
    elif direction == "equal":
        verdict = "pass" if abs(delta) <= tol else "regression"
    elif direction == "higher_better":
        if delta < -tol:
            verdict = "regression"
        elif delta > tol:
            verdict = "improvement"
        else:
            verdict = "pass"
    else:  # lower_better
        if delta > tol:
            verdict = "regression"
        elif delta < -tol:
            verdict = "improvement"
        else:
            verdict = "pass"
    return MetricVerdict(
        name=name,
        verdict=verdict,
        baseline=b,
        current=c,
        tolerance=tol,
        direction=direction,
    )


def evaluate(
    current: list[BenchmarkResult],
    baseline: list[BenchmarkResult],
    policy: GatePolicy = DEFAULT_POLICY,
) -> dict[str, Any]:
    """Compare current receipts against baseline receipts.

    Returns a report dict: per-scenario verdicts, per-metric detail, and
    an overall gate verdict. ``fail`` requires at least one ``regression``
    — unmeasured/unknown/no-baseline are reported, never gated.
    """
    base_index: dict[tuple[str, str, str, str | None], list[tuple[BenchmarkResult, Any]]] = {}
    for run in baseline:
        for res in run.results:
            key = (run.forge, run.suite, res.scenario_id, run.subject)
            base_index.setdefault(key, []).append((run, res))

    scenarios: list[ScenarioVerdict] = []
    seen_current: set[tuple[str, str, str, str | None]] = set()
    for run in current:
        for res in run.results:
            key = (run.forge, run.suite, res.scenario_id, run.subject)
            if key in seen_current:
                continue
            seen_current.add(key)
            cur_pairs = [
                (r, x)
                for r in current
                for x in r.results
                if (r.forge, r.suite, x.scenario_id, r.subject) == key
            ]
            base_pairs = base_index.get(key, [])
            if not base_pairs:
                scenarios.append(
                    ScenarioVerdict(
                        scenario_id=res.scenario_id,
                        verdict="no-baseline",
                        detail=f"{key[0]}/{key[1]}/{res.scenario_id} subject={key[3]!r}",
                    )
                )
                continue
            base_verdicts = [x.verdict for _r, x in base_pairs]
            cur_verdicts = [x.verdict for _r, x in cur_pairs]
            if "pass" not in base_verdicts:
                scenarios.append(
                    ScenarioVerdict(
                        scenario_id=res.scenario_id,
                        verdict="no-baseline",
                        detail="baseline scenario never passed — cannot regress",
                    )
                )
                continue
            if "pass" not in cur_verdicts:
                scenarios.append(
                    ScenarioVerdict(
                        scenario_id=res.scenario_id,
                        verdict="regression",
                        detail="scenario verdict degraded below baseline",
                    )
                )
                continue
            base_metrics = _agg_metrics(base_pairs)
            cur_metrics = _agg_metrics(cur_pairs)
            verdicts = [
                _compare_metric(name, base_metrics.get(name, []), cur_metrics.get(name, []), policy)
                for name in sorted(set(base_metrics) | set(cur_metrics))
            ]
            worst = max(verdicts, key=lambda v: _WORST[v.verdict], default=None)
            scenarios.append(
                ScenarioVerdict(
                    scenario_id=res.scenario_id,
                    verdict=worst.verdict if worst else "pass",
                    metrics=verdicts,
                )
            )

    counts: dict[str, int] = {}
    for s in scenarios:
        counts[s.verdict] = counts.get(s.verdict, 0) + 1
    regressions = sum(
        1 for s in scenarios for m in s.metrics if m.verdict == "regression"
    ) + counts.get("regression", 0)
    return {
        "verdict": "fail" if regressions else "pass",
        "regressions": regressions,
        "scenarios": [
            {
                "scenario_id": s.scenario_id,
                "verdict": s.verdict,
                "detail": s.detail,
                "metrics": [
                    {
                        "name": m.name,
                        "verdict": m.verdict,
                        "baseline": m.baseline,
                        "current": m.current,
                        "tolerance": m.tolerance,
                        "direction": m.direction,
                    }
                    for m in s.metrics
                ],
            }
            for s in scenarios
        ],
        "counts": dict(sorted(counts.items())),
        "baseline_runs": len(baseline),
        "current_runs": len(current),
        "policy": policy.id,
        "taxonomy": sorted(STANDARD_METRICS),
    }
