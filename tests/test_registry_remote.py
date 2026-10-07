"""Cycle 4 Wave D — read-only remote registry client.

Gate: offline core still passes — the http source is opt-in per config,
killable via THEFORGE_NO_NETWORK, and every failure mode is a SourceRead
value (unavailable/stale/invalid), never an exception (§20-21).
"""

import json
from pathlib import Path

import pytest

from theforge.contracts import to_dict
from theforge.contracts.registry import (
    ForgeRegistryEntry,
    RegistryDocument,
    RegistryIdentity,
)
from theforge.registry.remote import (
    FetchResponse,
    HttpRegistrySource,
    _check_url,
)
from theforge.registry.sources import SourceSpec, read_sources


def entry(provider: str = "remote-forge", **kw: object) -> ForgeRegistryEntry:
    return ForgeRegistryEntry(provider=provider, version="1.0.0", **kw)


def doc_json(*entries: ForgeRegistryEntry) -> str:
    return json.dumps(
        to_dict(
            RegistryDocument(
                registry=RegistryIdentity(id="remote-reg", url="https://reg.example"),
                produced_at="2026-01-01T00:00:00Z",
                entries=list(entries),
            )
        )
    )


def spec(tmp_path: Path, **kw: object) -> SourceSpec:
    kw.setdefault("id", "remote")
    kw.setdefault("enabled", True)
    return SourceSpec(kind="http", url="https://reg.example/index.json", **kw)


def source(tmp_path: Path, fetcher, **kw: object) -> HttpRegistrySource:
    return HttpRegistrySource(spec(tmp_path, **kw), fetcher=fetcher, cache_dir=tmp_path / "cache")


def fake_fetch(
    payload: str = "",
    status: int = 200,
    headers: dict[str, str] | None = None,
    calls: list[tuple[str, dict[str, str]]] | None = None,
    fail: Exception | None = None,
):
    def fetch(url: str, req_headers, timeout: float) -> FetchResponse:
        if calls is not None:
            calls.append((url, dict(req_headers)))
        if fail is not None:
            raise fail
        return FetchResponse(status=status, headers=headers or {}, body=payload.encode("utf-8"))

    return fetch


# ── URL policy ──────────────────────────────────────────────────────────────


def test_url_policy() -> None:
    assert _check_url("https://reg.example/x.json", "s") is None
    assert _check_url("http://127.0.0.1:8080/x.json", "s") is None
    assert _check_url("http://localhost/x.json", "s") is None
    assert _check_url("http://reg.example/x.json", "s") is not None
    assert _check_url("ftp://reg.example/x", "s") is not None
    assert _check_url("file:///etc/passwd", "s") is not None


def test_insecure_url_is_invalid_not_crashed(tmp_path: Path) -> None:
    spec_ = SourceSpec(id="s", kind="http", url="http://evil.example/x", enabled=True)
    read = HttpRegistrySource(spec_, cache_dir=tmp_path / "c").read()
    assert read.status == "invalid"
    assert "https" in (read.detail or "")


# ── happy path + cache ──────────────────────────────────────────────────────


def test_fetch_ok_and_cache_roundtrip(tmp_path: Path) -> None:
    calls: list = []
    fetch = fake_fetch(doc_json(entry()), headers={"ETag": '"v1"'}, calls=calls)
    src = source(tmp_path, fetch)
    read = src.read()
    assert read.status == "ok" and read.freshness == "fresh"
    assert read.document is not None
    assert read.document.entries[0].provider == "remote-forge"
    assert read.etag == '"v1"' and read.body_sha256 and len(read.body_sha256) == 64
    assert not read.from_cache

    # Second read within the freshness budget: cache hit, no new fetch.
    read2 = src.read()
    assert read2.status == "ok" and read2.from_cache and read2.freshness == "fresh"
    assert len(calls) == 1


def test_conditional_get_and_304(tmp_path: Path) -> None:
    calls: list = []
    fetch = fake_fetch(doc_json(entry()), headers={"ETag": '"v1"'}, calls=calls)
    src = source(tmp_path, fetch, max_age_s=1)
    src.read()
    assert len(calls) == 1

    # Expire the budget by rewriting retrieved_at far in the past.
    cache = tmp_path / "cache" / "remote.json"
    env = json.loads(cache.read_text(encoding="utf-8"))
    env["retrieved_at"] = "2000-01-01T00:00:00.000000Z"
    cache.write_text(json.dumps(env), encoding="utf-8")

    fetch304 = fake_fetch(status=304, calls=calls)
    src2 = source(tmp_path, fetch304, max_age_s=3600)
    read = src2.read()
    assert read.status == "ok" and read.freshness == "fresh"
    assert calls[-1][1].get("If-None-Match") == '"v1"'  # conditional request sent


