"""Cycle 5 contract invariants: memory, capability relations, targets, remote, strategy."""

import json
from pathlib import Path
from typing import Any

import pytest

from theforge.contracts import ContractError, from_dict, to_dict
from theforge.contracts.capability_graph import (
    CAPABILITY_RELATION_SCHEMA,
    CapabilityRelation,
)
from theforge.contracts.memory import (
    EngineeringMemoryEntry,
    FailurePattern,
    MemoryPack,
    MemorySummary,
)
from theforge.contracts.remote import RemoteExecutionReceipt, RemoteExecutionRequest
from theforge.contracts.strategy import (
    CounterfactualPlanComparison,
    PlanSimulation,
    SimulatedNode,
    StrategyPolicy,
)
from theforge.contracts.targets import ExecutionTarget, TargetNegotiation

P = {"id": "theforge", "version": "1"}
SHA = "a" * 64
SHA_B = "b" * 64
NOW = "2026-01-01T00:00:00+00:00"
SCHEMAS = Path(__file__).parents[1] / "schemas"


def memory_dict(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "schema": "theforge/EngineeringMemoryEntry/v1",
        "producer": P,
        "created_at": NOW,
        "id": SHA,
        "subject": "kafka source needs schema registry",
        "claim": "the orders topic requires avro deserialization",
    }
    data.update(overrides)
    return data


class TestEngineeringMemoryEntry:
    def test_round_trip_unresolved(self) -> None:
        entry = from_dict(EngineeringMemoryEntry, memory_dict(), strict=True)
        assert entry.epistemic == "unresolved"
        assert from_dict(EngineeringMemoryEntry, to_dict(entry), strict=True) == entry

    def test_confirmed_requires_evidence(self) -> None:
        with pytest.raises(ContractError, match="evidence_refs or decision_refs"):
            from_dict(
                EngineeringMemoryEntry,
                memory_dict(epistemic="confirmed", source_refs=["run:abc"]),
                strict=True,
            )
        entry = from_dict(
            EngineeringMemoryEntry,
            memory_dict(epistemic="confirmed", evidence_refs=["artifact:e1"]),
            strict=True,
        )
        assert entry.epistemic == "confirmed"

    def test_non_unresolved_requires_provenance(self) -> None:
        with pytest.raises(ContractError, match="requires provenance"):
            from_dict(
                EngineeringMemoryEntry, memory_dict(epistemic="observed"), strict=True
            )

    def test_reported_cannot_self_confirm(self) -> None:
        # 'reported' only needs a source; it must not carry the confirmed shape.
        entry = from_dict(
            EngineeringMemoryEntry,
            memory_dict(epistemic="reported", source_refs=["ticket:123"]),
            strict=True,
        )
        assert entry.epistemic == "reported"

    def test_superseded_links_forward(self) -> None:
        with pytest.raises(ContractError, match="requires superseded_by"):
            from_dict(
                EngineeringMemoryEntry,
                memory_dict(epistemic="superseded", source_refs=["run:a"]),
                strict=True,
            )
        entry = from_dict(
            EngineeringMemoryEntry,
            memory_dict(
                epistemic="superseded", source_refs=["run:a"], superseded_by=SHA_B
            ),
            strict=True,
        )
        assert entry.superseded_by == SHA_B

    def test_cannot_supersede_itself(self) -> None:
        with pytest.raises(ContractError, match="cannot supersede itself"):
            from_dict(
                EngineeringMemoryEntry,
                memory_dict(supersedes=SHA, source_refs=["run:a"], epistemic="observed"),
                strict=True,
            )

    def test_stale_requires_reason(self) -> None:
        with pytest.raises(ContractError, match="requires stale_reason"):
            from_dict(
                EngineeringMemoryEntry,
                memory_dict(epistemic="stale", source_refs=["run:a"]),
                strict=True,
            )

    def test_timestamps_need_timezone(self) -> None:
        with pytest.raises(ContractError, match="timezone"):
            from_dict(
                EngineeringMemoryEntry,
                memory_dict(created_at="2026-01-01T00:00:00"),
                strict=True,
            )

    def test_cross_project_scope_requires_classification(self) -> None:
        with pytest.raises(ContractError, match="origin_project_class"):
            from_dict(
                EngineeringMemoryEntry,
                memory_dict(scope="portable", source_refs=["run:a"], epistemic="observed"),
                strict=True,
            )
        entry = from_dict(
            EngineeringMemoryEntry,
            memory_dict(
                scope="organization",
                epistemic="observed",
                source_refs=["run:a"],
                origin_project_class="internal-lib",
                redaction="no paths, no ids",
            ),
            strict=True,
        )
        assert entry.scope == "organization"

    def test_project_scope_rejects_cross_project_fields(self) -> None:
        with pytest.raises(ContractError, match="cross-project"):
            from_dict(
                EngineeringMemoryEntry,
                memory_dict(origin_project_class="x", source_refs=["run:a"],
                            epistemic="observed"),
                strict=True,
            )


