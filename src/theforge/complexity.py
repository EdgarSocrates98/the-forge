"""Complexity engine: the deterministic measurement behind ``--profile auto``.

``assess`` scores the declared dimensions (repository spread, risk, routing
ambiguity, file impact, ...) into a weighted 0..1 score, maps it to a level
(trivial < low < medium < high < critical) and selects the effective budget
profile. Every input is measured evidence from the scan, the routing decision
and the provider manifests — never the prompt's length or phrasing. Dimensions
without evidence stay unmeasured: they cut ``confidence`` and are named in
``limitations`` instead of being guessed.

The policy is configuration, not code: ``[weights]``, ``[thresholds]`` and
``[profiles]`` live in ``complexity.toml`` next to ``policy.toml`` (user file
under the config dir, project file under ``.forge/config/``; the project file
overrides the user's — this is tuning, not a gate, so it is not tighten-only).
"""

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Final, Literal, cast

from theforge.context.scan import WorkspaceScan
from theforge.contracts import (
    ComplexityAssessment,
    ComplexityDimension,
    ComplexityLevel,
    Handoff,
    Producer,
    RiskDimensions,
    RoutingDecision,
    TaskSpec,
    WorkspaceDescriptor,
)
from theforge.contracts.canonical import utc_now
from theforge.contracts.types import BudgetProfile, ProfileRequest
from theforge.meta import PRODUCER
from theforge.policy import assess_dimensions
from theforge.profiles import PROFILES
from theforge.registry import RegistryRecord

CONFIG_FILE = "complexity.toml"

# Dimension names, in contract order. Weights are policy: these defaults are the
# built-in opinion and every key is overridable in complexity.toml.
DIMENSIONS: Final[tuple[str, ...]] = (
    "repositories", "technologies", "candidate_providers", "capabilities_matched",
    "file_impact", "dependency_depth", "cross_domain", "mutation_level",
    "external_systems", "security_sensitivity", "cross_account", "ambiguity",
    "required_verification", "estimated_context", "execution_cost",
)

DEFAULT_WEIGHTS: Final[Mapping[str, float]] = MappingProxyType({
    "mutation_level": 2.0,
    "security_sensitivity": 2.0,
    "external_systems": 1.5,
    "cross_account": 1.5,
    "repositories": 1.0,
    "technologies": 1.0,
    "candidate_providers": 1.0,
    "cross_domain": 1.0,
    "dependency_depth": 1.0,
    "ambiguity": 1.0,
    "required_verification": 1.0,
    "file_impact": 1.0,
    "capabilities_matched": 0.5,
    "estimated_context": 0.5,
    "execution_cost": 0.5,
})
# Upper bounds, exclusive: score < low -> trivial, < medium -> low, ... else critical.
DEFAULT_THRESHOLDS: Final[Mapping[str, float]] = MappingProxyType({
    "low": 0.20, "medium": 0.40, "high": 0.60, "critical": 0.80,
})
DEFAULT_PROFILE_MAP: Final[Mapping[ComplexityLevel, BudgetProfile]] = MappingProxyType({
    "trivial": "economy", "low": "economy", "medium": "balanced",
    "high": "max", "critical": "max",
})
DEFAULT_FALLBACK: Final[BudgetProfile] = "balanced"
DEFAULT_MIN_CONFIDENCE: Final = 0.5

# Reference points for the measured dimensions (the ``max`` profile bounds).
_MAX_PROFILE_FILES: Final = 256
_RISK_SCORE: Final[Mapping[str, float]] = MappingProxyType({
    "destructive": 1.0, "external_mutation": 0.7, "external_read": 0.5,
    "local_mutation": 0.4, "read_only": 0.0,
})


@dataclass(frozen=True)
class ComplexityConfig:
    """The resolved policy: defaults overlaid by the user and project files."""

    weights: Mapping[str, float]
    thresholds: Mapping[str, float]
    profile_map: Mapping[ComplexityLevel, BudgetProfile]
    fallback_profile: BudgetProfile
    min_confidence: float
    source: str  # "default" or the layers that contributed, e.g. "user+project"


