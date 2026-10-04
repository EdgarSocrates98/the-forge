"""Forger context phase (context-intelligence-v2 task 4.1): profiles, git and fingerprint
cache wired into ``ask``; one provider executed per run in every profile."""

import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from helpers import bad_entry, make_workspace, write_file
from theforge.context.git import GitState
from theforge.contracts import Response
from theforge.contracts.context import GitSummary
from theforge.contracts.types import BudgetProfile
from theforge.forger import AskRequest, Forger, orchestrator
from theforge.protocol import SubprocessTransport
from theforge.registry import Registry
from theforge.runs import RunStore

LINES10 = "".join(f"line {i:02d}\n" for i in range(1, 11))


class _Recorder:
    """Transport that records every op it forwards to the real subprocess transport."""

    calls: list[tuple[str, str]] = []

    def __init__(self, argv: Sequence[str]) -> None:
        self.argv = list(argv)
        self.inner = SubprocessTransport(argv)

    def call(self, op: str, payload: dict[str, Any], *, timeout: float,
             cwd: Path | None = None, check_protocol: bool = True) -> Response:
        _Recorder.calls.append((op, self.argv[-1]))
        return self.inner.call(op, payload, timeout=timeout, cwd=cwd,
                               check_protocol=check_protocol)


@pytest.fixture
def recorder() -> type[_Recorder]:
    _Recorder.calls = []
    return _Recorder


