"""Registry: describe providers, negotiate protocol, cache ready manifests, apply trust."""

import contextlib
import json
import os
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final, Literal

from theforge.contracts import ContractError, ForgeManifest, Producer, from_dict, to_dict
from theforge.contracts.canonical import sha256_of, utc_now
from theforge.contracts.codes import Codes
from theforge.contracts.integrity import check_producer, validate_manifest_limits
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
from theforge.security.redact import redact
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


@dataclass(frozen=True, kw_only=True)
class RevalidationOutcome:
    """Result of re-describing a provider and comparing it with the record in use."""

    status: Literal["fresh", "changed", "unreachable"]
    record: RegistryRecord


def provider_cwd() -> tempfile.TemporaryDirectory[str]:
    """Fresh, controlled working directory for one describe/health call (5.4)."""
    return tempfile.TemporaryDirectory(prefix="theforge-", ignore_cleanup_errors=True)


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
        self._in_use: dict[str, RegistryRecord] = {}

    def entries(self) -> list[ProviderEntry]:
        found: list[str] = []
        entries = resolve_entries(self.forge_dir, self.user_dir, found)
        for warning in found:  # config is re-read on every lookup: record each warning once
            self._warn(warning)
        return entries

    def _warn(self, warning: str) -> None:
        if warning not in self.warnings:
            self.warnings.append(warning)

    def refresh(self) -> list[RegistryRecord]:
        self._remove_legacy_cache()
        records = [self._describe(entry) for entry in self.entries()]
        for record in records:
            self._write_cache(record)
        self._in_use = {r.entry.id: r for r in records}
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
        self._in_use = {r.entry.id: r for r in out}
        return out

    def get(self, provider_id: str) -> RegistryRecord:
        for record in self.records():
            if record.entry.id == provider_id:
                return record
        raise _unknown(provider_id)

    def revalidate(self, provider_ids: Sequence[str]) -> list[RevalidationOutcome]:
        """Describe each provider again and compare it with the record in use (4.3).

        The record in use is the one last returned by ``records``/``refresh`` on this
        instance, else the cached one. Nothing is written: a caller that sees ``changed``
        calls ``invalidate`` and reloads.
        """
        entries = {e.id: e for e in self.entries()}
        outcomes: list[RevalidationOutcome] = []
        for provider_id in provider_ids:
            entry = entries.get(provider_id)
            if entry is None:
                raise _unknown(provider_id)
            in_use = self._in_use.get(provider_id)
            if in_use is None or in_use.entry != entry:
                in_use = self._read_cache(entry)
            fresh = self._describe(entry)
            status: Literal["fresh", "changed", "unreachable"]
            if fresh.state == "unreachable":
                status = "unreachable"
            elif (in_use is not None and fresh.state == in_use.state
                  and fresh.manifest_sha256 == in_use.manifest_sha256
                  and fresh.protocol == in_use.protocol):
                status = "fresh"
            else:
                status = "changed"
            outcomes.append(RevalidationOutcome(status=status, record=fresh))
        return outcomes

    def invalidate(self, provider_id: str) -> None:
        """Drop the cached and in-memory record of ``provider_id``; the next read describes."""
        self._in_use.pop(provider_id, None)
        for entry in self.entries():
            if entry.id != provider_id:
                continue
            path = self._cache_path(entry)
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                self._warn(
                    f"registry cache for {provider_id} not removed ({path}): {exc}")

    def _describe(self, entry: ProviderEntry) -> RegistryRecord:
        if entry.trust == "blocked":
            return RegistryRecord(entry=entry, state="blocked", error="provider is blocked")
        if entry.trust == "unverified" and not self.allow_unverified:
            return RegistryRecord(
                entry=entry, state="untrusted",
                error="provider is unverified and was not executed; trust it in your user "
                      "providers.toml or pass --allow-unverified")
        try:
            with provider_cwd() as cwd:
                response = self.transport_factory(entry.argv).call(
                    "describe", {}, timeout=self.timeout, cwd=Path(cwd), check_protocol=False)
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
        violation = check_producer(
            response.producer, expected=Producer(id=entry.id, version=manifest.version),
            field="$.producer")
        if violation is not None:
            return RegistryRecord(entry=entry, state="invalid",
                                  error=f"{violation.code}: {violation.detail}")
        limited = self._apply_limits(manifest)
        if isinstance(limited, str):
            return RegistryRecord(entry=entry, state="invalid", error=limited)
        manifest = limited
        digest = sha256_of(to_dict(manifest))
        protocol = choose_protocol(manifest.protocols)
        if protocol is None:
            return RegistryRecord(
                entry=entry, state="incompatible", manifest=manifest, manifest_sha256=digest,
                error=f"no common protocol (offered {manifest.protocols}, "
                      f"supported {list(SUPPORTED_PROTOCOLS)})")
        return RegistryRecord(entry=entry, state="ready", manifest=manifest,
                              manifest_sha256=digest, protocol=protocol)

    def _apply_limits(self, manifest: ForgeManifest) -> ForgeManifest | str:
        """Exclude capabilities over the manifest limits, with a warning (1.9).

        Returns the (possibly filtered) manifest, or an error string when the manifest
        itself is over the limits or no capability remains after the exclusion.
        """
        violations = validate_manifest_limits(manifest)
        if not violations:
            return manifest
        manifest_level = [v for v in violations if v.field == "capabilities"]
        if manifest_level:
            return f"{Codes.MANIFEST_LIMITS}: {manifest_level[0].detail}"
        excluded: dict[int, str] = {}
        for v in violations:
            index = _capability_index(v.field)
            if index is not None:
                excluded.setdefault(index, v.detail)
        kept = [c for i, c in enumerate(manifest.capabilities) if i not in excluded]
        if not kept:
            first = next(iter(excluded.values()))
            return (f"{Codes.MANIFEST_LIMITS}: every capability of {manifest.id} exceeds "
                    f"the manifest limits ({first})")
        for index, detail in sorted(excluded.items()):
            self._warn(
                f"{manifest.id}: capability {manifest.capabilities[index].id!r} excluded "
                f"({Codes.MANIFEST_LIMITS}: {detail})")
        return replace(manifest, capabilities=kept)

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
            self._warn(warning)

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
            document = to_dict(cached)
            if redact(document) != document:
                # Persisted data must pass through redaction, but the cache is re-read
                # strictly against the live entry and manifest hash: a redacted copy would
                # never match. Secret-shaped values therefore disable caching instead.
                path.unlink(missing_ok=True)
                self._warn(f"registry cache for {record.entry.id} not cached: its entry or "
                           "manifest contains secret-shaped values (described on every use)")
                return
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.stem}-", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(json.dumps(document, indent=2, sort_keys=True))
                os.replace(tmp, path)
            except BaseException:
                with contextlib.suppress(OSError):
                    os.unlink(tmp)
                raise
        except OSError as exc:
            self._warn(
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
            self._warn(f"registry cache for {entry.id} discarded: {exc}")
            return None



def _unknown(provider_id: str) -> UsageError:
    return UsageError(f"unknown provider {provider_id!r} (see `theforge registry list`)")


def _capability_index(field: str | None) -> int | None:
    """``capabilities[3].signals.file_globs[0]`` -> 3; anything else -> None."""
    prefix = "capabilities["
    if field is None or not field.startswith(prefix):
        return None
    number, sep, _ = field[len(prefix):].partition("]")
    return int(number) if sep and number.isdigit() else None
