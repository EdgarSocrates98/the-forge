"""Project intelligence: fingerprinted incremental memory + decision memory.

Wave I: ``.forge/intel/project.json`` caches the workspace descriptor behind
content fingerprints — never silently stale (I2), refreshed section-wise (I1);
``.forge/intel/decisions.json`` remembers only the reusable decisions (I3).
"""

import json
import shutil
from pathlib import Path

import pytest

from helpers import SPARK_ENTRY, make_workspace, write_file
from theforge.context.scan import scan_workspace
from theforge.contracts import (
    ContractError,
    DecisionMemory,
    Producer,
    ProjectIntel,
    RememberedDecision,
    from_dict,
    to_dict,
)
from theforge.forger.orchestrator import AskRequest, Forger
from theforge.forger.plan_executor import PlanCommand, PlanExecutor
from theforge.intel import (
    compute_fingerprints,
    freshness,
    load_decisions,
    load_intel,
    record_decision,
    refresh_intel,
)
from theforge.registry import Registry
from theforge.runs import RunStore
from theforge.workspace.describe import describe_workspace, discover_repositories

P = Producer(id="theforge", version="0")
INTEL = Path(".forge") / "intel"


def _records(root: Path) -> list:
    return list(Registry(root / ".forge").records())


def _rows(records: list) -> list[tuple[str, str, str | None]]:
    return [(r.entry.id, r.state, r.manifest_sha256) for r in records]


def _workspace(root: Path) -> None:
    make_workspace(root, [SPARK_ENTRY])
    (root / ".git").mkdir()  # a repository root: its dep manifests are fingerprinted
    write_file(root, "jobs_glue.py", "x = 1")
    write_file(root, "requirements.txt", "pyspark==3.5.0\n")


def _refresh(root: Path):
    scan = scan_workspace(root, [])
    return refresh_intel(root, scan, _records(root))


# --- fingerprints + freshness (I2) -------------------------------------------------


def _repos(root: Path) -> list[str]:
    return discover_repositories(root)


def test_fingerprints_are_deterministic(tmp_path: Path) -> None:
    _workspace(tmp_path)
    records = _rows(_records(tmp_path))
    scan = scan_workspace(tmp_path, [])
    repos = _repos(tmp_path)
    a = compute_fingerprints(tmp_path, scan.files, repos, records)
    b = compute_fingerprints(tmp_path, scan.files, repos, records)
    assert a == b


def test_freshness_current_then_stale_on_changed_inputs(tmp_path: Path) -> None:
    _workspace(tmp_path)
    intel, notes = _refresh(tmp_path)
    scan = scan_workspace(tmp_path, [])
    records = _rows(_records(tmp_path))
    validity, stale = freshness(intel, scan.files, _repos(tmp_path), records)
    assert validity == "current" and stale == []
    # A changed dependency manifest is observable: depfiles fingerprint moves.
    write_file(tmp_path, "requirements.txt", "pyspark==3.5.0\npandas==2.0\n")
    validity, stale = freshness(intel, scan_workspace(tmp_path, []).files,
                                _repos(tmp_path), records)
    assert validity == "stale" and "technologies" in stale


def test_freshness_never_silent_on_new_files(tmp_path: Path) -> None:
    _workspace(tmp_path)
    intel, _ = _refresh(tmp_path)
    write_file(tmp_path, "new_job.py", "y = 2")
    validity, stale = freshness(
        intel, scan_workspace(tmp_path, []).files, _repos(tmp_path),
        _rows(_records(tmp_path)))
    assert validity == "stale"  # files_sha moved — the snapshot is not "current"


def test_malformed_intel_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / INTEL / "project.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    intel, warning = load_intel(tmp_path)
    assert intel is None and warning is not None and "intel:" in warning


def test_absent_intel_is_no_memory(tmp_path: Path) -> None:
    intel, warning = load_intel(tmp_path)
    assert intel is None and warning is None


# --- incremental refresh (I1) -------------------------------------------------------


