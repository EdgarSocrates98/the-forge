"""Portable install lifecycle for The Forge — ``forge/*`` contract v1 over
the vendored installkit (``theforge._installkit``, ADR-0058).

`install apply` writes managed host assets into the consumer repo;
`install auto` delegates to every forge registered by the bootstrap under
``~/.forge/installations/`` — the control plane coordinates, each forge
installs itself. Stdlib-only; the only subprocess use is the explicit
``auto`` delegation and ``update``'s pip call.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from theforge import __version__
from theforge import _installkit as kit
from theforge.install import render

FORGE_ID = "the-forge"
STATE_DIR = ".forge/install"
PROFILES: tuple[str, ...] = ("minimal", "recommended", "full")
SCOPES: tuple[str, ...] = ("project", "workspace", "user")


def _spec() -> kit.ForgeSpec:
    return kit.ForgeSpec(
        forge_id=FORGE_ID,
        package="theforge",
        distribution="theforge",
        cli_name="theforge",
        python_spec=">=3.11",
        state_dir=STATE_DIR,
        mcp_command=(),
        mcp_server_name=None,
        version_cmd=("--version",),
        render_assets=_render_for,
        marker_files=("AGENTS.md", "CLAUDE.md"),
        marker_body=(
            "**The Forge** esta instalado neste projeto.\n\n"
            "- Skills: mirrors gerenciados nos diretorios de host\n"
            "- Ciclo de vida: `theforge install status|doctor|repair|uninstall`\n\n"
            "Conteudo entre os marcadores `the-forge:managed` e gerenciado; "
            "o que estiver fora e do usuario."
        ),
        user_state_dir="~/.forge",
    )


def _render_for(ctx: kit.InstallContext) -> dict[str, bytes]:
    kinds = set(kit.asset_kinds_for(ctx))
    return render.render(ctx.hosts, skills="skill" in kinds)


def _ctx(
    scope: str,
    root: Path | None,
    hosts: tuple[str, ...],
    profile: str,
    dry_run: bool,
    cwd: Path | None = None,
    components: tuple[str, ...] | None = None,
) -> kit.InstallContext:
    spec = _spec()
    base = Path(cwd or Path.cwd())
    target = kit.resolve_scope(spec, scope, base, root)
    return kit.InstallContext(
        spec=spec,
        scope=scope,
        root=target,
        state_dir=kit.state_dir_for(spec, scope, target),
        profile=profile,
        hosts=hosts,
        dry_run=dry_run,
        options=kit.component_options(profile, components),
    )


def _hosts(host: str | None) -> tuple[str, ...]:
    """Resolve o contrato de hosts: ``all`` → todos; ``none``/ausente →
    nenhum host configurado (opt-out explícito, nunca "todos"); um nome ou
    csv de nomes → o subconjunto validado."""
    if host == "all":
        return render.HOSTS
    if not host or host == "none":
        return ()
    names = [h.strip() for h in host.split(",") if h.strip()]
    unknown = [h for h in names if h not in render.HOSTS]
    if unknown:
        raise kit.InstallError(
            kit.E_HOST,
            f"host {unknown[0]!r}; conhecidos: {list(render.HOSTS)} + all,none",
        )
    return tuple(dict.fromkeys(names))


def install(
    host: str = "all",
    *,
    scope: str = "project",
    root: Path | None = None,
    profile: str = "recommended",
    yes: bool = False,
    dry_run: bool = False,
    components: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    if profile not in PROFILES:
        raise kit.InstallError(kit.E_PROFILE, f"profile {profile!r}; {PROFILES}")
    ctx = _ctx(scope, root, _hosts(host), profile, dry_run, components=components)
    if dry_run:
        return kit.apply_install(ctx, approved=yes)
    with kit.acquire_lock(ctx.state_dir) as lock:
        receipt = kit.apply_install(ctx, approved=yes)
        if lock.recovered:
            receipt.setdefault("checks", []).append(
                {
                    "id": "lock",
                    "status": "PASS",
                    "detail": "stale lock reclaimed (interrupted install recovered)",
                }
            )
    if not dry_run and receipt.get("status") == "completed":
        kit._write_receipt(ctx.state_dir, receipt)
    return receipt


def status(*, scope: str = "project", root: Path | None = None) -> dict[str, Any]:
    return kit.status(_ctx(scope, root, (), "recommended", True))


def doctor(*, scope: str = "project", root: Path | None = None) -> dict[str, Any]:
    return kit.doctor(_ctx(scope, root, (), "recommended", True))


def repair(
    *, scope: str = "project", root: Path | None = None, dry_run: bool = False
) -> dict[str, Any]:
    ctx = _ctx(scope, root, render.HOSTS, "full", dry_run)
    if dry_run:
        return kit.status(ctx)
    with kit.acquire_lock(ctx.state_dir) as lock:
        r = kit.repair(ctx)
        if lock.recovered:
            r.setdefault("checks", []).append(
                {
                    "id": "lock",
                    "status": "PASS",
                    "detail": "stale lock reclaimed (interrupted install recovered)",
                }
            )
        return r


def uninstall(
    *, scope: str = "project", root: Path | None = None, purge: bool = False, dry_run: bool = False
) -> dict[str, Any]:
    ctx = _ctx(scope, root, (), "recommended", dry_run)
    if not ctx.state_dir.exists() or dry_run:
        if not dry_run:
            # Nothing installed: idempotent no-op that writes no state.
            return _receipt(
                "uninstall",
                [{"id": "uninstall", "status": "PASS", "detail": "0 removed, 0 kept"}],
                "completed",
            ) | {"removed": [], "kept": [], "scope": scope, "target_root": str(ctx.root)}
        st = kit.status(ctx)
        return {
            "schema": kit.SCHEMA_RECEIPT,
            "forge_id": FORGE_ID,
            "operation": "uninstall",
            "scope": scope,
            "dry_run": True,
            "planned": st.get("drift", {}),
            "status": "planned",
            "verification": {"status": "UNVERIFIED"},
            "created_at": kit._utc_now(),
        }
    with kit.acquire_lock(ctx.state_dir) as lock:
        r = kit.uninstall(ctx, purge_state=purge)
        if lock.recovered:
            r.setdefault("checks", []).append(
                {
                    "id": "lock",
                    "status": "PASS",
                    "detail": "stale lock reclaimed (interrupted install recovered)",
                }
            )
        return r


def update(
    *, to: str | None = None, repo: Path | None = None, dry_run: bool = False
) -> dict[str, Any]:
    if to == "latest":
        return _receipt(
            "update",
            [{"id": "version", "status": "FAIL", "detail": "'latest' nunca e instalavel"}],
            "failed",
        )
    manifest = _manifest()
    src = repo or (Path(p) if (p := (manifest.get("source") or {}).get("path")) else None)
    if src is None or not src.exists():
        return _receipt(
            "update",
            [{"id": "source", "status": "BLOCKED", "detail": "sem checkout registrado"}],
            "failed",
        )
    venv = manifest.get("venv")
    if not venv:
        return _receipt(
            "update",
            [
                {
                    "id": "venv",
                    "status": "FAIL",
                    "detail": "sem venv; rode scripts/forge_bootstrap.py",
                }
            ],
            "failed",
        )
    venv_py = Path(venv) / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    cmd = [str(venv_py), "-m", "pip", "install", "--upgrade", str(src)]
    if dry_run:
        return _receipt(
            "update", [{"id": "pip", "status": "UNVERIFIED", "detail": " ".join(cmd)}], "planned"
        )
    import subprocess

    proc = subprocess.run(  # venv python + fixed pip args
        cmd, capture_output=True, text=True, timeout=900, check=False
    )
    checks = [
        {
            "id": "pip",
            "status": "PASS" if proc.returncode == 0 else "FAIL",
            "detail": (proc.stdout or proc.stderr)[-300:],
        }
    ]
    return _receipt("update", checks, "completed" if proc.returncode == 0 else "failed")


# --------------------------------------------------------------------------
# install auto + installations registry
# --------------------------------------------------------------------------


def _manifest() -> dict[str, Any]:
    doc = kit._load_json(kit.installations_dir() / f"{FORGE_ID}.json", None)
    return doc if isinstance(doc, dict) else {}


def installations() -> list[dict[str, Any]]:
    return kit.installed_forges()


def _delegated_cmd(manifest: dict[str, Any], scope: str, target: Path, dry_run: bool) -> list[str]:
    """Argv for delegating ``install`` to a sibling forge. Most forges
    expose ``<cli> install``; a manifest may instead carry
    ``install_command`` — an argv template where ``{python}`` resolves to
    the forge's registered venv interpreter and ``{checkout}`` to its
    registered source path (used by forges whose package boundary forbids
    the install engine, e.g. RC-locked CLIs that install via a script)."""
    tpl = manifest.get("install_command")
    if tpl:
        venv = manifest.get("venv") or ""
        py = Path(venv) / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        checkout = str((manifest.get("source") or {}).get("path") or ".")
        argv = [
            a.replace("{python}", str(py) if py.exists() else sys.executable).replace(
                "{checkout}", checkout
            )
            for a in tpl
        ]
    else:
        cli = str((manifest.get("cli") or {}).get("name") or manifest.get("forge_id"))
        argv = [cli]
    return argv + [
        "install",
        "--scope",
        scope,
        "--root",
        str(target),
        "--dry-run" if dry_run else "--yes",
    ]


def install_auto(
    *,
    scope: str = "project",
    root: Path | None = None,
    yes: bool = False,
    dry_run: bool = False,
    forge: str | None = None,
    members: tuple[str, ...] = (),
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Orquestra a familia: cada forge registrada no bootstrap instala a si
    mesma no alvo resolvido. Delega ao CLI real — nunca simula.
    ``forge`` restringe a delegação a uma única forge. No escopo
    ``workspace``, ``members`` seleciona subprojetos (paths relativos ao
    root) para delegação per-member adicional — o default e instalar os
    assets compartilhados no root da workspace sem tocar os membros."""
    spec = _spec()
    base = Path(cwd or Path.cwd())
    target = kit.resolve_scope(spec, scope, base, root)
    found = kit.installed_forges()
    if forge is not None:
        found = [m for m in found if m.get("forge_id") == forge]
        if not found:
            raise kit.InstallError(
                kit.E_NOTINSTALLED, f"forge {forge!r} nao registrada em ~/.forge/installations"
            )
    checks: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    if not found:
        checks.append(
            {
                "id": "registry",
                "status": "BLOCKED",
                "detail": "nenhuma forge registrada em ~/.forge/installations — rode o setup",
            }
        )
        return {
            "schema": kit.SCHEMA_RECEIPT,
            "forge_id": FORGE_ID,
            "operation": "install-auto",
            "scope": scope,
            "target_root": str(target),
            "checks": checks,
            "managed_files": [],
            "forges": [],
            "verification": {"status": "FAIL"},
            "status": "failed",
            "created_at": kit._utc_now(),
        }
    for manifest in found:
        fid = manifest.get("forge_id", "?")
        if fid == FORGE_ID:
            out = (
                install(scope=scope, root=target, yes=yes, dry_run=dry_run)
                if (yes or dry_run)
                else {"status": "refused", "detail": "sem --yes"}
            )
            results.append(
                {
                    "forge_id": fid,
                    "via": "self",
                    **{k: out.get(k) for k in ("status", "verification")},
                }
            )
            checks.append(
                {
                    "id": f"forge:{fid}",
                    "status": "PASS" if out.get("status") in ("completed", "planned") else "FAIL",
                    "detail": out.get("status"),
                }
            )
            continue
        cmd = _delegated_cmd(manifest, scope, target, dry_run)
        if not (yes or dry_run):
            results.append({"forge_id": fid, "status": "refused", "detail": "sem --yes"})
            checks.append(
                {"id": f"forge:{fid}", "status": "BLOCKED", "detail": "approval gate — sem --yes"}
            )
            continue
        import shutil

        exe = cmd[0]
        probe_ok = (
            Path(exe).exists()
            if Path(exe).is_absolute() or os.sep in exe
            else shutil.which(exe) is not None
        )
        if not probe_ok:
            results.append({"forge_id": fid, "status": "blocked", "detail": f"{exe} nao resolvido"})
            checks.append(
                {"id": f"forge:{fid}", "status": "BLOCKED", "detail": f"{exe} nao encontrado"}
            )
            continue
        if dry_run:
            results.append({"forge_id": fid, "status": "planned", "cmd": cmd})
            checks.append({"id": f"forge:{fid}", "status": "UNVERIFIED", "detail": " ".join(cmd)})
            continue
        import subprocess

        proc = subprocess.run(  # delegation to the forge's own governed CLI
            cmd, capture_output=True, text=True, timeout=600, check=False
        )
        ok = proc.returncode == 0
        results.append(
            {
                "forge_id": fid,
                "status": "completed" if ok else "failed",
                "returncode": proc.returncode,
            }
        )
        checks.append(
            {
                "id": f"forge:{fid}",
                "status": "PASS" if ok else "FAIL",
                "detail": (proc.stdout or proc.stderr)[-200:],
            }
        )
    overall = (
        "planned"
        if dry_run
        else (
            "completed" if all(c["status"] in ("PASS", "UNVERIFIED") for c in checks) else "failed"
        )
    )
    receipt: dict[str, Any] = {
        "schema": kit.SCHEMA_RECEIPT,
        "forge_id": FORGE_ID,
        "operation": "install-auto",
        "scope": scope,
        "target_root": str(target),
        "dry_run": dry_run,
        "checks": checks,
        "forges": results,
        "managed_files": [],
        "verification": {
            "status": "PASS" if overall == "completed" else ("UNVERIFIED" if dry_run else "FAIL")
        },
        "status": overall,
        "created_at": kit._utc_now(),
        "created_by": f"theforge/{__version__}",
    }
    if scope == "workspace":
        receipt["workspace"] = _workspace_report(
            target, results, found, members=members, approved=yes, dry_run=dry_run
        )
    return receipt