class TestMemoryPack:
    def pack_dict(self, **overrides: Any) -> dict[str, Any]:
        data: dict[str, Any] = {
            "schema": "theforge/MemoryPack/v1",
            "producer": P,
            "created_at": NOW,
            "total_matches": 0,
        }
        data.update(overrides)
        return data

    def test_truncated_requires_withheld(self) -> None:
        with pytest.raises(ContractError, match="truncated with nothing withheld"):
            from_dict(MemoryPack, self.pack_dict(truncated=True), strict=True)
        pack = from_dict(
            MemoryPack,
            self.pack_dict(entries=[memory_dict()], total_matches=2, truncated=True),
            strict=True,
        )
        assert pack.truncated

    def test_total_below_delivered_rejected(self) -> None:
        with pytest.raises(ContractError, match="below delivered"):
            from_dict(
                MemoryPack,
                self.pack_dict(entries=[memory_dict()], total_matches=0),
                strict=True,
            )


class TestMemorySummary:
    def test_sources_required_and_unique(self) -> None:
        base = {
            "schema": "theforge/MemorySummary/v1",
            "producer": P,
            "created_at": NOW,
            "id": SHA,
            "subject": "s",
            "summary": "t",
            "generated_at": NOW,
        }
        with pytest.raises(ContractError, match="must not be empty"):
            from_dict(MemorySummary, {**base, "source_ids": []}, strict=True)
        with pytest.raises(ContractError, match="duplicate"):
            from_dict(
                MemorySummary, {**base, "source_ids": [SHA_B, SHA_B]}, strict=True
            )
        summary = from_dict(
            MemorySummary, {**base, "source_ids": [SHA_B]}, strict=True
        )
        assert summary.source_ids == [SHA_B]

    def test_summary_never_crosses_projects(self) -> None:
        with pytest.raises(ContractError, match="project-local"):
            from_dict(
                MemorySummary,
                {
                    "schema": "theforge/MemorySummary/v1",
                    "producer": P,
                    "created_at": NOW,
                    "id": SHA,
                    "subject": "s",
                    "summary": "t",
                    "source_ids": [SHA_B],
                    "generated_at": NOW,
                    "scope": "portable",
                },
                strict=True,
            )


class TestFailurePattern:
    def pattern_dict(self, **overrides: Any) -> dict[str, Any]:
        data: dict[str, Any] = {
            "schema": "theforge/FailurePattern/v1",
            "producer": P,
            "created_at": NOW,
            "id": SHA,
            "error_family": "timeout",
            "occurrences": 3,
            "first_seen": "2026-01-01T00:00:00+00:00",
            "last_seen": "2026-01-02T00:00:00+00:00",
        }
        data.update(overrides)
        return data

    def test_occurrences_positive(self) -> None:
        with pytest.raises(ContractError, match="positive"):
            from_dict(FailurePattern, self.pattern_dict(occurrences=0), strict=True)

    def test_last_seen_after_first_seen(self) -> None:
        with pytest.raises(ContractError, match="precedes"):
            from_dict(
                FailurePattern,
                self.pattern_dict(last_seen="2025-01-01T00:00:00+00:00"),
                strict=True,
            )

    def test_round_trip(self) -> None:
        pattern = from_dict(FailurePattern, self.pattern_dict(), strict=True)
        assert from_dict(FailurePattern, to_dict(pattern), strict=True) == pattern


