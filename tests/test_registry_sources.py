"""Cycle 4 Wave C — registry source abstraction.

Gate: local behavior unchanged — the installed-providers registry stays
authoritative. A *source* yields ``RegistryDocument`` metadata only: untrusted
input that can inform discovery, never trust, identity or routability (§15-18).
"""

import json
from pathlib import Path

import pytest

from theforge.cli.main import main
from theforge.contracts import ContractError, from_dict, to_dict
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
from theforge.errors import UsageError
from theforge.registry import ProviderEntry, RegistryRecord
from theforge.registry.sources import (
    FileRegistrySource,
    SourceSpec,
    load_source_specs,
    local_document,
    read_sources,
)


def entry(provider: str = "acme-forge", version: str = "1.2.3", **kw: object) -> ForgeRegistryEntry:
    return ForgeRegistryEntry(provider=provider, version=version, **kw)


def document(*entries: ForgeRegistryEntry, **kw: object) -> RegistryDocument:
    return RegistryDocument(
        registry=RegistryIdentity(id="test-registry", url="https://reg.example"),
        produced_at="2026-01-01T00:00:00Z",
        entries=list(entries),
        **kw,
    )


def write_doc(path: Path, data: object) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def file_spec(tmp_path: Path, **kw: object) -> SourceSpec:
    kw.setdefault("id", "mirror")
    kw.setdefault("enabled", True)
    return SourceSpec(kind="local-file", path=str(tmp_path / "registry.json"), **kw)


# ── contract validation ────────────────────────────────────────────────────


def test_entry_validates_provider_id() -> None:
    with pytest.raises(ContractError):
        entry(provider="Bad_Id")


def test_entry_validates_semver() -> None:
    with pytest.raises(ContractError):
        entry(version="latest")
    with pytest.raises(ContractError):
        entry(version="1.0")


def test_entry_validates_sha256_fields() -> None:
    with pytest.raises(ContractError):
        entry(manifest_sha256="abc")
    with pytest.raises(ContractError):
        entry(hashes={"wheel": "not-a-digest"})
    with pytest.raises(ContractError):
        DistributionRef(kind="pip-package", package="x", sha256="zzz")


def test_entry_validates_platform_format() -> None:
    entry(platforms=["win32", "linux-x86_64", "any"])
    with pytest.raises(ContractError):
        entry(platforms=["Windows 11"])


def test_entry_rejects_wrong_schema() -> None:
    with pytest.raises(ContractError):
        ForgeRegistryEntry(
            schema="theforge/ForgeRegistryEntry/v2", provider="acme-forge", version="1.0.0"
        )


def test_document_rejects_duplicate_provider_versions() -> None:
    # Same provider twice at the SAME version is a contradiction; different
    # versions of one provider are normal registry content.
    with pytest.raises(ContractError):
        document(entry(provider="dup-forge"), entry(provider="dup-forge"))
    document(
        entry(provider="dup-forge", version="1.0.0"), entry(provider="dup-forge", version="2.0.0")
    )
    document(entry(provider="a-forge"), entry(provider="b-forge"))


def test_identities_require_id() -> None:
    with pytest.raises(ContractError):
        PublisherIdentity(id="")
    with pytest.raises(ContractError):
        RegistryIdentity(id="")


def test_entry_round_trip_full() -> None:
    e = entry(
        publisher=PublisherIdentity(
            id="acme", organization="Acme", repository="https://github.com/acme/x", key_id="key-1"
        ),
        description="does things",
        manifest_url="https://reg.example/m.json",
        manifest_sha256="a" * 64,
        distribution=DistributionRef(
            kind="pip-package", package="acme-forge", version="1.2.3", sha256="b" * 64
        ),
        protocols=["forge/v1"],
        capabilities=["data.pipeline"],
        platforms=["any"],
        runtime=RuntimeRequirements(
            python=">=3.11", offline=True, requires_network=False, requires_credentials=False
        ),
        signatures=[SignatureRef(key_id="key-1", algorithm="ed25519", signature="sig")],
        source_repository="https://github.com/acme/x",
        license="Apache-2.0",
        security_contact="sec@acme.example",
        released_at="2026-01-01T00:00:00Z",
        limitations=["no windows support"],
    )
    decoded = from_dict(ForgeRegistryEntry, to_dict(e), "$")
    assert decoded == e


def test_document_tolerates_unknown_fields() -> None:
    """Forward compatibility: a newer registry may add fields; v1 ignores them."""
    data = to_dict(document(entry()))
    data["future_field"] = {"anything": 1}
    data["entries"][0]["future_entry_field"] = [1, 2, 3]
    decoded = from_dict(RegistryDocument, data, "$")
    assert decoded.entries[0].provider == "acme-forge"


