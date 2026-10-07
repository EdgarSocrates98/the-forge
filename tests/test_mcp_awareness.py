"""Cycle 4 Wave J — MCP registry awareness (§68-72).

Boundary under test: MCP = tools/resources/prompts, a different object type
than Forge providers — ``mcp`` sources never yield provider candidates, the
Forge detects declared ``mcp_requires`` availability, and nothing installs
or configures a server.
"""

import json
from pathlib import Path

import pytest

from theforge.contracts import ContractError
from theforge.contracts.manifest import Capability, ExecutionInfo, ForgeManifest, Signals
from theforge.contracts.mcp import (
    McpRegistryDocument,
    McpServerEntry,
)
from theforge.contracts.negotiation import CapabilityRequirement
from theforge.interop.mcp import MAX_MCP_PAGE, parse_server_list
from theforge.registry import ProviderEntry, RegistryRecord
from theforge.registry.discovery import discover
from theforge.registry.mcp import McpRegistrySource, read_mcp_sources
from theforge.registry.remote import FetchResponse
from theforge.registry.sources import SourceSpec, read_sources

# ── fixtures ────────────────────────────────────────────────────────────────

SERVER_LIST = {
    "servers": [{
        "server": {
            "name": "io.github.acme/filesystem",
            "title": "Filesystem",
            "description": "file and directory tools",
            "version": "1.0.0",
            "remotes": [{"type": "streamable-http",
                         "url": "https://mcp.example/sse",
                         "headers": [{"name": "Authorization"}]}],
            "packages": [{"registryType": "npm",
                          "identifier": "@acme/fs-server",
                          "version": "1.0.0",
                          "environmentVariables": [
                              {"name": "API_KEY", "isSecret": True}]}],
        },
        "_meta": {"io.modelcontextprotocol.registry/official": {
            "status": "active", "isLatest": True}},
    }],
    "metadata": {"count": 1, "nextCursor": "cursor-2"},
}


def mcp_spec(**kw: object) -> SourceSpec:
    kw.setdefault("id", "mcp-hub")
    kw.setdefault("enabled", True)
    kw.setdefault("url", "https://registry.example/v0/servers")
    return SourceSpec(kind="mcp", **kw)  # type: ignore[arg-type]


def good_fetch(body: bytes):
    def fetch(url: str, headers: object, timeout: float) -> FetchResponse:
        return FetchResponse(status=200, headers={}, body=body)
    return fetch


def capability(cid: str = "data.pipeline", **kw: object) -> Capability:
    kw.setdefault("actions", ["run"])
    kw.setdefault("default_action", "run")
    kw.setdefault("state", "supported")
    kw.setdefault("operation_class", "read_only")
    kw.setdefault("signals", Signals(keywords=["data"]))
    return Capability(id=cid, **kw)  # type: ignore[arg-type]


def record(pid: str, caps: list[Capability]) -> RegistryRecord:
    manifest = ForgeManifest(id=pid, version="1", protocols=["forge/v1"],
                             ops=["describe", "health", "execute"],
                             capabilities=list(caps),
                             execution=ExecutionInfo())
    return RegistryRecord(entry=ProviderEntry(id=pid, argv=["x"],
                                              trust="local"),
                          state="ready", manifest=manifest,
                          manifest_sha256="0" * 64, protocol="forge/v1")


# ── contracts ───────────────────────────────────────────────────────────────

def test_server_entry_validates_name() -> None:
    with pytest.raises(ContractError):
        McpServerEntry(name="bad name!")
    assert McpServerEntry(name="io.github.acme/fs").name


def test_document_rejects_duplicate_names() -> None:
    with pytest.raises(ContractError, match="duplicate"):
        McpRegistryDocument(
            source_id="s", produced_at="t",
            entries=[McpServerEntry(name="a/b"), McpServerEntry(name="a/b")])


# ── decode ──────────────────────────────────────────────────────────────────

def test_parse_server_list_envelope() -> None:
    doc, err = parse_server_list(json.dumps(SERVER_LIST), source_id="m",
                                 produced_at="t")
    assert err is None and doc is not None
    (entry,) = doc.entries
    assert entry.name == "io.github.acme/filesystem"
    assert entry.requires_network is True
    assert entry.requires_credentials is True  # headers + secret env var
    assert entry.remotes[0].headers == ["Authorization"]
    assert entry.packages[0].registry_type == "npm"
    assert doc.next_cursor == "cursor-2"  # surfaced, never followed
    assert "publisher-declared" in entry.limitations[-1]


def test_parse_server_list_flat_shape() -> None:
    flat = {"servers": [{"name": "io.acme/tools", "description": "d"}]}
    doc, err = parse_server_list(json.dumps(flat), source_id="m",
                                 produced_at="t")
    assert err is None and doc is not None and len(doc.entries) == 1


def test_parse_server_list_malformed() -> None:
    doc, err = parse_server_list("{oops", source_id="m", produced_at="t")
    assert doc is None and err is not None
    doc, err = parse_server_list('{"nope": []}', source_id="m", produced_at="t")
    assert doc is None and "servers" in (err or "")