@dataclass(frozen=True, kw_only=True)
class CandidateRisk:
    """Risk evidence for one routed candidate; ``dimensions`` None = manifest unknown."""

    provider: str
    capability: str
    rank_key: tuple[int, ...]
    dimensions: RiskDimensions | None


@dataclass(frozen=True, kw_only=True)
class ComplexityInputs:
    """Everything the engine measures from. ``None`` fields stay unmeasured."""

    task_id: str
    requested_profile: ProfileRequest = "auto"
    targets: int = 1
    files_scanned: int = 0
    candidates: tuple[CandidateRisk, ...] = ()
    routing_confidence: Literal["high", "low"] = "high"
    routing_unresolved: int = 0  # signals the router could not resolve
    repositories: int | None = None  # None = no workspace descriptor
    technologies: int | None = None
    handoff_items: int = 0
    upstream_nodes: int = 0  # distinct plan nodes this run consumes evidence from
    # Distinct providers the run may need (plan decomposition). A structural floor,
    # not a score: ``auto`` must never pick a profile that forbids the split.
    required_providers: int = 1


def _ladder(value: int, marks: tuple[tuple[int, float], ...]) -> float:
    """Score of ``value`` on a step ladder: the score of the highest reached mark."""
    score = 0.0
    for mark, mark_score in marks:
        if value >= mark:
            score = mark_score
    return score


def _worst_risk(candidates: tuple[CandidateRisk, ...], attr: str) -> str:
    """Worst declared level across candidates: yes > unknown > no (worst-first)."""
    levels = [getattr(c.dimensions, attr) for c in candidates if c.dimensions is not None]
    if not levels:
        return "no"
    for worst in ("yes", "unknown"):
        if worst in levels:
            return worst
    return "no"


def _measure(inputs: ComplexityInputs) -> dict[str, tuple[float | None, str]]:
    """Every dimension's (score, evidence); ``None`` score = not measured."""
    providers = {c.provider for c in inputs.candidates}
    declared = [c for c in inputs.candidates if c.dimensions is not None]
    families = {c.capability.split(".", 1)[0] for c in inputs.candidates}
    worst_class = "read_only"
    for name, score in _RISK_SCORE.items():
        if any(getattr(c.dimensions, name) == "yes" for c in declared) and (
                score >= _RISK_SCORE[worst_class]):
            worst_class = name
    ext_read = _worst_risk(inputs.candidates, "external_read")
    ext_mut = _worst_risk(inputs.candidates, "external_mutation")
    if "yes" in (ext_read, ext_mut):
        external = "yes"
    elif ("unknown" in (ext_read, ext_mut)
          or len(declared) < len(inputs.candidates)):
        external = "unknown"
    else:
        external = "no"
    credentials = _worst_risk(inputs.candidates, "credentials")
    cross_account = _worst_risk(inputs.candidates, "cross_account")
    ties = 0
    if inputs.candidates:
        top = min(c.rank_key for c in inputs.candidates)
        ties = sum(1 for c in inputs.candidates if c.rank_key == top) - 1
    ambiguity = (0.6 if inputs.routing_confidence == "low" else 0.1)
    ambiguity = min(1.0, ambiguity + 0.1 * inputs.routing_unresolved + 0.15 * ties)
    return {
        "repositories": (
            None if inputs.repositories is None else
            _ladder(inputs.repositories, ((1, 0.0), (2, 0.4), (3, 0.7), (4, 1.0))),
            "unknown: no workspace descriptor" if inputs.repositories is None else
            str(inputs.repositories)),
        "technologies": (
            None if inputs.technologies is None else min(1.0, inputs.technologies / 4),
            "unknown: no workspace descriptor" if inputs.technologies is None else
            str(inputs.technologies)),
        "candidate_providers": (
            min(1.0, max(0, len(providers) - 1) / 3), str(len(providers))),
        "capabilities_matched": (
            min(1.0, max(0, len(inputs.candidates) - 1) / 4), str(len(inputs.candidates))),
        # Breadth on either axis raises impact: a wide workspace to search or many
        # explicitly named targets to cover (16 targets saturate the dimension).
        "file_impact": (
            min(1.0, max(inputs.files_scanned / _MAX_PROFILE_FILES,
                         inputs.targets / 16)),
            f"{inputs.files_scanned} files, {inputs.targets} targets"),
        "dependency_depth": (min(1.0, inputs.upstream_nodes / 3),
                             f"{inputs.upstream_nodes} upstream nodes"),
        "cross_domain": (min(1.0, max(0, len(families) - 1) / 2),
                         f"{len(families)} families"),
        "mutation_level": (_RISK_SCORE[worst_class], worst_class),
        "external_systems": ({"yes": 1.0, "unknown": 0.3, "no": 0.0}[external], external),
        "security_sensitivity": (
            {"yes": 1.0, "unknown": 0.3, "no": 0.0}[credentials], credentials),
        "cross_account": ({"yes": 1.0, "unknown": 0.3, "no": 0.0}[cross_account],
                          cross_account),
        "ambiguity": (ambiguity,
                      f"{inputs.routing_confidence} confidence, "
                      f"{inputs.routing_unresolved} unresolved, {ties} ties"),
        "required_verification": (
            0.8 if _RISK_SCORE[worst_class] >= 0.7 else
            0.4 if _RISK_SCORE[worst_class] >= 0.4 else 0.1,
            f"derived from {worst_class}"),
        # Byte-accurate context cost needs the broker's selection; the scan only lists
        # files, so the v1 estimate stays unmeasured rather than guessed.
        "estimated_context": (None, "unknown: context bytes not estimated pre-broker"),
        "execution_cost": (
            min(1.0, inputs.files_scanned / (2 * _MAX_PROFILE_FILES)
                + len(providers) / 8 + inputs.handoff_items / 32),
            f"{inputs.files_scanned} files, {len(providers)} providers, "
            f"{inputs.handoff_items} handoff items"),
    }