# ── SourceSpec / load_source_specs ──────────────────────────────────────────


def test_spec_validation() -> None:
    with pytest.raises(ContractError):
        SourceSpec(id="bad id!", kind="local-file", path="x.json")
    with pytest.raises(ContractError):
        SourceSpec(id="f", kind="local-file")
    with pytest.raises(ContractError):
        SourceSpec(id="h", kind="http")
    with pytest.raises(ContractError):
        SourceSpec(id="f", kind="local-file", path="x", max_age_s=0)


def test_specs_default_disabled() -> None:
    spec = SourceSpec(id="f", kind="local-file", path="x.json")
    assert spec.enabled is False


def test_load_specs_user_and_project(tmp_path: Path) -> None:
    user_dir = tmp_path / "user"
    user_dir.mkdir()
    (user_dir / "registries.toml").write_text(
        '[[sources]]\nid = "shared"\nkind = "local-file"\npath = "a.json"\nenabled = true\n',
        encoding="utf-8",
    )
    forge = tmp_path / "proj" / ".forge" / "config"
    forge.mkdir(parents=True)
    (forge / "registries.toml").write_text(
        '[[sources]]\nid = "shared"\nkind = "local-file"\npath = "evil.json"\n'
        '[[sources]]\nid = "project-only"\nkind = "local-file"\n'
        'path = "b.json"\n',
        encoding="utf-8",
    )
    warnings: list[str] = []
    specs = load_source_specs(tmp_path / "proj" / ".forge", user_dir=user_dir, warnings=warnings)
    assert [s.id for s in specs] == ["project-only", "shared"]
    shared = next(s for s in specs if s.id == "shared")
    # The project file cannot override a user-defined source id.
    assert shared.enabled is True
    assert shared.path == str(user_dir / "a.json")
    assert any("shared" in w for w in warnings)


def test_load_specs_missing_files(tmp_path: Path) -> None:
    assert load_source_specs(tmp_path / "nope", user_dir=tmp_path / "nouser") == []


def test_load_specs_malformed(tmp_path: Path) -> None:
    user_dir = tmp_path / "u"
    user_dir.mkdir()
    (user_dir / "registries.toml").write_text("not = [toml", encoding="utf-8")
    with pytest.raises(UsageError):
        load_source_specs(None, user_dir=user_dir)
    (user_dir / "registries.toml").write_text('sources = "oops"', encoding="utf-8")
    with pytest.raises(UsageError):
        load_source_specs(None, user_dir=user_dir)


def test_load_specs_bad_entry(tmp_path: Path) -> None:
    user_dir = tmp_path / "u"
    user_dir.mkdir()
    (user_dir / "registries.toml").write_text(
        '[[sources]]\nid = "x"\nkind = "local-file"\n', encoding="utf-8"
    )
    with pytest.raises(UsageError, match="path"):
        load_source_specs(None, user_dir=user_dir)


# ── FileRegistrySource / read_sources ───────────────────────────────────────


def test_file_source_reads_document(tmp_path: Path) -> None:
    write_doc(tmp_path / "registry.json", to_dict(document(entry(capabilities=["data.pipeline"]))))
    read = FileRegistrySource(spec=file_spec(tmp_path)).read()
    assert read.status == "ok"
    assert read.document is not None
    assert read.document.registry.id == "test-registry"
    assert read.document.entries[0].capabilities == ["data.pipeline"]


def test_file_source_missing_file(tmp_path: Path) -> None:
    read = FileRegistrySource(spec=file_spec(tmp_path)).read()
    assert read.status == "unavailable"
    assert "mirror" in (read.detail or "")


def test_file_source_invalid_json(tmp_path: Path) -> None:
    (tmp_path / "registry.json").write_text("{nope", encoding="utf-8")
    read = FileRegistrySource(spec=file_spec(tmp_path)).read()
    assert read.status == "invalid"
    assert "JSON" in (read.detail or "")


def test_file_source_invalid_document(tmp_path: Path) -> None:
    bad = to_dict(document(entry()))
    bad["entries"][0]["provider"] = "NOT-VALID"
    write_doc(tmp_path / "registry.json", bad)
    read = FileRegistrySource(spec=file_spec(tmp_path)).read()
    assert read.status == "invalid"
    assert "provider" in (read.detail or "")


def test_read_sources_reports_disabled(tmp_path: Path) -> None:
    spec = file_spec(tmp_path, enabled=False)
    reads = read_sources([spec])
    assert reads[0].status == "disabled"
    assert reads[0].document is None


