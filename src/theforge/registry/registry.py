"""Registry: describe providers, negotiate protocol, cache ready manifests, apply trust."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from theforge.contracts import ContractError, ForgeManifest, from_dict, to_dict
from theforge.contracts.canonical import sha256_of
from theforge.errors import PersistenceError, UsageError
from theforge.protocol import (
    SUPPORTED_PROTOCOLS,
    SubprocessTransport,
    TransportError,
    TransportFactory,
    choose_protocol,
)
from theforge.registry.config import ProviderEntry, resolve_entries

RecordState = Literal[
    "ready", "incompatible", "invalid", "unreachable", "blocked", "untrusted"
]
CACHE_SCHEMA = "theforge/RegistryCache/v1"
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


class Registry:
    def __init__(
        self, forge_dir: Path | None, *, user_dir: Path | None = None,
        transport_factory: TransportFactory = SubprocessTransport,
        timeout: float = DESCRIBE_TIMEOUT, allow_unverified: bool = False,
    ) -> None:
        self.forge_dir = forge_dir
        self.user_dir = user_dir
        self.transport_factory = transport_factory
        self.timeout = timeout
        self.allow_unverified = allow_unverified
        self.warnings: list[str] = []

    def entries(self) -> list[ProviderEntry]:
        return resolve_entries(self.forge_dir, self.user_dir, self.warnings)

    def refresh(self) -> list[RegistryRecord]:
        records = [self._describe(entry) for entry in self.entries()]
        for record in records:
            self._write_cache(record)
        return records

    def records(self) -> list[RegistryRecord]:
        out: list[RegistryRecord] = []
        for entry in self.entries():
            record = self._read_cache(entry)
            if record is None:
                record = self._describe(entry)
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

    def _cache_path(self, provider_id: str) -> Path | None:
        if self.forge_dir is None:
            return None
        return self.forge_dir / "registry" / f"{provider_id}.json"

    def _write_cache(self, record: RegistryRecord) -> None:
        path = self._cache_path(record.entry.id)
        if path is None:
            return
        try:
            if record.state != "ready" or record.entry.trust == "unverified":
                path.unlink(missing_ok=True)
                return
            doc = {"schema": CACHE_SCHEMA, **to_dict(record)}
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(json.dumps(doc, indent=2, sort_keys=True), encoding="utf-8")
            tmp.replace(path)
        except OSError as exc:
            raise PersistenceError(f"cannot write registry cache {path}: {exc}") from exc

    def _read_cache(self, entry: ProviderEntry) -> RegistryRecord | None:
        path = self._cache_path(entry.id)
        if path is None or not path.is_file():
            return None
        if entry.trust == "unverified":
            return None
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(doc, dict) or doc.get("schema") != CACHE_SCHEMA:
                raise ValueError("unexpected cache schema")
            record = from_dict(RegistryRecord, doc)
            if record.entry != entry:
                return None
            if record.manifest is None or record.state != "ready":
                raise ValueError("cache entry is not a ready manifest")
            if sha256_of(to_dict(record.manifest)) != record.manifest_sha256:
                raise ValueError("manifest hash mismatch")
            if record.manifest.id != entry.id:
                raise ValueError("manifest id does not match registry entry")
            protocol = choose_protocol(record.manifest.protocols)
            if protocol is None or protocol != record.protocol:
                raise ValueError("cached protocol does not match negotiated protocol")
            return record
        except (OSError, ValueError) as exc:
            self.warnings.append(f"registry cache for {entry.id} discarded: {exc}")
            return None
