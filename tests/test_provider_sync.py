from __future__ import annotations

import sys
from pathlib import Path

from theforge.install.providers import provider_argv, sync
from theforge.registry import Registry

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PROVIDER = ROOT / "tests" / "fixtures" / "providers" / "fixture_forge.py"
FIXTURE_MANIFEST = ROOT / "tests" / "fixtures" / "providers" / "fixture-spark.json"


def _manifest() -> dict[str, object]:
    return {
        "forge_id": "fixture-spark",
        "python": {"executable": sys.executable},
        "provider": {"argv": [sys.executable, str(FIXTURE_PROVIDER), str(FIXTURE_MANIFEST)]},
    }


def _isolated_config(tmp_path: Path, monkeypatch) -> Path:
    config = tmp_path / "config"
    cache = tmp_path / "cache"
    monkeypatch.setenv("THEFORGE_CONFIG_DIR", str(config))
    monkeypatch.setenv("THEFORGE_CACHE_DIR", str(cache))
    return config


def test_sync_writes_managed_provider_and_refreshes(tmp_path: Path, monkeypatch) -> None:
    config = _isolated_config(tmp_path, monkeypatch)
    root = tmp_path / "workspace"
    root.mkdir()

    out = sync([_manifest()], root=root, approved=True)

    assert out["status"] == "completed"
    assert out["verification"]["status"] == "PASS"
    text = (config / "providers.toml").read_text(encoding="utf-8")
    assert "BEGIN THEFORGE MANAGED PROVIDERS" in text
    assert 'trust = "local"' in text
    record = Registry(None, user_dir=config).get("fixture-spark")
    assert record.state == "ready"
    assert record.routable()


def test_sync_preserves_unmanaged_entries_and_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    config = _isolated_config(tmp_path, monkeypatch)
    config.mkdir(parents=True)
    path = config / "providers.toml"
    path.write_text(
        '[[providers]]\nid = "user-forge"\nargv = ["user-cli"]\ntrust = "trusted"\n\n'
        "# BEGIN THEFORGE MANAGED PROVIDERS\n\n"
        '[[providers]]\nid = "fixture-spark"\nargv = ["old"]\ntrust = "local"\n'
        "# END THEFORGE MANAGED PROVIDERS\n",
        encoding="utf-8",
    )

    first = sync([_manifest()], approved=True)
    before = path.read_text(encoding="utf-8")
    second = sync([_manifest()], approved=True)

    assert first["status"] == second["status"] == "completed"
    assert before == path.read_text(encoding="utf-8")
    assert 'id = "user-forge"' in before
    assert before.count('id = "fixture-spark"') == 1


def test_sync_dry_run_and_refusal_do_not_write(tmp_path: Path, monkeypatch) -> None:
    config = _isolated_config(tmp_path, monkeypatch)
    planned = sync([_manifest()], dry_run=True)
    refused = sync([_manifest()], approved=False)

    assert planned["status"] == "planned"
    assert refused["status"] == "refused"
    assert not (config / "providers.toml").exists()


def test_sync_removes_stale_managed_entries_only(tmp_path: Path, monkeypatch) -> None:
    config = _isolated_config(tmp_path, monkeypatch)
    config.mkdir(parents=True)
    path = config / "providers.toml"
    path.write_text(
        '[[providers]]\nid = "user-forge"\nargv = ["user-cli"]\ntrust = "trusted"\n\n'
        "# BEGIN THEFORGE MANAGED PROVIDERS\n\n"
        '[[providers]]\nid = "old-forge"\nargv = ["old"]\ntrust = "local"\n'
        "# END THEFORGE MANAGED PROVIDERS\n",
        encoding="utf-8",
    )

    out = sync([], approved=True)

    assert out["status"] == "completed"
    text = path.read_text(encoding="utf-8")
    assert 'id = "user-forge"' in text
    assert "THEFORGE MANAGED PROVIDERS" not in text
    assert 'id = "old-forge"' not in text


def test_scoped_sync_preserves_other_managed_providers(tmp_path: Path, monkeypatch) -> None:
    config = _isolated_config(tmp_path, monkeypatch)
    config.mkdir(parents=True)
    path = config / "providers.toml"
    path.write_text(
        "# BEGIN THEFORGE MANAGED PROVIDERS\n\n"
        '[[providers]]\nid = "other-forge"\nargv = ["other"]\ntrust = "local"\n'
        "# END THEFORGE MANAGED PROVIDERS\n",
        encoding="utf-8",
    )

    out = sync([_manifest()], forge="fixture-spark", approved=True)

    assert out["status"] == "completed"
    text = path.read_text(encoding="utf-8")
    assert 'id = "fixture-spark"' in text
    assert 'id = "other-forge"' in text


def test_provider_argv_prefers_account_python_variable(monkeypatch) -> None:
    manifest = {
        "forge_id": "spark-forge-aws",
        "environment": {"variables": {"SPARK_FORGE_AWS_PYTHON": sys.executable}},
        "python": {"executable": "C:/missing/python.exe"},
        "provider": {"argv": ["{python}", "-m", "adapter"]},
    }

    argv, error = provider_argv(manifest)

    assert error is None
    assert argv == [sys.executable, "-m", "adapter"]


def test_provider_argv_derives_bundled_adapter_module() -> None:
    argv, error = provider_argv(
        {"forge_id": "spark-forge-aws", "python": {"executable": sys.executable}}
    )

    assert error is None
    assert argv == [sys.executable, "-m", "theforge_sparkforge_aws"]
