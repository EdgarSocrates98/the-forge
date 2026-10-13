"""Cycle 5.1 §11/§20: every surface-bound evidence loses freshness when the
surface changes — same package version included.

The invariant under test: ``same version + different runtime surface =
stale evidence``. Each surface-bound artifact type gets a focused proof:
capability relations, memory facts, provider observations, strategy policies
and the fingerprints themselves.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import pytest
from tests.test_memory import make_entry

from theforge.capability_graph import relation_fresh
from theforge.contracts import (
    Capability,
    CapabilityRelation,
    ContractError,
    ForgeManifest,
)
from theforge.contracts.canonical import utc_now
from theforge.learning import refresh_policies
from theforge.memory import entry_fresh, record_entry
from theforge.meta import PRODUCER
from theforge.metrics import load_performance, record_performance
from theforge.registry.surface import capability_fingerprint, surface_fingerprint

pytestmark = pytest.mark.unit


def _cap(cid: str, **kw: Any) -> Capability:
    fields = {
        "actions": ["run"],
        "default_action": "run",
        "state": "supported",
        "operation_class": "read_only",
    }
    fields.update(kw)
    return Capability(id=cid, **fields)


def _manifest(**over: Any) -> ForgeManifest:
    """A manifest whose ``version`` never changes — only surface fields do."""
    base: dict[str, Any] = {
        "id": "fixture-x",
        "version": "1.0.0",
        "protocols": ["forge/v1"],
        "ops": ["describe", "health", "execute"],
        "capabilities": [_cap("x.op")],
    }
    base.update(over)
    return ForgeManifest(**base)


def _relation(surface: str | None, **kw: Any) -> CapabilityRelation:
    fields = {
        "producer": PRODUCER,
        "created_at": utc_now(),
        "source": "x.op",
        "relation": "verifies",
        "target": "report.v1",
        "evidence": ["manifest x.op"],
        "surface": surface,
    }
    fields.update(kw)
    return CapabilityRelation(**fields)


S_OLD = "a" * 64
S_NEW = "b" * 64


class TestSameVersionDifferentSurface:
    """The headline invariant of §11: fingerprints — not versions — carry the
    truth of a surface."""

    def test_same_version_different_surface_different_fingerprint(self) -> None:
        m1 = _manifest()
        m2 = _manifest(ops=["describe", "health", "execute", "verify"])
        assert m1.version == m2.version == "1.0.0"
        assert surface_fingerprint(m1) != surface_fingerprint(m2)
        # capability fingerprint also reacts to operational capability changes
        m3 = _manifest(capabilities=[_cap("x.op", actions=["run", "diagnose"])])
        assert capability_fingerprint(m1) != capability_fingerprint(m3)


class TestRelationFreshness:
    """§20: a surface-bound relation is stale when the bound surface changes —
    producer, consumer or verifier."""

    def test_bound_relation_stales_on_change(self) -> None:
        rel = _relation(S_OLD)
        assert relation_fresh(rel, S_OLD)
        assert not relation_fresh(rel, S_NEW)

    def test_bound_relation_not_fresh_when_surface_unknown(self) -> None:
        assert not relation_fresh(_relation(S_OLD), None)

    def test_unbound_relation_always_fresh(self) -> None:
        rel = _relation(None)
        assert relation_fresh(rel, S_OLD)
        assert relation_fresh(rel, S_NEW)
        assert relation_fresh(rel, None)

    def test_relation_surface_must_be_sha256(self) -> None:
        with pytest.raises(ContractError):
            _relation("not-a-fingerprint")


class TestMemoryFreshness:
    def test_unbound_entry_always_fresh(self) -> None:
        entry = make_entry(subject="s", claim="c")
        assert entry_fresh(entry, S_OLD)
        assert entry_fresh(entry, S_NEW)
        assert entry_fresh(entry, None)

    def test_bound_entry_stales_on_change(self) -> None:
        bound = dataclasses.replace(make_entry(subject="s", claim="c"), surface_fingerprint=S_OLD)
        assert entry_fresh(bound, S_OLD)
        assert not entry_fresh(bound, S_NEW)
        assert not entry_fresh(bound, None)  # unknown surface cannot confirm

    def test_terminal_entries_never_fresh(self) -> None:
        stale = dataclasses.replace(
            make_entry(
                subject="s",
                claim="c",
                epistemic="stale",
                stale_reason="surface changed",
            ),
            surface_fingerprint=S_OLD,
        )
        assert not entry_fresh(stale, S_OLD)


class TestProviderObservationsPerSurface:
    """Performance history accumulates per (provider, capability, surface): a
    changed surface starts clean instead of inheriting the old numbers."""

    def test_surface_change_does_not_inherit_history(self, tmp_path: Path) -> None:
        for _ in range(3):
            record_performance(
                tmp_path,
                "p1",
                "x.op",
                status="ok",
                verified=True,
                evidence=1,
                artifacts=0,
                context_bytes=10,
                files_sent=1,
                files_cited=0,
                duration_ms=5.0,
                surface=S_OLD,
            )
        record_performance(
            tmp_path,
            "p1",
            "x.op",
            status="failed",
            verified=False,
            evidence=0,
            artifacts=0,
            context_bytes=4,
            files_sent=0,
            files_cited=0,
            duration_ms=9.0,
            surface=S_NEW,
        )
        store, _ = load_performance(tmp_path)
        assert store is not None
        by_surface = {e.surface: e for e in store.entries}
        assert by_surface[S_OLD].runs == 3 and by_surface[S_OLD].ok == 3
        # the new surface has exactly the run it earned — no inherited history
        assert by_surface[S_NEW].runs == 1 and by_surface[S_NEW].failed == 1


class TestMemorySurfaceWriteAndPolicy:
    def test_entry_fresh_integrates_with_store(self, tmp_path: Path) -> None:
        bound = dataclasses.replace(
            make_entry(subject="surf", claim="c", evidence_refs=["run:r1/result.json"]),
            surface_fingerprint=S_OLD,
        )
        record_entry(tmp_path, bound)
        from theforge.memory import load_entries

        entries, _ = load_entries(tmp_path)
        loaded = next(e for e in entries if e.id == bound.id)
        assert entry_fresh(loaded, S_OLD)
        assert not entry_fresh(loaded, S_NEW)

    def test_policy_stale_on_surface_change(self) -> None:
        from tests.test_learning import APPROVAL, _experiment, _obs

        from theforge.learning import promote_experiment

        obs = [_obs(run_id=f"r{i}") for i in range(8)]
        _, policy = promote_experiment(_experiment(), obs, approval_sha256=APPROVAL)
        assert not policy.stale
        refreshed = refresh_policies([policy], {"beta": S_NEW})
        assert refreshed[0].stale
        # stale is permanent: re-refreshing on the same surface never un-stales
        assert refresh_policies(refreshed, {"beta": S_NEW})[0].stale
