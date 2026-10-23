"""forge_context v1.3.0 — install-2.0 §9: transactions, stable resource
ids and multi-forge routing.

The canonical engine ``scripts/installkit/forge_context.py`` is loaded
standalone (same import trick as ``test_forgecontext.py``) so these tests
prove the vendored module stays self-contained and stdlib-only.

Covered:

- §9.2 transactions: install_transaction/uninstall_transaction run the
  full pipeline (preflight → registry → lock → recover → conflicts →
  backup → journal → write → verify → commit) under ONE lock, roll back
  from the durable ``txn/`` backup on failure, and recover interrupted
  journals/locks on the next op.
- §9.4 stable ids: registry entries carry ``qualified_ids``
  (``<forge-id>:<resource-id>``) — schema-optional, always emitted.
- §9.5 routing: ``route`` returns candidates + declared signals with
  explicit ambiguity — deterministic order, never installation order.
"""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import sys
import time
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "docs" / "portable-installation" / "schemas"
ENGINE_PATH = ROOT / "scripts" / "installkit" / "forge_context.py"

spec = importlib.util.spec_from_file_location("forge_context", ENGINE_PATH)
fctx = importlib.util.module_from_spec(spec)
sys.modules["forge_context"] = fctx
spec.loader.exec_module(fctx)


def _schema(name: str) -> dict:
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


def _manifest(fid: str, **over) -> dict:
    kw = {
        "forge_id": fid,
        "name": f"Forge {fid}",
        "version": "1.2.3",
        "cli": fid,
        "package": fid.replace("-", "_"),
        "distribution": fid,
        "python_spec": ">=3.10",
        "scope": "project",
        "hosts": ("claude",),
        "domains": ("forge-ecosystem",),
        "skills": ("skill-a",),
        "agents": ("agent-a",),
        "protocols": ({"id": "forge/v1", "version": "1"},),
        "recorded_at": "2026-10-22T00:00:00Z",
    }
    kw.update(over)
    return fctx.build_manifest(**kw)


def _ctx(root: Path) -> Path:
    return root / ".forge" / "context"


