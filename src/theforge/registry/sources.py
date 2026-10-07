"""Registry sources (Cycle 4, Wave C/D): where provider *metadata* comes from.

Three levels (§15): the local registry (installed providers — always
authoritative), configured remote/file registries (untrusted metadata), and —
one day — a marketplace UX on top. A *source* only ever yields a
``RegistryDocument`` of ``ForgeRegistryEntry`` records; it never yields trust,
identity, or a ``ProviderEntry`` — remote data cannot silently become an
installed provider (§18, §25).

Configured in ``registries.toml`` (user config dir first, then project
``.forge/config/`` — the project file only *adds* sources by id):

.. code-block:: toml

    [[sources]]
    id = "team-mirror"
    kind = "local-file"        # or "http" (Wave D client)
    path = "registry.json"     # relative to the config file's directory
    enabled = true             # every source is opt-in: default disabled

    [[sources]]
    id = "public-registry"
    kind = "http"
    url = "https://registry.example"
    enabled = false            # remote never surprises (§20 air-gapped)
    max_age_s = 3600           # freshness budget for cached documents (§21)
"""

import json
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from theforge.registry.remote import Fetcher

from theforge.contracts import ContractError, from_dict
from theforge.contracts.canonical import utc_now
from theforge.contracts.registry import (
    ForgeRegistryEntry,
    PublisherIdentity,
    RegistryDocument,
    RegistryIdentity,
    RuntimeRequirements,
)
from theforge.errors import UsageError
from theforge.registry.config import user_config_dir
from theforge.registry.registry import RegistryRecord
from theforge.security.redact import redact_text

__all__ = [
    "REGISTRIES_FILE",
    "SOURCE_KINDS",
    "FileRegistrySource",
    "RegistrySource",
    "SourceRead",
    "SourceSpec",
    "load_source_specs",
    "local_document",
    "read_sources",
]

REGISTRIES_FILE = "registries.toml"
LOCAL_REGISTRY_ID = "local"

SOURCE_KINDS = ("local-file", "http")
SourceKind = Literal["local-file", "http"]


@dataclass(frozen=True, kw_only=True)
class SourceSpec:
    """A configured registry source — inert data, never a live connection."""

    id: str
    kind: SourceKind
    enabled: bool = False  # opt-in: a configured source does nothing until enabled
    path: str | None = None   # local-file: JSON document path (config-relative)
    url: str | None = None    # http: document URL (Wave D client)
    max_age_s: int | None = None  # freshness budget for cached remote documents
    timeout_s: int | None = None  # http: bounded wait per request (default 10)

    def __post_init__(self) -> None:
        if not self.id or not self.id.replace("-", "").replace("_", "").isalnum():
            raise ContractError(f"registry source: invalid id {self.id!r}")
        if self.kind == "local-file" and not self.path:
            raise ContractError(f"registry source {self.id!r}: local-file requires 'path'")
        if self.kind == "http" and not self.url:
            raise ContractError(f"registry source {self.id!r}: http requires 'url'")
        if self.max_age_s is not None and self.max_age_s <= 0:
            raise ContractError(
                f"registry source {self.id!r}: max_age_s must be positive")
        if self.timeout_s is not None and self.timeout_s <= 0:
            raise ContractError(
                f"registry source {self.id!r}: timeout_s must be positive")


def load_source_specs(forge_dir: Path | None, user_dir: Path | None = None,
                      warnings: list[str] | None = None) -> list[SourceSpec]:
    """All configured sources: user ``registries.toml`` first, then the project
    file adds ids not already defined (the project file can never override a
    user source — same precedence philosophy as providers.toml)."""
    merged: dict[str, SourceSpec] = {}
    user_path = (user_dir or user_config_dir()) / REGISTRIES_FILE
    paths = [user_path]
    if forge_dir is not None:
        paths.append(forge_dir / "config" / REGISTRIES_FILE)
    for path in paths:
        for spec in _read_specs(path):
            if spec.id in merged:
                if warnings is not None:
                    warnings.append(
                        f"{path}: registry source {spec.id!r} ignored; already defined "
                        "in the user registries.toml")
                continue
            merged[spec.id] = spec
    return sorted(merged.values(), key=lambda s: s.id)


def _read_specs(path: Path) -> list[SourceSpec]:
    if not path.is_file():
        return []
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise UsageError(f"{path}: cannot read registries file ({exc})") from exc
    items = data.get("sources", [])
    if not isinstance(items, list):
        raise UsageError(f"{path}: 'sources' must be an array of tables")
    specs: list[SourceSpec] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise UsageError(f"{path}: sources[{index}] must be a table")
        raw = dict(item)
        source_path = raw.get("path")
        if isinstance(source_path, str) and source_path and not Path(source_path).anchor:
            raw["path"] = str(path.parent / source_path)
        try:
            specs.append(from_dict(SourceSpec, raw, f"{path.name}.sources[{index}]"))
        except ContractError as exc:
            raise UsageError(str(exc)) from exc
    return specs


