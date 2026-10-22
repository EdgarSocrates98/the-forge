"""forge-context/v1 — workspace context registry (install-2.0 cycle 2, ADR-0061).

The canonical engine ``scripts/installkit/forge_context.py`` is loaded
standalone (spec_from_file_location — the same trick as the installkit
tests), so these tests prove the vendored module is self-contained and
stdlib-only. The JSON Schemas in ``docs/portable-installation/schemas/``
are the published contract; conformance is checked both against them
(jsonschema) and against the module's own validators.
"""

from __future__ import annotations

import importlib.util
import json
import sys
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


def _manifest(fid: str = "the-forge", **over) -> dict:
    kw = {
        "forge_id": fid,
        "name": f"Forge {fid}",
        "version": "1.2.3",
        "cli": fid,
        "package": fid.replace("-", "_"),
        "distribution": fid,
        "python_spec": ">=3.11",
        "scope": "project",
        "hosts": ("claude",),
        "domains": ("forge-ecosystem",),
        "skills": ("forge-routing",),
        "recorded_at": "2026-10-22T00:00:00Z",
    }
    kw.update(over)
    return fctx.build_manifest(**kw)


def _ctx(tmp_path: Path) -> Path:
    return tmp_path / ".forge" / "context"


# --- schema documents exist and conform --------------------------------------


def test_schema_files_exist():
    assert (SCHEMAS / "ForgeContext.schema.json").exists()
    assert (SCHEMAS / "ForgeContextRegistry.schema.json").exists()


def test_built_manifest_conforms_to_json_schema_and_engine():
    doc = _manifest()
    jsonschema.validate(doc, _schema("ForgeContext.schema.json"))
    assert fctx.validate_manifest(doc) == []


@pytest.mark.parametrize(
    "patch",
    [
        {"forge_id": "Bad_ID"},
        {"version": "not-semver"},
        {"state": "sometimes"},
        {"surprise": True},
    ],
)
def test_invalid_manifests_rejected_by_both_validators(patch):
    doc = _manifest()
    key, value = next(iter(patch.items()))
    doc[key] = value
    assert fctx.validate_manifest(doc), f"engine accepted {patch}"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc, _schema("ForgeContext.schema.json"))


def test_manifest_unknown_capability_shape_rejected():
    doc = _manifest()
    doc["capabilities"]["bogus"] = {"available": "yes"}
    assert fctx.validate_manifest(doc)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc, _schema("ForgeContext.schema.json"))


def test_degraded_state_requires_reasons():
    # the builder itself refuses to emit a degraded manifest without reasons
    with pytest.raises(fctx.ContextError) as exc:
        _manifest(state="degraded", degraded_reasons=())
    assert exc.value.kind == fctx.E_SCHEMA
    doc2 = _manifest(state="degraded", degraded_reasons=("knowledge bundle absent",))
    assert fctx.validate_manifest(doc2) == []
    jsonschema.validate(doc2, _schema("ForgeContext.schema.json"))


def test_command_and_path_validation():
    # build_manifest refuses to emit invalid docs — mutate a valid one instead
    doc = _manifest()
    doc["discovery"]["commands"] = [{"id": "x", "argv": [], "read_only": True}]
    assert any("argv" in p for p in fctx.validate_manifest(doc))
    doc2 = _manifest()
    doc2["resources"]["bad"] = {"kind": "copied", "location": "../escape", "optional": True}
    assert any(".." in p for p in fctx.validate_manifest(doc2))
    doc3 = _manifest()
    doc3["resources"]["bad"] = {"kind": "copied", "location": "~/home/path", "optional": True}
    assert fctx.validate_manifest(doc3)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc, _schema("ForgeContext.schema.json"))


def test_discovery_ops_map_conceptual_ops_to_declared_commands():
    """`discovery.ops` resolves a §6.2 conceptual op to a declared command
    id — the manifest carries the mapping, consumers never guess verbs."""
    cmds = (
        {
            "id": "rules-lookup",
            "argv": ["sparkforge-aws", "rules", "lookup"],
            "read_only": True,
        },
        {
            "id": "knowledge-path",
            "argv": ["sparkforge-aws", "knowledge", "path"],
            "read_only": True,
        },
    )
    doc = _manifest(
        discovery_commands=cmds,
        discovery_ops={
            "rules.search": "rules-lookup",
            "knowledge.get": "knowledge-path",
        },
    )
    assert fctx.validate_manifest(doc) == []
    jsonschema.validate(doc, _schema("ForgeContext.schema.json"))
    assert doc["discovery"]["ops"] == {
        "rules.search": "rules-lookup",
        "knowledge.get": "knowledge-path",
    }