def test_read_sources_http_unavailable_offline(tmp_path: Path) -> None:
    """Enabled http source + no cache + blocked network → unavailable (not a
    crash): the core treats a dead source as data (§20)."""
    spec = SourceSpec(id="remote", kind="http", url="https://reg.example", enabled=True)
    reads = read_sources([spec], cache_dir=tmp_path / "cache")
    assert reads[0].status == "unavailable"


def test_read_sources_order(tmp_path: Path) -> None:
    write_doc(tmp_path / "registry.json", to_dict(document(entry())))
    specs = [
        file_spec(tmp_path, id="a", enabled=False),
        file_spec(tmp_path, id="b"),
        SourceSpec(id="c", kind="http", url="https://x", enabled=True),
    ]
    reads = read_sources(specs, cache_dir=tmp_path / "cache")
    assert [(r.spec.id, r.status) for r in reads] == [
        ("a", "disabled"),
        ("b", "ok"),
        ("c", "unavailable"),
    ]


# ── local_document: the installed registry as a source ──────────────────────


def make_record(
    pid: str, cap_ids: list[str], *, state: str = "ready", sha: str = "0" * 64, trust: str = "local"
) -> RegistryRecord:
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
        version="2.0.0",
        protocols=["forge/v1"],
        ops=["describe", "health"],
        capabilities=caps,
        execution=ExecutionInfo(offline=True, requires_network=False),
        limitations=["beta surface"],
    )
    return RegistryRecord(
        entry=ProviderEntry(id=pid, argv=["x"], trust=trust),
        state=state,
        manifest=manifest,
        manifest_sha256=sha,
        protocol="forge/v1",
    )


def test_local_document_projects_ready_records() -> None:
    doc = local_document(
        [make_record("one-forge", ["a.b", "c.d"]), make_record("two-forge", ["x.y"])]
    )
    assert doc.registry.id == "local"
    assert [e.provider for e in doc.entries] == ["one-forge", "two-forge"]
    e = doc.entries[0]
    assert e.version == "2.0.0"
    assert e.capabilities == ["a.b", "c.d"]
    assert e.runtime is not None and e.runtime.offline is True
    assert e.hashes == {"manifest_sha256": "0" * 64}
    assert e.limitations == ["beta surface"]
    assert e.publisher is not None and e.publisher.id == "local:one-forge"


def test_local_document_skips_non_ready() -> None:
    doc = local_document([make_record("bad-forge", ["a.b"], state="invalid")])
    assert doc.entries == []


def test_local_document_excludes_unsupported_capabilities() -> None:
    caps = [
        Capability(
            id="ok.cap",
            actions=["run"],
            default_action="run",
            state="supported",
            operation_class="read_only",
            signals=Signals(),
        ),
        Capability(
            id="gone.cap",
            actions=["run"],
            default_action="run",
            state="unsupported",
            operation_class="read_only",
            signals=Signals(),
        ),
    ]
    manifest = ForgeManifest(
        id="p-forge",
        version="1.0.0",
        protocols=["forge/v1"],
        ops=["describe", "health"],
        capabilities=caps,
    )
    rec = RegistryRecord(
        entry=ProviderEntry(id="p-forge", argv=["x"]),
        state="ready",
        manifest=manifest,
        manifest_sha256="0" * 64,
        protocol="forge/v1",
    )
    doc = local_document([rec])
    assert doc.entries[0].capabilities == ["ok.cap"]


# ── CLI surface ─────────────────────────────────────────────────────────────


def test_cli_registry_sources(
    tmp_path: Path, user_config_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_doc(user_config_dir / "feed.json", to_dict(document(entry())))
    (user_config_dir / "registries.toml").write_text(
        '[[sources]]\nid = "feed"\nkind = "local-file"\npath = "feed.json"\n'
        "enabled = true\n"
        '[[sources]]\nid = "off"\nkind = "http"\nurl = "https://x"\n',
        encoding="utf-8",
    )
    code = main(["registry", "sources", "--root", str(tmp_path), "--json"])
    out = capsys.readouterr().out
    assert code == 0
    data = json.loads(out)
    by_id = {s["id"]: s for s in data["sources"]}
    assert by_id["feed"]["status"] == "ok" and by_id["feed"]["entries"] == 1
    # Configured-but-disabled sources are reported, never silently read (§20).
    assert by_id["off"]["status"] == "disabled"


def test_cli_registry_sources_text(
    tmp_path: Path, user_config_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["registry", "sources", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert "local (authoritative)" in out


def test_source_tier_org() -> None:
    spec = SourceSpec(id="corp", kind="http", url="https://r.corp/idx.json", tier="org")
    assert spec.tier == "org"
    default = SourceSpec(id="pub", kind="http", url="https://r.pub/idx.json")
    assert default.tier == "public"
    with pytest.raises(ContractError):
        SourceSpec(id="x", kind="http", url="https://x/", tier="internal")