def assess(inputs: ComplexityInputs, config: ComplexityConfig, *,
           producer: Producer = PRODUCER, created_at: str | None = None
           ) -> ComplexityAssessment:
    """Score the inputs, pick the level and resolve the effective profile."""
    measured = _measure(inputs)
    dimensions = [
        ComplexityDimension(name=name, score=measured[name][0],
                            weight=config.weights.get(name, 0.0), value=measured[name][1])
        for name in DIMENSIONS
    ]
    limitations: list[str] = []
    signals: list[str] = []
    measured_weight = total_weight = 0.0
    for dim in dimensions:
        total_weight += dim.weight
        if dim.score is None:
            if dim.weight > 0:
                limitations.append(f"{dim.name}: {dim.value}")
            continue
        measured_weight += dim.weight
        if dim.score >= 0.3:  # signals are the notable evidence, not every measure
            signals.append(f"{dim.name}={dim.value}")
    if any(c.dimensions is None for c in inputs.candidates):
        missing = sum(1 for c in inputs.candidates if c.dimensions is None)
        limitations.append(f"risk undeclared for {missing} candidate(s); "
                           "their dimensions scored as unknown")
    score = (sum(d.score * d.weight for d in dimensions if d.score is not None)
             / measured_weight if measured_weight else 0.0)
    confidence = measured_weight / total_weight if total_weight else 0.0
    thresholds = config.thresholds
    level: ComplexityLevel = "critical"
    for name, bound in (("low", "trivial"), ("medium", "low"),
                        ("high", "medium"), ("critical", "high")):
        if score < thresholds[name]:
            level = bound  # type: ignore[assignment]  # literal ladder
            break
    if confidence < config.min_confidence:
        selected = config.fallback_profile
        reason = (f"confidence {confidence:.2f} < {config.min_confidence:.2f} "
                  f"-> fallback {selected}")
    else:
        selected = config.profile_map[level]
        reason = f"level {level} -> {selected}"
    # Structural floor: the run needs ``required_providers`` seats; a profile that
    # allows fewer would silently degrade the work (decompose caps the split).
    if inputs.required_providers > PROFILES[selected].max_providers:
        raised: BudgetProfile = "max"
        for candidate_name in cast(tuple[BudgetProfile, ...],
                                   ("economy", "balanced", "max")):
            if PROFILES[candidate_name].max_providers >= inputs.required_providers:
                raised = candidate_name
                break
        reason += f"; {inputs.required_providers} providers required -> {raised}"
        selected = raised
        if inputs.required_providers > PROFILES["max"].max_providers:
            limitations.append(
                f"{inputs.required_providers} providers required; 'max' allows "
                f"{PROFILES['max'].max_providers}")
    return ComplexityAssessment(
        producer=producer, created_at=created_at or utc_now(), task_id=inputs.task_id,
        level=level, score=round(score, 4), confidence=round(confidence, 4),
        dimensions=dimensions, signals=sorted(signals),
        requested_profile=inputs.requested_profile, selected_profile=selected,
        profile_reason=reason, config_source=config.source, limitations=limitations)