def test_refresh_persists_and_reuses_unchanged_sections(tmp_path: Path) -> None:
    _workspace(tmp_path)
    first, _ = _refresh(tmp_path)
    assert (tmp_path / INTEL / "project.json").is_file()
    assert first.reused == []  # first analysis computes everything
    second, notes = _refresh(tmp_path)
    # Same inputs: technologies and dependency_files come from the snapshot.
    assert "technologies" in second.reused
    assert "dependency_files" in second.reused
    assert second.descriptor.technologies == first.descriptor.technologies
    assert second.created_at == first.created_at  # the snapshot line is kept
    assert notes == []  # a clean reuse has nothing to report


def test_refresh_recomputes_only_stale_sections(tmp_path: Path) -> None:
    _workspace(tmp_path)
    first, _ = _refresh(tmp_path)
    write_file(tmp_path, "requirements.txt", "pyspark==3.5.0\npandas==2.0\n")
    second, _ = _refresh(tmp_path)
    # depfiles_sha moved: technologies recomputed, no longer marked reused.
    assert second.reused == []


def test_refresh_matches_plain_describe(tmp_path: Path) -> None:
    """The incremental path must produce the same descriptor as a full describe."""
    _workspace(tmp_path)
    scan = scan_workspace(tmp_path, [])
    intel, _ = refresh_intel(tmp_path, scan, _records(tmp_path))
    plain = describe_workspace(tmp_path, _records(tmp_path), scan)
    assert intel.descriptor.repositories == plain.repositories
    assert intel.descriptor.technologies == plain.technologies
    assert intel.descriptor.relations == plain.relations
    assert intel.descriptor.paths == plain.paths


def test_refresh_reused_still_matches_plain(tmp_path: Path) -> None:
    """Reused sections stay byte-identical to a fresh full describe."""
    _workspace(tmp_path)
    _refresh(tmp_path)
    second, _ = _refresh(tmp_path)
    assert second.reused  # something was reused
    plain = describe_workspace(tmp_path, _records(tmp_path), scan_workspace(tmp_path, []))
    assert second.descriptor.technologies == plain.technologies
    assert {r.path: r.dependency_files for r in second.descriptor.repositories} == \
        {r.path: r.dependency_files for r in plain.repositories}


def test_snapshot_from_another_root_is_not_reused(tmp_path: Path) -> None:
    """A moved workspace cannot inherit memory: even byte-identical content,
    a snapshot recorded for a different root is a first refresh here."""
    original = tmp_path / "original"
    moved = tmp_path / "moved"
    _workspace(original)
    _refresh(original)
    shutil.copytree(original, moved)  # .forge included, as a move would carry it
    second, notes = _refresh(moved)
    assert second.reused == []
    assert "snapshot root differs" in " ".join(notes)


# --- decision memory (I3) ------------------------------------------------------------


def test_record_decision_creates_and_dedupes(tmp_path: Path) -> None:
    assert record_decision(tmp_path, "routing", "spark.performance",
                           "fixture-spark", "matched 2 signal types", "run-1") is None
    again = record_decision(tmp_path, "routing", "spark.performance",
                            "fixture-spark", "matched 2 signal types", "run-2")
    assert again is None
    memory, warning = load_decisions(tmp_path)
    assert warning is None and memory is not None
    (entry,) = memory.entries  # same identity: reaffirmed, not duplicated
    assert entry.kind == "routing" and entry.choice == "fixture-spark"
    assert entry.corroborations == 2
    assert entry.runs == ["run-1", "run-2"]


def test_decision_distinct_choice_is_a_new_entry(tmp_path: Path) -> None:
    record_decision(tmp_path, "routing", "cap.x", "prov-a", "r1", "run-1")
    record_decision(tmp_path, "routing", "cap.x", "prov-b", "r2", "run-2")
    memory, _ = load_decisions(tmp_path)
    assert memory is not None and len(memory.entries) == 2


def test_decision_memory_bounded(tmp_path: Path) -> None:
    for i in range(5):
        record_decision(tmp_path, "pattern", "plan", f"pattern-{i}", "b", f"r{i}")
    memory, _ = load_decisions(tmp_path)
    assert memory is not None and len(memory.entries) == 5


