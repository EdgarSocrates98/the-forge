"""Cycle 4 Wave I — experimental A2A bridge conformance (§63-67).

The bridge translates documents only: Forge providers → A2A Agent Cards,
TaskSpecs → message/send params, results → artifacts/parts; and remote A2A
cards → ``ForgeRegistryEntry`` remote candidates. Nothing here executes a
remote agent; every card claim stays unverified metadata.
"""

import json
from pathlib import Path

import pytest

from theforge.contracts.canonical import utc_now
from theforge.contracts.manifest import Capability, ExecutionInfo, ForgeManifest, Signals
from theforge.contracts.negotiation import CapabilityRequirement
from theforge.contracts.result import (
    Artifact,
    Evidence,
    ExecutionResult,
    Finding,
    Producer,
)
from theforge.contracts.task import TaskSpec
from theforge.interop.a2a import (
    FORGE_METADATA_KEY,
    agent_card,
    artifacts_from_result,
    card_to_document,
    entry_from_card,
    parse_agent_card,
    task_to_send_params,
)
from theforge.registry import ProviderEntry, RegistryRecord
from theforge.registry.remote import A2ACardSource, FetchResponse
from theforge.registry.sources import SourceSpec, read_sources

# ── fixtures ────────────────────────────────────────────────────────────────


def capability(cid: str = "data.pipeline", **kw: object) -> Capability:
    kw.setdefault("actions", ["run", "dry-run"])
    kw.setdefault("default_action", "run")
    kw.setdefault("state", "supported")
    kw.setdefault("operation_class", "read_only")
    kw.setdefault("signals", Signals(keywords=["data"]))
    return Capability(id=cid, **kw)  # type: ignore[arg-type]


def record(pid: str = "forge-provider") -> RegistryRecord:
    manifest = ForgeManifest(
        id=pid,
        version="1.2.3",
        protocols=["forge/v1"],
        ops=["describe", "health", "execute"],
        capabilities=[capability()],
        execution=ExecutionInfo(local=True, offline=False, requires_network=True),
        limitations=["no windows support"],
    )
    return RegistryRecord(
        entry=ProviderEntry(id=pid, argv=["x"], trust="local"),
        state="ready",
        manifest=manifest,
        manifest_sha256="a" * 64,
        protocol="forge/v1",
    )


def task(**kw: object) -> TaskSpec:
    kw.setdefault("id", "t-1")
    kw.setdefault("intent", "pipeline the orders table")
    return TaskSpec(
        producer=Producer(id="theforge", version="1"),
        created_at=utc_now(),
        workspace_root="/ws",
        **kw,
    )  # type: ignore[arg-type]


def result() -> ExecutionResult:
    return ExecutionResult(
        producer=Producer(id="forge-provider", version="1.2.3"),
        created_at=utc_now(),
        status="ok",
        findings=[Finding(id="f1", title="found", severity="info")],
        evidence=[
            Evidence(
                id="e1",
                epistemic="observed",
                subject="s",
                claim="c",
                producer=Producer(id="p", version="1"),
                hash="b" * 64,
            )
        ],
        artifacts=[Artifact(path="out/report.json", sha256="c" * 64)],
        limitations=["partial coverage"],
    )


CARD = {
    "name": "Acme Agent",
    "description": "remote acme agent",
    "version": "2.0.1",
    "url": "https://agent.example/a2a",
    "protocolVersion": "1.0",
    "capabilities": {"streaming": True},
    "skills": [
        {
            "id": "data.transform",
            "name": "transform",
            "description": "transforms data",
            "tags": ["etl", "json"],
            "inputModes": ["text/plain", "application/json"],
            "outputModes": ["application/json"],
        }
    ],
    "securitySchemes": {"oauth": {"type": "oauth2"}},
}


# ── Forge -> A2A ────────────────────────────────────────────────────────────


def test_agent_card_maps_manifest() -> None:
    card = agent_card(record())
    assert card["name"] == "forge-provider"
    assert card["version"] == "1.2.3"
    assert card["protocolVersion"] == "1.0"
    assert card["capabilities"]["streaming"] is False
    assert card["url"] == ""  # subprocess provider — no remote endpoint
    (skill,) = card["skills"]
    assert skill["id"] == "data.pipeline"
    assert "forge-capability" in skill["tags"]
    forge = card["metadata"][FORGE_METADATA_KEY]
    assert forge["manifest_sha256"] == "a" * 64
    assert forge["execution"]["requires_network"] is True
    assert forge["limitations"] == ["no windows support"]
    # round-trip: the emitted card is valid JSON and re-parseable
    parsed, err = parse_agent_card(json.dumps(card))
    assert err is None and parsed == card


