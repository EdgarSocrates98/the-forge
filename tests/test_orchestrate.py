"""lf-0031: the orchestrator lane — intent -> discovery -> justified governed
plan -> consolidated report. The spec scenario is the PySpark audit:
spark-forge-aws + forge-doctor-data picked with justification, data-sentinel
an honest optional gap, never a forced diagnostic without declared inputs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from theforge import delegation, orchestrate
from theforge.contracts import (
    EvidenceHandoff,
    SpecialistCapability,
    SpecialistDelegation,
    from_dict,
    to_dict,
)
from theforge.contracts.base import ContractError
from theforge.contracts.orchestration import (
    ORCHESTRATION_REPORT_SCHEMA,
    OrchestrationReport,
)
from theforge.contracts.specialist_delegation import DelegationPolicy, SpecialistRef
from theforge.delegation_governance import seal_handoff
from theforge.discovery import DiscoveryReport, SpecialistDiscovery

# --- fixtures ---------------------------------------------------------------------


def _manifest(provider: str, capabilities: list[dict]) -> SpecialistCapability:
    return from_dict(
        SpecialistCapability,
        {
            "specialist": {"id": provider, "version": "1.0.0"},
            "capabilities": capabilities,
        },
    )


def _entry(
    provider: str,
    state: str = "VERIFIED",
    capabilities: list[dict] | None = None,
    *,
    manifest: bool = True,
) -> SpecialistDiscovery:
    caps = (
        capabilities
        if capabilities is not None
        else [{"id": f"{provider.split('-')[0]}.analyze", "risk": "read_only"}]
    )
    return SpecialistDiscovery(
        forge_id=provider,
        state=state,  # type: ignore[arg-type]
        version="1.0.0",
        capability_manifest=_manifest(provider, caps) if manifest else None,
    )


def _report(*entries: SpecialistDiscovery) -> DiscoveryReport:
    return DiscoveryReport(entries=list(entries), context_digest="ctx-test")


def _delegation(*refs: SpecialistRef) -> SpecialistDelegation:
    return SpecialistDelegation(
        consumer="the-forge",
        specialists=list(refs),
        policy=DelegationPolicy(discovery="runtime", execution="governed"),
    )


# The audit scenario: AWS does PySpark static analysis, Doctor Data reviews the
# data pipeline, Sentinel diagnoses runtime failures — when it exists at all.
AWS_CAPS = [
    {
        "id": "pyspark.static-analysis",
        "description": "Static analysis of PySpark code by AST",
        "risk": "read_only",
        "external_cost": "none",
        "finding_class": "static",
        "entrypoint": ["{python}", "-m", "sparkforge_aws", "analyze"],
    },
    {
        "id": "spark.runtime-analysis",
        "description": "Spark runtime evidence: event logs and SQL metrics",
        "risk": "read_only",
        "external_cost": "none",
        "finding_class": "runtime",
        "requires": ["event-log"],
        "entrypoint": ["{python}", "-m", "sparkforge_aws", "analyze-log"],
    },
]
DD_CAPS = [
    {
        "id": "data.scan",
        "description": "Deterministic scan of a data platform repository",
        "risk": "read_only",
        "external_cost": "none",
        "finding_class": "static",
        "entrypoint": ["{python}", "-m", "forge_doctor_data", "scan"],
    }
]
SENTINEL_CAPS = [
    {
        "id": "sentinel.log-analyze",
        "description": "runtime failure log analysis",
        "risk": "read_only",
        "external_cost": "none",
        "finding_class": "runtime",
        "requires": ["event-log"],
        "entrypoint": ["{python}", "-m", "data_sentinel", "analyze"],
    }
]


def _audit_delegation() -> SpecialistDelegation:
    """Declared intents the consumer authored per delegate — each specialist
    serves a *different* claim, all subsets of the audit intent's tokens.
    Two providers claiming the same declared intent is ambiguity by design
    (test_plan_ambiguity_is_reported_never_guessed)."""
    return _delegation(
        SpecialistRef(provider="spark-forge-aws", optional=True, intents=["pyspark"]),
        SpecialistRef(provider="forge-doctor-data", optional=True, intents=["project"]),
        SpecialistRef(provider="data-sentinel-forge", optional=True, intents=["audit"]),
    )


def _handoff(provider: str, capability: str, findings: list[dict]) -> EvidenceHandoff:
    return from_dict(
        EvidenceHandoff,
        {
            "run_id": "run-1",
            "correlation_id": "corr-1",
            "idempotency_key": "idem-1",
            "source_provider": provider,
            "consumer_provider": "the-forge",
            "capability": capability,
            "status": "completed",
            "created_at": "2026-10-21T00:00:00Z",
            "findings": findings,
        },
    )


# --- the consumer declaration ------------------------------------------------------


def test_build_delegation_every_specialist_optional_no_mandatory_deps():
    decl = orchestrate.build_delegation()
    assert decl.consumer == "the-forge"
    assert decl.specialists
    # Every declared delegate is optional: a forge never gains a mandatory
    # dependency on another forge (spec acceptance).
    assert all(s.optional for s in decl.specialists)
    assert all(s.provider != "the-forge" for s in decl.specialists)  # never self
    sentinel = decl.specialist("data-sentinel-forge")
    assert sentinel is not None and sentinel.optional


def test_build_delegation_derives_intents_from_knowledge():
    decl = orchestrate.build_delegation()
    aws = decl.specialist("spark-forge-aws")
    assert aws is not None
    # Knowledge-pack intents/technologies slugified into the delegation
    # vocabulary — "pyspark" is an authored technology of spark-forge-aws.
    assert "pyspark" in aws.intents


# --- the plan lane -----------------------------------------------------------------


def test_plan_audit_picks_aws_and_doctor_data_sentinel_is_a_named_gap():
    report = _report(
        _entry("spark-forge-aws", capabilities=AWS_CAPS),
        _entry("forge-doctor-data", capabilities=DD_CAPS),
        # data-sentinel-forge is NOT_INSTALLED on this machine: honest gap.
        _entry("data-sentinel-forge", state="NOT_INSTALLED", manifest=False),
    )
    outcome = orchestrate.orchestrate_plan(
        "audit a pyspark project",
        delegation_doc=_audit_delegation(),
        report=report,
        authorized_risks={"LOCAL_READ"},
    )
    plan = outcome.plan
    assert plan.status == "planned"
    picked = {p.provider: p for p in plan.picks}
    assert set(picked) == {"spark-forge-aws", "forge-doctor-data"}
    # Justification names the matched intent and the capability evidence.
    assert any("pyspark" in j for p in plan.picks for j in p.justification)
    assert picked["spark-forge-aws"].capability == "pyspark.static-analysis"
    assert picked["forge-doctor-data"].capability == "data.scan"
    # The absent sentinel is a named refusal + a recommendation, never a failure.
    absent = [r for r in plan.refusals if r.provider == "data-sentinel-forge"]
    assert absent and absent[0].code == "provider-absent"
    assert any(
        r.provider == "data-sentinel-forge" and "install" in r.action
        for r in outcome.report.recommended
    )


def test_plan_never_forces_a_diagnostic_without_declared_inputs():
    """A capability whose ``requires`` the caller did not satisfy is filtered
    out as insufficient-evidence — the sentinel/log diagnostic is never run
    against absent evidence."""
    report = _report(_entry("data-sentinel-forge", capabilities=SENTINEL_CAPS))
    outcome = orchestrate.orchestrate_plan(
        "diagnose a pyspark failure",
        delegation_doc=_delegation(
            SpecialistRef(provider="data-sentinel-forge", optional=True, intents=["pyspark"])
        ),
        report=report,
        inputs=set(),  # no event-log declared
        authorized_risks={"LOCAL_READ"},
    )
    assert outcome.plan.picks == []
    refusal = next(r for r in plan_refusals(outcome) if r.provider == "data-sentinel-forge")
    assert refusal.code == "insufficient-evidence"
    assert "event-log" in refusal.detail


def plan_refusals(outcome: orchestrate.Orchestration):
    return outcome.plan.refusals


def test_plan_with_declared_input_keeps_the_pick():
    report = _report(_entry("data-sentinel-forge", capabilities=SENTINEL_CAPS))
    outcome = orchestrate.orchestrate_plan(
        "diagnose a pyspark failure",
        delegation_doc=_delegation(
            SpecialistRef(provider="data-sentinel-forge", optional=True, intents=["pyspark"])
        ),
        report=report,
        inputs={"event-log"},
        authorized_risks={"LOCAL_READ"},
    )
    assert [p.provider for p in outcome.plan.picks] == ["data-sentinel-forge"]


def test_plan_absent_specialist_is_optional_never_fatal():
    report = _report(_entry("data-sentinel-forge", state="NOT_INSTALLED", manifest=False))
    outcome = orchestrate.orchestrate_plan(
        "diagnose a pyspark failure",
        delegation_doc=_delegation(
            SpecialistRef(provider="data-sentinel-forge", optional=True, intents=["pyspark"])
        ),
        report=report,
    )
    assert outcome.plan.status == "unavailable"
    assert outcome.plan.refusals[0].code == "provider-absent"
    # The report recommends installing it — as an option, not a requirement.
    assert any("optional" in r.action for r in outcome.report.recommended)


def test_plan_ambiguity_is_reported_never_guessed():
    report = _report(
        _entry(
            "spark-forge-aws",
            capabilities=[
                {
                    "id": "a.pyspark",
                    "description": "pyspark analysis",
                    "risk": "read_only",
                },
                {
                    "id": "b.pyspark",
                    "description": "pyspark analysis",
                    "risk": "read_only",
                },
            ],
        )
    )
    outcome = orchestrate.orchestrate_plan(
        "audit pyspark",
        delegation_doc=_delegation(
            SpecialistRef(provider="spark-forge-aws", optional=True, intents=["pyspark"])
        ),
        report=report,
        authorized_risks={"LOCAL_READ"},
    )
    assert outcome.plan.status == "ambiguous"
    assert outcome.report.unknowns


# --- the run lane ------------------------------------------------------------------


def _completed(request: delegation.DelegationRequest, handoff: EvidenceHandoff | None):
    """A fake governed executor: COMPLETED, emitting the sealed handoff on
    stdout the way a real specialist would."""
    sealed = seal_handoff(handoff) if handoff is not None else None
    tail = [json.dumps(to_dict(sealed))] if sealed is not None else ["no output"]
    return delegation.DelegationResult(
        task_id=request.task_id,
        provider=request.provider,
        stage="COMPLETED",
        execution_mode=request.execution_mode,
        stdout_tail=tail,
        evidence=["exit_code=0"],
        exit_code=0,
    )


def test_run_consolidates_classed_findings_with_provenance(tmp_path: Path):
    report = _report(
        _entry("spark-forge-aws", capabilities=AWS_CAPS),
        _entry("forge-doctor-data", capabilities=DD_CAPS),
        _entry("data-sentinel-forge", state="NOT_INSTALLED", manifest=False),
    )
    handoffs = {
        "spark-forge-aws": _handoff(
            "spark-forge-aws",
            "pyspark.static-analysis",
            [
                {
                    "id": "SF-PY-001",
                    "severity": "high",
                    "confidence": "CONFIRMED",
                    "summary": "skewed join",
                    "evidence_refs": ["fact:1"],
                }
            ],
        ),
        "forge-doctor-data": _handoff(
            "forge-doctor-data",
            "data.scan",
            [
                {
                    "id": "DD-SCAN-1",
                    "severity": "medium",
                    "confidence": "LIKELY",
                    "summary": "missing quality gate",
                    "evidence_refs": ["fact:2"],
                }
            ],
        ),
    }

    def fake_execute(request, *, cwd=None):
        return _completed(request, handoffs.get(request.provider))

    outcome = orchestrate.orchestrate_run(
        "audit a pyspark project",
        delegation_doc=_audit_delegation(),
        report=report,
        authorized_risks={"LOCAL_READ"},
        executor=fake_execute,
    )
    rep = outcome.report
    assert rep.kind == "run" and rep.plan_status == "planned"
    assert rep.correlation_id.startswith("orch-")
    # Findings carry the emitting capability's declared class.
    by_id = {f.id: f for f in rep.findings}
    assert by_id["SF-PY-001"].finding_class == "STATIC"
    assert by_id["DD-SCAN-1"].finding_class == "STATIC"
    assert by_id["SF-PY-001"].providers == ["spark-forge-aws"]
    # Every pick produced a completed entry with a received handoff.
    assert all(e.status == "completed" for e in rep.entries)
    assert all(e.handoff_status == "received" for e in rep.entries)
    # Sentinel stays a named gap inside the same report.
    assert any(u.provider == "data-sentinel-forge" for u in rep.unresolved)
    # Provenance: the delegation task receipts are named.
    assert len(rep.provenance.delegation_tasks) == 2


def test_run_marks_correlated_findings_across_providers():
    shared = {
        "id": "SHARED-1",
        "severity": "high",
        "confidence": "LIKELY",
        "summary": "same finding seen twice",
        "evidence_refs": ["fact:9"],
    }
    entries = [
        _entry("spark-forge-aws", capabilities=AWS_CAPS),
        _entry("forge-doctor-data", capabilities=DD_CAPS),
    ]
    decl = _delegation(
        SpecialistRef(provider="spark-forge-aws", optional=True, intents=["pyspark"]),
        SpecialistRef(provider="forge-doctor-data", optional=True, intents=["audit"]),
    )
    handoffs = {
        "spark-forge-aws": _handoff("spark-forge-aws", "pyspark.static-analysis", [shared]),
        "forge-doctor-data": _handoff("forge-doctor-data", "data.scan", [shared]),
    }

    outcome = orchestrate.orchestrate_run(
        "audit pyspark",
        delegation_doc=decl,
        report=_report(*entries),
        authorized_risks={"LOCAL_READ"},
        executor=lambda req, *, cwd=None: _completed(req, handoffs[req.provider]),
    )
    finding = next(f for f in outcome.report.findings if f.id == "SHARED-1")
    assert finding.correlated
    assert finding.providers == ["forge-doctor-data", "spark-forge-aws"]


def test_run_completed_without_handoff_is_honest_not_fabricated():
    report = _report(_entry("forge-doctor-data", capabilities=DD_CAPS))
    decl = _delegation(
        SpecialistRef(provider="forge-doctor-data", optional=True, intents=["pyspark"])
    )
    outcome = orchestrate.orchestrate_run(
        "audit pyspark",
        delegation_doc=decl,
        report=report,
        authorized_risks={"LOCAL_READ"},
        executor=lambda req, *, cwd=None: _completed(req, None),
    )
    entry = outcome.report.entries[0]
    assert entry.status == "completed" and entry.handoff_status == "absent"
    assert outcome.report.findings == []  # nothing invented
    assert any("without an EvidenceHandoff" in n for n in entry.notes)


def test_run_refused_when_argv_entrypoint_cannot_resolve():
    # data-sentinel-forge has no binary on PATH — {cli} cannot resolve.
    caps = [
        {
            "id": "sentinel.log-analyze",
            "description": "log analysis",
            "risk": "read_only",
            "external_cost": "none",
            "entrypoint": ["{cli}", "analyze"],
        }
    ]
    report = _report(_entry("data-sentinel-forge", capabilities=caps))
    decl = _delegation(
        SpecialistRef(provider="data-sentinel-forge", optional=True, intents=["pyspark"])
    )
    outcome = orchestrate.orchestrate_run(
        "audit pyspark",
        delegation_doc=decl,
        report=report,
        authorized_risks={"LOCAL_READ"},
        executor=lambda req, *, cwd=None: pytest.fail("executor must not run"),
    )
    entry = outcome.report.entries[0]
    assert entry.status == "refused"
    assert any(u.code == "invalid-input" for u in outcome.report.unresolved)


def test_run_denies_unauthorized_risk_at_execution_time():
    caps = [
        {
            "id": "data.write",
            "description": "writes data",
            "risk": "local_mutation",
            "external_cost": "none",
            "entrypoint": ["{python}", "x.py"],
        }
    ]
    report = _report(_entry("forge-doctor-data", capabilities=caps))
    decl = _delegation(
        SpecialistRef(provider="forge-doctor-data", optional=True, intents=["pyspark"])
    )
    outcome = orchestrate.orchestrate_run(
        "audit pyspark data write",
        delegation_doc=decl,
        report=report,
        authorized_risks={"LOCAL_READ"},  # LOCAL_WRITE never granted
        executor=lambda req, *, cwd=None: pytest.fail("denied capability ran"),
    )
    assert outcome.plan.picks == []
    assert any(r.code == "policy-refusal" for r in outcome.plan.refusals)


# --- the report contract + persistence ----------------------------------------------


def test_report_roundtrip_and_schema():
    report = OrchestrationReport(
        kind="plan",
        intent="audit a pyspark project",
        plan_status="unavailable",
    )
    assert report.schema == ORCHESTRATION_REPORT_SCHEMA
    restored = from_dict(OrchestrationReport, to_dict(report))
    assert restored == report


def test_report_rejects_an_unknown_unresolved_code():
    with pytest.raises(ContractError):
        from_dict(
            OrchestrationReport,
            to_dict(
                OrchestrationReport(
                    kind="plan",
                    intent="x",
                    plan_status="refused",
                    unresolved=[
                        {"code": "not-a-code", "detail": "bogus"}  # type: ignore[list-item]
                    ],
                )
            ),
        )


def test_persist_report_writes_redacted_receipt(tmp_path: Path):
    report = OrchestrationReport(
        kind="run",
        intent="audit",
        correlation_id="orch-test1234",
        generated_at="2026-10-21T00:00:00Z",
        plan_status="planned",
    )
    path = orchestrate.persist_report(report, tmp_path)
    assert path.is_file()
    assert path.parent == tmp_path / ".forge" / "orchestrations"
    doc = json.loads(path.read_text())
    assert doc["schema"] == ORCHESTRATION_REPORT_SCHEMA
    assert doc["correlation_id"] == "orch-test1234"


# --- capability manifest derivation -------------------------------------------------


def test_capability_manifest_derivation_preserves_declared_finding_class():
    from theforge import capability_manifest
    from theforge.contracts.manifest import ForgeManifest

    manifest = from_dict(
        ForgeManifest,
        {
            "id": "spark-forge-aws",
            "version": "1.0.0",
            "protocols": ["forge/v1"],
            "ops": ["describe", "health", "execute"],
            "capabilities": [
                {
                    "id": "pyspark.static-analysis",
                    "actions": ["analyze"],
                    "default_action": "analyze",
                    "state": "supported",
                    "operation_class": "read_only",
                    "description": "static analysis",
                    "finding_class": "static",
                },
                {
                    "id": "spark.runtime-analysis",
                    "actions": ["analyze"],
                    "default_action": "analyze",
                    "state": "supported",
                    "operation_class": "read_only",
                    "description": "runtime evidence",
                    # no finding_class declared -> stays ""
                },
            ],
        },
    )
    derived = capability_manifest.specialist_capability_from_manifest(
        manifest, expected_id="spark-forge-aws"
    )
    assert derived.specialist.id == "spark-forge-aws"
    assert derived.capability("pyspark.static-analysis").finding_class == "static"
    assert derived.capability("spark.runtime-analysis").finding_class == ""
    # Forge Protocol is the invocation surface — no argv template invented.
    assert derived.capability("pyspark.static-analysis").entrypoint == []


def test_capability_manifest_derivation_binds_the_expected_id():
    from theforge import capability_manifest
    from theforge.contracts.manifest import ForgeManifest

    manifest = from_dict(
        ForgeManifest,
        {
            "id": "api-forge",
            "version": "1.0.0",
            "protocols": ["forge/v1"],
            "ops": ["describe", "health"],
        },
    )
    with pytest.raises(ContractError):
        capability_manifest.specialist_capability_from_manifest(
            manifest, expected_id="spark-forge-aws"
        )
