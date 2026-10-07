"""InstallationPlan v2 builder (Cycle 4, Wave F).

``plan_installation`` turns a remote ``ForgeRegistryEntry`` into a
deterministic, approval-gated install plan (§27-30): pinned version, immutable
distribution reference, expected hashes, declared signature, isolated target
environment, ordered stages, rollback info. The plan is a *document* — nothing
here downloads, installs, or grants trust; the `approval` stage records the
gate, and execution stays a separate milestone.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from theforge.contracts.canonical import utc_now
from theforge.contracts.installation import (
    INSTALL_STAGES,
    InstallApproval,
    InstallationPlanV2,
    InstallStep,
    RollbackStrategy,
)
from theforge.contracts.registry import ForgeRegistryEntry, RegistryDocument
from theforge.contracts.semver import parse_semver
from theforge.errors import UsageError
from theforge.meta import PRODUCER
from theforge.registry.registry import Registry, RegistryRecord
from theforge.registry.sources import SourceSpec, load_source_specs, read_sources

__all__ = ["InstallPlanResult", "build_install_plan", "plan_installation"]

def _semver_key(version: str) -> tuple[int, int, int]:
    parsed = parse_semver(version)
    return (parsed.major, parsed.minor, parsed.patch) if parsed else (0, 0, 0)


_STAGE_DESCRIPTIONS = {
    "plan": "resolve the candidate metadata and pin the distribution",
    "approval": "human/policy approval — nothing happens before this stage",
    "download": "fetch the pinned distribution into a staging area",
    "verify": "recompute sha256 of every artifact against expected_hashes; "
              "verify the declared signature when a public key is configured",
    "isolated-install": "install into the isolated environment "
                        "(no interpreter pollution)",
    "provider-check": "add a reviewed ProviderEntry to user providers.toml "
                      "and run describe",
    "surface-fingerprint": "record ProviderSurfaceIdentity + capability "
                           "fingerprints for the new install",
    "health": "theforge providers health — the provider reports its own state",
}


@dataclass(frozen=True, kw_only=True)
class InstallPlanResult:
    """The plan plus the honest accounting of what fed it."""

    plan: InstallationPlanV2
    source: SourceSpec
    document: RegistryDocument


def plan_installation(entry: ForgeRegistryEntry, *,
                      source_id: str, registry_id: str | None,
                      existing: RegistryRecord | None = None,
                      approved_by: str | None = None,
                      approved_at: str | None = None,
                      extra_limitation: str | None = None) -> InstallationPlanV2:
    """Build the v2 plan for one registry entry — pure function over claims.

    ``existing`` is the installed record being replaced (rollback material).
    ``approved_by`` records that the human/policy gate was exercised; the plan
    still does not execute anything — stages stay ``pending``."""
    if entry.distribution is None:
        raise UsageError(
            f"{entry.provider}@{entry.version}: no distribution declared — "
            "nothing verifiable to install")
    if parse_semver(entry.version) is None or entry.version == "latest":
        raise UsageError(
            f"{entry.provider}: version {entry.version!r} is not pinned — "
            "'latest' is never installable")

    environment = f"venv:providers/{entry.provider}-{entry.version}"
    permissions = []
    if entry.runtime and entry.runtime.requires_network:
        permissions.append("network")
    if entry.runtime and entry.runtime.requires_credentials:
        permissions.append("credentials")
    if entry.runtime and entry.runtime.offline is False:
        permissions.append("non-offline-runtime")

    expected_hashes = dict(entry.hashes)
    if entry.manifest_sha256:
        expected_hashes["manifest"] = entry.manifest_sha256
    if entry.distribution.sha256:
        expected_hashes["distribution"] = entry.distribution.sha256

    dependencies = list(entry.dependencies)
    limitations = list(entry.limitations)
    if extra_limitation:
        limitations.append(extra_limitation)
    unpinned = [d for d in dependencies if "==" not in d]
    if unpinned:
        limitations.append(
            f"unpinned dependencies {sorted(unpinned)} — pin before approving")
    if not expected_hashes:
        limitations.append("no expected hashes declared — verify stage cannot "
                           "check integrity; treat as untrusted")

    rollback = RollbackStrategy(
        action="restore-previous" if existing is not None else "remove-new",
        previous_version=existing.manifest.version
        if existing and existing.manifest else None,
        previous_manifest_sha256=existing.manifest_sha256
        if existing else None,
        previous_surface_fingerprint=existing.surface.surface_fingerprint
        if existing and existing.surface else None,
        environment=environment)

    return InstallationPlanV2(
        producer=PRODUCER, created_at=utc_now(),
        provider=entry.provider, version=entry.version,
        source=source_id, registry=registry_id,
        distribution=entry.distribution,
        expected_hashes=expected_hashes,
        signature=entry.signatures[0] if entry.signatures else None,
        runtime=entry.runtime, environment=environment,
        dependencies=dependencies, permissions=permissions,
        post_install_checks=["provider-check", "surface-fingerprint", "health"],
        rollback=rollback,
        steps=[InstallStep(stage=s, description=_STAGE_DESCRIPTIONS[s])
               for s in INSTALL_STAGES],
        approval=InstallApproval(
            required=True, granted=approved_by is not None,
            granted_by=approved_by, granted_at=approved_at),
        limitations=limitations)


def build_install_plan(provider: str, version: str, source_id: str, *,
                       forge_dir: Path | None,
                       approve: bool = False,
                       **source_kwargs: Any) -> InstallPlanResult:
    """Resolve provider@version from a configured source into an
    InstallationPlanV2. Raises UsageError when the source is disabled, the
    document is unreadable, or the exact provider@version is absent — the plan
    never guesses a different version."""
    specs = {s.id: s for s in load_source_specs(forge_dir)}
    spec = specs.get(source_id)
    if spec is None:
        raise UsageError(f"unknown registry source {source_id!r} — configured "
                         f"sources: {sorted(specs) or 'none'}")
    if not spec.enabled:
        raise UsageError(f"registry source {source_id!r} is disabled — enable it "
                         "in registries.toml first")
    reads = read_sources([spec], **source_kwargs)
    read = reads[0]
    if read.document is None:
        raise UsageError(f"source {source_id!r}: {read.status} — "
                         f"{read.detail or 'no document'}")
    document = read.document
    candidates = [e for e in document.entries if e.provider == provider]
    match = next((e for e in candidates if e.version == version), None)
    if match is None:
        versions = sorted((e.version for e in candidates), key=_semver_key)
        raise UsageError(
            f"{provider}@{version} not in source {source_id!r}"
            + (f" — available: {', '.join(versions)}" if versions
               else " — provider absent"))
    # A stale document may still describe the candidate — the plan records the
    # freshness so whoever approves sees what they are approving (§21).
    stale_note = (f"source metadata is stale ({read.detail})"
                  if read.status == "stale" else None)
    existing = next((r for r in Registry(forge_dir).records()
                     if r.entry.id == provider), None)
    plan = plan_installation(
        match, source_id=source_id, registry_id=document.registry.id,
        existing=existing,
        approved_by="cli-user" if approve else None,
        approved_at=utc_now() if approve else None,
        extra_limitation=stale_note)
    return InstallPlanResult(plan=plan, source=spec, document=document)
