"""Registry cache v2: user cache dir, fingerprint invalidation, atomic writes, migration."""

import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import pytest

from helpers import API_ENTRY, PROVIDERS, SPARK_ENTRY, case_a, make_workspace, write_providers
from theforge.contracts.canonical import sha256_of
from theforge.forger import AskRequest, Forger
from theforge.protocol import SubprocessTransport
from theforge.registry import Registry, fingerprint, user_cache_dir
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


def test_tampered_extra_capability_of_selected_provider_is_rediscovered_before_execute(
    tmp_path: Path,
) -> None:
    forge = make_workspace(tmp_path, [SPARK_ENTRY, API_ENTRY])
    case_a(tmp_path)
    Registry(forge).refresh()
    path = _cache_files("fixture-spark")[0]
    doc = json.loads(path.read_text(encoding="utf-8"))
    injected = {**doc["manifest"]["capabilities"][0], "id": "spark.injected",
                "operation_class": "local_mutation"}
    doc["manifest"]["capabilities"].append(injected)
    doc["manifest_sha256"] = sha256_of(doc["manifest"])
    path.write_text(json.dumps(doc), encoding="utf-8")
    # the tampered cache is internally consistent: records() serves it without describing
    tampered = Registry(forge, transport_factory=_boom).get("fixture-spark")
    assert tampered.manifest is not None
    assert [c.id for c in tampered.manifest.capabilities] == ["spark.performance",
                                                              "spark.injected"]

    store = _CountingStore(forge)
    out = Forger(tmp_path, Registry(forge), store).ask(
        AskRequest(intent="analise esse Glue Job porque está lento"))
    assert out.status == "ok"
    assert out.decision.selected[0].provider == "fixture-spark"
    assert out.decision.selected[0].capability == "spark.performance"
    assert "spark.injected" not in {c.capability for c in out.decision.candidates}
    assert "registry-revalidated: fixture-spark" in out.decision.limitations
    assert store.writes.count("routing") == 1
    assert store.writes.count("result") == 1
    fresh = json.loads(path.read_text(encoding="utf-8"))
    assert [c["id"] for c in fresh["manifest"]["capabilities"]] == ["spark.performance"]


def _copied_spark(tmp_path: Path) -> tuple[dict[str, Any], Path]:
    manifest = tmp_path / "fixture-spark.json"
    shutil.copy(PROVIDERS / "fixture-spark.json", manifest)
    entry = {**SPARK_ENTRY, "argv": [*SPARK_ENTRY["argv"][:-1], str(manifest)]}
    return entry, manifest


def test_provider_version_change_invalidates_cache(tmp_path: Path) -> None:
    entry, manifest = _copied_spark(tmp_path)
    forge = _forge(tmp_path, [entry])
    Registry(forge).refresh()
    doc = json.loads(manifest.read_text(encoding="utf-8"))
    assert doc["version"] == "0.0.1"
    doc["version"] = "0.0.10"  # a size change too: robust to coarse mtime resolution
    manifest.write_text(json.dumps(doc), encoding="utf-8")
    counting = _Counting()
    record = Registry(forge, transport_factory=counting).get("fixture-spark")
    assert counting.calls == 1
    assert record.state == "ready" and record.manifest is not None
    assert record.manifest.version == "0.0.10"
    cached = json.loads(_cache_files("fixture-spark")[0].read_text(encoding="utf-8"))
    assert cached["manifest"]["version"] == "0.0.10"


def test_executable_change_invalidates_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import theforge.registry.identity as identity

    forge = _forge(tmp_path, [SPARK_ENTRY])
    Registry(forge).refresh()
    spark = next(e for e in Registry(forge).entries() if e.id == "fixture-spark")
    before = fingerprint(spark)
    other = tmp_path / "bin" / "python-other"
    other.parent.mkdir()
    other.write_text("stand-in interpreter", encoding="utf-8")
    real_which = identity.shutil.which

    def moved_which(cmd: str, *args: Any, **kwargs: Any) -> str | None:
        return str(other) if cmd == spark.argv[0] else real_which(cmd, *args, **kwargs)

    monkeypatch.setattr(identity.shutil, "which", moved_which)
    after = fingerprint(spark)
    assert after.executable == str(other) and after.digest != before.digest
    counting = _Counting()
    registry = Registry(forge, transport_factory=counting)
    sharing = [e.id for e in registry.entries() if e.argv[0] == spark.argv[0]]
    assert "fixture-spark" in sharing  # echo-forge runs on the same interpreter
    record = registry.get("fixture-spark")
    assert record.state == "ready"
    assert counting.calls == len(sharing)  # every entry on the moved executable re-described
    cached = json.loads(_cache_files("fixture-spark")[0].read_text(encoding="utf-8"))
    assert cached["fingerprint"] == after.digest


