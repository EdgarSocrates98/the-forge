"""Optional MCP registry awareness (Cycle 4, Wave J).

A ``mcp`` source reads a page of the official MCP Registry API
(``GET /v0{,.1}/servers``) into a bounded ``McpRegistryDocument`` — *tooling
metadata*, a different object than provider registries on purpose: an MCP
server is never a Forge provider (§68), so these reads never flow through
``read_sources``/``SourceRead.document`` or into capability negotiation.

Same transport discipline as ``http`` sources: https-only (loopback http for
tests), size cap, hash-verified cache, explicit freshness, and the
``THEFORGE_NO_NETWORK`` kill-switch.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from theforge.contracts.canonical import utc_now
from theforge.contracts.mcp import McpRegistryDocument
from theforge.interop.mcp import parse_server_list
from theforge.registry.config import user_cache_dir
from theforge.registry.remote import (
    DEFAULT_MAX_AGE_S,
    DEFAULT_TIMEOUT_S,
    MAX_BODY_BYTES,
    CacheEnvelope,
    Fetcher,
    _age_s,
    _check_url,
    default_fetcher,
    network_disabled,
    read_envelope,
    touch_envelope,
    write_envelope,
)
from theforge.registry.sources import SourceSpec
from theforge.security.redact import redact_text

__all__ = [
    "McpRegistrySource",
    "McpSourceRead",
    "read_mcp_sources",
]


@dataclass(frozen=True, kw_only=True)
class McpSourceRead:
    """One ``mcp`` source attempted — same provenance fields as ``SourceRead``,
    a different document type (tooling metadata, not provider metadata)."""

    spec: SourceSpec
    status: Literal["ok", "disabled", "unavailable", "invalid", "stale"]
    document: McpRegistryDocument | None = None
    detail: str | None = None
    freshness: Literal["fresh", "stale", "unknown"] = "unknown"
    from_cache: bool = False
    retrieved_at: str | None = None
    bytes_received: int = 0
    latency_ms: float | None = None


class McpRegistrySource:
    """``mcp`` source: one bounded page of MCP server metadata per read."""

    def __init__(self, spec: SourceSpec, *, fetcher: Fetcher | None = None,
                 cache_dir: Path | None = None,
                 clock: Callable[[], str] = utc_now):
        self.spec = spec
        self._fetcher = fetcher or default_fetcher
        self._cache_dir = cache_dir if cache_dir is not None else (
            user_cache_dir() / "mcp")
        self._clock = clock

    @property
    def _cache_path(self) -> Path:
        return self._cache_dir / f"{self.spec.id}.json"

    def _decode(self, body: str) -> McpRegistryDocument | None:
        document, _error = parse_server_list(
            body, source_id=self.spec.id, produced_at=self._clock())
        return document

    def read(self) -> McpSourceRead:
        spec = self.spec
        if not spec.enabled:
            return McpSourceRead(spec=spec, status="disabled")
        assert spec.url is not None  # enforced by SourceSpec
        if detail := _check_url(spec.url, spec.id):
            return McpSourceRead(spec=spec, status="invalid", detail=detail)

        envelope = read_envelope(self._cache_path, spec.id, spec.url)
        document = self._decode(envelope.body) if envelope else None
        cached = envelope if document is not None else None
        if network_disabled():
            if cached is not None:
                assert document is not None
                return self._cached_read(cached, document, "network disabled")
            return McpSourceRead(spec=spec, status="unavailable",
                                 detail=f"{spec.id}: network disabled "
                                        "and no cache")

        max_age = spec.max_age_s or DEFAULT_MAX_AGE_S
        now = self._clock()
        if cached is not None:
            age = _age_s(cached.retrieved_at, now)
            if age is not None and age <= max_age:
                return McpSourceRead(
                    spec=spec, status="ok", document=document,
                    freshness="fresh", from_cache=True,
                    retrieved_at=cached.retrieved_at,
                    bytes_received=cached.body_bytes)

        started = time.monotonic()
        try:
            response = self._fetcher(
                spec.url,
                {"Accept": "application/json",
                 **({"If-None-Match": cached.etag}
                    if cached and cached.etag else {})},
                float(spec.timeout_s or DEFAULT_TIMEOUT_S))
        except Exception as exc:  # noqa: BLE001 — transport failure is data
            return self._degraded(spec, cached, document,
                                  f"fetch failed: {type(exc).__name__}")
        latency_ms = (time.monotonic() - started) * 1000.0

        if response.status == 304 and cached is not None:
            touch_envelope(self._cache_path, clock=self._clock)
            return McpSourceRead(spec=spec, status="ok", document=document,
                                 freshness="fresh", from_cache=True,
                                 retrieved_at=now,
                                 bytes_received=cached.body_bytes,
                                 latency_ms=latency_ms)
        if response.status != 200:
            return self._degraded(spec, cached, document,
                                  f"HTTP {response.status}")
        if len(response.body) > MAX_BODY_BYTES:
            return self._degraded(spec, cached, document,
                                  "response too large")

        try:
            text = response.body.decode("utf-8")
        except UnicodeDecodeError as exc:
            return McpSourceRead(spec=spec, status="invalid",
                                 detail=f"{spec.id}: "
                                        f"{redact_text(str(exc))[:200]}")
        fresh_document = self._decode(text)
        if fresh_document is None:
            return McpSourceRead(spec=spec, status="invalid",
                                 detail=f"{spec.id}: not an MCP server list")
        body_sha = hashlib.sha256(response.body).hexdigest()
        etag = next((v for k, v in response.headers.items()
                     if k.lower() == "etag"), None)
        write_envelope(self._cache_path, source_id=spec.id, url=spec.url,
                       retrieved_at=now, etag=etag, body_sha=body_sha,
                       body=text)
        return McpSourceRead(spec=spec, status="ok", document=fresh_document,
                             freshness="fresh", retrieved_at=now,
                             bytes_received=len(response.body),
                             latency_ms=latency_ms)

    def _cached_read(self, envelope: CacheEnvelope,
                     document: McpRegistryDocument,
                     note: str) -> McpSourceRead:
        spec = self.spec
        max_age = spec.max_age_s or DEFAULT_MAX_AGE_S
        age = _age_s(envelope.retrieved_at, self._clock())
        fresh = age is not None and age <= max_age
        return McpSourceRead(
            spec=spec, status="ok" if fresh else "stale",
            document=document,
            freshness="fresh" if fresh else "stale",
            from_cache=True, retrieved_at=envelope.retrieved_at,
            bytes_received=envelope.body_bytes, detail=None if fresh else
            f"{spec.id}: {note}; cached document is stale")

    def _degraded(self, spec: SourceSpec, envelope: CacheEnvelope | None,
                  document: McpRegistryDocument | None,
                  why: str) -> McpSourceRead:
        if envelope is not None and document is not None:
            return McpSourceRead(
                spec=spec, status="stale", document=document,
                freshness="stale", from_cache=True,
                retrieved_at=envelope.retrieved_at,
                bytes_received=envelope.body_bytes,
                detail=f"{spec.id}: {why}; cached document from "
                       f"{envelope.retrieved_at} is stale")
        return McpSourceRead(spec=spec, status="unavailable",
                             detail=f"{spec.id}: {why}")


def read_mcp_sources(specs: Sequence[SourceSpec], *,
                     fetcher: Fetcher | None = None,
                     cache_dir: Path | None = None) -> list[McpSourceRead]:
    """Read every ``mcp``-kind spec, in order; non-mcp specs are skipped."""
    reads: list[McpSourceRead] = []
    for spec in specs:
        if spec.kind != "mcp":
            continue
        reads.append(McpRegistrySource(spec=spec, fetcher=fetcher,
                                       cache_dir=cache_dir).read())
    return reads
