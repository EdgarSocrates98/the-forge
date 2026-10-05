import json
from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from helpers import (
    API_ENTRY,
    SPARK_ENTRY,
    bad_argv,
    bad_entry,
    case_a,
    make_workspace,
    write_providers,
)
from theforge.contracts import Producer, Response, to_dict
from theforge.contracts.canonical import sha256_of
from theforge.contracts.codes import Codes
from theforge.errors import UsageError
from theforge.forger import AskRequest, Forger
from theforge.protocol import ProviderTransport, SubprocessTransport
from theforge.registry import Registry, check_health, user_cache_dir
from theforge.runs import RunStore


def cache_files(provider_id: str) -> list[Path]:
    return sorted((user_cache_dir() / "registry").glob(f"{provider_id}-*.json"))


def cache_file(provider_id: str) -> Path:
    files = cache_files(provider_id)
    assert len(files) == 1, files
    return files[0]


def make_forge(tmp_path: Path, entries: list[dict[str, Any]]) -> Path:
    forge = tmp_path / ".forge"
    write_providers(forge, entries)
    return forge


def test_refresh_describes_and_caches(tmp_path: Path) -> None:
    forge = make_forge(tmp_path, [SPARK_ENTRY])
    records = {r.entry.id: r for r in Registry(forge).refresh()}
    assert records["echo-forge"].state == "ready"
    assert records["fixture-spark"].state == "ready"
    assert records["fixture-spark"].protocol == "forge/v1"
    assert cache_file("fixture-spark").is_file()
    assert not (forge / "registry").exists()


def test_records_use_cache_without_spawning(tmp_path: Path) -> None:
    forge = make_forge(tmp_path, [SPARK_ENTRY])
    Registry(forge).refresh()

    def boom(argv: object) -> Any:
        raise AssertionError("cache hit must not spawn providers")

    assert all(r.state == "ready" for r in Registry(forge, transport_factory=boom).records())


def test_tampered_cache_is_discarded(tmp_path: Path) -> None:
    forge = make_forge(tmp_path, [SPARK_ENTRY])
    Registry(forge).refresh()
    path = cache_file("fixture-spark")
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["manifest"]["version"] = "6.6.6"
    path.write_text(json.dumps(doc), encoding="utf-8")
    registry = Registry(forge)
    record = registry.get("fixture-spark")
    assert record.manifest is not None and record.manifest.version == "0.0.1"
    assert any("fixture-spark" in warning for warning in registry.warnings)


def test_corrupt_cache_is_discarded(tmp_path: Path) -> None:
    forge = make_forge(tmp_path, [SPARK_ENTRY])
    Registry(forge).refresh()
    cache_file("fixture-spark").write_text("{nope", encoding="utf-8")
    registry = Registry(forge)
    assert registry.get("fixture-spark").state == "ready"
    assert registry.warnings


@pytest.mark.parametrize(
    ("mode", "state"),
    [("wrong-major", "incompatible"), ("invalid-manifest", "invalid"),
     ("describe-crash", "unreachable")],
)
def test_bad_providers_degrade(tmp_path: Path, mode: str, state: str) -> None:
    record = Registry(make_forge(tmp_path, [bad_entry(mode, "bad-a")])).get("bad-a")
    assert record.state == state and record.error
    assert not record.routable(allow_unverified=True)


def test_manifest_id_must_match_entry(tmp_path: Path) -> None:
    entry = {"id": "impostor", "argv": bad_argv("ok", "bad-forge"), "trust": "local"}
    record = Registry(make_forge(tmp_path, [entry])).get("impostor")
    assert record.state == "invalid" and "does not match" in (record.error or "")


def test_blocked_is_never_spawned(tmp_path: Path) -> None:
    entry = {"id": "nope-forge", "argv": ["definitely-not-a-real-forge-binary"],
             "trust": "blocked"}
    record = Registry(make_forge(tmp_path, [entry])).get("nope-forge")
    assert record.state == "blocked" and not record.routable(allow_unverified=True)


