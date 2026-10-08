"""Engineering Memory store: .forge/memory/ (Cycle 5, Wave B/C/S/T/Y)."""

import json
from pathlib import Path

import pytest

from theforge import memory as memory_store
from theforge.contracts import to_dict
from theforge.contracts.canonical import utc_now
from theforge.contracts.memory import (
    EngineeringMemoryEntry,
    MemoryKind,
)
from theforge.meta import PRODUCER
from theforge.runs import RunStore
from theforge.state import FORGE_DIR_NAME

P = {"id": "theforge", "version": "0.2.1"}


def make_entry(
    *,
    kind: MemoryKind = "fact",
    epistemic: str = "observed",
    subject: str = "s",
    claim: str = "c",
    scope: str = "project",
    tags: tuple[str, ...] = (),
    provider: str | None = None,
    capability: str | None = None,
    evidence_refs: list[str] | None = None,
    **kw,
) -> EngineeringMemoryEntry:
    from dataclasses import replace

    entry = EngineeringMemoryEntry(
        producer=PRODUCER,
        created_at=utc_now(),
        id="0" * 64,
        kind=kind,
        epistemic=epistemic,  # type: ignore[arg-type]
        scope=scope,  # type: ignore[arg-type]
        subject=subject,
        claim=claim,
        provider=provider,
        capability=capability,
        tags=list(tags),
        source_refs=["run:r1"],
        evidence_refs=(
            evidence_refs
            if evidence_refs is not None
            else (["run:r1:verification"] if epistemic == "confirmed" else [])
        ),
        **kw,
    )
    return replace(entry, id=memory_store.memory_entry_id(entry))


class TestStore:
    def test_record_and_load_round_trip(self, tmp_path: Path) -> None:
        entry = make_entry(subject="a", claim="b")
        assert memory_store.record_entry(tmp_path, entry) is None
        entries, warning = memory_store.load_entries(tmp_path)
        assert warning is None
        assert entries == [entry]

    def test_record_dedups_by_content_id(self, tmp_path: Path) -> None:
        entry = make_entry(subject="a", claim="b")
        memory_store.record_entry(tmp_path, entry)
        memory_store.record_entry(tmp_path, entry)
        entries, _ = memory_store.load_entries(tmp_path)
        assert len(entries) == 1

    def test_corrupt_lines_are_skipped_not_fatal(self, tmp_path: Path) -> None:
        good = make_entry(subject="good", claim="kept")
        path = tmp_path / FORGE_DIR_NAME / "memory" / "entries.jsonl"
        path.parent.mkdir(parents=True)
        path.write_text(
            json.dumps(to_dict(good)) + "\n" + "{not json}\n" + '["bad"]\n',
            encoding="utf-8",
        )
        entries, warning = memory_store.load_entries(tmp_path)
        assert entries == [good]
        assert warning is not None and "skipped 2" in warning

    def test_empty_store_is_empty_not_error(self, tmp_path: Path) -> None:
        entries, warning = memory_store.load_entries(tmp_path)
        assert entries == [] and warning is None


class TestTransitions:
    def test_mark_stale_needs_reason_and_provenance(self, tmp_path: Path) -> None:
        from dataclasses import replace

        sourced = make_entry(subject="s", claim="c")
        orphan = make_entry(subject="o", claim="orphan", epistemic="unresolved",
                            evidence_refs=[])
        orphan = replace(orphan, source_refs=[])
        for e in (sourced, orphan):
            assert memory_store.record_entry(tmp_path, e) is None
        changed, _ = memory_store.mark_stale(tmp_path, [sourced.id, orphan.id], "surface changed")
        assert changed == 1
        entries, _ = memory_store.load_entries(tmp_path)
        by_id = {e.id: e for e in entries}
        assert by_id[sourced.id].epistemic == "stale"
        assert by_id[sourced.id].stale_reason == "surface changed"
        assert by_id[orphan.id].epistemic == "unresolved"  # orphans cannot go stale

    def test_supersede_links_forward_and_keeps_source(self, tmp_path: Path) -> None:
        old = make_entry(subject="s", claim="v1")
        memory_store.record_entry(tmp_path, old)
        new = make_entry(subject="s", claim="v2", supersedes=old.id)
        ok, warning = memory_store.supersede(tmp_path, old.id, new)
        assert ok and warning is None
        entries, _ = memory_store.load_entries(tmp_path)
        by_id = {e.id: e for e in entries}
        assert by_id[old.id].epistemic == "superseded"
        assert by_id[old.id].superseded_by == new.id
        assert by_id[new.id].supersedes == old.id
        assert len(entries) == 2  # history kept

    def test_supersede_unknown_source_fails(self, tmp_path: Path) -> None:
        ok, warning = memory_store.supersede(tmp_path, "f" * 64, make_entry())
        assert not ok and "unknown" in (warning or "")


