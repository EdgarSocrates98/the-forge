"""Benchmark contracts: federated lab suites and results.

Cycle 9 (ecosystem-2026 program, ADR-0060): specialist forges own their
benchmark engines; the core owns only the wire shape they report on.
``forge/BenchmarkSuite/v1`` declares a versioned scenario set; each
specialist lab emits ``forge/BenchmarkResult/v1`` receipts that the
federated collector (``theforge.lab``) validates and aggregates.

Metrics are declared data, not evidence: the contract carries a
``name -> {value, unit}`` map so cross-domain numbers are never blended —
comparison happens per scenario, never across domains.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from theforge.contracts.base import ContractError, from_dict, to_dict
from theforge.contracts.types import Producer

SUITE_SCHEMA = "forge/BenchmarkSuite/v1"
RESULT_SCHEMA = "forge/BenchmarkResult/v1"

SUITE_ID_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$", re.ASCII)
FORGE_ID_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$", re.ASCII)
SCENARIO_ID_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$", re.ASCII)
METRIC_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)*$", re.ASCII)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$", re.ASCII)
TIMESTAMP_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(Z|[+-][0-9]{2}:[0-9]{2})$",
    re.ASCII,
)
LabMode = Literal["A", "B", "C"]
Verdict = Literal["pass", "fail", "error", "skipped"]
MetricState = Literal["measured", "not_available", "not_applicable"]
GateDirection = Literal["higher_better", "lower_better", "equal", "informative"]

# §9.5 canonical metric names (dotted suffixes allowed, e.g.
# ``precision.api``). ``direction`` drives regression gates —
# ``informative`` metrics are reported but never gate on their own.
STANDARD_METRICS: dict[str, str] = {
    "duration_ms": "lower_better",
    "tokens": "lower_better",
    "cost_usd": "lower_better",
    "tool_calls": "lower_better",
    "handoffs": "lower_better",
    "handoff_cost_ms": "lower_better",
    "context_bytes": "lower_better",
    "duplication_ratio": "lower_better",
    "success": "higher_better",
    "test_pass_rate": "higher_better",
    "precision": "higher_better",
    "recall": "higher_better",
    "false_positives": "lower_better",
    "evidence_coverage": "higher_better",
    "reproducibility_rate": "higher_better",
    "components_matched": "higher_better",
    "components_total": "informative",  # denominator — reported, never gated
    "transported_context_bytes": "lower_better",
    "routing_failures": "lower_better",
    "re_executions": "lower_better",
    "labs_invoked": "informative",  # environment-dependent count
    "participants_declared": "informative",
    "participants_present": "higher_better",
    "receipt_integrity": "higher_better",
}


def metric_direction(name: str) -> GateDirection | None:
    """Direction of a standard metric; ``None`` for names outside §9.5 —
    unknown metrics never gate, they are reported as ``unknown``."""
    if name in STANDARD_METRICS:
        return STANDARD_METRICS[name]  # type: ignore[return-value]
    base = name.split(".", 1)[0]
    if base in STANDARD_METRICS:
        return STANDARD_METRICS[base]  # type: ignore[return-value]
    return None


def _check_rel_path(path: str, *, what: str) -> None:
    """Scenario/evidence references are repo-relative — never absolute,
    never escaping (ground truth is referenced, not copied)."""
    if not path or path.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", path):
        raise ContractError(f"benchmark: {what} must be a relative path, got {path!r}")
    if any(part == ".." for part in re.split(r"[/\\]", path)):
        raise ContractError(f"benchmark: {what} must not escape the repo, got {path!r}")


@dataclass(frozen=True, kw_only=True)
class LabScenario:
    """One versioned scenario owned by a specialist lab.

    ``sha256`` pins the ground-truth fixture when declared — the collector
    references by path+hash, never copies content into the core.
    """

    id: str
    path: str
    sha256: str | None = None
    mode: LabMode = "A"

    def __post_init__(self) -> None:
        if not SCENARIO_ID_RE.fullmatch(self.id):
            raise ContractError(f"benchmark: bad scenario id {self.id!r}")
        _check_rel_path(self.path, what=f"scenario {self.id!r} path")
        if self.sha256 is not None and not SHA256_RE.fullmatch(self.sha256):
            raise ContractError(
                f"benchmark: scenario {self.id!r} sha256 must be 64-hex, got {self.sha256!r}"
            )


@dataclass(frozen=True, kw_only=True)
class BenchmarkSuite:
    """``forge/BenchmarkSuite/v1`` — a specialist lab's declared scenario set."""

    schema: str = SUITE_SCHEMA
    id: str
    owner_forge: str
    created_at: str
    source: str  # where the suite is declared (e.g. "labs/suite.json")
    scenarios: list[LabScenario]
    mode: LabMode = "A"
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != SUITE_SCHEMA:
            raise ContractError(
                f"benchmark suite: unsupported schema {self.schema!r}, expected {SUITE_SCHEMA!r}"
            )
        if not SUITE_ID_RE.fullmatch(self.id):
            raise ContractError(f"benchmark suite: bad suite id {self.id!r}")
        if not FORGE_ID_RE.fullmatch(self.owner_forge):
            raise ContractError(f"benchmark suite: bad owner_forge {self.owner_forge!r}")
        if not DATE_RE.fullmatch(self.created_at):
            raise ContractError(
                f"benchmark suite: created_at must be ISO date, got {self.created_at!r}"
            )
        _check_rel_path(self.source, what="source")
        if not self.scenarios:
            raise ContractError("benchmark suite: scenarios must not be empty")
        ids = [s.id for s in self.scenarios]
        if len(set(ids)) != len(ids):
            raise ContractError("benchmark suite: duplicate scenario ids")
        for s in self.scenarios:
            if s.mode == "C" and self.mode != "C":
                raise ContractError(
                    f"benchmark suite: scenario {s.id!r} is mode C but suite mode is {self.mode}"
                )


