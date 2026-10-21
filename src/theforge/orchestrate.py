"""The orchestrator lane (lf-0031, PHASE 9+12): intent -> discovered
specialists -> a justified, governed delegation plan -> consolidated report.

This is not a second orchestrator. It composes surfaces that already exist:

- ``discovery.discover_specialists`` (lf-0027) decides which specialists
  are VERIFIED on this machine;
- ``delegation_router.plan_delegation`` (lf-0028) picks capabilities by
  declared intent with justification, ambiguity and named refusals;
- ``delegation_governance`` gates risk, mints the chain (correlation id,
  visited providers, hop/timeout budgets) and resolves entrypoint argv;
- ``delegation.execute`` (FASE 5) runs the typed argv — the same governed
  channel ``task run`` uses;
- ``contracts.evidence_handoff`` bounds and seals what comes back;
- ``contracts.orchestration`` is the consolidated report: STATIC /
  RUNTIME / ARCHITECTURAL / UNSPECIFIED findings, CORRELATED marks,
  UNRESOLVED gaps, RECOMMENDED next steps, provenance and receipts.

Honest-behavior rules carried from the spec: every specialist is an
optional delegate (a forge never gains a mandatory dependency on another);
a specialist that is absent or unverifiable is a named refusal, never a
guess; and a capability whose declared ``requires`` inputs the caller did
not provide is filtered out of the plan — the lane never forces a
diagnostic (e.g. runtime-log analysis) without adequate declared inputs.
"""

from __future__ import annotations

import dataclasses
import json
import shutil
import sys
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from theforge import delegation, knowledge
from theforge.contracts.base import ContractError, from_dict, to_dict
from theforge.contracts.canonical import sha256_of, utc_now
from theforge.contracts.evidence_handoff import (
    EVIDENCE_HANDOFF_SCHEMA,
    EvidenceHandoff,
)
from theforge.contracts.orchestration import (
    OrchestrationEntry,
    OrchestrationFinding,
    OrchestrationProvenance,
    OrchestrationRecommendation,
    OrchestrationReport,
    OrchestrationUnresolved,
    ReportClass,
)
from theforge.contracts.specialist_capability import DeclaredCapability
from theforge.contracts.specialist_delegation import (
    DELEGATION_SLUG,
    DelegationFailure,
    DelegationPolicy,
    DelegationRisk,
    SpecialistDelegation,
    SpecialistRef,
)
from theforge.delegation_governance import (
    DelegationRefusal,
    ExecutionBudget,
    admit_hop,
    argv_problems,
    capability_risks,
    gate_capability,
    resolve_capability_argv,
    start_chain,
    verify_integrity,
)
from theforge.delegation_router import DelegationPick, DelegationPlan, plan_delegation
from theforge.discovery import DiscoveryReport, SpecialistDiscovery, discover_specialists
from theforge.routing.signals import normalize_tokens
from theforge.security.redact import redact

__all__ = [
    "ORCHESTRATIONS_DIR",
    "Orchestration",
    "build_delegation",
    "orchestrate_plan",
    "orchestrate_run",
    "persist_report",
]

ORCHESTRATIONS_DIR = ".forge/orchestrations"

_CLASS_MAP: dict[str, ReportClass] = {
    "static": "STATIC",
    "runtime": "RUNTIME",
    "architectural": "ARCHITECTURAL",
}

# DelegationResult stage -> the failure taxonomy, when it is not a finish.
_STAGE_FAILURE: dict[str, DelegationFailure] = {
    "FAILED": "runtime-error",
    "BLOCKED": "invalid-input",
}


@dataclass(frozen=True, kw_only=True)
class Orchestration:
    """One orchestrate pass: the report plus the evidence behind it."""

    report: OrchestrationReport
    discovery: DiscoveryReport
    plan: DelegationPlan


# --- the consumer declaration -------------------------------------------------


def _intent_slug(phrase: str) -> str | None:
    """``"spark on aws"`` -> ``"spark.on.aws"``; None when a segment cannot
    be represented in the DELEGATION_SLUG vocabulary (dropped, not mangled)."""
    tokens = normalize_tokens(phrase)
    if not tokens:
        return None
    slug = ".".join(t.replace("_", "-") for t in tokens)
    return slug if DELEGATION_SLUG.match(slug) else None


