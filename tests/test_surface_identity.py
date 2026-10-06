"""Cycle 3.1 Wave B: ProviderSurfaceIdentity, surface fingerprints, feature
negotiation and surface-scoped performance history.

``version`` is not identity: fingerprints make a changed surface visible even
when ``manifest.version`` does not move, and scope history/cache to it.
"""

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from helpers import SPARK_ENTRY, make_workspace, write_file
from theforge.contracts import (
    CapabilityRelations,
    ContractError,
    ExecutionReceipt,
    ForgeManifest,
    ProviderCapabilityPerformance,
    ProviderPerformance,
    Signals,
    from_dict,
    to_dict,
)
from theforge.contracts.features import (
    HANDOFF,
    PLAN_PROPOSAL,
    RESOLVE,
    VERIFY,
    implied_features,
    supported_features,
    supports,
)
from theforge.contracts.identity import (
    SURFACE_IDENTITY_SCHEMA,
    ProviderSurfaceIdentity,
)
from theforge.errors import ReplayRefused
from theforge.explain import build_explain_report
from theforge.forger import AskRequest, Forger
from theforge.forger.replay import replay
from theforge.meta import PRODUCER
from theforge.metrics import load_performance, record_performance
from theforge.protocol import SubprocessTransport
from theforge.registry import (
    Registry,
    capability_fingerprint,
    surface_fingerprint,
    surface_identity,
    user_cache_dir,
)
from theforge.registry.health import check_health
from theforge.registry.registry import RegistryRecord
from theforge.runs import RunStore

SHA = "a" * 64


def _manifest(**over: Any) -> ForgeManifest:
    base: dict[str, Any] = {
        "id": "fixture-spark", "version": "0.0.1", "protocols": ["forge/v1"],
        "ops": ["describe", "health", "execute"], "domains": ["data-engineering"],
        "capabilities": [{
            "id": "spark.performance",
            "actions": ["diagnose", "review", "optimize"],
            "default_action": "diagnose", "state": "supported",
            "operation_class": "read_only",
            "description": "Diagnose slow Spark and Glue jobs",
            "signals": {"keywords": ["spark", "glue"], "file_globs": ["*.py"],
                        "dependencies": ["pyspark"]},
        }],
    }
    base.update(over)
    # allow Capability objects in overrides — serialize them back to dicts
    base["capabilities"] = [
        to_dict(c) if not isinstance(c, dict) else c
        for c in base["capabilities"]]
    return from_dict(ForgeManifest, base, "$")


def _capability(manifest: ForgeManifest) -> Any:
    return manifest.capabilities[0]


# --- ProviderSurfaceIdentity contract ------------------------------------------------------


def test_identity_roundtrips_strict() -> None:
    identity = surface_identity(_manifest(), protocol="forge/v1", recorded_at="t")
    assert identity.schema == SURFACE_IDENTITY_SCHEMA
    assert identity.provider_id == "fixture-spark"
    assert identity.provider_version == "0.0.1"
    assert identity.protocol_version == "forge/v1"
    assert identity.recorded_at == "t"
    assert from_dict(ProviderSurfaceIdentity, to_dict(identity),
                     strict=True) == identity


def test_identity_rejects_malformed_fingerprints() -> None:
    for field_name in ("surface_fingerprint", "capability_fingerprint"):
        kwargs: dict[str, Any] = {"provider_id": "p", "provider_version": "1",
                                  "surface_fingerprint": SHA,
                                  "capability_fingerprint": SHA}
        kwargs[field_name] = "not-a-sha"
        with pytest.raises(ContractError, match=field_name):
            ProviderSurfaceIdentity(**kwargs)


def test_identity_rejects_bad_native_fingerprint_and_empty_ids() -> None:
    with pytest.raises(ContractError, match="native_surface_fingerprint"):
        ProviderSurfaceIdentity(provider_id="p", provider_version="1",
                                surface_fingerprint=SHA, capability_fingerprint=SHA,
                                native_surface_fingerprint="zz")
    with pytest.raises(ContractError, match="provider_id"):
        ProviderSurfaceIdentity(provider_id="", provider_version="1",
                                surface_fingerprint=SHA, capability_fingerprint=SHA)


