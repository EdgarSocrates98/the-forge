"""Portable install lifecycle for The Forge — ``forge/*`` contract v1 over
the vendored installkit (``theforge._installkit``, ADR-0058).

`install apply` writes managed host assets into the consumer repo;
`install auto` delegates to every forge registered by the bootstrap under
``~/.forge/installations/`` — the control plane coordinates, each forge
installs itself. Stdlib-only; the only subprocess use is the explicit
``auto`` delegation and ``update``'s pip call.
"""

from __future__ import annotations

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
    kinds = set(kit.profile_asset_kinds(ctx.profile))
    return render.render(ctx.hosts, skills="skill" in kinds)


def _ctx(scope: str, root: Path | None, hosts: tuple[str, ...],
         profile: str, dry_run: bool, cwd: Path | None = None) -> kit.InstallContext:
    spec = _spec()
    base = Path(cwd or Path.cwd())
    target = kit.resolve_scope(spec, scope, base, root)
    return kit.InstallContext(
        spec=spec, scope=scope, root=target,
        state_dir=kit.state_dir_for(spec, scope, target),
        profile=profile, hosts=hosts, dry_run=dry_run)


def _hosts(host: str | None) -> tuple[str, ...]:
    if not host or host == "all":
        return render.HOSTS
    if host not in render.HOSTS:
        raise kit.InstallError(
            kit.E_HOST, f"host {host!r}; conhecidos: {list(render.HOSTS)} + all")
    return (host,)


def install(host: str = "all", *, scope: str = "project",
            root: Path | None = None, profile: str = "recommended",
            yes: bool = False, dry_run: bool = False) -> dict[str, Any]:
    if profile not in PROFILES:
        raise kit.InstallError(kit.E_PROFILE, f"profile {profile!r}; {PROFILES}")
    ctx = _ctx(scope, root, _hosts(host), profile, dry_run)
    if dry_run:
        return kit.apply_install(ctx, approved=yes)
    with kit.acquire_lock(ctx.state_dir):
        receipt = kit.apply_install(ctx, approved=yes)
    if not dry_run and receipt.get("status") == "completed":
        kit._write_receipt(ctx.state_dir, receipt)
    return receipt


def status(*, scope: str = "project", root: Path | None = None) -> dict[str, Any]:
    return kit.status(_ctx(scope, root, (), "recommended", True))


def doctor(*, scope: str = "project", root: Path | None = None) -> dict[str, Any]:
    return kit.doctor(_ctx(scope, root, (), "recommended", True))


def repair(*, scope: str = "project", root: Path | None = None,
           dry_run: bool = False) -> dict[str, Any]:
    ctx = _ctx(scope, root, render.HOSTS, "full", dry_run)
    if dry_run:
        return kit.status(ctx)
    with kit.acquire_lock(ctx.state_dir):
        return kit.repair(ctx)


def uninstall(*, scope: str = "project", root: Path | None = None,
              purge: bool = False, dry_run: bool = False) -> dict[str, Any]:
    ctx = _ctx(scope, root, (), "recommended", dry_run)
    if not ctx.state_dir.exists() or dry_run:
        if not dry_run:
            # Nothing installed: idempotent no-op that writes no state.
            return _receipt("uninstall", [{"id": "uninstall", "status": "PASS",
                                           "detail": "0 removed, 0 kept"}],
                            "completed") | {"removed": [], "kept": [],
                                            "scope": scope,
                                            "target_root": str(ctx.root)}
        st = kit.status(ctx)
        return {"schema": kit.SCHEMA_RECEIPT, "forge_id": FORGE_ID,
                "operation": "uninstall", "scope": scope, "dry_run": True,
                "planned": st.get("drift", {}), "status": "planned",
                "verification": {"status": "UNVERIFIED"},
                "created_at": kit._utc_now()}
    with kit.acquire_lock(ctx.state_dir):
        return kit.uninstall(ctx, purge_state=purge)


def update(*, to: str | None = None, repo: Path | None = None,
           dry_run: bool = False) -> dict[str, Any]:
    if to == "latest":
        return _receipt("update", [{"id": "version", "status": "FAIL",
                                    "detail": "'latest' nunca e instalavel"}],
                        "failed")
    manifest = _manifest()
    src = repo or (Path(p) if (p := (manifest.get("source") or {}).get("path"))
                   else None)
    if src is None or not src.exists():
        return _receipt("update", [{"id": "source", "status": "BLOCKED",
                                    "detail": "sem checkout registrado"}],
                        "failed")
    venv = manifest.get("venv")
    if not venv:
        return _receipt("update", [{"id": "venv", "status": "FAIL",
                                    "detail": "sem venv; rode scripts/forge_bootstrap.py"}],
                        "failed")
    venv_py = Path(venv) / ("Scripts/python.exe" if sys.platform == "win32"
                            else "bin/python")
    cmd = [str(venv_py), "-m", "pip", "install", "--upgrade", str(src)]
    if dry_run:
        return _receipt("update", [{"id": "pip", "status": "UNVERIFIED",
                                    "detail": " ".join(cmd)}], "planned")
    import subprocess
    proc = subprocess.run(  # venv python + fixed pip args
        cmd, capture_output=True, text=True, timeout=900, check=False)
    checks = [{"id": "pip",
               "status": "PASS" if proc.returncode == 0 else "FAIL",
               "detail": (proc.stdout or proc.stderr)[-300:]}]
    return _receipt("update", checks,
                    "completed" if proc.returncode == 0 else "failed")


