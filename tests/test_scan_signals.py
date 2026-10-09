import os
import subprocess
from pathlib import Path

import pytest

from helpers import write_file
from theforge.context import scan_workspace
from theforge.contracts import ExcludedFile
from theforge.routing.signals import (
    glob_matches,
    keyword_matches,
    normalize_tokens,
    workspace_dependencies,
)


def test_scan_lists_files_and_skips_ignored(tmp_path: Path) -> None:
    write_file(tmp_path, "src/app.py")
    write_file(tmp_path, ".git/config")
    write_file(tmp_path, "node_modules/x.js")
    write_file(tmp_path, ".forge/runs/a.json")
    write_file(tmp_path, ".env", "A=1")
    scan = scan_workspace(tmp_path, ["."])
    assert scan.files == ["src/app.py"]
    assert ExcludedFile(path=".env", reason="secret") in scan.excluded


def test_scan_targets_and_missing(tmp_path: Path) -> None:
    write_file(tmp_path, "api/a.yaml")
    write_file(tmp_path, "jobs/j.py")
    scan = scan_workspace(tmp_path, ["api", "nope"])
    assert scan.files == ["api/a.yaml"]
    assert ExcludedFile(path="nope", reason="missing") in scan.excluded


def test_scan_target_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    (tmp_path / "other").mkdir()
    scan = scan_workspace(root, ["../other"])
    assert scan.files == []
    assert ExcludedFile(path="../other", reason="outside_root") in scan.excluded


def test_scan_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    secret = tmp_path / "outside.txt"
    secret.write_text("s")
    try:
        os.symlink(secret, root / "link.txt")
    except OSError:
        pytest.skip("symlinks not permitted on this host")
    scan = scan_workspace(root, ["."])
    assert scan.files == []
    assert ExcludedFile(path="link.txt", reason="outside_root") in scan.excluded


def test_normalize_tokens() -> None:
    assert normalize_tokens("Análise do Job está LENTO!") == [
        "analise",
        "do",
        "job",
        "esta",
        "lento",
    ]


def test_keyword_matches_multiword_and_order() -> None:
    assert keyword_matches({"glue", "job", "lento"}, ["glue job", "spark", "lento"]) == [
        "glue job",
        "lento",
    ]


def test_workspace_dependencies(tmp_path: Path) -> None:
    write_file(
        tmp_path,
        "pyproject.toml",
        '[project]\ndependencies = ["PySpark>=3.5", "boto3"]\n'
        '[tool.poetry.dependencies]\npython = "^3.11"\nFastAPI = "*"\n',
    )
    write_file(tmp_path, "requirements-dev.txt", "# c\n-r base.txt\naws_glue_libs==4\n\n")
    write_file(
        tmp_path,
        "package.json",
        '{"dependencies": {"express": "4"}, "devDependencies": {"Jest": "29"}}',
    )
    assert workspace_dependencies(tmp_path) == {
        "pyspark",
        "boto3",
        "fastapi",
        "aws-glue-libs",
        "express",
        "jest",
    }


def test_workspace_dependencies_tolerates_garbage(tmp_path: Path) -> None:
    write_file(tmp_path, "pyproject.toml", "not = [toml")
    write_file(tmp_path, "package.json", "{")
    assert workspace_dependencies(tmp_path) == set()


def test_glob_matches() -> None:
    files = ["api/openapi.yaml", "jobs/orders_glue_job.py"]
    assert glob_matches(files, ["openapi.yaml", "*glue*.py", "*.scala"]) == [
        "openapi.yaml",
        "*glue*.py",
    ]


def test_scan_junction_escape(tmp_path: Path) -> None:
    if os.name != "nt":
        pytest.skip("junctions are Windows-only")
    root = tmp_path / "ws"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "leak.txt").write_text("s")
    link = root / "jct"
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(outside)], capture_output=True, check=False
    )
    if result.returncode != 0 or not link.exists():
        pytest.skip("cannot create junction on this host")
    write_file(root, "ok.py")
    scan = scan_workspace(root, ["."])
    assert scan.files == ["ok.py"]
    assert ExcludedFile(path="jct", reason="symlinked_dir") in scan.excluded
    scan_targeted = scan_workspace(root, ["jct"])
    assert scan_targeted.files == []


def test_scan_symlink_to_secret(tmp_path: Path) -> None:
    write_file(tmp_path, ".env", "A=1")
    try:
        os.symlink(tmp_path / ".env", tmp_path / "notes.txt")
    except OSError:
        pytest.skip("symlinks not permitted on this host")
    scan = scan_workspace(tmp_path, ["."])
    assert "notes.txt" not in scan.files
    assert ExcludedFile(path="notes.txt", reason="secret") in scan.excluded


def test_scan_max_files_is_global(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("theforge.context.scan.MAX_FILES", 2)
    for rel in ("a/1.py", "a/2.py", "a/3.py", "b/1.py", "b/2.py"):
        write_file(tmp_path, rel)
    scan = scan_workspace(tmp_path, ["a", "b"])
    assert len(scan.files) == 2
    assert [e for e in scan.excluded if e.reason == "max_files_reached"] == [
        ExcludedFile(path="*", reason="max_files_reached")
    ]


def test_requirements_skip_urls(tmp_path: Path) -> None:
    write_file(
        tmp_path,
        "requirements.txt",
        "https://example.com/pkg.whl\ngit+https://github.com/x/y.git\nrequests==2\n",
    )
    assert workspace_dependencies(tmp_path) == {"requests"}


def test_dependency_file_symlink_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    outside = tmp_path / "evil.toml"
    outside.write_text('[project]\ndependencies = ["leaked"]\n')
    try:
        os.symlink(outside, root / "pyproject.toml")
    except OSError:
        pytest.skip("symlinks not permitted on this host")
    assert workspace_dependencies(root) == set()