def build_delegation(
    *,
    consumer: str = "the-forge",
    workspace_root: Path | None = None,
    knowledge_dir: Path | None = None,
) -> SpecialistDelegation:
    """The default ``theforge/SpecialistDelegation/v1`` the CLI uses.

    Every catalog specialist becomes an OPTIONAL delegate — a forge never
    gains a mandatory dependency on another (spec: integrations are
    optional by construction). Declared intents come from the knowledge
    pack's authored ``intents`` + ``technologies``, slugified into the
    delegation vocabulary; a specialist without a pack declares no intents
    and is never picked (its absence is a named refusal, not silence).
    """
    packs = knowledge.load_all(knowledge_dir)
    refs: list[SpecialistRef] = []
    from theforge import specialists as spec_mod

    for forge_id in spec_mod.catalog_ids(workspace_root):
        if forge_id == consumer:
            # A consumer never declares itself a delegate — that is a cycle
            # at depth 0, not a specialist.
            continue
        pack = packs.get(forge_id)
        intents: set[str] = set()
        if pack is not None:
            for phrase in (*pack.intents, *pack.technologies):
                slug = _intent_slug(phrase)
                if slug is not None:
                    intents.add(slug)
        refs.append(
            SpecialistRef(provider=forge_id, optional=True, intents=sorted(intents))
        )
    return SpecialistDelegation(
        consumer=consumer,
        specialists=refs,
        policy=DelegationPolicy(
            discovery="runtime", execution="governed", preserve_evidence=True
        ),
    )


# --- the plan lane -------------------------------------------------------------


def _capability_of(
    pick: DelegationPick, entries: list[SpecialistDiscovery]
) -> DeclaredCapability | None:
    entry = next((e for e in entries if e.forge_id == pick.provider), None)
    if entry is None or entry.capability_manifest is None:
        return None
    return entry.capability_manifest.capability(pick.capability)


def _filter_inputs(
    plan: DelegationPlan,
    entries: list[SpecialistDiscovery],
    inputs: frozenset[str] | set[str],
) -> DelegationPlan:
    """Drop picks whose declared ``requires`` the caller did not satisfy.

    ``requires`` names declared input kinds (e.g. a runtime log class); a
    capability that cannot get its inputs is an ``insufficient-evidence``
    refusal in the plan — the lane never forces a diagnostic on inadequate
    data. Capabilities with empty ``requires`` are unaffected.
    """
    keep: list[DelegationPick] = []
    refusals = list(plan.refusals)
    for pick in plan.picks:
        cap = _capability_of(pick, entries)
        missing = sorted(set(cap.requires) - inputs) if cap is not None else []
        if cap is not None and missing:
            refusals.append(
                DelegationRefusal(
                    code="insufficient-evidence",
                    provider=pick.provider,
                    detail=(
                        f"{pick.provider}/{pick.capability}: declared inputs missing "
                        f"({', '.join(missing)}) — never run a diagnostic without "
                        "the data it requires (--input to declare)"
                    ),
                )
            )
            continue
        keep.append(pick)
    status = plan.status
    if not keep and plan.picks:
        status = (
            "refused"
            if any(r.code in ("policy-refusal", "permission-denied") for r in refusals)
            else "unavailable"
        )
    return replace(plan, status=status, picks=keep, refusals=refusals)


def orchestrate_plan(
    intent: str,
    *,
    delegation_doc: SpecialistDelegation | None = None,
    workspace_root: Path | None = None,
    inputs: frozenset[str] | set[str] = frozenset(),
    authorized_risks: frozenset[DelegationRisk] | set[DelegationRisk] = frozenset(),
    budget: ExecutionBudget | None = None,
    probe: bool = True,
    allow_unverified: bool = False,
    report: DiscoveryReport | None = None,
    **discovery_kwargs: Any,
) -> Orchestration:
    """Intent + context -> deterministic, justified delegation plan.

    ``delegation_doc`` overrides the default consumer declaration (the
    ``--delegation`` file of the CLI); ``inputs`` declares the artifact
    kinds available to capabilities (the ``--input`` flags).
    """
    if report is None:
        report = discover_specialists(
            workspace_root=workspace_root,
            probe=probe,
            allow_unverified=allow_unverified,
            **discovery_kwargs,
        )
    decl = delegation_doc or build_delegation(workspace_root=workspace_root)
    plan = plan_delegation(
        intent,
        decl,
        report.entries,
        authorized_risks=authorized_risks,
        budget=budget or ExecutionBudget(),
    )
    plan = _filter_inputs(plan, report.entries, set(inputs))
    return Orchestration(report=_plan_report(intent, plan, report), discovery=report, plan=plan)