class TestCapabilityRelation:
    def rel_dict(self, **overrides: Any) -> dict[str, Any]:
        data: dict[str, Any] = {
            "schema": CAPABILITY_RELATION_SCHEMA,
            "producer": P,
            "created_at": NOW,
            "source": "demo.audit",
            "relation": "verified_by",
            "target": "demo.scan",
            "evidence": ["manifest declares verification"],
        }
        data.update(overrides)
        return data

    def test_evidence_required(self) -> None:
        with pytest.raises(ContractError, match="evidence must not be empty"):
            from_dict(CapabilityRelation, self.rel_dict(evidence=[]), strict=True)

    def test_unknown_relation_rejected(self) -> None:
        with pytest.raises(ContractError, match="unknown relation"):
            from_dict(
                CapabilityRelation, self.rel_dict(relation="trusts"), strict=True
            )

    def test_round_trip(self) -> None:
        rel = from_dict(CapabilityRelation, self.rel_dict(), strict=True)
        assert from_dict(CapabilityRelation, to_dict(rel), strict=True) == rel


class TestExecutionTarget:
    def target_dict(self, **overrides: Any) -> dict[str, Any]:
        data: dict[str, Any] = {
            "schema": "theforge/ExecutionTarget/v1",
            "producer": P,
            "created_at": NOW,
            "id": "local-main",
            "type": "local",
        }
        data.update(overrides)
        return data

    def test_remote_needs_identity(self) -> None:
        with pytest.raises(ContractError, match="requires identity_ref"):
            from_dict(
                ExecutionTarget,
                self.target_dict(type="remote-forge", network="egress"),
                strict=True,
            )
        target = from_dict(
            ExecutionTarget,
            self.target_dict(
                type="remote-forge",
                network="egress",
                identity_ref="org-forge:r1",
            ),
            strict=True,
        )
        assert target.type == "remote-forge"

    def test_remote_needs_network(self) -> None:
        with pytest.raises(ContractError, match="network 'none'"):
            from_dict(
                ExecutionTarget,
                self.target_dict(
                    type="a2a-agent", identity_ref="a2a:agent-x", network="none"
                ),
                strict=True,
            )

    def test_type_cap_is_structural(self) -> None:
        with pytest.raises(ContractError, match="cannot carry"):
            from_dict(
                ExecutionTarget,
                self.target_dict(
                    type="remote-forge",
                    network="egress",
                    identity_ref="org-forge:r1",
                    data_classes=["internal", "confidential"],
                ),
                strict=True,
            )
        with pytest.raises(ContractError, match="cannot carry"):
            from_dict(
                ExecutionTarget,
                self.target_dict(
                    type="a2a-agent",
                    network="egress",
                    identity_ref="a2a:agent-x",
                    data_classes=["internal"],
                ),
                strict=True,
            )

    def test_a2a_trust_never_self_promotes(self) -> None:
        with pytest.raises(ContractError, match="cannot exceed"):
            from_dict(
                ExecutionTarget,
                self.target_dict(
                    type="a2a-agent",
                    network="egress",
                    identity_ref="a2a:agent-x",
                    trust="verified",
                ),
                strict=True,
            )

    def test_unknown_data_stays_local(self) -> None:
        local = from_dict(ExecutionTarget, self.target_dict(), strict=True)
        remote = from_dict(
            ExecutionTarget,
            self.target_dict(
                id="r1",
                type="remote-forge",
                network="egress",
                identity_ref="org-forge:r1",
                data_classes=["public", "internal"],
            ),
            strict=True,
        )
        restricted_local = from_dict(
            ExecutionTarget,
            self.target_dict(id="l2", data_classes=["public", "restricted"]),
            strict=True,
        )
        assert local.admits("unknown")
        assert not local.admits("restricted")  # undeclared class is not admitted
        assert restricted_local.admits("restricted")
        assert not remote.admits("unknown")
        assert not remote.admits("confidential")
        assert remote.admits("internal")


