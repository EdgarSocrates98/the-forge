"""Cycle 4 Wave E — remote discovery by CapabilityRequirement.

Gate: no install occurs — discovery returns RemoteProviderCandidate metadata
and stops. Local negotiation first; remote sources only when nothing local
fully satisfies (or --remote). Remote fit tops out at declared/partial —
unverified claims can never be FULL (§22-26).
"""

import json
from pathlib import Path

import pytest

from theforge.cli.main import main
from theforge.contracts import CapabilityRequirement, to_dict
from theforge.contracts.manifest import Capability, ExecutionInfo, ForgeManifest, Signals
from theforge.contracts.registry import (
    DistributionRef,
    ForgeRegistryEntry,
    PublisherIdentity,
    RegistryDocument,
    RegistryIdentity,
    RuntimeRequirements,
    SignatureRef,
)
from theforge.registry import ProviderEntry, RegistryRecord
from theforge.registry.discovery import discover, evaluate_entry
from theforge.registry.remote import FetchResponse
from theforge.registry.sources import SourceSpec


def req(cap: str = "security.scan", **kw: object) -> CapabilityRequirement:
    return CapabilityRequirement(capability=cap, **kw)


def record(pid: str, cap_ids: list[str]) -> RegistryRecord:
    caps = [
        Capability(
            id=c,
            actions=["run"],
            default_action="run",
            state="supported",
            operation_class="read_only",
            signals=Signals(),
        )
        for c in cap_ids
    ]
    manifest = ForgeManifest(
        id=pid,
        version="1.0.0",
        protocols=["forge/v1"],
        ops=["describe", "health"],
        capabilities=caps,
        execution=ExecutionInfo(),
    )
    return RegistryRecord(
        entry=ProviderEntry(id=pid, argv=["x"]),
        state="ready",
        manifest=manifest,
        manifest_sha256="0" * 64,
        protocol="forge/v1",
    )


def entry(
    provider: str, version: str = "1.0.0", capabilities: list[str] | None = None, **kw
) -> ForgeRegistryEntry:
    kw.setdefault("protocols", ["forge/v1"])
    return ForgeRegistryEntry(
        provider=provider, version=version, capabilities=capabilities or ["security.scan"], **kw
    )


def file_source(
    tmp_path: Path, source_id: str, *entries: ForgeRegistryEntry, enabled: bool = True
) -> SourceSpec:
    doc = RegistryDocument(
        registry=RegistryIdentity(id=f"reg-{source_id}"),
        produced_at="2026-01-01T00:00:00Z",
        entries=list(entries),
    )
    path = tmp_path / f"{source_id}.json"
    path.write_text(json.dumps(to_dict(doc)), encoding="utf-8")
    return SourceSpec(id=source_id, kind="local-file", path=str(path), enabled=enabled)


# ── evaluate_entry ──────────────────────────────────────────────────────────


def test_entry_declares_capability() -> None:
    fit, matched, missing, unknowns, bad = evaluate_entry(req(), entry("x-forge"))
    assert bad is None and fit == "declared"
    assert matched == ["capability:security.scan"]
    assert missing == [] and unknowns == []


def test_entry_without_capability_not_candidate() -> None:
    fit, matched, missing, _, bad = evaluate_entry(
        req(), entry("x-forge", capabilities=["other.cap"])
    )
    assert fit == "unknown" and bad is None
    assert missing == ["capability:security.scan"]


def test_entry_runtime_contradictions_exclude() -> None:
    net = entry("net-forge", runtime=RuntimeRequirements(requires_network=True))
    _, _, _, _, bad = evaluate_entry(req(offline_required=True), net)
    assert bad is not None and "offline_required" in bad
    _, _, _, _, bad = evaluate_entry(req(network_allowed=False), net)
    assert bad is not None and "network_allowed" in bad
    cred = entry("cred-forge", runtime=RuntimeRequirements(requires_credentials=True))
    _, _, _, _, bad = evaluate_entry(req(credentials_allowed=False), cred)
    assert bad is not None and "credentials" in bad


def test_entry_platforms() -> None:
    _, matched, _, _, bad = evaluate_entry(
        req(platform_constraints=["linux"]), entry("x", platforms=["linux"])
    )
    assert bad is None and "platform" in matched
    _, _, _, _, bad = evaluate_entry(
        req(platform_constraints=["linux"]), entry("x", platforms=["win32"])
    )
    assert bad is not None
    _, _, _, unknowns, _ = evaluate_entry(
        req(platform_constraints=["linux"]), entry("x", platforms=[])
    )
    assert "platforms:undeclared" in unknowns