def _entry_class(pick: DelegationPick, entries: list[SpecialistDiscovery]) -> ReportClass:
    cap = _capability_of(pick, entries)
    if cap is None:
        return "UNSPECIFIED"
    return _CLASS_MAP.get(cap.finding_class, "UNSPECIFIED")


def _plan_report(intent: str, plan: DelegationPlan, report: DiscoveryReport) -> OrchestrationReport:
    entries = [
        OrchestrationEntry(
            provider=p.provider,
            capability=p.capability,
            status="planned",
            finding_class=_entry_class(p, report.entries),
            risks=list(p.risks),
            justification=list(p.justification),
            command=list(p.entrypoint),
        )
        for p in plan.picks
    ]
    unresolved = [
        OrchestrationUnresolved(code=r.code, detail=r.detail, provider=r.provider)
        for r in plan.refusals
    ]
    return OrchestrationReport(
        kind="plan",
        intent=intent,
        generated_at=utc_now(),
        plan_status=plan.status,
        entries=entries,
        unresolved=unresolved,
        recommended=_recommend(plan, report),
        provenance=OrchestrationProvenance(
            discovery_digest=report.context_digest,
            plan_sha256=sha256_of(dataclasses.asdict(plan)),
        ),
        limitations=[*report.limitations, *plan.limitations],
        unknowns=plan.unknowns,
    )


# --- the governed run lane ------------------------------------------------------


def _cli_argv(entry: SpecialistDiscovery) -> list[str] | None:
    """Resolve the specialist's cli argv: agentic manifest cli, then the
    provider id itself on PATH. Never a guess — None when nothing resolves."""
    candidates: list[str] = []
    if entry.agentic_manifest is not None and entry.agentic_manifest.cli:
        candidates.append(entry.agentic_manifest.cli)
    pack = knowledge.knowledge_for(entry.forge_id)
    if pack is not None and pack.binary:
        candidates.append(pack.binary)
    candidates.append(entry.forge_id)
    for name in candidates:
        resolved = shutil.which(name)
        if resolved:
            return [resolved]
    return None


def _checkout_path(entry: SpecialistDiscovery) -> str | None:
    for ev in entry.sources:
        if ev.source in ("checkout", "configured-path") and ev.path:
            return ev.path
    return None


def _handoff_from_output(lines: list[str]) -> EvidenceHandoff | None | str:
    """Extract a ``theforge/EvidenceHandoff/v1`` document from a run's stdout
    tail: one JSON object per line, last one wins. ``None`` = none emitted;
    ``str`` = a malformed/invalid document (honest, never silent)."""
    found: EvidenceHandoff | None = None
    error: str | None = None
    for line in lines:
        text = line.strip()
        if not text.startswith("{") or EVIDENCE_HANDOFF_SCHEMA not in text:
            continue
        try:
            doc = json.loads(text)
        except json.JSONDecodeError:
            error = "handoff-looking line is not JSON"
            continue
        if not isinstance(doc, dict) or doc.get("schema") != EVIDENCE_HANDOFF_SCHEMA:
            continue
        try:
            found = from_dict(EvidenceHandoff, doc, "$")
        except ContractError as exc:
            error = f"handoff document invalid: {exc}"
            found = None
    if found is not None and not verify_integrity(found):
        # An unsealed or tampered envelope is evidence-shaped but unverifiable.
        error = "handoff integrity missing or mismatched — treated as unverified"
        return error
    return error if error is not None and found is None else found


