"""Read-only HTTP registry source (Cycle 4, Wave D).

An ``http`` source fetches a ``RegistryDocument`` over the network, caches it
under the user cache dir, and reports freshness honestly — a stale document is
never silently fresh (§21). The client is optional: the offline core never
touches it (nothing outside ``registry sources``/discovery reads sources),
``THEFORGE_NO_NETWORK=1`` disables it wholesale, and every source is opt-in.

Trust boundary: the response body is untrusted input — capped in size, decoded
tolerantly (forward-compat), validated as a contract, and cached together with
its sha256 so a poisoned cache file is detected rather than served (§18).
"""

import contextlib
import hashlib
import ipaddress
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from theforge import __version__
from theforge.contracts import ContractError, from_dict
from theforge.contracts.canonical import utc_now
from theforge.contracts.registry import RegistryDocument
from theforge.registry.config import user_cache_dir
from theforge.registry.sources import SourceRead, SourceSpec
from theforge.security.redact import redact_text

__all__ = [
    "A2ACardSource",
    "CACHE_KIND",
    "DEFAULT_MAX_AGE_S",
    "DEFAULT_TIMEOUT_S",
    "MAX_BODY_BYTES",
    "FetchResponse",
    "Fetcher",
    "HttpRegistrySource",
    "network_disabled",
]

CACHE_KIND = "theforge-registry-cache/v1"
DEFAULT_TIMEOUT_S = 10
DEFAULT_MAX_AGE_S = 3600
MAX_BODY_BYTES = 8 * 1024 * 1024

NO_NETWORK_ENV = "THEFORGE_NO_NETWORK"


def network_disabled() -> bool:
    """Hard kill-switch for air-gapped environments (§20): independent of the
    per-source ``enabled`` flag — when set, no remote read is attempted."""
    return os.environ.get(NO_NETWORK_ENV, "").lower() in ("1", "true", "yes")


@dataclass(frozen=True, kw_only=True)
class FetchResponse:
    """What a fetcher returns — transport-neutral so tests inject fakes."""

    status: int
    headers: Mapping[str, str]
    body: bytes


Fetcher = Callable[[str, Mapping[str, str], float], FetchResponse]


