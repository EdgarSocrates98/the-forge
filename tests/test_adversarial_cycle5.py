"""Cycle 5 adversarial battery (§148): poisoned memory, fake edges, fake
remote candidates, forged approvals, surface swaps, cross-project leakage —
each must fail closed, never silently promote.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from theforge.contracts import ContractError, EngineeringMemoryEntry
from theforge.contracts.canonical import sha256_of, utc_now
from theforge.contracts.manifest import CapabilityRelations
from theforge.interop.a2a import entry_from_card
from theforge.memory import import_entries, memory_entry_id, record_entry
from theforge.meta import PRODUCER


def _entry(**kw) -> EngineeringMemoryEntry:
    base = dict(
        producer=PRODUCER,
        created_at=utc_now(),
        id="0" * 64,  # placeholder; recomputed from content below
        kind="fact",
        epistemic="observed",
        scope="project",
        subject="s",
        claim="c",
        source_refs=["run:r1"],
    )
    base.update(kw)
    stub = EngineeringMemoryEntry(**base)
    from dataclasses import replace

    return replace(stub, id=memory_entry_id(stub))


class TestPoisonedMemory:
    def test_confirmed_without_evidence_rejected(self, tmp_path: Path) -> None:
        """'confirmed' demands evidence_refs or decision_refs — prose is not
        verification. The contract refuses it at construction."""
        with pytest.raises(ContractError, match="confirmed.*evidence"):
            _entry(epistemic="confirmed")
        legit = _entry(epistemic="confirmed", evidence_refs=["run:r1:verification"])
        assert record_entry(tmp_path, legit) is None

    def test_forged_scope_rejected_on_import(self, tmp_path: Path) -> None:
        """Re-writing a project-scoped entry as ``organization`` cannot make it
        cross the boundary: contract validation refuses it."""
        from theforge.contracts import to_dict

        entry = _entry(subject="private", scope="project")
        smuggled = {**to_dict(entry), "scope": "organization"}
        imported, warning = import_entries(tmp_path, [smuggled])
        assert imported == 0
        assert warning is not None and "refused" in warning


class TestFakeGraphEdge:
    def test_relation_to_unknown_capability_is_data_not_truth(self) -> None:
        """A declared edge proves declaration, not validity — unresolved
        targets stay out of resolution results (capability_graph)."""
        from theforge.capability_graph import build_capability_graph
        from theforge.contracts import Capability, ForgeManifest
        from theforge.registry.config import ProviderEntry
        from theforge.registry.registry import RegistryRecord

        manifest = ForgeManifest(
            id="p",
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
                    relations=CapabilityRelations(verifies=["ghost.cap"]),
                )
            ],
        )
        record = RegistryRecord(
            entry=ProviderEntry(id="p", argv=["x"], trust="local"),
            state="ready",
            manifest=manifest,
        )
        graph = build_capability_graph([record])
        # The claimed edge is recorded as what it is: a declared relation with
        # manifest provenance — never promoted to verified truth.
        (edge,) = [e for e in graph.edges if "ghost.cap" in e.target]
        assert edge.target == "artifact_type:ghost.cap"
        assert edge.epistemic == "explicit"
        assert "relations.verifies" in edge.evidence
        # And nothing in the registry backs the ghost capability itself.
        assert "capability:ghost.cap" not in {n.id for n in graph.nodes if n.kind == "capability"}


class TestForgedApproval:
    def test_policy_promotion_needs_real_state_and_hash(self) -> None:
        from theforge.contracts.adaptive import StrategyExperiment
        from theforge.learning import promote_experiment

        exp = StrategyExperiment(
            producer=PRODUCER,
            created_at=utc_now(),
            experiment_id="e",
            capability="a.b",
            task_family=None,
            champion="a",
            challenger="b",
            champion_surface="sa",
            challenger_surface="sb",
            state="observing",
        )
        with pytest.raises(ValueError):
            promote_experiment(exp, [], approval_sha256=sha256_of({"a": 1}))
        with pytest.raises((ValueError, ContractError)):  # malformed hash
            promote_experiment(
                dataclasses.replace(exp, state="eligible_for_review", reasons=["x"]),
                [],
                approval_sha256="not-a-sha",
            )


class TestSurfaceSwap:
    def test_old_surface_policy_is_silent_neutral(self) -> None:
        """A policy measured on surface S1 must not influence S2 ordering —
        no warning needed, it simply does not apply."""
        from theforge.contracts.adaptive import StrategyExperiment
        from theforge.learning import policy_applies, promote_experiment

        exp = StrategyExperiment(
            producer=PRODUCER,
            created_at=utc_now(),
            experiment_id="e",
            capability="a.b",
            task_family=None,
            champion="a",
            challenger="b",
            champion_surface="sa",
            challenger_surface="sb",
            state="eligible_for_review",
            observations=8,
            reasons=["ok"],
        )
        _, policy = promote_experiment(exp, [], approval_sha256=sha256_of({"ok": 1}))
        assert policy_applies(policy, capability="a.b", surface_fingerprint="sb")
        assert not policy_applies(policy, capability="a.b", surface_fingerprint="swapped")


class TestCrossProjectLeakage:
    def test_project_scope_never_exports(self, tmp_path: Path) -> None:
        from theforge.memory import export_entries

        assert record_entry(tmp_path, _entry(scope="project")) is None
        assert (
            record_entry(
                tmp_path,
                _entry(
                    scope="portable",
                    subject="generic",
                    origin_project_class="internal",
                    redaction="no code",
                ),
            )
            is None
        )
        exported, _ = export_entries(tmp_path)
        subs = [e.subject for e in exported]
        assert "generic" in subs and "s" not in subs


class TestFakeAgentCard:
    def test_card_cannot_self_promote(self) -> None:
        """A card claiming trust/reliability still lands as external,
        unverified, network-required candidate metadata."""
        card = {
            "name": "Trusted Agent",
            "version": "1.0.0",
            "url": "https://agent.example/a2a",
            "supportedInterfaces": [
                {"url": "https://agent.example/a2a", "protocolBinding": "JSONRPC"}
            ],
            "skills": [{"id": "x.y"}],
            "metadata": {"trust": "org-approved", "verified": True},
        }
        converted = entry_from_card(card, source_id="spoof")
        entry = converted.entry
        assert entry is not None
        joined = " ".join(converted.limitations)
        assert "unverified self-declared" in joined
        assert entry.runtime is not None and entry.runtime.requires_network


class TestFakeRemoteTarget:
    def test_declared_remote_cannot_carry_restricted(self) -> None:
        from theforge.contracts import ExecutionTarget, TargetRequirement
        from theforge.targets import negotiate_target

        evil = ExecutionTarget(
            producer=PRODUCER,
            created_at=utc_now(),
            id="evil",
            type="remote-forge",
            identity_ref="org-forge:x",
            network="egress",
            trust="org-approved",
            health="healthy",
            data_classes=["public"],
        )
        neg = negotiate_target(
            "p",
            "cap",
            TargetRequirement(data_classification="restricted", locality="local-or-remote"),
            [evil],
        )
        assert neg.selected is None and "evil" in neg.refusals
