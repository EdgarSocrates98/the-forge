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
from theforge.registry.mcp import read_mcp_sources
from theforge.registry.registry import RegistryRecord
from theforge.registry.sources import (
    SourceRead,
    SourceSpec,
    load_source_specs,
    read_sources,
)

__all__ = [
    "DiscoveryReport",
    "McpDependency",
    "McpToolingNote",
    "discover",
    "evaluate_entry",
]

MAX_MCP_NOTES = 10  # §71 progressive discovery: bounded tool listings


@dataclass(frozen=True, kw_only=True)
class McpToolingNote:
    """An MCP server whose declared metadata may serve tooling needs —
    deliberately *not* a ``RemoteProviderCandidate``: MCP servers provide
    tools, they are never Forge providers (§68)."""

    source: str
    name: str
    version: str | None
    matched_terms: list[str]
    requires_network: bool
    requires_credentials: bool
    remotes: list[str]  # "type url"
    packages: list[str]  # "registryType:identifier"
    limitations: list[str]


@dataclass(frozen=True, kw_only=True)
class McpDependency:
    """A capability's declared MCP dependency (§70) with availability
    detection — ``listed`` means a configured MCP source serves the name,
    never that the Forge installed or trusts it."""

    name: str
    declared_by: str  # "provider/capability"
    availability: Literal["listed", "unlisted"]


@dataclass(frozen=True, kw_only=True)
class DiscoveryReport:
    """Outcome of remote discovery for one requirement — data, never action."""

    requirement: CapabilityRequirement
    profile: str = "balanced"  # the policy that decided remote consult
    # Local side: best negotiation state among installed providers.
    local_state: str = "UNSUPPORTED"  # FULL / PARTIAL / UNSUPPORTED / ...
    local_provider: str | None = None
    satisfied_locally: bool = False
    # Remote side.
    candidates: list[RemoteProviderCandidate] = field(default_factory=list)
    sources_consulted: list[str] = field(default_factory=list)
    sources_skipped: list[str] = field(default_factory=list)  # disabled/unavailable
    entries_scanned: int = 0
    entries_excluded: list[str] = field(default_factory=list)  # "provider@ver: reason"
    # Discovery economy (§47): what the lookup itself cost — reads that served
    # a document, bytes of metadata consumed, real network latency (``None``
    # when no fetch hit the network: cached and local reads cost none).
    registry_calls: int = 0
    metadata_bytes: int = 0
    network_ms: float | None = None
    # MCP awareness (§69-72): tooling candidates and declared provider deps.
    # Separate from ``candidates`` — an MCP server is never a provider.
    mcp_tooling: list[McpToolingNote] = field(default_factory=list)
    mcp_dependencies: list[McpDependency] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


def evaluate_entry(
    requirement: CapabilityRequirement, entry: ForgeRegistryEntry
) -> tuple[Literal["declared", "partial", "unknown"], list[str], list[str], list[str], str | None]:
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
        return (
            "unknown",
            matched,
            [f"capability:{requirement.capability}"],
            unknowns,
            None,
        )  # not a candidate at all — no reason to report

    runtime = entry.runtime
    if requirement.offline_required and runtime and runtime.requires_network:
        return (
            "unknown",
            matched,
            missing,
            unknowns,
            "requires_network conflicts with offline_required",
        )
    if not requirement.network_allowed and runtime and runtime.requires_network:
        return (
            "unknown",
            matched,
            missing,
            unknowns,
            "requires_network conflicts with network_allowed=false",
        )
    if not requirement.credentials_allowed and runtime and runtime.requires_credentials:
        return (
            "unknown",
            matched,
            missing,
            unknowns,
            "requires_credentials conflicts with credentials_allowed=false",
        )

    # Platform constraints: "any" satisfies everything; empty = undeclared.
    if requirement.platform_constraints:
        if not entry.platforms:
            unknowns.append("platforms:undeclared")
        elif "any" in entry.platforms or set(requirement.platform_constraints) & set(
            entry.platforms
        ):
            matched.append("platform")
        else:
            return (
                "unknown",
                matched,
                missing,
                unknowns,
                f"platforms {entry.platforms} miss {requirement.platform_constraints}",
            )

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
    fit: Literal["declared", "partial"] = "declared" if not missing and not unknowns else "partial"
    return fit, matched, missing, unknowns, None


def _signature_state(signatures: list[SignatureRef]) -> Literal["none", "declared"]:
    # Wave F verifies them; at discovery time a signature is only *declared*.
    return "declared" if signatures else "none"


