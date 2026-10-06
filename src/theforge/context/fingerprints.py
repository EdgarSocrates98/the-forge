"""FingerprintStore: conservative sha256 reuse, cached outside the workspace (ADR 0009 model).

A cached hash is reused only when ``size``, ``mtime_ns``, ``ctime_ns``, ``ino``, ``dev`` and
the resolved path all equal the current ``stat`` **and** the entry was recorded more than
``RACY_WINDOW_NS`` after the file's mtime. Anything else reads and hashes the content; the
new entry is recorded only when ``stat`` is identical before and after the read.

The cache document (``theforge/FingerprintCache/v1``, core-only) lives at
``user_cache_dir()/context/<digest12>.json`` (``digest12`` = first 12 hex of the sha256 of
the resolved root as a POSIX string), is re-read with ``strict=True`` and discarded when it
is unreadable, malformed, of another version or of another root. It is written at most once
per run, atomically, after ``security.redact``.

This module is also the single owner of line-range hashing (``hash_lines``/
``prefix_lines``), used by the broker and by context re-verification. Newline rule: lines
are delimited by ``\\n`` only (``\\r\\n`` keeps its ``\\r`` inside the line); a last line
without ``\\n`` counts as-is; a trailing ``\\n`` does not start an extra empty line.
"""

import contextlib
import hashlib
import json
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Literal

from theforge.contracts.base import ContractError, from_dict, to_dict
from theforge.contracts.context import LineRange
from theforge.contracts.types import check_sha256
from theforge.registry.config import user_cache_dir
from theforge.security.redact import redact

CACHE_SCHEMA: Final = "theforge/FingerprintCache/v1"
RACY_WINDOW_NS: Final = 2_000_000_000  # 2 s
_CHUNK: Final = 1 << 16


@dataclass(frozen=True, kw_only=True)
class FingerprintEntry:
    path: str  # resolved path, POSIX string
    sha256: str
    size: int
    mtime_ns: int
    ctime_ns: int
    ino: int
    dev: int
    recorded_ns: int

    def __post_init__(self) -> None:
        check_sha256(self.sha256, field="sha256")
        for name in ("size", "mtime_ns", "ctime_ns", "ino", "dev", "recorded_ns"):
            if getattr(self, name) < 0:
                raise ContractError(f"{name}: must be >= 0")


@dataclass(frozen=True, kw_only=True)
class FingerprintCache:
    """On-disk document; keys of ``entries`` are workspace-relative POSIX paths."""

    schema: Literal["theforge/FingerprintCache/v1"]
    root: str
    entries: dict[str, FingerprintEntry] = field(default_factory=dict)


@dataclass
class HashStats:
    files_hashed: int = 0
    bytes_hashed: int = 0
    hits: int = 0
    misses: int = 0


@dataclass(frozen=True, kw_only=True)
class Fingerprint:
    sha256: str
    size: int
    reused: bool


_StatKey = tuple[int, int, int, int, int]


def _stat_key(st: os.stat_result) -> _StatKey:
    return (st.st_size, st.st_mtime_ns, st.st_ctime_ns, st.st_ino, st.st_dev)


def _read_bytes(path: Path) -> bytes:
    """Whole-file read (module-level so tests can prove a hit never reads content)."""
    with path.open("rb") as fh:
        return fh.read()


