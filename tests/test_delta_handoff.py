"""Delta handoff (Phase 49): ``delta/v1`` providers receive a ``delta`` hint on the
``execute`` payload only on subsequent runs over the same workspace — the fingerprint
cache is the prior observation. First runs, delta-less providers and disabled caches
never see the field; a hint is never fabricated.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from helpers import SPARK_ENTRY, fixture_argv, make_workspace, write_file
from theforge.context.fingerprints import FingerprintStore
from theforge.contracts import ContractError, DeltaRequest
from theforge.forger import AskRequest, Forger
from theforge.protocol import SubprocessTransport
from theforge.registry import Registry
from theforge.runs import RunStore

DELTA_ENTRY = {
    "id": "fixture-delta",
    "argv": fixture_argv("fixture_forge.py",
                         str(Path(__file__).parent / "fixtures" / "providers"
                             / "fixture-delta.json")),
    "trust": "local",
}

WORKSPACE = {"jobs/orders_glue_job.py": "df = spark.read.parquet('s3://b/orders')\n",
             "requirements.txt": "pyspark==3.5.1\n"}


def _workspace(root: Path) -> None:
    for rel, text in WORKSPACE.items():
        write_file(root, rel, text)


def _forger(root: Path) -> Forger:
    forge = root / ".forge"
    return Forger(root, Registry(forge), RunStore(forge),
                  transport_factory=SubprocessTransport)


def _run(root: Path) -> Any:
    out = _forger(root).ask(AskRequest(intent="diagnose the glue job",
                                       capability="spark.performance"))
    assert out.status == "ok", out.error
    return out


def _delta_evidence(root: Path, run_id: str) -> dict[str, Any] | None:
    result = RunStore(root / ".forge").read(run_id, "result")
    for item in result.get("evidence") or []:
        if item.get("id") == "delta":
            return item
    return None


# --- contract ---------------------------------------------------------------------------------

def test_delta_request_rejects_non_relative_paths() -> None:
    for bad in ("../escape.txt", "/abs/path.py", "C:\\\\win.py", "", "a\\\\b.py"):
        with pytest.raises(ContractError):
            DeltaRequest(changed_files=[bad])


def test_delta_request_bounds_and_default_baseline() -> None:
    DeltaRequest()  # empty hint is a legal value
    DeltaRequest(changed_files=["f.py"] * 256)
    with pytest.raises(ContractError):
        DeltaRequest(changed_files=["f.py"] * 257)
    with pytest.raises(ContractError):
        DeltaRequest(baseline_ref="x" * 257)


# --- fingerprint changed surface --------------------------------------------------------------

def test_changed_surface_is_none_on_a_cold_cache(tmp_path: Path) -> None:
    store = FingerprintStore(tmp_path)
    assert store.changed_surface({"a.py": "0" * 64}, {"a.py"}) is None


def test_changed_surface_buckets_added_modified_removed(tmp_path: Path) -> None:
    # THEFORGE_CACHE_DIR points outside tmp_path (autouse isolation fixture).
    write_file(tmp_path, "keep.py", "same\n")
    write_file(tmp_path, "gone.py", "old\n")
    write_file(tmp_path, "mod.py", "old\n")
    first = FingerprintStore(tmp_path)
    for rel in ("keep.py", "gone.py", "mod.py"):
        got = first.file(rel, tmp_path / rel)
        assert got is not None
    first.save()

    (tmp_path / "gone.py").unlink()
    write_file(tmp_path, "mod.py", "new content\n")
    write_file(tmp_path, "new.py", "new\n")
    second = FingerprintStore(tmp_path)
    current: dict[str, str] = {}
    for rel in ("keep.py", "mod.py", "new.py"):
        fp = second.file(rel, tmp_path / rel)
        assert fp is not None
        current[rel] = fp.sha256
    present = {"keep.py", "mod.py", "new.py"}
    assert second.changed_surface(current, present) == (["mod.py", "new.py"],
                                                        ["gone.py"])


# --- execute payload --------------------------------------------------------------------------

def test_first_run_sends_no_delta_then_second_run_does(tmp_path: Path) -> None:
    make_workspace(tmp_path, [DELTA_ENTRY])
    _workspace(tmp_path)
    first = _run(tmp_path)
    assert _delta_evidence(tmp_path, first.run_id) is None  # cold cache: no baseline

    write_file(tmp_path, "jobs/orders_glue_job.py",
               "df = spark.read.parquet('s3://b/orders2')\n")
    write_file(tmp_path, "jobs/new_job.py", "df = spark.read.json('s3://b/n')\n")
    second = _run(tmp_path)
    delta = _delta_evidence(tmp_path, second.run_id)
    assert delta is not None, "subsequent run must carry the delta hint"
    assert "jobs/new_job.py" in delta["claim"] or "new_job" in delta["claim"]


def test_unchanged_second_run_sends_an_empty_delta(tmp_path: Path) -> None:
    make_workspace(tmp_path, [DELTA_ENTRY])
    _workspace(tmp_path)
    _run(tmp_path)
    second = _run(tmp_path)
    delta = _delta_evidence(tmp_path, second.run_id)
    assert delta is not None
    assert "changed=0" in delta["claim"]


def test_provider_without_delta_feature_never_receives_a_hint(tmp_path: Path) -> None:
    make_workspace(tmp_path, [SPARK_ENTRY])
    _workspace(tmp_path)
    _run(tmp_path)
    write_file(tmp_path, "jobs/orders_glue_job.py", "df = spark.read.table('t')\n")
    second = _run(tmp_path)
    assert _delta_evidence(tmp_path, second.run_id) is None


def test_disabled_cache_means_no_delta(tmp_path: Path, monkeypatch) -> None:
    make_workspace(tmp_path, [DELTA_ENTRY])
    monkeypatch.setenv("THEFORGE_CACHE_DIR", str(tmp_path / "inside-ws-cache"))
    _workspace(tmp_path)
    _run(tmp_path)
    write_file(tmp_path, "jobs/new_job.py", "x = 1\n")
    second = _run(tmp_path)
    # The cache dir inside the workspace is refused: no prior state, no delta.
    assert _delta_evidence(tmp_path, second.run_id) is None


def test_fixture_manifest_declares_delta() -> None:
    manifest = json.loads((Path(__file__).parent / "fixtures" / "providers"
                           / "fixture-delta.json").read_text(encoding="utf-8"))
    assert manifest["features"] == ["delta/v1"]
