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
from theforge.install import providers, render

FORGE_ID = "the-forge"
DIST_NAME = "theforge-core"  # PyPI dist name — import package stays `theforge`
STATE_DIR = ".forge/install"
PROFILES: tuple[str, ...] = ("minimal", "recommended", "full")
SCOPES: tuple[str, ...] = ("project", "workspace", "user")
GATEWAY_PROFILES: tuple[str, ...] = ("economy", "balanced", "deep")


def _spec() -> kit.ForgeSpec:
    return kit.ForgeSpec(
        forge_id=FORGE_ID,
        package="theforge",
        distribution=DIST_NAME,
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
    return render.render(
        ctx.hosts,
        skills="skill" in kinds,
        agents="agent" in kinds,
    )


def _ctx(
    scope: str,
    root: Path | None,
    hosts: tuple[str, ...],
    profile: str,
    dry_run: bool,
    cwd: Path | None = None,
    components: tuple[str, ...] | None = None,
    gateway_profile: str | None = None,
) -> kit.InstallContext:
    spec = _spec()
    base = Path(cwd or Path.cwd())
    target = kit.resolve_scope(spec, scope, base, root)
    options = kit.component_options(profile, components)
    if gateway_profile is not None:
        if gateway_profile not in GATEWAY_PROFILES:
            raise kit.InstallError(
                kit.E_PROFILE,
                f"gateway profile {gateway_profile!r}; {GATEWAY_PROFILES}",
            )
        options["execution_profile"] = gateway_profile
    return kit.InstallContext(
        spec=spec,
        scope=scope,
        root=target,
        state_dir=kit.state_dir_for(spec, scope, target),
        profile=profile,
        hosts=hosts,
        dry_run=dry_run,
        options=options,
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
    gateway_profile: str | None = None,
) -> dict[str, Any]:
    if profile not in PROFILES:
        raise kit.InstallError(kit.E_PROFILE, f"profile {profile!r}; {PROFILES}")
    ctx = _ctx(
        scope,
        root,
        _hosts(host),
        profile,
        dry_run,
        components=components,
        gateway_profile=gateway_profile,
    )
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
    source = manifest.get("source") or {}
    src = repo or (Path(p) if (p := source.get("path")) else None)
    if source.get("kind") == "pypi":
        # `--repo` trocaria a origem para checkout — e' um re-install, nao
        # um update. Recusar em vez de ignorar a flag silenciosamente.
        if repo is not None:
            return _receipt(
                "update",
                [
                    {
                        "id": "source",
                        "status": "FAIL",
                        "detail": (
                            "--repo nao se aplica a instalacao pypi; "
                            "para trocar de origem reinstale com forge_bootstrap.py --repo"
                        ),
                    }
                ],
                "failed",
            )
        # installacao via --dist: update e `pip install -U <spec>`, nao
        # re-install de checkout. `--to X` compoe `dist[extras]==X`
        # preservando os extras do spec registrado; sem ele cai no spec
        # (ou na distribution pura para -U latest real).
        dist_name = manifest.get("distribution")
        spec = source.get("spec") or ""
        spec_name, spec_extras = _split_spec_extras(spec)
        if spec and _canonical(spec_name) != _canonical(dist_name or ""):
            return _receipt(
                "update",
                [
                    {
                        "id": "source",
                        "status": "BLOCKED",
                        "detail": f"spec registrado {spec!r} diverge de {dist_name!r}",
                    }
                ],
                "failed",
            )
        if "***@" in spec:
            return _receipt(
                "update",
                [
                    {
                        "id": "source",
                        "status": "FAIL",
                        "detail": (
                            "spec redigido (credencial removida na persistencia); "
                            "reinstale via forge_bootstrap.py --dist --allow-url"
                        ),
                    }
                ],
                "failed",
            )
        if to and " @ " in spec:
            return _receipt(
                "update",
                [
                    {
                        "id": "source",
                        "status": "FAIL",
                        "detail": (
                            f"--to retargetaria a origem {spec!r} para PyPI; "
                            "reinstale via forge_bootstrap.py --dist --allow-url"
                        ),
                    }
                ],
                "failed",
            )
        target = f"{dist_name}{spec_extras}=={to}" if to and dist_name else (spec or dist_name)
        if not target or (to and not dist_name):
            return _receipt(
                "update",
                [{"id": "source", "status": "BLOCKED", "detail": "spec pypi ausente"}],
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
        cmd = [str(venv_py), "-m", "pip", "install", "--upgrade", str(target)]
        return _run_pip("update", cmd, dry_run=dry_run)
    if to is not None:
        # checkout re-instala do path registrado; um pin de versao exige
        # um spec pypi. Antes era ignorado em silencio — recusar nomeado.
        return _receipt(
            "update",
            [
                {
                    "id": "version",
                    "status": "FAIL",
                    "detail": (
                        "--to so se aplica a instalacoes pypi (--dist); checkout atualiza para HEAD"
                    ),
                }
            ],
            "failed",
        )
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
    return _run_pip("update", cmd, dry_run=dry_run)


def _split_spec_extras(spec: str) -> tuple[str, str]:
    """``name[e1]==v`` -> ("name", "[e1]"); extras preservados no pin de --to."""
    import re

    m = re.match(r"^\s*([A-Za-z0-9._-]+)(\[[^\]]*\])?", spec)
    if not m:
        return spec, ""
    return m.group(1), m.group(2) or ""


def _canonical(name: str) -> str:
    import re

    return re.sub(r"[-_.]+", "-", name.strip().lower())


def _run_pip(verb: str, cmd: list[str], *, dry_run: bool) -> dict[str, Any]:
    if not Path(cmd[0]).is_file():
        return _receipt(
            verb,
            [{"id": "venv", "status": "FAIL", "detail": f"venv python ausente: {cmd[0]}"}],
            "failed",
        )
    if dry_run:
        return _receipt(
            verb,
            [
                {
                    "id": "pip",
                    "status": "UNVERIFIED",
                    "detail": kit.redact_url_userinfo(" ".join(cmd)),
                }
            ],
            "planned",
        )
    import subprocess

    proc = subprocess.run(  # venv python + fixed pip args
        cmd, capture_output=True, text=True, timeout=900, check=False
    )
    checks = [
        {
            "id": "pip",
            "status": "PASS" if proc.returncode == 0 else "FAIL",
            "detail": kit.redact_url_userinfo((proc.stdout or proc.stderr)[-300:]),
        }
    ]
    return _receipt(verb, checks, "completed" if proc.returncode == 0 else "failed")


# --------------------------------------------------------------------------
# install auto + installations registry
# --------------------------------------------------------------------------


def _manifest() -> dict[str, Any]:
    doc = kit._load_json(kit.installations_dir() / f"{FORGE_ID}.json", None)
    return doc if isinstance(doc, dict) else {}


def installations() -> list[dict[str, Any]]:
    return kit.installed_forges()


def sync_provider_registry(
    *,
    root: Path | None = None,
    forge: str | None = None,
    yes: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Register installed local adapters and refresh live provider state."""
    return providers.sync(
        kit.installed_forges(),
        root=root,
        forge=forge,
        approved=yes,
        dry_run=dry_run,
    )


def _delegated_cmd(
    manifest: dict[str, Any],
    scope: str,
    target: Path,
    dry_run: bool,
    *,
    host: str = "all",
    profile: str = "recommended",
    components: tuple[str, ...] | None = None,
) -> list[str]:
    """Argv for delegating ``install`` to a sibling forge. Most forges
    expose ``<cli> install``; a manifest may instead carry
    ``install_command`` — an argv template where ``{python}`` resolves to
    the forge's registered venv interpreter and ``{checkout}`` to its
    registered source path (used by forges whose package boundary forbids
    the install engine, e.g. RC-locked CLIs that install via a script)."""
    tpl = manifest.get("install_command")
    if tpl:
        py = providers.manifest_python(manifest)
        checkout = str((manifest.get("source") or {}).get("path") or ".")
        replacements = {
            "python": py or sys.executable,
            "checkout": checkout,
            "home": checkout,
            "install_root": str(manifest.get("install_root") or ""),
        }
        argv = [
            a.replace("{python}", replacements["python"])
            .replace("{checkout}", replacements["checkout"])
            .replace("{home}", replacements["home"])
            .replace("{install_root}", replacements["install_root"])
            for a in tpl
        ]
    else:
        cli = providers.manifest_cli(manifest) or str(manifest.get("forge_id"))
        argv = [cli]
    command = argv + [
        "install",
        "--scope",
        scope,
        "--root",
        str(target),
    ]
    command.extend(["--host", host, "--profile", profile])
    if components is not None:
        command.extend(["--components", ",".join(components)])
    command.append("--dry-run" if dry_run else "--yes")
    return command


def install_auto(
    *,
    scope: str = "project",
    root: Path | None = None,
    yes: bool = False,
    dry_run: bool = False,
    forge: str | None = None,
    members: tuple[str, ...] = (),
    cwd: Path | None = None,
    host: str = "all",
    profile: str = "recommended",
    components: tuple[str, ...] | None = None,
    gateway_profile: str | None = None,
) -> dict[str, Any]:
    """Orquestra a familia: cada forge registrada no bootstrap instala a si
    mesma no alvo resolvido. Delega ao CLI real — nunca simula.
    ``forge`` restringe a delegação a uma única forge. No escopo
    ``workspace``, ``members`` seleciona subprojetos (paths relativos ao
    root) para delegação per-member adicional — o default e instalar os
    assets compartilhados no root da workspace sem tocar os membros."""
    if profile not in PROFILES:
        raise kit.InstallError(kit.E_PROFILE, f"profile {profile!r}; {PROFILES}")
    _hosts(host)  # validate once before any delegation
    kit.component_options(profile, components)  # validate even when self is absent
    if gateway_profile is not None and gateway_profile not in GATEWAY_PROFILES:
        raise kit.InstallError(
            kit.E_PROFILE,
            f"gateway profile {gateway_profile!r}; {GATEWAY_PROFILES}",
        )
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
                install(
                    scope=scope,
                    root=target,
                    host=host,
                    profile=profile,
                    components=components,
                    gateway_profile=gateway_profile,
                    yes=yes,
                    dry_run=dry_run,
                )
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
        cmd = _delegated_cmd(
            manifest,
            scope,
            target,
            dry_run,
            host=host,
            profile=profile,
            components=components,
        )
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
    registry_sync: dict[str, Any] | None = None
    if yes or dry_run:
        registry_sync = sync_provider_registry(
            root=target,
            forge=forge,
            yes=yes,
            dry_run=dry_run,
        )
        sync_status = registry_sync.get("status")
        sync_verification = (registry_sync.get("verification") or {}).get("status")
        checks.append(
            {
                "id": "provider-registry",
                "status": (
                    "PASS"
                    if sync_status == "completed" and sync_verification == "PASS"
                    else "UNVERIFIED"
                    if sync_status in ("completed", "planned")
                    else "FAIL"
                ),
                "detail": registry_sync.get("path") or registry_sync.get("detail"),
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
        "host": host,
        "profile": profile,
        "components": list(components) if components is not None else None,
        "execution_profile": gateway_profile,
        "checks": checks,
        "forges": results,
        "provider_registry": registry_sync,
        "managed_files": [],
        "verification": {
            "status": (
                "UNVERIFIED"
                if dry_run or any(c["status"] == "UNVERIFIED" for c in checks)
                else "PASS"
                if overall == "completed"
                else "FAIL"
            )
        },
        "status": overall,
        "created_at": kit._utc_now(),
        "created_by": f"theforge/{__version__}",
    }
    if scope == "workspace":
        receipt["workspace"] = _workspace_report(
            target,
            results,
            found,
            members=members,
            approved=yes,
            dry_run=dry_run,
            host=host,
            profile=profile,
            components=components,
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
    host: str = "all",
    profile: str = "recommended",
    components: tuple[str, ...] | None = None,
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
            cmd = _delegated_cmd(
                manifest,
                "project",
                member_dir,
                dry_run,
                host=host,
                profile=profile,
                components=components,
            )
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
    "sync_provider_registry",
    "repair",
    "status",
    "uninstall",
    "update",
]