def test_parse_server_list_bounded_page() -> None:
    big = {"servers": [{"server": {"name": f"o/s{i}"}}
                       for i in range(MAX_MCP_PAGE + 5)]}
    doc, err = parse_server_list(json.dumps(big), source_id="m",
                                 produced_at="t")
    assert err is None and doc is not None
    assert len(doc.entries) == MAX_MCP_PAGE
    assert any("truncated" in lim for lim in doc.limitations)


def test_parse_server_list_skips_bad_entries() -> None:
    doc, err = parse_server_list(
        json.dumps({"servers": [{"server": {"name": ""}},
                                {"server": {"name": "ok/one"}}]}),
        source_id="m", produced_at="t")
    assert err is None and doc is not None
    assert [e.name for e in doc.entries] == ["ok/one"]
    assert any("usable 'name'" in lim for lim in doc.limitations)


# ── mcp source ──────────────────────────────────────────────────────────────

def test_mcp_source_reads_and_caches(tmp_path: Path) -> None:
    spec = mcp_spec()
    source = McpRegistrySource(spec=spec,
                               fetcher=good_fetch(json.dumps(SERVER_LIST).encode()),
                               cache_dir=tmp_path)
    read = source.read()
    assert read.status == "ok" and read.document is not None
    assert read.document.entries[0].name == "io.github.acme/filesystem"
    cached = McpRegistrySource(spec=spec, fetcher=good_fetch(b"junk"),
                             cache_dir=tmp_path).read()
    assert cached.status == "ok" and cached.from_cache
    assert cached.document is not None


def test_mcp_source_failures(tmp_path: Path) -> None:
    def boom(url, headers, timeout):
        raise TimeoutError("t/o")
    read = McpRegistrySource(spec=mcp_spec(), fetcher=boom,
                             cache_dir=tmp_path).read()
    assert read.status == "unavailable" and "TimeoutError" in (read.detail or "")
    read = McpRegistrySource(spec=mcp_spec(),
                             fetcher=good_fetch(b"not json"),
                             cache_dir=tmp_path / "other").read()
    assert read.status == "invalid"


def test_mcp_source_network_disabled(tmp_path: Path,
                                     monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("THEFORGE_NO_NETWORK", "1")
    read = McpRegistrySource(spec=mcp_spec(),
                             fetcher=good_fetch(json.dumps(SERVER_LIST).encode()),
                             cache_dir=tmp_path).read()
    assert read.status == "unavailable"


def test_read_sources_skips_mcp(tmp_path: Path) -> None:
    """Provider-registry readers never serve mcp specs — separate object."""
    reads = read_sources([mcp_spec()],
                         fetcher=good_fetch(json.dumps(SERVER_LIST).encode()))
    assert reads[0].status == "skipped"
    assert "not a provider registry" in (reads[0].detail or "")
    assert read_mcp_sources([mcp_spec()],
                            fetcher=good_fetch(
                                json.dumps(SERVER_LIST).encode()),
                            cache_dir=tmp_path)[0].status == "ok"


# ── discovery integration ───────────────────────────────────────────────────

def test_discover_mcp_tooling_never_a_provider(tmp_path: Path) -> None:
    requirement = CapabilityRequirement(capability="data.pipeline",
                                        technologies=["filesystem"])
    report = discover(requirement, [record("p1", [capability()])],
                      specs=[mcp_spec()],
                      fetcher=good_fetch(json.dumps(SERVER_LIST).encode()),
                      cache_dir=tmp_path)
    # local capability lacks a declared `technologies` offer → honest PARTIAL
    assert report.local_state == "PARTIAL"
    (note,) = report.mcp_tooling
    assert note.name == "io.github.acme/filesystem"
    assert note.matched_terms == ["filesystem"]
    assert note.requires_network and note.requires_credentials
    # tooling is never a provider candidate
    assert all(note.name not in c.provider for c in report.candidates)


def test_discover_mcp_dependency_detection(tmp_path: Path) -> None:
    cap = capability(mcp_requires=["io.github.acme/filesystem"])
    report = discover(
        CapabilityRequirement(capability="data.pipeline"),
        [record("p1", [cap])], specs=[mcp_spec()],
        fetcher=good_fetch(json.dumps(SERVER_LIST).encode()),
        cache_dir=tmp_path)
    (dep,) = report.mcp_dependencies
    assert dep.name == "io.github.acme/filesystem"
    assert dep.declared_by == "p1/data.pipeline"
    assert dep.availability == "listed"


def test_discover_mcp_dependency_unlisted(tmp_path: Path) -> None:
    cap = capability(mcp_requires=["io.unknown/missing"])
    report = discover(
        CapabilityRequirement(capability="data.pipeline"),
        [record("p1", [cap])], specs=[mcp_spec()],
        fetcher=good_fetch(json.dumps(SERVER_LIST).encode()),
        cache_dir=tmp_path)
    assert report.mcp_dependencies[0].availability == "unlisted"


def test_capability_rejects_bad_mcp_name() -> None:
    with pytest.raises(ContractError):
        capability(mcp_requires=["not a name!!"])