def orchestrate_run(
    intent: str,
    *,
    delegation_doc: SpecialistDelegation | None = None,
    workspace_root: Path | None = None,
    target: str | None = None,
    inputs: frozenset[str] | set[str] = frozenset(),
    authorized_risks: frozenset[DelegationRisk] | set[DelegationRisk] = frozenset(),
    budget: ExecutionBudget | None = None,
    correlation_id: str | None = None,
    probe: bool = True,
    allow_unverified: bool = False,
    report: DiscoveryReport | None = None,
    executor: Any = delegation.execute,
    **discovery_kwargs: Any,
) -> Orchestration:
    """Plan, then execute each pick through the governed delegation channel.

    Execution is argv-only and sequential: each pick resolves its declared
    ``entrypoint`` template (``{cli}``/``{python}``/``{checkout}``/
    ``{target}``) through ``delegation_governance.resolve_capability_argv``
    and runs through ``delegation.execute`` — never shell=True. A pick with
    no declared entrypoint (a Forge-Protocol-only capability) is honestly
    ``prepared``: the report says it was not executed, never fakes a run.
    ``executor`` is injectable for tests.
    """
    correlation = correlation_id or f"orch-{uuid.uuid4().hex[:12]}"
    outcome = orchestrate_plan(
        intent,
        delegation_doc=delegation_doc,
        workspace_root=workspace_root,
        inputs=inputs,
        authorized_risks=authorized_risks,
        budget=budget,
        probe=probe,
        allow_unverified=allow_unverified,
        report=report,
        **discovery_kwargs,
    )
    plan, discovered = outcome.plan, outcome.discovery
    decl = delegation_doc or build_delegation(workspace_root=workspace_root)
    target_dir = target or (str(workspace_root) if workspace_root else ".")
    chain_budget = budget or ExecutionBudget()

    chained = start_chain(
        decl,
        correlation_id=correlation,
        max_hops=chain_budget.max_hops,
        timeout_budget_s=chain_budget.timeout_budget_s,
    )

    entries: list[OrchestrationEntry] = []
    unresolved: list[OrchestrationUnresolved] = [
        OrchestrationUnresolved(code=r.code, detail=r.detail, provider=r.provider)
        for r in plan.refusals
    ]
    findings: list[OrchestrationFinding] = []
    tasks: list[str] = []
    handoffs: list[EvidenceHandoff] = []

    for pick in plan.picks:
        entry = next((e for e in discovered.entries if e.forge_id == pick.provider), None)
        cap = _capability_of(pick, discovered.entries)
        cls = _entry_class(pick, discovered.entries)
        # chain admission: the hop is refused, never silently skipped
        admitted = admit_hop(chained, pick.provider, elapsed_s=0)
        if isinstance(admitted, DelegationRefusal):
            entries.append(
                OrchestrationEntry(
                    provider=pick.provider,
                    capability=pick.capability,
                    status="refused",
                    finding_class=cls,
                    risks=list(pick.risks),
                    justification=list(pick.justification),
                    notes=[admitted.detail],
                )
            )
            unresolved.append(
                OrchestrationUnresolved(
                    code=admitted.code, detail=admitted.detail, provider=pick.provider
                )
            )
            continue
        chained = admitted
        # defense in depth: re-gate the declared risks at execution time
        if cap is not None:
            gate = gate_capability(capability_risks(cap), authorized=set(authorized_risks))
            if gate.decision == "deny":
                entries.append(
                    OrchestrationEntry(
                        provider=pick.provider,
                        capability=pick.capability,
                        status="refused",
                        finding_class=cls,
                        risks=list(pick.risks),
                        justification=list(pick.justification),
                        notes=[gate.reason],
                    )
                )
                unresolved.append(
                    OrchestrationUnresolved(
                        code="policy-refusal", detail=gate.reason, provider=pick.provider
                    )
                )
                continue
        if not pick.entrypoint:
            entries.append(
                OrchestrationEntry(
                    provider=pick.provider,
                    capability=pick.capability,
                    status="prepared",
                    finding_class=cls,
                    risks=list(pick.risks),
                    justification=list(pick.justification),
                    notes=[
                        "no argv entrypoint declared — the capability is reachable "
                        "through the specialist's Forge Protocol execute surface only"
                    ],
                )
            )
            continue
        argv_or_refusal = resolve_capability_argv(
            pick.entrypoint,
            cli_argv=_cli_argv(entry) if entry is not None else None,
            python=sys.executable,
            checkout=_checkout_path(entry) if entry is not None else None,
            target=target_dir,
        )
        if isinstance(argv_or_refusal, DelegationRefusal):
            entries.append(
                OrchestrationEntry(
                    provider=pick.provider,
                    capability=pick.capability,
                    status="refused",
                    finding_class=cls,
                    risks=list(pick.risks),
                    justification=list(pick.justification),
                    command=list(pick.entrypoint),
                    notes=[argv_or_refusal.detail],
                )
            )
            unresolved.append(
                OrchestrationUnresolved(
                    code=argv_or_refusal.code,
                    detail=argv_or_refusal.detail,
                    provider=pick.provider,
                )
            )
            continue
        argv: list[str] = argv_or_refusal
        if problems := argv_problems(argv):
            detail = "resolved argv invalid: " + "; ".join(problems)
            entries.append(
                OrchestrationEntry(
                    provider=pick.provider,
                    capability=pick.capability,
                    status="refused",
                    finding_class=cls,
                    risks=list(pick.risks),
                    justification=list(pick.justification),
                    command=argv,
                    notes=[detail],
                )
            )
            unresolved.append(
                OrchestrationUnresolved(code="invalid-input", detail=detail, provider=pick.provider)
            )
            continue
        request = delegation.new_request(
            intent=intent,
            provider=pick.provider,
            execution_mode="DIRECT_CAPABILITY",
            command=argv,
            target=target_dir,
            constraints=[f"correlation_id={correlation}"],
            expected_outputs=[EVIDENCE_HANDOFF_SCHEMA],
            budget={"timeout_s": cap.timeout_s} if cap and cap.timeout_s else {},
        )
        result = executor(request, cwd=target_dir)
        tasks.append(result.task_id)
        notes: list[str] = []
        handoff_status = "absent"
        if result.stage == "COMPLETED":
            extracted = _handoff_from_output(result.stdout_tail)
            if isinstance(extracted, EvidenceHandoff):
                handoffs.append(extracted)
                handoff_status = "received"
            elif isinstance(extracted, str):
                handoff_status = "invalid"
                notes.append(extracted)
                unresolved.append(
                    OrchestrationUnresolved(
                        code="invalid-output", detail=extracted, provider=pick.provider
                    )
                )
            else:
                notes.append(
                    "run completed without an EvidenceHandoff document — "
                    "no findings consolidated"
                )
        elif result.stage in _STAGE_FAILURE:
            detail = "; ".join(result.limitations) or f"delegation {result.stage}"
            unresolved.append(
                OrchestrationUnresolved(
                    code=_STAGE_FAILURE[result.stage], detail=detail, provider=pick.provider
                )
            )
        entries.append(
            OrchestrationEntry(
                provider=pick.provider,
                capability=pick.capability,
                status=result.stage.lower(),
                finding_class=cls,
                risks=list(pick.risks),
                justification=list(pick.justification),
                command=argv,
                delegation_stage=result.stage,
                handoff_status=handoff_status,
                notes=notes + list(result.evidence[:2]),
            )
        )

    findings = _consolidate_findings(handoffs, plan, discovered.entries)
    run_report = OrchestrationReport(
        kind="run",
        intent=intent,
        correlation_id=correlation,
        generated_at=utc_now(),
        plan_status=plan.status,
        entries=entries,
        findings=findings,
        unresolved=unresolved,
        recommended=_recommend(plan, discovered),
        provenance=OrchestrationProvenance(
            discovery_digest=discovered.context_digest,
            plan_sha256=sha256_of(dataclasses.asdict(plan)),
            delegation_tasks=tasks,
        ),
        limitations=[*discovered.limitations, *plan.limitations],
        unknowns=plan.unknowns,
    )
    return Orchestration(report=run_report, discovery=discovered, plan=plan)


