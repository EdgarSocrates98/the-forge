"""Forger context phase (context-intelligence-v2 task 4.1): profiles, git and fingerprint
cache wired into ``ask``; one provider executed per run in every profile."""

import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from helpers import bad_entry, make_workspace, write_file
from theforge.context.fingerprints import FingerprintStore
from theforge.context.git import GitState
from theforge.contracts import ExecutionReceipt, Metric, Response
from theforge.contracts.codes import Codes
from theforge.contracts.context import GitSummary
from theforge.contracts.integrity import validate_receipt
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


# --- context negotiation (8.1, 8.3-8.6; task 4.2) --------------------------------------------

REQUESTED = "req.txt"  # the file bad_forge's context-request modes ask for


@pytest.fixture
def no_git(monkeypatch: pytest.MonkeyPatch) -> None:
    def stub(root: Path, **_: Any) -> GitState:
        return GitState(summary=GitSummary(available=False), changed=frozenset(),
                        limitations=())

    monkeypatch.setattr(orchestrator, "read_git_state", stub)


def _negotiate(root: Path, mode: str, profile: BudgetProfile,
               recorder: type[_Recorder]) -> Any:
    make_workspace(root, [bad_entry(mode, "bad-a")])
    write_file(root, REQUESTED, LINES10)
    return _forger(root, recorder).ask(
        AskRequest(intent="run it", capability="bad.thing", profile=profile))


def _assert_receipt_consistent(root: Path, run_id: str) -> ExecutionReceipt:
    store = RunStore(root / ".forge")
    receipt = store.read_contract(run_id, "receipt", ExecutionReceipt)
    validate_receipt(receipt, result_sha256=store.persisted_sha256(run_id, "result"))
    rounds = [sha for name in ("context-r1", "context-r2")
              if (sha := store.persisted_sha256(run_id, name)) is not None]
    assert receipt.inputs.context_round_sha256 == rounds
    return receipt


def test_valid_request_in_balanced_extends_the_pack_and_ends_ok(
        tmp_path: Path, recorder: type[_Recorder], no_git: None) -> None:
    out = _negotiate(tmp_path, "context-request", "balanced", recorder)
    assert out.status == "ok", out.error
    assert out.result is not None and out.result.context_request is None
    assert _executed(recorder) == ["bad-a", "bad-a"]
    store = RunStore(tmp_path / ".forge")
    initial = store.read(out.run_id, "context")
    round1 = store.read(out.run_id, "context-r1")
    assert initial["round"] == 0 and round1["round"] == 1
    requested = [f for f in round1["files"] if f["tier"] == "requested"]
    assert [f["path"] for f in requested] == [REQUESTED]
    assert store.read_optional(out.run_id, "context-r2") is None
    persisted = store.read(out.run_id, "result")
    assert persisted.get("context_request") is None
    assert persisted["metrics"]["context_bytes"]["value"] == round1["used_bytes"]
    receipt = _assert_receipt_consistent(tmp_path, out.run_id)
    assert len(receipt.inputs.context_round_sha256) == 1


def test_valid_request_in_economy_fails_by_limit(
        tmp_path: Path, recorder: type[_Recorder], no_git: None) -> None:
    out = _negotiate(tmp_path, "context-request", "economy", recorder)
    assert out.status == "provider_failure" and out.result is None
    assert out.error is not None and out.error.code == Codes.CONTEXT_REQUEST_LIMIT
    assert _executed(recorder) == ["bad-a"]
    store = RunStore(tmp_path / ".forge")
    assert store.read_optional(out.run_id, "result") is None
    assert store.read_optional(out.run_id, "context-r1") is None
    assert _assert_receipt_consistent(tmp_path, out.run_id).result_sha256 is None


@pytest.mark.parametrize(("profile", "rounds"), [("balanced", 1), ("max", 2)])
def test_request_loop_fails_by_limit_after_the_profile_rounds(
        tmp_path: Path, recorder: type[_Recorder], no_git: None,
        profile: BudgetProfile, rounds: int) -> None:
    out = _negotiate(tmp_path, "context-request-loop", profile, recorder)
    assert out.status == "provider_failure" and out.result is None
    assert out.error is not None and out.error.code == Codes.CONTEXT_REQUEST_LIMIT
    assert _executed(recorder) == ["bad-a"] * (rounds + 1)
    store = RunStore(tmp_path / ".forge")
    assert store.read_optional(out.run_id, "result") is None
    for n in (1, 2):
        assert (store.read_optional(out.run_id, f"context-r{n}") is not None) == (n <= rounds)
    receipt = _assert_receipt_consistent(tmp_path, out.run_id)
    assert len(receipt.inputs.context_round_sha256) == rounds
    assert receipt.status == "provider_failure" and receipt.result_sha256 is None


@pytest.mark.parametrize(("mode", "code"), [
    ("context-request-undeclared", Codes.CONTEXT_REQUEST_UNSUPPORTED),
    ("context-request-invalid", Codes.CONTEXT_REQUEST_INVALID),
])
@pytest.mark.parametrize("profile", ["balanced", "max"])
def test_undeclared_or_invalid_request_fails_with_its_code(
        tmp_path: Path, recorder: type[_Recorder], no_git: None,
        mode: str, code: str, profile: BudgetProfile) -> None:
    out = _negotiate(tmp_path, mode, profile, recorder)
    assert out.status == "provider_failure" and out.result is None
    assert out.error is not None and out.error.code == code
    assert _executed(recorder) == ["bad-a"]
    store = RunStore(tmp_path / ".forge")
    assert store.read_optional(out.run_id, "result") is None
    assert store.read_optional(out.run_id, "context-r1") is None
    assert _assert_receipt_consistent(tmp_path, out.run_id).inputs.context_round_sha256 == []


