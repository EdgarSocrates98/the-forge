import hashlib
import os
import stat
from pathlib import Path
from typing import Any

import pytest

from helpers import write_file
from theforge.context import BUDGETS, build_context_pack, scan_workspace
from theforge.contracts import ExcludedFile, TaskSpec
from theforge.contracts.canonical import utc_now
from theforge.meta import PRODUCER


def task(root: Path, profile: str = "balanced") -> TaskSpec:
    return TaskSpec(producer=PRODUCER, created_at=utc_now(), id="t1", intent="x",
                    workspace_root=str(root), budget_profile=profile)


def test_pack_selects_by_glob_and_hashes(tmp_path: Path) -> None:
    write_file(tmp_path, "api/openapi.yaml", "openapi: 3.0.0\n")
    write_file(tmp_path, "api/main.py", "x=1\n")
    write_file(tmp_path, ".env", "A=1")
    pack = build_context_pack(task(tmp_path), "api-forge", ["openapi.yaml", "*.yaml"],
                              scan_workspace(tmp_path, ["."]))
    assert [f.path for f in pack.files] == ["api/openapi.yaml"]
    item = pack.files[0]
    assert item.sha256 == hashlib.sha256(b"openapi: 3.0.0\n").hexdigest()
    assert item.bytes == 15 and item.reason == "glob:openapi.yaml,*.yaml"
    assert pack.status == "complete" and not pack.truncated
    assert pack.used_bytes == 15 and pack.budget_bytes == BUDGETS["balanced"]
    assert ExcludedFile(path=".env", reason="secret") in pack.excluded


def test_pack_orders_by_glob_hits_then_path(tmp_path: Path) -> None:
    for name in ("b.yaml", "a.yaml", "openapi.yaml"):
        write_file(tmp_path, name, "x")
    pack = build_context_pack(task(tmp_path), "p", ["*.yaml", "openapi.yaml"],
                              scan_workspace(tmp_path, ["."]))
    assert [f.path for f in pack.files] == ["openapi.yaml", "a.yaml", "b.yaml"]


def test_pack_respects_budget(tmp_path: Path) -> None:
    write_file(tmp_path, "big.txt", "x" * 70_000)
    write_file(tmp_path, "small.txt", "0123456789")
    pack = build_context_pack(task(tmp_path, "economy"), "p", ["*.txt"],
                              scan_workspace(tmp_path, ["."]))
    assert [f.path for f in pack.files] == ["small.txt"]
    assert ExcludedFile(path="big.txt", reason="budget") in pack.excluded
    assert pack.truncated and pack.status == "truncated"


def test_pack_bounds_read_when_file_grows_after_stat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_file(tmp_path, "small.txt", "0123456789")
    scan = scan_workspace(tmp_path, ["."])
    target = tmp_path / "small.txt"
    with target.open("ab") as fh:
        fh.write(b"x" * 70_000)
    real_stat = Path.stat

    def stale_stat(self: Path, *args: Any, **kwargs: Any) -> os.stat_result:
        result = real_stat(self, *args, **kwargs)
        if self.name == "small.txt":
            fields = list(result)
            fields[stat.ST_SIZE] = 10
            return os.stat_result(fields)
        return result

    monkeypatch.setattr(Path, "stat", stale_stat)
    pack = build_context_pack(task(tmp_path, "economy"), "p", ["*.txt"], scan)
    assert pack.files == []
    assert ExcludedFile(path="small.txt", reason="budget") in pack.excluded
    assert pack.truncated and pack.used_bytes <= pack.budget_bytes


def test_pack_without_globs_is_empty(tmp_path: Path) -> None:
    write_file(tmp_path, "a.txt", "x")
    pack = build_context_pack(task(tmp_path), "p", [], scan_workspace(tmp_path, ["."]))
    assert pack.files == [] and pack.used_bytes == 0
