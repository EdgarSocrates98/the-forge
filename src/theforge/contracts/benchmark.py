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
    """One measured value with its unit — the denominator is part of the data."""

    value: int | float | str
    unit: str = ""


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