def test_entry_technologies() -> None:
    _, matched, missing, _, _ = evaluate_entry(
        req(technologies=["kafka", "spark"]), entry("x", technologies=["kafka"])
    )
    assert "technology:kafka" in matched
    assert "technology:spark" in missing


def test_entry_undeclared_dims_are_unknown_never_silent() -> None:
    _, _, _, unknowns, _ = evaluate_entry(
        req(
            required_actions=["scan"],
            required_evidence=["finding"],
            protocol_features=["handoff/v1"],
        ),
        entry("x"),
    )
    assert "required_actions:remote-undeclared" in unknowns
    assert "required_evidence:remote-undeclared" in unknowns
    assert "protocol_features:remote-undeclared" in unknowns


def test_entry_missing_forge_protocol_marked() -> None:
    _, _, missing, _, _ = evaluate_entry(req(), entry("x", protocols=["a2a/v1"]))
    assert "protocol:forge/v1" in missing


def test_entry_partial_when_unknowns() -> None:
    fit, _, _, _, _ = evaluate_entry(req(required_actions=["scan"]), entry("x"))
    assert fit == "partial"  # declared capability but unverifiable actions


# ── discover() ──────────────────────────────────────────────────────────────


def test_discover_local_full_skips_remote(tmp_path: Path) -> None:
    specs = [file_source(tmp_path, "feed", entry("remote-x"))]
    report = discover(req("data.pipeline"), [record("local-p", ["data.pipeline"])], specs=specs)
    assert report.satisfied_locally and report.local_state == "FULL"
    assert report.candidates == [] and report.sources_consulted == []


def test_discover_remote_when_missing(tmp_path: Path) -> None:
    specs = [
        file_source(
            tmp_path,
            "feed",
            entry("remote-x", "1.0.0"),
            entry("remote-x", "2.0.0"),
            entry("unrelated", capabilities=["other.cap"]),
        )
    ]
    report = discover(req(), [record("local-p", ["data.pipeline"])], specs=specs)
    assert not report.satisfied_locally
    assert report.sources_consulted == ["feed"] and report.entries_scanned == 3
    assert [c.provider for c in report.candidates] == ["remote-x", "remote-x"]
    # Newest version first within the same provider.
    assert report.candidates[0].version == "2.0.0"
    assert all(c.source == "feed" and c.registry == "reg-feed" for c in report.candidates)


def test_discover_declared_before_partial(tmp_path: Path) -> None:
    partial_req = req(required_actions=["scan"])
    specs = [file_source(tmp_path, "f", entry("a-forge"), entry("b-forge"))]
    report = discover(partial_req, [], specs=specs)
    # Both have the capability but unverifiable actions → all partial; order
    # falls back to provider id.
    assert [c.fit for c in report.candidates] == ["partial", "partial"]
    assert [c.provider for c in report.candidates] == ["a-forge", "b-forge"]


def test_discover_force_remote(tmp_path: Path) -> None:
    specs = [file_source(tmp_path, "feed", entry("remote-x", capabilities=["data.pipeline"]))]
    report = discover(
        req("data.pipeline"), [record("local-p", ["data.pipeline"])], specs=specs, force_remote=True
    )
    assert report.satisfied_locally and report.candidates


def test_discover_no_sources(tmp_path: Path) -> None:
    report = discover(req(), [], specs=[])
    assert "no registry sources configured" in report.limitations


def test_discover_disabled_source_skipped(tmp_path: Path) -> None:
    specs = [file_source(tmp_path, "off", entry("remote-x"), enabled=False)]
    report = discover(req(), [], specs=specs)
    assert report.sources_skipped == ["off"] and report.candidates == []


def test_discover_excludes_incompatible(tmp_path: Path) -> None:
    bad_entry_ = entry("net-forge", runtime=RuntimeRequirements(requires_network=True))
    specs = [file_source(tmp_path, "feed", bad_entry_, entry("good-forge"))]
    report = discover(req(offline_required=True), [], specs=specs)
    assert [c.provider for c in report.candidates] == ["good-forge"]
    assert any("net-forge" in e and "offline_required" in e for e in report.entries_excluded)