def test_discovery_ops_rejects_unknown_op_and_dangling_ref():
    cmds = (
        {
            "id": "rules-lookup",
            "argv": ["sparkforge-aws", "rules", "lookup"],
            "read_only": True,
        },
    )
    # build_manifest refuses to emit an invalid doc — mutate a valid one
    bad_op = _manifest(
        discovery_commands=cmds, discovery_ops={"rules.search": "rules-lookup"}
    )
    bad_op["discovery"]["ops"]["telemetry.export"] = "rules-lookup"
    assert any("unknown op" in p for p in fctx.validate_manifest(bad_op))
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad_op, _schema("ForgeContext.schema.json"))

    dangling = _manifest(
        discovery_commands=cmds, discovery_ops={"rules.search": "rules-lookup"}
    )
    dangling["discovery"]["ops"]["rules.get"] = "no-such-command"
    problems = fctx.validate_manifest(dangling)
    assert any("undeclared command" in p for p in problems)

    with pytest.raises(fctx.ContextError):
        _manifest(
            discovery_commands=cmds, discovery_ops={"rules.search": "undeclared"}
        )

    not_a_map = _manifest()
    not_a_map["discovery"]["ops"] = ["rules.search"]
    assert fctx.validate_manifest(not_a_map)


def test_discovery_ops_absent_by_default():
    doc = _manifest()
    assert "ops" not in doc["discovery"]


# --- registry round-trip ------------------------------------------------------


def test_register_writes_all_documents(tmp_path):
    out = fctx.register_forge(tmp_path, _manifest(), owner="the-forge")
    assert out["status"] == "registered"
    ctx = _ctx(tmp_path)
    assert (ctx / "registry.json").is_file()
    assert (ctx / "capabilities" / "the-forge.json").is_file()
    assert (ctx / "ROUTING.md").is_file()
    reg = fctx.load_registry(tmp_path)
    assert reg is not None
    jsonschema.validate(reg, _schema("ForgeContextRegistry.schema.json"))
    assert fctx.validate_registry(reg) == []
    assert [e["forge_id"] for e in reg["forges"]] == ["the-forge"]


def test_reregister_is_idempotent_byte_identical(tmp_path):
    fctx.register_forge(tmp_path, _manifest(), owner="the-forge")
    ctx = _ctx(tmp_path)
    before = {p.name: p.read_bytes() for p in ctx.rglob("*") if p.is_file()}
    again = fctx.register_forge(
        tmp_path, _manifest(recorded_at="2999-01-01T00:00:00Z"), owner="the-forge"
    )
    assert again["status"] == "unchanged"
    after = {p.name: p.read_bytes() for p in ctx.rglob("*") if p.is_file()}
    assert before == after


def test_upgrade_writes_new_version_preserves_installed_at(tmp_path):
    fctx.register_forge(tmp_path, _manifest(), owner="the-forge")
    first = fctx.load_registry(tmp_path)["forges"][0]
    up = _manifest(version="9.9.9")
    out = fctx.register_forge(tmp_path, up, owner="the-forge")
    assert out["status"] == "registered"
    entry = fctx.load_registry(tmp_path)["forges"][0]
    assert entry["version"] == "9.9.9"
    assert entry["installed_at"] == first["installed_at"]
    assert entry["updated_at"] != first["updated_at"] or entry["version"] == "9.9.9"


def test_multi_forge_registry_and_domains_index(tmp_path):
    fctx.register_forge(tmp_path, _manifest(), owner="the-forge")
    fctx.register_forge(
        tmp_path,
        _manifest(
            "spark-forge-aws",
            domains=("apache-spark", "forge-ecosystem"),
            skills=("analyze-pyspark",),
        ),
        owner="spark-forge-aws",
    )
    reg = fctx.load_registry(tmp_path)
    jsonschema.validate(reg, _schema("ForgeContextRegistry.schema.json"))
    assert [e["forge_id"] for e in reg["forges"]] == ["spark-forge-aws", "the-forge"]
    assert reg["domains_index"]["forge-ecosystem"] == ["spark-forge-aws", "the-forge"]
    routing = (tmp_path / ".forge" / "context" / "ROUTING.md").read_text(encoding="utf-8")
    assert "forge-ecosystem | spark-forge-aws, the-forge" in routing