def test_malformed_decisions_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / INTEL / "decisions.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"schema": "theforge/DecisionMemory/v1", "entries": ['
                    '{"id": "x", "id2": "y"}]}', encoding="utf-8")
    memory, warning = load_decisions(tmp_path)
    assert memory is None and warning is not None


def test_decision_contract_rejects_duplicates() -> None:
    entry = RememberedDecision(id="x", kind="routing", subject="c", choice="p",
                               basis="b", created_at="t", updated_at="t")
    with pytest.raises(ContractError):
        DecisionMemory(producer=P, created_at="t", entries=[entry, entry])


def test_intel_roundtrips_strict(tmp_path: Path) -> None:
    _workspace(tmp_path)
    intel, _ = _refresh(tmp_path)
    assert from_dict(ProjectIntel,
                     json.loads(json.dumps(to_dict(intel))), strict=True) == intel


# --- e2e -----------------------------------------------------------------------------


def _forger(root: Path) -> Forger:
    forge = root / ".forge"
    return Forger(root, Registry(forge), RunStore(forge))


def test_plan_run_writes_project_intel(tmp_path: Path) -> None:
    forge = make_workspace(tmp_path, [SPARK_ENTRY])
    store = RunStore(forge)
    executor = PlanExecutor(Forger(tmp_path, Registry(forge), store))
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps({
        "task_id": "from-file", "pattern": "pipeline", "source": "file",
        "profile": "balanced",
        "nodes": [{"id": "n1", "role": "standalone", "provider": "fixture-spark",
                   "capability": "spark.performance", "action": "diagnose"}],
    }), encoding="utf-8")
    out = executor.run(PlanCommand(intent="spec", profile="balanced",
                                   plan_file=plan_file, execute=True))
    assert out.result is not None
    intel, warning = load_intel(tmp_path)
    assert warning is None and intel is not None
    assert intel.capability_graph_sha is not None  # the run's graph, referenced
    # The run's descriptor artifact is the same descriptor the intel cached.
    run_dir = tmp_path / ".forge" / "runs" / out.run_id
    descriptor = json.loads(
        (run_dir / "workspace-descriptor.json").read_text(encoding="utf-8"))
    assert to_dict(intel.descriptor) == descriptor


def test_ask_run_records_routing_decision(tmp_path: Path) -> None:
    make_workspace(tmp_path, [SPARK_ENTRY])
    write_file(tmp_path, "jobs_glue.py", "x = 1")
    out = _forger(tmp_path).ask(
        AskRequest(intent="analise esse glue job lento", profile="balanced"))
    assert out.status == "ok"
    memory, warning = load_decisions(tmp_path)
    assert warning is None and memory is not None
    routing = [e for e in memory.entries if e.kind == "routing"]
    assert len(routing) == 1
    assert routing[0].subject == "spark.performance"
    assert routing[0].choice == "fixture-spark"
    assert out.run_id in routing[0].runs


def test_plan_run_records_pattern_decision(tmp_path: Path) -> None:
    forge = make_workspace(tmp_path, [SPARK_ENTRY])
    store = RunStore(forge)
    executor = PlanExecutor(Forger(tmp_path, Registry(forge), store))
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps({
        "task_id": "from-file", "pattern": "pipeline", "source": "file",
        "profile": "balanced",
        "nodes": [{"id": "n1", "role": "standalone", "provider": "fixture-spark",
                   "capability": "spark.performance", "action": "diagnose"}],
    }), encoding="utf-8")
    out = executor.run(PlanCommand(intent="spec", profile="balanced",
                                   plan_file=plan_file, execute=True))
    assert out.result is not None
    memory, _ = load_decisions(tmp_path)
    assert memory is not None
    patterns = [e for e in memory.entries if e.kind == "pattern"]
    assert len(patterns) == 1 and patterns[0].choice == "pipeline"
    # the node's own routing decision was remembered by its child ask run
    assert any(e.kind == "routing" for e in memory.entries)