def _is_loopback_host(host: str | None) -> bool:
    if host is None:
        return False
    host = host.strip("[]").split("%", 1)[0].lower()
    if host in ("localhost", "localhost.localdomain"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _check_url(url: str, source_id: str) -> str | None:
    """Return an error detail if the url is unacceptable, else None.
    https only; plain http is allowed for loopback hosts (local mirrors,
    dev/test fixtures) — never for remote hosts."""
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return f"{source_id}: malformed url"
    if parsed.scheme == "https":
        return None
    if parsed.scheme == "http" and _is_loopback_host(parsed.hostname):
        return None
    return f"{source_id}: url must be https (http allowed only for loopback)"


def default_fetcher(url: str, headers: Mapping[str, str], timeout: float) -> FetchResponse:
    """urllib-based GET; validates the *final* URL after redirects."""
    if detail := _check_url(url, "fetch"):
        raise ValueError(detail)
    request = urllib.request.Request(url, headers=dict(headers), method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            final = resp.geturl()
            if detail := _check_url(final, "fetch"):
                raise ValueError(f"redirect to unsafe url: {detail}")
            body = resp.read(MAX_BODY_BYTES + 1)
            return FetchResponse(
                status=resp.status,
                headers={k.lower(): v for k, v in resp.headers.items()},
                body=body,
            )
    except urllib.error.HTTPError as exc:
        # urllib raises for every non-2xx — including 304 Not Modified.
        body = exc.read(MAX_BODY_BYTES + 1) if exc.fp else b""
        return FetchResponse(
            status=exc.code,
            headers={k.lower(): v for k, v in exc.headers.items()} if exc.headers else {},
            body=body,
        )


def _parse_time(text: str) -> datetime | None:
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
    except (ValueError, TypeError):
        return None


def _age_s(retrieved_at: str, now: str) -> float | None:
    then, current = _parse_time(retrieved_at), _parse_time(now)
    if then is None or current is None:
        return None
    return (current - then).total_seconds()


@dataclass(frozen=True, kw_only=True)
class CacheEnvelope:
    """A verified cache envelope — raw body only; each source type decodes
    it through its own ``_decode`` (registry documents and MCP pages share
    the same integrity/freshness discipline)."""

    retrieved_at: str
    etag: str | None
    body_sha256: str
    body: str

    @property
    def body_bytes(self) -> int:
        return len(self.body.encode("utf-8"))


@dataclass(frozen=True, kw_only=True)
class CachedDocument:
    """A cache envelope after integrity verification + document decode."""

    retrieved_at: str
    etag: str | None
    body_sha256: str
    body: str
    document: RegistryDocument

    @property
    def body_bytes(self) -> int:
        return len(self.body.encode("utf-8"))


def read_envelope(cache_path: Path, source_id: str, url: str | None) -> CacheEnvelope | None:
    """Verified envelope read: url match + sha256 of the stored body —
    a tampered cache file is simply absent. Document decode stays with the
    caller so every source kind re-checks the *raw* cached body."""
    try:
        if cache_path.stat().st_size > MAX_BODY_BYTES * 2:
            return None
        raw = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if (
        not isinstance(raw, dict)
        or raw.get("kind") != CACHE_KIND
        or raw.get("source_id") != source_id
        or raw.get("url") != url
    ):
        return None
    body = raw.get("body")
    body_sha = raw.get("body_sha256")
    retrieved_at = raw.get("retrieved_at")
    if (
        not isinstance(body, str)
        or not isinstance(body_sha, str)
        or not isinstance(retrieved_at, str)
    ):
        return None
    if hashlib.sha256(body.encode("utf-8")).hexdigest() != body_sha:
        return None  # poisoned cache: integrity failure → treat as absent
    etag = raw.get("etag")
    return CacheEnvelope(
        retrieved_at=retrieved_at,
        etag=etag if isinstance(etag, str) else None,
        body_sha256=body_sha,
        body=body,
    )


def write_envelope(
    cache_path: Path,
    *,
    source_id: str,
    url: str,
    retrieved_at: str,
    etag: str | None,
    body_sha: str,
    body: str,
) -> None:
    envelope = {
        "kind": CACHE_KIND,
        "source_id": source_id,
        "url": url,
        "retrieved_at": retrieved_at,
        "etag": etag,
        "body_sha256": body_sha,
        "body": body,
    }
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(envelope, indent=1, sort_keys=True), encoding="utf-8")
        tmp.replace(cache_path)
    except OSError:
        pass  # cache is an optimization; a failed write never fails the read


def touch_envelope(cache_path: Path, *, clock: Callable[[], str]) -> None:
    """304: refresh retrieved_at so the freshness budget restarts."""
    raw: dict[str, object] = {}
    try:
        raw = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if isinstance(raw, dict):
        raw["retrieved_at"] = clock()
        with contextlib.suppress(OSError):
            cache_path.write_text(json.dumps(raw, indent=1, sort_keys=True), encoding="utf-8")


class HttpRegistrySource:
    """``http`` source: conditional GET + verified local cache.

    Read order: fresh cache → conditional fetch (If-None-Match) → stale
    cache (explicitly marked) → unavailable. Nothing here mutates the
    installed-provider registry; the result is metadata only."""

    def __init__(
        self,
        spec: SourceSpec,
        *,
        fetcher: Fetcher | None = None,
        cache_dir: Path | None = None,
        clock: Callable[[], str] = utc_now,
    ):
        self.spec = spec
        self._fetcher = fetcher or default_fetcher
        self._cache_dir = cache_dir if cache_dir is not None else (user_cache_dir() / "registries")
        self._clock = clock

    @property
    def _cache_path(self) -> Path:
        return self._cache_dir / f"{self.spec.id}.json"

    def read(self) -> SourceRead:
        spec = self.spec
        if not spec.enabled:
            return SourceRead(spec=spec, status="disabled")
        assert spec.url is not None  # enforced by SourceSpec
        if detail := _check_url(spec.url, spec.id):
            return SourceRead(spec=spec, status="invalid", detail=detail)
        if network_disabled():
            cached = self._load_cache()
            if cached is not None:
                return self._cached_read(cached, note="network disabled")
            return SourceRead(
                spec=spec,
                status="unavailable",
                detail=f"{spec.id}: network disabled ({NO_NETWORK_ENV}) and no cache",
            )

        cached = self._load_cache()
        max_age = spec.max_age_s or DEFAULT_MAX_AGE_S
        now = self._clock()
        if cached is not None:
            age = _age_s(cached.retrieved_at, now)
            if age is not None and age <= max_age:
                return SourceRead(
                    spec=spec,
                    status="ok",
                    document=cached.document,
                    freshness="fresh",
                    from_cache=True,
                    retrieved_at=cached.retrieved_at,
                    etag=cached.etag,
                    body_sha256=cached.body_sha256,
                    bytes_received=cached.body_bytes,
                )

        started = time.monotonic()
        try:
            response = self._fetcher(
                spec.url,
                {
                    "Accept": "application/json",
                    "User-Agent": f"theforge/{__version__}",
                    **({"If-None-Match": cached.etag} if cached and cached.etag else {}),
                },
                float(spec.timeout_s or DEFAULT_TIMEOUT_S),
            )
        except Exception as exc:  # noqa: BLE001 — any transport failure is data
            return self._degraded(spec, cached, f"fetch failed: {type(exc).__name__}")
        latency_ms = (time.monotonic() - started) * 1000.0

        if response.status == 304 and cached is not None:
            self._touch_cache(cached)
            return SourceRead(
                spec=spec,
                status="ok",
                document=cached.document,
                freshness="fresh",
                from_cache=True,
                retrieved_at=now,
                etag=cached.etag,
                body_sha256=cached.body_sha256,
                bytes_received=cached.body_bytes,
                latency_ms=latency_ms,
            )
        if response.status != 200:
            return self._degraded(spec, cached, f"HTTP {response.status}")
        if len(response.body) > MAX_BODY_BYTES:
            return self._degraded(spec, cached, "response too large")

        try:
            text = response.body.decode("utf-8")
        except UnicodeDecodeError as exc:
            return SourceRead(
                spec=spec, status="invalid", detail=f"{spec.id}: {redact_text(str(exc))[:200]}"
            )
        document, error = self._decode(text)
        if error is not None or document is None:
            return SourceRead(
                spec=spec,
                status="invalid",
                detail=f"{spec.id}: {redact_text(error or 'empty document')[:200]}",
            )

        body_sha = hashlib.sha256(response.body).hexdigest()
        etag = next((v for k, v in response.headers.items() if k.lower() == "etag"), None)
        self._write_cache(retrieved_at=now, etag=etag, body_sha=body_sha, body=text)
        return SourceRead(
            spec=spec,
            status="ok",
            document=document,
            freshness="fresh",
            retrieved_at=now,
            etag=etag,
            body_sha256=body_sha,
            bytes_received=len(response.body),
            latency_ms=latency_ms,
        )

    def _decode(self, text: str) -> tuple[RegistryDocument | None, str | None]:
        """Decode a fetched/cached body into a document — the one seam the
        A2A card source overrides (the body stays the raw fetched bytes, so a
        cached card re-converts the same way)."""
        try:
            return from_dict(RegistryDocument, json.loads(text), "$"), None
        except (ValueError, ContractError) as exc:
            return None, str(exc)

    def _degraded(self, spec: SourceSpec, cached: CachedDocument | None, why: str) -> SourceRead:
        """Fetch failed: serve the cache *marked stale*, or report absence."""
        if cached is not None:
            return SourceRead(
                spec=spec,
                status="stale",
                document=cached.document,
                freshness="stale",
                from_cache=True,
                retrieved_at=cached.retrieved_at,
                etag=cached.etag,
                body_sha256=cached.body_sha256,
                bytes_received=cached.body_bytes,
                detail=f"{spec.id}: {why}; cached document from {cached.retrieved_at} is stale",
            )
        return SourceRead(spec=spec, status="unavailable", detail=f"{spec.id}: {why}")

    def _cached_read(self, cached: CachedDocument, *, note: str) -> SourceRead:
        spec = self.spec
        max_age = spec.max_age_s or DEFAULT_MAX_AGE_S
        age = _age_s(cached.retrieved_at, self._clock())
        fresh = age is not None and age <= max_age
        return SourceRead(
            spec=spec,
            status="ok" if fresh else "stale",
            document=cached.document,
            freshness="fresh" if fresh else "stale",
            from_cache=True,
            retrieved_at=cached.retrieved_at,
            etag=cached.etag,
            body_sha256=cached.body_sha256,
            bytes_received=cached.body_bytes,
            detail=None if fresh else f"{spec.id}: {note}; cached document is stale",
        )

    def _load_cache(self) -> CachedDocument | None:
        """Verified cache read: integrity envelope, then a fresh decode of
        the raw body — a tampered cache file is simply absent."""
        envelope = read_envelope(self._cache_path, self.spec.id, self.spec.url)
        if envelope is None:
            return None
        document, error = self._decode(envelope.body)
        if error is not None or document is None:
            return None
        return CachedDocument(
            retrieved_at=envelope.retrieved_at,
            etag=envelope.etag,
            body_sha256=envelope.body_sha256,
            body=envelope.body,
            document=document,
        )

    def _write_cache(
        self, *, retrieved_at: str, etag: str | None, body_sha: str, body: str
    ) -> None:
        assert self.spec.url is not None
        write_envelope(
            self._cache_path,
            source_id=self.spec.id,
            url=self.spec.url,
            retrieved_at=retrieved_at,
            etag=etag,
            body_sha=body_sha,
            body=body,
        )

    def _touch_cache(self, cached: CachedDocument) -> None:
        """304: refresh retrieved_at so the freshness budget restarts."""
        touch_envelope(self._cache_path, clock=self._clock)


class A2ACardSource(HttpRegistrySource):
    """``a2a`` source: fetch a remote A2A Agent Card and bridge it into a
    single-entry ``RegistryDocument`` (Cycle 4, Wave I).

    Same transport, cache, and freshness discipline as ``http`` sources; only
    the body decode differs. The card's claims enter as an unverified remote
    candidate — a remote agent is never a local provider, and the entry
    carries the endpoint and policy caveats in ``limitations``.
    """

    def _decode(self, text: str) -> tuple[RegistryDocument | None, str | None]:
        from theforge.interop.a2a import card_to_document, parse_agent_card

        card, error = parse_agent_card(text)
        if error is not None or card is None:
            return None, error or "empty agent card"
        document, warnings = card_to_document(
            card, source_id=self.spec.id, produced_at=self._clock()
        )
        if document is None:
            return None, "; ".join(warnings) or "unusable agent card"
        return document, None  # warnings ride inside document.limitations