def _workspace_report(
    ws_root: Path,
    results: list[dict[str, Any]],
    manifests: list[dict[str, Any]],
    *,
    members: tuple[str, ...] = (),
    approved: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Member discovery + precedence + the ``forge/WorkspaceInstall/v1``
    manifest for ``install auto --scope workspace``.

    Members = independent ``.git`` checkouts under the root (never
    assumed to be a monorepo). A member already project-installed for a
    forge (own ``.mcp.json`` key or ``<tag>:managed`` marker block) keeps
    project precedence — workspace assets specialize, never widen.
    ``members`` names subprojects (relative paths) for explicit
    per-member delegation through the same governed CLI path."""
    ws_root = Path(ws_root).resolve()
    discovered = kit.discover_projects(ws_root)
    by_rel = {str(m.relative_to(ws_root)) if m != ws_root else ".": m for m in discovered}
    member_entries: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    done = [r for r in results if r.get("status") == "completed"]

    def _member_state(member: Path, fid: str) -> str | None:
        mcp = member / ".mcp.json"
        if mcp.exists():
            doc = kit._load_json(mcp, None)
            if isinstance(doc, dict) and fid in (doc.get("mcpServers") or {}):
                return "project"
        agents = member / "AGENTS.md"
        if agents.exists() and f"{fid}:managed:begin" in agents.read_text(
            encoding="utf-8", errors="replace"
        ):
            return "project"
        return None

    for member in discovered:
        rel = str(member.relative_to(ws_root)) if member != ws_root else "."
        entry: dict[str, Any] = {"path": rel}
        for fid in {r["forge_id"] for r in done}:
            prec = _member_state(member, fid)
            if prec:
                entry.setdefault("precedence", {})[fid] = prec
                conflicts.append(
                    {
                        "member": rel,
                        "forge_id": fid,
                        "decision": prec,
                        "detail": "project install takes precedence — "
                        "workspace assets specialize, never widen",
                    }
                )
        member_entries.append(entry)

    # Explicit per-member delegation — project scope inside each selected
    # member, same governed argv as the workspace-level delegation.
    member_results: list[dict[str, Any]] = []
    unknown_members = [m for m in members if m not in by_rel]
    for rel in members:
        member_dir = by_rel.get(rel)
        if member_dir is None:
            continue  # reported via unknown_members
        for manifest in manifests:
            fid = manifest.get("forge_id", "?")
            if fid == FORGE_ID:
                continue  # self already installed at workspace root
            cmd = _delegated_cmd(manifest, "project", member_dir, dry_run)
            if not (approved or dry_run):
                member_results.append(
                    {"member": rel, "forge_id": fid, "status": "refused", "detail": "approval gate"}
                )
                continue
            if dry_run:
                member_results.append(
                    {"member": rel, "forge_id": fid, "status": "planned", "detail": " ".join(cmd)}
                )
                continue
            import subprocess

            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=False)
            member_results.append(
                {
                    "member": rel,
                    "forge_id": fid,
                    "status": ("completed" if proc.returncode == 0 else "failed"),
                    "receipt_id": f"{rel}/{fid}",
                }
            )

    projects: list[dict[str, Any]] = [
        {
            "path": r["member"],
            "forge_id": r["forge_id"],
            "receipt_id": r["receipt_id"],
            "installed_at": kit._utc_now(),
        }
        for r in member_results
        if r["status"] == "completed"
    ]

    manifest = {
        "schema": "forge/WorkspaceInstall/v1",
        "workspace_root": str(ws_root),
        "projects": projects,
        "created_at": kit._utc_now(),
        "updated_at": kit._utc_now(),
    }
    state = ws_root / ".forge"
    if not dry_run and (done or projects):
        state.mkdir(parents=True, exist_ok=True)
        prev = kit._load_json(state / "workspace-install.json", None)
        if isinstance(prev, dict) and prev.get("created_at"):
            manifest["created_at"] = prev["created_at"]
            merged = {(p["path"], p["forge_id"]): p for p in prev.get("projects", [])}
            for p in projects:
                merged[(p["path"], p["forge_id"])] = p
            manifest["projects"] = sorted(merged.values(), key=lambda p: (p["path"], p["forge_id"]))
        kit._atomic_write(
            state / "workspace-install.json",
            (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode(),
        )
    return {
        "members": member_entries,
        "conflicts": conflicts,
        "member_results": member_results,
        "unknown_members": unknown_members,
        "manifest": manifest,
    }


def _receipt(operation: str, checks: list[dict[str, Any]], status: str) -> dict[str, Any]:
    return {
        "schema": kit.SCHEMA_RECEIPT,
        "forge_id": FORGE_ID,
        "operation": operation,
        "managed_files": [],
        "checks": checks,
        "verification": {
            "status": "PASS"
            if all(c["status"] in ("PASS", "NOT_APPLICABLE", "UNVERIFIED") for c in checks)
            else "FAIL"
        },
        "status": status,
        "created_at": kit._utc_now(),
        "created_by": f"theforge/{__version__}",
    }


__all__ = [
    "PROFILES",
    "SCOPES",
    "doctor",
    "install",
    "install_auto",
    "installations",
    "repair",
    "status",
    "uninstall",
    "update",
]
