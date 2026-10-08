"""Cycle 5 wave Q/R: governed strategy-policy lifecycle — promote only from
eligible experiments with explicit approval, scope-check by exact surface,
staleness on surface change, negotiation re-ordering.
"""

from __future__ import annotations

import pytest

from theforge.contracts.adaptive import StrategyExperiment
from theforge.contracts.canonical import sha256_of, utc_now
from theforge.contracts.observation import ExecutionObservation
from theforge.learning import (
    policy_applies,
    preferred_providers,
    promote_experiment,
    refresh_policies,
)
from theforge.meta import PRODUCER
from theforge.registry.registry import RegistryRecord

APPROVAL = sha256_of({"approval": "operator-ok"})


def _experiment(state: str = "eligible_for_review") -> StrategyExperiment:
    return StrategyExperiment(
        producer=PRODUCER,
        created_at=utc_now(),
        experiment_id="exp1",
        capability="spark.perf",
        task_family="perf",
        champion="alpha",
        challenger="beta",
        champion_surface="s_a",
        challenger_surface="s_b",
        state=state,
        minimum_runs=4,
        minimum_verified_runs=2,
        observations=8,
        verified_observations=6,
        reasons=["challenger improved wall_time_ms; review required"],
    )


def _obs(provider: str = "beta", surface: str = "s_b", **kw) -> ExecutionObservation:
    base = dict(
        run_id="r1",
        provider=provider,
        capability="spark.perf",
        status="ok",
        task_family="perf",
        surface_fingerprint=surface,
        verification="passed",
        wall_time_ms=100.0,
        context_bytes=1000,
    )
    base.update(kw)
    return ExecutionObservation(producer=PRODUCER, created_at=utc_now(), **base)


class TestPromotion:
    def test_ineligible_cannot_promote(self) -> None:
        for state in ("planned", "shadow", "observing", "rejected", "stale"):
            with pytest.raises(ValueError, match="eligible_for_review"):
                promote_experiment(_experiment(state), [], approval_sha256=APPROVAL)

    def test_promotion_binds_approval_and_evidence(self) -> None:
        obs = [_obs(run_id=f"r{i}", wall_time_ms=100.0 + i) for i in range(8)]
        promoted, policy = promote_experiment(_experiment(), obs, approval_sha256=APPROVAL)
        assert promoted.state == "promoted"
        assert promoted.approval_sha256 == APPROVAL
        assert policy.approval_sha256 == APPROVAL
        assert policy.experiment_id == "exp1"
        assert policy.prefer == ["beta"]
        assert policy.surface_fingerprint == "s_b"
        assert policy.sample_runs == 8
        assert policy.metrics["verified_rate"] == 1.0
        assert "median_wall_time_ms" in policy.metrics

    def test_policy_id_is_deterministic(self) -> None:
        _, p1 = promote_experiment(_experiment(), [], approval_sha256=APPROVAL)
        _, p2 = promote_experiment(_experiment(), [], approval_sha256=APPROVAL)
        assert p1.id == p2.id


class TestPolicyScope:
    def _policy(self):
        _, policy = promote_experiment(_experiment(), [], approval_sha256=APPROVAL)
        return policy

    def test_exact_scope_match(self) -> None:
        p = self._policy()
        assert policy_applies(
            p, capability="spark.perf", surface_fingerprint="s_b", task_family="perf"
        )
        assert not policy_applies(
            p,
            capability="spark.perf",
            surface_fingerprint="s_other",
            task_family="perf",
        )
        assert not policy_applies(
            p, capability="other.cap", surface_fingerprint="s_b", task_family="perf"
        )
        assert not policy_applies(
            p,
            capability="spark.perf",
            surface_fingerprint="s_b",
            task_family="other",
        )

    def test_stale_never_applies(self) -> None:
        import dataclasses

        p = dataclasses.replace(self._policy(), stale=True)
        assert not policy_applies(
            p, capability="spark.perf", surface_fingerprint="s_b", task_family="perf"
        )

    def test_valid_until_expiry(self) -> None:
        import dataclasses

        p = dataclasses.replace(self._policy(), valid_until="2020-01-01T00:00:00+00:00")
        assert not policy_applies(
            p,
            capability="spark.perf",
            surface_fingerprint="s_b",
            task_family="perf",
            at=utc_now(),
        )

    def test_preferred_providers_ladder(self) -> None:
        p = self._policy()
        ladder = preferred_providers(
            [p],
            capability="spark.perf",
            surface_fingerprint="s_b",
            task_family="perf",
        )
        assert ladder == ["beta"]
        assert preferred_providers([p], capability="spark.perf", surface_fingerprint="other") == []