class TestTargetNegotiation:
    REQ = {"data_classification": "internal", "locality": "local-or-remote"}

    def neg_dict(self, **overrides: Any) -> dict[str, Any]:
        data: dict[str, Any] = {
            "schema": "theforge/TargetNegotiation/v1",
            "producer": P,
            "created_at": NOW,
            "provider": "demo",
            "capability": "demo.echo",
            "requirement": self.REQ,
            "candidates": ["local-main"],
            "selected": "local-main",
        }
        data.update(overrides)
        return data

    def test_selected_must_be_candidate(self) -> None:
        with pytest.raises(ContractError, match="one of the candidates"):
            from_dict(
                TargetNegotiation, self.neg_dict(selected="ghost"), strict=True
            )

    def test_no_answer_rejected(self) -> None:
        with pytest.raises(ContractError, match="not an answer"):
            from_dict(
                TargetNegotiation,
                self.neg_dict(candidates=[], selected=None),
                strict=True,
            )

    def test_candidate_cannot_also_be_refused(self) -> None:
        with pytest.raises(ContractError, match="both candidate and refused"):
            from_dict(
                TargetNegotiation,
                self.neg_dict(refusals={"local-main": "busy"}),
                strict=True,
            )


class TestRemoteExecution:
    def request_dict(self, **overrides: Any) -> dict[str, Any]:
        data: dict[str, Any] = {
            "schema": "theforge/RemoteExecutionRequest/v1",
            "producer": P,
            "created_at": NOW,
            "task_sha256": SHA,
            "context_sha256": SHA,
            "budget_sha256": SHA,
            "provider": "demo",
            "surface_fingerprint": SHA_B,
            "target_id": "r1",
            "target_identity_ref": "org-forge:r1",
            "data_classification": "public",
        }
        data.update(overrides)
        return data

    def test_confidential_never_leaves(self) -> None:
        for cls in ("confidential", "restricted", "unknown"):
            with pytest.raises(ContractError, match="cannot leave"):
                from_dict(
                    RemoteExecutionRequest,
                    self.request_dict(data_classification=cls),
                    strict=True,
                )

    def test_allow_requires_policy_ref(self) -> None:
        with pytest.raises(ContractError, match="policy_ref"):
            from_dict(
                RemoteExecutionRequest,
                self.request_dict(policy_decision="allow"),
                strict=True,
            )
        req = from_dict(
            RemoteExecutionRequest,
            self.request_dict(policy_decision="allow", policy_ref="policy:p1"),
            strict=True,
        )
        assert req.policy_decision == "allow"

    def test_receipt_binds_request_and_hashes(self) -> None:
        base = {
            "schema": "theforge/RemoteExecutionReceipt/v1",
            "producer": P,
            "created_at": NOW,
            "request_sha256": SHA,
            "execution_id": "e1",
            "target_id": "r1",
            "target_identity_ref": "org-forge:r1",
            "provider": "demo",
        }
        with pytest.raises(ContractError, match="input_hashes"):
            from_dict(RemoteExecutionReceipt, base, strict=True)
        receipt = from_dict(
            RemoteExecutionReceipt,
            {
                **base,
                "input_hashes": {"task": SHA},
                "output_hashes": {"result": SHA_B},
            },
            strict=True,
        )
        assert receipt.request_sha256 == SHA