def test_receipt_records_identity_matching_the_cache(tmp_path: Path) -> None:
    forge = make_workspace(tmp_path, [SPARK_ENTRY, API_ENTRY])
    case_a(tmp_path)
    registry = Registry(forge)
    registry.refresh()
    spark = next(e for e in registry.entries() if e.id == "fixture-spark")
    expected = fingerprint(spark)
    cached = json.loads(_cache_files("fixture-spark")[0].read_text(encoding="utf-8"))
    assert cached["fingerprint"] == expected.digest
    store = RunStore(forge)
    out = Forger(tmp_path, Registry(forge), store).ask(
        AskRequest(intent="analise esse Glue Job porque está lento"))
    assert out.status == "ok"
    provider = out.receipt.provider
    assert provider is not None and provider.id == "fixture-spark"
    assert provider.executable == expected.executable
    assert provider.fingerprint == expected.digest
    assert provider.observed_version == "0.0.1"
    # the manifest hash is recorded separately: it describes the provider, it does not identify it
    assert provider.manifest_sha256 == cached["manifest_sha256"]
    persisted = store.read(out.run_id, "receipt")["provider"]
    assert (persisted["executable"], persisted["fingerprint"], persisted["observed_version"]) == (
        expected.executable, expected.digest, "0.0.1")


def _symlinked_legacy(forge: Path, tmp_path: Path) -> tuple[Path, Path]:
    target = tmp_path / "outside-target"
    target.mkdir()
    (target / "keep.json").write_text("{}", encoding="utf-8")
    link = forge / "registry"
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(target, link, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"cannot create directory symlinks here: {exc}")
    return link, target


def test_refresh_unlinks_symlinked_legacy_dir_without_deleting_target(tmp_path: Path) -> None:
    forge = _forge(tmp_path, [SPARK_ENTRY])
    link, target = _symlinked_legacy(forge, tmp_path)
    registry = Registry(forge)
    registry.refresh()
    assert not link.exists() and not link.is_symlink()
    assert (target / "keep.json").is_file()
    assert any("registry" in w for w in registry.warnings)


def test_init_unlinks_symlinked_legacy_dir_without_deleting_target(tmp_path: Path) -> None:
    init_workspace(tmp_path)
    link, target = _symlinked_legacy(tmp_path / ".forge", tmp_path)
    warnings: list[str] = []
    init_workspace(tmp_path, warnings)
    assert not link.exists() and not link.is_symlink()
    assert (target / "keep.json").is_file()
    assert warnings and "registry" in warnings[0]


def _not_os_contention(warnings: list[str]) -> list[str]:
    """Warnings other than OS-level contention (e.g. a torn or corrupted cache read)."""
    return [w for w in warnings if "WinError" not in w and "Errno" not in w]


