import json
from pathlib import Path
from typing import Any

import pytest
from helpers import SPARK_ENTRY, bad_argv, bad_entry, write_providers

from theforge.errors import UsageError
from theforge.registry import Registry, check_health


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
    assert (forge / "registry" / "fixture-spark.json").is_file()


def test_records_use_cache_without_spawning(tmp_path: Path) -> None:
    forge = make_forge(tmp_path, [SPARK_ENTRY])
    Registry(forge).refresh()

    def boom(argv: object) -> Any:
        raise AssertionError("cache hit must not spawn providers")

    assert all(r.state == "ready" for r in Registry(forge, transport_factory=boom).records())


def test_tampered_cache_is_discarded(tmp_path: Path) -> None:
    forge = make_forge(tmp_path, [SPARK_ENTRY])
    Registry(forge).refresh()
    path = forge / "registry" / "fixture-spark.json"
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
    (forge / "registry" / "fixture-spark.json").write_text("{nope", encoding="utf-8")
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
