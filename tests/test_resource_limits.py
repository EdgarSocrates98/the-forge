"""Adversarial hard-read-limit tests for ``context/resources.py`` (cycle 16.1 §5.4).

The service enforces an internal ceiling the caller can never widen by
argument, validates hostile ``max_bytes``/``offset`` values, refuses
special files, and signals truncation/redaction/integrity honestly —
every failure is a typed ``ResourceFailure``, never a crash or a silent
success.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from theforge.context import resources
from theforge.context.resources import (
    ForgeResourceRoot,
    ResourceErrorKind,
    ResourceFailure,
    ResourceResolver,
)
from theforge.contracts.base import from_dict
from theforge.contracts.specialist import AgenticManifest


def _resolver(tmp: Path, resources_: list[dict]) -> tuple[ResourceResolver, Path]:
    root = tmp / "tforge"
    root.mkdir(parents=True)
    (root / "forge.agentic.json").write_text(
        json.dumps(
            {
                "schema": "forge/SpecialistAgenticManifest/v1",
                "id": "tforge",
                "version": "0.0.1",
                "resources": resources_,
            }
        ),
        encoding="utf-8",
    )
    manifest = from_dict(
        AgenticManifest,
        json.loads((root / "forge.agentic.json").read_text(encoding="utf-8")),
    )
    fr = ForgeResourceRoot(forge_id="tforge", root=root, origin="explicit", manifest=manifest)
    return ResourceResolver([fr]), root


def _file_root(
    tmp: Path, body: bytes, name: str = "knowledge/d.md"
) -> tuple[ResourceResolver, Path]:
    res, root = _resolver(tmp, [{"id": "doc", "kind": "knowledge", "location": name}])
    target = root / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(body)
    return res, root


# --- max_bytes ------------------------------------------------------------


def test_max_bytes_negative_and_non_int_rejected(tmp_path: Path) -> None:
    res, _ = _file_root(tmp_path, b"payload")
    for bad in (-1, -(10**9)):
        with pytest.raises(ResourceFailure) as ei:
            res.get("tforge:doc", max_bytes=bad)
        assert ei.value.kind == ResourceErrorKind.INVALID
    for non_int in (1.5, "100", None, True, False):
        with pytest.raises(ResourceFailure) as ei:
            res.get("tforge:doc", max_bytes=non_int)  # type: ignore[arg-type]
        assert ei.value.kind == ResourceErrorKind.INVALID


def test_max_bytes_cannot_exceed_hard_ceiling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Shrink the ceiling so the adversarial request stays cheap — the same
    # code path clamps the real MAX_READ_BYTES.
    monkeypatch.setattr(resources, "MAX_READ_BYTES", 16)
    body = b"a" * 100
    res, _ = _file_root(tmp_path, body)
    out = res.get("tforge:doc", max_bytes=10**12)
    assert out.served_bytes == 16
    assert out.capped
    assert out.truncated
    assert out.file_bytes == 100
    # And a request below the cap is honored without the flag.
    out2 = res.get("tforge:doc", max_bytes=8)
    assert out2.served_bytes == 8 and not out2.capped and out2.truncated


def test_hard_ceiling_is_real_and_above_default() -> None:
    assert resources.MAX_READ_BYTES >= resources.DEFAULT_MAX_BYTES
    assert isinstance(resources.MAX_READ_BYTES, int)


def test_hard_ceiling_enforced_with_real_file(tmp_path: Path) -> None:
    # ~1 MiB file — proves the shipped cap actually binds, not just the
    # monkeypatched one.
    res, _ = _file_root(tmp_path, b"z" * (resources.MAX_READ_BYTES + 64))
    out = res.get("tforge:doc", max_bytes=resources.MAX_READ_BYTES * 4)
    assert out.served_bytes == resources.MAX_READ_BYTES
    assert out.capped and out.truncated


def test_max_bytes_zero_is_empty_window(tmp_path: Path) -> None:
    res, _ = _file_root(tmp_path, b"payload")
    out = res.get("tforge:doc", max_bytes=0)
    assert out.served_bytes == 0 and out.truncated


# --- offset ---------------------------------------------------------------


def test_offset_negative_and_non_int_rejected(tmp_path: Path) -> None:
    res, _ = _file_root(tmp_path, b"payload")
    for bad in (-1, -100):
        with pytest.raises(ResourceFailure) as ei:
            res.get("tforge:doc", offset=bad)
        assert ei.value.kind == ResourceErrorKind.INVALID
    for non_int in (0.5, "3", None, True):
        with pytest.raises(ResourceFailure) as ei:
            res.get("tforge:doc", offset=non_int)  # type: ignore[arg-type]
        assert ei.value.kind == ResourceErrorKind.INVALID


def test_offset_beyond_eof_is_typed_error(tmp_path: Path) -> None:
    res, _ = _file_root(tmp_path, b"12345")
    with pytest.raises(ResourceFailure) as ei:
        res.get("tforge:doc", offset=6)
    assert ei.value.kind == ResourceErrorKind.INVALID
    # offset == size is the legal EOF marker: empty page, no truncation.
    out = res.get("tforge:doc", offset=5)
    assert out.served_bytes == 0 and not out.truncated


def test_pagination_reassembles_whole_file(tmp_path: Path) -> None:
    body = (b"line %03d\n" % 0) + b"".join(b"line %03d\n" % i for i in range(1, 40))
    res, _ = _file_root(tmp_path, body)
    pages: list[bytes] = []
    offset = 0
    while True:
        out = res.get("tforge:doc", offset=offset, max_bytes=64)
        pages.append((out.text or "").encode("utf-8"))
        if not out.truncated:
            break
        offset += out.served_bytes
        assert offset <= (out.file_bytes or 0)
    assert b"".join(pages) == body


# --- special / protected / hostile targets --------------------------------


def test_special_file_refused_not_blocked_on(tmp_path: Path) -> None:
    if not hasattr(os, "mkfifo"):
        pytest.skip("fifo unsupported on this platform")
    res, root = _resolver(
        tmp_path, [{"id": "fifo", "kind": "knowledge", "location": "knowledge/pipe"}]
    )
    (root / "knowledge").mkdir()
    try:
        os.mkfifo(root / "knowledge" / "pipe")
    except OSError:
        pytest.skip("mkfifo refused by platform/policy")
    with pytest.raises(ResourceFailure) as ei:
        res.get("tforge:fifo")
    assert ei.value.kind == ResourceErrorKind.UNAVAILABLE


def test_protected_file_permission_denied(tmp_path: Path) -> None:
    res, root = _file_root(tmp_path, b"secret")
    target = root / "knowledge" / "d.md"
    target.chmod(0o000)
    try:
        if os.access(target, os.R_OK):  # e.g. running as root
            pytest.skip("filesystem does not enforce mode bits for this user")
        with pytest.raises(ResourceFailure) as ei:
            res.get("tforge:doc")
        assert ei.value.kind == ResourceErrorKind.PERMISSION_DENIED
    finally:
        target.chmod(0o644)


def test_binary_content_is_corrupted_not_served(tmp_path: Path) -> None:
    res, _ = _file_root(tmp_path, b"\x89PNG\r\n\x1a\n\xff\xfe\x00", name="knowledge/b.md")
    with pytest.raises(ResourceFailure) as ei:
        res.get("tforge:doc")
    assert ei.value.kind == ResourceErrorKind.CORRUPTED


def test_symlink_inside_root_served_outside_blocked(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    res, root = _resolver(
        tmp_path,
        [
            {"id": "in", "kind": "knowledge", "location": "links/in.md"},
            {"id": "out", "kind": "knowledge", "location": "links/out.md"},
        ],
    )
    (root / "links").mkdir()
    (root / "real.md").write_text("inside", encoding="utf-8")
    outside = tmp_path_factory.mktemp("outside") / "s.md"
    outside.write_text("outside", encoding="utf-8")
    try:
        (root / "links" / "in.md").symlink_to(root / "real.md")
        (root / "links" / "out.md").symlink_to(outside)
    except OSError:
        pytest.skip("symlink unsupported on this platform/policy")
    assert res.get("tforge:in").text == "inside"
    with pytest.raises(ResourceFailure) as ei:
        res.get("tforge:out")
    assert ei.value.kind == ResourceErrorKind.BLOCKED_BY_POLICY


def test_absent_and_unindexed_resources_are_typed(tmp_path: Path) -> None:
    res, _ = _resolver(
        tmp_path, [{"id": "gone", "kind": "knowledge", "location": "knowledge/x.md"}]
    )
    with pytest.raises(ResourceFailure) as ei:
        res.get("tforge:gone")
    assert ei.value.kind == ResourceErrorKind.UNAVAILABLE
    with pytest.raises(ResourceFailure) as ei:
        res.get("tforge:never-declared")
    assert ei.value.kind == ResourceErrorKind.NOT_INDEXED
    with pytest.raises(ResourceFailure) as ei:
        res.get("ghost-forge:x")
    assert ei.value.kind == ResourceErrorKind.NOT_INSTALLED


def test_denied_suffix_and_denied_dir_target(tmp_path: Path) -> None:
    res, root = _resolver(tmp_path, [{"id": "exe", "kind": "tool", "location": "bin/x.exe"}])
    (root / "bin").mkdir()
    (root / "bin" / "x.exe").write_bytes(b"MZ")
    with pytest.raises(ResourceFailure) as ei:
        res.get("tforge:exe")
    assert ei.value.kind == ResourceErrorKind.BLOCKED_BY_POLICY


# --- signaling: truncation, redaction, listing, integrity ------------------


def test_truncation_signals_served_window(tmp_path: Path) -> None:
    res, _ = _file_root(tmp_path, b"0123456789")
    out = res.get("tforge:doc", max_bytes=4)
    assert out.truncated and out.served_bytes == 4 and out.file_bytes == 10
    assert out.text == "0123"


def test_output_is_redacted(tmp_path: Path) -> None:
    res, root = _resolver(tmp_path, [{"id": "cfg", "kind": "config", "location": "cfg/s.yaml"}])
    (root / "cfg").mkdir()
    (root / "cfg" / "s.yaml").write_text(
        'aws_secret_access_key: "AKIAIOSFODNN7EXAMPLE"\n', encoding="utf-8"
    )
    out = res.get("tforge:cfg")
    assert "AKIAIOSFODNN7EXAMPLE" not in (out.text or "")
    assert out.redacted


def test_large_directory_listing_capped(tmp_path: Path) -> None:
    res, root = _resolver(tmp_path, [{"id": "dir", "kind": "rule", "location": "rules"}])
    d = root / "rules"
    d.mkdir()
    for i in range(resources.MAX_LISTING + 10):
        (d / f"r{i:04d}.yaml").write_text("x", encoding="utf-8")
    out = res.get("tforge:dir")
    assert out.content_type == "listing"
    assert out.listing_truncated
    assert out.entries is not None and len(out.entries) == resources.MAX_LISTING


def test_integrity_scopes_file_vs_window(tmp_path: Path) -> None:
    body = b"integrity payload\n" * 4
    res, _ = _file_root(tmp_path, body)
    whole = res.get("tforge:doc", integrity=True)
    assert whole.sha256 == hashlib.sha256(body).hexdigest()
    assert whole.sha256_scope == "file"
    window = res.get("tforge:doc", max_bytes=8, integrity=True)
    assert window.sha256_scope == "window"
    assert window.sha256 == hashlib.sha256(body[:8]).hexdigest()
    paged = res.get("tforge:doc", offset=4, integrity=True)
    assert paged.sha256_scope == "window"
    assert paged.sha256 == hashlib.sha256(body[4:]).hexdigest()