def test_unverified_is_not_executed_without_opt_in(tmp_path: Path) -> None:
    entry = {"id": "u-forge", "argv": ["definitely-not-a-real-forge-binary"], "trust": "unverified"}
    record = Registry(make_forge(tmp_path, [entry])).get("u-forge")
    assert record.state == "untrusted" and not record.routable(allow_unverified=True)


def test_unverified_routable_only_with_opt_in(tmp_path: Path) -> None:
    forge = make_forge(tmp_path, [bad_entry("ok", "bad-a", trust="unverified")])
    record = Registry(forge, allow_unverified=True).get("bad-a")
    assert not record.routable() and record.routable(allow_unverified=True)


def test_project_file_cannot_grant_trust(tmp_path: Path) -> None:
    forge = tmp_path / ".forge"
    write_providers(forge, [bad_entry("ok", "bad-a", trust="trusted")], scope="project")
    registry = Registry(forge)
    assert registry.get("bad-a").state == "untrusted"
    assert any("bad-a" in w for w in registry.warnings)


def test_repeated_lookups_do_not_duplicate_config_warnings(tmp_path: Path) -> None:
    forge = tmp_path / ".forge"
    write_providers(forge, [bad_entry("ok", "bad-a", trust="trusted")], scope="project")
    registry = Registry(forge)
    for _ in range(3):
        registry.entries()
        registry.records()
        registry.get("bad-a")
    demoted = [w for w in registry.warnings if "bad-a" in w and "ignored" in w]
    assert len(demoted) == 1, registry.warnings
    assert len(registry.warnings) == len(set(registry.warnings))


def test_unknown_provider(tmp_path: Path) -> None:
    with pytest.raises(UsageError, match="unknown provider"):
        Registry(make_forge(tmp_path, [])).get("nope")


def test_health_ok_and_unavailable(tmp_path: Path) -> None:
    registry = Registry(make_forge(tmp_path, [bad_entry("unhealthy", "bad-a")]))
    assert check_health(registry.get("echo-forge")).status == "ok"
    outcome = check_health(registry.get("bad-a"))
    assert outcome.status == "unavailable"
    assert outcome.error is not None and outcome.error.code == "FORGE-HEALTH-UNAVAILABLE"


def test_health_on_not_ready(tmp_path: Path) -> None:
    registry = Registry(make_forge(tmp_path, [bad_entry("describe-crash", "bad-a")]))
    outcome = check_health(registry.get("bad-a"))
    assert outcome.status == "error"
    assert outcome.error is not None and outcome.error.code == "FORGE-PROVIDER-NOT-READY"


def test_registry_without_forge_dir_still_describes() -> None:
    records = Registry(None).records()
    assert [r.entry.id for r in records] == ["echo-forge"] and records[0].state == "ready"


def _boom(argv: object) -> Any:
    raise AssertionError("must not spawn")


def test_unverified_is_never_cached(tmp_path: Path) -> None:
    forge = make_forge(tmp_path, [bad_entry("ok", "bad-a", trust="unverified")])
    record = Registry(forge, allow_unverified=True).refresh()
    assert any(r.entry.id == "bad-a" and r.state == "ready" for r in record)
    assert not cache_files("bad-a")
    assert Registry(forge).get("bad-a").state == "untrusted"


def test_forged_cache_cannot_launder_unverified(tmp_path: Path) -> None:
    forge = make_forge(tmp_path, [SPARK_ENTRY])
    Registry(forge).refresh()
    path = cache_file("fixture-spark")
    doc = json.loads(path.read_text(encoding="utf-8"))
    unverified = {"id": "fixture-spark", "argv": ["definitely-not-a-real-forge-binary"],
                  "trust": "unverified"}
    write_providers(forge, [unverified])
    entry = next(e for e in Registry(forge).entries() if e.id == "fixture-spark")
    doc["entry"] = to_dict(entry)
    path.write_text(json.dumps(doc), encoding="utf-8")
    registry = Registry(forge, transport_factory=_boom)
    assert registry.get("fixture-spark").state == "untrusted"


