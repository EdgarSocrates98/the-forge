"""Remote discovery by CapabilityRequirement (Cycle 4, Wave E).

The flow (§22-26): local negotiation first — when an installed provider fully
satisfies the requirement, remote registries are not consulted (economic: no
unneeded network). Otherwise enabled sources are read and every entry is
evaluated as an *unverified claim*: a candidate can reach ``declared``/``partial``
fit, never ``FULL`` — remote metadata cannot prove actions, evidence, or
surface. Discovery reports candidates and stops; nothing is installed,
executed, or trusted (§25).
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from theforge.contracts.negotiation import CapabilityRequirement
from theforge.contracts.performance import ProviderPerformance
from theforge.contracts.registry import (
    ForgeRegistryEntry,
    RemoteProviderCandidate,
    SignatureRef,
)
from theforge.contracts.semver import parse_semver
from theforge.negotiation import negotiate_all
from theforge.registry.registry import RegistryRecord
from theforge.registry.sources import (
    SourceRead,
    SourceSpec,
    load_source_specs,
    read_sources,
)

__all__ = [
    "DiscoveryReport",
    "discover",
    "evaluate_entry",
]


@dataclass(frozen=True, kw_only=True)
class DiscoveryReport:
    """Outcome of remote discovery for one requirement — data, never action."""

    requirement: CapabilityRequirement
    # Local side: best negotiation state among installed providers.
    local_state: str                       # FULL / PARTIAL / UNSUPPORTED / ...
    local_provider: str | None = None
    satisfied_locally: bool = False
    # Remote side.
    candidates: list[RemoteProviderCandidate] = field(default_factory=list)
    sources_consulted: list[str] = field(default_factory=list)
    sources_skipped: list[str] = field(default_factory=list)   # disabled/unavailable
    entries_scanned: int = 0
    entries_excluded: list[str] = field(default_factory=list)  # "provider@ver: reason"
    limitations: list[str] = field(default_factory=list)


def evaluate_entry(requirement: CapabilityRequirement,
                   entry: ForgeRegistryEntry
                   ) -> tuple[Literal["declared", "partial", "unknown"],
                              list[str], list[str], list[str], str | None]:
    """Coarse fit of a remote *claim* against a requirement.

    Returns (fit, matched, missing, unknowns, incompatible_reason).
    ``incompatible_reason`` set → the entry is excluded from candidates:
    hard contradictions (declared runtime contradicting a hard requirement)
    eliminate claims the same way hard gates eliminate providers.
    """
    matched: list[str] = []
    missing: list[str] = []
    unknowns: list[str] = []

    # Capability presence is the admission ticket: remote entries carry ids
    # only — "declared", never verified. Alias resolution stays local.
    if requirement.capability in entry.capabilities:
        matched.append(f"capability:{requirement.capability}")
    else:
        return "unknown", matched, [f"capability:{requirement.capability}"], \
            unknowns, None  # not a candidate at all — no reason to report

    runtime = entry.runtime
    if requirement.offline_required and runtime and runtime.requires_network:
        return "unknown", matched, missing, unknowns, \
            "requires_network conflicts with offline_required"
    if not requirement.network_allowed and runtime and runtime.requires_network:
        return "unknown", matched, missing, unknowns, \
            "requires_network conflicts with network_allowed=false"
    if not requirement.credentials_allowed and runtime \
            and runtime.requires_credentials:
        return "unknown", matched, missing, unknowns, \
            "requires_credentials conflicts with credentials_allowed=false"

    # Platform constraints: "any" satisfies everything; empty = undeclared.
    if requirement.platform_constraints:
        if not entry.platforms:
            unknowns.append("platforms:undeclared")
        elif "any" in entry.platforms or \
                set(requirement.platform_constraints) & set(entry.platforms):
            matched.append("platform")
        else:
            return "unknown", matched, missing, unknowns, \
                f"platforms {entry.platforms} miss {requirement.platform_constraints}"

    # Declared technologies (§23 filter).
    if requirement.technologies:
        declared = set(entry.technologies)
        have = sorted(set(requirement.technologies) & declared)
        lack = sorted(set(requirement.technologies) - declared)
        if have:
            matched.extend(f"technology:{t}" for t in have)
        if not declared:
            unknowns.append("technologies:undeclared")
        missing.extend(f"technology:{t}" for t in lack)

    if requirement.required_actions:
        unknowns.append("required_actions:remote-undeclared")
    if requirement.required_evidence:
        unknowns.append("required_evidence:remote-undeclared")
    if requirement.protocol_features:
        unknowns.append("protocol_features:remote-undeclared")
    if requirement.operation_class_ceiling is not None:
        unknowns.append("operation_class:remote-undeclared")

    # Forge Protocol compatibility is an installability floor: an entry that
    # never speaks forge/v1 cannot become a local provider later.
    if entry.protocols and "forge/v1" not in entry.protocols:
        missing.append("protocol:forge/v1")

    # Remote claims top out at "declared": every unverifiable dimension degrades
    # the entry to "partial" — remote metadata can never prove FULL.
    fit: Literal["declared", "partial"] = \
        "declared" if not missing and not unknowns else "partial"
    return fit, matched, missing, unknowns, None


def _signature_state(signatures: list[SignatureRef]) -> Literal["none", "declared"]:
    # Wave F verifies them; at discovery time a signature is only *declared*.
    return "declared" if signatures else "none"


def _entry_to_candidate(read: SourceRead, entry: ForgeRegistryEntry,
                        fit: Literal["declared", "partial", "unknown"],
                        matched: list[str], missing: list[str],
                        unknowns: list[str]) -> RemoteProviderCandidate:
    document = read.document
    assert document is not None
    return RemoteProviderCandidate(
        source=read.spec.id, registry=document.registry.id,
        registry_url=document.registry.url,
        provider=entry.provider, version=entry.version,
        publisher=entry.publisher, distribution=entry.distribution,
        manifest_sha256=entry.manifest_sha256,
        signature_state=_signature_state(entry.signatures),
        freshness=read.freshness, retrieved_at=read.retrieved_at,
        fit=fit, matched=matched, missing=missing, unknowns=unknowns,
        protocols=list(entry.protocols), capabilities=list(entry.capabilities),
        platforms=list(entry.platforms), runtime=entry.runtime,
        limitations=list(entry.limitations),
    )


def _version_key(candidate: RemoteProviderCandidate) -> tuple[int, int, int]:
    parsed = parse_semver(candidate.version)
    return (parsed.major, parsed.minor, parsed.patch) if parsed else (0, 0, 0)


def discover(requirement: CapabilityRequirement,
             records: Sequence[RegistryRecord], *,
             specs: Sequence[SourceSpec] | None = None,
             forge_dir: Path | None = None, force_remote: bool = False,
             performance: ProviderPerformance | None = None,
             **source_kwargs: Any) -> DiscoveryReport:
    """Local-first discovery: negotiate installed providers; consult enabled
    sources only when nothing local fully satisfies the requirement (or
    ``force_remote``). ``source_kwargs`` forwards fetcher/cache_dir to
    ``read_sources`` (tests)."""
    local_results = negotiate_all(requirement, list(records),
                                  performance=performance)
    top = local_results[0] if local_results else None
    local_state = top.state if top else "UNSUPPORTED"
    satisfied = local_state == "FULL"

    candidates: list[RemoteProviderCandidate] = []
    sources_consulted: list[str] = []
    sources_skipped: list[str] = []
    entries_excluded: list[str] = []
    limitations: list[str] = []
    entries_scanned = 0

    if satisfied and not force_remote:
        limitations.append(
            "local provider satisfies the requirement — remote sources not "
            "consulted")
    else:
        if specs is None:
            specs = load_source_specs(forge_dir, warnings=limitations)
        if not specs:
            limitations.append("no registry sources configured")
        for read in read_sources(list(specs), **source_kwargs):
            if read.status == "disabled":
                sources_skipped.append(read.spec.id)
                continue
            if read.document is None or read.status == "invalid":
                sources_skipped.append(read.spec.id)
                limitations.append(
                    f"source {read.spec.id}: {read.status} — "
                    f"{read.detail or 'no document'}")
                continue
            sources_consulted.append(read.spec.id)
            if read.status == "stale":
                limitations.append(
                    f"source {read.spec.id}: document is stale ({read.detail})")
            for entry in read.document.entries:
                entries_scanned += 1
                fit, matched, missing, unknowns, incompatible = evaluate_entry(
                    requirement, entry)
                if incompatible is not None:
                    entries_excluded.append(
                        f"{entry.provider}@{entry.version}: {incompatible}")
                    continue
                if fit == "unknown":
                    continue  # does not declare the capability
                candidates.append(_entry_to_candidate(
                    read, entry, fit, matched, missing, unknowns))

    # Deterministic order: declared > partial, then provider, then newest
    # version, then registry — popularity never orders candidates (§34).
    candidates.sort(key=lambda c: (
        0 if c.fit == "declared" else 1,
        c.provider, tuple(-n for n in _version_key(c)), c.registry))
    return DiscoveryReport(
        requirement=requirement, local_state=local_state,
        local_provider=top.provider if top else None,
        satisfied_locally=satisfied, candidates=candidates,
        sources_consulted=sources_consulted, sources_skipped=sources_skipped,
        entries_scanned=entries_scanned, entries_excluded=entries_excluded,
        limitations=limitations)
