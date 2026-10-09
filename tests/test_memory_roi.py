"""Cycle 5.1 §14-16: pack_stats instrumentation + memory safety regressions."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from theforge.contracts.base import to_dict
from theforge.contracts.canonical import utc_now
from theforge.contracts.memory import EngineeringMemoryEntry
from theforge.memory import (
    DEFAULT_PACK_ENTRIES,
    MemoryQuery,
    load_entries,
    mark_stale,
    memory_entry_id,
    memory_pack,
    pack_stats,
    record_entry,
)
from theforge.meta import PRODUCER

pytestmark = pytest.mark.unit

SURF = "a" * 64
OTHER_SURF = "b" * 64


def _entry(i: int, root: Path, **kw) -> EngineeringMemoryEntry:
    stub = EngineeringMemoryEntry(
        producer=PRODUCER,
        created_at=utc_now(),
        id="0" * 64,
        kind=kw.get("kind", "failure"),
        scope="project",
        workspace=str(root),
        subject=f"subject {i}",
        claim=f"claim {i} {kw.get('claim', '')}",
        epistemic="observed",
        provider=kw.get("provider", "prov-a"),
        capability=kw.get("capability", "check.plan"),
        task_family=kw.get("family", "audit"),
        surface_fingerprint=kw.get("surface", SURF),
        source_refs=[f"run:{i:04d}"],
        evidence_refs=[f"run:{i:04d}:result"],
        tags=[kw.get("tag", "timeout")],
    )
    return replace(stub, id=memory_entry_id(stub))


def _seed(root: Path, n: int, **kw) -> list[EngineeringMemoryEntry]:
    entries = [_entry(i, root, **kw) for i in range(n)]
    for entry in entries:
        assert record_entry(root, entry) is None
    return entries


def test_pack_stats_mirrors_memory_pack(tmp_path: Path) -> None:
    """delivered/bytes are the pack's own numbers — instrumentation over the
    real path, not an estimate (§14)."""
    entries = _seed(tmp_path, 40)
    query = MemoryQuery(capability="check.plan", task_family="audit")
    stats, _ = pack_stats(tmp_path, query, surface=SURF)
    pack, _ = memory_pack(tmp_path, query)
    assert stats["entries_considered"] == 40
    assert stats["entries_matched"] == 40
    assert stats["entries_fresh"] == 40
    assert stats["entries_delivered"] == len(pack.entries) == DEFAULT_PACK_ENTRIES
    assert stats["entries_withheld"] == 40 - len(pack.entries)
    assert stats["bytes_delivered"] == pack.delivered_bytes
    assert stats["bytes_matched"] == sum(
        len(json.dumps(to_dict(e), sort_keys=True).encode()) for e in entries
    )


def test_pack_stats_counts_terminal_but_never_delivers(tmp_path: Path) -> None:
    entries = _seed(tmp_path, 5)
    changed, _ = mark_stale(tmp_path, [entries[0].id, entries[1].id], "surface rotated")
    assert changed == 2
    stats, _ = pack_stats(tmp_path, MemoryQuery(capability="check.plan"), surface=SURF)
    assert stats["entries_terminal"] == 2
    assert stats["entries_matched"] == 3  # the terminal two are not in the match
    pack, _ = memory_pack(tmp_path, MemoryQuery(capability="check.plan"))
    assert all(e.epistemic == "observed" for e in pack.entries)


def test_pack_stats_unknown_surface_means_not_fresh(tmp_path: Path) -> None:
    """§16/§20: surface-bound memory under an unknown surface is *not* fresh —
    unknown is never silently read as trustworthy."""
    _seed(tmp_path, 6)
    query = MemoryQuery(capability="check.plan")
    stats, _ = pack_stats(tmp_path, query, surface=None)
    assert stats["entries_fresh"] == 0
    assert stats["entries_not_fresh"] == stats["entries_matched"]
    # And a *different* surface marks bound evidence not-fresh the same way.
    stats_other, _ = pack_stats(tmp_path, query, surface=OTHER_SURF)
    assert stats_other["entries_fresh"] == 0
    # Unbound entries stay fresh on any surface reading.
    _seed(tmp_path, 3, surface=None, capability="check.plan", claim="unbound", tag="unbound")
    stats_unbound, _ = pack_stats(tmp_path, MemoryQuery(tag="unbound"), surface=None)
    assert stats_unbound["entries_matched"] == 3
    assert stats_unbound["entries_fresh"] == 3


def test_pack_stats_is_read_only_and_deterministic(tmp_path: Path) -> None:
    _seed(tmp_path, 10)
    path = tmp_path / ".forge" / "memory" / "entries.jsonl"
    before = path.read_bytes()
    first, _ = pack_stats(tmp_path)
    second, _ = pack_stats(tmp_path)
    assert first == second
    assert path.read_bytes() == before
    entries, _ = load_entries(tmp_path)
    assert len(entries) == 10
