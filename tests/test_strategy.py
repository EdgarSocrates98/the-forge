"""Adaptive strategy — shadow champion/challenger recommendations (cycle 4, wave H).

Advisory only: a shadow never changes the selection, and fires only when
measured history clears the promotion bar (enough runs, quality not degraded,
context improvement observed).
"""

import pytest

from theforge.contracts import ContractError, TaskSpec
from theforge.contracts.base import from_dict, to_dict
from theforge.contracts.manifest import (
    Capability,
    ExecutionInfo,
    ForgeManifest,
    Signals,
)
from theforge.contracts.performance import (
    ProviderCapabilityPerformance,
    ProviderPerformance,
)
from theforge.contracts.routing import RoutingDecision, ShadowRecommendation
from theforge.meta import PRODUCER
from theforge.registry import ProviderEntry, RegistryRecord
from theforge.routing import route
from theforge.strategy import shadow_recommendation

CAP = "security.scan"


def entry(
    runs: int,
    *,
    provider: str = "b-forge",
    surface: str | None = "s1",
    verified: int | None = None,
    ctx: int = 0,
    duration_ms: float = 0.0,
) -> ProviderCapabilityPerformance:
    ok = runs
    return ProviderCapabilityPerformance(
        provider=provider,
        capability=CAP,
        runs=runs,
        ok=ok,
        partial=0,
        failed=0,
        verified_runs=verified if verified is not None else runs,
        evidence=0,
        artifacts=0,
        context_bytes=ctx,
        files_sent=0,
        files_cited=0,
        duration_ms=duration_ms,
        surface=surface,
        updated_at="t",
    )


def store(*entries: ProviderCapabilityPerformance) -> ProviderPerformance:
    return ProviderPerformance(producer=PRODUCER, created_at="t", entries=list(entries))


def surf_fp(label: str) -> str:
    """Deterministic sha256 stand-in for a surface fingerprint."""
    from theforge.contracts.canonical import sha256_of

    return sha256_of({"surface": label})


def record(
    pid: str, capability: str = CAP, *, surface: str = "s1", trust: str = "local"
) -> RegistryRecord:
    caps = [
        Capability(
            id=capability,
            actions=["run"],
            default_action="run",
            state="supported",
            operation_class="read_only",
            signals=Signals(),
        )
    ]
    manifest = ForgeManifest(
        id=pid,
        version="1.0.0",
        protocols=["forge/v1"],
        ops=["describe", "health", "execute"],
        capabilities=caps,
        execution=ExecutionInfo(),
    )
    from theforge.contracts.identity import ProviderSurfaceIdentity

    surf = ProviderSurfaceIdentity(
        provider_id=pid,
        provider_version="1.0.0",
        surface_fingerprint=surf_fp(surface),
        capability_fingerprint=surf_fp(f"cap-{surface}"),
    )
    return RegistryRecord(
        entry=ProviderEntry(id=pid, argv=["x"], trust=trust),
        state="ready",
        manifest=manifest,
        manifest_sha256="0" * 64,
        protocol="forge/v1",
        surface=surf,
    )


def task(capability: str = CAP) -> TaskSpec:
    from theforge.contracts.canonical import utc_now

    return TaskSpec(
        producer=PRODUCER,
        created_at=utc_now(),
        id="t1",
        intent="scan",
        workspace_root=".",
        requested_capability=capability,
    )


class TestContract:
    def test_shadow_requires_evidence(self) -> None:
        with pytest.raises(ContractError, match="evidence"):
            ShadowRecommendation(provider="b", capability=CAP, maturity="mature", evidence=[])

    def test_shadow_is_advisory_by_definition(self) -> None:
        with pytest.raises(ContractError, match="advisory"):
            ShadowRecommendation(
                provider="b", capability=CAP, maturity="mature", evidence=["e"], advisory=False
            )  # type: ignore[arg-type]


