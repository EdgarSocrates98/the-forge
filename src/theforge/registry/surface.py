"""Deterministic surface fingerprints of a provider manifest (cycle 3.1).

``version`` is not identity: the same declared version can ship a different
surface (seen on sparkforge-aws 0.5.0 and apiforge 0.1.0). These digests answer
"did the declared operational surface change?" and feed the
``ProviderSurfaceIdentity`` the registry attaches to every record.

Inputs to the fingerprints are exactly the declared surface:

- ``capability_fingerprint``: each capability's id, actions, default action,
  state, operation class, context tiers, handoff/plan/resolve flags, aliases,
  deprecation and declared relations.
- ``surface_fingerprint``: the capability fingerprint plus ops, protocols,
  declared features, execution info, revalidation strategy and domains.

Excluded deliberately: ``id``/``version`` (identity, not surface), capability
``description``/``signals`` (presentation and routing hints, not operational
shape), ``limitations``/``unknowns`` (prose), ``adapter_version`` and
``native_surface_fingerprint`` (carried separately on the identity), and any
timestamp/path/machine-specific value — none appear in a manifest anyway.
"""

from typing import Any

from theforge.contracts.canonical import sha256_of
from theforge.contracts.identity import ProviderSurfaceIdentity
from theforge.contracts.manifest import Capability, ForgeManifest


def _capability_projection(cap: Capability) -> dict[str, Any]:
    rel = cap.relations
    return {
        "id": cap.id,
        "actions": sorted(cap.actions),
        "default_action": cap.default_action,
        "state": cap.state,
        "operation_class": cap.operation_class,
        "aliases": sorted(cap.aliases),
        "deprecated": cap.deprecated,
        "replaced_by": cap.replaced_by,
        "context": {"excerpts": cap.context.excerpts, "requests": cap.context.requests},
        "accepts_handoff": cap.accepts_handoff,
        "proposes_plans": cap.proposes_plans,
        "resolves_ambiguity": cap.resolves_ambiguity,
        "relations": {
            "produces": sorted(rel.produces),
            "consumes": sorted(rel.consumes),
            "requires": sorted(rel.requires),
            "complements": sorted(rel.complements),
            "conflicts": sorted(rel.conflicts),
            "can_verify": sorted(rel.can_verify),
            "can_review": sorted(rel.can_review),
        },
    }


def capability_fingerprint(manifest: ForgeManifest) -> str:
    """sha256 over the capability set only (order-independent)."""
    projected = sorted(
        (_capability_projection(c) for c in manifest.capabilities), key=lambda c: c["id"]
    )
    return sha256_of({"capabilities": projected})


def surface_fingerprint(manifest: ForgeManifest) -> str:
    """sha256 over the whole declared operational surface."""
    execution = manifest.execution
    return sha256_of(
        {
            "capabilities": capability_fingerprint(manifest),
            "ops": sorted(manifest.ops),
            "protocols": sorted(manifest.protocols),
            "features": sorted(manifest.features),
            "domains": sorted(manifest.domains),
            "execution": {
                "local": execution.local,
                "offline": execution.offline,
                "requires_network": execution.requires_network,
                "deterministic": execution.deterministic,
            },
            "context_revalidation": manifest.context_revalidation,
        }
    )


def surface_identity(
    manifest: ForgeManifest, *, protocol: str, recorded_at: str
) -> ProviderSurfaceIdentity:
    """The versioned identity of ``manifest``'s surface as observed now."""
    return ProviderSurfaceIdentity(
        provider_id=manifest.id,
        provider_version=manifest.version,
        adapter_version=manifest.adapter_version,
        protocol_version=protocol,
        surface_fingerprint=surface_fingerprint(manifest),
        capability_fingerprint=capability_fingerprint(manifest),
        native_surface_fingerprint=manifest.native_surface_fingerprint,
        recorded_at=recorded_at,
    )
