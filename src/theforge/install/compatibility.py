"""EcosystemCompatibility: which component versions form a certified release.

Cycle 8 (ecosystem-2026 program): the nine Forge repositories ship on
independent lifecycles. The manifest — ``forge/EcosystemCompatibility/v1``,
part of the install-plane ``forge/*`` contract family documented in
``docs/portable-installation/`` — is the declared source of truth for which
*combination* of component versions is certified, plus the supported major
windows of the wire contracts that cross between components.

Declared data, not evidence: certification comes from the release pipeline
that publishes the manifest, never from the document asserting itself.
Consumers (forge-cli, Portal, hosts) read the JSON document; this module
validates its shape and answers the two questions consumers ask: "is this
component version certified?" and "is this contract major supported?".
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from theforge.contracts.base import ContractError, from_dict, to_dict
from theforge.contracts.semver import parse_semver
from theforge.contracts.types import Producer

ECOSYSTEM_SCHEMA = "forge/EcosystemCompatibility/v1"

RELEASE_ID_RE = re.compile(r"^[0-9]{4}\.(0[1-9]|1[0-2])$", re.ASCII)
COMPONENT_ID_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$", re.ASCII)
FAMILY_ID_RE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$", re.ASCII)
CONTRACT_REF_RE = re.compile(r"^(forge|theforge)/[A-Z][A-Za-z0-9]*$", re.ASCII)
PEP440_VERSION_RE = re.compile(r"^[0-9]+(\.[0-9]+)*((a|b|rc)[0-9]+)?(\.post[0-9]+)?$", re.ASCII)
DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$", re.ASCII)


@dataclass(frozen=True, kw_only=True)
class ContractRange:
    """Supported major-version window of one wire-contract family.

    ``contract=None`` is the honest *unversioned* state — the family is named
    (e.g. ``portal_api`` before the Portal publishes its own contract) instead
    of being silently absent, and range fields must stay unset.
    """

    family: str
    contract: str | None = None
    min_major: int | None = None
    max_major: int | None = None

    def __post_init__(self) -> None:
        if not FAMILY_ID_RE.fullmatch(self.family):
            raise ContractError(f"compat manifest: bad contract family {self.family!r}")
        if self.contract is None:
            if self.min_major is not None or self.max_major is not None:
                raise ContractError(
                    f"compat manifest: family {self.family!r} is unversioned "
                    "(contract=null) — min_major/max_major must be unset"
                )
            return
        if not CONTRACT_REF_RE.fullmatch(self.contract):
            raise ContractError(
                f"compat manifest: bad contract id {self.contract!r} "
                "(expected e.g. 'theforge/ForgeManifest' or 'forge/InstallReceipt')"
            )
        if self.min_major is None or self.max_major is None:
            raise ContractError(
                f"compat manifest: family {self.family!r} requires both min_major and max_major"
            )
        if self.min_major < 1 or self.max_major < self.min_major:
            raise ContractError(
                f"compat manifest: invalid major window "
                f"[{self.min_major}, {self.max_major}] for {self.family!r}"
            )


@dataclass(frozen=True, kw_only=True)
class ComponentVersion:
    """One certified component version with its declared scheme and provenance."""

    component: str
    version: str
    scheme: Literal["semver", "pep440"] = "semver"
    source: str = ""  # where the version is declared (e.g. "pyproject.toml")
    distribution: str | None = None  # package name once published; None = source-only

    def __post_init__(self) -> None:
        if not COMPONENT_ID_RE.fullmatch(self.component):
            raise ContractError(f"compat manifest: bad component id {self.component!r}")
        if self.version in ("", "latest"):
            raise ContractError(
                f"compat manifest: {self.component} requires a pinned version "
                "— 'latest' is never certifiable"
            )
        if self.scheme == "semver":
            if parse_semver(self.version) is None:
                raise ContractError(
                    f"compat manifest: {self.component} version {self.version!r} "
                    "is not SemVer 2.0.0 (declared scheme 'semver')"
                )
        elif not PEP440_VERSION_RE.fullmatch(self.version):
            raise ContractError(
                f"compat manifest: {self.component} version {self.version!r} "
                "is not PEP 440-shaped (declared scheme 'pep440')"
            )
        if not self.source:
            raise ContractError(
                f"compat manifest: {self.component} requires 'source' — "
                "published manifests carry zero fictional versions"
            )


CheckVerdict = Literal["certified", "incompatible", "unknown"]


@dataclass(frozen=True, kw_only=True)
class EcosystemCompatibility:
    """``forge/EcosystemCompatibility/v1`` — certified release combination."""

    schema: str = ECOSYSTEM_SCHEMA
    release: str
    created_at: str
    producer: Producer
    components: list[ComponentVersion]
    contracts: list[ContractRange]
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema != ECOSYSTEM_SCHEMA:
            raise ContractError(
                f"compat manifest: unsupported schema {self.schema!r}, "
                f"expected {ECOSYSTEM_SCHEMA!r}"
            )
        if not RELEASE_ID_RE.fullmatch(self.release):
            raise ContractError(
                f"compat manifest: bad release id {self.release!r} (expected YYYY.MM)"
            )
        if not DATE_RE.fullmatch(self.created_at):
            raise ContractError(
                f"compat manifest: created_at must be ISO date, got {self.created_at!r}"
            )
        if not self.components:
            raise ContractError("compat manifest: components must not be empty")
        ids = [c.component for c in self.components]
        if len(set(ids)) != len(ids):
            raise ContractError("compat manifest: duplicate component ids")
        families = [r.family for r in self.contracts]
        if len(set(families)) != len(families):
            raise ContractError("compat manifest: duplicate contract families")

    def component(self, component: str) -> ComponentVersion | None:
        return next((c for c in self.components if c.component == component), None)

    def check(self, component: str, version: str) -> CheckVerdict:
        """Is ``component@version`` part of this certified combination?

        Exact-match on the declared version string — compatibility *evaluation*
        beyond membership (downgrade windows, partial upgrades) is the
        consumer's policy, not the manifest's.
        """

        entry = self.component(component)
        if entry is None:
            return "unknown"
        return "certified" if entry.version == version else "incompatible"

    def contract_supported(self, family: str, major: int) -> bool:
        """Is ``major`` inside the declared window of ``family``?

        False for absent and for honestly-unversioned families.
        """

        entry = next((r for r in self.contracts if r.family == family), None)
        if entry is None or entry.min_major is None or entry.max_major is None:
            return False
        return entry.min_major <= major <= entry.max_major


def parse_manifest(data: Any, *, strict: bool = False) -> EcosystemCompatibility:
    """Parse manifest data (already-decoded JSON). Never raises on good input;

    on bad input raises ``ContractError`` naming the offending path.
    """

    return from_dict(EcosystemCompatibility, data, strict=strict)


def load_manifest(path: Path) -> EcosystemCompatibility:
    """Load and validate a committed/published manifest file."""

    return parse_manifest(json.loads(path.read_text(encoding="utf-8")), strict=True)


def dump_manifest(manifest: EcosystemCompatibility) -> dict[str, Any]:
    return to_dict(manifest)
