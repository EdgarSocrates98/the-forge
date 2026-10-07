"""Cycle 3.1 Phases 50-52: context-economy benchmark shape, isolation and
terminology. The heavy measurement never runs here; the smoke test uses a
tiny workspace and the replay adapters, offline."""

import importlib
import json
from pathlib import Path
from types import ModuleType

import pytest

BENCH = Path(__file__).parents[1] / "scripts" / "bench"


@pytest.fixture
def economy(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.syspath_prepend(str(BENCH))
    return importlib.import_module("run_context_economy")


# --- report shape ----------------------------------------------------------------------------


def test_report_schema_and_provider_mode(economy: ModuleType) -> None:
    arms = {name: {key: 0 for key in economy.METRICS} for name in economy.ARMS}
    report = economy.build_report(arms, economy.collect_origin())
    assert report["schema"] == "theforge-economy-bench/v1"
    assert report["provider_mode"] == "specialist-replay"
    assert set(report["arms"]) == {"direct", "mesh"}
    assert report["unmeasurable"] == ["model_calls", "provider_tokens"]


def test_every_observable_metric_is_compared(economy: ModuleType) -> None:
    arms = {"direct": {key: 10.0 for key in economy.METRICS},
            "mesh": {key: 4.0 for key in economy.METRICS}}
    report = economy.build_report(arms, {})
    assert set(report["comparison"]) == set(economy.METRICS)
    entry = report["comparison"]["context_bytes"]
    assert entry == {"direct": 10.0, "mesh": 4.0, "mesh_minus_direct": -6.0}


def test_mesh_arm_is_observe_then_bounded_engineers(economy: ModuleType) -> None:
    """The mesh arm is one whole-workspace observer plus domain-bounded
    consumers; the direct arm rereads the whole workspace per specialist."""
    mesh = {n["id"]: n for n in economy.MESH_NODES}
    assert mesh["n1"]["provider"] == "forge-doctor-data"
    assert mesh["n1"]["targets"] == ["."]
    for nid in ("n2", "n3"):
        node = mesh[nid]
        assert node["role"] == "consumer" and node["inputs"] == ["n1"]
        assert node["targets"] != ["."]
    assert all(n["targets"] == ["."] for n in economy.DIRECT_NODES)


# --- workspace and plan isolation -------------------------------------------------------------


def test_seed_workspace_is_deterministic(economy: ModuleType,
                                          tmp_path: Path) -> None:
    economy._seed_workspace(tmp_path / "a")
    economy._seed_workspace(tmp_path / "b")
    snap = {p.relative_to(tmp_path / "a").as_posix(): p.read_bytes()
            for p in sorted((tmp_path / "a").rglob("*")) if p.is_file()}
    other = {p.relative_to(tmp_path / "b").as_posix(): p.read_bytes()
             for p in sorted((tmp_path / "b").rglob("*")) if p.is_file()}
    assert snap == other
    assert len(snap) == economy.WORKSPACE_FILES + len(economy.DOMAIN_FILES)
    assert "jobs/orders_glue_job.py" in snap and "api/openapi.yaml" in snap


def test_plan_file_lives_outside_the_workspace(economy: ModuleType,
                                               tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    economy._seed_workspace(workspace)
    plan = economy._write_plan(tmp_path / "ws-plan.json", economy.DIRECT_NODES)
    data = json.loads(plan.read_text("utf-8"))
    assert not plan.is_relative_to(workspace)
    assert data["source"] == "file" and len(data["nodes"]) == len(economy.DIRECT_NODES)


# --- smoke: both arms end to end (replay adapters, offline) ------------------------------------


def test_both_arms_run_end_to_end(economy: ModuleType, tmp_path: Path,
                                  monkeypatch: pytest.MonkeyPatch) -> None:
    for module in ("theforge_doctordata", "theforge_doctorapi",
                   "theforge_sparkforge_aws", "theforge_apiforge"):
        pytest.importorskip(module)
    monkeypatch.setattr(economy, "WORKSPACE_FILES", 24)
    monkeypatch.setattr(economy, "DEFAULT_RUNS", 1)

    config_dir, cache_dir = tmp_path / "config", tmp_path / "cache"
    with economy._isolated_env(config_dir, cache_dir):
        economy._write_providers(config_dir)
        arms = {name: economy.run_arm(tmp_path, name, nodes, 1)
                for name, nodes in economy.ARMS.items()}

    direct, mesh = arms["direct"], arms["mesh"]
    # The mesh premise: the observer scans once, the engineers rescan nothing.
    assert direct["files_scanned"] > mesh["files_scanned"]
    downstream = [r for r in mesh["runs"] if r["provider"] != "forge-doctor-data"]
    assert downstream and all(
        r["files_scanned"] == r["context_files"] for r in downstream)
    assert mesh["provider_calls"] == direct["provider_calls"] + 1
    assert mesh["handoff_bytes"] > 0 and direct["handoff_bytes"] == 0
    # Unmeasurable dimensions stay explicit nulls, never zero.
    for arm in arms.values():
        assert arm["model_calls"] is None and arm["provider_tokens"] is None
