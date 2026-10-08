"""Deterministic synthetic workspaces for the benchmark (requirement 11.1). Stdlib only.

The same ``(files, seed)`` always yields byte-identical trees: a fixed rotation of ``.md``,
``.txt``, ``.py`` and ``.json`` files, each one of the fixed ``SIZES``, ``FILES_PER_DIR``
files per directory, ASCII with LF line endings. Names never look like secrets and no
directory is one the scan ignores, so every generated file is a scan candidate.

Workspaces are written only where the caller points (the benchmark uses a temporary
directory) and never into a non-empty directory.
"""

from __future__ import annotations

import random
from collections.abc import Iterator
from pathlib import Path
from typing import Final

EXTENSIONS: Final = (".md", ".txt", ".py", ".json")
SIZES: Final = (256, 1024, 4096)
FILES_PER_DIR: Final = 100
_WORDS: Final = (
    "forge",
    "context",
    "budget",
    "profile",
    "route",
    "signal",
    "provider",
    "capability",
    "workspace",
    "receipt",
    "result",
    "evidence",
    "hash",
    "scan",
    "glob",
    "tier",
    "cache",
    "orders",
    "report",
    "pipeline",
    "table",
    "query",
    "schema",
    "metric",
    "review",
)
_HEADERS: Final = {
    ".md": ("# Document {index:05d}\n\n", ""),
    ".txt": ("note {index:05d}\n", ""),
    ".py": ('"""Module {index:05d}."""\n', "# "),
}


def _lines(rng: random.Random, prefix: str, size: int) -> str:
    """Lines of ASCII words, each starting with ``prefix``, cut to exactly ``size`` chars."""
    out: list[str] = []
    length = 0
    while length < size:
        words = [rng.choice(_WORDS) for _ in range(rng.randint(4, 10))]
        line = prefix + " ".join(words) + "\n"
        out.append(line)
        length += len(line)
    return "".join(out)[:size]


def _content(index: int, ext: str, size: int, rng: random.Random) -> bytes:
    if ext == ".json":
        head = f'{{"id": {index}, "text": "'
        tail = '"}\n'
        body = _lines(rng, "", size - len(head) - len(tail)).replace("\n", " ")
        text = head + body + tail
    else:
        template, prefix = _HEADERS[ext]
        header = template.format(index=index)
        text = header + _lines(rng, prefix, size - len(header) - 1) + "\n"
    data = text.encode("ascii")
    if len(data) != size:  # guards the fixed-size contract
        raise AssertionError(f"generated {len(data)} bytes for a {size}-byte file")
    return data


def plan_workspace(files: int, *, seed: int = 0) -> Iterator[tuple[str, bytes]]:
    """``(relative POSIX path, content)`` for every file of the workspace, in order."""
    if files < 1:
        raise ValueError(f"files must be >= 1, got {files}")
    return _plan(files, seed)


def _plan(files: int, seed: int) -> Iterator[tuple[str, bytes]]:
    rng = random.Random(seed)
    for index in range(files):
        ext = EXTENSIONS[index % len(EXTENSIONS)]
        size = rng.choice(SIZES)
        rel = f"dir{index // FILES_PER_DIR:03d}/file{index:05d}{ext}"
        yield rel, _content(index, ext, size, rng)


def generate_workspace(root: Path, files: int, *, seed: int = 0) -> None:
    """Write the deterministic workspace of ``files`` files under ``root`` (empty or new)."""
    plan = plan_workspace(files, seed=seed)  # validates ``files`` before touching the disk
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise ValueError(f"{root} is not empty; refusing to generate a workspace into it")
    for rel, data in plan:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
