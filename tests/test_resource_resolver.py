"""Resource resolver & retrieval (Onda 04) — roots, search, typed reads.

Gate §10.8: every ``available`` resource has a real discovery/access path;
unavailability is always a typed state, never a disguised empty result.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from theforge.context.resources import (
    ForgeResourceRoot,
    ResourceErrorKind,
    ResourceFailure,
    ResourceResolver,
    discover_roots,
    split_identity,
)
from theforge.contracts.base import from_dict
from theforge.contracts.specialist import AgenticManifest


def _write_manifest(root: Path, resources: list[dict], fid: str = "tforge") -> None:
    (root / "forge.json").write_text(json.dumps({"forge_id": fid}), encoding="utf-8")
    (root / "forge.agentic.json").write_text(
        json.dumps(
            {
                "schema": "forge/SpecialistAgenticManifest/v1",
                "id": fid,
                "version": "0.0.1",
                "skills": ["legacy-skill"],
                "agents": ["legacy-agent"],
                "resources": resources,
            }
        ),
        encoding="utf-8",
    )


def _root(tmp: Path, fid: str = "tforge", resources: list[dict] | None = None) -> Path:
    root = tmp / fid
    root.mkdir(parents=True)
    _write_manifest(root, resources or [], fid)
    return root


def _resolver(tmp: Path, resources: list[dict]) -> tuple[ResourceResolver, Path]:
    root = _root(tmp, resources=resources)
    manifest = from_dict(
        AgenticManifest,
        json.loads((root / "forge.agentic.json").read_text(encoding="utf-8")),
    )
    fr = ForgeResourceRoot(
        forge_id="tforge", root=root, origin="explicit", manifest=manifest
    )
    return ResourceResolver([fr]), root


def test_split_identity_nested_kind() -> None:
    assert split_identity("tforge:agent:glue-arch") == ("tforge", "agent:glue-arch")


def test_split_identity_rejects_bad() -> None:
    for bad in ("noforge", ":x", "f:", "", "::"):
        with pytest.raises(ResourceFailure) as ei:
            split_identity(bad)
        assert ei.value.kind == ResourceErrorKind.INVALID


def test_list_filters(tmp_path: Path) -> None:
    res, _ = _resolver(
        tmp_path,
        [
            {"id": "a", "kind": "skill", "location": "skills/a/SKILL.md",
             "resource_class": "agentic"},
            {"id": "b", "kind": "contract", "location": "contracts/x.yaml",
             "resource_class": "validation"},
        ],
    )
    assert {r.entry.id for r in res.list()} >= {"a", "b", "legacy-skill", "legacy-agent"}
    assert [r.entry.id for r in res.list(kind="contract")] == ["b"]
    assert {r.entry.id for r in res.list(resource_class="agentic")} == {
        "a", "legacy-skill", "legacy-agent",
    }
    assert [r.entry.id for r in res.list(availability="conditional")] == [
        "legacy-skill", "legacy-agent",
    ]
    assert res.list(forge_id="other") == []


def test_search_ranks_id_first(tmp_path: Path) -> None:
    res, _ = _resolver(
        tmp_path,
        [
            {"id": "spark-bench", "kind": "eval", "location": "evals/x",
             "description": "unrelated"},
            {"id": "bench-helper", "kind": "skill", "location": "skills/b/SKILL.md",
             "description": "mentions spark-bench"},
        ],
    )
    hits = res.search("spark-bench")
    assert [h.entry.id for h in hits][:1] == ["spark-bench"]
    assert res.search("") == []
    assert res.search("zzz") == []


def test_describe_unavailable_is_typed(tmp_path: Path) -> None:
    res, _ = _resolver(tmp_path, [])
    with pytest.raises(ResourceFailure) as ei:
        res.describe("tforge:legacy-skill")
    assert ei.value.kind == ResourceErrorKind.UNAVAILABLE


def test_describe_not_indexed_and_not_installed(tmp_path: Path) -> None:
    res, _ = _resolver(tmp_path, [])
    with pytest.raises(ResourceFailure) as ei:
        res.describe("tforge:ghost")
    assert ei.value.kind == ResourceErrorKind.NOT_INDEXED
    with pytest.raises(ResourceFailure) as ei:
        res.describe("ghost-forge:anything")
    assert ei.value.kind == ResourceErrorKind.NOT_INSTALLED


def test_get_text_window_and_integrity(tmp_path: Path) -> None:
    res, root = _resolver(
        tmp_path,
        [{"id": "doc", "kind": "knowledge", "location": "knowledge/d.md"}],
    )
    body = "line one\nline two\n" * 3
    (root / "knowledge").mkdir()
    (root / "knowledge" / "d.md").write_bytes(body.encode("utf-8"))
    full = res.get("tforge:doc", integrity=True)
    assert full.content_type == "text"
    assert full.text == body
    assert not full.truncated
    assert full.sha256 == hashlib.sha256(body.encode()).hexdigest()
    assert full.sha256_scope == "file"
    window = res.get("tforge:doc", max_bytes=8)
    assert window.truncated and window.text == body[:8]
    assert window.sha256_scope == "window"
    tail = res.get("tforge:doc", offset=9, max_bytes=8)
    assert tail.text == body[9:17]


def test_get_redacts_secrets(tmp_path: Path) -> None:
    res, root = _resolver(
        tmp_path,
        [{"id": "cfg", "kind": "config", "location": "config/s.yaml"}],
    )
    (root / "config").mkdir()
    (root / "config" / "s.yaml").write_text(
        'aws_secret_access_key: "AKIAIOSFODNN7EXAMPLE"\nplain: 1\n', encoding="utf-8"
    )
    out = res.get("tforge:cfg")
    assert "AKIAIOSFODNN7EXAMPLE" not in (out.text or "")
    assert out.redacted


def test_get_directory_listing_bounded(tmp_path: Path) -> None:
    res, root = _resolver(
        tmp_path,
        [{"id": "rules", "kind": "rule", "location": "rules/catalog"}],
    )
    d = root / "rules" / "catalog"
    d.mkdir(parents=True)
    for i in range(7):
        (d / f"r{i}.yaml").write_text("x", encoding="utf-8")
    out = res.get("tforge:rules")
    assert out.content_type == "listing"
    assert out.entries == [f"r{i}.yaml" for i in range(7)]


def test_get_denies_executable(tmp_path: Path) -> None:
    res, root = _resolver(
        tmp_path,
        [{"id": "tool", "kind": "tool", "location": "bin/x.exe"}],
    )
    (root / "bin").mkdir()
    (root / "bin" / "x.exe").write_bytes(b"MZ")
    with pytest.raises(ResourceFailure) as ei:
        res.get("tforge:tool")
    assert ei.value.kind == ResourceErrorKind.BLOCKED_BY_POLICY


def test_get_blocks_traversal_location(tmp_path: Path) -> None:
    # Contract rejects ".." at parse — this exercises the resolver's own
    # containment as defense-in-depth against a hand-built rogue entry.
    from dataclasses import MISSING, fields
    from types import SimpleNamespace

    from theforge.contracts.specialist import ResourceEntry

    rogue = object.__new__(ResourceEntry)
    for f_ in fields(ResourceEntry):
        if f_.default is not MISSING:
            object.__setattr__(rogue, f_.name, f_.default)
        elif f_.default_factory is not MISSING:  # type: ignore[misc]
            object.__setattr__(rogue, f_.name, f_.default_factory())
        else:
            object.__setattr__(rogue, f_.name, None)
    object.__setattr__(rogue, "id", "evil")
    object.__setattr__(rogue, "kind", "knowledge")
    object.__setattr__(rogue, "location", "../outside.md")
    object.__setattr__(rogue, "availability", "available")

    root = _root(tmp_path, resources=[])
    manifest = SimpleNamespace(skills=[], agents=[], resources=[rogue])
    fr = ForgeResourceRoot(
        forge_id="tforge", root=root, origin="explicit", manifest=manifest
    )
    res = ResourceResolver([fr])
    with pytest.raises(ResourceFailure) as ei:
        res.get("tforge:evil")
    assert ei.value.kind == ResourceErrorKind.BLOCKED_BY_POLICY


def test_get_missing_location_unavailable(tmp_path: Path) -> None:
    res, _ = _resolver(
        tmp_path,
        [{"id": "gone", "kind": "example", "location": "examples/gone.md"}],
    )
    with pytest.raises(ResourceFailure) as ei:
        res.get("tforge:gone")
    assert ei.value.kind == ResourceErrorKind.UNAVAILABLE


def test_get_corrupted_encoding(tmp_path: Path) -> None:
    res, root = _resolver(
        tmp_path,
        [{"id": "blob", "kind": "fixture", "location": "fixtures/b.bin.md"}],
    )
    (root / "fixtures").mkdir()
    (root / "fixtures" / "b.bin.md").write_bytes(b"\xff\xfe\x00\x01\xff")
    with pytest.raises(ResourceFailure) as ei:
        res.get("tforge:blob")
    assert ei.value.kind == ResourceErrorKind.CORRUPTED


def test_get_symlink_escape_blocked(tmp_path: Path, tmp_path_factory) -> None:
    res, root = _resolver(
        tmp_path,
        [{"id": "lnk", "kind": "knowledge", "location": "knowledge/link.md"}],
    )
    outside = tmp_path_factory.mktemp("outside") / "secret.md"
    outside.write_text("top secret", encoding="utf-8")
    (root / "knowledge").mkdir()
    link = root / "knowledge" / "link.md"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlink unsupported on this platform/policy")
    with pytest.raises(ResourceFailure) as ei:
        res.get("tforge:lnk")
    assert ei.value.kind == ResourceErrorKind.BLOCKED_BY_POLICY


def test_discover_roots_explicit_and_checkout(tmp_path: Path) -> None:
    # explicit root
    exp = _root(tmp_path / "exp", fid="exp-forge")
    roots = discover_roots(None, explicit=[("exp-forge", exp)])
    assert [r.forge_id for r in roots] == ["exp-forge"]
    assert roots[0].origin == "explicit"
    # workspace checkout via kit.discover_projects layout (needs .git)
    ws = tmp_path / "ws"
    checkout = _root(ws / "ck-forge", fid="ck-forge")
    (checkout / ".git").mkdir()
    roots = discover_roots(ws)
    assert any(r.forge_id == "ck-forge" and r.origin == "checkout" for r in roots)


def test_resolve_identity_roundtrip(tmp_path: Path) -> None:
    res, root = _resolver(
        tmp_path,
        [{"id": "s1", "kind": "skill", "location": "skills/s1/SKILL.md"}],
    )
    (root / "skills" / "s1").mkdir(parents=True)
    (root / "skills" / "s1" / "SKILL.md").write_text("# s1", encoding="utf-8")
    ref = res.describe("tforge:s1")
    assert ref.identity == "tforge:s1"
    assert ref.path and ref.path.name == "SKILL.md"
    assert ref.origin == "explicit"
