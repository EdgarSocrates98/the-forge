"""Deterministic delegation routing (lf-0028, PHASE 3).

Given a consumer's ``SpecialistDelegation`` declaration, a user intent and
the ``DiscoveryReport`` of ``discovery.py``, produce a *justified* plan —
or a named refusal. No LLM participates: matching is token-set arithmetic
over declared intents and capability ids/descriptions, ambiguity is a
status, never a guess, and the router never fans out to every declared
specialist — each pick names the declared intent(s) it serves, the
capability evidence that selected it, and the risk gate outcome.

Route inputs are data, not instructions: a specialist's declared intents or
capability description can influence *which declared option* is selected —
they cannot widen the risk gate, add providers the consumer did not
declare, or turn a refusal into a pick.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from theforge.contracts.specialist_capability import DeclaredCapability
from theforge.contracts.specialist_delegation import (
    DELEGATION_FAILURES,
    DelegationFailure,
    DelegationRisk,
    SpecialistDelegation,
)
from theforge.delegation_governance import (
    DelegationRefusal,
    ExecutionBudget,
    capability_risks,
    gate_capability,
)
from theforge.discovery import SpecialistDiscovery
from theforge.routing.signals import normalize_tokens

__all__ = [
    "DelegationPick",
    "DelegationPlan",
    "plan_delegation",
]

PlanStatus = Literal["planned", "ambiguous", "unavailable", "refused"]

_DEFAULT_BUDGET = ExecutionBudget()

# Discovery states mapped onto the failure taxonomy: an absent provider and
# an unverified one are both "provider-absent" (the plan explains the state
# in the detail); INCOMPATIBLE is version-incompatible; UNTRUSTED is a
# permission denial — it was *found* and is not allowed to run.
_STATE_FAILURE: dict[str, DelegationFailure] = {
    "NOT_INSTALLED": "provider-absent",
    "DISCOVERED": "provider-absent",
    "UNAVAILABLE": "provider-absent",
    "DEGRADED": "provider-absent",
    "INCOMPATIBLE": "version-incompatible",
    "UNTRUSTED": "permission-denied",
}

for _code in _STATE_FAILURE.values():
    assert _code in DELEGATION_FAILURES  # taxonomy drift guard

# Codes that make an empty plan a refusal (something *denied* the delegation)
# vs an unavailability (nothing eligible existed). Honest statuses: a missing
# provider is never dressed up as a denial, and a denial is never softened
# into "unavailable".
_DENIAL_FAILURES: frozenset[str] = frozenset(
    {"permission-denied", "policy-refusal", "cycle-detected", "budget-exhausted", "cancelled"}
)


@dataclass(frozen=True, kw_only=True)
class DelegationPick:
    """One selected specialist capability, with the evidence that chose it."""

    provider: str
    capability: str
    capability_version: str = ""
    risks: tuple[DelegationRisk, ...] = ()
    entrypoint: list[str] = field(default_factory=list)
    justification: list[str] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class DelegationPlan:
    """The router's answer: picks, refusals and an honest status.

    ``ambiguous`` carries the competing providers/capabilities in
    ``unknowns``; ``refused``/``unavailable`` name their codes in
    ``refusals``. A plan never contains an anonymous failure.
    """

    status: PlanStatus
    picks: list[DelegationPick] = field(default_factory=list)
    refusals: list[DelegationRefusal] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)


def _capability_tokens(capability: DeclaredCapability) -> set[str]:
    tokens = set(normalize_tokens(capability.id.replace(".", " ").replace("-", " ")))
    tokens.update(normalize_tokens(capability.description))
    return tokens


def _pick_capability(
    provider: str,
    capabilities: list[DeclaredCapability],
    intent_tokens: set[str],
) -> DeclaredCapability | DelegationRefusal:
    """Deterministic capability choice inside one verified specialist — a
    capability, or a named refusal (``capability-absent`` /
    ``insufficient-evidence``); never a silent guess."""
    if not capabilities:
        return DelegationRefusal(
            code="capability-absent",
            detail=f"{provider}: capability manifest declares no capabilities",
            provider=provider,
        )
    scored = sorted(
        ((len(intent_tokens & _capability_tokens(c)), c.id, c) for c in capabilities),
        key=lambda s: (-s[0], s[1]),
    )
    top_score = scored[0][0]
    tied = [s for s in scored if s[0] == top_score]
    if top_score > 0 and len(tied) > 1:
        return DelegationRefusal(
            code="insufficient-evidence",
            detail=(
                f"{provider}: capabilities tied on intent match: " + ", ".join(s[1] for s in tied)
            ),
            provider=provider,
        )
    if top_score == 0:
        if len(scored) == 1:
            return scored[0][2]
        return DelegationRefusal(
            code="insufficient-evidence",
            detail=(
                f"{provider}: no declared capability matched the intent "
                f"({len(scored)} candidates) — never a guess"
            ),
            provider=provider,
        )
    return scored[0][2]


def plan_delegation(
    intent: str,
    delegation: SpecialistDelegation,
    discovered: Sequence[SpecialistDiscovery],
    *,
    authorized_risks: frozenset[DelegationRisk] | set[DelegationRisk] = frozenset(),
    budget: ExecutionBudget = _DEFAULT_BUDGET,
) -> DelegationPlan:
    """Plan a delegation over *discovered* specialists — deterministic.

    ``discovered`` is the ``DiscoveryReport.entries`` of the lf-0027 scan;
    only ``VERIFIED`` entries with a parsed capability manifest are
    executable — every other state maps onto a named refusal.
    """
    policy = delegation.policy
    if policy.discovery == "off" or policy.execution == "forbidden":
        return DelegationPlan(
            status="refused",
            refusals=[
                DelegationRefusal(
                    code="policy-refusal",
                    detail=(
                        f"consumer {delegation.consumer!r} policy forbids delegation "
                        f"(discovery={policy.discovery}, execution={policy.execution})"
                    ),
                )
            ],
        )

    chain = delegation.chain
    if chain is not None and chain.cancelled:
        return DelegationPlan(
            status="refused",
            refusals=[
                DelegationRefusal(
                    code="cancelled",
                    detail=f"chain {chain.correlation_id} was cancelled",
                )
            ],
        )
    if chain is not None and chain.delegation_depth >= chain.max_hops:
        return DelegationPlan(
            status="refused",
            refusals=[
                DelegationRefusal(
                    code="budget-exhausted",
                    detail=(
                        f"hop budget exhausted: depth {chain.delegation_depth} "
                        f"at max_hops {chain.max_hops}"
                    ),
                )
            ],
        )
    visited = set(chain.visited_providers) | {delegation.consumer} if chain else set()

    by_id = {d.forge_id: d for d in discovered}
    intent_tokens = set(normalize_tokens(intent))
    refusals: list[DelegationRefusal] = []
    limitations: list[str] = []
    unknowns: list[str] = []

    # 1. eligibility: declared ∩ verified ∩ not-visited
    eligible: dict[str, SpecialistDiscovery] = {}
    for ref in sorted(delegation.specialists, key=lambda r: r.provider):
        entry = by_id.get(ref.provider)
        if entry is None:
            refusals.append(
                DelegationRefusal(
                    code="provider-absent",
                    detail=f"{ref.provider}: declared but never discovered",
                    provider=ref.provider,
                )
            )
            continue
        code = _STATE_FAILURE.get(entry.state)
        if entry.state != "VERIFIED":
            refusals.append(
                DelegationRefusal(
                    code=code or "provider-absent",
                    detail=(
                        f"{ref.provider}: discovery state {entry.state} is not VERIFIED"
                        + (f" ({'; '.join(entry.notes)})" if entry.notes else "")
                    ),
                    provider=ref.provider,
                )
            )
            continue
        if entry.capability_manifest is None:
            refusals.append(
                DelegationRefusal(
                    code="capability-absent",
                    detail=f"{ref.provider}: VERIFIED but no capability manifest parsed",
                    provider=ref.provider,
                )
            )
            continue
        if ref.provider in visited:
            refusals.append(
                DelegationRefusal(
                    code="cycle-detected",
                    detail=(
                        f"{ref.provider}: already visited in chain "
                        f"{chain.correlation_id if chain else ''} — delegation cycle refused"
                    ),
                    provider=ref.provider,
                )
            )
            continue
        eligible[ref.provider] = entry

    # 2. intent match on declared intents — a specialist is a candidate only
    #    when at least one of its declared intents is named by the task.
    matched: dict[str, list[str]] = {}  # provider -> matched declared intents
    for provider in eligible:
        decl = delegation.specialist(provider)
        assert decl is not None  # eligible ⊆ declared
        hits = [
            declared_intent
            for declared_intent in decl.intents
            if (tokens := set(normalize_tokens(declared_intent))) and tokens <= intent_tokens
        ]
        if hits:
            matched[provider] = sorted(hits)
        else:
            limitations.append(
                f"{provider}: not delegated — no declared intent matched the task "
                "(router never fans out to all specialists)"
            )

    # 3. per declared intent, a unique provider must answer — two providers
    #    serving the same declared intent is ambiguity, never a guess.
    intent_served: dict[str, str] = {}
    for provider, intents in matched.items():
        for declared_intent in intents:
            rival = intent_served.get(declared_intent)
            if rival is not None and rival != provider:
                unknowns.append(
                    f"intent {declared_intent!r} claimed by both {rival} and {provider}"
                )
            else:
                intent_served[declared_intent] = provider

    picks: list[DelegationPick] = []
    ambiguous = bool(unknowns)
    for provider in sorted(matched):
        entry = eligible[provider]
        intents = matched[provider]
        # Provider loses on *every* intent it declared when a rival also
        # claimed each of them — its selection evidence is gone.
        served = [i for i in intents if intent_served.get(i) == provider]
        if not served:
            continue
        manifest = entry.capability_manifest
        assert manifest is not None  # eligibility guarantees
        pick = _pick_capability(provider, manifest.capabilities, intent_tokens)
        if isinstance(pick, DelegationRefusal):
            refusals.append(pick)
            if pick.code == "insufficient-evidence" and "tied" in pick.detail:
                ambiguous = True
                unknowns.append(pick.detail)
            continue
        gate = gate_capability(capability_risks(pick), authorized=set(authorized_risks))
        if gate.decision == "deny":
            refusals.append(
                DelegationRefusal(
                    code="policy-refusal",
                    detail=f"{provider}/{pick.id}: {gate.reason}",
                    provider=provider,
                )
            )
            continue
        picks.append(
            DelegationPick(
                provider=provider,
                capability=pick.id,
                capability_version=pick.version or entry.version,
                risks=gate.risks,
                entrypoint=list(pick.entrypoint),
                justification=[
                    "declared intent(s) matched the task: " + ", ".join(served),
                    (
                        f"capability {pick.id!r}: "
                        f"{len(intent_tokens & _capability_tokens(pick))} intent "
                        "token(s) matched id/description"
                    ),
                    f"risk gate: {gate.reason} (risks: {', '.join(gate.risks)})",
                    f"provider version {entry.version}, state {entry.state}",
                ],
            )
        )

    if len(picks) > budget.max_providers:
        overflow = picks[budget.max_providers :]
        picks = picks[: budget.max_providers]
        limitations.append(
            f"provider budget {budget.max_providers}: not delegated to "
            + ", ".join(p.provider for p in overflow)
        )

    if ambiguous:
        status: PlanStatus = "ambiguous"
    elif picks:
        status = "planned"
    elif any(r.code in _DENIAL_FAILURES for r in refusals):
        status = "refused"
    else:
        status = "unavailable"
    if status == "unavailable" and not matched:
        unknowns.append("no declared intent matched the task intent")
    return DelegationPlan(
        status=status,
        picks=picks,
        refusals=refusals,
        limitations=limitations,
        unknowns=unknowns,
    )
