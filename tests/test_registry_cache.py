"""Registry cache v2: user cache dir, fingerprint invalidation, atomic writes, migration."""

import json
import os
import shutil
import threading
from pathlib import Path
from typing import Any

import pytest

from helpers import API_ENTRY, PROVIDERS, SPARK_ENTRY, case_a, make_workspace, write_providers
from theforge.contracts.canonical import sha256_of
from theforge.forger import AskRequest, Forger
from theforge.protocol import SubprocessTransport
from theforge.registry import Registry, user_cache_dir
from theforge.runs import RunStore
from theforge.state import init_workspace


def _forge(tmp_path: Path, entries: list[dict[str, Any]]) -> Path:
    forge = tmp_path / ".forge"
    write_providers(forge, entries)
    return forge


def _cache_files(provider_id: str) -> list[Path]:
    return sorted((user_cache_dir() / "registry").glob(f"{provider_id}-*.json"))


class _Counting:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, argv: list[str]) -> SubprocessTransport:
        self.calls += 1
        return SubprocessTransport(argv)


def test_cache_lives_in_user_cache_dir_not_forge(tmp_path: Path) -> None:
    forge = _forge(tmp_path, [SPARK_ENTRY])
    Registry(forge).refresh()
    assert not (forge / "registry").exists()
    assert not [p for p in forge.rglob("*.json") if "config" not in p.parts]
    files = _cache_files("fixture-spark")
    assert len(files) == 1
    assert files[0].is_relative_to(Path(os.environ["THEFORGE_CACHE_DIR"]))
    doc = json.loads(files[0].read_text(encoding="utf-8"))
    assert doc["schema"] == "theforge/RegistryCache/v2"
    assert set(doc) == {"schema", "entry", "entry_digest", "fingerprint", "state", "manifest",
                        "manifest_sha256", "protocol", "written_at"}
    assert files[0].name == f"fixture-spark-{doc['entry_digest'][:12]}.json"


def test_explicit_cache_dir_parameter(tmp_path: Path) -> None:
    forge = _forge(tmp_path, [SPARK_ENTRY])
    cache = tmp_path / "elsewhere"
    Registry(forge, cache_dir=cache).refresh()
    assert list((cache / "registry").glob("fixture-spark-*.json"))
    assert not _cache_files("fixture-spark")


def test_cache_hit_avoids_describe(tmp_path: Path) -> None:
    forge = _forge(tmp_path, [SPARK_ENTRY])
    Registry(forge).refresh()
    counting = _Counting()
    assert all(r.state == "ready" for r in Registry(forge, transport_factory=counting).records())
    assert counting.calls == 0