def _read_config(path: Path, label: str, warnings: list[str]) -> dict[str, dict[str, object]]:
    """One complexity.toml as {table: {key: value}}; malformed keys warn, never raise."""
    try:
        raw = tomllib.loads(path.read_bytes().decode("utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, tomllib.TOMLDecodeError) as exc:
        warnings.append(f"{label} complexity {path}: unreadable ({exc}); defaults apply")
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, object]] = {"weights": {}, "thresholds": {}, "profiles": {}}
    for table, values in raw.items():
        if table not in out or not isinstance(values, dict):
            warnings.append(f"{label} complexity {path}: unknown table {table!r}; ignored")
            continue
        for key, value in values.items():
            out[table][key] = value
    return out


def _valid_weights(values: dict[str, object], label: str, path: Path,
                   warnings: list[str]) -> dict[str, float]:
    valid: dict[str, float] = {}
    for key, value in values.items():
        if key not in DIMENSIONS:
            warnings.append(f"{label} complexity {path}: unknown weight {key!r}; ignored")
        elif not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
            warnings.append(f"{label} complexity {path}: weight {key!r} must be a "
                            f"non-negative number; ignored")
        else:
            valid[key] = float(value)
    return valid


def _valid_thresholds(values: dict[str, object], label: str, path: Path,
                      warnings: list[str]) -> dict[str, float]:
    valid: dict[str, float] = {}
    for key, value in values.items():
        if key not in DEFAULT_THRESHOLDS:
            warnings.append(f"{label} complexity {path}: unknown threshold {key!r}; ignored")
        elif (not isinstance(value, (int, float)) or isinstance(value, bool)
                or not 0.0 < value < 1.0):
            warnings.append(f"{label} complexity {path}: threshold {key!r} must be a "
                            "number inside 0..1; ignored")
        else:
            valid[key] = float(value)
    merged = {**DEFAULT_THRESHOLDS, **valid}
    bounds = [merged[name] for name in ("low", "medium", "high", "critical")]
    if bounds != sorted(bounds):
        warnings.append(f"{label} complexity {path}: thresholds are not ordered "
                        f"({bounds}); the whole table is ignored")
        return {}
    return valid


def _valid_profiles(values: dict[str, object], label: str, path: Path,
                    warnings: list[str]) -> dict[str, object]:
    valid: dict[str, object] = {}
    for key, value in values.items():
        if key in (*DEFAULT_PROFILE_MAP, "fallback"):
            if value not in ("economy", "balanced", "max"):
                warnings.append(f"{label} complexity {path}: profile {key!r} must be a "
                                "budget profile; ignored")
            else:
                valid[key] = value
        elif key == "min_confidence":
            if (not isinstance(value, (int, float)) or isinstance(value, bool)
                    or not 0.0 <= value <= 1.0):
                warnings.append(f"{label} complexity {path}: min_confidence must be a "
                                "number inside 0..1; ignored")
            else:
                valid[key] = float(value)
        else:
            warnings.append(f"{label} complexity {path}: unknown profile key {key!r}; "
                            "ignored")
    return valid


