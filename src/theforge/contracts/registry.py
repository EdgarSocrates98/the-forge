"""Registry metadata contracts (Cycle 4, Wave C/D/E).

``ForgeRegistryEntry`` is the *published* metadata of a provider version —
independent of installation (§17): a registry document is untrusted input that
the core may use for discovery and negotiation, never a source of trust or
identity (§18). ``RegistryDocument`` is what a registry source returns: the
registry identity plus the entries it advertises.

Nothing here grants trust. ``publisher`` is declared metadata — a verified
publisher is not a safe provider (§34), and ``trust`` of an installed provider
is decided only by the local configuration, never by remote data.
"""

import re
from dataclasses import dataclass, field
from typing import Literal

from theforge.contracts.base import ContractError
from theforge.contracts.manifest import PROVIDER_ID
from theforge.contracts.semver import parse_semver
from theforge.contracts.types import SHA256_RE

REGISTRY_ENTRY_SCHEMA = "theforge/ForgeRegistryEntry/v1"
REGISTRY_DOCUMENT_SCHEMA = "theforge/RegistryDocument/v1"

DISTRIBUTION_KIND = Literal["pip-package", "file", "vcs", "container"]
PLATFORM_RE_SRC = r"^[a-z0-9]+(-[a-z0-9_]+)*$"  # "win32", "linux-x86_64", "any"


@dataclass(frozen=True, kw_only=True)
class PublisherIdentity:
    """Declared publisher metadata (§34) — claims, not verified facts."""

    id: str
    organization: str | None = None
    repository: str | None = None
    homepage: str | None = None
    # Fingerprint/id of the publisher's signing key, when signatures are used.
    key_id: str | None = None

    def __post_init__(self) -> None:
        if not self.id:
            raise ContractError("publisher identity: id must not be empty")


@dataclass(frozen=True, kw_only=True)
class DistributionRef:
    """How a provider version is distributed — an *immutable* reference (§30)."""

    kind: DISTRIBUTION_KIND
    package: str | None = None
    version: str | None = None
    url: str | None = None
    sha256: str | None = None
    # VCS refs must be immutable (commit/tag digest), never a moving branch.
    ref: str | None = None

    def __post_init__(self) -> None:
        if self.sha256 is not None and not SHA256_RE.fullmatch(self.sha256):
            raise ContractError("distribution: sha256 must be a sha256 hex digest")


@dataclass(frozen=True, kw_only=True)
class SignatureRef:
    """A declared signature over a part of the entry (e.g. the manifest)."""

    key_id: str
    algorithm: str
    signature: str
    signed: str = "manifest"


@dataclass(frozen=True, kw_only=True)
class RuntimeRequirements:
    """What the provider needs at runtime, as declared by the publisher."""

    python: str | None = None          # e.g. ">=3.11"
    offline: bool | None = None        # None = undeclared
    requires_network: bool | None = None
    requires_credentials: bool | None = None


@dataclass(frozen=True, kw_only=True)
class ForgeRegistryEntry:
    """Published metadata of one provider version (theforge/ForgeRegistryEntry/v1)."""

    schema: str = REGISTRY_ENTRY_SCHEMA
    provider: str
    version: str
    publisher: PublisherIdentity | None = None
    description: str | None = None
    manifest_url: str | None = None
    manifest_sha256: str | None = None
    distribution: DistributionRef | None = None
    protocols: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    platforms: list[str] = field(default_factory=list)
    runtime: RuntimeRequirements | None = None
    hashes: dict[str, str] = field(default_factory=dict)   # name -> sha256 hex
    signatures: list[SignatureRef] = field(default_factory=list)
    source_repository: str | None = None
    license: str | None = None
    security_contact: str | None = None
    released_at: str | None = None
    limitations: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != REGISTRY_ENTRY_SCHEMA:
            raise ContractError(
                f"unsupported schema {self.schema!r}, expected {REGISTRY_ENTRY_SCHEMA!r}")
        if not PROVIDER_ID.match(self.provider):
            raise ContractError(f"registry entry: invalid provider id {self.provider!r}")
        if parse_semver(self.version) is None:
            raise ContractError(
                f"registry entry {self.provider!r}: version {self.version!r} is not "
                "SemVer 2.0.0")
        if self.manifest_sha256 is not None and not SHA256_RE.fullmatch(
                self.manifest_sha256):
            raise ContractError("registry entry: manifest_sha256 must be a sha256 hex")
        for name, digest in self.hashes.items():
            if not SHA256_RE.fullmatch(digest):
                raise ContractError(
                    f"registry entry {self.provider!r}: hash {name!r} is not sha256")
        for platform in self.platforms:
            if not re.fullmatch(PLATFORM_RE_SRC, platform):
                raise ContractError(
                    f"registry entry {self.provider!r}: invalid platform {platform!r}")


@dataclass(frozen=True, kw_only=True)
class RegistryIdentity:
    """Who produced a registry document (§21: identity travels with the data)."""

    id: str
    name: str | None = None
    url: str | None = None

    def __post_init__(self) -> None:
        if not self.id:
            raise ContractError("registry identity: id must not be empty")


@dataclass(frozen=True, kw_only=True)
class RegistryDocument:
    """What a registry source returns (theforge/RegistryDocument/v1)."""

    schema: str = REGISTRY_DOCUMENT_SCHEMA
    registry: RegistryIdentity
    produced_at: str
    entries: list[ForgeRegistryEntry] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != REGISTRY_DOCUMENT_SCHEMA:
            raise ContractError(
                f"unsupported schema {self.schema!r}, expected {REGISTRY_DOCUMENT_SCHEMA!r}")
        ids = [e.provider for e in self.entries]
        if len(set(ids)) != len(ids):
            raise ContractError("registry document: duplicate provider entries")