class FingerprintStore:
    """Per-run fingerprint cache for one workspace root. Never raises on cache problems."""

    def __init__(self, root: Path, *, cache_dir: Path | None = None,
                 enabled: bool = True) -> None:
        self.root = root.resolve()
        self.root_key = self.root.as_posix()
        self.enabled = enabled
        self.stats = HashStats()
        self.warnings: list[str] = []
        self._entries: dict[str, FingerprintEntry] = {}
        base = cache_dir if cache_dir is not None else user_cache_dir()
        digest = hashlib.sha256(self.root_key.encode("utf-8")).hexdigest()[:12]
        self.path: Path | None = base / "context" / f"{digest}.json"
        if not enabled:
            return
        if _inside(self.path, self.root):
            self.warnings.append(
                f"fingerprint cache disabled: {self.path} is inside the workspace")
            self.path = None
            return
        self._load()

    # --- whole files ---------------------------------------------------------------------

    def file(self, rel: str, resolved: Path) -> Fingerprint | None:
        """sha256 of ``resolved``: reused when provably unchanged, else read. None = unreadable."""
        try:
            before = os.stat(resolved)
        except OSError:
            return None
        entry = self._entries.get(rel) if self.enabled else None
        if entry is not None and self._trusted(entry, resolved, before):
            self.stats.hits += 1
            return Fingerprint(sha256=entry.sha256, size=entry.size, reused=True)
        self.stats.misses += 1
        self._entries.pop(rel, None)
        try:
            data = _read_bytes(resolved)
            after = os.stat(resolved)
        except OSError:
            return None
        recorded_ns = time.time_ns()
        sha = hashlib.sha256(data).hexdigest()
        self.stats.files_hashed += 1
        self.stats.bytes_hashed += len(data)
        if (self.enabled and _stat_key(before) == _stat_key(after)
                and after.st_size == len(data)):
            self._entries[rel] = FingerprintEntry(
                path=resolved.as_posix(), sha256=sha, size=after.st_size,
                mtime_ns=after.st_mtime_ns, ctime_ns=after.st_ctime_ns, ino=after.st_ino,
                dev=after.st_dev, recorded_ns=recorded_ns)
        return Fingerprint(sha256=sha, size=len(data), reused=False)

    @staticmethod
    def _trusted(entry: FingerprintEntry, resolved: Path, st: os.stat_result) -> bool:
        same = (entry.path == resolved.as_posix()
                and (entry.size, entry.mtime_ns, entry.ctime_ns, entry.ino, entry.dev)
                == _stat_key(st))
        return same and entry.recorded_ns - entry.mtime_ns > RACY_WINDOW_NS

    # --- line ranges (never cached; counted as hashed) -----------------------------------

    def lines(self, resolved: Path, lines: LineRange) -> tuple[str, int] | None:
        got = hash_lines(resolved, lines)
        if got is not None:
            self._count(got[1])
        return got

    def prefix(self, resolved: Path, max_bytes: int) -> tuple[LineRange, str, int] | None:
        got = prefix_lines(resolved, max_bytes)
        if got is not None:
            self._count(got[2])
        return got

    def _count(self, size: int) -> None:
        self.stats.files_hashed += 1
        self.stats.bytes_hashed += size

    # --- persistence ---------------------------------------------------------------------

    def _load(self) -> None:
        assert self.path is not None
        try:
            if not self.path.exists():
                return
            doc = json.loads(self.path.read_text(encoding="utf-8"))
            cache = from_dict(FingerprintCache, doc, "$", strict=True)
            if cache.root != self.root_key:
                raise ContractError(f"root {cache.root!r} is not {self.root_key!r}")
        except (OSError, ValueError, RecursionError) as exc:
            # ContractError and JSONDecodeError are ValueErrors.
            self.warnings.append(f"fingerprint cache discarded ({self.path}): {exc}")
            return
        self._entries = dict(cache.entries)

    def save(self) -> None:
        """Write the cache once, atomically, after redaction. Failures become warnings."""
        if not self.enabled or self.path is None:
            return
        path = self.path
        entries: dict[str, FingerprintEntry] = {}
        for rel, entry in sorted(self._entries.items()):
            item = {"rel": rel, **to_dict(entry)}
            if redact(item) != item:
                self.warnings.append(
                    f"fingerprint for {rel!r} not cached: it contains secret-shaped values")
                continue
            entries[rel] = entry
        document = to_dict(FingerprintCache(schema=CACHE_SCHEMA, root=self.root_key,
                                            entries=entries))
        try:
            if redact(document) != document:
                # A redacted copy would never match on the strict re-read: refuse it.
                path.unlink(missing_ok=True)
                self.warnings.append(
                    f"fingerprint cache not written ({path}): redaction would alter it "
                    "(secret-shaped workspace path)")
                return
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.stem}-", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(json.dumps(document, indent=1, sort_keys=True))
                os.replace(tmp, path)
            except BaseException:
                with contextlib.suppress(OSError):
                    os.unlink(tmp)
                raise
        except OSError as exc:
            self.warnings.append(f"fingerprint cache not written ({path}): {exc}")


def _inside(path: Path, root: Path) -> bool:
    try:
        return path.resolve().is_relative_to(root)
    except OSError:
        return False


# --- line-range hashing: single owner of the newline rule ---------------------------------


def hash_file(resolved: Path) -> tuple[str, int] | None:
    """(sha256, bytes) of the whole file, streamed in chunks. None = unreadable."""
    digest = hashlib.sha256()
    size = 0
    try:
        with resolved.open("rb") as fh:
            while chunk := fh.read(_CHUNK):
                digest.update(chunk)
                size += len(chunk)
    except OSError:
        return None
    return digest.hexdigest(), size


def hash_lines(resolved: Path, lines: LineRange) -> tuple[str, int] | None:
    """(sha256, bytes) of lines ``start..end`` (1-based, inclusive).

    None when the file is unreadable or the range goes past the last line.
    """
    digest = hashlib.sha256()
    size = 0
    number = 0
    try:
        with resolved.open("rb") as fh:
            for number, line in enumerate(fh, start=1):  # binary iteration splits on b"\n"
                if number < lines.start:
                    continue
                digest.update(line)
                size += len(line)
                if number == lines.end:
                    return digest.hexdigest(), size
    except OSError:
        return None
    return None


def prefix_lines(resolved: Path, max_bytes: int) -> tuple[LineRange, str, int] | None:
    """Longest prefix of complete lines within ``max_bytes`` (at least one line).

    A last line without ``\\n`` is complete only when it ends the file. None when the file
    is unreadable or empty, or when its first line alone exceeds ``max_bytes``.
    """
    if max_bytes <= 0:
        return None
    try:
        with resolved.open("rb") as fh:
            data = fh.read(max_bytes + 1)
    except OSError:
        return None
    if len(data) <= max_bytes:
        prefix = data  # whole file fits: an unterminated last line is complete
    else:
        cut = data.rfind(b"\n", 0, max_bytes)
        prefix = data[:cut + 1] if cut >= 0 else b""
    if not prefix:
        return None
    count = prefix.count(b"\n") + (0 if prefix.endswith(b"\n") else 1)
    return (LineRange(start=1, end=count), hashlib.sha256(prefix).hexdigest(), len(prefix))