def test_negotiation_saves_the_fingerprint_cache_once(
        tmp_path: Path, recorder: type[_Recorder], no_git: None,
        monkeypatch: pytest.MonkeyPatch) -> None:
    saves: list[int] = []
    real_save = FingerprintStore.save

    def counting(self: FingerprintStore) -> None:
        saves.append(1)
        real_save(self)

    monkeypatch.setattr(FingerprintStore, "save", counting)
    out = _negotiate(tmp_path, "context-request", "max", recorder)
    assert out.status == "ok"
    assert saves == [1]


# --- post-execution drift and honest tokens (6.1-6.3, 6.7, 7.2-7.4, 9.1-9.3; task 4.3) -------

DRIFTED = "notes.txt"  # the *.txt file bad_forge's drift-report/mutate-context modes cover


def _run_mode(root: Path, mode: str, profile: BudgetProfile) -> Any:
    make_workspace(root, [bad_entry(mode, "bad-a")])
    write_file(root, DRIFTED, LINES10)
    return _forger(root).ask(AskRequest(intent="run it", capability="bad.thing",
                                        profile=profile))


@pytest.mark.parametrize("profile", ["economy", "balanced", "max"])
def test_reported_drift_ends_partial_with_demoted_evidence(
        tmp_path: Path, no_git: None, profile: BudgetProfile) -> None:
    out = _run_mode(tmp_path, "drift-report", profile)
    assert out.status == "partial", out.error
    assert out.result is not None and out.result.status == "partial"
    [evidence] = out.result.evidence
    assert evidence.epistemic == "unresolved"
    assert "context-drift: was confirmed" in evidence.limitations
    assert f"context-drift: {DRIFTED}" in out.result.limitations
    store = RunStore(tmp_path / ".forge")
    persisted = store.read(out.run_id, "result")
    assert persisted["status"] == "partial"
    assert persisted["evidence"][0]["epistemic"] == "unresolved"
    assert f"context-drift: {DRIFTED}" in persisted["limitations"]
    receipt = _assert_receipt_consistent(tmp_path, out.run_id)
    assert receipt.status == "partial" and receipt.result_sha256 is not None
    assert f"context-drift: {DRIFTED}" in receipt.limitations


@pytest.mark.parametrize(("profile", "detected"), [
    ("economy", False), ("balanced", True), ("max", True)])
def test_change_during_execution_is_detected_by_reverification(
        tmp_path: Path, no_git: None, profile: BudgetProfile, detected: bool) -> None:
    out = _run_mode(tmp_path, "mutate-context", profile)
    assert (tmp_path / DRIFTED).read_text(encoding="utf-8") != LINES10  # it did change
    assert out.result is not None
    receipt = _assert_receipt_consistent(tmp_path, out.run_id)
    drift_note = f"context-drift: {DRIFTED}"
    if detected:
        assert out.status == "partial" and receipt.status == "partial"
        assert out.result.evidence[0].epistemic == "unresolved"
        assert drift_note in out.result.limitations and drift_note in receipt.limitations
        assert "context-not-reverified" not in receipt.limitations
    else:  # economy: minimal verification, recorded as a limitation (9.1)
        assert out.status == "ok" and receipt.status == "ok"
        assert out.result.evidence[0].epistemic == "confirmed"
        assert drift_note not in receipt.limitations
        assert "context-not-reverified" in receipt.limitations


@pytest.mark.parametrize("profile", ["balanced", "max"])
def test_unchanged_context_is_reverified_without_drift(
        tmp_path: Path, no_git: None, profile: BudgetProfile) -> None:
    out = _run_mode(tmp_path, "ok", profile)
    assert out.status == "ok"
    assert not any(n.startswith("context-") for n in out.receipt.limitations)


def test_provider_measured_tokens_are_persisted_unchanged(
        tmp_path: Path, no_git: None) -> None:
    out = _run_mode(tmp_path, "tokens-measured", "balanced")
    assert out.status == "ok", out.error
    store = RunStore(tmp_path / ".forge")
    metrics = store.read(out.run_id, "result")["metrics"]
    assert metrics["tokens"] == {"value": 1234, "kind": "measured"}
    # duration and context bytes stay the core's own measurements, never the provider's
    pack = store.read(out.run_id, "context")
    assert metrics["context_bytes"] == {"value": pack["used_bytes"], "kind": "measured"}
    assert metrics["duration_ms"]["kind"] == "measured"
    assert metrics["duration_ms"]["value"] != 999999


@pytest.mark.parametrize(("reported", "kept"), [
    (Metric(value=1234.0, kind="measured"), Metric(value=1234.0, kind="measured")),
    (Metric(value=88.0, kind="estimated"), Metric(value=88.0, kind="estimated")),
    (Metric(value=None, kind="unknown"), Metric()),
    (Metric(value=5.0, kind="unknown"), Metric()),       # a value without a kind is not kept
    (Metric(value=None, kind="measured"), Metric()),     # a kind without a value is not kept
    (Metric(value=-1.0, kind="measured"), Metric()),     # a negative count is not a count
])
def test_honest_tokens_keeps_only_reported_counts(reported: Metric, kept: Metric) -> None:
    assert orchestrator.honest_tokens(reported) == kept


def test_tokens_without_a_provider_count_are_unknown(tmp_path: Path, no_git: None) -> None:
    out = _run_mode(tmp_path, "ok", "balanced")
    tokens = RunStore(tmp_path / ".forge").read(out.run_id, "result")["metrics"]["tokens"]
    assert tokens == {"value": None, "kind": "unknown"}  # never derived from bytes (7.3)