class TestStrategyPolicy:
    def policy_dict(self, **overrides: Any) -> dict[str, Any]:
        data: dict[str, Any] = {
            "schema": "theforge/StrategyPolicy/v1",
            "producer": P,
            "created_at": NOW,
            "id": SHA,
            "capability": "demo.scan",
            "surface_fingerprint": SHA_B,
            "prefer": ["demo"],
            "experiment_id": "exp-1",
            "approval_sha256": SHA_B,
            "sample_runs": 5,
            "valid_from": NOW,
        }
        data.update(overrides)
        return data

    def test_prefer_and_approval_required(self) -> None:
        with pytest.raises(ContractError, match="prefer must not be empty"):
            from_dict(
                StrategyPolicy, self.policy_dict(prefer=[]), strict=True
            )
        with pytest.raises(ContractError, match="approval_sha256"):
            from_dict(
                StrategyPolicy,
                self.policy_dict(approval_sha256="not-a-sha"),
                strict=True,
            )

    def test_round_trip(self) -> None:
        policy = from_dict(StrategyPolicy, self.policy_dict(), strict=True)
        assert from_dict(StrategyPolicy, to_dict(policy), strict=True) == policy


class TestPlanSimulation:
    def sim_dict(self, **overrides: Any) -> dict[str, Any]:
        data: dict[str, Any] = {
            "schema": "theforge/PlanSimulation/v1",
            "producer": P,
            "created_at": NOW,
            "plan_sha256": SHA,
            "nodes": [
                {
                    "node": "n1",
                    "provider": "demo",
                    "capability": "demo.scan",
                    "network": "none",
                }
            ],
        }
        data.update(overrides)
        return data

    def test_cost_is_never_invented(self) -> None:
        sim = from_dict(PlanSimulation, self.sim_dict(), strict=True)
        assert sim.cost == "unknown"

    def test_round_trip(self) -> None:
        sim = from_dict(
            PlanSimulation,
            self.sim_dict(risk_flags=["network"], cost="known"),
            strict=True,
        )
        assert sim.risk_flags == ["network"]
        assert from_dict(PlanSimulation, to_dict(sim), strict=True) == sim


class TestCounterfactual:
    def cf_dict(self, **overrides: Any) -> dict[str, Any]:
        data: dict[str, Any] = {
            "schema": "theforge/CounterfactualPlanComparison/v1",
            "producer": P,
            "created_at": NOW,
            "base_sha256": SHA,
            "alternative_sha256": SHA_B,
            "differences": ["alternative adds a verification node"],
        }
        data.update(overrides)
        return data

    def test_same_plan_rejected(self) -> None:
        with pytest.raises(ContractError, match="same plan"):
            from_dict(
                CounterfactualPlanComparison,
                self.cf_dict(alternative_sha256=SHA),
                strict=True,
            )

    def test_empty_comparison_rejected(self) -> None:
        with pytest.raises(ContractError, match="differences or unknowns"):
            from_dict(
                CounterfactualPlanComparison,
                self.cf_dict(differences=[]),
                strict=True,
            )


def test_cycle5_schemas_are_exported() -> None:
    for name in (
        "EngineeringMemoryEntry",
        "MemoryPack",
        "MemorySummary",
        "FailurePattern",
        "CapabilityRelation",
        "ExecutionTarget",
        "TargetRequirement",
        "TargetNegotiation",
        "RemoteExecutionRequest",
        "RemoteExecutionReceipt",
        "StrategyPolicy",
        "PlanSimulation",
        "CounterfactualPlanComparison",
    ):
        path = SCHEMAS / f"{name}.schema.json"
        assert path.is_file(), f"missing exported schema {path.name}"
        schema = json.loads(path.read_text(encoding="utf-8"))
        assert schema["title"] == name


def test_simulated_node_needs_identifiers() -> None:
    with pytest.raises(ContractError):
        SimulatedNode(node="", provider="demo", capability="c")