def load_complexity_config(*, user_dir: Path, forge_dir: Path,
                           warnings: list[str]) -> ComplexityConfig:
    """Merge defaults, the user file and the project file (project wins per key).

    Missing files keep the defaults; problems are appended to ``warnings`` and never
    raise — a broken complexity policy must not stop a run.
    """
    weights = dict(DEFAULT_WEIGHTS)
    thresholds = dict(DEFAULT_THRESHOLDS)
    profile_map: dict[ComplexityLevel, BudgetProfile] = dict(DEFAULT_PROFILE_MAP)
    fallback: BudgetProfile = DEFAULT_FALLBACK
    min_confidence = DEFAULT_MIN_CONFIDENCE
    contributed: list[str] = []
    for path, label in ((user_dir / CONFIG_FILE, "user"),
                        (forge_dir / "config" / CONFIG_FILE, "project")):
        tables = _read_config(path, label, warnings)
        changed = False
        for key, value in _valid_weights(tables.get("weights", {}), label, path,
                                         warnings).items():
            weights[key] = value
            changed = True
        for key, value in _valid_thresholds(tables.get("thresholds", {}), label, path,
                                            warnings).items():
            thresholds[key] = value
            changed = True
        for key, raw in _valid_profiles(tables.get("profiles", {}), label, path,
                                        warnings).items():
            if key == "fallback":
                fallback = cast(BudgetProfile, raw)
            elif key == "min_confidence":
                min_confidence = cast(float, raw)
            else:
                profile_map[cast(ComplexityLevel, key)] = cast(BudgetProfile, raw)
            changed = True
        if changed:
            contributed.append(label)
    return ComplexityConfig(
        weights=MappingProxyType(weights), thresholds=MappingProxyType(thresholds),
        profile_map=MappingProxyType(profile_map), fallback_profile=fallback,
        min_confidence=min_confidence,
        source="+".join(contributed) if contributed else "default")


def candidate_risks(decision: RoutingDecision,
                    records: Mapping[str, RegistryRecord]) -> tuple[CandidateRisk, ...]:
    """Risk evidence per routed candidate: declared dims, or None when the manifest
    (or the capability on it) is unknown — ``assess`` then scores it as unknown."""
    out: list[CandidateRisk] = []
    for candidate in decision.candidates:
        record = records.get(candidate.provider)
        dims = None
        if record is not None and record.manifest is not None:
            resolved = record.manifest.resolve(candidate.capability)
            capability = resolved[0] if resolved else None
            if capability is not None:
                dims = assess_dimensions(operation_class=capability.operation_class,
                                         execution=record.manifest.execution)
        out.append(CandidateRisk(provider=candidate.provider,
                                 capability=candidate.capability,
                                 rank_key=tuple(candidate.rank_key), dimensions=dims))
    return tuple(out)


def upstream_fan_in(handoff: Handoff | None) -> tuple[int, int]:
    """(distinct upstream nodes, items) of a plan-node handoff; (0, 0) without one."""
    if handoff is None:
        return 0, 0
    nodes = {item.origin.node for item in handoff.items}
    return len(nodes), len(handoff.items)


def task_inputs(task: TaskSpec, scan: WorkspaceScan, decision: RoutingDecision,
                records: Mapping[str, RegistryRecord], *,
                descriptor: WorkspaceDescriptor | None = None,
                handoff: Handoff | None = None,
                decomposable: bool = False) -> ComplexityInputs:
    """Build the engine's inputs from the run's measured evidence (nothing else).

    ``decomposable`` marks a plan run: the distinct providers among the routed
    candidates become the structural ``required_providers`` floor.
    """
    upstream, items = upstream_fan_in(handoff)
    candidates = candidate_risks(decision, records)
    return ComplexityInputs(
        task_id=task.id, requested_profile=task.budget_profile,
        targets=len(task.targets), files_scanned=len(scan.files),
        candidates=candidates,
        routing_confidence=decision.confidence.level,
        routing_unresolved=len(decision.confidence.unresolved),
        repositories=len(descriptor.repositories) if descriptor is not None else None,
        technologies=len(descriptor.technologies) if descriptor is not None else None,
        handoff_items=items, upstream_nodes=upstream,
        required_providers=(len({c.provider for c in candidates})
                            if decomposable else 1))