class RegistrySource(Protocol):
    """A readable registry source (protocol, not a base class: Wave D adds the
    http client without touching this layer)."""

    @property
    def spec(self) -> SourceSpec: ...

    def read(self) -> "SourceRead":
        """The read outcome: a document, or the explicit reason it is absent —
        an unavailable source is data, not an exception (§20)."""
        ...


@dataclass(frozen=True, kw_only=True)
class SourceRead:
    """One source attempted: the document or the explicit reason it is absent.
    Freshness metadata travels with remote reads — stale is never silently
    fresh (§21)."""

    spec: SourceSpec
    status: Literal["ok", "disabled", "unavailable", "invalid", "stale"]
    document: RegistryDocument | None = None
    detail: str | None = None
    # Remote-read provenance (None for local-file reads).
    freshness: Literal["fresh", "stale", "unknown"] = "unknown"
    from_cache: bool = False
    retrieved_at: str | None = None
    etag: str | None = None
    body_sha256: str | None = None
    # Discovery economy (§47): bytes of metadata this read consumed and the
    # network latency it paid (``None`` when no network fetch happened —
    # cached and local reads report the bytes, not a latency).
    bytes_received: int = 0
    latency_ms: float | None = None


@dataclass(frozen=True, kw_only=True)
class FileRegistrySource:
    """``local-file``: a ``RegistryDocument`` JSON file — the offline-friendly
    registry stand-in (mirrors, vendored catalogs, air-gapped feeds)."""

    spec: SourceSpec

    def read(self) -> SourceRead:
        assert self.spec.path is not None  # enforced by SourceSpec
        path = Path(self.spec.path)
        try:
            body = path.read_bytes()
            data = json.loads(body.decode("utf-8"))
        except OSError as exc:
            return SourceRead(spec=self.spec, status="unavailable",
                              detail=f"{self.spec.id}: {exc.strerror or exc}")
        except ValueError:
            return SourceRead(spec=self.spec, status="invalid",
                              detail=f"{self.spec.id}: not a JSON document")
        try:
            # Tolerant decode: a registry document is external metadata that
            # may carry newer fields — forward-compat beats strictness here.
            document = from_dict(RegistryDocument, data, "$")
        except ContractError as exc:
            return SourceRead(spec=self.spec, status="invalid",
                              detail=f"{self.spec.id}: {redact_text(str(exc))}")
        return SourceRead(spec=self.spec, status="ok", document=document,
                          bytes_received=len(body))


def read_sources(specs: Sequence[SourceSpec], *, fetcher: "Fetcher | None" = None,
                 cache_dir: Path | None = None) -> list[SourceRead]:
    """Read every *enabled* source, in spec order; disabled ones are reported
    as ``disabled`` so the UX can say a source exists but is off (§20).

    ``fetcher``/``cache_dir`` exist for tests and embeddings — production
    callers leave them None (urllib transport, user cache dir)."""
    reads: list[SourceRead] = []
    for spec in specs:
        if not spec.enabled:
            reads.append(SourceRead(spec=spec, status="disabled"))
            continue
        source: RegistrySource
        if spec.kind == "local-file":
            source = FileRegistrySource(spec=spec)
        else:  # http — read-only remote client (Wave D)
            from theforge.registry.remote import HttpRegistrySource
            source = HttpRegistrySource(spec=spec, fetcher=fetcher,
                                        cache_dir=cache_dir)
        reads.append(source.read())
    return reads


def local_document(records: Sequence[RegistryRecord]) -> RegistryDocument:
    """Project installed providers into registry-entry metadata (§16): the
    local registry is a *source* too — authoritative because it is built from
    verified manifests, never from self-declared remote claims."""
    entries: list[ForgeRegistryEntry] = []
    for record in records:
        manifest = record.manifest
        if record.state != "ready" or manifest is None:
            continue
        entries.append(ForgeRegistryEntry(
            provider=manifest.id, version=manifest.version,
            publisher=PublisherIdentity(id=f"local:{manifest.id}"),
            description=None,
            protocols=list(manifest.protocols),
            capabilities=sorted(c.id for c in manifest.capabilities
                                if c.state != "unsupported"),
            platforms=["any"],
            runtime=RuntimeRequirements(
                python=None, offline=manifest.execution.offline,
                requires_network=manifest.execution.requires_network),
            hashes={"manifest_sha256": record.manifest_sha256}
            if record.manifest_sha256 else {},
            limitations=list(manifest.limitations)))
    return RegistryDocument(
        registry=RegistryIdentity(id=LOCAL_REGISTRY_ID, name="installed providers"),
        produced_at=utc_now(), entries=entries)