def test_health_refuses_unverified_and_blocked(tmp_path: Path) -> None:
    forge = make_forge(tmp_path, [bad_entry("ok", "bad-a", trust="unverified"),
                                  {"id": "nope-forge", "argv": ["x"], "trust": "blocked"}])
    ready = Registry(forge, allow_unverified=True).get("bad-a")
    assert ready.state == "ready"
    outcome = check_health(ready, transport_factory=_boom)
    assert outcome.error is not None and outcome.error.code == "FORGE-PROVIDER-UNTRUSTED"
    assert check_health(ready, allow_unverified=True).status in {"ok", "degraded"}
    blocked = Registry(forge).get("nope-forge")
    outcome = check_health(blocked, transport_factory=_boom, allow_unverified=True)
    assert outcome.error is not None and outcome.error.code == "FORGE-PROVIDER-BLOCKED"


def _tampered(tmp_path: Path, mutate: Any) -> Registry:
    forge = make_forge(tmp_path, [SPARK_ENTRY])
    Registry(forge).refresh()
    path = cache_file("fixture-spark")
    doc = json.loads(path.read_text(encoding="utf-8"))
    mutate(doc)
    path.write_text(json.dumps(doc), encoding="utf-8")
    registry = Registry(forge)
    assert registry.get("fixture-spark").state == "ready"
    return registry


def test_cache_with_wrong_protocol_is_discarded(tmp_path: Path) -> None:
    def mutate(doc: dict[str, Any]) -> None:
        doc["protocol"] = "forge/v9"
    registry = _tampered(tmp_path, mutate)
    assert registry.get("fixture-spark").protocol == "forge/v1"
    assert any("fixture-spark" in w for w in registry.warnings)


def test_cache_with_wrong_manifest_id_is_discarded(tmp_path: Path) -> None:
    def mutate(doc: dict[str, Any]) -> None:
        doc["manifest"]["id"] = "someone-else"
        doc["manifest_sha256"] = sha256_of(doc["manifest"])
    registry = _tampered(tmp_path, mutate)
    manifest = registry.get("fixture-spark").manifest
    assert manifest is not None and manifest.id == "fixture-spark"
    assert any("fixture-spark" in w for w in registry.warnings)


def test_refresh_removes_stale_cache(tmp_path: Path) -> None:
    forge = make_forge(tmp_path, [SPARK_ENTRY])
    Registry(forge).refresh()
    cache = cache_file("fixture-spark")
    assert cache.is_file()
    broken = {**SPARK_ENTRY, "argv": ["definitely-not-a-real-forge-binary"]}
    write_providers(forge, [broken])
    records = {r.entry.id: r for r in Registry(forge).refresh()}
    assert records["fixture-spark"].state == "unreachable"
    # cache files are keyed by entry digest: the changed entry never sees the old
    # manifest, its unreachable record is not cached, and the old-digest file is
    # pruned rather than orphaned
    assert cache_files("fixture-spark") == []
    assert Registry(forge).get("fixture-spark").state == "unreachable"


def test_records_persist_false_leaves_no_cache(tmp_path: Path) -> None:
    forge = make_forge(tmp_path, [SPARK_ENTRY])
    records = Registry(forge).records(persist=False)
    assert all(r.state == "ready" for r in records)
    assert not cache_files("fixture-spark") and not (forge / "registry").exists()


# --- producer checks, manifest limits, controlled cwd, revalidation ----------------------


class _Recording:
    """Transport factory recording every call's (op, cwd) and response; may rewrite them."""

    def __init__(self, rewrite: Callable[[str, Response], Response] | None = None) -> None:
        self.calls: list[tuple[str, Path | None]] = []
        self.responses: list[Response] = []
        self.rewrite = rewrite

    def __call__(self, argv: Sequence[str]) -> ProviderTransport:
        return _RecordingTransport(self, argv)