def test_stale_cache_on_fetch_failure(tmp_path: Path) -> None:
    src = source(tmp_path, fake_fetch(doc_json(entry())), max_age_s=1)
    src.read()
    cache = tmp_path / "cache" / "remote.json"
    env = json.loads(cache.read_text(encoding="utf-8"))
    env["retrieved_at"] = "2000-01-01T00:00:00.000000Z"
    cache.write_text(json.dumps(env), encoding="utf-8")

    down = source(tmp_path, fake_fetch(fail=TimeoutError("boom")), max_age_s=1)
    read = down.read()
    assert read.status == "stale" and read.freshness == "stale"
    assert read.document is not None  # stale data is still inspectable
    assert "TimeoutError" in (read.detail or "")


def test_unavailable_without_cache(tmp_path: Path) -> None:
    read = source(tmp_path, fake_fetch(fail=OSError("no route"))).read()
    assert read.status == "unavailable"
    assert read.document is None


def test_http_error_status_with_cache_is_stale(tmp_path: Path) -> None:
    src = source(tmp_path, fake_fetch(doc_json(entry())), max_age_s=1)
    src.read()
    env = json.loads((tmp_path / "cache" / "remote.json").read_text())
    env["retrieved_at"] = "2000-01-01T00:00:00.000000Z"
    (tmp_path / "cache" / "remote.json").write_text(json.dumps(env))
    read = source(tmp_path, fake_fetch(status=500), max_age_s=1).read()
    assert read.status == "stale" and "HTTP 500" in (read.detail or "")


def test_invalid_document_200(tmp_path: Path) -> None:
    bad = json.dumps(
        {
            "schema": "theforge/RegistryDocument/v1",
            "registry": {"id": "r"},
            "produced_at": "t",
            "entries": [{"provider": "BAD ID", "version": "1.0.0"}],
        }
    )
    read = source(tmp_path, fake_fetch(bad)).read()
    assert read.status == "invalid"


def test_oversized_response_rejected(tmp_path: Path) -> None:
    big = " " * (8 * 1024 * 1024 + 10)
    read = source(tmp_path, fake_fetch(big, status=200)).read()
    assert read.status == "unavailable"
    assert "too large" in (read.detail or "")


# ── cache integrity (poisoning is never silently served) ────────────────────


def test_poisoned_cache_ignored(tmp_path: Path) -> None:
    src = source(tmp_path, fake_fetch(doc_json(entry())))
    src.read()
    cache = tmp_path / "cache" / "remote.json"
    env = json.loads(cache.read_text(encoding="utf-8"))
    env["body"] = env["body"].replace("remote-forge", "evil-forge ")
    cache.write_text(json.dumps(env), encoding="utf-8")

    calls: list = []
    read = source(tmp_path, fake_fetch(doc_json(entry()), calls=calls)).read()
    assert read.status == "ok" and not read.from_cache
    assert calls  # tampered cache forced a real fetch
    assert read.document is not None
    assert read.document.entries[0].provider == "remote-forge"


def test_cache_url_mismatch_ignored(tmp_path: Path) -> None:
    src = source(tmp_path, fake_fetch(doc_json(entry())))
    src.read()
    env = json.loads((tmp_path / "cache" / "remote.json").read_text())
    env["url"] = "https://other.example/x.json"
    (tmp_path / "cache" / "remote.json").write_text(json.dumps(env))
    calls: list = []
    source(tmp_path, fake_fetch(doc_json(entry()), calls=calls)).read()
    assert calls  # url changed → cache not reused


# ── kill-switch ─────────────────────────────────────────────────────────────


def test_no_network_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("THEFORGE_NO_NETWORK", "1")
    calls: list = []
    read = source(tmp_path, fake_fetch(doc_json(entry()), calls=calls)).read()
    assert read.status == "unavailable"
    assert not calls  # no fetch attempted at all

    # With a fresh cache, the cached document is served while disabled.
    monkeypatch.delenv("THEFORGE_NO_NETWORK")
    source(tmp_path, fake_fetch(doc_json(entry()))).read()
    monkeypatch.setenv("THEFORGE_NO_NETWORK", "1")
    read = source(tmp_path, fake_fetch()).read()
    assert read.status == "ok" and read.from_cache


def test_read_sources_dispatches_http(tmp_path: Path) -> None:
    calls: list = []
    reads = read_sources(
        [spec(tmp_path)],
        fetcher=fake_fetch(doc_json(entry()), calls=calls),
        cache_dir=tmp_path / "cache",
    )
    assert reads[0].status == "ok"
    assert calls and calls[0][0] == "https://reg.example/index.json"


def test_timeout_forwarded(tmp_path: Path) -> None:
    seen: list[float] = []

    def fetch(url, headers, timeout):
        seen.append(timeout)
        return FetchResponse(status=200, headers={}, body=doc_json(entry()).encode())

    source(tmp_path, fetch, timeout_s=3).read()
    assert seen == [3.0]