def _entry_to_candidate(
    read: SourceRead,
    entry: ForgeRegistryEntry,
    fit: Literal["declared", "partial", "unknown"],
    matched: list[str],
    missing: list[str],
    unknowns: list[str],
) -> RemoteProviderCandidate:
    document = read.document
    assert document is not None
    return RemoteProviderCandidate(
        source=read.spec.id,
        registry=document.registry.id,
        registry_url=document.registry.url,
        source_tier=read.spec.tier,
        provider=entry.provider,
        version=entry.version,
        publisher=entry.publisher,
        distribution=entry.distribution,
        manifest_sha256=entry.manifest_sha256,
        signature_state=_signature_state(entry.signatures),
        freshness=read.freshness,
        retrieved_at=read.retrieved_at,
        fit=fit,
        matched=matched,
        missing=missing,
        unknowns=unknowns,
        protocols=list(entry.protocols),
        capabilities=list(entry.capabilities),
        platforms=list(entry.platforms),
        runtime=entry.runtime,
        limitations=list(entry.limitations),
    )


def _version_key(candidate: RemoteProviderCandidate) -> tuple[int, int, int]:
    parsed = parse_semver(candidate.version)
    return (parsed.major, parsed.minor, parsed.patch) if parsed else (0, 0, 0)


DiscoveryProfile = Literal["economy", "balanced", "max"]


def _remote_wanted(
    profile: DiscoveryProfile, local_state: str, satisfied: bool, force_remote: bool
) -> tuple[bool, str | None]:
    """Whether remote sources should be consulted under ``profile`` (§48).

    ``economy`` pays a remote read only when nothing local exists at all (or
    the caller explicitly asks); ``balanced`` consults when no local provider
    fully satisfies the requirement; ``max`` always looks, so a satisfying
    local provider can still be compared against remote claims.
    """
    if force_remote:
        return True, None
    if profile == "max":
        return True, None
    if profile == "economy":
        # Nothing local can serve the requirement: no provider declares the
        # capability, or the only claimant is hard-incompatible.
        needed = local_state in ("UNSUPPORTED", "INCOMPATIBLE")
        return needed, (
            None
            if needed
            else "economy profile: local capability exists — remote sources not consulted"
        )
    needed = not satisfied
    return needed, (
        None
        if needed
        else "local provider satisfies the requirement — remote sources not consulted"
    )