class TestRetrieval:
    def test_pack_filters_and_echoes_query(self, tmp_path: Path) -> None:
        memory_store.record_entry(tmp_path, make_entry(subject="kafka", claim="a",
                                                       provider="p1"))
        memory_store.record_entry(tmp_path, make_entry(subject="api", claim="b",
                                                       provider="p2"))
        pack, _ = memory_store.memory_pack(
            tmp_path, memory_store.MemoryQuery(provider="p1")
        )
        assert pack.total_matches == 1
        assert pack.entries[0].provider == "p1"
        assert pack.query == {"provider": "p1"}

    def test_pack_excludes_terminal_by_default(self, tmp_path: Path) -> None:
        stale = make_entry(subject="old", claim="x")
        memory_store.record_entry(tmp_path, stale)
        memory_store.mark_stale(tmp_path, [stale.id], "old")
        pack, _ = memory_store.memory_pack(tmp_path, memory_store.MemoryQuery())
        assert pack.total_matches == 0
        pack_all, _ = memory_store.memory_pack(
            tmp_path, memory_store.MemoryQuery(include_terminal=True)
        )
        assert pack_all.total_matches == 1

    def test_pack_is_bounded_and_marks_truncation(self, tmp_path: Path) -> None:
        for i in range(5):
            memory_store.record_entry(tmp_path, make_entry(subject=f"s{i}", claim=f"c{i}"))
        pack, _ = memory_store.memory_pack(tmp_path, max_entries=2)
        assert len(pack.entries) == 2 and pack.total_matches == 5 and pack.truncated
        pack_b, _ = memory_store.memory_pack(tmp_path, max_bytes=1024)
        assert pack_b.truncated or pack_b.delivered_bytes <= 1024

    def test_deterministic_order(self, tmp_path: Path) -> None:
        for i in range(3):
            memory_store.record_entry(tmp_path, make_entry(subject=f"s{i}", claim="c"))
        a, _ = memory_store.memory_pack(tmp_path)
        b, _ = memory_store.memory_pack(tmp_path)
        assert [e.id for e in a.entries] == [e.id for e in b.entries]


class TestDistillation:
    def test_summary_requires_existing_sources(self, tmp_path: Path) -> None:
        doc, problem = memory_store.summarize(
            tmp_path, subject="s", summary="t", source_ids=["a" * 64]
        )
        assert doc is None and "not recorded" in (problem or "")

    def test_summary_keeps_sources(self, tmp_path: Path) -> None:
        src = make_entry(subject="s", claim="c")
        memory_store.record_entry(tmp_path, src)
        doc, problem = memory_store.summarize(
            tmp_path, subject="s", summary="combined", source_ids=[src.id]
        )
        assert problem is None and doc is not None
        assert doc.source_ids == [src.id]
        entries, _ = memory_store.load_entries(tmp_path)
        assert len(entries) == 1  # source never deleted
        summaries, _ = memory_store.load_summaries(tmp_path)
        assert summaries[0].id == doc.id