def _consolidate_findings(
    handoffs: list[EvidenceHandoff],
    plan: DelegationPlan,
    entries: list[SpecialistDiscovery],
) -> list[OrchestrationFinding]:
    """Group handoff findings by id; mark multi-provider ones CORRELATED.

    Correlation is co-occurrence, never promoted to independent proof: the
    finding keeps each source's declared severity/confidence (the most
    severe wins the row, providers list the rest).
    """
    severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    confidence_rank = {"CONFIRMED": 0, "LIKELY": 1, "POSSIBLE": 2, "UNKNOWN": 3}
    picks = {p.provider: p for p in plan.picks}
    groups: dict[str, list[tuple[EvidenceHandoff, Any]]] = {}
    for handoff in handoffs:
        for finding in handoff.findings:
            groups.setdefault(finding.id, []).append((handoff, finding))
    out: list[OrchestrationFinding] = []
    for fid in sorted(groups):
        items = groups[fid]
        items.sort(
            key=lambda t: (
                severity_rank.get(t[1].severity, 9),
                confidence_rank.get(t[1].confidence, 9),
                t[0].source_provider,
            )
        )
        head = items[0][1]
        providers = sorted({h.source_provider for h, _f in items})
        caps = sorted({h.capability for h, _f in items})
        pick = picks.get(items[0][0].source_provider)
        cls: ReportClass = "UNSPECIFIED"
        if pick is not None:
            cls = _entry_class(pick, entries)
        refs: list[str] = []
        for _h, f in items:
            for r in f.evidence_refs:
                if r not in refs:
                    refs.append(r)
        out.append(
            OrchestrationFinding(
                id=fid,
                finding_class=cls,
                severity=head.severity,
                confidence=head.confidence,
                summary=head.summary,
                providers=providers,
                capabilities=caps,
                correlated=len(providers) > 1,
                evidence_refs=refs[:16],
            )
        )
    return out


