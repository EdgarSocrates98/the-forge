"""FingerprintStore: conservative sha256 reuse outside the workspace (5.1-5.6, 12.3, 12.4)."""

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

import theforge.context.fingerprints as fp
from theforge.context.fingerprints import (
    CACHE_SCHEMA,
    RACY_WINDOW_NS,
    FingerprintStore,
    hash_file,
    hash_lines,
    prefix_lines,
)
from theforge.contracts import LineRange
from theforge.registry.config import user_cache_dir


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _age(path: Path, seconds: int = 60) -> None:
    """Move mtime safely out of the racy window."""
    old = time.time_ns() - seconds * 1_000_000_000
    os.utime(path, ns=(old, old))


@pytest.fixture
def ws(tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    root.mkdir()
    return root


def _write(root: Path, rel: str, data: bytes, *, aged: bool = True) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    if aged:
        _age(path)
    return path.resolve()


def _cache_file(root: Path) -> Path:
    files = list((user_cache_dir() / "context").glob("*.json"))
    assert len(files) == 1, files
    return files[0]


def _populate(root: Path, rel: str = "a.py", data: bytes = b"print(1)\n") -> Path:
    resolved = _write(root, rel, data)
    store = FingerprintStore(root)
    got = store.file(rel, resolved)
    assert got is not None and not got.reused
    store.save()
    assert not store.warnings
    return resolved


def _no_read(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(path: Path) -> bytes:
        raise AssertionError(f"content of {path} must not be read on a hit")

    monkeypatch.setattr(fp, "_read_bytes", boom)


# --- reuse (5.1) ----------------------------------------------------------------------------


def test_hit_reuses_hash_without_reading_content(ws: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    resolved = _populate(ws)
    _no_read(monkeypatch)
    store = FingerprintStore(ws)  # loads the cache document before any read is forbidden

    def no_open(*args: object, **kwargs: object) -> None:
        raise AssertionError(f"no file may be opened on a hit: {args!r}")

    monkeypatch.setattr("builtins.open", no_open)
    monkeypatch.setattr("io.open", no_open)
    monkeypatch.setattr(os, "open", no_open)
    monkeypatch.setattr(Path, "open", no_open)
    monkeypatch.setattr(Path, "read_bytes", no_open)
    got = store.file("a.py", resolved)
    assert got is not None
    assert got.reused is True
    assert got.sha256 == _sha(b"print(1)\n")
    assert got.size == len(b"print(1)\n")
    assert (store.stats.hits, store.stats.misses) == (1, 0)
    assert (store.stats.files_hashed, store.stats.bytes_hashed) == (0, 0)


def test_miss_counts_files_and_bytes(ws: Path) -> None:
    a = _write(ws, "a.py", b"abc")
    b = _write(ws, "b.py", b"hello\n")
    store = FingerprintStore(ws)
    assert store.file("a.py", a) is not None
    assert store.file("b.py", b) is not None
    assert (store.stats.hits, store.stats.misses) == (0, 2)
    assert (store.stats.files_hashed, store.stats.bytes_hashed) == (2, 9)


def test_unreadable_file_returns_none(ws: Path) -> None:
    store = FingerprintStore(ws)
    assert store.file("ghost.py", (ws / "ghost.py").resolve()) is None
    assert store.stats.files_hashed == 0


# --- change evidence (5.2) ------------------------------------------------------------------


@pytest.mark.parametrize("field", ["size", "mtime_ns", "ctime_ns", "ino", "dev", "path"])
def test_any_differing_stat_field_forces_rehash(ws: Path, field: str) -> None:
    resolved = _populate(ws)
    cache = _cache_file(ws)
    doc = json.loads(cache.read_text(encoding="utf-8"))
    entry = doc["entries"]["a.py"]
    entry[field] = entry[field] + "x" if field == "path" else entry[field] + 1
    entry["sha256"] = "0" * 64  # a reuse would surface this bogus hash
    cache.write_text(json.dumps(doc), encoding="utf-8")
    store = FingerprintStore(ws)
    got = store.file("a.py", resolved)
    assert got is not None and got.reused is False
    assert got.sha256 == _sha(b"print(1)\n")
    assert (store.stats.hits, store.stats.misses, store.stats.files_hashed) == (0, 1, 1)


def test_content_change_with_new_size_is_a_miss(ws: Path) -> None:
    resolved = _populate(ws)
    _write(ws, "a.py", b"print(22)\n")
    got = FingerprintStore(ws).file("a.py", resolved)
    assert got is not None and not got.reused and got.sha256 == _sha(b"print(22)\n")


def test_replaced_file_with_same_size_and_mtime_is_a_miss(ws: Path) -> None:
    """Same size, same mtime, different content: identity (ino/ctime) gives it away."""
    resolved = _populate(ws, data=b"AAAA\n")
    before = os.stat(resolved)
    tmp = ws / "a.tmp"
    tmp.write_bytes(b"BBBB\n")
    os.utime(tmp, ns=(before.st_atime_ns, before.st_mtime_ns))
    os.replace(tmp, resolved)
    after = os.stat(resolved)
    assert (after.st_size, after.st_mtime_ns) == (before.st_size, before.st_mtime_ns)
    got = FingerprintStore(ws).file("a.py", resolved)
    assert got is not None and not got.reused and got.sha256 == _sha(b"BBBB\n")


def test_resolved_path_change_is_a_miss(ws: Path) -> None:
    """The same relative name resolving to another file never reuses the old hash."""
    _populate(ws)
    other = _write(ws, "other.py", b"print(1)\n")
    got = FingerprintStore(ws).file("a.py", other)
    assert got is not None and not got.reused


def test_racy_mtime_is_never_reused(ws: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    resolved = _write(ws, "a.py", b"x = 1\n", aged=False)  # mtime ~ now
    first = FingerprintStore(ws)
    assert first.file("a.py", resolved) is not None
    first.save()
    entry = json.loads(_cache_file(ws).read_text(encoding="utf-8"))["entries"]["a.py"]
    assert entry["recorded_ns"] - entry["mtime_ns"] <= RACY_WINDOW_NS
    second = FingerprintStore(ws)
    got = second.file("a.py", resolved)
    assert got is not None and got.reused is False
    assert second.stats.misses == 1


def test_racy_boundary_and_future_mtime(ws: Path) -> None:
    resolved = _populate(ws)
    cache = _cache_file(ws)
    doc = json.loads(cache.read_text(encoding="utf-8"))
    entry = doc["entries"]["a.py"]
    for recorded, reused in (
        (entry["mtime_ns"] + RACY_WINDOW_NS, False),
        (entry["mtime_ns"] - 1, False),  # clock went backwards
        (entry["mtime_ns"] + RACY_WINDOW_NS + 1, True),
    ):
        entry["recorded_ns"] = recorded
        cache.write_text(json.dumps(doc), encoding="utf-8")
        got = FingerprintStore(ws).file("a.py", resolved)
        assert got is not None and got.reused is reused, recorded


def test_racy_miss_rerecords_so_a_later_run_hits(ws: Path) -> None:
    resolved = _write(ws, "a.py", b"x = 1\n", aged=False)
    first = FingerprintStore(ws)
    first.file("a.py", resolved)
    first.save()
    _age(resolved)  # now stable and old
    second = FingerprintStore(ws)
    assert second.file("a.py", resolved).reused is False  # type: ignore[union-attr]
    second.save()
    third = FingerprintStore(ws)
    assert third.file("a.py", resolved).reused is True  # type: ignore[union-attr]


def test_file_changing_during_read_is_hashed_but_not_recorded(
    ws: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    resolved = _write(ws, "a.py", b"one\n")
    real = fp._read_bytes

    def racing_read(path: Path) -> bytes:
        data = real(path)
        path.write_bytes(b"two two\n")
        _age(path, 30)
        return data

    monkeypatch.setattr(fp, "_read_bytes", racing_read)
    store = FingerprintStore(ws)
    got = store.file("a.py", resolved)
    assert got is not None and got.sha256 == _sha(b"one\n") and not got.reused
    store.save()
    doc = json.loads(_cache_file(ws).read_text(encoding="utf-8"))
    assert "a.py" not in doc["entries"]


# --- invalid cache (5.3) --------------------------------------------------------------------


def test_missing_cache_is_silent(ws: Path) -> None:
    resolved = _write(ws, "a.py", b"x")
    store = FingerprintStore(ws)
    assert store.file("a.py", resolved) is not None
    assert store.warnings == []


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda d: "{not json", id="malformed-json"),
        pytest.param(lambda d: [], id="not-an-object"),
        pytest.param(
            lambda d: {**d, "schema": "theforge/FingerprintCache/v9"}, id="unknown-version"
        ),
        pytest.param(lambda d: {**d, "root": d["root"] + "-elsewhere"}, id="other-root"),
        pytest.param(lambda d: {**d, "sneaky": True}, id="unknown-field"),
        pytest.param(
            lambda d: {**d, "entries": {"a.py": {**d["entries"]["a.py"], "size": "1"}}},
            id="wrong-type",
        ),
        pytest.param(
            lambda d: {**d, "entries": {"a.py": {**d["entries"]["a.py"], "sha256": "zz"}}},
            id="bad-hash",
        ),
        pytest.param(
            lambda d: {**d, "entries": {"a.py": {**d["entries"]["a.py"], "size": -1}}},
            id="negative-size",
        ),
    ],
)
def test_invalid_cache_is_discarded_with_warning(
    ws: Path, mutate: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    resolved = _populate(ws)
    cache = _cache_file(ws)
    doc = mutate(json.loads(cache.read_text(encoding="utf-8")))
    cache.write_text(doc if isinstance(doc, str) else json.dumps(doc), encoding="utf-8")
    store = FingerprintStore(ws)
    got = store.file("a.py", resolved)
    assert got is not None and got.reused is False
    assert got.sha256 == _sha(b"print(1)\n")
    assert len(store.warnings) == 1 and "fingerprint cache" in store.warnings[0]


def test_unreadable_cache_is_discarded_with_warning(ws: Path) -> None:
    _populate(ws)
    cache = _cache_file(ws)
    cache.unlink()
    cache.mkdir()  # reading a directory fails with OSError
    store = FingerprintStore(ws)
    assert store.warnings and "fingerprint cache" in store.warnings[0]


# --- location (5.4) -------------------------------------------------------------------------


def test_cache_lives_in_user_cache_dir_outside_workspace(ws: Path) -> None:
    _populate(ws)
    cache = _cache_file(ws)
    digest = _sha(ws.resolve().as_posix().encode("utf-8"))[:12]
    assert cache == user_cache_dir() / "context" / f"{digest}.json"
    assert not cache.resolve().is_relative_to(ws.resolve())
    assert sorted(p.name for p in ws.rglob("*")) == ["a.py"]
    doc = json.loads(cache.read_text(encoding="utf-8"))
    assert doc["schema"] == CACHE_SCHEMA and doc["root"] == ws.resolve().as_posix()


def test_explicit_cache_dir(ws: Path, tmp_path: Path) -> None:
    resolved = _write(ws, "a.py", b"x")
    base = tmp_path / "elsewhere"
    store = FingerprintStore(ws, cache_dir=base)
    store.file("a.py", resolved)
    store.save()
    assert len(list((base / "context").glob("*.json"))) == 1


def test_cache_dir_inside_workspace_is_refused(ws: Path) -> None:
    resolved = _write(ws, "a.py", b"x")
    store = FingerprintStore(ws, cache_dir=ws / ".cache")
    assert store.file("a.py", resolved) is not None
    store.save()
    assert not (ws / ".cache").exists()
    assert any("inside the workspace" in w for w in store.warnings)


def test_workspace_cannot_prepopulate_fingerprints(ws: Path) -> None:
    """A planted file inside the project is never consulted."""
    resolved = _write(ws, "a.py", b"real\n")
    planted = ws / ".forge" / "context"
    planted.mkdir(parents=True)
    (planted / "fingerprints.json").write_text("{}", encoding="utf-8")
    got = FingerprintStore(ws).file("a.py", resolved)
    assert got is not None and not got.reused


# --- write (5.5, 12.3, 12.4) ----------------------------------------------------------------


def test_write_failure_becomes_warning(ws: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    resolved = _write(ws, "a.py", b"x")
    store = FingerprintStore(ws)
    store.file("a.py", resolved)

    def broken_replace(src: object, dst: object) -> None:
        raise OSError("disk on fire")

    monkeypatch.setattr(os, "replace", broken_replace)
    store.save()  # never raises
    assert any("disk on fire" in w for w in store.warnings)
    assert not list((user_cache_dir() / "context").glob("*"))


def test_unwritable_cache_dir_becomes_warning(ws: Path, tmp_path: Path) -> None:
    blocker = tmp_path / "cache-is-a-file"
    blocker.write_text("x", encoding="utf-8")
    resolved = _write(ws, "a.py", b"x")
    store = FingerprintStore(ws, cache_dir=blocker)
    assert store.file("a.py", resolved) is not None
    store.save()
    assert any("fingerprint cache" in w for w in store.warnings)


def test_entry_altered_by_redaction_is_not_written(ws: Path) -> None:
    good = _write(ws, "a.py", b"x")
    bad_rel = "password=hunter2.txt"
    bad = _write(ws, bad_rel, b"y")
    store = FingerprintStore(ws)
    store.file("a.py", good)
    store.file(bad_rel, bad)
    store.save()
    doc = json.loads(_cache_file(ws).read_text(encoding="utf-8"))
    assert list(doc["entries"]) == ["a.py"]
    assert "hunter2" not in _cache_file(ws).read_text(encoding="utf-8")
    assert any("not cached" in w for w in store.warnings)


def test_document_altered_by_redaction_is_refused_and_old_copy_removed(tmp_path: Path) -> None:
    root = tmp_path / "token=abcdef123"
    root.mkdir()
    resolved = _write(root, "a.py", b"x")
    store = FingerprintStore(root)
    store.file("a.py", resolved)
    path = store.path
    assert path is not None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("stale", encoding="utf-8")
    store.save()
    assert not path.exists()
    assert any("redaction" in w for w in store.warnings)


def test_save_writes_atomically_once_and_keeps_untouched_entries(ws: Path) -> None:
    a = _populate(ws, "a.py", b"a\n")
    b = _write(ws, "b.py", b"b\n")
    store = FingerprintStore(ws)
    store.file("b.py", b)  # a.py untouched this run
    store.save()
    entries = json.loads(_cache_file(ws).read_text(encoding="utf-8"))["entries"]
    assert sorted(entries) == ["a.py", "b.py"]
    assert not [p for p in _cache_file(ws).parent.iterdir() if p.suffix == ".tmp"]
    assert FingerprintStore(ws).file("a.py", a).reused is True  # type: ignore[union-attr]


# --- enabled=False and the cache on/off property (5.6) --------------------------------------


def test_disabled_store_never_reads_nor_writes_cache(ws: Path) -> None:
    resolved = _populate(ws)
    cache = _cache_file(ws)
    before = cache.read_bytes()
    store = FingerprintStore(ws, enabled=False)
    got = store.file("a.py", resolved)
    assert got is not None and not got.reused
    store.save()
    assert cache.read_bytes() == before
    assert (store.stats.hits, store.stats.misses, store.stats.files_hashed) == (0, 1, 1)


_FILES = st.dictionaries(
    st.sampled_from(["a.py", "b.txt", "pkg/c.py", "pkg/d.md"]), st.binary(max_size=64), min_size=1
)


@settings(
    max_examples=40,
    deadline=None,
    database=None,
    derandomize=True,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(rounds=st.lists(_FILES, min_size=1, max_size=4), aged=st.booleans())
def test_property_cache_on_or_off_yields_identical_hashes(
    tmp_path_factory: pytest.TempPathFactory, rounds: list[dict[str, bytes]], aged: bool
) -> None:
    root = tmp_path_factory.mktemp("prop")
    cache_base = tmp_path_factory.mktemp("prop-cache")
    for files in rounds:
        for rel, data in files.items():
            _write(root, rel, data, aged=aged)
        on = FingerprintStore(root, cache_dir=cache_base)
        off = FingerprintStore(root, cache_dir=cache_base, enabled=False)
        for rel, data in files.items():
            resolved = (root / rel).resolve()
            hot = on.file(rel, resolved)
            cold = off.file(rel, resolved)
            assert hot is not None and cold is not None
            assert hot.sha256 == cold.sha256 == _sha(data)
            assert hot.size == cold.size == len(data)
        on.save()


# --- range hash: single owner, one newline rule ---------------------------------------------


def test_hash_lines_middle_and_last_line_without_newline(tmp_path: Path) -> None:
    path = tmp_path / "f.txt"
    path.write_bytes(b"one\ntwo\r\nthree")
    assert hash_lines(path, LineRange(start=2, end=2)) == (_sha(b"two\r\n"), 5)
    assert hash_lines(path, LineRange(start=3, end=3)) == (_sha(b"three"), 5)
    assert hash_lines(path, LineRange(start=1, end=3)) == (_sha(b"one\ntwo\r\nthree"), 14)


def test_hash_lines_trailing_newline_adds_no_empty_line(tmp_path: Path) -> None:
    path = tmp_path / "f.txt"
    path.write_bytes(b"a\nb\n")
    assert hash_lines(path, LineRange(start=2, end=2)) == (_sha(b"b\n"), 2)
    assert hash_lines(path, LineRange(start=3, end=3)) is None


def test_hash_lines_range_past_end_or_unreadable_is_none(tmp_path: Path) -> None:
    path = tmp_path / "f.txt"
    path.write_bytes(b"a\nb")
    assert hash_lines(path, LineRange(start=2, end=3)) is None
    assert hash_lines(path, LineRange(start=5, end=9)) is None
    empty = tmp_path / "empty.txt"
    empty.write_bytes(b"")
    assert hash_lines(empty, LineRange(start=1, end=1)) is None
    assert hash_lines(tmp_path / "missing.txt", LineRange(start=1, end=1)) is None


def test_prefix_lines_longest_complete_prefix(tmp_path: Path) -> None:
    path = tmp_path / "f.txt"
    path.write_bytes(b"aa\nbbb\ncccc")
    assert prefix_lines(path, 3) == (LineRange(start=1, end=1), _sha(b"aa\n"), 3)
    assert prefix_lines(path, 6) == (LineRange(start=1, end=1), _sha(b"aa\n"), 3)
    assert prefix_lines(path, 7) == (LineRange(start=1, end=2), _sha(b"aa\nbbb\n"), 7)
    # The last line without a trailing newline is complete only when it ends the file.
    assert prefix_lines(path, 10) == (LineRange(start=1, end=2), _sha(b"aa\nbbb\n"), 7)
    assert prefix_lines(path, 11) == (LineRange(start=1, end=3), _sha(b"aa\nbbb\ncccc"), 11)
    assert prefix_lines(path, 100) == (LineRange(start=1, end=3), _sha(b"aa\nbbb\ncccc"), 11)


def test_prefix_lines_none_when_first_line_does_not_fit(tmp_path: Path) -> None:
    path = tmp_path / "f.txt"
    path.write_bytes(b"long line\nx\n")
    assert prefix_lines(path, 5) is None
    assert prefix_lines(path, 0) is None
    empty = tmp_path / "empty.txt"
    empty.write_bytes(b"")
    assert prefix_lines(empty, 10) is None
    assert prefix_lines(tmp_path / "missing.txt", 10) is None


@settings(
    max_examples=80,
    deadline=None,
    database=None,
    derandomize=True,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(data=st.binary(max_size=80), budget=st.integers(min_value=0, max_value=100))
def test_property_prefix_agrees_with_hash_lines(
    tmp_path_factory: pytest.TempPathFactory, data: bytes, budget: int
) -> None:
    path = tmp_path_factory.mktemp("pfx") / "f.bin"
    path.write_bytes(data)
    got = prefix_lines(path, budget)
    if got is None:
        return
    lines, sha, size = got
    assert size <= budget and lines.start == 1
    assert hash_lines(path, lines) == (sha, size)
    assert _sha(data[:size]) == sha


def test_hash_file_whole_content_and_unreadable(tmp_path: Path) -> None:
    path = tmp_path / "f.bin"
    path.write_bytes(b"one\ntwo\r\nthree")
    assert hash_file(path) == (_sha(b"one\ntwo\r\nthree"), 14)
    empty = tmp_path / "empty.bin"
    empty.write_bytes(b"")
    assert hash_file(empty) == (_sha(b""), 0)
    assert hash_file(tmp_path / "missing.bin") is None
    assert hash_file(tmp_path) is None  # a directory is not a readable file


def test_store_range_helpers_count_hashed_bytes(ws: Path) -> None:
    path = _write(ws, "f.txt", b"aa\nbbb\ncccc")
    store = FingerprintStore(ws)
    assert store.lines(path, LineRange(start=2, end=2)) == (_sha(b"bbb\n"), 4)
    assert store.prefix(path, 7) == (LineRange(start=1, end=2), _sha(b"aa\nbbb\n"), 7)
    assert store.lines(path, LineRange(start=9, end=9)) is None
    assert (store.stats.files_hashed, store.stats.bytes_hashed) == (2, 11)
    assert (store.stats.hits, store.stats.misses) == (0, 0)