class _RecordingTransport:
    def __init__(self, owner: _Recording, argv: Sequence[str]) -> None:
        self.owner = owner
        self.inner = SubprocessTransport(argv)

    def call(self, op: str, payload: dict[str, Any], *, timeout: float,
             cwd: Path | None = None, check_protocol: bool = True) -> Response:
        self.owner.calls.append((op, cwd))
        response = self.inner.call(op, payload, timeout=timeout, cwd=cwd,
                                   check_protocol=check_protocol)
        if self.owner.rewrite is not None:
            response = self.owner.rewrite(op, response)
        self.owner.responses.append(response)
        return response


def _bump_version(op: str, response: Response) -> Response:
    return replace(response, producer=Producer(id=response.producer.id, version="9.9.9"))


def test_describe_with_divergent_producer_id_is_invalid(tmp_path: Path) -> None:
    forge = make_forge(tmp_path, [bad_entry("describe-wrong-producer", "bad-a")])
    record = Registry(forge).get("bad-a")
    assert record.state == "invalid" and not record.routable()
    assert Codes.PROTO_PRODUCER in (record.error or "")
    assert not cache_files("bad-a")


def test_describe_with_divergent_producer_version_is_invalid(tmp_path: Path) -> None:
    forge = make_forge(tmp_path, [bad_entry("ok", "bad-a")])
    record = Registry(forge, transport_factory=_Recording(_bump_version)).get("bad-a")
    assert record.state == "invalid"
    assert Codes.PROTO_PRODUCER in (record.error or "") and "9.9.9" in (record.error or "")


def test_health_with_divergent_producer_id_is_error(tmp_path: Path) -> None:
    forge = make_forge(tmp_path, [bad_entry("health-wrong-producer", "bad-a")])
    record = Registry(forge).get("bad-a")
    assert record.state == "ready"
    outcome = check_health(record)
    assert outcome.status == "error"
    assert outcome.error is not None and outcome.error.code == Codes.PROTO_PRODUCER


def test_health_with_divergent_producer_version_is_error(tmp_path: Path) -> None:
    forge = make_forge(tmp_path, [bad_entry("ok", "bad-a")])
    record = Registry(forge).get("bad-a")

    def health_only(op: str, response: Response) -> Response:
        return _bump_version(op, response) if op == "health" else response

    outcome = check_health(record, transport_factory=_Recording(health_only))
    assert outcome.status == "error"
    assert outcome.error is not None and outcome.error.code == Codes.PROTO_PRODUCER


def _assert_controlled_cwd(observed: str, caller: Path) -> None:
    path = Path(observed)
    assert path.resolve() != caller.resolve()
    assert path.name.startswith("theforge-")
    assert not path.exists()  # a fresh temporary directory per call, removed afterwards


def test_describe_runs_in_a_controlled_temporary_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    forge = make_forge(tmp_path, [bad_entry("describe-cwd-probe", "bad-a")])
    monkeypatch.chdir(tmp_path)
    record = Registry(forge).get("bad-a")
    assert record.state == "ready" and record.manifest is not None
    [limitation] = record.manifest.limitations
    assert limitation.startswith("cwd=")
    _assert_controlled_cwd(limitation.removeprefix("cwd="), tmp_path)


def test_health_runs_in_a_controlled_temporary_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    forge = make_forge(tmp_path, [bad_entry("health-cwd-probe", "bad-a")])
    monkeypatch.chdir(tmp_path)
    recording = _Recording()
    outcome = check_health(Registry(forge).get("bad-a"), transport_factory=recording)
    assert outcome.status == "ok"
    [check] = recording.responses[-1].payload["checks"]
    _assert_controlled_cwd(check["detail"], tmp_path)


