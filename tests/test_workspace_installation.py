"""install-2.1 (cycle-16 wave-01 part 2, ADR-0065) —
``forge/WorkspaceInstallation/v2`` contract, consolidated plan, typed
install delegation, cross-forge ownership inventory and the init marker.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from theforge import _installkit as kit
from theforge.contracts import (
    ForgeInstallation,
    InstallResource,
    InstallSurface,
    PathConflict,
    Signals,
    WorkspaceInstallation,
    axes_index,
)
from theforge.contracts.base import ContractError, from_dict, to_dict
from theforge.install import service


@pytest.fixture()
def forge_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("FORGE_HOME_OVERRIDE", str(home))
    return home


def _register(forge_home: Path, doc: dict) -> None:
    inst = forge_home / ".forge" / "installations"
    inst.mkdir(parents=True, exist_ok=True)
    (inst / f"{doc['forge_id']}.json").write_text(json.dumps(doc), "utf-8")


def _stub_receipt(fid: str, planned: list[dict], *, writes: list[dict] | None = None) -> str:
    """A child CLI stub: emits a valid ``forge/InstallReceipt/v1`` — the
    plan receipt on --dry-run, the apply receipt otherwise."""
    return (
        "import json, sys\n"
        "planned = '--dry-run' in sys.argv\n"
        "doc = {\n"
        " 'schema': 'forge/InstallReceipt/v1', 'receipt_id': 'sha256:stub',\n"
        f" 'forge_id': {fid!r}, 'operation': 'install',\n"
        " 'status': 'planned' if planned else 'completed',\n"
        " 'verification': {'status': 'UNVERIFIED' if planned else 'PASS'},\n"
        " 'checks': [],\n"
        f" 'managed_files': {json.dumps(writes or [])} if not planned else [],\n"
        f" 'planned_files': {json.dumps(planned)} if planned else [],\n"
        "}\n"
        "print(json.dumps(doc))\n"
    )


def _register_stub(
    forge_home: Path,
    fid: str,
    planned: list[dict],
    *,
    writes: list[dict] | None = None,
    kind: str = "content",
    install: dict | None = None,
    depends_on: list[str] | None = None,
) -> None:
    stub = forge_home / f"{fid}-stub.py"
    stub.write_text(_stub_receipt(fid, planned, writes=writes), "utf-8")
    doc: dict = {
        "forge_id": fid,
        "cli": {"name": fid},
        "install_command": ["{python}", str(stub).replace("\\", "/")],
        "installation_kind": kind,
    }
    if install is not None:
        doc["install"] = install
    if depends_on is not None:
        doc["depends_on"] = depends_on
    _register(forge_home, doc)


# --------------------------------------------------------------------------
# forge/WorkspaceInstallation/v2 — the consolidated contract
# --------------------------------------------------------------------------


def test_workspace_installation_roundtrip() -> None:
    doc = WorkspaceInstallation(
        workspace_root="/ws",
        created_at="t",
        updated_at="t",
        order=["the-forge"],
        forges=[
            ForgeInstallation(
                forge_id="the-forge",
                installation_kind="control-tool",
                surface=InstallSurface(
                    operations=["apply", "uninstall"],
                    flags=["--scope", "--yes"],
                    scopes=["project"],
                ),
                resources=[
                    InstallResource(
                        id="the-forge:AGENTS.md",
                        kind="managed-block",
                        location="AGENTS.md",
                        sha256="a" * 64,
                        owner="the-forge",
                        policy="forge-owned",
                    )
                ],
                owned_paths=["AGENTS.md"],
                classification="new",
                verification="PASS",
            )
        ],
    )
    data = to_dict(doc)
    assert data["schema"] == "forge/WorkspaceInstallation/v2"
    assert data["forges"][0]["installation_kind"] == "control-tool"
    back = from_dict(WorkspaceInstallation, data, strict=True)
    assert back == doc


def test_installation_kind_closed() -> None:
    with pytest.raises((ContractError, TypeError)):
        ForgeInstallation(forge_id="x", installation_kind="bogus")


def test_install_surface_validates_declared_values() -> None:
    with pytest.raises(ContractError):
        InstallSurface(operations=["teleport"])
    with pytest.raises(ContractError):
        InstallSurface(scopes=["galactic"])
    with pytest.raises(ContractError):
        InstallSurface(flags=["-x"])  # only --long flags
    with pytest.raises(ContractError):
        InstallSurface(hosts=["emacs"])


def test_path_conflict_winner_loser_must_be_claimants() -> None:
    with pytest.raises(ContractError):
        PathConflict(path="x", claimants=["a", "b"], winner="a", loser="a")
    with pytest.raises(ContractError):
        PathConflict(path="x", claimants=["a", "b"], winner="c", loser="a")


def test_manifest_for_declares_installation_surface() -> None:
    spec = kit.ForgeSpec(
        forge_id="x",
        package="x",
        distribution="x",
        cli_name="x",
        python_spec=">=3.10",
        state_dir=".x",
    )
    doc = kit.manifest_for(
        spec,
        install_root=Path("/i"),
        venv=None,
        version="1.0.0",
        source={"kind": "git-checkout", "path": "c"},
        shim=None,
        installation_kind="control-tool",
        install={"flags": ["--yes"], "operations": ["apply"]},
        depends_on=["the-forge"],
    )
    assert doc["installation_kind"] == "control-tool"
    assert doc["install"] == {"flags": ["--yes"], "operations": ["apply"]}
    assert doc["depends_on"] == ["the-forge"]
    with pytest.raises(kit.InstallError):
        kit.manifest_for(
            spec,
            install_root=Path("/i"),
            venv=None,
            version="1.0.0",
            source={"kind": "git-checkout", "path": "c"},
            shim=None,
            installation_kind="bogus",
        )


# --------------------------------------------------------------------------
# install order + typed delegation
# --------------------------------------------------------------------------


def test_install_order_topological_and_noted() -> None:
    manifests = [
        {"forge_id": "forge-c", "depends_on": ["forge-b"]},
        {"forge_id": "forge-a"},
        {"forge_id": "forge-b"},
    ]
    order, notes = service._install_order(manifests)
    ids = [m["forge_id"] for m in order]
    assert ids.index("forge-b") < ids.index("forge-c")
    # declared deps are honored — the "stable default" note is not emitted
    assert not any("stable default" in n for n in notes)


def test_install_order_undeclared_is_stable_and_noted() -> None:
    manifests = [
        {"forge_id": "forge-z", "installation_kind": "content"},
        {"forge_id": "the-forge", "installation_kind": "control-tool"},
        {"forge_id": "forge-a", "installation_kind": "service"},
    ]
    order, notes = service._install_order(manifests)
    assert [m["forge_id"] for m in order] == ["the-forge", "forge-a", "forge-z"]
    assert any("stable default" in n for n in notes)


def test_install_order_cycle_broken_honestly() -> None:
    manifests = [
        {"forge_id": "a", "depends_on": ["b"]},
        {"forge_id": "b", "depends_on": ["a"]},
    ]
    order, notes = service._install_order(manifests)
    assert sorted(m["forge_id"] for m in order) == ["a", "b"]
    assert any("cycle" in n for n in notes)


def test_delegated_cmd_honors_declared_flags() -> None:
    """A declared ``install.flags`` list is honored verbatim: a request
    flag the surface does not declare makes the request unhonorable —
    E_UNSUPPORTED, never a silent widen."""
    manifest = {
        "forge_id": "f",
        "cli": {"name": "f-cli"},
        "install": {"flags": ["--scope", "--root", "--yes"]},
    }
    with pytest.raises(kit.InstallError) as exc:
        service._delegated_cmd(manifest, "project", Path("T"), False)
    assert exc.value.kind == kit.E_UNSUPPORTED
    # every request flag declared -> argv carries them
    manifest["install"]["flags"] += ["--host", "--profile"]
    argv = service._delegated_cmd(manifest, "project", Path("T"), False)
    assert "--host" in argv and "--profile" in argv and "--yes" in argv
    # dry-run needs --dry-run declared
    with pytest.raises(kit.InstallError):
        service._delegated_cmd(manifest, "project", Path("T"), True)


def test_delegated_cmd_declared_approval_flag() -> None:
    manifest = {
        "forge_id": "f",
        "cli": {"name": "f-cli"},
        "install": {
            "flags": ["--scope", "--root", "--host", "--profile", "--approve"],
            "approval": "--approve",
        },
    }
    argv = service._delegated_cmd(manifest, "project", Path("T"), False)
    assert argv[-1] == "--approve"
    assert "--yes" not in argv


# --------------------------------------------------------------------------
# consolidated plan + cross-forge conflicts
# --------------------------------------------------------------------------


def _the_forge_manifest(forge_home: Path) -> None:
    _register(
        forge_home,
        {"forge_id": "the-forge", "cli": {"name": "theforge"}, "installation_kind": "control-tool"},
    )


def test_auto_dry_run_emits_consolidated_plan(forge_home: Path, tmp_path: Path) -> None:
    _the_forge_manifest(forge_home)
    _register_stub(
        forge_home,
        "forge-x",
        [{"path": "x.txt", "kind": "skill", "action": "create", "sha256": "a"}],
    )
    target = tmp_path / "consumer"
    target.mkdir()
    out = service.install_auto(scope="project", root=target, dry_run=True)
    doc = out["installation"]
    assert doc["schema"] == "forge/WorkspaceInstallation/v2"
    assert doc["order"][0] == "the-forge"  # control-tool ranks first
    by_id = {f["forge_id"]: f for f in doc["forges"]}
    assert by_id["forge-x"]["classification"] == "new"
    assert by_id["the-forge"]["classification"] == "new"
    assert doc["conflicts"] == []
    # nothing written — plan-only
    assert not (target / "x.txt").exists()
    assert not (target / ".forge").exists()


def test_cross_forge_path_conflict_plan_and_apply(forge_home: Path, tmp_path: Path) -> None:
    """Two forges claiming the same managed asset path: the plan reports
    the conflict, apply honors it — the loser path is skipped, never
    last-writer-wins."""
    shared = {
        "path": ".agents/skills/shared/SKILL.md",
        "kind": "skill",
        "action": "create",
        "sha256": "b" * 64,
    }
    _register_stub(
        forge_home,
        "forge-a",
        [dict(shared)],
        writes=[{**shared, "action": "created"}],
    )
    _register_stub(
        forge_home,
        "forge-b",
        [dict(shared)],
        writes=[{**shared, "action": "unchanged", "note": "user-owned, not managed — skipped"}],
    )
    target = tmp_path / "consumer"
    target.mkdir()

    plan = service.install_auto(scope="project", root=target, dry_run=True)
    conflicts = plan["installation"]["conflicts"]
    assert [(c["path"], c["winner"], c["loser"]) for c in conflicts] == [
        (".agents/skills/shared/SKILL.md", "forge-a", "forge-b")
    ]
    loser = next(f for f in plan["installation"]["forges"] if f["forge_id"] == "forge-b")
    assert loser["classification"] == "conflict"
    assert conflicts[0]["resolution"] is None  # plan-only records no outcome

    out = service.install_auto(scope="project", root=target, yes=True)
    applied = out["installation"]["conflicts"][0]
    assert applied["resolution"] == "skipped"
    assert out["status"] == "completed"


def test_loser_overwriting_is_named_not_silent(forge_home: Path, tmp_path: Path) -> None:
    """A rogue child that writes the loser path anyway is a recorded plan
    violation — FAIL, never a silent last-writer-wins."""
    shared = {
        "path": ".agents/skills/shared/SKILL.md",
        "kind": "skill",
        "action": "create",
        "sha256": "b" * 64,
    }
    _register_stub(forge_home, "forge-a", [dict(shared)], writes=[{**shared, "action": "created"}])
    _register_stub(
        forge_home, "forge-b", [dict(shared)], writes=[{**shared, "action": "created"}]
    )  # rogue: claims the write
    target = tmp_path / "consumer"
    target.mkdir()
    out = service.install_auto(scope="project", root=target, yes=True)
    applied = out["installation"]["conflicts"][0]
    assert applied["resolution"].startswith("overwritten")
    assert any(c["id"] == "cross-forge-conflicts" and c["status"] == "FAIL" for c in out["checks"])


def test_mcp_and_marker_kinds_never_conflict(forge_home: Path, tmp_path: Path) -> None:
    """``mcp`` managed keys and ``marker`` managed blocks are namespaced
    per forge — two forges writing the same file is NOT a path conflict."""
    same = [
        {"path": ".mcp.json", "kind": "mcp", "action": "create", "sha256": "x"},
        {"path": "AGENTS.md", "kind": "marker", "action": "update", "sha256": "y"},
    ]
    _register_stub(forge_home, "forge-a", [dict(f) for f in same])
    _register_stub(forge_home, "forge-b", [dict(f) for f in same])
    target = tmp_path / "consumer"
    target.mkdir()
    out = service.install_auto(scope="project", root=target, dry_run=True)
    assert out["installation"]["conflicts"] == []


def test_unsupported_capability_classification(forge_home: Path, tmp_path: Path) -> None:
    _register(forge_home, {"forge_id": "ghost"})  # no cli/install_command
    target = tmp_path / "consumer"
    target.mkdir()
    out = service.install_auto(scope="project", root=target, dry_run=True)
    forge = out["installation"]["forges"][0]
    assert forge["classification"] == "unsupported-capability"
    assert forge["verification"] == "BLOCKED"


# --------------------------------------------------------------------------
# consolidated ownership inventory (persisted)
# --------------------------------------------------------------------------


def test_workspace_install_json_carries_installation(forge_home: Path, tmp_path: Path) -> None:
    """The persisted ``forge/WorkspaceInstall/v1`` manifest carries the
    ``forge/WorkspaceInstallation/v2`` inventory: per-forge owned paths,
    qualified resources with hashes, policy and provenance."""
    ws = tmp_path / "ws"
    (ws / "backend-api" / ".git").mkdir(parents=True)
    _the_forge_manifest(forge_home)
    _register_stub(
        forge_home,
        "forge-x",
        [
            {
                "path": ".agents/skills/x/SKILL.md",
                "kind": "skill",
                "action": "create",
                "sha256": "c" * 64,
            }
        ],
        writes=[
            {
                "path": ".agents/skills/x/SKILL.md",
                "kind": "skill",
                "action": "created",
                "sha256": "c" * 64,
            }
        ],
    )
    out = service.install_auto(scope="workspace", root=ws, yes=True)
    manifest = json.loads((ws / ".forge" / "workspace-install.json").read_text("utf-8"))
    assert manifest["schema"] == "forge/WorkspaceInstall/v1"
    inst = manifest["installation"]
    assert inst["schema"] == "forge/WorkspaceInstallation/v2"
    fx = next(f for f in inst["forges"] if f["forge_id"] == "forge-x")
    assert fx["owned_paths"] == [".agents/skills/x/SKILL.md"]
    res = fx["resources"][0]
    assert res["id"] == "forge-x:.agents/skills/x/SKILL.md"
    assert res["sha256"] == "c" * 64
    assert res["owner"] == "forge-x"
    assert fx["ownership_source"] == "receipt"
    # the consolidated doc also lands on the receipt + member list
    assert out["installation"]["members"] == ["backend-api"]


# --------------------------------------------------------------------------
# theforge init — workspace marker round-trip
# --------------------------------------------------------------------------


def test_init_writes_workspace_marker(tmp_path: Path) -> None:
    """``theforge init`` creates ``forge.workspace.yaml`` — the marker the
    installkit's workspace-root search recognizes, so ``init`` +
    ``setup --scope workspace`` round-trips."""
    from theforge.state import init_workspace

    created = init_workspace(tmp_path)
    assert "forge.workspace.yaml" in created
    assert (tmp_path / "forge.workspace.yaml").exists()
    # the installkit resolves this directory as the workspace root
    spec = service._spec()
    resolved = kit.resolve_scope(spec, "workspace", tmp_path, None)
    assert resolved == tmp_path.resolve()
    # idempotent: a second init does not rewrite the marker
    created2 = init_workspace(tmp_path)
    assert "forge.workspace.yaml" not in created2


def test_init_marker_does_not_shadow_existing(tmp_path: Path) -> None:
    from theforge.state import init_workspace

    (tmp_path / "forge.workspace.yaml").write_text("custom: true\n", "utf-8")
    init_workspace(tmp_path)
    assert (tmp_path / "forge.workspace.yaml").read_text("utf-8") == "custom: true\n"


# --------------------------------------------------------------------------
# Signals classification axes
# --------------------------------------------------------------------------


def test_signals_axes_optional_and_indexed() -> None:
    from theforge.contracts.manifest import Capability, ForgeManifest

    cap = Capability(
        id="spark.emit",
        actions=["run"],
        default_action="run",
        state="supported",
        operation_class="read_only",
        signals=Signals(
            keywords=["spark"],
            platform=["linux"],
            service=["mcp-server"],
            language=["python"],
            artifact_type=["code-analysis-evidence"],
        ),
    )
    manifest = ForgeManifest(
        id="spark-forge",
        version="1.0.0",
        protocols=["forge/v1"],
        ops=["describe", "health"],
        capabilities=[cap],
    )
    idx = axes_index(manifest)
    assert idx["platform"]["linux"] == ["spark.emit"]
    assert idx["artifact_type"]["code-analysis-evidence"] == ["spark.emit"]
    # undeclared axes are omitted, never invented
    assert "language" not in axes_index(
        ForgeManifest(
            id="x",
            version="1.0.0",
            protocols=["forge/v1"],
            ops=["describe", "health"],
        )
    )


# --------------------------------------------------------------------------
# safe apply default
# --------------------------------------------------------------------------


def test_approve_plan_defaults_to_no(monkeypatch: pytest.MonkeyPatch) -> None:
    """Interactive apply confirmation defaults to No — an empty Enter
    never writes (install-2.1 safe default)."""
    from theforge.ui import kit as uikit

    seen: dict[str, bool] = {}
    monkeypatch.setattr(uikit, "confirm", lambda *a, **k: seen.setdefault("d", k["default"]))
    ctx = uikit.UIContext(interactive=True, color=False, unicode=False, width=80, language="en")
    assert uikit.approve_plan({"forge_id": "f", "operation": "install"}, ctx=ctx) is False
    assert seen["d"] is False


def test_format_status_doc_renders_consolidated_plan(tmp_path: Path) -> None:
    from theforge.ui.kit import UIContext, format_status_doc

    doc = {
        "forge_id": "the-forge",
        "operation": "install-auto",
        "status": "planned",
        "scope": "workspace",
        "host": "all",
        "installation": {
            "schema": "forge/WorkspaceInstallation/v2",
            "order": ["the-forge", "forge-a"],
            "forges": [
                {"forge_id": "the-forge", "classification": "new", "verification": "UNVERIFIED"},
                {
                    "forge_id": "forge-a",
                    "classification": "conflict",
                    "verification": "UNVERIFIED",
                    "classification_detail": "loses 1 path",
                },
            ],
            "conflicts": [
                {
                    "path": ".agents/x/SKILL.md",
                    "winner": "the-forge",
                    "loser": "forge-a",
                    "resolution": None,
                }
            ],
            "order_note": "stable default order",
        },
    }
    ctx = UIContext(interactive=False, color=False, unicode=False, width=100, language="en")
    text = format_status_doc(doc, ctx=ctx)
    assert "INSTALLATION PLAN" in text
    assert "the-forge" in text and "forge-a" in text
    assert "conflict" in text and ".agents/x/SKILL.md" in text
    assert "new 1" in text and "conflict 1" in text