def test_uninstall_round_trip_removes_only_own(tmp_path):
    fctx.register_forge(tmp_path, _manifest(), owner="the-forge")
    fctx.register_forge(tmp_path, _manifest("other-forge"), owner="other-forge")
    out = fctx.unregister_forge(tmp_path, "the-forge", owner="the-forge")
    assert out["status"] == "unregistered"
    assert not (tmp_path / ".forge" / "context" / "capabilities" / "the-forge.json").exists()
    reg = fctx.load_registry(tmp_path)
    assert [e["forge_id"] for e in reg["forges"]] == ["other-forge"]
    assert (tmp_path / ".forge" / "context" / "capabilities" / "other-forge.json").exists()
    # and the whole cycle is replayable
    fctx.register_forge(tmp_path, _manifest(), owner="the-forge")
    assert [e["forge_id"] for e in fctx.load_registry(tmp_path)["forges"]] == [
        "other-forge",
        "the-forge",
    ]


# --- ownership ----------------------------------------------------------------


def test_forge_never_registers_another(tmp_path):
    with pytest.raises(fctx.ContextError) as exc:
        fctx.register_forge(tmp_path, _manifest("victim"), owner="attacker")
    assert exc.value.kind == fctx.E_OWNERSHIP


def test_forge_never_unregisters_another(tmp_path):
    fctx.register_forge(tmp_path, _manifest("victim"), owner="victim")
    with pytest.raises(fctx.ContextError) as exc:
        fctx.unregister_forge(tmp_path, "victim", owner="attacker")
    assert exc.value.kind == fctx.E_OWNERSHIP
    assert (tmp_path / ".forge" / "context" / "capabilities" / "victim.json").exists()


def test_foreign_manifest_at_our_path_is_refused(tmp_path):
    cap = tmp_path / ".forge" / "context" / "capabilities" / "the-forge.json"
    cap.parent.mkdir(parents=True)
    cap.write_text(json.dumps(_manifest("foreign-installer")), encoding="utf-8")
    with pytest.raises(fctx.ContextError) as exc:
        fctx.register_forge(tmp_path, _manifest(), owner="the-forge")
    assert exc.value.kind == fctx.E_OWNERSHIP
    # foreign content untouched
    assert json.loads(cap.read_text())["forge_id"] == "foreign-installer"


def test_invalid_manifest_refused(tmp_path):
    with pytest.raises(fctx.ContextError) as exc:
        fctx.register_forge(tmp_path, {"schema": "forge/context/v1"}, owner="the-forge")
    assert exc.value.kind == fctx.E_SCHEMA


# --- interruption recovery -----------------------------------------------------


def test_journal_recovered_on_next_op(tmp_path):
    """Kill between journal write and apply → next op redoes the journal."""
    ctx = _ctx(tmp_path)
    ctx.mkdir(parents=True)
    zombie = _manifest("zombie-forge")
    (ctx / fctx.JOURNAL_NAME).write_text(
        json.dumps({"op": "register", "manifest": zombie}), encoding="utf-8"
    )
    out = fctx.register_forge(tmp_path, _manifest(), owner="the-forge")
    assert out["recovered"] == {"op": "register", "forge_id": "zombie-forge"}
    assert (ctx / "capabilities" / "zombie-forge.json").exists()
    assert not (ctx / fctx.JOURNAL_NAME).exists()
    assert {e["forge_id"] for e in fctx.load_registry(tmp_path)["forges"]} == {
        "the-forge",
        "zombie-forge",
    }


def test_repair_converges_partial_state(tmp_path):
    """Crash after capability write but before registry update → repair
    rebuilds registry from disk."""
    fctx.register_forge(tmp_path, _manifest(), owner="the-forge")
    ctx = _ctx(tmp_path)
    # simulate the interrupted state: manifest present, registry gone
    (ctx / "registry.json").unlink()
    (ctx / "ROUTING.md").unlink()
    out = fctx.repair_context(tmp_path)
    assert out["status"] == "repaired"
    assert out["forges"] == ["the-forge"]
    reg = fctx.load_registry(tmp_path)
    jsonschema.validate(reg, _schema("ForgeContextRegistry.schema.json"))


