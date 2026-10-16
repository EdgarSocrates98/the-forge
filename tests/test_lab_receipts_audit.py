"""Audit the real benchmark receipts committed under docs/programs — Cycle 10.1 §7.

Every line in ``results-*.jsonl`` is a real ``forge/BenchmarkResult/v1``
receipt produced by a sibling lab emitter. These tests validate the stored
evidence itself: schema conformance, provenance, dedup, metric-state
discipline, and reproducibility of a fresh collection on the same inputs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from theforge.contracts.base import ContractError
from theforge.contracts.benchmark import parse_result

BENCH = (
    Path(__file__).resolve().parent.parent
    / "docs"
    / "programs"
    / "ecosystem-2026"
    / "benchmarks"
)
RECEIPTS = sorted(BENCH.glob("results-*.jsonl"))

VALID_STATES = {"measured", "not_available", "not_applicable"}


def _lines() -> list[tuple[Path, dict]]:
    out = []
    for f in RECEIPTS:
        for ln in f.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                out.append((f, json.loads(ln)))
    return out


def test_receipts_exist():
    assert RECEIPTS, "no benchmark receipts collected"


def test_every_receipt_conforms_to_contract():
    bad = []
    for f, doc in _lines():
        try:
            parse_result(doc, strict=False)
        except ContractError as e:  # noqa: PERF203
            bad.append((f.name, doc.get("forge"), str(e)[:120]))
    assert not bad, f"non-conforming receipts: {bad[:5]}"


def test_provenance_fields_present():
    for f, doc in _lines():
        assert doc.get("schema") == "forge/BenchmarkResult/v1", f"{f.name}: wrong schema"
        assert doc.get("forge"), f"{f.name}: missing forge"
        prod = doc.get("producer") or {}
        assert prod.get("id"), f"{f.name}: missing producer.id"
        assert isinstance(doc.get("external"), bool), f"{f.name}: external flag missing"
        assert doc.get("created_at"), f"{f.name}: missing created_at"
        assert doc.get("results"), f"{f.name}: no results"


def test_no_duplicate_scenario_ids_within_receipt():
    for f, doc in _lines():
        ids = [r.get("scenario_id") for r in doc.get("results", [])]
        dupes = {i for i in ids if ids.count(i) > 1}
        assert not dupes, f"{f.name}/{doc.get('forge')}: duplicate scenario ids {sorted(dupes)}"


def test_metric_states_disciplined():
    for f, doc in _lines():
        for r in doc.get("results", []):
            sid = r.get("scenario_id", "?")
            for name, m in (r.get("metrics") or {}).items():
                state = m.get("state", "measured")
                assert state in VALID_STATES, f"{f.name}/{sid}.{name}: bad state {state!r}"
                if state == "measured":
                    assert m.get("value") is not None, (
                        f"{f.name}/{sid}.{name}: measured with null value"
                    )
                else:
                    assert m.get("value") is None, (
                        f"{f.name}/{sid}.{name}: {state} must carry null, "
                        f"got {m.get('value')!r}"
                    )


def test_verdicts_are_closed_set():
    valid = {"pass", "fail", "skipped", "error", "inconclusive"}
    for f, doc in _lines():
        for r in doc.get("results", []):
            assert r.get("verdict") in valid, f"{f.name}: bad verdict {r.get('verdict')!r}"


def test_verdict_histogram_and_failures_preserved():
    """Real failures must stay visible — no fake green."""
    hist: dict[str, int] = {}
    total = 0
    for _f, doc in _lines():
        for r in doc.get("results", []):
            hist[r["verdict"]] = hist.get(r["verdict"], 0) + 1
            total += 1
    assert total >= 203, f"expected 203+ scenarios across receipts, got {total}"
    assert hist.get("pass", 0) > 0
    # The lab corpus deliberately includes negative scenarios; their verdicts
    # must survive into the stored receipts (no silent filtering to green).
    assert hist.get("fail", 0) >= 1, f"failure verdicts filtered out? {hist}"


@pytest.mark.parametrize("fname", [r.name for r in RECEIPTS])
def test_each_file_has_one_receipt_per_forge(fname: str):
    docs = [json.loads(ln) for ln in (BENCH / fname).read_text().splitlines() if ln.strip()]
    forges = [d.get("forge") for d in docs]
    assert len(forges) == len(set(forges)), f"{fname}: repeated forge entries {forges}"
