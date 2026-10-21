"""ForgeManifest -> SpecialistCapability derivation (lf-0031).

The honest floor for capability manifests: a provider whose ``describe``
surface answers ``theforge/ForgeManifest/v1`` already advertises every
capability it can run — actions, state, operation class, routing signals,
network needs. When no richer ``theforge/SpecialistCapability/v1``
document was emitted (no ``capabilities`` op, no bundled manifest file),
this module translates that declared surface into the discovery
advertisement the delegation router consumes.

Translation rules — everything declared maps, nothing is invented:

- ``id``/``description`` copy verbatim; ``risk`` maps ``operation_class``
  positionally.
- ``entrypoint`` stays empty: the Forge Protocol ``execute`` op is the
  invocation surface — no argv template is derivable from a describe
  payload, and inventing one would fabricate an execution path.
- ``execution_mode``/``network`` come from the manifest's ``execution``
  block; a ``local`` capability never pairs with ``network=True`` (the
  contract refuses that combination — offline manifests derive ``local``).
- ``external_cost`` is ``"none"`` only when the manifest declares
  ``offline=True`` and ``requires_network=False`` — an explicit claim that
  made the call impossible, so ``none`` is justified; anything else stays
  ``"unknown"`` (undeclared cost is possibly bearing, never free).
- ``requires``/``permissions`` stay empty: the ForgeManifest has no such
  vocabulary — undeclared, never guessed.
- ``discovery_mode="registry"``, ``verification_mode="handshake"``: the
  document exists because a governed ``describe`` answered.
- ``finding_class`` copies the capability's own declaration (the
  ForgeManifest ``finding_class`` field, lf-0031); an explicit caller map
  only fills capabilities that declared none. Undeclared stays ``""`` —
  the report buckets those findings as UNSPECIFIED rather than laundering
  them into a class the capability never claimed.
"""

from __future__ import annotations

from collections.abc import Mapping

from theforge.contracts.base import ContractError
from theforge.contracts.manifest import ForgeManifest
from theforge.contracts.specialist_capability import (
    RUNTIME_DETECTED,
    DeclaredCapability,
    FindingClass,
    SpecialistCapability,
    SpecialistIdentity,
    SurfaceSupport,
)

__all__ = ["specialist_capability_from_manifest"]


def specialist_capability_from_manifest(
    manifest: ForgeManifest,
    *,
    expected_id: str | None = None,
    finding_classes: Mapping[str, FindingClass] | None = None,
) -> SpecialistCapability:
    """Derive the discovery advertisement from a live ``describe`` manifest.

    ``expected_id`` binds the derivation to the catalog id the caller asked
    about — a manifest answering under a different id is a ContractError,
    never silently rebranded.
    """
    if expected_id is not None and manifest.id != expected_id:
        raise ContractError(
            f"manifest id {manifest.id!r} does not match specialist {expected_id!r}"
        )
    classes = finding_classes or {}
    remote = manifest.execution.requires_network or not manifest.execution.local
    offline_and_local = manifest.execution.offline and not manifest.execution.requires_network
    capabilities: list[DeclaredCapability] = []
    for cap in manifest.capabilities:
        capabilities.append(
            DeclaredCapability(
                id=cap.id,
                description=cap.description,
                # The describe surface is the invocation path — there is no
                # declared argv entrypoint to derive.
                entrypoint=[],
                execution_mode="remote" if remote else "local",
                risk=cap.operation_class,
                network=manifest.execution.requires_network,
                external_cost="none" if offline_and_local else "unknown",
                requires=[],
                limitations=(
                    ["capability state: " + cap.state] if cap.state != "supported" else []
                ),
                discovery_mode="registry",
                verification_mode="handshake",
                # The manifest's own declaration wins; an explicit caller map
                # only fills capabilities that declared no class.
                finding_class=cap.finding_class or classes.get(cap.id, ""),
            )
        )
    return SpecialistCapability(
        specialist=SpecialistIdentity(
            id=manifest.id,
            version=manifest.version or RUNTIME_DETECTED,
            domain=manifest.domains[0] if manifest.domains else "",
        ),
        capabilities=capabilities,
        health=SurfaceSupport(
            supported="health" in manifest.ops,
            detail="health op declared" if "health" in manifest.ops else "",
        ),
        handoff=SurfaceSupport(
            supported="handoff/v1" in manifest.features,
            detail="handoff/v1 feature declared" if "handoff/v1" in manifest.features else "",
        ),
    )
