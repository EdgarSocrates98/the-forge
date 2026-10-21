"""lf-0027: universal specialist discovery — states, sources, governed probes."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from theforge import discovery
from theforge.contracts.base import to_dict
from theforge.contracts.envelope import Response
from theforge.contracts.manifest import ForgeManifest
from theforge.contracts.types import Producer
from theforge.discovery import _DistMeta
from theforge.registry.config import ProviderEntry
from theforge.registry.registry import RegistryRecord
from theforge.security.redact import redact

# -- fakes -------------------------------------------------------------------


class _FakeRegistry:
    """Duck-typed ``Registry`` — no providers.toml or cache reads."""

    def __init__(self, entries=(), records=()):
        self._entries = list(entries)
        self._records = list(records)

    def entries(self):
        return list(self._entries)

    def records(self, *, persist=True):
        return list(self._records)

    def cached_records(self):
        return list(self._records)


class _FakeTransport:
    """Answers a governed ``health`` op like a real adapter would."""

    def __init__(self, argv):
        self.argv = argv

    def call(self, op, payload, *, timeout, cwd=None, check_protocol=True):
        return Response(
            request_id="r_fake",
            op=op,
            producer=Producer(id="probe-forge", version="1.0.0"),
            status="ok",
            payload={"status": "ok", "checks": []},
        )


class _FakeDist:
    """Minimal ``Distribution.locate_file`` for bundled-manifest tests."""

    def __init__(self, base: Path):
        self._base = base

    def locate_file(self, rel):
        return self._base / rel


CAPABILITY_DOC = {
    "schema": "theforge/SpecialistCapability/v1",
    "specialist": {"id": "sentinel-forge", "version": "1.2.3", "domain": "data"},
    "capabilities": [
        {"id": "data.detect-schema", "description": "infer schema", "risk": "read_only"}
    ],
    "health": {"supported": True},
    "handoff": {"supported": True},
}


def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "forge-home"
    monkeypatch.setenv("FORGE_HOME_OVERRIDE", str(home))
    return home


def _write_install(home: Path, forge_id: str, doc: dict) -> Path:
    install_dir = home / ".forge" / "installations"  # FORGE_HOME/installations
    install_dir.mkdir(parents=True, exist_ok=True)
    path = install_dir / f"{forge_id}.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def _write_json(path: Path, doc: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def _scan(**kwargs):
    """Hermetic scan: no real registry, no real dists, no real entry points."""
    kwargs.setdefault("registry", _FakeRegistry())
    kwargs.setdefault("dist_loader", lambda _name: None)
    kwargs.setdefault("entry_point_scan", lambda: [])
    kwargs.setdefault("use_cache", False)
    return discovery.discover_specialists(**kwargs)


# -- catalog floor -----------------------------------------------------------


def test_absent_specialist_is_not_installed(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    report = _scan()
    entry = report.entry("api-forge")  # known via bundled forge-knowledge
    assert entry is not None
    assert entry.state == "NOT_INSTALLED"
    assert entry.sources == []


def test_discovered_is_not_verified_without_probe(tmp_path, monkeypatch):
    """Metadata-only scans top out at DISCOVERED — presence != executable."""
    _home(tmp_path, monkeypatch)
    root = tmp_path / "sentinel checkout"
    _write_json(root / "forge.json", {"forge_id": "sentinel-forge", "cli": "sentinel"})
    _write_json(root / "forge.capabilities.json", CAPABILITY_DOC)
    report = _scan(configured_paths=[root], probe=False)
    entry = report.entry("sentinel-forge")
    assert entry is not None
    assert entry.state == "DISCOVERED"  # manifest parses, but nothing ran
    assert entry.checks["manifest"] == "PASS"
    assert entry.checks["handshake"] == "SKIP"
    assert entry.capability_manifest is not None


def test_installed_and_probed_is_verified(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    root = tmp_path / "sentinel checkout"
    _write_json(root / "forge.json", {"forge_id": "sentinel-forge", "cli": "sentinel"})
    _write_json(root / "forge.capabilities.json", CAPABILITY_DOC)
    _write_install(
        home,
        "sentinel-forge",
        {
            "forge_id": "sentinel-forge",
            "version": "1.2.3",
            "install_root": str(tmp_path),
            "cli": {
                "name": "sentinel",
                "version_cmd": [sys.executable, "-c", "print('sentinel-forge 1.2.3')"],
            },
        },
    )
    report = _scan(configured_paths=[root], probe=True)
    entry = report.entry("sentinel-forge")
    assert entry is not None
    assert entry.state == "VERIFIED"
    assert entry.checks == {"handshake": "PASS", "manifest": "PASS", "health": "PASS"}
    assert entry.version == "1.2.3"


# -- declared-surface failures ------------------------------------------------


def test_bad_capability_manifest_is_untrusted(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    root = tmp_path / "rogue checkout"
    _write_json(root / "forge.json", {"forge_id": "rogue-forge"})
    _write_json(root / "forge.capabilities.json", {"schema": "wrong/Schema/v1"})
    report = _scan(configured_paths=[root], probe=False)
    entry = report.entry("rogue-forge")
    assert entry is not None
    assert entry.state == "UNTRUSTED"
    assert entry.checks["manifest"] == "FAIL"


def test_unreadable_manifest_is_untrusted(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    root = tmp_path / "broken checkout"
    _write_json(root / "forge.json", {"forge_id": "broken-forge"})
    (root / "forge.capabilities.json").write_text("{not json", encoding="utf-8")
    report = _scan(configured_paths=[root], probe=False)
    assert report.entry("broken-forge").state == "UNTRUSTED"


def test_incompatible_requires_python(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    root = tmp_path / "future checkout"
    _write_json(root / "forge.json", {"forge_id": "future-forge", "distribution": "future-dist"})

    def dist_loader(name):
        if name == "future-dist":
            return _DistMeta(
                name="future-dist",
                version="9.9.9",
                requires_python=">=99.0",
                files=[],
                entry_points=[],
            )
        return None

    report = _scan(configured_paths=[root], dist_loader=dist_loader)
    entry = report.entry("future-forge")
    assert entry is not None
    assert entry.state == "INCOMPATIBLE"
    assert any("requires-python" in lim for lim in entry.limitations)


def test_degraded_when_install_root_and_cli_dead(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _write_install(
        home,
        "ghost-forge",
        {
            "forge_id": "ghost-forge",
            "version": "0.1.0",
            "install_root": str(tmp_path / "was deleted"),
            "cli": {
                "name": "ghost",
                "version_cmd": [sys.executable, "-c", "import sys; sys.exit(3)"],
            },
        },
    )
    report = _scan(probe=True)
    entry = report.entry("ghost-forge")
    assert entry is not None
    assert entry.state == "DEGRADED"
    assert entry.checks["handshake"] == "FAIL"


# -- registry path -------------------------------------------------------------


def _manifest(forge_id: str, version: str = "1.0.0") -> ForgeManifest:
    return ForgeManifest(
        id=forge_id,
        version=version,
        protocols=["forge/v1"],
        ops=["describe", "health"],
    )


def test_registry_record_verified_through_governed_transport(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    entry = ProviderEntry(
        id="probe-forge", argv=["fake", "argv"], trust="trusted", source="user"
    )
    record = RegistryRecord(entry=entry, state="ready", manifest=_manifest("probe-forge"))
    report = _scan(
        registry=_FakeRegistry([entry], [record]),
        transport_factory=_FakeTransport,
        probe=True,
    )
    found = report.entry("probe-forge")
    assert found is not None
    assert found.state == "VERIFIED"
    assert found.checks["health"] == "PASS"
    assert found.version == "1.0.0"


def test_registry_ready_without_probe_stays_discovered(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    entry = ProviderEntry(
        id="probe-forge", argv=["fake", "argv"], trust="trusted", source="user"
    )
    record = RegistryRecord(entry=entry, state="ready", manifest=_manifest("probe-forge"))
    report = _scan(registry=_FakeRegistry([entry], [record]), probe=False)
    found = report.entry("probe-forge")
    assert found is not None
    assert found.state == "DISCOVERED"
    assert found.checks["handshake"] == "PASS"
    assert any("metadata only" in lim for lim in found.limitations)


def test_unreachable_registry_record_is_unavailable(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    entry = ProviderEntry(
        id="ghost-forge", argv=["fake"], trust="trusted", source="user"
    )
    record = RegistryRecord(entry=entry, state="unreachable", error="spawn failed")
    report = _scan(registry=_FakeRegistry([entry], [record]))
    assert report.entry("ghost-forge").state == "UNAVAILABLE"


def test_unverified_registry_entry_is_untrusted(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    entry = ProviderEntry(
        id="rogue-forge", argv=["rogue", "--serve"], trust="unverified", source="project"
    )
    report = _scan(registry=_FakeRegistry([entry], []))
    found = report.entry("rogue-forge")
    assert found is not None
    assert found.state == "UNTRUSTED"


# -- sources -------------------------------------------------------------------


def test_workspace_checkout_with_git(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    workspace = tmp_path / "workspace"
    member = workspace / "spark-forge-aws"
    (member / ".git").mkdir(parents=True)
    _write_json(member / "forge.json", {"forge_id": "spark-forge-aws"})
    report = _scan(workspace_root=workspace)
    entry = report.entry("spark-forge-aws")
    assert entry is not None
    assert entry.state == "DISCOVERED"
    assert any(e.source == "checkout" for e in entry.sources)


def test_configured_path_with_spaces_needs_no_git(tmp_path, monkeypatch):
    """Explicit paths discover specialists where no .git exists at all."""
    _home(tmp_path, monkeypatch)
    root = tmp_path / "dir with spaces" / "data sentinel"
    root.mkdir(parents=True)
    assert not (root / ".git").exists()
    _write_json(root / "forge.json", {"forge_id": "data-sentinel"})
    report = _scan(configured_paths=[root])
    entry = report.entry("data-sentinel")
    assert entry is not None
    assert entry.state == "DISCOVERED"
    assert any(
        e.source == "configured-path" and "dir with spaces" in (e.path or "")
        for e in entry.sources
    )


def test_discovery_toml_declares_paths(tmp_path, monkeypatch, user_config_dir):
    _home(tmp_path, monkeypatch)
    root = tmp_path / "external forges" / "sentinel-forge"
    root.mkdir(parents=True)
    _write_json(root / "forge.json", {"forge_id": "sentinel-forge"})
    toml_path = str(root).replace("\\", "\\\\")  # TOML basic-string escaping
    (user_config_dir / "discovery.toml").write_text(
        f'paths = ["{toml_path}"]\n', encoding="utf-8"
    )
    paths = discovery.configured_specialist_paths(config_dir=user_config_dir)
    assert (None, root) in paths
    report = _scan(config_dir=user_config_dir)
    assert report.entry("sentinel-forge").state == "DISCOVERED"


def test_entry_point_group_discovers_unknown_specialist(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    report = _scan(
        entry_point_scan=lambda: [
            ("theforge.specialists", "weird-forge", "weird_forge.spec:main")
        ]
    )
    entry = report.entry("weird-forge")
    assert entry is not None
    assert entry.state == "DISCOVERED"
    assert any(e.source == "entry-point" for e in entry.sources)


def test_forge_cli_receipt_counts_as_evidence(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    cli_state = home / ".forge-cli" / "forges" / "state.json"
    _write_json(
        cli_state,
        {
            "forges": {
                "cli-forge": {
                    "name": "cli-forge",
                    "version": "2.0.0",
                    "shim": str(tmp_path / "bin" / "cli-forge"),
                }
            }
        },
    )
    report = _scan()
    entry = report.entry("cli-forge")
    assert entry is not None
    assert entry.state == "DISCOVERED"
    assert any(e.source == "forge-cli" for e in entry.sources)


def test_bundled_manifest_inside_distribution(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    dist_root = tmp_path / "dist files"
    _write_json(dist_root / "forge.capabilities.json", CAPABILITY_DOC)
    _write_install(
        home,
        "sentinel-forge",
        {
            "forge_id": "sentinel-forge",
            "version": "1.2.3",
            "install_root": str(tmp_path),
            "cli": {
                "name": "sentinel",
                "version_cmd": [sys.executable, "-c", "print('1.2.3')"],
            },
        },
    )

    def dist_loader(name):
        if name == "sentinel":
            return _DistMeta(
                name="sentinel-forge-dist",
                version="1.2.3",
                requires_python=">=3.11",
                files=["forge.capabilities.json"],
                entry_points=[("console_scripts", "sentinel", "sentinel.cli:main")],
                _dist=_FakeDist(dist_root),
            )
        return None

    report = _scan(dist_loader=dist_loader, probe=True)
    entry = report.entry("sentinel-forge")
    assert entry is not None
    assert entry.state == "VERIFIED"
    assert entry.capability_manifest is not None
    assert any(e.source == "package" for e in entry.sources)


def test_mcp_registration_in_install_manifest(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _write_install(
        home,
        "mcp-forge",
        {
            "forge_id": "mcp-forge",
            "install_root": str(tmp_path),
            "mcp": {"command": "mcp-forge", "args": ["mcp"]},
        },
    )
    report = _scan()
    entry = report.entry("mcp-forge")
    assert entry is not None
    assert any(e.source == "mcp" for e in entry.sources)


# -- bounds, cache, honesty -----------------------------------------------------


def test_scan_budget_truncation_is_reported(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    report = _scan(scan_budget_s=0.0)
    assert report.truncated
    assert any("budget" in lim for lim in report.limitations)


def test_report_is_json_serializable_and_redaction_clean(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    root = tmp_path / "checkout"
    _write_json(root / "forge.json", {"forge_id": "data-sentinel"})
    report = _scan(configured_paths=[root])
    document = to_dict(report)
    json.dumps(document)  # must not raise
    assert redact(document) == document


def test_cache_serves_same_context_and_redacts_nothing(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    root = tmp_path / "checkout"
    _write_json(root / "forge.json", {"forge_id": "data-sentinel"})
    cache_dir = tmp_path / "cache"
    first = _scan(configured_paths=[root], use_cache=True, cache_dir=cache_dir)
    assert first.entry("data-sentinel").state == "DISCOVERED"
    cached = list(cache_dir.glob("discovery/report-*.json"))
    assert cached, "cache report was not written"
    # Mutate the source, keep the context — the cached report still answers.
    _write_json(root / "forge.capabilities.json", CAPABILITY_DOC | {
        "specialist": {"id": "data-sentinel", "version": "9.9.9", "domain": "x"}
    })
    second = _scan(configured_paths=[root], use_cache=True, cache_dir=cache_dir)
    assert second.entry("data-sentinel").capability_manifest is None
    third = _scan(configured_paths=[root], use_cache=False, cache_dir=cache_dir)
    assert third.entry("data-sentinel").capability_manifest is not None


def test_discover_specialist_single(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    assert (
        discovery.discover_specialist(
            "api-forge",
            registry=_FakeRegistry(),
            dist_loader=lambda _n: None,
            entry_point_scan=lambda: [],
            use_cache=False,
        ).state
        == "NOT_INSTALLED"
    )
    assert (
        discovery.discover_specialist(
            "not-a-real-forge",
            registry=_FakeRegistry(),
            dist_loader=lambda _n: None,
            entry_point_scan=lambda: [],
            use_cache=False,
        )
        is None
    )