def test_candidate_carries_provenance(tmp_path: Path) -> None:
    e = entry(
        "full-forge",
        publisher=PublisherIdentity(id="acme"),
        distribution=DistributionRef(kind="pip-package", package="full-forge", version="1.0.0"),
        signatures=[SignatureRef(key_id="k", algorithm="ed25519", signature="s")],
        limitations=["l"],
    )
    report = discover(req(), [], specs=[file_source(tmp_path, "f", e)])
    c = report.candidates[0]
    assert c.signature_state == "declared"
    assert c.publisher is not None and c.publisher.id == "acme"
    assert c.distribution is not None and c.distribution.package == "full-forge"
    assert c.limitations == ["l"]
    assert c.freshness == "unknown"  # local-file has no freshness tracking


def test_discover_via_http_source(tmp_path: Path) -> None:
    doc = RegistryDocument(
        registry=RegistryIdentity(id="remote-reg"), produced_at="t", entries=[entry("remote-y")]
    )
    body = json.dumps(to_dict(doc)).encode()

    def fetch(url, headers, timeout):
        return FetchResponse(status=200, headers={}, body=body)

    specs = [SourceSpec(id="live", kind="http", url="https://reg.example/x", enabled=True)]
    report = discover(req(), [], specs=specs, fetcher=fetch, cache_dir=tmp_path / "cache")
    assert report.candidates[0].provider == "remote-y"
    assert report.candidates[0].freshness == "fresh"


# ── CLI ─────────────────────────────────────────────────────────────────────


def test_cli_discover_missing_capability(
    tmp_path: Path, user_config_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    doc = RegistryDocument(
        registry=RegistryIdentity(id="team-reg"),
        produced_at="t",
        entries=[entry("security-forge", "1.3.2")],
    )
    (user_config_dir / "feed.json").write_text(json.dumps(to_dict(doc)), encoding="utf-8")
    (user_config_dir / "registries.toml").write_text(
        '[[sources]]\nid = "feed"\nkind = "local-file"\npath = "feed.json"\nenabled = true\n',
        encoding="utf-8",
    )
    code = main(
        ["capabilities", "discover", "--capability", "security.scan", "--root", str(tmp_path)]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "no installed provider" in out
    assert "Remote candidates" in out and "security-forge 1.3.2" in out
    assert "No action was taken." in out


def test_cli_discover_json(
    tmp_path: Path, user_config_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        ["capabilities", "discover", "--capability", "x.y", "--root", str(tmp_path), "--json"]
    )
    data = json.loads(capsys.readouterr().out)
    assert code == 0
    assert data["satisfied_locally"] is False
    assert data["action_taken"] is False
    assert data["candidates"] == []


# ── discovery profiles + economy (wave G, §47-48) ────────────────────────────


def test_profile_economy_skips_remote_when_capability_exists(tmp_path: Path) -> None:
    specs = [file_source(tmp_path, "feed", entry("remote-x"))]
    # A local claimant still counts as "the capability exists" — economy pays
    # a remote read only when *nothing* local can serve the requirement.
    report = discover(
        req("data.pipeline"), [record("local-p", ["data.pipeline"])], specs=specs, profile="economy"
    )
    assert report.local_state == "FULL"
    assert report.registry_calls == 0 and report.sources_consulted == []
    assert any("economy profile" in lim for lim in report.limitations)


def test_profile_economy_consults_when_nothing_local(tmp_path: Path) -> None:
    specs = [file_source(tmp_path, "feed", entry("remote-x"))]
    report = discover(req(), [record("local-p", ["other.cap"])], specs=specs, profile="economy")
    assert report.local_state == "UNSUPPORTED"
    assert report.sources_consulted == ["feed"] and report.registry_calls == 1


def test_profile_max_consults_despite_local_full(tmp_path: Path) -> None:
    specs = [file_source(tmp_path, "feed", entry("remote-x", capabilities=["data.pipeline"]))]
    report = discover(
        req("data.pipeline"), [record("local-p", ["data.pipeline"])], specs=specs, profile="max"
    )
    assert report.satisfied_locally
    assert report.sources_consulted == ["feed"] and report.candidates


def test_profile_default_balanced_skips_when_satisfied(tmp_path: Path) -> None:
    specs = [file_source(tmp_path, "feed", entry("remote-x"))]
    report = discover(
        req("data.pipeline"), [record("local-p", ["data.pipeline"])], specs=specs
    )  # default profile
    assert report.satisfied_locally and report.registry_calls == 0


def test_discovery_economy_fields(tmp_path: Path) -> None:
    spec = file_source(tmp_path, "feed", entry("remote-x"))
    report = discover(req(), [], specs=[spec])
    assert report.registry_calls == 1
    assert report.metadata_bytes > 0
    assert report.network_ms is None  # local-file: no network latency
