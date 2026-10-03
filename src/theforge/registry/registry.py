"""Registry: describe providers, negotiate protocol, cache ready manifests, apply trust."""

import contextlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from theforge.contracts import ContractError, ForgeManifest, from_dict, to_dict
from theforge.contracts.canonical import sha256_of, utc_now
from theforge.errors import UsageError
from theforge.protocol import (
    SUPPORTED_PROTOCOLS,
    SubprocessTransport,
    TransportError,
    TransportFactory,
    choose_protocol,
)
from theforge.registry.config import ProviderEntry, resolve_entries, user_cache_dir
from theforge.registry.identity import fingerprint
from theforge.state import LEGACY_REGISTRY_DIR, remove_legacy_cache

RecordState = Literal[
    "ready", "incompatible", "invalid", "unreachable", "blocked", "untrusted"
]
CACHE_SCHEMA: Final = "theforge/RegistryCache/v2"
DESCRIBE_TIMEOUT = 10.0
ROUTABLE_TRUST = frozenset({"builtin", "trusted", "local"})


@dataclass(frozen=True, kw_only=True)
class RegistryRecord:
    entry: ProviderEntry
    state: RecordState
    manifest: ForgeManifest | None = None
    manifest_sha256: str | None = None
    protocol: str | None = None
    error: str | None = None

    def routable(self, allow_unverified: bool = False) -> bool:
        if self.state != "ready" or self.manifest is None:
            return False
        if self.entry.trust in ROUTABLE_TRUST:
            return True
        return allow_unverified and self.entry.trust == "unverified"


@dataclass(frozen=True, kw_only=True)
class RegistryCacheEntry:
    """On-disk registry cache document (user cache dir), re-read with ``strict=True``."""

    schema: Literal["theforge/RegistryCache/v2"]
    entry: ProviderEntry
    entry_digest: str
    fingerprint: str
    state: Literal["ready"]
    manifest: ForgeManifest
    manifest_sha256: str
    protocol: str
    written_at: str