# --- recommendations -------------------------------------------------------------


def _recommend(plan: DelegationPlan, report: DiscoveryReport) -> list[OrchestrationRecommendation]:
    """Deterministic next steps derived from refusals — never invented gains."""
    recs: list[OrchestrationRecommendation] = []
    for refusal in plan.refusals:
        provider = refusal.provider
        if refusal.code == "provider-absent":
            entry = report.entry(provider) if provider else None
            state = entry.state if entry else "never discovered"
            recs.append(
                OrchestrationRecommendation(
                    action=(
                        f"install {provider} or configure its path — optional, "
                        "the plan does not block on it"
                    ),
                    why=f"declared delegate absent: discovery state {state} ({refusal.detail})",
                    provider=provider,
                )
            )
        elif refusal.code == "capability-absent":
            recs.append(
                OrchestrationRecommendation(
                    action=(
                        f"upgrade {provider} or its adapter to emit a "
                        "SpecialistCapability manifest"
                    ),
                    why=refusal.detail,
                    provider=provider,
                )
            )
        elif refusal.code == "policy-refusal":
            recs.append(
                OrchestrationRecommendation(
                    action=(
                        "authorize the missing risk levels (--authorize RISK) or narrow "
                        "the intent to read-only capabilities"
                    ),
                    why=refusal.detail,
                    provider=provider,
                )
            )
        elif refusal.code == "permission-denied":
            recs.append(
                OrchestrationRecommendation(
                    action=f"grant trust to {provider} in providers.toml or use --allow-unverified",
                    why=refusal.detail,
                    provider=provider,
                )
            )
        elif refusal.code == "version-incompatible":
            recs.append(
                OrchestrationRecommendation(
                    action=f"align {provider} with its declared compatibility window",
                    why=refusal.detail,
                    provider=provider,
                )
            )
        elif refusal.code == "insufficient-evidence":
            recs.append(
                OrchestrationRecommendation(
                    action="declare the required inputs (--input) or disambiguate the intent",
                    why=refusal.detail,
                    provider=provider,
                )
            )
    if plan.status == "ambiguous":
        recs.append(
            OrchestrationRecommendation(
                action="disambiguate the intent — the competing claims are listed in unknowns",
                why="routing ambiguity: deterministic rules refuse to guess",
            )
        )
    if plan.status == "unavailable" and not plan.picks:
        recs.append(
            OrchestrationRecommendation(
                action=(
                    "no verified specialist serves this intent — install one "
                    "or broaden the delegation declaration"
                ),
                why="every declared specialist was absent, unverified or unmatched",
            )
        )
    return recs


# --- persistence -------------------------------------------------------------------


def persist_report(report: OrchestrationReport, root: Path) -> Path:
    """Persist the report redacted under ``.forge/orchestrations/`` — the
    receipt the caller references. A report containing secret-shaped values
    is refused, never written."""
    document = to_dict(report)
    if redact(document) != document:
        raise ContractError(
            "orchestration report contains secret-shaped values — refused to persist"
        )
    directory = root / ORCHESTRATIONS_DIR
    directory.mkdir(parents=True, exist_ok=True)
    name = f"{report.correlation_id or 'plan'}-{report.generated_at.replace(':', '-')}.json"
    path = directory / name
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(document, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)
    return path
