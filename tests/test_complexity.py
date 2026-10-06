"""Cycle 3 wave A: ComplexityAssessment/v1 and the deterministic complexity engine.

The engine measures declared dimensions (repositories, risk, ambiguity, impact)
into a weighted score, maps it to a level and resolves the effective profile for
``--profile auto``. Unmeasured dimensions cut confidence, never get guessed;
the prompt's length or wording is never an input.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from helpers import API_ENTRY, SPARK_ENTRY, case_a, make_workspace
from theforge.complexity import (
    DIMENSIONS,
    CandidateRisk,
    ComplexityInputs,
    assess,
    load_complexity_config,
    task_inputs,
)
from theforge.contracts import (
    ComplexityAssessment,
    ContractError,
    ExecutionReceipt,
    RunTelemetry,
    from_dict,
    to_dict,
)
from theforge.contracts.canonical import utc_now
from theforge.forger import AskRequest, Forger
from theforge.meta import PRODUCER
from theforge.policy import assess_dimensions
from theforge.registry import Registry
from theforge.runs import RunStore


def _dims(op: str, *, network: bool = False) -> Any:
    from theforge.contracts import ExecutionInfo
    return assess_dimensions(operation_class=op,  # type: ignore[arg-type]
                             execution=ExecutionInfo(requires_network=network))


def _risk(op: str, provider: str = "p", capability: str = "cap.x", *,
          rank: tuple[int, ...] = (1,), network: bool = False) -> CandidateRisk:
    return CandidateRisk(provider=provider, capability=capability, rank_key=rank,
                         dimensions=_dims(op, network=network))


def _config(tmp_path: Path, *, project: str = "", user: str = "") -> Any:
    user_dir = tmp_path / "user"
    forge_dir = tmp_path / "repo" / ".forge"
    if user:
        user_dir.mkdir(parents=True, exist_ok=True)
        (user_dir / "complexity.toml").write_text(user, encoding="utf-8")
    if project:
        (forge_dir / "config").mkdir(parents=True, exist_ok=True)
        (forge_dir / "config" / "complexity.toml").write_text(project, encoding="utf-8")
    warnings: list[str] = []
    config = load_complexity_config(user_dir=user_dir, forge_dir=forge_dir,
                                    warnings=warnings)
    return config, warnings


def _score(assessment: ComplexityAssessment, name: str) -> float | None:
    return next(d.score for d in assessment.dimensions if d.name == name)


class TestDimensions:
    def test_all_declared_dimensions_present(self, tmp_path: Path) -> None:
        config, _ = _config(tmp_path)
        a = assess(ComplexityInputs(task_id="t"), config)
        assert [d.name for d in a.dimensions] == list(DIMENSIONS)

    def test_trivial_single_repo_read_only(self, tmp_path: Path) -> None:
        config, _ = _config(tmp_path)
        a = assess(ComplexityInputs(
            task_id="t", files_scanned=3, candidates=(_risk("read_only"),),
            repositories=1, technologies=1), config)
        assert a.level == "trivial"
        assert a.selected_profile == "economy"
        # The one permanent limitation: context bytes are unknowable pre-broker.
        assert a.limitations == [
            "estimated_context: unknown: context bytes not estimated pre-broker"]

    def test_critical_destructive_multi_repo(self, tmp_path: Path) -> None:
        config, _ = _config(tmp_path)
        a = assess(ComplexityInputs(
            task_id="t", files_scanned=600, repositories=5, technologies=6,
            routing_confidence="low", routing_unresolved=3,
            candidates=(_risk("destructive", "a", "x.y", rank=(1,)),
                        _risk("external_mutation", "b", "z.w", rank=(1,)),
                        _risk("read_only", "c", "q.r", rank=(2,))),
        ), config)
        assert a.level in ("high", "critical")
        assert a.selected_profile == "max"
        assert _score(a, "mutation_level") == 1.0
        assert _score(a, "cross_domain") == 1.0

    def test_unmeasured_dimensions_cut_confidence(self, tmp_path: Path) -> None:
        config, _ = _config(tmp_path)
        measured = assess(ComplexityInputs(
            task_id="t", files_scanned=3, candidates=(_risk("read_only"),),
            repositories=1, technologies=1), config)
        unmeasured = assess(ComplexityInputs(
            task_id="t", files_scanned=3, candidates=(_risk("read_only"),)), config)
        assert unmeasured.confidence < measured.confidence
        assert any("repositories" in lim for lim in unmeasured.limitations)
        assert _score(unmeasured, "repositories") is None

    def test_estimated_context_never_guessed(self, tmp_path: Path) -> None:
        config, _ = _config(tmp_path)
        a = assess(ComplexityInputs(task_id="t"), config)
        assert _score(a, "estimated_context") is None
        assert any("estimated_context" in lim for lim in a.limitations)

    def test_candidate_without_manifest_is_unknown_risk(self, tmp_path: Path) -> None:
        config, _ = _config(tmp_path)
        a = assess(ComplexityInputs(
            task_id="t", candidates=(
                CandidateRisk(provider="ghost", capability="x.y", rank_key=(1,),
                              dimensions=None),)), config)
        assert _score(a, "security_sensitivity") is not None  # scored as "unknown"
        assert any("risk undeclared" in lim for lim in a.limitations)

    def test_ambiguity_from_routing(self, tmp_path: Path) -> None:
        config, _ = _config(tmp_path)
        tied = (_risk("read_only", "a", rank=(1,)), _risk("read_only", "b", rank=(1,)))
        a = assess(ComplexityInputs(task_id="t", routing_confidence="low",
                                    routing_unresolved=2, candidates=tied), config)
        assert _score(a, "ambiguity") == pytest.approx(0.6 + 0.2 + 0.15)

    def test_dependency_depth_from_handoff_fan_in(self, tmp_path: Path) -> None:
        config, _ = _config(tmp_path)
        a = assess(ComplexityInputs(task_id="t", upstream_nodes=3, handoff_items=9),
                   config)
        assert _score(a, "dependency_depth") == 1.0
        assert _score(a, "execution_cost") > 0

    def test_prompt_text_is_not_an_input(self) -> None:
        fields = ComplexityInputs.__dataclass_fields__
        assert "intent" not in fields and "prompt" not in fields
        assert "description" not in fields


class TestProviderFloor:
    """``required_providers`` is structural: a plan needing N providers must not
    resolve to a profile that forbids the split (decompose caps at max_providers)."""

    def test_two_providers_raise_economy_to_max(self, tmp_path: Path) -> None:
        config, _ = _config(tmp_path)
        a = assess(ComplexityInputs(
            task_id="t", files_scanned=3, repositories=1, technologies=1,
            required_providers=2,
            candidates=(_risk("read_only", "a"), _risk("read_only", "b", "x.z"))),
            config)
        assert a.level == "trivial"  # the work is simple; the SHAPE is not
        assert a.selected_profile == "max"
        assert "2 providers required -> max" in a.profile_reason

    def test_floor_respects_fallback(self, tmp_path: Path) -> None:
        config, _ = _config(tmp_path, user="[profiles]\nmin_confidence = 0.99\n")
        a = assess(ComplexityInputs(task_id="t", required_providers=2,
                                    candidates=(_risk("read_only", "a"),
                                                _risk("read_only", "b", "x.z"))),
                   config)
        assert a.confidence < 0.99  # fallback path, then floored up
        assert a.selected_profile == "max"

    def test_required_beyond_max_is_capped_and_named(self, tmp_path: Path) -> None:
        config, _ = _config(tmp_path)
        a = assess(ComplexityInputs(task_id="t", required_providers=6,
                                    candidates=(_risk("read_only"),)), config)
        assert a.selected_profile == "max"
        assert any("6 providers required" in lim for lim in a.limitations)


class TestLevels:
    def test_level_boundaries(self, tmp_path: Path) -> None:
        config, _ = _config(tmp_path)
        # Zero the weights of all but one dimension to control the score exactly.
        for bound, expected in ((0.19, "trivial"), (0.21, "low"), (0.39, "low"),
                                (0.41, "medium"), (0.59, "medium"), (0.61, "high"),
                                (0.79, "high"), (0.81, "critical")):
            weights = dict(config.weights)
            weights["file_impact"] = 1.0
            for name in DIMENSIONS:
                if name != "file_impact":
                    weights[name] = 0.0
            config2 = type(config)(weights=weights, thresholds=config.thresholds,
                                   profile_map=config.profile_map,
                                   fallback_profile=config.fallback_profile,
                                   min_confidence=0.0, source="test")
            files = round(bound * 256)
            a = assess(ComplexityInputs(task_id="t", files_scanned=files), config2)
            assert a.score == pytest.approx(min(1.0, files / 256), abs=0.004)
            assert a.level == expected, f"score {a.score} bound {bound}"


class TestPolicy:
    def test_min_confidence_fallback(self, tmp_path: Path) -> None:
        config, _ = _config(tmp_path, user="[profiles]\nmin_confidence = 0.95\n")
        a = assess(ComplexityInputs(task_id="t", files_scanned=3,
                                    candidates=(_risk("read_only"),)), config)
        assert a.confidence < 0.95
        assert a.selected_profile == "balanced"
        assert "fallback" in a.profile_reason

    def test_profile_map_override(self, tmp_path: Path) -> None:
        config, _ = _config(tmp_path,
                            project='[profiles]\ntrivial = "balanced"\nmedium = "max"\n')
        a = assess(ComplexityInputs(
            task_id="t", files_scanned=3, candidates=(_risk("read_only"),),
            repositories=1, technologies=1), config)
        assert a.selected_profile == "balanced"  # trivial remapped by the project
        assert a.config_source == "project"

    def test_project_overrides_user_per_key(self, tmp_path: Path) -> None:
        config, _ = _config(tmp_path,
                            user='[weights]\nmutation_level = 9.0\n',
                            project='[weights]\nmutation_level = 0.5\n')
        assert config.weights["mutation_level"] == 0.5
        assert config.source == "user+project"

    def test_invalid_values_warn_never_raise(self, tmp_path: Path) -> None:
        config, warnings = _config(tmp_path, project=(
            '[weights]\nmutation_level = -1\nbogus_dim = 5\n'
            '[thresholds]\nlow = 0.9\nhigh = 0.1\n'
            '[profiles]\ntrivial = "ludicrous"\nunknown_key = 1\n'))
        assert config.weights["mutation_level"] == 2.0  # default kept
        assert config.thresholds["low"] == 0.20  # unordered table ignored
        assert len(warnings) >= 5

    def test_malformed_toml_warns_and_defaults(self, tmp_path: Path) -> None:
        config, warnings = _config(tmp_path, project="[weights\nbroken")
        assert config.source == "default"
        assert any("unreadable" in w for w in warnings)

    def test_weight_zero_disables_dimension(self, tmp_path: Path) -> None:
        config, _ = _config(tmp_path, project='[weights]\nfile_impact = 0\n')
        a = assess(ComplexityInputs(task_id="t", files_scanned=256), config)
        dim = next(d for d in a.dimensions if d.name == "file_impact")
        assert dim.weight == 0.0


class TestInputs:
    """``task_inputs`` wiring: real contracts in, measured engine inputs out."""

    def _decision(self, providers: tuple[str, ...]) -> Any:
        from theforge.contracts import Confidence, RoutingDecision
        from theforge.contracts.routing import Candidate, Selection
        return RoutingDecision(
            producer=PRODUCER, created_at=utc_now(), status="routed", task_id="t",
            reason="test", confidence=Confidence(level="high"),
            selected=[Selection(provider=providers[0], capability="cap.x",
                                action="run")],
            candidates=[Candidate(provider=p, capability="cap.x",
                                  rank_key=[1]) for p in providers])

    def _task(self, **kw: Any) -> Any:
        from theforge.contracts import TaskSpec
        return TaskSpec(producer=PRODUCER, created_at=utc_now(), id="t",
                        intent="do it", workspace_root=".", **kw)

    def test_ask_run_never_requires_more_than_one_provider(self, tmp_path: Path) -> None:
        from theforge.context.scan import WorkspaceScan
        task = self._task(budget_profile="auto")
        scan = WorkspaceScan(root=tmp_path, files=[], excluded=[])
        inputs = task_inputs(task, scan, self._decision(("a", "b")), {})
        assert inputs.required_providers == 1  # ask executes a single provider

    def test_decomposable_run_floors_on_distinct_providers(self, tmp_path: Path) -> None:
        from theforge.context.scan import WorkspaceScan
        task = self._task(budget_profile="auto")
        scan = WorkspaceScan(root=tmp_path, files=[], excluded=[])
        inputs = task_inputs(task, scan, self._decision(("a", "b", "a")), {},
                             decomposable=True)
        assert inputs.required_providers == 2

    def test_candidates_without_manifest_keep_none_dimensions(self, tmp_path: Path) -> None:
        from theforge.context.scan import WorkspaceScan
        task = self._task()
        scan = WorkspaceScan(root=tmp_path, files=[], excluded=[])
        inputs = task_inputs(task, scan, self._decision(("ghost",)), {})
        assert inputs.candidates[0].dimensions is None


class TestContract:
    def _valid(self, **overrides: Any) -> ComplexityAssessment:
        fields = {"producer": PRODUCER, "created_at": utc_now(), "task_id": "t",
                  "level": "low", "score": 0.3, "confidence": 0.8,
                  "selected_profile": "economy", **overrides}
        return ComplexityAssessment(**fields)  # type: ignore[arg-type]

    def test_round_trip(self) -> None:
        a = self._valid(signals=["mutation_level=external_mutation"])
        assert from_dict(ComplexityAssessment, to_dict(a), "$") == a

    def test_score_out_of_range(self) -> None:
        with pytest.raises(ContractError):
            self._valid(score=1.5)

    def test_bad_level(self) -> None:
        with pytest.raises(ContractError):
            self._valid(level="spicy")  # type: ignore[arg-type]

    def test_bad_selected_profile(self) -> None:
        with pytest.raises(ContractError):
            self._valid(selected_profile="ludicrous")  # type: ignore[arg-type]


class TestOrchestrator:
    """``--profile auto`` end to end: assessment persisted, hash-linked, applied."""

    def _forger(self, root: Path) -> tuple[Forger, RunStore]:
        forge = root / ".forge"
        store = RunStore(forge)
        return Forger(root, Registry(forge), store), store

    def test_auto_resolves_and_persists(self, tmp_path: Path) -> None:
        make_workspace(tmp_path, [SPARK_ENTRY, API_ENTRY])
        case_a(tmp_path)
        forger, store = self._forger(tmp_path)
        outcome = forger.ask(AskRequest(intent="avalie o glue job", targets=["jobs"],
                                      capability="spark.performance"))
        assert outcome.status in ("ok", "partial")
        raw = store.read_optional(outcome.run_id, "complexity")
        assert raw is not None
        assessment = from_dict(ComplexityAssessment, raw, "$")
        assert assessment.requested_profile == "auto"
        assert assessment.selected_profile in ("economy", "balanced", "max")
        assert assessment.level in ("trivial", "low", "medium", "high", "critical")
        # The receipt binds the assessment; telemetry records the resolved profile.
        receipt = store.read_contract(outcome.run_id, "receipt", ExecutionReceipt)
        assert receipt.inputs.complexity_sha256 is not None
        telemetry = store.read_contract(outcome.run_id, "telemetry", RunTelemetry)
        assert telemetry.profile.name == assessment.selected_profile

    def test_explicit_profile_skips_assessment(self, tmp_path: Path) -> None:
        make_workspace(tmp_path, [SPARK_ENTRY])
        case_a(tmp_path)
        forger, store = self._forger(tmp_path)
        outcome = forger.ask(AskRequest(intent="avalie o glue job", targets=["jobs"],
                                      capability="spark.performance",
                                      profile="balanced"))
        assert outcome.status in ("ok", "partial")
        assert store.read_optional(outcome.run_id, "complexity") is None
        receipt = store.read_contract(outcome.run_id, "receipt", ExecutionReceipt)
        assert receipt.inputs.complexity_sha256 is None

    def test_no_route_writes_no_assessment(self, tmp_path: Path) -> None:
        make_workspace(tmp_path, [SPARK_ENTRY])
        forger, store = self._forger(tmp_path)
        outcome = forger.ask(AskRequest(intent="nothing routable at all"))
        assert outcome.status == "no_route"
        assert store.read_optional(outcome.run_id, "complexity") is None
        # The assumed (fallback) profile is what telemetry can honestly report.
        telemetry = store.read_contract(outcome.run_id, "telemetry", RunTelemetry)
        assert telemetry.profile.name == "balanced"

    def test_task_records_auto_verbatim(self, tmp_path: Path) -> None:
        make_workspace(tmp_path, [SPARK_ENTRY])
        case_a(tmp_path)
        forger, store = self._forger(tmp_path)
        outcome = forger.ask(AskRequest(intent="x", targets=["jobs"],
                                      capability="spark.performance"))
        task = store.read_contract(outcome.run_id, "task", __import__(
            "theforge.contracts", fromlist=["TaskSpec"]).TaskSpec)
        assert task.budget_profile == "auto"

    def test_assessment_is_deterministic(self, tmp_path: Path) -> None:
        make_workspace(tmp_path, [SPARK_ENTRY])
        case_a(tmp_path)
        forger, store = self._forger(tmp_path)
        out = [forger.ask(AskRequest(intent="x", targets=["jobs"],
                                     capability="spark.performance"))
               for _ in range(2)]
        dims = [from_dict(ComplexityAssessment,
                          store.read_optional(o.run_id, "complexity"), "$").dimensions  # type: ignore[arg-type]
                for o in out]
        assert [[(d.name, d.score, d.value) for d in ds] for ds in dims][0] == \
               [[(d.name, d.score, d.value) for d in ds] for ds in dims][1]
