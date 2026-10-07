"""ProviderSurfaceIdentity: the versioned identity of a provider surface (cycle 3.1).

``version`` alone is not identity: a provider can keep ``manifest.version`` while
its declared surface changes underneath (observed with sparkforge 0.5.0 and
apiforge 0.1.0 during the cycle-3.1 audit). The identity pairs the declared
versions with two deterministic fingerprints computed by the core from the
manifest in use — never with timestamps, paths or machine-specific values:

- ``capability_fingerprint``: the capability set only (ids, actions, operation
  classes, context support, handoff/verify relations, planning flags...).
- ``surface_fingerprint``: the whole declared operational surface — the
  capability fingerprint plus ops, protocols, features, execution info,
  revalidation strategy and domains.

``native_surface_fingerprint`` is *declared* by the provider (adapters hash the
snapshot of the specialist surface they expose); the core verifies its shape,
not its content — a hash is evidence, not trust. ``recorded_at`` is when the
core computed the identity, not part of any fingerprint.
"""

from dataclasses import dataclass

from theforge.contracts.base import ContractError
from theforge.contracts.types import check_sha256

SURFACE_IDENTITY_SCHEMA = "theforge/ProviderSurfaceIdentity/v1"


@dataclass(frozen=True, kw_only=True)
class ProviderSurfaceIdentity:
    schema: str = SURFACE_IDENTITY_SCHEMA
    provider_id: str
    # ``manifest.version`` — for adapters, the adapter's own release.
    provider_version: str
    # The adapter release the provider declares itself to be, when it is one
    # (manifest ``adapter_version``); None for direct/built-in providers.
    adapter_version: str | None = None
    protocol_version: str = ""
    surface_fingerprint: str
    capability_fingerprint: str
    # Provider-declared digest of the specialist surface behind the adapter.
    native_surface_fingerprint: str | None = None
    recorded_at: str = ""

    def __post_init__(self) -> None:
        if self.schema != SURFACE_IDENTITY_SCHEMA:
            raise ContractError(f"unsupported schema {self.schema!r}, "
                                f"expected {SURFACE_IDENTITY_SCHEMA!r}")
        if not self.provider_id:
            raise ContractError("surface identity: provider_id must not be empty")
        if not self.provider_version:
            raise ContractError("surface identity: provider_version must not be empty")
        check_sha256(self.surface_fingerprint, field="surface_fingerprint")
        check_sha256(self.capability_fingerprint, field="capability_fingerprint")
        if self.native_surface_fingerprint is not None:
            check_sha256(self.native_surface_fingerprint,
                         field="native_surface_fingerprint")