def discover(
    requirement: CapabilityRequirement,
    records: Sequence[RegistryRecord],
    *,
    specs: Sequence[SourceSpec] | None = None,
    forge_dir: Path | None = None,
    force_remote: bool = False,
    profile: DiscoveryProfile = "balanced",
    performance: ProviderPerformance | None = None,
    **source_kwargs: Any,
) -> DiscoveryReport:
    """Local-first discovery: negotiate installed providers; consult enabled
    sources under the ``profile`` policy (or ``force_remote``).
    ``source_kwargs`` forwards fetcher/cache_dir to ``read_sources`` (tests)."""
    # Lazy import: ``theforge.negotiation`` imports ``theforge.registry``
    # submodules — keeping this here breaks the import cycle either way.
    from theforge.negotiation import negotiate_all

    local_results = negotiate_all(requirement, list(records), performance=performance)
    top = local_results[0] if local_results else None
    local_state = top.state if top else "UNSUPPORTED"
    satisfied = local_state == "FULL"

    candidates: list[RemoteProviderCandidate] = []
    sources_consulted: list[str] = []
    sources_skipped: list[str] = []
    entries_excluded: list[str] = []
    limitations: list[str] = []
    entries_scanned = 0
    registry_calls = 0
    metadata_bytes = 0
    network_ms: float | None = None

    wanted, why_not = _remote_wanted(profile, local_state, satisfied, force_remote)
    if not wanted:
        assert why_not is not None
        limitations.append(why_not)
    else:
        if specs is None:
            specs = load_source_specs(forge_dir, warnings=limitations)
        if not specs:
            limitations.append("no registry sources configured")
        for read in read_sources(list(specs), **source_kwargs):
            if read.status == "disabled":
                sources_skipped.append(read.spec.id)
                continue
            if read.status == "skipped":
                continue  # mcp sources are tooling reads, handled below
            if read.document is None or read.status == "invalid":
                sources_skipped.append(read.spec.id)
                limitations.append(
                    f"source {read.spec.id}: {read.status} — {read.detail or 'no document'}"
                )
                continue
            sources_consulted.append(read.spec.id)
            registry_calls += 1
            metadata_bytes += read.bytes_received
            if read.latency_ms is not None:
                network_ms = (network_ms or 0.0) + read.latency_ms
            if read.status == "stale":
                limitations.append(f"source {read.spec.id}: document is stale ({read.detail})")
            for entry in read.document.entries:
                entries_scanned += 1
                fit, matched, missing, unknowns, incompatible = evaluate_entry(requirement, entry)
                if incompatible is not None:
                    entries_excluded.append(f"{entry.provider}@{entry.version}: {incompatible}")
                    continue
                if fit == "unknown":
                    continue  # does not declare the capability
                candidates.append(_entry_to_candidate(read, entry, fit, matched, missing, unknowns))

    # MCP awareness (§68-72): provider deps + tooling candidates — a
    # separate object type, never mixed into provider ``candidates``.
    mcp_tooling: list[McpToolingNote] = []
    mcp_dependencies: list[McpDependency] = []
    declared_deps: dict[str, str] = {}  # server name -> "provider/capability"
    for result in local_results:
        if result.state not in ("FULL", "PARTIAL"):
            continue
        record = next((r for r in records if r.entry.id == result.provider), None)
        manifest = record.manifest if record else None
        for cap in manifest.capabilities if manifest else ():
            if cap.id == requirement.capability:
                for dep in cap.mcp_requires:
                    declared_deps.setdefault(dep, f"{result.provider}/{cap.id}")
    # MCP reads obey the same profile gate as provider sources; but the
    # dependency listing needs specs loaded even when remote was not wanted.
    if specs is None and (requirement.technologies or declared_deps):
        specs = load_source_specs(forge_dir, warnings=limitations)
    mcp_specs = [s for s in (specs or []) if s.kind == "mcp" and s.enabled]
    # Dependency detection is worth a read even when the profile gates
    # provider-candidate discovery; technology hints pay a fetch only when
    # remote consultation was wanted anyway.
    mcp_wanted = bool(declared_deps) or (wanted and bool(requirement.technologies))
    if mcp_specs and mcp_wanted:
        tech_terms = {t.lower() for t in requirement.technologies}
        listed_names: set[str] = set()
        for mcp_read in read_mcp_sources(mcp_specs, **source_kwargs):
            if mcp_read.document is None:
                if mcp_read.status != "disabled":
                    limitations.append(
                        f"mcp source {mcp_read.spec.id}: {mcp_read.status} — "
                        f"{mcp_read.detail or 'no document'}"
                    )
                continue
            registry_calls += 1
            metadata_bytes += mcp_read.bytes_received
            if mcp_read.latency_ms is not None:
                network_ms = (network_ms or 0.0) + mcp_read.latency_ms
            if mcp_read.status == "stale":
                limitations.append(
                    f"mcp source {mcp_read.spec.id}: document is stale ({mcp_read.detail})"
                )
            for mcp_entry in mcp_read.document.entries:
                listed_names.add(mcp_entry.name)
                haystack = (
                    f"{mcp_entry.name} {mcp_entry.title or ''} "
                    f"{mcp_entry.description or ''}".lower()
                )
                hit = sorted(t for t in tech_terms if t in haystack)
                if hit:
                    mcp_tooling.append(
                        McpToolingNote(
                            source=mcp_read.spec.id,
                            name=mcp_entry.name,
                            version=mcp_entry.version,
                            matched_terms=hit,
                            requires_network=mcp_entry.requires_network,
                            requires_credentials=mcp_entry.requires_credentials,
                            remotes=sorted(f"{r.type} {r.url}" for r in mcp_entry.remotes),
                            packages=sorted(
                                f"{p.registry_type}:{p.identifier}" for p in mcp_entry.packages
                            ),
                            limitations=list(mcp_entry.limitations),
                        )
                    )
        for dep, by in sorted(declared_deps.items()):
            mcp_dependencies.append(
                McpDependency(
                    name=dep,
                    declared_by=by,
                    availability="listed" if dep in listed_names else "unlisted",
                )
            )
    elif declared_deps:
        for dep, by in sorted(declared_deps.items()):
            mcp_dependencies.append(
                McpDependency(name=dep, declared_by=by, availability="unlisted")
            )
        if any(s.kind == "mcp" for s in (specs or [])):
            limitations.append(
                "mcp sources configured but disabled — dependency availability unknown"
            )
    mcp_tooling.sort(key=lambda n: (n.name, n.source))
    mcp_tooling = mcp_tooling[:MAX_MCP_NOTES]

    # Deterministic order: declared > partial, then provider, then newest
    # version, then registry — popularity never orders candidates (§34).
    candidates.sort(
        key=lambda c: (
            0 if c.fit == "declared" else 1,
            c.provider,
            tuple(-n for n in _version_key(c)),
            c.registry,
        )
    )
    return DiscoveryReport(
        requirement=requirement,
        profile=profile,
        local_state=local_state,
        local_provider=top.provider if top else None,
        satisfied_locally=satisfied,
        candidates=candidates,
        sources_consulted=sources_consulted,
        sources_skipped=sources_skipped,
        entries_scanned=entries_scanned,
        entries_excluded=entries_excluded,
        registry_calls=registry_calls,
        metadata_bytes=metadata_bytes,
        network_ms=network_ms,
        mcp_tooling=mcp_tooling,
        mcp_dependencies=mcp_dependencies,
        limitations=limitations,
    )