class TestCrossProject:
    def portable(self, **kw) -> EngineeringMemoryEntry:
        return make_entry(
            scope="portable",
            origin_project_class="internal-lib",
            redaction="no identifiers",
            **kw,
        )

    def test_export_only_moves_portable_scopes(self, tmp_path: Path) -> None:
        memory_store.record_entry(tmp_path, make_entry(subject="local", claim="x"))
        memory_store.record_entry(tmp_path, self.portable(subject="pattern", claim="y"))
        entries, _ = memory_store.export_entries(tmp_path)
        assert len(entries) == 1 and entries[0].scope == "portable"

    def test_import_refuses_project_scoped(self, tmp_path: Path) -> None:
        src_dir = tmp_path / "a"
        dst_dir = tmp_path / "b"
        memory_store.record_entry(src_dir, make_entry(subject="private", claim="x"))
        memory_store.record_entry(
            src_dir, self.portable(subject="shared", claim="y")
        )
        exported, _ = memory_store.export_entries(src_dir)
        imported, warning = memory_store.import_entries(
            dst_dir, [to_dict(e) for e in exported]
            + [to_dict(make_entry(subject="private", claim="x"))]
        )
        assert imported == 1
        assert warning and "refused 1" in warning
        entries, _ = memory_store.load_entries(dst_dir)
        assert {e.subject for e in entries} == {"shared"}


class TestLearnFromRun:
    def _write_run(self, root: Path, *, verdict: str = "passed") -> str:
        from theforge.contracts.verification import VerificationCheck, VerificationResult

        forge = root / FORGE_DIR_NAME
        store = RunStore(forge)
        run_id = "20260101T000000Z-deadbeef"
        store.create(run_id)
        store.write(
            run_id,
            "verification",
            VerificationResult(
                producer=PRODUCER,
                created_at=utc_now(),
                run_id=run_id,
                self_report=VerificationCheck(status="reported"),
                provider_evidence=VerificationCheck(status="not_performed"),
                forge=VerificationCheck(status=verdict),  # type: ignore[arg-type]
                independent=VerificationCheck(status="not_performed"),
            ),
        )
        return run_id

    def test_passed_verification_becomes_confirmed_resolution(self, tmp_path: Path) -> None:
        run_id = self._write_run(tmp_path, verdict="passed")
        count, notes = memory_store.learn_from_run(
            tmp_path, RunStore(tmp_path / FORGE_DIR_NAME), run_id
        )
        assert count == 1 and not notes
        entries, _ = memory_store.load_entries(tmp_path)
        assert entries[0].kind == "resolution"
        assert entries[0].epistemic == "confirmed"
        assert f"run:{run_id}" in entries[0].source_refs

    def test_failed_verification_becomes_observed_failure(self, tmp_path: Path) -> None:
        run_id = self._write_run(tmp_path, verdict="failed")
        count, _ = memory_store.learn_from_run(
            tmp_path, RunStore(tmp_path / FORGE_DIR_NAME), run_id
        )
        assert count == 1
        entries, _ = memory_store.load_entries(tmp_path)
        assert entries[0].kind == "failure" and entries[0].epistemic == "observed"

    def test_failure_patterns_aggregate(self, tmp_path: Path) -> None:
        run_id = self._write_run(tmp_path, verdict="failed")
        store = RunStore(tmp_path / FORGE_DIR_NAME)
        memory_store.learn_from_run(tmp_path, store, run_id)
        patterns, _ = memory_store.failure_patterns(tmp_path)
        assert len(patterns) == 1
        assert patterns[0].occurrences == 1
        assert patterns[0].error_family


class TestCLI:
    def test_memory_list_and_learn(self, tmp_path: Path, capsys: pytest.CaptureFixture[str],
                                   monkeypatch: pytest.MonkeyPatch) -> None:
        from theforge.cli.main import build_parser
        from theforge.state import init_workspace

        init_workspace(tmp_path)
        parser = build_parser()

        args = parser.parse_args(
            ["memory", "list", "--root", str(tmp_path), "--json"]
        )
        assert args.handler(args) == 0
        out = json.loads(capsys.readouterr().out)
        assert out["total_matches"] == 0

        entry = make_entry(subject="cli", claim="visible")
        memory_store.record_entry(tmp_path, entry)
        args = parser.parse_args(
            ["memory", "list", "--root", str(tmp_path), "--subject", "cli", "--json"]
        )
        args.handler(args)
        out = json.loads(capsys.readouterr().out)
        assert out["total_matches"] == 1

    def test_export_cli(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        from theforge.cli.main import build_parser
        from theforge.state import init_workspace

        init_workspace(tmp_path)
        parser = build_parser()
        args = parser.parse_args(["memory", "export", "--root", str(tmp_path), "--json"])
        assert args.handler(args) == 0
        assert json.loads(capsys.readouterr().out)["count"] == 0