class TestShadowRecommendation:
    def test_no_performance_no_shadow(self) -> None:
        assert (
            shadow_recommendation(
                None,
                selected_provider="a",
                capability=CAP,
                selected_surface="s1",
                rival_surfaces={"b": "s1"},
            )
            is None
        )

    def test_cold_history_never_advises(self) -> None:
        perf = store(entry(2))  # < warming threshold
        assert (
            shadow_recommendation(
                perf,
                selected_provider="a",
                capability=CAP,
                selected_surface="s1",
                rival_surfaces={"b-forge": "s1"},
            )
            is None
        )

    def test_incumbent_without_history_any_verified_challenger_wins(self) -> None:
        perf = store(entry(4, provider="b-forge", verified=4, ctx=400))
        rec = shadow_recommendation(
            perf,
            selected_provider="a-forge",
            capability=CAP,
            selected_surface="s1",
            rival_surfaces={"b-forge": "s1"},
        )
        assert rec is not None and rec.provider == "b-forge"
        assert rec.maturity == "warming" and rec.advisory is True
        assert any("no measured history" in e for e in rec.evidence)

    def test_challenger_must_not_degrade_quality(self) -> None:
        perf = store(
            entry(8, provider="a-forge", verified=8, ctx=800),  # incumbent 100%
            entry(8, provider="b-forge", verified=4, ctx=100),
        )  # challenger 50%
        assert (
            shadow_recommendation(
                perf,
                selected_provider="a-forge",
                capability=CAP,
                selected_surface="s1",
                rival_surfaces={"b-forge": "s1"},
            )
            is None
        )

    def test_challenger_must_be_strictly_cheaper(self) -> None:
        perf = store(
            entry(8, provider="a-forge", verified=8, ctx=400),
            entry(8, provider="b-forge", verified=8, ctx=800),
        )  # more expensive
        assert (
            shadow_recommendation(
                perf,
                selected_provider="a-forge",
                capability=CAP,
                selected_surface="s1",
                rival_surfaces={"b-forge": "s1"},
            )
            is None
        )

    def test_equal_quality_lower_cost_recommends(self) -> None:
        perf = store(
            entry(8, provider="a-forge", verified=8, ctx=800),
            entry(8, provider="b-forge", verified=8, ctx=100),
        )
        rec = shadow_recommendation(
            perf,
            selected_provider="a-forge",
            capability=CAP,
            selected_surface="s1",
            rival_surfaces={"b-forge": "s1"},
        )
        assert rec is not None and rec.provider == "b-forge"
        assert rec.maturity == "mature"
        assert any("avg context_bytes 12 vs 100" in e for e in rec.evidence)

    def test_surface_scoping_isolation(self) -> None:
        # Challenger's history is against another surface — does not apply.
        perf = store(entry(8, provider="b-forge", surface="old-surface", verified=8, ctx=1))
        assert (
            shadow_recommendation(
                perf,
                selected_provider="a-forge",
                capability=CAP,
                selected_surface="s1",
                rival_surfaces={"b-forge": "s1"},
            )
            is None
        )

    def test_selected_provider_never_shadows_itself(self) -> None:
        perf = store(entry(8, provider="a-forge", verified=8, ctx=10))
        assert (
            shadow_recommendation(
                perf,
                selected_provider="a-forge",
                capability=CAP,
                selected_surface="s1",
                rival_surfaces={"a-forge": "s1"},
            )
            is None
        )

    def test_deterministic_tiebreak(self) -> None:
        # Identical challenger scores → lowest provider id wins.
        perf = store(
            entry(8, provider="z-forge", verified=8, ctx=10),
            entry(8, provider="b-forge", verified=8, ctx=10),
        )
        rec = shadow_recommendation(
            perf,
            selected_provider="a-forge",
            capability=CAP,
            selected_surface="s1",
            rival_surfaces={"b-forge": "s1", "z-forge": "s1"},
        )
        assert rec is not None and rec.provider == "b-forge"


class TestRoutingIntegration:
    """route() attaches the shadow; selection never moves."""

    def _two_providers(self) -> list[RegistryRecord]:
        # a-forge outranks on trust (``trusted`` > ``local``): history prefers
        # b-forge but the deterministic order keeps the trusted incumbent —
        # the shadow is the visible alternative.
        return [record("a-forge", trust="trusted"), record("b-forge", trust="local")]

    def test_shadow_when_trust_wins_over_history(self) -> None:
        records = self._two_providers()
        perf = store(entry(8, provider="b-forge", verified=8, ctx=10, surface=surf_fp("s1")))
        decision = route(task(), records, [], set(), performance=perf)
        assert decision.status == "routed"
        assert decision.selected[0].provider == "a-forge"  # trust wins
        assert decision.shadow is not None
        assert decision.shadow.provider == "b-forge"
        assert decision.shadow.advisory is True
        # Selection is never rewritten by history (§55).
        assert decision.selected[0].provider == "a-forge"

    def test_no_shadow_when_history_itself_picked(self) -> None:
        # Same trust on both: history breaks the tie (H5), so b-forge *is* the
        # selection — no shadow recommendation needed.
        records = [record("a-forge"), record("b-forge")]
        perf = store(entry(8, provider="b-forge", verified=8, ctx=10, surface=surf_fp("s1")))
        decision = route(task(), records, [], set(), performance=perf)
        assert decision.selected[0].provider == "b-forge"
        assert decision.shadow is None

    def test_no_shadow_without_history(self) -> None:
        decision = route(task(), self._two_providers(), [], set())
        assert decision.shadow is None

    def test_no_shadow_when_incumbent_better(self) -> None:
        perf = store(
            entry(8, provider="a-forge", verified=8, ctx=10, surface=surf_fp("s1")),
            entry(8, provider="b-forge", verified=4, ctx=5, surface=surf_fp("s1")),
        )
        decision = route(task(), self._two_providers(), [], set(), performance=perf)
        assert decision.shadow is None

    def test_shadow_survives_serialization(self) -> None:
        perf = store(entry(8, provider="b-forge", verified=8, ctx=10, surface=surf_fp("s1")))
        decision = route(task(), self._two_providers(), [], set(), performance=perf)
        assert decision.shadow is not None
        again = from_dict(RoutingDecision, to_dict(decision), strict=True)
        assert again.shadow == decision.shadow