def test_catch_all_glob_capability_is_excluded_with_warning(tmp_path: Path) -> None:
    forge = make_forge(tmp_path, [bad_entry("describe-catch-all-glob", "bad-a")])
    registry = Registry(forge)
    record = registry.get("bad-a")
    assert record.state == "ready" and record.manifest is not None
    assert [c.id for c in record.manifest.capabilities] == ["bad.thing"]
    assert record.manifest_sha256 == sha256_of(to_dict(record.manifest))
    assert any("bad.greedy" in w and Codes.MANIFEST_LIMITS in w for w in registry.warnings)
    # the filtered manifest is what gets cached and re-read
    cached = Registry(forge, transport_factory=_boom).get("bad-a")
    assert cached.manifest == record.manifest


def test_manifest_with_only_excluded_capabilities_is_invalid(tmp_path: Path) -> None:
    forge = make_forge(tmp_path, [bad_entry("describe-only-catch-all-glob", "bad-a")])
    record = Registry(forge).get("bad-a")
    assert record.state == "invalid" and Codes.MANIFEST_LIMITS in (record.error or "")


def test_manifest_with_too_many_capabilities_is_invalid(tmp_path: Path) -> None:
    forge = make_forge(tmp_path, [bad_entry("describe-too-many-capabilities", "bad-a")])
    record = Registry(forge).get("bad-a")
    assert record.state == "invalid" and Codes.MANIFEST_LIMITS in (record.error or "")
    assert not record.routable(allow_unverified=True)


def test_revalidate_fresh(tmp_path: Path) -> None:
    forge = make_forge(tmp_path, [SPARK_ENTRY])
    Registry(forge).refresh()
    registry = Registry(forge)
    in_use = registry.get("fixture-spark")
    [outcome] = registry.revalidate(["fixture-spark"])
    assert outcome.status == "fresh"
    assert outcome.record.manifest_sha256 == in_use.manifest_sha256


def test_revalidate_detects_altered_cached_manifest(tmp_path: Path) -> None:
    forge = make_forge(tmp_path, [SPARK_ENTRY])
    Registry(forge).refresh()
    path = cache_file("fixture-spark")
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["manifest"]["capabilities"][0]["signals"]["keywords"].append("injected")
    doc["manifest_sha256"] = sha256_of(doc["manifest"])  # self-consistent tampering
    path.write_text(json.dumps(doc), encoding="utf-8")
    registry = Registry(forge)
    tampered = registry.get("fixture-spark")
    assert tampered.manifest_sha256 == doc["manifest_sha256"]  # accepted from the cache
    [outcome] = registry.revalidate(["fixture-spark"])
    assert outcome.status == "changed"
    assert outcome.record.state == "ready"
    assert outcome.record.manifest_sha256 != tampered.manifest_sha256


def test_revalidate_reports_unreachable(tmp_path: Path) -> None:
    forge = make_forge(tmp_path, [SPARK_ENTRY])
    Registry(forge).refresh()

    def unreachable(argv: Sequence[str]) -> ProviderTransport:
        return SubprocessTransport(["definitely-not-a-real-forge-binary"])

    registry = Registry(forge, transport_factory=unreachable)
    assert registry.get("fixture-spark").state == "ready"  # from the cache
    outcomes = registry.revalidate(["fixture-spark", "echo-forge"])
    assert [o.status for o in outcomes] == ["unreachable", "unreachable"]
    assert all(o.record.state == "unreachable" for o in outcomes)


def test_revalidate_unknown_provider(tmp_path: Path) -> None:
    with pytest.raises(UsageError, match="unknown provider"):
        Registry(make_forge(tmp_path, [])).revalidate(["nope"])


def test_invalidate_removes_cache_entry(tmp_path: Path) -> None:
    forge = make_forge(tmp_path, [SPARK_ENTRY])
    Registry(forge).refresh()
    registry = Registry(forge)
    registry.records()
    registry.invalidate("fixture-spark")
    assert not cache_files("fixture-spark")
    assert cache_files("echo-forge")
    recording = _Recording()
    record = next(r for r in Registry(forge, transport_factory=recording).records()
                  if r.entry.id == "fixture-spark")
    assert record.state == "ready"
    assert [op for op, _ in recording.calls] == ["describe"]