@dataclass(frozen=True, kw_only=True)
class MetricValue:
    """One metric datum: ``measured`` carries ``value``; ``not_available``
    (the lab tried, could not measure) and ``not_applicable`` (does not
    apply to this scenario) carry none — unknown is never a zero (§9.5)."""

    value: int | float | str | None = None
    unit: str = ""
    state: MetricState = "measured"

    def __post_init__(self) -> None:
        if self.state == "measured":
            if self.value is None:
                raise ContractError("metric: state 'measured' requires a value")
        elif self.value is not None:
            raise ContractError(f"metric: state {self.state!r} must not carry a value")

    @property
    def measured(self) -> bool:
        return self.state == "measured"


@dataclass(frozen=True, kw_only=True)
class JudgeDeclaration:
    """LLM-as-judge registration (§9.8): mandatory whenever a judge scores
    a scenario — model, rubric reference, human-validated sample count and
    declared limitations travel with the receipt."""

    model: str
    rubric: str
    human_validated_samples: int | None = None
    limitations: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.model:
            raise ContractError("judge: model is required")
        if not self.rubric:
            raise ContractError("judge: rubric reference is required")
        if self.human_validated_samples is not None and self.human_validated_samples < 0:
            raise ContractError("judge: human_validated_samples must be >= 0")


@dataclass(frozen=True, kw_only=True)
class ScenarioResult:
    """Outcome of one scenario run: verdict + metrics + evidence reference.

    ``evidence_ref`` points at the specialist's own receipt (relative path
    or locator) — the core stores the reference, not the payload.
    """

    scenario_id: str
    verdict: Verdict
    metrics: dict[str, MetricValue] = field(default_factory=dict)
    duration_ms: int | None = None
    evidence_ref: str = ""
    detail: str = ""
    judge: JudgeDeclaration | None = None

    def __post_init__(self) -> None:
        if not SCENARIO_ID_RE.fullmatch(self.scenario_id):
            raise ContractError(f"benchmark result: bad scenario id {self.scenario_id!r}")
        if self.duration_ms is not None and self.duration_ms < 0:
            raise ContractError("benchmark result: duration_ms must be >= 0")
        for name in self.metrics:
            if not METRIC_NAME_RE.fullmatch(name):
                raise ContractError(f"benchmark result: bad metric name {name!r}")
        # a locator URI (ctx://, file://, lab://…) or a repo-relative
        # path — never an absolute filesystem path, never escaping
        if self.evidence_ref and not re.match(r"^[a-z][a-z0-9+.-]*://", self.evidence_ref):
            _check_rel_path(self.evidence_ref, what="evidence_ref")