def test_script_mtime_change_forces_new_describe(tmp_path: Path) -> None:
    script = tmp_path / "fixture_forge.py"
    shutil.copy(PROVIDERS / "fixture_forge.py", script)
    entry = {**SPARK_ENTRY, "argv": [SPARK_ENTRY["argv"][0], str(script),
                                     str(PROVIDERS / "fixture-spark.json")]}
    forge = _forge(tmp_path, [entry])
    Registry(forge).refresh()
    counting = _Counting()
    Registry(forge, transport_factory=counting).records()
    assert counting.calls == 0
    st = script.stat()
    os.utime(script, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
    counting = _Counting()
    record = next(r for r in Registry(forge, transport_factory=counting).records()
                  if r.entry.id == "fixture-spark")
    assert record.state == "ready"
    assert counting.calls == 1  # echo-forge stays cached; only fixture-spark re-described


def test_interleaved_writers_do_not_fail(tmp_path: Path) -> None:
    forge = _forge(tmp_path, [SPARK_ENTRY])
    first, second = Registry(forge), Registry(forge)
    records = [r for r in first.refresh() if r.entry.id == "fixture-spark"]
    errors: list[BaseException] = []

    def hammer(registry: Registry) -> None:
        try:
            for _ in range(25):
                registry._write_cache(records[0])
        except BaseException as exc:  # noqa: BLE001 - surfaced by the assertion below
            errors.append(exc)

    threads = [threading.Thread(target=hammer, args=(r,)) for r in (first, second)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert len(_cache_files("fixture-spark")) == 1
    assert not list((user_cache_dir() / "registry").glob("*.tmp"))
    reread = Registry(forge, transport_factory=_boom).get("fixture-spark")
    assert reread.state == "ready"


def _boom(argv: object) -> Any:
    raise AssertionError("must not spawn")


def test_write_failure_becomes_warning(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import theforge.registry.registry as module

    def broken_replace(src: object, dst: object) -> None:
        raise OSError("disk on fire")

    monkeypatch.setattr(module.os, "replace", broken_replace)
    forge = _forge(tmp_path, [SPARK_ENTRY])
    registry = Registry(forge)
    records = {r.entry.id: r for r in registry.refresh()}
    assert records["fixture-spark"].state == "ready"
    assert any("disk on fire" in w for w in registry.warnings)
    assert not list((user_cache_dir() / "registry").glob("*"))


def test_unwritable_cache_dir_becomes_warning(tmp_path: Path) -> None:
    blocker = tmp_path / "cache-is-a-file"
    blocker.write_text("x", encoding="utf-8")
    forge = _forge(tmp_path, [SPARK_ENTRY])
    registry = Registry(forge, cache_dir=blocker)
    assert all(r.state == "ready" for r in registry.records())
    assert any("registry cache" in w for w in registry.warnings)


def test_strict_read_rejects_unknown_key(tmp_path: Path) -> None:
    forge = _forge(tmp_path, [SPARK_ENTRY])
    Registry(forge).refresh()
    path = _cache_files("fixture-spark")[0]
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["manifest"]["sneaky"] = True
    path.write_text(json.dumps(doc), encoding="utf-8")
    counting = _Counting()
    registry = Registry(forge, transport_factory=counting)
    assert registry.get("fixture-spark").state == "ready"
    assert counting.calls == 1
    assert any("fixture-spark" in w and "sneaky" in w for w in registry.warnings)


def test_entry_change_invalidates(tmp_path: Path) -> None:
    forge = _forge(tmp_path, [SPARK_ENTRY])
    Registry(forge).refresh()
    write_providers(forge, [{**SPARK_ENTRY, "trust": "trusted"}])
    counting = _Counting()
    record = Registry(forge, transport_factory=counting).get("fixture-spark")
    assert record.entry.trust == "trusted" and record.state == "ready"
    assert counting.calls == 1


def test_fingerprint_mismatch_in_file_is_a_miss(tmp_path: Path) -> None:
    forge = _forge(tmp_path, [SPARK_ENTRY])
    Registry(forge).refresh()
    path = _cache_files("fixture-spark")[0]
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["fingerprint"] = "0" * 64
    path.write_text(json.dumps(doc), encoding="utf-8")
    counting = _Counting()
    assert Registry(forge, transport_factory=counting).get("fixture-spark").state == "ready"
    assert counting.calls == 1


def _legacy(forge: Path) -> Path:
    legacy = forge / "registry"
    legacy.mkdir(parents=True, exist_ok=True)
    (legacy / "fixture-spark.json").write_text("{}", encoding="utf-8")
    return legacy


def test_refresh_removes_legacy_dir_with_warning(tmp_path: Path) -> None:
    forge = _forge(tmp_path, [SPARK_ENTRY])
    legacy = _legacy(forge)
    registry = Registry(forge)
    registry.refresh()
    assert not legacy.exists()
    assert any(".forge" in w and "registry" in w for w in registry.warnings)


def test_init_removes_legacy_dir_with_warning(tmp_path: Path) -> None:
    init_workspace(tmp_path)
    legacy = _legacy(tmp_path / ".forge")
    warnings: list[str] = []
    init_workspace(tmp_path, warnings)
    assert not legacy.exists()
    assert warnings and "registry" in warnings[0]


def test_init_does_not_create_registry_dir(tmp_path: Path) -> None:
    created = init_workspace(tmp_path)
    assert ".forge/registry" not in created
    assert not (tmp_path / ".forge" / "registry").exists()


def test_registry_without_forge_dir_uses_user_cache() -> None:
    Registry(None).refresh()
    assert _cache_files("echo-forge")


def test_cache_without_schema_or_v1_is_discarded(tmp_path: Path) -> None:
    forge = _forge(tmp_path, [SPARK_ENTRY])
    Registry(forge).refresh()
    path = _cache_files("fixture-spark")[0]
    doc = json.loads(path.read_text(encoding="utf-8"))
    for schema in (None, "theforge/RegistryCache/v1"):
        bad = {k: v for k, v in doc.items() if k != "schema"}
        if schema:
            bad["schema"] = schema
        path.write_text(json.dumps(bad), encoding="utf-8")
        registry = Registry(forge, transport_factory=_Counting())
        assert registry.get("fixture-spark").state == "ready"
        assert any("fixture-spark" in w for w in registry.warnings)


# --- revalidation before the final routing decision (4.3, task 3.6) -------------------------

class _CountingStore(RunStore):
    def __init__(self, forge_dir: Path) -> None:
        super().__init__(forge_dir)
        self.writes: list[str] = []

    def write(self, run_id: str, name: str, contract: Any) -> str:
        self.writes.append(name)
        return super().write(run_id, name, contract)


def _tamper_api_with_spark_signals() -> Path:
    """Copy fixture-spark's signals into fixture-api's cached manifest, hash kept consistent."""
    spark = json.loads(_cache_files("fixture-spark")[0].read_text(encoding="utf-8"))
    path = _cache_files("fixture-api")[0]
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["manifest"]["capabilities"][0]["signals"] = spark["manifest"]["capabilities"][0]["signals"]
    doc["manifest_sha256"] = sha256_of(doc["manifest"])
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def test_tampered_cache_of_non_selected_provider_is_detected_before_decision(
    tmp_path: Path,
) -> None:
    forge = make_workspace(tmp_path, [SPARK_ENTRY, API_ENTRY])
    case_a(tmp_path)
    Registry(forge).refresh()
    path = _tamper_api_with_spark_signals()
    # the tampered cache is accepted as-is by records(): it would force a tie
    tampered = {r.entry.id: r for r in Registry(forge, transport_factory=_boom).records()}
    assert tampered["fixture-api"].manifest is not None
    assert tampered["fixture-api"].manifest.capabilities[0].signals.dependencies == [
        "pyspark", "awsglue"]

    store = _CountingStore(forge)
    out = Forger(tmp_path, Registry(forge), store).ask(
        AskRequest(intent="analise esse Glue Job porque está lento"))
    assert out.status == "ok"
    assert out.decision.selected[0].provider == "fixture-spark"
    assert "registry-revalidated: fixture-api" in out.decision.limitations
    assert "fixture-api" not in {c.provider for c in out.decision.candidates}
    assert store.writes.count("routing") == 1
    routing = store.read(out.run_id, "routing")
    assert routing["limitations"] == out.decision.limitations
    assert out.receipt.inputs.routing_sha256 == sha256_of(routing)
    # the cache was rediscovered from the real provider
    fresh = json.loads(path.read_text(encoding="utf-8"))
    assert fresh["manifest"]["capabilities"][0]["signals"]["dependencies"] == ["fastapi", "flask"]