def test_concurrent_readers_never_see_a_torn_entry(tmp_path: Path) -> None:
    forge = _forge(tmp_path, [SPARK_ENTRY])
    writer = Registry(forge)
    record = next(r for r in writer.refresh() if r.entry.id == "fixture-spark")
    readers = [Registry(forge, transport_factory=_boom) for _ in range(2)]
    stop = threading.Event()
    errors: list[BaseException] = []
    hits: list[int] = []

    def write() -> None:
        try:
            for _ in range(60):
                writer._write_cache(record)
        except BaseException as exc:  # noqa: BLE001 - surfaced by the assertion below
            errors.append(exc)
        finally:
            stop.set()

    def read(registry: Registry) -> None:
        try:
            while not stop.is_set():
                got = registry._read_cache(record.entry)
                if got is not None:
                    assert got.manifest_sha256 == record.manifest_sha256
                    hits.append(1)
        except BaseException as exc:  # noqa: BLE001 - surfaced by the assertion below
            errors.append(exc)

    threads = [threading.Thread(target=write),
               *(threading.Thread(target=read, args=(r,)) for r in readers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert hits
    for registry in (writer, *readers):
        assert _not_os_contention(registry.warnings) == []
    assert not list((user_cache_dir() / "registry").glob("*.tmp"))
    assert Registry(forge, transport_factory=_boom).get("fixture-spark").state == "ready"


_WRITER_SCRIPT = """
import json, sys
from pathlib import Path
from theforge.registry import Registry
registry = Registry(Path(sys.argv[1]))
record = next(r for r in registry.records() if r.entry.id == "fixture-spark")
assert record.state == "ready", record
for _ in range(int(sys.argv[2])):
    registry._write_cache(record)
print(json.dumps(registry.warnings))
"""


def test_concurrent_writer_processes_leave_a_valid_entry(tmp_path: Path) -> None:
    forge = _forge(tmp_path, [SPARK_ENTRY])
    Registry(forge).refresh()
    procs = [subprocess.Popen([sys.executable, "-c", _WRITER_SCRIPT, str(forge), "40"],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
             for _ in range(3)]
    outputs = [p.communicate(timeout=120) for p in procs]
    for proc, (out, err) in zip(procs, outputs, strict=True):
        assert proc.returncode == 0, err
        assert _not_os_contention(json.loads(out)) == []
    assert len(_cache_files("fixture-spark")) == 1
    assert not list((user_cache_dir() / "registry").glob("*.tmp"))
    reread = Registry(forge, transport_factory=_boom)
    assert reread.get("fixture-spark").state == "ready"
    assert not any("fixture-spark" in w for w in reread.warnings)


# Secret-shaped values never reach the cache (CLAUDE.md: everything persisted is redacted).

_SECRET = "-".join(("hunter2", "cache", "leak", "probe"))


def _secret_provider(tmp_path: Path, *, in_argv: bool, in_manifest: bool) -> dict[str, Any]:
    manifest = json.loads((PROVIDERS / "fixture-spark.json").read_text(encoding="utf-8"))
    manifest["id"] = "secret-forge"
    if in_manifest:
        manifest["capabilities"][0]["description"] = f"connects with password={_SECRET}"
    folder = tmp_path / (f"token={_SECRET}" if in_argv else "plain")
    folder.mkdir()
    path = folder / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return {"id": "secret-forge", "trust": "local",
            "argv": [sys.executable, str(PROVIDERS / "fixture_forge.py"), str(path)]}


@pytest.mark.parametrize(("in_argv", "in_manifest"), [(True, False), (False, True)],
                         ids=["argv", "manifest"])
def test_secret_shaped_values_are_never_written_to_the_cache(
    tmp_path: Path, in_argv: bool, in_manifest: bool
) -> None:
    forge = _forge(tmp_path, [SPARK_ENTRY,
                              _secret_provider(tmp_path, in_argv=in_argv,
                                               in_manifest=in_manifest)])
    registry = Registry(forge)
    records = {r.entry.id: r for r in registry.refresh()}
    assert records["secret-forge"].state == "ready"  # still usable, just not cached
    assert _cache_files("secret-forge") == []
    assert _cache_files("fixture-spark")  # ordinary providers keep their cache
    leaked = [p.name for p in user_cache_dir().rglob("*")
              if p.is_file() and _SECRET.encode() in p.read_bytes()]
    assert leaked == []
    assert any("secret-forge" in w and "not cached" in w for w in registry.warnings)


def test_stale_cache_with_secret_is_removed(tmp_path: Path) -> None:
    entry = _secret_provider(tmp_path, in_argv=False, in_manifest=True)
    forge = _forge(tmp_path, [entry])
    registry = Registry(forge)
    resolved = next(e for e in registry.entries() if e.id == "secret-forge")
    stale = registry._cache_path(resolved)
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_text(f'{{"left": "{_SECRET}"}}', encoding="utf-8")
    registry.refresh()
    assert not stale.exists()