def test_no_core_caller_uses_the_callers_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """describe, health, revalidate and execute always pass a controlled ``cwd``."""
    make_workspace(tmp_path, [SPARK_ENTRY, API_ENTRY])
    case_a(tmp_path)
    monkeypatch.chdir(tmp_path)
    forge = tmp_path / ".forge"
    recording = _Recording()
    registry = Registry(forge, transport_factory=recording)
    registry.refresh()
    registry.revalidate(["fixture-spark", "fixture-api"])
    check_health(registry.get("fixture-spark"), transport_factory=recording)
    registry.invalidate("fixture-spark")
    out = Forger(tmp_path, registry, RunStore(forge), transport_factory=recording).ask(
        AskRequest(intent="analise esse Glue Job porque está lento"))
    assert out.status == "ok"
    assert {op for op, _ in recording.calls} == {"describe", "health", "execute"}
    for op, cwd in recording.calls:
        assert isinstance(cwd, Path), (op, cwd)
        assert cwd.resolve() != tmp_path.resolve(), op


def test_malformed_version_is_invalid_with_truncated_version(tmp_path: Path) -> None:
    forge = make_forge(tmp_path, [bad_entry("describe-bad-version", "bad-a")])
    record = Registry(forge).get("bad-a")
    error = record.error or ""
    assert record.state == "invalid" and not record.routable(allow_unverified=True)
    assert error.startswith(f"{Codes.MANIFEST_VERSION}: version ")
    assert "v1.2.3-long" in error and "SemVer 2.0.0" in error
    assert ("-long" * 20) not in error  # the received version is echoed truncated
    assert not cache_files("bad-a")


def test_off_taxonomy_capability_is_excluded_once_with_warning(tmp_path: Path) -> None:
    forge = make_forge(tmp_path, [bad_entry("describe-off-taxonomy", "bad-a")])
    registry = Registry(forge)
    record = registry.get("bad-a")
    assert record.state == "ready" and record.manifest is not None
    assert [c.id for c in record.manifest.capabilities] == ["bad.thing"]
    assert record.manifest_sha256 == sha256_of(to_dict(record.manifest))
    excluded = [w for w in registry.warnings if "theforge.all" in w]
    assert len(excluded) == 1, registry.warnings  # several violations, one exclusion
    assert excluded[0].startswith(
        f"bad-a: capability 'theforge.all' excluded ({Codes.MANIFEST_TAXONOMY}: ")


def test_only_off_taxonomy_capabilities_is_invalid(tmp_path: Path) -> None:
    forge = make_forge(tmp_path, [bad_entry("describe-only-off-taxonomy", "bad-a")])
    record = Registry(forge).get("bad-a")
    assert record.state == "invalid" and not record.routable(allow_unverified=True)
    assert Codes.MANIFEST_TAXONOMY in (record.error or "")
    assert "forge.misc" in (record.error or "")


def test_colliding_alias_makes_provider_invalid(tmp_path: Path) -> None:
    forge = make_forge(tmp_path, [bad_entry("describe-colliding-alias", "bad-a")])
    record = Registry(forge).get("bad-a")
    assert record.state == "invalid" and not record.routable(allow_unverified=True)
    assert "alias equal to capability id" in (record.error or "")
    assert "bad.thing" in (record.error or "")


def test_refused_describe_records_redacted_truncated_detail(tmp_path: Path) -> None:
    forge = make_forge(tmp_path, [bad_entry("describe-refused", "bad-a")])
    record = Registry(forge).get("bad-a")
    error = record.error or ""
    assert record.state == "invalid" and not record.routable(allow_unverified=True)
    prefix = "describe refused BAD-NOT-INSTALLED: "
    assert error.startswith(prefix + "specialist not importable token=")
    assert "supersecretvalue123" not in error
    assert len(error) - len(prefix) == 500