# --- fingerprint determinism ---------------------------------------------------------------


def test_fingerprints_are_deterministic_and_order_independent() -> None:
    manifest = _manifest()
    shuffled = _manifest(capabilities=[{
        "id": "spark.performance", "default_action": "diagnose",
        "actions": ["optimize", "review", "diagnose"],  # same set, other order
        "state": "supported", "operation_class": "read_only",
        "description": "Diagnose slow Spark and Glue jobs",
        "signals": {"keywords": ["spark", "glue"], "file_globs": ["*.py"],
                    "dependencies": ["pyspark"]},
    }], ops=["execute", "health", "describe"], protocols=["forge/v1"])
    assert surface_fingerprint(manifest) == surface_fingerprint(shuffled)
    assert capability_fingerprint(manifest) == capability_fingerprint(shuffled)


def test_capability_fingerprint_changes_on_operational_fields() -> None:
    base = _manifest()
    cap = _capability(base)
    variants = [
        replace(cap, actions=["diagnose"]),
        replace(cap, default_action="review"),
        replace(cap, state="heuristic"),
        replace(cap, operation_class="local_mutation"),
        replace(cap, accepts_handoff=True),
        replace(cap, relations=CapabilityRelations(produces=["report.md"])),
    ]
    seen = {capability_fingerprint(base)}
    for variant in variants:
        fingerprint = capability_fingerprint(replace(base, capabilities=[variant]))
        assert fingerprint not in seen
        seen.add(fingerprint)


def test_surface_fingerprint_changes_on_surface_fields() -> None:
    base = _manifest()
    changed = [
        replace(base, ops=["describe", "health", "execute", "verify"]),
        replace(base, features=["handoff/v1"]),
        replace(base, domains=["api"]),
        replace(base, protocols=["forge/v1", "forge/v2"]),
        replace(base, context_revalidation="hash"),
    ]
    seen = {surface_fingerprint(base)}
    for manifest in changed:
        fingerprint = surface_fingerprint(manifest)
        assert fingerprint not in seen
        seen.add(fingerprint)
    # ops/protocols/domains/features are surface-level: the capability digest stays
    for manifest in changed:
        assert capability_fingerprint(manifest) == capability_fingerprint(base)


def test_fingerprints_ignore_non_operational_fields() -> None:
    base = _manifest()
    cap = _capability(base)
    same = [
        replace(base, version="9.9.9"),
        replace(base, id="other-provider"),
        replace(base, capabilities=[replace(cap, description="totally different")]),
        replace(base, capabilities=[replace(
            cap, signals=Signals(keywords=["x"], file_globs=["*.y"],
                                 dependencies=["z"]))]),
        replace(base, limitations=["l"], unknowns=["u"]),
        replace(base, adapter_version="7.7.7"),
        replace(base, native_surface_fingerprint="b" * 64),
    ]
    for manifest in same:
        assert surface_fingerprint(manifest) == surface_fingerprint(base)
        assert capability_fingerprint(manifest) == capability_fingerprint(base)


# --- feature negotiation --------------------------------------------------------------------


def test_features_validate_and_dedupe() -> None:
    with pytest.raises(ContractError, match="malformed feature"):
        _manifest(features=["handoff"])           # missing /vN
    with pytest.raises(ContractError, match="malformed feature"):
        _manifest(features=["Handoff/v1"])        # uppercase name
    with pytest.raises(ContractError, match="duplicate features"):
        _manifest(features=["handoff/v1", "handoff/v1"])
    assert _manifest(features=["delta/v9", "custom-x/v2"]).features == [
        "delta/v9", "custom-x/v2"]


def test_supports_declared_and_implied() -> None:
    handoff_cap = replace(_capability(_manifest()), accepts_handoff=True)
    manifest = _manifest(ops=["describe", "health", "execute", "verify"],
                         capabilities=[handoff_cap],
                         features=["delta/v1"])
    assert supports(manifest, HANDOFF)        # implied by accepts_handoff
    assert supports(manifest, VERIFY)         # implied by the verify op
    assert supports(manifest, "delta/v1")     # declared
    assert not supports(manifest, "resume/v1")
    assert not supports(manifest, "made-up/v3")  # unknown id degrades to absent
    assert implied_features(manifest) == frozenset({HANDOFF, VERIFY})
    assert supported_features(manifest) == frozenset({HANDOFF, VERIFY, "delta/v1"})