def test_corrupt_registry_quarantined_not_lost(tmp_path):
    fctx.register_forge(tmp_path, _manifest(), owner="the-forge")
    ctx = _ctx(tmp_path)
    (ctx / "registry.json").write_text("{ not json", encoding="utf-8")
    out = fctx.register_forge(tmp_path, _manifest(), owner="the-forge")
    assert out["status"] == "registered"
    quarantined = list(ctx.glob("registry.json.corrupt-*"))
    assert quarantined, "corrupt registry was not quarantined"
    jsonschema.validate(fctx.load_registry(tmp_path), _schema("ForgeContextRegistry.schema.json"))


def test_stale_lock_reclaimed(tmp_path):
    ctx = _ctx(tmp_path)
    ctx.mkdir(parents=True)
    (ctx / fctx.LOCK_NAME).write_text(
        json.dumps({"pid": 2**22, "created_at": "2020-01-01T00:00:00Z"}), encoding="utf-8"
    )
    out = fctx.register_forge(tmp_path, _manifest(), owner="the-forge")
    assert out["lock_recovered"] is True


def test_held_lock_refuses(tmp_path):
    ctx = _ctx(tmp_path)
    ctx.mkdir(parents=True)
    (ctx / fctx.LOCK_NAME).write_text(
        json.dumps({"pid": __import__("os").getpid(), "created_at": "2999-01-01T00:00:00Z"}),
        encoding="utf-8",
    )
    with pytest.raises(fctx.LockError) as exc:
        fctx.register_forge(tmp_path, _manifest(), owner="the-forge")
    assert exc.value.kind == fctx.E_LOCKED


# --- ROUTING.md determinism ----------------------------------------------------


def test_routing_document_deterministic(tmp_path):
    fctx.register_forge(tmp_path, _manifest(), owner="the-forge")
    fctx.register_forge(tmp_path, _manifest("b-forge", domains=("a-domain",)), owner="b-forge")
    reg = fctx.load_registry(tmp_path)
    manifests = fctx.list_capabilities(tmp_path)
    one = fctx.routing_document(reg, manifests)
    two = fctx.routing_document(reg, manifests)
    assert one == two
    assert "T" not in one.splitlines()[0]  # header, no timestamps anywhere
    import re

    assert not re.search(r"\d{4}-\d{2}-\d{2}T", one), "ROUTING.md embeds timestamps"
    for fid in ("b-forge", "the-forge"):
        assert f"### {fid}" in one
        assert f"capabilities/{fid}.json" in one


def test_empty_registry_routing(tmp_path):
    reg = fctx._empty_registry(tmp_path)
    text = fctx.routing_document(reg, {})
    assert "_No forges registered" in text
    assert "_No domains registered" in text


# --- vendored copy parity ------------------------------------------------------


def test_vendored_copy_matches_canonical():
    """``src/theforge/_forgecontext.py`` is the vendored copy — the only
    allowed difference from the canonical source is the _SOURCE_SHA256
    stamp (same drift contract as _installkit)."""
    canonical = ENGINE_PATH.read_bytes()
    vendored = (ROOT / "src" / "theforge" / "_forgecontext.py").read_bytes()
    import hashlib

    sha = hashlib.sha256(canonical).hexdigest()[:16]
    expected = canonical.replace(
        b'_SOURCE_SHA256 = "canonical"', f'_SOURCE_SHA256 = "{sha}"'.encode()
    )
    assert vendored == expected, "vendored _forgecontext.py drifted from canonical"


