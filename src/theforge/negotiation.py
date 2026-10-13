"""Capability negotiation engine (Cycle 4, Waves A/B).

Deterministic, local, evidence-first: a ``CapabilityRequirement`` is negotiated
against each provider manifest's declared surface — never inferred from names.
Hard gates (protocol, policy, operation class, runtime, required technology,
required evidence, required features) reject as ``INCOMPATIBLE``; what the
manifest does not declare negotiates as ``unknown`` and degrades the result to
``PARTIAL`` — absent data is never silently satisfied.

Soft signals (measured history) only rank results that already passed every
gate; a clean ``FULL`` against a provider with no history still beats an
``INCOMPATIBLE`` with perfect history (§9, §90).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from theforge.contracts import (
    Capability,
    CapabilityNegotiationResult,
    CapabilityOffer,
    CapabilityRequirement,
    ForgeManifest,
    ProviderPerformance,
)
from theforge.contracts.canonical import utc_now
from theforge.contracts.features import supported_features
from theforge.contracts.negotiation import (
    _OPERATION_RANK,
    DimensionMatch,
    HistoryMaturity,
    NegotiationState,
)
from theforge.contracts.strategy import StrategyPolicy
from theforge.contracts.types import TRUST_RANK
from theforge.meta import PRODUCER
from theforge.registry.registry import RegistryRecord

__all__ = ["negotiate", "negotiate_all", "feature_satisfied", "maturity"]

# Cold/warming/mature thresholds on measured run counts (§44, §55).
_WARMING_RUNS = 3
_MATURE_RUNS = 8

_MUTATING = frozenset({"local_mutation", "external_mutation", "destructive"})

_DIM_ORDER = {"none": 0, "partial": 1, "unknown": 2, "full": 3, "not_applicable": 4}
# A fresh result's dimensions: demands the engine did not evaluate stay
# ``unknown`` (capability/protocol/policy) or ``not_applicable`` (the rest).
_BLANK_DIMS: dict[str, DimensionMatch] = {
    "capability_match": "unknown",
    "protocol_match": "unknown",
    "policy_match": "unknown",
    "runtime_match": "not_applicable",
    "technology_match": "not_applicable",
    "evidence_match": "not_applicable",
    "artifact_match": "not_applicable",
    "feature_match": "not_applicable",
}
_STATE_RANK: Mapping[NegotiationState, int] = {
    "INCOMPATIBLE": 0,
    "UNRESOLVED": 1,
    "UNSUPPORTED": 2,
    "PARTIAL": 3,
    "FULL": 4,
}
_HISTORY_RANK: Mapping[HistoryMaturity, int] = {
    "absent": 0,
    "stale": 0,
    "cold": 1,
    "warming": 2,
    "mature": 3,
}


def feature_satisfied(declared: frozenset[str] | set[str], required: str) -> bool:
    """``name/vN`` satisfied by the same name at major >= N (additive versioning)."""
    name, _, major = required.rpartition("/v")
    if not name or not major.isdigit():
        return required in declared
    want = int(major)
    for feature in declared:
        fname, _, fmajor = feature.rpartition("/v")
        if fname == name and fmajor.isdigit() and int(fmajor) >= want:
            return True
    return False


def maturity(
    performance: ProviderPerformance | None, provider: str, capability: str, surface: str | None
) -> HistoryMaturity:
    """Measured-history maturity scoped to the exact surface (§42-44).

    ``stale`` when runs exist for the provider/capability but only against a
    different surface fingerprint — surface change invalidates history (§43).
    """
    if performance is None:
        return "absent"
    exact = next(
        (
            e
            for e in performance.entries
            if e.provider == provider and e.capability == capability and e.surface == surface
        ),
        None,
    )
    if exact is None:
        touched = any(
            e.provider == provider and e.capability == capability for e in performance.entries
        )
        return "stale" if touched and surface is not None else "absent"
    if exact.runs >= _MATURE_RUNS:
        return "mature"
    if exact.runs >= _WARMING_RUNS:
        return "warming"
    return "cold"


@dataclass
class _Verdict:
    """The mutable accumulator a negotiation fills before the frozen result."""

    state: NegotiationState = "UNRESOLVED"
    capability: str | None = None
    dimensions: dict[str, DimensionMatch] = field(default_factory=lambda: dict(_BLANK_DIMS))
    history: HistoryMaturity = "absent"
    matched: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    policy_conflicts: list[str] = field(default_factory=list)


def negotiate(
    requirement: CapabilityRequirement,
    record: RegistryRecord,
    *,
    performance: ProviderPerformance | None = None,
) -> CapabilityNegotiationResult:
    """Negotiate one requirement against one provider record (deterministic)."""
    provider = record.entry.id
    surface = record.surface.surface_fingerprint if record.surface else None
    v = _Verdict()

    manifest = record.manifest
    if manifest is None:
        v.missing.append("manifest")
        v.limitations.append(f"{provider}: {record.state} — no manifest to negotiate")
        return _result(requirement, record, surface, v)

    resolved = manifest.resolve(requirement.capability)
    if resolved is None:
        v.state = "UNSUPPORTED"
        v.missing.append(f"capability:{requirement.capability}")
        v.dimensions["capability_match"] = "none"
        return _result(requirement, record, surface, v)
    capability, via_alias = resolved
    v.capability = capability.id
    v.matched.append(
        f"capability:{requirement.capability}->{capability.id}"
        if via_alias
        else f"capability:{capability.id}"
    )
    v.dimensions["capability_match"] = "full"
    if capability.state in ("heuristic", "unresolved"):
        v.limitations.append(f"capability_state:{capability.state}")

    if _hard_gates(requirement, manifest, capability, record, v) is not None:
        v.state = "INCOMPATIBLE"
        return _result(requirement, record, surface, v)

    _soft_dimensions(requirement, manifest, capability, v)
    if performance is not None:
        v.history = maturity(performance, provider, capability.id, surface)
    v.state = _state(v.dimensions, v.missing)
    return _result(requirement, record, surface, v)


def _result(
    requirement: CapabilityRequirement, record: RegistryRecord, surface: str | None, v: _Verdict
) -> CapabilityNegotiationResult:
    return CapabilityNegotiationResult(
        producer=PRODUCER,
        created_at=utc_now(),
        requirement=requirement,
        provider=record.entry.id,
        state=v.state,
        capability=v.capability,
        dimensions=v.dimensions,
        history=v.history,
        matched=sorted(v.matched),
        missing=sorted(set(v.missing)),
        limitations=v.limitations,
        policy_conflicts=sorted(set(v.policy_conflicts)),
        surface_fingerprint=surface,
    )


def _features(manifest: ForgeManifest, capability: Capability) -> frozenset[str]:
    offer = capability.offer
    return supported_features(manifest) | frozenset(offer.features if offer else ())


def _produces(capability: Capability, offer: CapabilityOffer | None) -> set[str]:
    return set(capability.relations.produces) | set(offer.produces_evidence if offer else ())


def _hard_gates(
    requirement: CapabilityRequirement,
    manifest: ForgeManifest,
    capability: Capability,
    record: RegistryRecord,
    v: _Verdict,
) -> str | None:
    """Evaluate hard gates (§9); on failure name the conflicts and return the gate."""
    trust = record.entry.trust
    if trust == "blocked" or (
        requirement.minimum_trust is not None
        and TRUST_RANK[trust] > TRUST_RANK[requirement.minimum_trust]
    ):
        v.policy_conflicts.append(f"trust:{trust}")
        v.dimensions["policy_match"] = "none"
        return "policy"
    v.dimensions["policy_match"] = "full"

    if "forge/v1" not in manifest.protocols:
        v.missing.append("protocol:forge/v1")
        v.dimensions["protocol_match"] = "none"
        return "protocol"

    supported = _features(manifest, capability)
    feature_missing = [
        f for f in requirement.protocol_features if not feature_satisfied(supported, f)
    ]
    if feature_missing:
        v.missing.extend(f"feature:{f}" for f in feature_missing)
        v.dimensions["protocol_match"] = "none"
        return "features"
    v.dimensions["protocol_match"] = "full"

    ceiling = requirement.operation_class_ceiling
    if ceiling and _OPERATION_RANK[capability.operation_class] > _OPERATION_RANK[ceiling]:
        v.policy_conflicts.append(f"operation_class:{capability.operation_class}>{ceiling}")
        return "operation_class"
    if not requirement.mutation_allowed and capability.operation_class in _MUTATING:
        v.policy_conflicts.append(f"mutation:{capability.operation_class}")
        return "mutation"

    offer = capability.offer
    if offer is not None and offer.technologies and requirement.technologies:
        tech_missing = [t for t in requirement.technologies if t not in offer.technologies]
        if tech_missing:
            v.missing.extend(f"technology:{t}" for t in tech_missing)
            return "technology"

    # Declared evidence coverage gates only when declared AND lacking; undeclared
    # degrades to ``unknown`` in soft dims below, never to a refusal.
    produces = _produces(capability, offer)
    if produces and requirement.required_evidence:
        ev_missing = [e for e in requirement.required_evidence if e not in produces]
        if ev_missing:
            v.missing.extend(f"evidence:{e}" for e in ev_missing)
            return "evidence"

    runtime = _runtime_gate(requirement, manifest, offer)
    if runtime is not None:
        v.policy_conflicts.append(runtime)
        v.dimensions["runtime_match"] = "none"
        return "runtime"
    return None


def _runtime_gate(
    requirement: CapabilityRequirement, manifest: ForgeManifest, offer: CapabilityOffer | None
) -> str | None:
    offline = offer.offline if offer and offer.offline is not None else manifest.execution.offline
    network = (
        offer.network_required
        if offer and offer.network_required is not None
        else manifest.execution.requires_network
    )
    credentials = offer.credentials_required if offer else None
    if requirement.offline_required and not offline:
        return "runtime:offline_required"
    if not requirement.network_allowed and network:
        return "runtime:network_denied"
    if not requirement.credentials_allowed and credentials:
        return "runtime:credentials_denied"
    return None


def _covered(required: list[str], declared: list[str] | set[str]) -> DimensionMatch:
    """Set-cover match: required ⊆ declared → full; nothing declared → unknown."""
    if not required:
        return "not_applicable"
    if not declared:
        return "unknown"
    missing = [item for item in required if item not in declared]
    return "full" if not missing else ("partial" if len(missing) < len(required) else "none")


def _soft_dimensions(
    requirement: CapabilityRequirement, manifest: ForgeManifest, capability: Capability, v: _Verdict
) -> None:
    """Soft dimensions + the explicit ``missing`` entries for unknown demands."""
    offer = capability.offer
    dims = v.dimensions

    missing_actions = [a for a in requirement.required_actions if a not in capability.actions]
    if missing_actions:
        dims["capability_match"] = "partial"
        v.missing.extend(f"action:{a}" for a in missing_actions)

    dims["technology_match"] = _covered(
        requirement.technologies, list(offer.technologies) if offer else []
    )
    dims["evidence_match"] = _covered(requirement.required_evidence, _produces(capability, offer))
    consumes = set(capability.relations.consumes) | set(
        offer.consumes_artifact_types if offer else ()
    )
    inputs = _covered(requirement.input_artifact_types, consumes)
    outputs = _covered(
        requirement.required_output_types, list(offer.produces_artifact_types) if offer else []
    )
    dims["artifact_match"] = (
        "not_applicable"
        if inputs == outputs == "not_applicable"
        else min((inputs, outputs), key=_DIM_ORDER.__getitem__)
    )

    # offline/network are always declared at manifest level (ExecutionInfo is
    # non-Optional); only offer.credentials_required can be undeclared — an
    # unverifiable credential demand degrades the dimension, never passes.
    runtime_levels: list[DimensionMatch] = []
    if requirement.offline_required:
        runtime_levels.append("full")
    if not requirement.network_allowed:
        runtime_levels.append("full")
    if not requirement.credentials_allowed:
        creds = offer.credentials_required if offer else None
        runtime_levels.append("full" if creds is not None else "unknown")
    dims["runtime_match"] = (
        "not_applicable" if not runtime_levels else min(runtime_levels, key=_DIM_ORDER.__getitem__)
    )

    feature_flags = {
        "handoff_required": "handoff/v1",
        "trace_required": "trace-ref/v1",
        "economy_required": "economy-receipt/v1",
        "graph_required": "graph-refs/v1",
    }
    demanded = {flag: feat for flag, feat in feature_flags.items() if getattr(requirement, flag)}
    if not demanded:
        dims["feature_match"] = "not_applicable"
    else:
        missing = [
            feat
            for flag, feat in demanded.items()
            if not feature_satisfied(_features(manifest, capability), feat)
        ]
        v.missing.extend(f"feature:{feat}" for feat in missing)
        dims["feature_match"] = "none" if missing else "full"

    v.missing.extend(
        f"undeclared:{name}" for name, level in sorted(dims.items()) if level == "unknown"
    )


def _state(dimensions: dict[str, DimensionMatch], missing: list[str]) -> NegotiationState:
    levels = set(dimensions.values())
    if missing or "none" in levels or "partial" in levels or "unknown" in levels:
        return "PARTIAL"
    return "FULL"


def negotiate_all(
    requirement: CapabilityRequirement,
    records: list[RegistryRecord],
    *,
    performance: ProviderPerformance | None = None,
    policies: Sequence[StrategyPolicy] = (),
) -> list[CapabilityNegotiationResult]:
    """Every record negotiated, sorted best-first deterministically.

    Order: state rank → per-dimension match tuple → history maturity →
    promoted-policy preference → surface fingerprint → provider id. No score
    arithmetic: lexicographic. A ``StrategyPolicy`` reorders candidates only
    inside its exact scope (capability + surface + task family); it can never
    lift an INCOMPATIBLE or unsupported provider — the hard gates already ran.
    """
    results = [negotiate(requirement, r, performance=performance) for r in records]
    dims = (
        "capability_match",
        "protocol_match",
        "policy_match",
        "runtime_match",
        "technology_match",
        "evidence_match",
        "artifact_match",
        "feature_match",
    )
    # Policy preference ladder per surface scope; evaluated lazily per result.
    from theforge.learning import preferred_providers

    def _policy_rank(result: CapabilityNegotiationResult) -> int:
        ladder = preferred_providers(
            policies,
            capability=requirement.capability,
            surface_fingerprint=result.surface_fingerprint,
            task_family=requirement.task_family,
        )
        try:
            return ladder.index(result.provider)
        except ValueError:
            return len(ladder) + 1  # out-of-scope is neutral-worst, never 0

    return sorted(
        results,
        key=lambda r: (
            -_STATE_RANK[r.state],
            tuple(-_DIM_ORDER[r.dimensions.get(d, "unknown")] for d in dims),
            -_HISTORY_RANK[r.history],
            _policy_rank(r),
            r.surface_fingerprint or "",
            r.provider,
        ),
    )
