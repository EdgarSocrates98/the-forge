"""ContextVerify: reported and re-verified context drift, evidence demotion (6.1-6.3, 6.7)."""

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from theforge.context.fingerprints import FingerprintStore, hash_lines
from theforge.context.verify import (
    DRIFT_LIMITATION_PREFIX,
    NOT_REVERIFIED_LIMITATION,
    DriftReport,
    apply_drift,
    check_drift,
    items_to_verify,
    provider_reported_drift,
    reverify,
)
from theforge.contracts import (
    ContextFile,
    ContextPack,
    Evidence,
    ExecutionResult,
    Finding,
    LineRange,
    Location,
    Producer,
)
from theforge.contracts.integrity import validate_result

PROVIDER = Producer(id="echo", version="1.0.0")
NOW = "2026-10-04T00:00:00Z"
LINES = b"one\ntwo\r\nthree\nfour\n"  # 4 lines; line 2 keeps its \r


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def ws(tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    root.mkdir()
    (root / "a.py").write_bytes(b"print('a')\n")
    (root / "b.py").write_bytes(LINES)
    (root / "c.py").write_bytes(b"c = 1\n")
    return root


def _ref(path: str, data: bytes) -> ContextFile:
    return ContextFile(path=path, sha256=_sha(data), bytes=len(data))


def _excerpt(root: Path, path: str, start: int, end: int, tier: str = "excerpt") -> ContextFile:
    got = hash_lines((root / path).resolve(), LineRange(start=start, end=end))
    assert got is not None
    return ContextFile(
        path=path,
        sha256=got[0],
        bytes=got[1],
        tier=tier,  # type: ignore[arg-type]
        lines=LineRange(start=start, end=end),
    )


def _pack(files: list[ContextFile]) -> ContextPack:
    return ContextPack(
        producer=Producer(id="theforge", version="0"),
        created_at=NOW,
        status="complete",
        task_id="t1",
        provider_id="echo",
        root="ws",
        files=files,
        budget_bytes=10_000,
        used_bytes=sum(f.bytes for f in files),
    )


def _ev(
    eid: str,
    status: str = "confirmed",
    *,
    path: str | None = None,
    digest: str | None = None,
    subject: str = "s",
) -> Evidence:
    return Evidence(
        id=eid,
        epistemic=status,
        subject=subject,
        claim="c",  # type: ignore[arg-type]
        producer=PROVIDER,
        location=Location(path=path) if path else None,
        hash=digest,
    )


def _result(evidence: list[Evidence], status: str = "ok") -> ExecutionResult:
    return ExecutionResult(
        producer=PROVIDER,
        created_at=NOW,
        status=status,  # type: ignore[arg-type]
        evidence=evidence,
        findings=[Finding(id="f1", title="t", evidence_ids=[e.id for e in evidence])],
    )


@pytest.fixture
def pack(ws: Path) -> ContextPack:
    return _pack(
        [_ref("a.py", b"print('a')\n"), _excerpt(ws, "b.py", 2, 3), _ref("c.py", b"c = 1\n")]
    )


# --- provider-reported drift (Evidence.hash semantics) -----------------------------------


def test_reported_hash_matching_whole_item_is_not_drift(pack: ContextPack) -> None:
    res = _result([_ev("e1", path="a.py", digest=_sha(b"print('a')\n"))])
    assert provider_reported_drift(pack, res) == frozenset()


def test_reported_hash_differing_from_whole_item_is_drift(pack: ContextPack) -> None:
    res = _result([_ev("e1", path="a.py", digest=_sha(b"changed"))])
    assert provider_reported_drift(pack, res) == frozenset({"a.py"})


def test_reported_range_hash_for_excerpt_is_not_drift(ws: Path, pack: ContextPack) -> None:
    range_hash = hash_lines((ws / "b.py").resolve(), LineRange(start=2, end=3))
    assert range_hash is not None
    res = _result([_ev("e1", path="b.py", digest=range_hash[0])])
    assert provider_reported_drift(pack, res) == frozenset()


def test_reported_whole_file_hash_for_excerpt_is_drift(pack: ContextPack) -> None:
    res = _result([_ev("e1", path="b.py", digest=_sha(LINES))])
    assert provider_reported_drift(pack, res) == frozenset({"b.py"})


def test_same_path_in_two_items_matching_either_is_enough(ws: Path) -> None:
    pack = _pack([_ref("b.py", LINES), _excerpt(ws, "b.py", 1, 2, tier="requested")])
    range_hash = pack.files[1].sha256
    for digest in (_sha(LINES), range_hash):
        res = _result([_ev("e1", path="b.py", digest=digest)])
        assert provider_reported_drift(pack, res) == frozenset()
    res = _result([_ev("e1", path="b.py", digest=_sha(b"neither"))])
    assert provider_reported_drift(pack, res) == frozenset({"b.py"})


def test_null_hash_or_missing_location_is_never_reported_drift(pack: ContextPack) -> None:
    res = _result(
        [_ev("e1", path="a.py", digest=None), _ev("e2", subject="a.py", digest=_sha(b"x"))]
    )
    assert provider_reported_drift(pack, res) == frozenset()


def test_location_line_does_not_change_hash_scope(pack: ContextPack) -> None:
    ev = Evidence(
        id="e1",
        epistemic="observed",
        subject="s",
        claim="c",
        producer=PROVIDER,
        location=Location(path="a.py", line=1),
        hash=_sha(b"print('a')\n"),
    )
    assert provider_reported_drift(pack, _result([ev])) == frozenset()


def test_hash_for_path_outside_pack_is_not_drift(pack: ContextPack) -> None:
    res = _result([_ev("e1", path="zzz.py", digest=_sha(b"x"))])
    assert provider_reported_drift(pack, res) == frozenset()


# --- items per level ---------------------------------------------------------------------


def test_minimal_level_selects_nothing(pack: ContextPack) -> None:
    res = _result([_ev("e1", path="a.py")])
    assert items_to_verify(pack, res, "minimal") == []


def test_conditional_selects_items_cited_by_confirmed_or_observed(pack: ContextPack) -> None:
    res = _result(
        [
            _ev("e1", "confirmed", path="a.py"),
            _ev("e2", "observed", subject="b.py"),  # no location: matched by subject
            _ev("e3", "inferred", path="c.py"),
            _ev("e4", "unresolved", path="c.py"),
        ]
    )
    assert [f.path for f in items_to_verify(pack, res, "conditional")] == ["a.py", "b.py"]


def test_strong_selects_every_item(pack: ContextPack) -> None:
    assert items_to_verify(pack, _result([]), "strong") == list(pack.files)


# --- re-verification without cache ------------------------------------------------------


def test_reverify_unchanged_items_has_no_drift(ws: Path, pack: ContextPack) -> None:
    assert reverify(ws, pack.files) == frozenset()


def test_reverify_detects_changed_whole_file(ws: Path, pack: ContextPack) -> None:
    (ws / "a.py").write_bytes(b"print('A')\n")
    assert reverify(ws, pack.files) == frozenset({"a.py"})


def test_reverify_excerpt_uses_range_hash(ws: Path, pack: ContextPack) -> None:
    (ws / "b.py").write_bytes(LINES + b"five\n")  # outside the range: no drift
    assert reverify(ws, pack.files) == frozenset()
    (ws / "b.py").write_bytes(b"one\nTWO\r\nthree\nfour\n")  # inside the range
    assert reverify(ws, pack.files) == frozenset({"b.py"})


def test_reverify_range_past_end_is_drift(ws: Path, pack: ContextPack) -> None:
    (ws / "b.py").write_bytes(b"one\n")
    assert reverify(ws, pack.files) == frozenset({"b.py"})


def test_reverify_missing_file_is_drift(ws: Path, pack: ContextPack) -> None:
    (ws / "c.py").unlink()
    assert reverify(ws, pack.files) == frozenset({"c.py"})


def test_reverify_path_outside_root_is_drift(ws: Path) -> None:
    (ws.parent / "out.py").write_bytes(b"x")
    item = _ref("../out.py", b"x")
    assert reverify(ws, [item]) == frozenset({"../out.py"})


def test_reverify_ignores_fingerprint_cache(ws: Path, pack: ContextPack) -> None:
    store = FingerprintStore(ws)
    assert store.file("a.py", (ws / "a.py").resolve()) is not None  # memoized in memory
    (ws / "a.py").write_bytes(b"print('A')\n")
    assert reverify(ws, pack.files) == frozenset({"a.py"})


# --- check_drift -------------------------------------------------------------------------


def test_check_drift_minimal_reports_only_provider_drift(ws: Path, pack: ContextPack) -> None:
    (ws / "a.py").write_bytes(b"changed\n")  # not re-verified at minimal
    res = _result([_ev("e1", path="c.py", digest=_sha(b"other"))])
    report = check_drift(ws, pack, res, "minimal")
    assert report == DriftReport(
        drifted=("c.py",), checked=0, level="minimal", limitations=(NOT_REVERIFIED_LIMITATION,)
    )


def test_check_drift_conditional_reverifies_cited_items(ws: Path, pack: ContextPack) -> None:
    (ws / "a.py").write_bytes(b"changed\n")
    (ws / "c.py").write_bytes(b"changed\n")  # not cited: not re-verified
    report = check_drift(ws, pack, _result([_ev("e1", path="a.py")]), "conditional")
    assert report.drifted == ("a.py",)
    assert report.checked == 1
    assert report.limitations == ()


def test_check_drift_strong_reverifies_all_sorted(ws: Path, pack: ContextPack) -> None:
    (ws / "c.py").unlink()
    (ws / "a.py").write_bytes(b"changed\n")
    report = check_drift(ws, pack, _result([]), "strong")
    assert report.drifted == ("a.py", "c.py")
    assert report.checked == 3


def test_check_drift_without_changes_is_empty(ws: Path, pack: ContextPack) -> None:
    report = check_drift(ws, pack, _result([_ev("e1", path="a.py")]), "strong")
    assert report.drifted == ()


# --- apply_drift -------------------------------------------------------------------------


def test_apply_drift_without_drift_returns_result_unchanged() -> None:
    res = _result([_ev("e1", path="a.py")])
    report = DriftReport(drifted=(), checked=3, level="strong", limitations=())
    assert apply_drift(res, report) is res
    minimal = DriftReport(
        drifted=(), checked=0, level="minimal", limitations=(NOT_REVERIFIED_LIMITATION,)
    )
    assert apply_drift(res, minimal) is res


def test_apply_drift_demotes_confirmed_and_observed_and_marks_partial() -> None:
    evidence = [
        _ev("e1", "confirmed", path="a.py"),
        _ev("e2", "observed", subject="a.py"),
        _ev("e3", "inferred", path="a.py"),
        _ev("e4", "confirmed", path="c.py"),
    ]
    res = replace(_result(evidence), limitations=["prior"])
    out = apply_drift(
        res, DriftReport(drifted=("a.py",), checked=1, level="strong", limitations=())
    )
    by_id = {e.id: e for e in out.evidence}
    assert by_id["e1"].epistemic == "unresolved"
    assert by_id["e1"].limitations == [f"{DRIFT_LIMITATION_PREFIX} was confirmed"]
    assert by_id["e2"].epistemic == "unresolved"
    assert by_id["e2"].limitations == [f"{DRIFT_LIMITATION_PREFIX} was observed"]
    assert by_id["e3"] == evidence[2]
    assert by_id["e4"] == evidence[3]
    assert out.status == "partial"
    assert out.limitations == ["prior", f"{DRIFT_LIMITATION_PREFIX} a.py"]
    assert [e.id for e in out.evidence] == ["e1", "e2", "e3", "e4"]
    assert not any(
        e.epistemic == "confirmed" and e.location and e.location.path == "a.py"
        for e in out.evidence
    )
    validate_result(out, expected=PROVIDER)


def test_apply_drift_records_every_path_and_keeps_partial() -> None:
    res = _result([], status="partial")
    out = apply_drift(
        res,
        DriftReport(
            drifted=("a.py", "b.py"),
            checked=0,
            level="minimal",
            limitations=(NOT_REVERIFIED_LIMITATION,),
        ),
    )
    assert out.status == "partial"
    assert out.limitations == [f"{DRIFT_LIMITATION_PREFIX} a.py", f"{DRIFT_LIMITATION_PREFIX} b.py"]


def test_drift_limitation_prefix_is_context_drift() -> None:
    assert DRIFT_LIMITATION_PREFIX == "context-drift:"
    assert NOT_REVERIFIED_LIMITATION == "context-not-reverified"