class Registry:
    def __init__(
        self, forge_dir: Path | None, *, user_dir: Path | None = None,
        cache_dir: Path | None = None, transport_factory: TransportFactory = SubprocessTransport,
        timeout: float = DESCRIBE_TIMEOUT, allow_unverified: bool = False,
    ) -> None:
        self.forge_dir = forge_dir
        self.user_dir = user_dir
        self.cache_dir = cache_dir if cache_dir is not None else user_cache_dir()
        self.transport_factory = transport_factory
        self.timeout = timeout
        self.allow_unverified = allow_unverified
        self.warnings: list[str] = []

    def entries(self) -> list[ProviderEntry]:
        return resolve_entries(self.forge_dir, self.user_dir, self.warnings)

    def refresh(self) -> list[RegistryRecord]:
        self._remove_legacy_cache()
        records = [self._describe(entry) for entry in self.entries()]
        for record in records:
            self._write_cache(record)
        return records

    def records(self, *, persist: bool = True) -> list[RegistryRecord]:
        out: list[RegistryRecord] = []
        for entry in self.entries():
            record = self._read_cache(entry)
            if record is None:
                record = self._describe(entry)
                if persist:
                    self._write_cache(record)
            out.append(record)
        return out

    def get(self, provider_id: str) -> RegistryRecord:
        for record in self.records():
            if record.entry.id == provider_id:
                return record
        raise UsageError(f"unknown provider {provider_id!r} (see `theforge registry list`)")

    def _describe(self, entry: ProviderEntry) -> RegistryRecord:
        if entry.trust == "blocked":
            return RegistryRecord(entry=entry, state="blocked", error="provider is blocked")
        if entry.trust == "unverified" and not self.allow_unverified:
            return RegistryRecord(
                entry=entry, state="untrusted",
                error="provider is unverified and was not executed; trust it in your user "
                      "providers.toml or pass --allow-unverified")
        try:
            response = self.transport_factory(entry.argv).call(
                "describe", {}, timeout=self.timeout, check_protocol=False)
        except TransportError as exc:
            return RegistryRecord(entry=entry, state="unreachable",
                                  error=f"{exc.code}: {exc.detail}")
        if response.status != "ok":
            code = response.error.code if response.error else response.status
            return RegistryRecord(entry=entry, state="invalid", error=f"describe {code}")
        try:
            manifest = from_dict(ForgeManifest, response.payload, "$.payload")
        except ContractError as exc:
            return RegistryRecord(entry=entry, state="invalid", error=str(exc))
        if manifest.id != entry.id:
            return RegistryRecord(
                entry=entry, state="invalid",
                error=f"manifest id {manifest.id!r} does not match registry entry {entry.id!r}")
        digest = sha256_of(to_dict(manifest))
        protocol = choose_protocol(manifest.protocols)
        if protocol is None:
            return RegistryRecord(
                entry=entry, state="incompatible", manifest=manifest, manifest_sha256=digest,
                error=f"no common protocol (offered {manifest.protocols}, "
                      f"supported {list(SUPPORTED_PROTOCOLS)})")
        return RegistryRecord(entry=entry, state="ready", manifest=manifest,
                              manifest_sha256=digest, protocol=protocol)

    def cached_ids(self) -> list[str]:
        """Ids of configured providers that currently have a cache file (no describe)."""
        return sorted(e.id for e in self.entries() if self._cache_path(e).is_file())

    def _cache_path(self, entry: ProviderEntry) -> Path:
        digest = sha256_of(to_dict(entry))
        return self.cache_dir / "registry" / f"{entry.id}-{digest[:12]}.json"

    def _remove_legacy_cache(self) -> None:
        if self.forge_dir is None:
            return
        legacy = self.forge_dir / LEGACY_REGISTRY_DIR
        warning = remove_legacy_cache(legacy)
        if warning:
            self.warnings.append(warning)

    def _write_cache(self, record: RegistryRecord) -> None:
        path = self._cache_path(record.entry)
        try:
            if (record.state != "ready" or record.entry.trust == "unverified"
                    or record.manifest is None or record.manifest_sha256 is None
                    or record.protocol is None):
                path.unlink(missing_ok=True)
                return
            cached = RegistryCacheEntry(
                schema=CACHE_SCHEMA, entry=record.entry,
                entry_digest=sha256_of(to_dict(record.entry)),
                fingerprint=fingerprint(record.entry).digest, state="ready",
                manifest=record.manifest, manifest_sha256=record.manifest_sha256,
                protocol=record.protocol, written_at=utc_now())
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.stem}-", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(json.dumps(to_dict(cached), indent=2, sort_keys=True))
                os.replace(tmp, path)
            except BaseException:
                with contextlib.suppress(OSError):
                    os.unlink(tmp)
                raise
        except OSError as exc:
            self.warnings.append(
                f"registry cache for {record.entry.id} not written ({path}): {exc}")

    def _read_cache(self, entry: ProviderEntry) -> RegistryRecord | None:
        if entry.trust == "unverified":
            return None
        path = self._cache_path(entry)
        try:
            if not path.is_file():
                return None
            doc = json.loads(path.read_text(encoding="utf-8"))
            cached = from_dict(RegistryCacheEntry, doc, "$", strict=True)
            if cached.entry != entry or cached.entry_digest != sha256_of(to_dict(entry)):
                return None
            if cached.fingerprint != fingerprint(entry).digest:
                return None
            if sha256_of(to_dict(cached.manifest)) != cached.manifest_sha256:
                raise ValueError("manifest hash mismatch")
            if cached.manifest.id != entry.id:
                raise ValueError("manifest id does not match registry entry")
            protocol = choose_protocol(cached.manifest.protocols)
            if protocol is None or protocol != cached.protocol:
                raise ValueError("cached protocol does not match negotiated protocol")
            return RegistryRecord(entry=entry, state="ready", manifest=cached.manifest,
                                  manifest_sha256=cached.manifest_sha256, protocol=protocol)
        except (OSError, ValueError) as exc:
            self.warnings.append(f"registry cache for {entry.id} discarded: {exc}")
            return None