def _tree(root: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


# --- install_transaction: the §9.2 pipeline ----------------------------------


def test_install_transaction_full_pipeline(tmp_path):
    m = _manifest("forge-x")
    out = fctx.install_transaction(tmp_path, m, owner="forge-x")
    assert out["status"] == "installed"
    assert out["phases"] == [
        "preflight", "lock", "recover", "registry", "conflicts",
        "backup", "write", "verify", "commit",
    ]
    assert out["verified"] == ["registry", "entry", "manifest", "docs"]
    ctx = _ctx(tmp_path)
    # registry + capability + routing + the three consumer docs
    assert (ctx / "registry.json").is_file()
    assert (ctx / "capabilities" / "forge-x.json").is_file()
    assert (ctx / "ROUTING.md").is_file()
    for name in ("AGENTS.md", "CLAUDE.md", "AGENT_PROTOCOL.md"):
        assert (tmp_path / name).is_file()
    # clean commit: no journal, no leftover backup
    assert not (ctx / fctx.JOURNAL_NAME).exists()
    assert not (ctx / fctx.TXN_DIR).exists()
    assert fctx.validate_registry(fctx.load_registry(tmp_path)) == []


def test_install_transaction_idempotent_byte_identical(tmp_path):
    m = _manifest("forge-x")
    fctx.install_transaction(tmp_path, m, owner="forge-x")
    before = _tree(tmp_path)
    out = fctx.install_transaction(tmp_path, m, owner="forge-x")
    assert out["status"] == "unchanged"
    assert _tree(tmp_path) == before


def test_install_transaction_user_docs_preserved(tmp_path):
    (tmp_path / "AGENTS.md").write_text("# mine\nuser text\n", "utf-8")
    (tmp_path / "CLAUDE.md").write_text("# claude notes\n", "utf-8")
    fctx.install_transaction(tmp_path, _manifest("forge-x"), owner="forge-x")
    assert (tmp_path / "AGENTS.md").read_text().startswith("# mine\nuser text\n")
    assert (tmp_path / "CLAUDE.md").read_text().startswith("# claude notes\n")


def test_install_transaction_docs_optional(tmp_path):
    """``docs=False`` covers scopes that register without consumer docs —
    the registry path still runs the full pipeline."""
    out = fctx.install_transaction(
        tmp_path, _manifest("forge-x"), owner="forge-x", docs=False
    )
    assert out["status"] == "installed"
    assert out["verified"] == ["registry", "entry", "manifest"]
    assert not (tmp_path / "AGENTS.md").exists()
    assert (_ctx(tmp_path) / "capabilities" / "forge-x.json").exists()


def test_install_transaction_conflict_refuses_before_writes(tmp_path):
    """Foreign protocol → E_CONFLICT at the conflicts phase; nothing was
    written (capability file, doc blocks — all absent)."""
    (tmp_path / "AGENT_PROTOCOL.md").write_text("# foreign protocol\n", "utf-8")
    with pytest.raises(fctx.ContextError) as exc:
        fctx.install_transaction(tmp_path, _manifest("forge-x"), owner="forge-x")
    assert exc.value.kind == fctx.E_CONFLICT
    ctx = _ctx(tmp_path)
    assert not (ctx / "capabilities" / "forge-x.json").exists()
    assert not (tmp_path / "AGENTS.md").exists()
    assert not (ctx / fctx.TXN_DIR).exists()


def test_install_transaction_ambiguous_markers_refuse(tmp_path):
    (tmp_path / "AGENTS.md").write_text(
        "# x\n<!-- forge:forge-x:begin -->\na\n"
        "<!-- forge:forge-x:begin -->\nb\n<!-- forge:forge-x:end -->\n",
        "utf-8",
    )
    with pytest.raises(fctx.ContextError) as exc:
        fctx.install_transaction(tmp_path, _manifest("forge-x"), owner="forge-x")
    assert exc.value.kind == fctx.E_CONFLICT
    assert "re-run" in exc.value.detail  # safe-correction guidance
    assert not (_ctx(tmp_path) / "capabilities" / "forge-x.json").exists()


def test_install_transaction_rollback_restores_state(tmp_path, monkeypatch):
    """A failure mid-write rolls the transaction back to the durable
    backup: pre-existing files restored, created files deleted."""
    fctx.install_transaction(tmp_path, _manifest("forge-x"), owner="forge-x")
    baseline = _tree(tmp_path)

    def boom(root, manifest, tags):
        raise RuntimeError("simulated write failure")

    monkeypatch.setattr(fctx, "_docs_install_apply", boom)
    with pytest.raises(fctx.ContextError) as exc:
        fctx.install_transaction(tmp_path, _manifest("forge-y"), owner="forge-y")
    assert "rolled back" in exc.value.detail
    assert _tree(tmp_path) == baseline
    assert not (_ctx(tmp_path) / fctx.JOURNAL_NAME).exists()
    assert not (_ctx(tmp_path) / fctx.TXN_DIR).exists()


def test_install_transaction_rollback_on_verify_failure(tmp_path, monkeypatch):
    fctx.install_transaction(tmp_path, _manifest("forge-x"), owner="forge-x")
    baseline = _tree(tmp_path)
    monkeypatch.setattr(
        fctx,
        "_verify_install",
        lambda *a, **kw: (_ for _ in ()).throw(
            fctx.ContextError(fctx.E_SCHEMA, "verify boom")
        ),
    )
    with pytest.raises(fctx.ContextError):
        fctx.install_transaction(tmp_path, _manifest("forge-y"), owner="forge-y")
    assert _tree(tmp_path) == baseline


def test_install_transaction_interrupt_propagates_bare(tmp_path, monkeypatch):
    """KeyboardInterrupt mid-write still rolls back, then propagates as
    itself — never re-typed into ContextError."""
    fctx.install_transaction(tmp_path, _manifest("forge-x"), owner="forge-x")
    baseline = _tree(tmp_path)

    def boom(root, manifest, tags):
        raise KeyboardInterrupt

    monkeypatch.setattr(fctx, "_docs_install_apply", boom)
    with pytest.raises(KeyboardInterrupt):
        fctx.install_transaction(tmp_path, _manifest("forge-y"), owner="forge-y")
    assert _tree(tmp_path) == baseline
    assert not (_ctx(tmp_path) / fctx.TXN_DIR).exists()


def test_txn_restore_rejects_tampered_meta_paths(tmp_path):
    """A tampered ``txn/meta.json`` must not write outside the workspace:
    ``..``, absolute, drive and backslash paths are reported as leftovers,
    never restored."""
    ctx = _ctx(tmp_path)
    files = ctx / fctx.TXN_DIR / fctx.TXN_FILES
    files.mkdir(parents=True)
    (files / "0000").write_bytes(b"pwned")
    meta = {
        "files": {
            "../escape.txt": {"blob": "0000", "sha256": "x"},
            "/abs/escape.txt": {"blob": "0000", "sha256": "x"},
            "C:/drive.txt": {"blob": "0000", "sha256": "x"},
            "a\\b.txt": {"blob": "0000", "sha256": "x"},
            "AGENTS.md": {"blob": "oops", "sha256": "x"},
            "OK.md": {"blob": "0000", "sha256": "x"},
        }
    }
    (ctx / fctx.TXN_DIR / fctx.TXN_META).write_text(json.dumps(meta), "utf-8")
    leftovers = fctx._txn_restore(ctx, tmp_path)
    assert len(leftovers) == 5 and all("unsafe" in item for item in leftovers)
    assert not (tmp_path / "escape.txt").exists()
    assert not (tmp_path.parent / "escape.txt").exists()
    # the one safe entry WAS restored inside the root
    assert (tmp_path / "OK.md").read_bytes() == b"pwned"
    assert not (ctx / fctx.TXN_DIR).exists()


def test_interrupted_install_journal_redone(tmp_path):
    """Kill between journal and apply → next op redoes install+docs."""
    ctx = _ctx(tmp_path)
    ctx.mkdir(parents=True)
    zombie = _manifest("zombie")
    (ctx / fctx.JOURNAL_NAME).write_text(
        json.dumps(
            {"op": "install", "manifest": zombie, "legacy_tags": [], "docs": True}
        ),
        encoding="utf-8",
    )
    # partial state: capability written, registry+docs not
    (ctx / "capabilities").mkdir()
    (ctx / "capabilities" / "zombie.json").write_text(json.dumps(zombie), "utf-8")
    out = fctx.install_transaction(tmp_path, _manifest("live"), owner="live")
    assert out["recovered"] == {"op": "install", "forge_id": "zombie"}
    assert {e["forge_id"] for e in fctx.load_registry(tmp_path)["forges"]} == {
        "zombie",
        "live",
    }
    assert "forge:zombie:begin" in (tmp_path / "AGENTS.md").read_text()
    assert not (ctx / fctx.JOURNAL_NAME).exists()
    assert not (ctx / fctx.TXN_DIR).exists()


def test_interrupted_uninstall_journal_redone(tmp_path):
    fctx.install_transaction(tmp_path, _manifest("doomed"), owner="doomed")
    fctx.install_transaction(tmp_path, _manifest("keeper"), owner="keeper")
    ctx = _ctx(tmp_path)
    (ctx / fctx.JOURNAL_NAME).write_text(
        json.dumps({"op": "uninstall", "forge_id": "doomed", "legacy_tags": []}),
        encoding="utf-8",
    )
    out = fctx.repair_context(tmp_path)
    assert out["recovered"] == {"op": "uninstall", "forge_id": "doomed"}
    assert [e["forge_id"] for e in fctx.load_registry(tmp_path)["forges"]] == [
        "keeper"
    ]
    assert "forge:doomed" not in (tmp_path / "AGENTS.md").read_text()


def test_stale_lock_reclaimed_by_transaction(tmp_path):
    ctx = _ctx(tmp_path)
    ctx.mkdir(parents=True)
    (ctx / fctx.LOCK_NAME).write_text(
        json.dumps({"pid": 2**22, "created_at": "2020-01-01T00:00:00Z"}),
        encoding="utf-8",
    )
    out = fctx.install_transaction(tmp_path, _manifest("forge-x"), owner="forge-x")
    assert out["lock_recovered"] is True


def test_orphan_txn_dir_dropped(tmp_path):
    """A txn backup dir without a journal is dead state — the next op
    drops it (kill between backup and journal write)."""
    fctx.install_transaction(tmp_path, _manifest("forge-x"), owner="forge-x")
    ctx = _ctx(tmp_path)
    (ctx / fctx.TXN_DIR / "files").mkdir(parents=True)
    (ctx / fctx.TXN_DIR / "meta.json").write_text("{}", "utf-8")
    fctx.install_transaction(tmp_path, _manifest("forge-y"), owner="forge-y")
    assert not (ctx / fctx.TXN_DIR).exists()


# --- uninstall_transaction ----------------------------------------------------


def test_uninstall_transaction_removes_only_own(tmp_path):
    fctx.install_transaction(tmp_path, _manifest("forge-x"), owner="forge-x")
    fctx.install_transaction(tmp_path, _manifest("forge-y"), owner="forge-y")
    out = fctx.uninstall_transaction(tmp_path, "forge-x", owner="forge-x")
    assert out["status"] == "uninstalled"
    assert out["verified"] == ["registry", "manifest", "docs"]
    ctx = _ctx(tmp_path)
    assert not (ctx / "capabilities" / "forge-x.json").exists()
    assert (ctx / "capabilities" / "forge-y.json").exists()
    assert [e["forge_id"] for e in fctx.load_registry(tmp_path)["forges"]] == [
        "forge-y"
    ]
    agents = (tmp_path / "AGENTS.md").read_text()
    assert "forge:forge-x" not in agents and "forge:forge-y" in agents
    proto = (tmp_path / "AGENT_PROTOCOL.md").read_text()
    assert "forge:forge-y" in proto and "forge:forge-x" not in proto


def test_uninstall_transaction_last_forge_removes_generated_docs(tmp_path):
    fctx.install_transaction(tmp_path, _manifest("only"), owner="only")
    fctx.uninstall_transaction(tmp_path, "only", owner="only")
    assert not (tmp_path / "AGENT_PROTOCOL.md").exists()
    assert not (tmp_path / "AGENTS.md").exists()
    assert not (tmp_path / "CLAUDE.md").exists()


def test_uninstall_transaction_keeps_user_file(tmp_path):
    (tmp_path / "AGENTS.md").write_text("# mine\nuser text\n", "utf-8")
    fctx.install_transaction(tmp_path, _manifest("forge-x"), owner="forge-x")
    fctx.uninstall_transaction(tmp_path, "forge-x", owner="forge-x")
    assert (tmp_path / "AGENTS.md").read_text() == "# mine\nuser text\n"


def test_uninstall_transaction_wrong_owner_refused(tmp_path):
    with pytest.raises(fctx.ContextError) as exc:
        fctx.uninstall_transaction(tmp_path, "victim", owner="attacker")
    assert exc.value.kind == fctx.E_OWNERSHIP


# --- §9.4 stable resource ids --------------------------------------------------


def test_qualified_ids_in_registry_entry(tmp_path):
    fctx.install_transaction(
        tmp_path,
        _manifest(
            "forge-x",
            skills=("s-a", "s-b"),
            agents=("a-a",),
            coordinators=("c-a",),
            rule_areas=("sf-x",),
            knowledge_providers=({"id": "kp-x", "interface": "native-runtime"},),
            eval_suites=({"id": "ev-1", "kind": "developer"},),
        ),
        owner="forge-x",
    )
    reg = fctx.load_registry(tmp_path)
    jsonschema.validate(reg, _schema("ForgeContextRegistry.schema.json"))
    entry = reg["forges"][0]
    qids = entry["qualified_ids"]
    for rid in ("s-a", "s-b", "a-a", "c-a", "sf-x", "kp-x", "ev-1", "forge/v1"):
        assert f"forge-x:{rid}" in qids, rid
    assert all(q.startswith("forge-x:") for q in qids)
    assert qids == sorted(qids)


def test_qualified_id_helpers():
    assert fctx.qualified_id("spark-forge-aws", "glue-performance") == (
        "spark-forge-aws:glue-performance"
    )
    assert fctx.split_qualified_id("a-b:c/d") == ("a-b", "c/d")
    # resource ids are indexes, not renames — no manifest mutation needed
    m = _manifest("forge-x", skills=("skill-a",))
    assert m["skills"] == ["skill-a"]


def test_registry_entry_without_qualified_ids_still_valid():
    """Optional field — registries written by engine < 1.3.0 validate."""
    reg = fctx._empty_registry(Path("/tmp/x"))
    entry = {
        "forge_id": "old",
        "owner": "old",
        "name": "Old",
        "version": "1.0.0",
        "state": "available",
        "scope": "project",
        "profile": "recommended",
        "hosts": [],
        "domains": [],
        "manifest": {
            "path": "capabilities/old.json",
            "sha256": "sha256:" + "0" * 64,
        },
        "installed_by": {"agent": "old", "version": "1.0.0"},
        "installed_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    reg["forges"] = [entry]
    assert fctx.validate_registry(reg) == []


def test_qualified_ids_pattern_enforced():
    reg = fctx._empty_registry(Path("/tmp/x"))
    entry = {
        "forge_id": "f",
        "owner": "f",
        "name": "F",
        "version": "1.0.0",
        "state": "available",
        "scope": "project",
        "profile": "recommended",
        "hosts": [],
        "domains": [],
        "manifest": {"path": "capabilities/f.json", "sha256": "sha256:" + "0" * 64},
        "qualified_ids": ["no-colon-here"],
        "installed_by": {"agent": "f", "version": "1.0.0"},
        "installed_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    reg["forges"] = [entry]
    assert any("qualified_ids" in p for p in fctx.validate_registry(reg))


# --- §9.5 routing --------------------------------------------------------------


def _two_forge_root(tmp_path: Path) -> Path:
    fctx.install_transaction(
        tmp_path,
        _manifest("a-forge", domains=("apache-spark", "shared")),
        owner="a-forge",
    )
    fctx.install_transaction(
        tmp_path,
        _manifest(
            "b-forge",
            domains=("api-contracts", "shared"),
            skills=("s1", "s2", "s3"),
            rule_areas=("rb-1",),
            knowledge_providers=({"id": "kb", "interface": "bundled"},),
            eval_suites=({"id": "ev", "kind": "developer"},),
        ),
        owner="b-forge",
    )
    return tmp_path


def test_route_by_domain(tmp_path):
    _two_forge_root(tmp_path)
    out = fctx.route(tmp_path, domain="apache-spark")
    assert out["status"] == "ok"
    assert [c["forge_id"] for c in out["candidates"]] == ["a-forge"]
    assert out["ambiguous"] is False
    assert out["unclaimed"] is False
    assert {e["forge_id"] for e in out["excluded"]} == {"b-forge"}


def test_route_ambiguity_is_explicit(tmp_path):
    _two_forge_root(tmp_path)
    out = fctx.route(tmp_path, domain="shared")
    assert out["ambiguous"] is True
    assert len(out["candidates"]) == 2
    # deterministic order: more available capability kinds first
    # (b-forge declares knowledge/rules/evals providers, a-forge does
    # not), forge_id as final tie-break — never installation order
    assert out["candidates"][0]["forge_id"] == "b-forge"


def test_route_unclaimed_domain(tmp_path):
    _two_forge_root(tmp_path)
    out = fctx.route(tmp_path, domain="nobody-claimed")
    assert out["candidates"] == []
    assert out["unclaimed"] is True
    assert len(out["excluded"]) == 2


def test_route_capability_filter(tmp_path):
    _two_forge_root(tmp_path)
    out = fctx.route(tmp_path, capability="evals")
    # only b-forge declares eval suites in the fixture
    assert [c["forge_id"] for c in out["candidates"]] == ["b-forge"]
    out = fctx.route(tmp_path, capability="bogus-kind")
    assert out["candidates"] == []
    fctx.install_transaction(
        tmp_path,
        _manifest(
            "c-forge",
            domains=("shared",),
            eval_suites=({"id": "ev", "kind": "developer"},),
        ),
        owner="c-forge",
    )
    out = fctx.route(tmp_path, capability="evals")
    assert {c["forge_id"] for c in out["candidates"]} == {"b-forge", "c-forge"}


def test_route_scope_and_host_filters(tmp_path):
    _two_forge_root(tmp_path)
    out = fctx.route(tmp_path, scope="workspace")
    assert out["candidates"] == []  # both installed at project scope
    out = fctx.route(tmp_path, scope="project", host="claude")
    assert len(out["candidates"]) == 2
    out = fctx.route(tmp_path, host="devin")
    assert out["candidates"] == []  # neither declared devin


def test_route_unavailable_state_excluded(tmp_path):
    fctx.install_transaction(
        tmp_path,
        _manifest(
            "sad-forge",
            state="unavailable",
            domains=("apache-spark",),
        ),
        owner="sad-forge",
    )
    out = fctx.route(tmp_path, domain="apache-spark")
    assert out["candidates"] == []
    out = fctx.route(tmp_path, domain="apache-spark", include_unavailable=True)
    assert [c["forge_id"] for c in out["candidates"]] == ["sad-forge"]


def test_route_signals_declared(tmp_path):
    _two_forge_root(tmp_path)
    out = fctx.route(tmp_path, domain="shared")
    cand = out["candidates"][0]
    for key in ("runtime", "security", "health", "evidence", "qualified_ids"):
        assert key in cand
    assert cand["runtime"]["offline_available"] is True
    assert cand["security"]["read_only_default"] is True
    assert "never dispatches" in out["selection"]


def test_route_empty_registry(tmp_path):
    out = fctx.route(tmp_path, domain="anything")
    assert out["status"] == "empty"
    assert out["candidates"] == []


def test_route_works_without_the_forge(tmp_path):
    """The registry is standalone — two specialists, no the-forge, and
    routing still returns candidates (install-2.0 §9.5)."""
    fctx.install_transaction(tmp_path, _manifest("s-aws", domains=("spark",)), owner="s-aws")
    fctx.install_transaction(tmp_path, _manifest("s-az", domains=("databricks",)), owner="s-az")
    out = fctx.route(tmp_path)
    assert out["status"] == "ok"
    assert {c["forge_id"] for c in out["candidates"]} == {"s-aws", "s-az"}
    reg = fctx.load_registry(tmp_path)
    assert "the-forge" not in {e["forge_id"] for e in reg["forges"]}


# --- order equivalence (§9.1/§9.5) --------------------------------------------


def test_install_order_independence(tmp_path):
    """Install order changes nothing in the final registry/protocol —
    the docs are regenerated deterministically from sorted entries."""
    a, b = _manifest("a-forge", domains=("d1",)), _manifest("b-forge", domains=("d2",))
    root1 = tmp_path / "r1"
    root2 = tmp_path / "r2"
    fctx.install_transaction(root1, a, owner="a-forge")
    fctx.install_transaction(root1, b, owner="b-forge")
    fctx.install_transaction(root2, b, owner="b-forge")
    fctx.install_transaction(root2, a, owner="a-forge")
    for name in ("AGENT_PROTOCOL.md",):
        assert (root1 / name).read_bytes() == (root2 / name).read_bytes()
    # ROUTING.md is deterministic markdown — byte-identical across orders
    assert (root1 / ".forge/context/ROUTING.md").read_bytes() == (
        root2 / ".forge/context/ROUTING.md"
    ).read_bytes()
    # registry.json differs only in volatile fields (timestamps, abs root)
    t1 = json.loads((root1 / ".forge/context/registry.json").read_text())
    t2 = json.loads((root2 / ".forge/context/registry.json").read_text())
    volatile = ("installed_at", "updated_at")

    def _stable(reg: dict) -> dict:
        out = {
            k: v for k, v in reg.items() if k not in ("updated_at", "workspace_root")
        }
        out["forges"] = [
            {k: v for k, v in e.items() if k not in volatile} for e in reg["forges"]
        ]
        return out

    assert _stable(t1) == _stable(t2)
    # AGENTS.md blocks: same set per forge (order may differ — appended)
    for fid in ("a-forge", "b-forge"):
        for root in (root1, root2):
            assert f"forge:{fid}:begin" in (root / "AGENTS.md").read_text()


# --- §13.1 typed errors: non-UTF-8 consumer docs ----------------------------

CP1252 = b"# guia do agente - configura\xe7\xe3o v\xe1lida\r\n"


def test_install_non_utf8_doc_is_typed_refusal_not_crash(tmp_path):
    """A pre-existing cp1252 AGENTS.md (common on Windows) must surface
    E_CONFLICT naming the file — never UnicodeDecodeError as an internal
    error leaving a half-installed forge."""
    (tmp_path / "AGENTS.md").write_bytes(CP1252)
    with pytest.raises(fctx.ContextError) as exc:
        fctx.install_transaction(tmp_path, _manifest("forge-x"), owner="forge-x")
    assert exc.value.kind == fctx.E_CONFLICT
    assert "AGENTS.md" in exc.value.detail and "UTF-8" in exc.value.detail
    assert "re-run" in exc.value.detail
    assert not (_ctx(tmp_path) / "capabilities" / "forge-x.json").exists()


def test_uninstall_non_utf8_doc_is_typed_refusal_not_crash(tmp_path):
    """Same doc state on the teardown path: uninstall also fails with a
    named refusal instead of a bare UnicodeDecodeError."""
    fctx.install_transaction(tmp_path, _manifest("forge-x"), owner="forge-x")
    (tmp_path / "AGENTS.md").write_bytes(CP1252)
    with pytest.raises(fctx.ContextError) as exc:
        fctx.uninstall_transaction(tmp_path, "forge-x", owner="forge-x")
    assert exc.value.kind == fctx.E_CONFLICT
    assert "AGENTS.md" in exc.value.detail


def test_protocol_non_utf8_is_typed_refusal(tmp_path):
    (tmp_path / "AGENT_PROTOCOL.md").write_bytes(CP1252)
    with pytest.raises(fctx.ContextError) as exc:
        fctx.install_transaction(tmp_path, _manifest("forge-x"), owner="forge-x")
    assert exc.value.kind == fctx.E_CONFLICT
    assert "AGENT_PROTOCOL.md" in exc.value.detail


# --- repair resilience: malformed capability files -------------------------


def test_repair_context_malformed_capability_is_reported_not_crash(tmp_path):
    """A capability file whose manifest lacks `installed` (corrupted or
    hand-edited) must not raise KeyError on the repair path — the one
    path meant to converge a broken context. It is skipped and reported
    in `invalid` while valid forges still register."""
    fctx.install_transaction(tmp_path, _manifest("forge-a"), owner="forge-a")
    (tmp_path / ".forge/context/capabilities/bad.json").write_text(
        json.dumps({"forge_id": "bad"}), encoding="utf-8"
    )
    out = fctx.repair_context(tmp_path)
    assert out["status"] == "repaired"
    assert "forge-a" in out["forges"]
    assert "bad" not in out["forges"]
    invalid_ids = {e["forge_id"] for e in out["invalid"]}
    assert "bad" in invalid_ids
    reg = json.loads((tmp_path / ".forge/context/registry.json").read_text())
    assert [e["forge_id"] for e in reg["forges"]] == ["forge-a"]


# --- lock ownership: token guard -------------------------------------------


def test_lock_exit_never_unlinks_foreign_lock(tmp_path):
    """After a stale reclaim the on-disk lock may belong to a newer
    claimant; __exit__ must only unlink when the token is ours, and
    `held` must reset either way."""
    lock_file = tmp_path / ".forge/context/.context.lock"
    lock_file.parent.mkdir(parents=True)
    lock = fctx._Lock(lock_file)
    with lock:
        assert lock_file.exists()
        held_doc = json.loads(lock_file.read_text())
        assert held_doc["token"] == lock._token
        # Simulate a foreign claimant writing the lock over ours.
        lock_file.write_text(
            json.dumps({"pid": 9_999_999, "token": "foreign", "created_at": "x"})
        )
    assert lock_file.exists()  # foreign lock preserved
    assert json.loads(lock_file.read_text())["token"] == "foreign"
    assert lock.held is False


def test_lock_reclaim_race_is_named_lock_error(tmp_path, monkeypatch):
    """If a third party wins the reclaim race after we unlink a stale
    lock, the second FileExistsError surfaces as LockError(E_LOCKED),
    not a bare exception."""
    lock_file = tmp_path / ".forge/context/.context.lock"
    lock_file.parent.mkdir(parents=True)
    # Holder undecidable (no pid field) and older than stale_after.
    lock_file.write_text(json.dumps({"note": "ancient"}))
    old = time.time() - 10_000
    os.utime(lock_file, (old, old))
    lock = fctx._Lock(lock_file)
    calls = {"n": 0}
    real_create = fctx._Lock._create

    def _racer(self):
        calls["n"] += 1
        if calls["n"] == 2:
            # A foreign claimant lands between our unlink and our create.
            lock_file.write_text(json.dumps({"token": "racer"}))
            raise FileExistsError
        real_create(self)

    monkeypatch.setattr(fctx._Lock, "_create", _racer)
    with pytest.raises(fctx.LockError) as exc, lock:
        pass  # pragma: no cover — never reached
    assert exc.value.kind == fctx.E_LOCKED
    assert calls["n"] == 2


def test_poisoned_journal_quarantines_instead_of_wedging(tmp_path):
    """A journal redo that hits a post-crash conflict (foreign
    AGENT_PROTOCOL.md) quarantines the intent and reports it — later
    context ops keep working instead of failing on the same journal
    forever."""
    root = tmp_path
    # Simulate an interrupted install: journal present, no registry.
    ctx = root / ".forge/context"
    ctx.mkdir(parents=True)
    manifest = _manifest("forge-x")
    (ctx / "journal.json").write_text(json.dumps({"op": "install", "manifest": manifest}))
    # A foreign protocol file appeared during the crash window — its
    # sentinel claims a *different* installer, so the redo must conflict.
    (root / "AGENT_PROTOCOL.md").write_text(
        "# protocol\n<!-- agent-protocol:another-installer -->\n", encoding="utf-8"
    )
    # repair_context triggers _recover_journal: conflict → quarantine.
    out = fctx.repair_context(root)
    rec = out["recovered"]
    assert rec and rec.get("quarantined") is True
    assert not (ctx / "journal.json").exists()
    assert any(p.name.startswith("journal") and p.name != "journal.json" for p in ctx.iterdir())
    # Subsequent ops are not wedged on the same journal — a second repair
    # converges cleanly, and install's refusal is the REAL foreign-doc
    # conflict (a named E_CONFLICT), not a journal failure.
    out2 = fctx.repair_context(root)
    assert out2["status"] == "repaired"
    with pytest.raises(fctx.ContextError) as exc:
        fctx.install_transaction(root, _manifest("forge-y"), owner="forge-y")
    assert exc.value.kind == fctx.E_CONFLICT
    assert "AGENT_PROTOCOL.md" in exc.value.detail


def test_atomic_write_preserves_file_mode(tmp_path):
    """_atomic_write must keep an existing file's mode — mkstemp's 0600
    would silently downgrade a user's 0644 doc."""
    doc = tmp_path / "AGENTS.md"
    doc.write_text("v1")
    doc.chmod(0o644)
    fctx._atomic_write(doc, b"v2")
    assert doc.read_text() == "v2"
    assert stat.S_IMODE(doc.stat().st_mode) == 0o644