# --------------------------------------------------------------------------
# install auto + installations registry
# --------------------------------------------------------------------------

def _manifest() -> dict[str, Any]:
    doc = kit._load_json(kit.installations_dir() / f"{FORGE_ID}.json", None)
    return doc if isinstance(doc, dict) else {}


def installations() -> list[dict[str, Any]]:
    return kit.installed_forges()


def install_auto(*, scope: str = "project", root: Path | None = None,
                 yes: bool = False, dry_run: bool = False,
                 forge: str | None = None,
                 cwd: Path | None = None) -> dict[str, Any]:
    """Orquestra a familia: cada forge registrada no bootstrap instala a si
    mesma no alvo resolvido. Delega ao CLI real — nunca simula.
    ``forge`` restringe a delegação a uma única forge."""
    spec = _spec()
    base = Path(cwd or Path.cwd())
    target = kit.resolve_scope(spec, scope, base, root)
    found = kit.installed_forges()
    if forge is not None:
        found = [m for m in found if m.get("forge_id") == forge]
        if not found:
            raise kit.InstallError(
                kit.E_NOTINSTALLED,
                f"forge {forge!r} nao registrada em ~/.forge/installations")
    checks: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    if not found:
        checks.append({"id": "registry", "status": "BLOCKED",
                       "detail": "nenhuma forge registrada em "
                                 "~/.forge/installations — rode o setup"})
        return {"schema": kit.SCHEMA_RECEIPT, "forge_id": FORGE_ID,
                "operation": "install-auto", "scope": scope,
                "target_root": str(target), "checks": checks,
                "managed_files": [], "forges": [],
                "verification": {"status": "FAIL"}, "status": "failed",
                "created_at": kit._utc_now()}
    for manifest in found:
        cli = ((manifest.get("cli") or {}).get("name")
               or manifest.get("forge_id"))
        fid = manifest.get("forge_id", "?")
        if fid == FORGE_ID:
            out = (install(scope=scope, root=target, yes=yes, dry_run=dry_run)
                   if (yes or dry_run) else
                   {"status": "refused", "detail": "sem --yes"})
            results.append({"forge_id": fid, "via": "self", **{
                k: out.get(k) for k in ("status", "verification")}})
            checks.append({"id": f"forge:{fid}",
                           "status": "PASS" if out.get("status") in
                           ("completed", "planned") else "FAIL",
                           "detail": out.get("status")})
            continue
        cmd = [str(cli), "install", "--scope", scope, "--root", str(target)]
        cmd.append("--dry-run" if dry_run else "--yes")
        if not (yes or dry_run):
            results.append({"forge_id": fid, "status": "refused",
                            "detail": "sem --yes"})
            checks.append({"id": f"forge:{fid}", "status": "BLOCKED",
                           "detail": "approval gate — sem --yes"})
            continue
        import shutil
        if shutil.which(str(cli)) is None:
            results.append({"forge_id": fid, "status": "blocked",
                            "detail": f"cli {cli} nao resolvido no PATH"})
            checks.append({"id": f"forge:{fid}", "status": "BLOCKED",
                           "detail": f"{cli} nao encontrado"})
            continue
        if dry_run:
            results.append({"forge_id": fid, "status": "planned",
                            "cmd": cmd})
            checks.append({"id": f"forge:{fid}", "status": "UNVERIFIED",
                           "detail": " ".join(cmd)})
            continue
        import subprocess
        proc = subprocess.run(  # delegation to the forge's own governed CLI
            cmd, capture_output=True, text=True, timeout=600, check=False)
        ok = proc.returncode == 0
        results.append({"forge_id": fid, "status": "completed" if ok else "failed",
                        "returncode": proc.returncode})
        checks.append({"id": f"forge:{fid}",
                       "status": "PASS" if ok else "FAIL",
                       "detail": (proc.stdout or proc.stderr)[-200:]})
    overall = "planned" if dry_run else (
        "completed" if all(
            c["status"] in ("PASS", "UNVERIFIED") for c in checks)
        else "failed")
    return {
        "schema": kit.SCHEMA_RECEIPT, "forge_id": FORGE_ID,
        "operation": "install-auto", "scope": scope,
        "target_root": str(target), "dry_run": dry_run,
        "checks": checks, "forges": results, "managed_files": [],
        "verification": {"status": "PASS" if overall == "completed" else
                         ("UNVERIFIED" if dry_run else "FAIL")},
        "status": overall, "created_at": kit._utc_now(),
        "created_by": f"theforge/{__version__}",
    }


def _receipt(operation: str, checks: list[dict[str, Any]],
             status: str) -> dict[str, Any]:
    return {
        "schema": kit.SCHEMA_RECEIPT, "forge_id": FORGE_ID,
        "operation": operation, "managed_files": [], "checks": checks,
        "verification": {"status": "PASS" if all(
            c["status"] in ("PASS", "NOT_APPLICABLE", "UNVERIFIED")
            for c in checks) else "FAIL"},
        "status": status, "created_at": kit._utc_now(),
        "created_by": f"theforge/{__version__}",
    }


__all__ = ["PROFILES", "SCOPES", "doctor", "install", "install_auto",
           "installations", "repair", "status", "uninstall", "update"]