class TestRefresh:
    def test_surface_change_marks_stale(self) -> None:
        _, policy = promote_experiment(_experiment(), [], approval_sha256=APPROVAL)
        refreshed = refresh_policies([policy], {"beta": "s_new"})
        assert refreshed[0].stale
        assert any("stale" in lim for lim in refreshed[0].limitations)

    def test_same_surface_stays_fresh(self) -> None:
        _, policy = promote_experiment(_experiment(), [], approval_sha256=APPROVAL)
        refreshed = refresh_policies([policy], {"beta": "s_b"})
        assert not refreshed[0].stale

    def test_stale_is_permanent(self) -> None:
        import dataclasses

        _, policy = promote_experiment(_experiment(), [], approval_sha256=APPROVAL)
        stale = dataclasses.replace(policy, stale=True)
        refreshed = refresh_policies([stale], {"beta": "s_b"})
        assert refreshed[0].stale  # never un-stales silently


class TestNegotiationIntegration:
    """Policy preference reorders equal-evidence candidates, never hard gates."""

    def _record(self, pid: str, surface_fp: str) -> RegistryRecord:
        from theforge.contracts import Capability, ForgeManifest
        from theforge.contracts.identity import ProviderSurfaceIdentity
        from theforge.registry.config import ProviderEntry

        return RegistryRecord(
            entry=ProviderEntry(id=pid, argv=["x"], trust="local"),
            state="ready",
            manifest=ForgeManifest(
                id=pid,
                version="1",
                protocols=["forge/v1"],
                ops=["describe", "health", "execute"],
                capabilities=[
                    Capability(
                        id="a.b",
                        actions=["run"],
                        default_action="run",
                        state="supported",
                        operation_class="read_only",
                    )
                ],
            ),
            manifest_sha256="0" * 64,
            protocol="forge/v1",
            surface=ProviderSurfaceIdentity(
                provider_id=pid,
                provider_version="1",
                protocol_version="forge/v1",
                surface_fingerprint=surface_fp,
                capability_fingerprint="1" * 64,
                recorded_at=utc_now(),
            ),
        )

    def test_policy_reorders_equal_candidates(self) -> None:
        from theforge.contracts import CapabilityRequirement
        from theforge.negotiation import negotiate_all

        sa, sb = "a" * 64, "b" * 64
        exp = StrategyExperiment(
            producer=PRODUCER,
            created_at=utc_now(),
            experiment_id="e",
            capability="a.b",
            task_family=None,
            champion="alpha",
            challenger="beta",
            champion_surface=sa,
            challenger_surface=sb,
            state="eligible_for_review",
            observations=8,
            reasons=["improved"],
        )
        _, policy = promote_experiment(exp, [], approval_sha256=APPROVAL)
        req = CapabilityRequirement(capability="a.b")
        records = [self._record("alpha", sa), self._record("beta", sb)]
        # Without policy: deterministic provider-id order puts alpha first.
        assert [r.provider for r in negotiate_all(req, records)] == ["alpha", "beta"]
        # With the promoted policy: beta is preferred on its own surface.
        assert [r.provider for r in negotiate_all(req, records, policies=[policy])] == [
            "beta",
            "alpha",
        ]

    def test_policy_cannot_lift_incompatible(self) -> None:
        from theforge.contracts import CapabilityRequirement
        from theforge.negotiation import negotiate_all

        sa, sb = "a" * 64, "b" * 64
        exp = StrategyExperiment(
            producer=PRODUCER,
            created_at=utc_now(),
            experiment_id="e",
            capability="a.b",
            task_family=None,
            champion="alpha",
            challenger="beta",
            champion_surface=sa,
            challenger_surface=sb,
            state="eligible_for_review",
            observations=8,
            reasons=["improved"],
        )
        _, policy = promote_experiment(exp, [], approval_sha256=APPROVAL)
        # beta is UNSUPPORTED (no a.b capability) — policy must not promote it.
        unsupported = self._record("beta", sb)
        object.__setattr__(unsupported.manifest.capabilities[0], "id", "z.z")
        req = CapabilityRequirement(capability="a.b")
        res = negotiate_all(req, [self._record("alpha", sa), unsupported], policies=[policy])
        assert res[0].provider == "alpha"
        assert res[-1].state == "UNSUPPORTED"