def test_plan_and_resolve_imply_their_features() -> None:
    planner = replace(_capability(_manifest()), proposes_plans=True,
                      resolves_ambiguity=True)
    manifest = _manifest(ops=["describe", "health", "execute", "plan", "resolve"],
                         capabilities=[planner])
    assert supports(manifest, PLAN_PROPOSAL) and supports(manifest, RESOLVE)
    # op without the capability flag is not enough — and vice-versa
    assert not supports(_manifest(ops=["describe", "health", "execute", "plan"]),
                      PLAN_PROPOSAL)
    assert not supports(_manifest(capabilities=[planner]), PLAN_PROPOSAL)


# --- registry propagation ---------------------------------------------------------------------


def _cache_file(provider_id: str) -> Path:
    return sorted((user_cache_dir() / "registry").glob(f"{provider_id}-*.json"))[0]


class _Counting:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, argv: list[str]) -> SubprocessTransport:
        self.calls += 1
        return SubprocessTransport(argv)


def test_record_and_cache_carry_surface_identity(tmp_path: Path) -> None:
    forge = make_workspace(tmp_path, [SPARK_ENTRY])
    record = next(r for r in Registry(forge).refresh() if r.entry.id == "fixture-spark")
    surface = record.surface
    assert surface is not None
    assert surface.provider_id == "fixture-spark"
    assert surface.provider_version == "0.0.1"
    assert surface.protocol_version == "forge/v1"
    assert surface.recorded_at
    assert record.manifest is not None
    assert surface.surface_fingerprint == surface_fingerprint(record.manifest)
    assert surface.capability_fingerprint == capability_fingerprint(record.manifest)
    doc = json.loads(_cache_file("fixture-spark").read_text(encoding="utf-8"))
    assert doc["surface_fingerprint"] == surface.surface_fingerprint
    assert doc["capability_fingerprint"] == surface.capability_fingerprint


@pytest.mark.parametrize("field_name", ["surface_fingerprint",
                                        "capability_fingerprint"])
def test_tampered_fingerprint_invalidates_the_cache(tmp_path: Path,
                                                    field_name: str) -> None:
    forge = make_workspace(tmp_path, [SPARK_ENTRY])
    Registry(forge).refresh()
    path = _cache_file("fixture-spark")
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc[field_name] = "0" * 64  # a real sha256, but not of this manifest
    path.write_text(json.dumps(doc), encoding="utf-8")
    counting = _Counting()
    registry = Registry(forge, transport_factory=counting)
    assert registry.get("fixture-spark").state == "ready"
    assert counting.calls >= 1  # the mismatch forced a fresh describe


# --- health / receipt / explain propagation -------------------------------------------------


def test_health_outcome_carries_the_surface_fingerprint(tmp_path: Path) -> None:
    forge = make_workspace(tmp_path, [SPARK_ENTRY])
    record = next(r for r in Registry(forge).refresh() if r.entry.id == "fixture-spark")
    outcome = check_health(record)
    assert outcome.status == "ok"
    assert record.surface is not None
    assert outcome.surface_fingerprint == record.surface.surface_fingerprint


def test_health_error_still_carries_the_fingerprint(tmp_path: Path) -> None:
    forge = make_workspace(tmp_path, [SPARK_ENTRY])
    record = next(r for r in Registry(forge).refresh() if r.entry.id == "fixture-spark")
    broken = RegistryRecord(entry=record.entry, state="unreachable",
                            error="gone", surface=record.surface)
    outcome = check_health(broken)
    assert outcome.status == "error"
    assert record.surface is not None
    assert outcome.surface_fingerprint == record.surface.surface_fingerprint