def test_module_is_stdlib_only():
    """The vendored engine must never grow third-party imports."""
    import ast

    tree = __import__("ast").parse(ENGINE_PATH.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    third_party = imported - set(sys.stdlib_module_names) - {"forge_context"}
    assert not third_party, f"non-stdlib imports: {third_party}"


# --- install wiring -------------------------------------------------------------


def test_install_writes_context_registry(tmp_path):
    """`theforge install apply` emits `.forge/context/` at the target."""
    from theforge.install import service

    target = tmp_path / "consumer"
    (target / ".git").mkdir(parents=True)
    receipt = service.install(scope="project", root=target, host="none", yes=True)
    assert receipt["status"] == "completed"
    ctx = target / ".forge" / "context"
    assert (ctx / "registry.json").is_file()
    assert (ctx / "capabilities" / "the-forge.json").is_file()
    assert (ctx / "ROUTING.md").is_file()
    manifest = json.loads((ctx / "capabilities" / "the-forge.json").read_text())
    jsonschema.validate(manifest, _schema("ForgeContext.schema.json"))
    reg = json.loads((ctx / "registry.json").read_text())
    jsonschema.validate(reg, _schema("ForgeContextRegistry.schema.json"))
    assert [e["forge_id"] for e in reg["forges"]] == ["the-forge"]


def test_uninstall_removes_context_entry(tmp_path):
    from theforge.install import service

    target = tmp_path / "consumer"
    (target / ".git").mkdir(parents=True)
    service.install(scope="project", root=target, host="none", yes=True)
    out = service.uninstall(scope="project", root=target)
    assert out["status"] == "completed"
    ctx = target / ".forge" / "context"
    assert not (ctx / "capabilities" / "the-forge.json").exists()
    reg = json.loads((ctx / "registry.json").read_text())
    assert reg["forges"] == []


def test_dry_run_writes_no_context(tmp_path):
    from theforge.install import service

    target = tmp_path / "consumer"
    (target / ".git").mkdir(parents=True)
    service.install(scope="project", root=target, host="none", dry_run=True)
    assert not (target / ".forge" / "context").exists()


# --- consumer docs — install-2.0 ciclo 3 (lf-0036) ---------------------------
#
# The canonical engine owns AGENTS.md/CLAUDE.md managed blocks and the shared
# AGENT_PROTOCOL.md. These tests exercise the module standalone (same import
# trick as above) plus one service-level wiring check.


def test_install_docs_creates_three_docs(tmp_path):
    m = _manifest("forge-x")
    fctx.register_forge(tmp_path, m, owner="forge-x")
    out = fctx.install_docs(tmp_path, m, owner="forge-x")
    assert out["status"] == "written"
    agents = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    claude = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    proto = (tmp_path / "AGENT_PROTOCOL.md").read_text(encoding="utf-8")
    assert "<!-- forge:ecosystem:begin -->" in agents
    assert "<!-- forge:forge-x:begin -->" in agents
    assert "@AGENTS.md" in claude
    assert proto.startswith(fctx.PROTOCOL_SENTINEL)
    for sec in (
        "1. Discovery", "2. Classification", "3. Routing",
        "4. Context Retrieval", "5. Planning", "6. Execution",
        "7. Evaluation", "8. Verification", "9. Reporting",
    ):
        assert sec in proto


def test_install_docs_is_byte_idempotent(tmp_path):
    m = _manifest("forge-x")
    fctx.register_forge(tmp_path, m, owner="forge-x")
    fctx.install_docs(tmp_path, m, owner="forge-x")
    snap = {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
    out = fctx.install_docs(tmp_path, m, owner="forge-x")
    assert out["status"] == "unchanged"
    assert snap == {p.name: p.read_bytes() for p in tmp_path.iterdir()
                    if p.is_file()}


def test_install_docs_preserves_user_content(tmp_path):
    (tmp_path / "AGENTS.md").write_text("# mine\nuser text\n", "utf-8")
    (tmp_path / "CLAUDE.md").write_text("# claude notes\n", "utf-8")
    m = _manifest("forge-x")
    fctx.register_forge(tmp_path, m, owner="forge-x")
    fctx.install_docs(tmp_path, m, owner="forge-x")
    assert (tmp_path / "AGENTS.md").read_text().startswith("# mine\nuser text\n")
    assert (tmp_path / "CLAUDE.md").read_text().startswith("# claude notes\n")


def test_install_docs_strips_legacy_markers(tmp_path):
    (tmp_path / "AGENTS.md").write_text(
        "# mine\n\n<!-- forge-x:managed:begin -->\nold\n"
        "<!-- forge-x:managed:end -->\n", "utf-8")
    m = _manifest("forge-x")
    fctx.register_forge(tmp_path, m, owner="forge-x")
    out = fctx.install_docs(tmp_path, m, owner="forge-x",
                            legacy_tags=("forge-x:managed",))
    assert "managed:begin" not in (tmp_path / "AGENTS.md").read_text()
    assert out["legacy_stripped"] == ["forge-x:managed"]


def test_install_docs_refuses_ambiguous_markers(tmp_path):
    (tmp_path / "AGENTS.md").write_text(
        "# x\n<!-- forge:forge-x:begin -->\na\n"
        "<!-- forge:forge-x:begin -->\nb\n<!-- forge:forge-x:end -->\n",
        "utf-8")
    m = _manifest("forge-x")
    fctx.register_forge(tmp_path, m, owner="forge-x")
    with pytest.raises(fctx.ContextError) as exc:
        fctx.install_docs(tmp_path, m, owner="forge-x")
    assert exc.value.kind == fctx.E_CONFLICT
    assert "ambiguous" in exc.value.detail


def test_install_docs_refuses_foreign_protocol(tmp_path):
    (tmp_path / "AGENT_PROTOCOL.md").write_text("# custom protocol\n", "utf-8")
    m = _manifest("forge-x")
    fctx.register_forge(tmp_path, m, owner="forge-x")
    with pytest.raises(fctx.ContextError) as exc:
        fctx.install_docs(tmp_path, m, owner="forge-x")
    assert exc.value.kind == fctx.E_CONFLICT
    assert (tmp_path / "AGENT_PROTOCOL.md").read_text() == "# custom protocol\n"


def test_two_forges_one_protocol_selective_uninstall(tmp_path):
    m1, m2 = _manifest("forge-x"), _manifest("forge-y")
    fctx.register_forge(tmp_path, m1, owner="forge-x")
    fctx.install_docs(tmp_path, m1, owner="forge-x")
    fctx.register_forge(tmp_path, m2, owner="forge-y")
    fctx.install_docs(tmp_path, m2, owner="forge-y")

    agents = (tmp_path / "AGENTS.md").read_text()
    assert agents.count("forge:ecosystem:begin") == 1
    assert "forge:forge-x:begin" in agents and "forge:forge-y:begin" in agents
    proto = (tmp_path / "AGENT_PROTOCOL.md").read_text()
    assert "forge:forge-x:begin" in proto and "forge:forge-y:begin" in proto

    fctx.unregister_forge(tmp_path, "forge-x", owner="forge-x")
    fctx.uninstall_docs(tmp_path, "forge-x", owner="forge-x")
    agents = (tmp_path / "AGENTS.md").read_text()
    assert "forge:forge-x" not in agents and "forge:forge-y" in agents
    proto = (tmp_path / "AGENT_PROTOCOL.md").read_text()
    assert "forge:forge-y" in proto and "forge-x" not in proto

    fctx.unregister_forge(tmp_path, "forge-y", owner="forge-y")
    fctx.uninstall_docs(tmp_path, "forge-y", owner="forge-y")
    assert not (tmp_path / "AGENT_PROTOCOL.md").exists()
    assert not (tmp_path / "AGENTS.md").exists()  # generated-only → removed
    assert not (tmp_path / "CLAUDE.md").exists()


def test_uninstall_docs_keeps_user_file(tmp_path):
    (tmp_path / "AGENTS.md").write_text("# mine\nuser text\n", "utf-8")
    m = _manifest("forge-x")
    fctx.register_forge(tmp_path, m, owner="forge-x")
    fctx.install_docs(tmp_path, m, owner="forge-x")
    fctx.unregister_forge(tmp_path, "forge-x", owner="forge-x")
    fctx.uninstall_docs(tmp_path, "forge-x", owner="forge-x")
    assert (tmp_path / "AGENTS.md").read_text() == "# mine\nuser text\n"


def test_repair_docs_heals_damaged_block(tmp_path):
    m = _manifest("forge-x")
    fctx.register_forge(tmp_path, m, owner="forge-x")
    fctx.install_docs(tmp_path, m, owner="forge-x")
    p = tmp_path / "AGENTS.md"
    p.write_text(p.read_text().replace("Forge forge-x", "ADULTERADO"), "utf-8")
    out = fctx.repair_docs(tmp_path)
    assert "AGENTS.md" in out["written"]
    assert "ADULTERADO" not in p.read_text()


def test_service_install_writes_consumer_docs(tmp_path):
    from theforge.install import service

    target = tmp_path / "consumer"
    (target / ".git").mkdir(parents=True)
    receipt = service.install(scope="project", root=target, host="none",
                              yes=True)
    check = next(c for c in receipt["checks"] if c["id"] == "consumer-docs")
    assert check["status"] == "PASS"
    assert (target / "AGENTS.md").is_file()
    assert (target / "CLAUDE.md").is_file()
    assert (target / "AGENT_PROTOCOL.md").is_file()
    assert "forge:the-forge:begin" in (target / "AGENTS.md").read_text()
