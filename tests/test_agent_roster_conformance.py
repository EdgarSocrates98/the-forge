from __future__ import annotations

from pathlib import Path

from theforge.agent_roster import inspect_roster
from theforge.contracts.specialist import AgenticManifest


def _manifest(
    *, agents: list[str] | None = None, coordinators: list[str] | None = None
) -> AgenticManifest:
    return AgenticManifest(
        provider="fixture-forge",
        agents=agents or [],
        coordinators=coordinators or [],
    )


def _write_roster(root: Path, relative: str, *names: str) -> None:
    path = root / relative
    path.mkdir(parents=True)
    for name in names:
        (path / f"{name}.md").write_text(f"# {name}\n", encoding="utf-8")


def test_exact_manifest_and_roster_are_conformant(tmp_path: Path) -> None:
    _write_roster(tmp_path, "agents", "planner", "reviewer")
    report = inspect_roster(_manifest(agents=["planner"], coordinators=["reviewer"]), tmp_path)
    assert report.state == "CONFORMANT"
    assert report.routable is True
    assert report.as_dict()["observed"] == ["planner", "reviewer"]


def test_empty_manifest_against_real_roster_is_drift(tmp_path: Path) -> None:
    _write_roster(tmp_path, "agents", "planner")
    report = inspect_roster(_manifest(), tmp_path)
    assert report.state == "DRIFT"
    assert report.routable is False


def test_missing_declared_agent_is_stale(tmp_path: Path) -> None:
    _write_roster(tmp_path, "agents", "planner")
    report = inspect_roster(_manifest(agents=["planner", "missing"]), tmp_path)
    assert report.state == "STALE"
    assert "missing" in report.declared


def test_absent_roster_preserves_unknown(tmp_path: Path) -> None:
    report = inspect_roster(_manifest(agents=["unverifiable"]), tmp_path)
    assert report.state == "UNKNOWN"
    assert report.routable is False


def test_conflicting_canonical_sources_are_not_merged_as_truth(tmp_path: Path) -> None:
    _write_roster(tmp_path, "agentic/agents", "planner")
    _write_roster(tmp_path, "agents", "reviewer")
    report = inspect_roster(_manifest(agents=["planner", "reviewer"]), tmp_path)
    assert report.state == "CONFLICT"
    assert report.observed == ("planner", "reviewer")


def test_declared_packaged_roster_path_is_evidence_inside_checkout(tmp_path: Path) -> None:
    _write_roster(tmp_path, "src/provider/assets/agents", "planner", "reviewer")
    report = inspect_roster(
        _manifest(agents=["planner", "reviewer"]),
        tmp_path,
        roster_dirs=(Path("agentic/agents"), Path("agents"), Path("src/provider/assets/agents")),
    )
    assert report.state == "CONFORMANT"
    assert report.routable is True
    assert Path(report.sources[-1].path) == Path("src/provider/assets/agents")


def test_roster_path_cannot_escape_checkout(tmp_path: Path) -> None:
    outside = tmp_path.parent / "agents-outside"
    _write_roster(outside, "", "planner")
    report = inspect_roster(
        _manifest(agents=["planner"]), tmp_path, roster_dirs=(Path("..") / outside.name,)
    )
    assert report.state == "UNKNOWN"