def test_receipt_and_explain_propagate_surface_identity(tmp_path: Path) -> None:
    forge = make_workspace(tmp_path, [SPARK_ENTRY])
    write_file(tmp_path, "jobs/orders_glue_job.py",
               "df = spark.read.parquet('s3://b/orders')\n")
    write_file(tmp_path, "requirements.txt", "pyspark==3.5.1\n")
    store = RunStore(forge)
    out = Forger(tmp_path, Registry(forge), store).ask(
        AskRequest(intent="analise esse Glue Job porque está lento"))
    assert out.status == "ok"
    provider = out.receipt.provider
    assert provider is not None and provider.surface_fingerprint
    registry_surface = Registry(forge).get("fixture-spark").surface
    assert registry_surface is not None
    assert provider.surface_fingerprint == registry_surface.surface_fingerprint
    persisted = store.read(out.run_id, "receipt")["provider"]
    assert persisted["surface_fingerprint"] == provider.surface_fingerprint

    report = build_explain_report(store, out.run_id)
    assert report.provider is not None
    assert report.provider.surface_fingerprint == provider.surface_fingerprint


# --- surface-scoped performance history -------------------------------------------------------


def _perf_entry(surface: str | None, *, verified: int = 2
                ) -> ProviderCapabilityPerformance:
    return ProviderCapabilityPerformance(
        provider="p1", capability="x.y", runs=3, ok=2, partial=1, failed=0,
        verified_runs=verified, evidence=4, artifacts=1, context_bytes=100,
        files_sent=2, files_cited=1, duration_ms=30.0, updated_at="t",
        surface=surface)


def test_score_is_scoped_by_surface_fingerprint() -> None:
    perf = ProviderPerformance(
        producer=PRODUCER, created_at="t",
        entries=[_perf_entry("old-surface"), _perf_entry("new-surface", verified=3)])
    assert perf.score("p1", "x.y", "new-surface")[0] == 1.0   # 3/3 verified
    assert perf.score("p1", "x.y", "old-surface")[0] == 2 / 3
    assert perf.score("p1", "x.y", "other-surface") == (0.0, 0.0, 0.0, 0)
    assert perf.score("p1", "x.y", None) == (0.0, 0.0, 0.0, 0)


def test_legacy_performance_entries_never_match_a_surface() -> None:
    # Entries written before surfaces exist carry surface=None: a provider with
    # a real fingerprint never silently inherits that history.
    perf = ProviderPerformance(producer=PRODUCER, created_at="t",
                               entries=[_perf_entry(None)])
    assert perf.score("p1", "x.y", "abc123") == (0.0, 0.0, 0.0, 0)
    assert perf.score("p1", "x.y", None)[3] == 3


def test_record_performance_keys_history_by_surface(tmp_path: Path) -> None:
    for surface in ("s1", "s2"):
        assert record_performance(tmp_path, "p1", "x.y", surface=surface,
                                  status="ok", verified=True, evidence=1,
                                  artifacts=0, context_bytes=10, files_sent=1,
                                  files_cited=1, duration_ms=5.0) is None
    perf, warning = load_performance(tmp_path)
    assert warning is None and perf is not None
    assert sorted(e.surface for e in perf.entries) == ["s1", "s2"]
    assert perf.score("p1", "x.y", "s1")[3] == 1  # one run under each surface
    assert perf.score("p1", "x.y", "s2")[3] == 1


def test_duplicate_provider_capability_surface_is_rejected() -> None:
    with pytest.raises(ContractError, match="duplicate"):
        ProviderPerformance(producer=PRODUCER, created_at="t",
                            entries=[_perf_entry("s1"), _perf_entry("s1")])


# --- replay drift ----------------------------------------------------------------------------


def test_replay_refuses_on_changed_surface(tmp_path: Path) -> None:
    forge = make_workspace(tmp_path, [])
    store = RunStore(forge)
    forger = Forger(tmp_path, Registry(forge), store)
    write_file(tmp_path, "notes.txt", "hello\n")
    out = forger.ask(AskRequest(intent="eco", capability="demo.echo",
                                profile="balanced"))
    assert out.status == "ok"
    receipt = store.read_contract(out.run_id, "receipt", ExecutionReceipt)
    assert receipt.provider is not None
    assert receipt.provider.surface_fingerprint is not None
    tampered = replace(receipt.provider, surface_fingerprint="0" * 64)
    store.write(out.run_id, "receipt", replace(receipt, provider=tampered))
    with pytest.raises(ReplayRefused) as caught:
        replay(forger, store, out.run_id, "execute")
    assert any("surface changed" in r for r in caught.value.reasons)