def test_agent_card_requires_ready_record() -> None:
    with pytest.raises(ValueError):
        agent_card(
            RegistryRecord(entry=ProviderEntry(id="x", argv=["y"]), state="error", manifest=None)
        )


def test_task_to_send_params_preserves_forge_semantics() -> None:
    t = task(
        requested_capability="data.pipeline",
        requested_action="run",
        requirement=CapabilityRequirement(capability="data.pipeline", offline_required=True),
        targets=["orders/"],
        constraints={"k": 1},
    )
    params = task_to_send_params(t)
    message = params["message"]
    assert message["role"] == "user" and message["messageId"] == "t-1"
    assert message["parts"] == [{"kind": "text", "text": t.intent}]
    forge = message["metadata"][FORGE_METADATA_KEY]
    assert forge["capability"] == "data.pipeline"
    assert forge["action"] == "run"
    assert forge["requirement"]["capability"] == "data.pipeline"
    assert forge["targets"] == ["orders/"]
    json.dumps(params)  # serializable


def test_artifacts_from_result() -> None:
    artifacts = artifacts_from_result(result())
    summary, file_art = artifacts
    data = summary["parts"][0]["data"]
    assert data["schema"] == "theforge/ExecutionResult/v1"
    assert data["evidence"][0]["hash"] == "b" * 64
    assert data["limitations"] == ["partial coverage"]
    assert file_art["parts"][0]["kind"] == "file"
    assert file_art["parts"][0]["file"]["uri"] == "out/report.json"
    assert file_art["metadata"][FORGE_METADATA_KEY]["sha256"] == "c" * 64


# ── A2A -> Forge ────────────────────────────────────────────────────────────


def test_entry_from_card_marks_remote_unverified() -> None:
    converted = entry_from_card(CARD, source_id="a2a-hub")
    entry = converted.entry
    assert entry is not None
    assert entry.provider == "acme-agent"
    assert entry.version == "2.0.1"
    assert entry.capabilities == ["data.transform"]
    assert entry.technologies == ["etl", "json"]
    assert entry.distribution is None  # an endpoint is not installable
    assert entry.runtime is not None
    assert entry.runtime.requires_network is True
    assert entry.runtime.offline is False
    assert entry.runtime.requires_credentials is True  # securitySchemes
    joined = " ".join(converted.limitations)
    assert "not a Forge provider" in joined
    assert "unverified self-declared" in joined
    assert "data egress" in joined
    assert "authentication" in joined
    assert "https://agent.example/a2a" in joined


def test_entry_from_card_slugifies_and_validates() -> None:
    bad = entry_from_card({"name": "!!!"}, source_id="s")
    assert bad.entry is None
    assert bad.warnings


def test_entry_from_card_non_semver_version() -> None:
    converted = entry_from_card({**CARD, "version": "latest"}, source_id="s")
    assert converted.entry is not None
    assert converted.entry.version == "0.0.0"
    assert any("not SemVer" in w for w in converted.warnings)


def test_unsupported_modality_is_limitation() -> None:
    card = {**CARD, "skills": [dict(CARD["skills"][0], inputModes=["image/png"])]}
    converted = entry_from_card(card, source_id="s")
    assert converted.entry is not None
    assert any(
        "unsupported modalities" in lim and "image/png" in lim for lim in converted.limitations
    )


def test_unknown_fields_and_extensions_tolerated() -> None:
    """Forward-compat: unknown card fields and Forge extension metadata
    must not break conversion (unknown-extension conformance case)."""
    card = {
        **CARD,
        "x-vendor-extension": {"nested": [1, 2]},
        "metadata": {"forge": {"surface_fingerprint": "x"}},
    }
    converted = entry_from_card(card, source_id="s")
    assert converted.entry is not None


def test_card_roundtrip_forge_to_a2a_to_entry() -> None:
    """A card emitted by the bridge converts back to the same provider id and
    capability set — no silent loss across the round-trip."""
    card = agent_card(record())
    converted = entry_from_card(card, source_id="s")
    entry = converted.entry
    assert entry is not None
    assert entry.provider == "forge-provider"
    assert entry.capabilities == ["data.pipeline"]
    # ...but re-imported, a Forge card is still only an unverified claim:
    assert entry.runtime is not None and entry.runtime.requires_network