@dataclass(frozen=True, kw_only=True)
class BenchmarkResult:
    """``forge/BenchmarkResult/v1`` — one lab run receipt (a suite, a mode)."""

    schema: str = RESULT_SCHEMA
    suite: str
    forge: str
    mode: LabMode
    created_at: str
    producer: Producer
    results: list[ScenarioResult]
    external: bool = False
    subject: str | None = None  # model/toolchain under test — separates
    # model variation from infra variation (§9.7); comparisons only pair
    # equal subjects
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != RESULT_SCHEMA:
            raise ContractError(
                f"benchmark result: unsupported schema {self.schema!r}, expected {RESULT_SCHEMA!r}"
            )
        if not SUITE_ID_RE.fullmatch(self.suite):
            raise ContractError(f"benchmark result: bad suite id {self.suite!r}")
        if not FORGE_ID_RE.fullmatch(self.forge):
            raise ContractError(f"benchmark result: bad forge id {self.forge!r}")
        if not TIMESTAMP_RE.fullmatch(self.created_at):
            raise ContractError(
                f"benchmark result: created_at must be ISO timestamp, got {self.created_at!r}"
            )
        if self.external != (self.mode == "C"):
            raise ContractError(
                f"benchmark result: external={self.external} inconsistent with "
                f"mode {self.mode} — external is required exactly for mode C"
            )
        ids = [r.scenario_id for r in self.results]
        if len(set(ids)) != len(ids):
            raise ContractError("benchmark result: duplicate scenario ids")


MULTIFORGE_SCHEMA = "forge/MultiForgeScenario/v1"


@dataclass(frozen=True, kw_only=True)
class MultiForgeScenario:
    """``forge/MultiForgeScenario/v1`` — a versioned scenario exercising
    composition across >= 2 forges (cyc9-03, §9.3/§9.4).

    ``participants`` carries real forge ids; ``expected`` declares the
    checkable expectations (presence, lab declarations, minimum ok runs)
    so the runner verifies composition instead of asserting it.
    """

    schema: str = MULTIFORGE_SCHEMA
    id: str
    title: str
    intent: str
    participants: list[str]
    expected: dict[str, Any] = field(default_factory=dict)
    mode: LabMode = "A"
    ground_truth: str | None = None
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != MULTIFORGE_SCHEMA:
            raise ContractError(f"multiforge scenario: unsupported schema {self.schema!r}")
        if not SCENARIO_ID_RE.fullmatch(self.id):
            raise ContractError(f"multiforge scenario: bad id {self.id!r}")
        if len(self.participants) < 2:
            raise ContractError(
                "multiforge scenario: at least 2 participants required — "
                "a single-specialist scenario is not multi-forge"
            )
        if len(set(self.participants)) != len(self.participants):
            raise ContractError("multiforge scenario: duplicate participants")
        for fid in self.participants:
            if not FORGE_ID_RE.fullmatch(fid):
                raise ContractError(f"multiforge scenario: bad participant id {fid!r}")
        if self.ground_truth is not None:
            _check_rel_path(self.ground_truth, what="ground_truth")


def parse_multiforge_scenario(data: Any, *, strict: bool = False) -> MultiForgeScenario:
    return from_dict(MultiForgeScenario, data, strict=strict)


def load_multiforge_scenario(path: Path) -> MultiForgeScenario:
    return parse_multiforge_scenario(json.loads(path.read_text(encoding="utf-8")), strict=True)


def parse_suite(data: Any, *, strict: bool = False) -> BenchmarkSuite:
    return from_dict(BenchmarkSuite, data, strict=strict)


def parse_result(data: Any, *, strict: bool = False) -> BenchmarkResult:
    return from_dict(BenchmarkResult, data, strict=strict)


def load_suite(path: Path) -> BenchmarkSuite:
    return parse_suite(json.loads(path.read_text(encoding="utf-8")), strict=True)


def load_result(path: Path) -> BenchmarkResult:
    return parse_result(json.loads(path.read_text(encoding="utf-8")), strict=True)


def dump_suite(suite: BenchmarkSuite) -> dict[str, Any]:
    return to_dict(suite)


def dump_result(result: BenchmarkResult) -> dict[str, Any]:
    return to_dict(result)