@pytest.fixture
def git_calls(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    calls: list[Path] = []

    def spy(root: Path, **_: Any) -> GitState:
        calls.append(root)
        return GitState(summary=GitSummary(available=False), changed=frozenset(),
                        limitations=("git: spy unavailable",))

    monkeypatch.setattr(orchestrator, "read_git_state", spy)
    return calls


def _forger(root: Path, transport: Any = SubprocessTransport) -> Forger:
    forge = root / ".forge"
    return Forger(root, Registry(forge), RunStore(forge), transport_factory=transport)


def _executed(recorder: type[_Recorder]) -> list[str]:
    return [pid for op, pid in recorder.calls if op == "execute"]


# --- health fallback by profile (9.1, 9.2) --------------------------------------------------

def _two_providers(root: Path) -> None:
    make_workspace(root, [bad_entry("unhealthy", "bad-a", trust="trusted"),
                          bad_entry("ok", "bad-b", trust="local")])


def test_economy_never_tries_the_fallback(
        tmp_path: Path, recorder: type[_Recorder], git_calls: list[Path]) -> None:
    _two_providers(tmp_path)
    out = _forger(tmp_path, recorder).ask(
        AskRequest(intent="run it", capability="bad.thing", profile="economy"))
    assert out.status == "provider_failure" and out.result is None
    assert out.error is not None and out.error.code == "FORGE-HEALTH-UNAVAILABLE"
    assert [pid for op, pid in recorder.calls if op == "health"] == ["bad-a"]
    assert _executed(recorder) == []
    assert "profile economy: fallback disabled" in out.receipt.limitations
    assert out.decision.fallbacks_used == ["bad-a:FORGE-HEALTH-UNAVAILABLE"]
    assert git_calls == []  # the context phase was never reached


@pytest.mark.parametrize("profile", ["balanced", "max"])
def test_balanced_and_max_try_the_fallback(
        tmp_path: Path, recorder: type[_Recorder], profile: BudgetProfile) -> None:
    _two_providers(tmp_path)
    out = _forger(tmp_path, recorder).ask(
        AskRequest(intent="run it", capability="bad.thing", profile=profile))
    assert out.status == "ok"
    assert out.decision.selected[0].provider == "bad-b"
    assert [pid for op, pid in recorder.calls if op == "health"] == ["bad-a", "bad-b"]
    assert _executed(recorder) == ["bad-b"]
    assert not any("fallback disabled" in note for note in out.receipt.limitations)


def test_economy_healthy_primary_runs_without_limitation(
        tmp_path: Path, recorder: type[_Recorder]) -> None:
    make_workspace(tmp_path, [bad_entry("ok", "bad-a")])
    out = _forger(tmp_path, recorder).ask(
        AskRequest(intent="run it", capability="bad.thing", profile="economy"))
    assert out.status == "ok"
    assert not any("fallback disabled" in note for note in out.receipt.limitations)


@pytest.mark.parametrize("profile", ["economy", "balanced", "max"])
def test_exactly_one_provider_executes_per_run(
        tmp_path: Path, recorder: type[_Recorder], profile: BudgetProfile) -> None:
    make_workspace(tmp_path, [bad_entry("ok", "bad-a", trust="trusted"),
                              bad_entry("ok", "bad-b", trust="local")])
    out = _forger(tmp_path, recorder).ask(
        AskRequest(intent="run it", capability="bad.thing", profile=profile))
    assert out.status == "ok"
    assert _executed(recorder) == ["bad-a"]


# --- git only after policy (3.1) -------------------------------------------------------------

def test_no_route_does_not_run_git(tmp_path: Path, git_calls: list[Path]) -> None:
    make_workspace(tmp_path, [])
    out = _forger(tmp_path).ask(AskRequest(intent="bom dia"))
    assert out.status == "no_route"
    assert git_calls == []


@pytest.mark.parametrize("mode", ["mutating", "no-execute-op"])
def test_refused_before_context_does_not_run_git(
        tmp_path: Path, git_calls: list[Path], mode: str) -> None:
    make_workspace(tmp_path, [bad_entry(mode, "bad-a")])
    out = _forger(tmp_path).ask(AskRequest(intent="run it", capability="bad.thing"))
    assert out.status == "refused"
    assert git_calls == []
    assert RunStore(tmp_path / ".forge").read_optional(out.run_id, "context") is None


def test_routed_run_queries_git_once_and_carries_its_limitations(
        tmp_path: Path, git_calls: list[Path]) -> None:
    make_workspace(tmp_path, [bad_entry("ok", "bad-a")])
    out = _forger(tmp_path).ask(AskRequest(intent="run it", capability="bad.thing"))
    assert out.status == "ok"
    assert git_calls == [tmp_path.resolve()]
    assert "git: spy unavailable" in out.receipt.limitations
    pack = RunStore(tmp_path / ".forge").read(out.run_id, "context")
    assert "git: spy unavailable" in pack["limitations"]
    assert pack["workspace"]["git"]["available"] is False


# --- persisted ContextPack v2 (1.4, 3.4) -----------------------------------------------------

def test_persisted_pack_has_workspace_signals_and_tiers(tmp_path: Path) -> None:
    make_workspace(tmp_path, [bad_entry("excerpts", "bad-a")])
    write_file(tmp_path, "notes.txt", LINES10)
    write_file(tmp_path, "pyproject.toml", "[project]\n")
    out = _forger(tmp_path).ask(AskRequest(intent="run it", capability="bad.thing"))
    assert out.status == "ok"
    pack = RunStore(tmp_path / ".forge").read(out.run_id, "context")
    assert pack["workspace"]["files_scanned"] >= 2
    assert pack["workspace"]["dependency_files"] == ["pyproject.toml"]
    by_path = {f["path"]: f for f in pack["files"]}
    assert by_path["notes.txt"]["signals"] == ["glob:*.txt"]
    assert by_path["notes.txt"]["tier"] == "reference"
    assert by_path["pyproject.toml"]["signals"] == ["dependency_manifest"]
    assert pack["tier_bytes"]["metadata"] == 0
    assert set(pack["tier_bytes"]) == {"metadata", "reference", "excerpt"}
    assert sum(pack["tier_bytes"].values()) == pack["used_bytes"]


# --- excerpts by profile through the full flow (1.6, 9.1-9.3) --------------------------------

@pytest.mark.parametrize(("profile", "excerpt"), [
    ("economy", False), ("balanced", True), ("max", True)])
def test_capability_declaring_excerpts_gets_them_except_in_economy(
        tmp_path: Path, profile: BudgetProfile, excerpt: bool) -> None:
    make_workspace(tmp_path, [bad_entry("excerpts", "bad-a")])
    write_file(tmp_path, "notes.txt", LINES10)
    out = _forger(tmp_path).ask(AskRequest(intent="run it notes.txt:2-3",
                                           capability="bad.thing", profile=profile))
    assert out.status == "ok"
    pack = RunStore(tmp_path / ".forge").read(out.run_id, "context")
    tiers = [f["tier"] for f in pack["files"]]
    if excerpt:
        assert tiers == ["excerpt"]
        assert pack["files"][0]["lines"] == {"start": 2, "end": 3}
        assert pack["files"][0]["bytes"] == 16
    else:
        assert "excerpt" not in tiers and tiers == ["reference"]
        assert "excerpt" not in pack["tier_bytes"]


def test_capability_without_excerpts_never_gets_them(tmp_path: Path) -> None:
    make_workspace(tmp_path, [bad_entry("ok", "bad-a")])
    write_file(tmp_path, "notes.txt", LINES10)
    out = _forger(tmp_path).ask(AskRequest(intent="run it notes.txt:2-3",
                                           capability="bad.thing", profile="max"))
    pack = RunStore(tmp_path / ".forge").read(out.run_id, "context")
    assert [f["tier"] for f in pack["files"]] == ["reference"]


# --- fingerprint cache (5.5) -----------------------------------------------------------------

def test_fingerprint_cache_is_saved_outside_the_workspace(tmp_path: Path) -> None:
    make_workspace(tmp_path, [bad_entry("excerpts", "bad-a")])
    write_file(tmp_path, "notes.txt", LINES10)
    out = _forger(tmp_path).ask(AskRequest(intent="run it", capability="bad.thing"))
    assert out.status == "ok"
    cache = Path(os.environ["THEFORGE_CACHE_DIR"]) / "context"
    assert len(list(cache.glob("*.json"))) == 1
    assert not any(note.startswith("fingerprint cache") for note in out.receipt.limitations)


def test_fingerprint_cache_warnings_become_run_limitations(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("THEFORGE_CACHE_DIR", str(tmp_path / "cache"))  # inside the workspace
    make_workspace(tmp_path, [bad_entry("excerpts", "bad-a")])
    write_file(tmp_path, "notes.txt", LINES10)
    out = _forger(tmp_path).ask(AskRequest(intent="run it", capability="bad.thing"))
    assert out.status == "ok"
    assert any(note.startswith("fingerprint cache disabled")
               for note in out.receipt.limitations)
    assert not (tmp_path / "cache" / "context").exists()  # nothing written inside it