def test_card_to_document_wraps_entry() -> None:
    doc, warnings = card_to_document(CARD, source_id="hub", produced_at="2026-01-01T00:00:00Z")
    assert doc is not None and warnings == []
    assert doc.registry.id == "hub"
    (entry,) = doc.entries
    assert entry.provider == "acme-agent"
    assert doc.limitations  # remote-candidate caveats travel with the doc


def test_parse_agent_card_malformed() -> None:
    card, err = parse_agent_card("{not json")
    assert card is None and err is not None
    card, err = parse_agent_card('["a"]')
    assert card is None and err is not None


# ── a2a source kind (transport + cache reuse) ────────────────────────────────


def a2a_spec(tmp_path: Path, **kw: object) -> SourceSpec:
    kw.setdefault("id", "agent-hub")
    kw.setdefault("enabled", True)
    kw.setdefault("url", "https://agent.example/.well-known/agent-card.json")
    return SourceSpec(kind="a2a", **kw)  # type: ignore[arg-type]


def good_fetch(body: bytes):
    def fetch(url: str, headers: object, timeout: float) -> FetchResponse:
        return FetchResponse(status=200, headers={}, body=body)

    return fetch


def test_a2a_source_converts_card(tmp_path: Path) -> None:
    spec = a2a_spec(tmp_path)
    source = A2ACardSource(
        spec=spec, fetcher=good_fetch(json.dumps(CARD).encode()), cache_dir=tmp_path
    )
    read = source.read()
    assert read.status == "ok" and read.document is not None
    (entry,) = read.document.entries
    assert entry.provider == "acme-agent"
    assert "a2a/1.0" in entry.protocols
    # cache round-trip: second read decodes the *cached card* the same way
    again = A2ACardSource(
        spec=spec, fetcher=good_fetch(b"should-not-be-served"), cache_dir=tmp_path
    ).read()
    assert again.status == "ok" and again.from_cache
    assert again.document is not None
    assert again.document.entries[0].provider == "acme-agent"


def test_a2a_source_via_read_sources(tmp_path: Path) -> None:
    reads = read_sources(
        [a2a_spec(tmp_path)], fetcher=good_fetch(json.dumps(CARD).encode()), cache_dir=tmp_path
    )
    assert reads[0].status == "ok"
    assert reads[0].document is not None


def test_a2a_source_remote_failure_and_timeout(tmp_path: Path) -> None:
    def boom(url, headers, timeout):
        raise TimeoutError("timed out")

    read = A2ACardSource(spec=a2a_spec(tmp_path), fetcher=boom, cache_dir=tmp_path).read()
    assert read.status == "unavailable"
    assert "TimeoutError" in (read.detail or "")


def test_a2a_source_malformed_body(tmp_path: Path) -> None:
    read = A2ACardSource(
        spec=a2a_spec(tmp_path), fetcher=good_fetch(b"<html>not a card</html>"), cache_dir=tmp_path
    ).read()
    assert read.status == "invalid"
    assert "not valid JSON" in (read.detail or "")


def test_a2a_source_card_without_name(tmp_path: Path) -> None:
    read = A2ACardSource(
        spec=a2a_spec(tmp_path),
        fetcher=good_fetch(json.dumps({"url": "x"}).encode()),
        cache_dir=tmp_path,
    ).read()
    assert read.status == "invalid"


def test_a2a_source_network_disabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("THEFORGE_NO_NETWORK", "1")
    read = A2ACardSource(
        spec=a2a_spec(tmp_path), fetcher=good_fetch(json.dumps(CARD).encode()), cache_dir=tmp_path
    ).read()
    assert read.status == "unavailable"
    assert "network disabled" in (read.detail or "")


def test_supported_interfaces_v1() -> None:
    """A2A 1.0 cards advertise ``supportedInterfaces``; preferred wins, ``url``
    remains the 0.3 fallback."""
    card = {
        **CARD,
        "url": "https://legacy.example/a2a",
        "supportedInterfaces": [
            {"url": "https://v1.example/a2a", "protocolBinding": "JSONRPC"},
            {"url": "https://grpc.example/a2a", "protocolBinding": "GRPC"},
        ],
    }
    converted = entry_from_card(card, source_id="s")
    assert converted.entry is not None
    joined = " ".join(converted.limitations)
    assert "https://v1.example/a2a" in joined  # first interface preferred
    assert "legacy.example" not in joined
    assert "JSONRPC" in joined


def test_emitted_card_declares_supported_interfaces() -> None:
    card = agent_card(record())
    assert card["supportedInterfaces"] == []  # local subprocess: no endpoint
    assert card["protocolVersion"] == "1.0"
