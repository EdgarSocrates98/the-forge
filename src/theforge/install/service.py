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
import re
import shutil
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from theforge.contracts.workspace_installation import VerificationState

from theforge import __version__
from theforge import _forgecontext as fctx
from theforge import _installkit as kit
from theforge.install import lifecycle, providers, render

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
        mcp_command=("theforge", "mcp", "serve"),
        mcp_server_name="theforge",
        mcp_verify_tool="theforge_status",
        version_cmd=("--version",),
        render_assets=_render_for,
        # Consumer docs (AGENTS.md/CLAUDE.md/AGENT_PROTOCOL.md) pertencem a
        # camada forge_context — blocos `forge:<forge-id>` + protocolo
        # consolidado, nao markers `the-forge:managed` (lf-0036).
        marker_files=(),
        marker_body="",
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
    exclude: tuple[str, ...] = (),
) -> kit.InstallContext:
    spec = _spec()
    base = Path(cwd or Path.cwd())
    target = kit.resolve_scope(spec, scope, base, root)
    # ``host=none`` is the explicit no-host-assets opt-out. Preserve the
    # historical default profile behavior by excluding MCP when no component
    # list was requested; an explicit ``components=("mcp",)`` remains an
    # intentional override for automation that wants only the shared config.
    effective_components = components
    if components is None and not hosts:
        effective_components = ("skills", "agents")
    options = kit.component_options(profile, effective_components)
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
        exclude=exclude,
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
    exclude: tuple[str, ...] = (),
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
        exclude=exclude,
    )
    if dry_run:
        plan_doc = kit.apply_install(ctx, approved=yes)
        plan_doc["lifecycle"] = lifecycle.receipt_block(plan_doc)
        return plan_doc
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
        _register_context(ctx, receipt)
        _drop_stale_doc_entries(ctx)
        # Derived AFTER the context layer — it may append checks or flip
        # the status to failed, and the lifecycle view must see the final
        # receipt, never the pre-context one.
        receipt["lifecycle"] = lifecycle.receipt_block(receipt)
        kit._write_receipt(ctx.state_dir, receipt)
    else:
        receipt["lifecycle"] = lifecycle.receipt_block(receipt)
    return receipt


# --------------------------------------------------------------------------
# forge-context/v1 wiring (install-2.0 cycle 2, ADR-0061)
# `.forge/context/` is the workspace-level capability registry — written at
# the install target, shared across forges, owned per forge_id.
# --------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[3]

_THEFORGE_DOMAINS: tuple[str, ...] = (
    "forge-ecosystem",
    "specialist-orchestration",
    "capability-negotiation",
    "economy-tracking",
)


def _context_manifest(ctx: kit.InstallContext) -> dict[str, Any]:
    """forge/context/v1 manifest for the-forge, built from real metadata:
    forge.json (when the checkout is present), the bundled skill/agent
    sources and the forge-knowledge catalog."""
    from theforge import agents as agents_mod
    from theforge import evals as evals_mod
    from theforge import knowledge as knowledge_mod

    forge_json = kit._load_json(Path(__file__).resolve().parents[1] / "forge.json", None)
    if not isinstance(forge_json, dict):
        forge_json = kit._load_json(_REPO_ROOT / "forge.json", None)
    forge_json = forge_json if isinstance(forge_json, dict) else None

    skills: list[str] = []
    skills_src = render._skills_src()
    if skills_src is not None:
        skills = sorted(d.name for d in skills_src.iterdir() if d.is_dir())
    agent_ids: list[str] = []
    try:
        agent_ids = sorted(agents_mod.load_all())
    except Exception:  # agent specs are optional outside a checkout
        agent_ids = []
    providers_: list[dict[str, Any]] = []
    try:
        providers_ = [
            {"id": pid, "interface": "native-runtime"} for pid in sorted(knowledge_mod.load_all())
        ]
    except Exception:
        providers_ = []

    checks: list[dict[str, Any]] = [
        {
            "id": "knowledge-catalog",
            "status": "PASS" if providers_ else "UNVERIFIED",
            "detail": f"{len(providers_)} knowledge packages",
        },
        {
            "id": "agent-specs",
            "status": "PASS" if agent_ids else "UNVERIFIED",
            "detail": f"{len(agent_ids)} agent specs",
        },
    ]
    return fctx.build_manifest(
        forge_id=FORGE_ID,
        name="The Forge",
        version=__version__,
        cli="theforge",
        package="theforge",
        distribution=DIST_NAME,
        python_spec=">=3.11",
        scope=ctx.scope,
        profile=ctx.profile,
        hosts=ctx.hosts,
        forge_json=forge_json,
        kind="orchestrator",
        domains=_THEFORGE_DOMAINS,
        skills=skills,
        agents=agent_ids,
        knowledge_providers=providers_,
        eval_suites=evals_mod.manifest_suites(),
        protocols=(
            {"id": "forge/v1", "version": "1"},
            {"id": "forge/context/v1", "version": "1"},
            {"id": "forge/context-registry/v1", "version": "1"},
            {"id": "theforge/KnowledgeInteroperability/v1", "version": "1"},
            {"id": "theforge/KnowledgeContextPack/v1", "version": "1"},
        ),
        discovery_commands=(
            {
                "id": "capabilities-list",
                "argv": ["theforge", "capabilities", "list", "--json"],
                "mode": "direct-capability",
                "read_only": True,
                "description": "capabilities.list (§6.2) — declared capability descriptors",
            },
            {
                "id": "protocol-describe",
                "argv": ["theforge", "providers", "health", "--json"],
                "mode": "diagnostic-only",
                "read_only": True,
                "description": (
                    "protocol.describe (§6.2) — observed provider protocol surfaces + fingerprints"
                ),
            },
            {
                "id": "knowledge-list",
                "argv": ["theforge", "knowledge", "list"],
                "mode": "direct-capability",
                "read_only": True,
                "description": (
                    "knowledge.search (§6.2) — bounded bootstrap knowledge "
                    "catalog (domain → providers → packages)"
                ),
            },
            {
                "id": "knowledge-get",
                "argv": ["theforge", "knowledge", "show", "{id}"],
                "mode": "direct-capability",
                "read_only": True,
                "description": "knowledge.get (§6.2) — one package by provider id",
            },
            {
                "id": "context-build",
                "argv": ["theforge", "workspace", "show", "--json"],
                "mode": "direct-capability",
                "read_only": True,
                "description": (
                    "context.build (§6.2) — bounded workspace context "
                    "description from cached manifests"
                ),
            },
            {
                "id": "agents-list",
                "argv": ["theforge", "agents", "list"],
                "mode": "direct-capability",
                "read_only": True,
                "description": "list registered agent specs and authorities",
            },
            {
                "id": "health-check",
                "argv": ["theforge", "doctor", "--json"],
                "mode": "diagnostic-only",
                "read_only": True,
                "description": "health.check (§6.2) — host, workspace and provider health",
            },
            {
                "id": "install-status",
                "argv": ["theforge", "install", "status"],
                "mode": "diagnostic-only",
                "read_only": True,
                "description": "install ledger drift + health of the target",
            },
            {
                "id": "evals-list",
                "argv": ["theforge", "evals", "list", "--json"],
                "mode": "direct-capability",
                "read_only": True,
                "description": (
                    "evals.list (§7.2) — classified catalog of declared eval "
                    "suites (metadata only, never holdout answers)"
                ),
            },
            {
                "id": "evals-describe",
                "argv": ["theforge", "evals", "describe", "{suite}", "--json"],
                "mode": "direct-capability",
                "read_only": True,
                "description": (
                    "evals.describe (§7.2) — one suite's kind, inputs, "
                    "environment and hash-pinned baselines/holdouts"
                ),
            },
            {
                "id": "evals-run",
                "argv": ["theforge", "evals", "run", "{suite}", "--json"],
                "mode": "specialist-workflow",
                "read_only": False,
                "description": (
                    "evals.run (§7.2) — execute a declared suite's allowlisted "
                    "argv and persist a receipt; missing inputs block, never skip"
                ),
            },
            {
                "id": "evals-result",
                "argv": ["theforge", "evals", "result", "{receipt}", "--json"],
                "mode": "direct-capability",
                "read_only": True,
                "description": "evals.result (§7.2) — read a persisted eval receipt",
            },
            {
                "id": "verify-plan",
                "argv": ["theforge", "verify", "plan", "--json"],
                "mode": "direct-capability",
                "read_only": True,
                "description": (
                    "verification.plan (§7.2/§7.4) — select applicable checks "
                    "and emit the validation plan; never executes"
                ),
            },
            {
                "id": "verify-run",
                "argv": ["theforge", "verify", "run", "--plan", "{plan}", "--json"],
                "mode": "specialist-workflow",
                "read_only": False,
                "description": (
                    "verification.run (§7.2/§7.4) — execute the plan's "
                    "authorized checks and record evidence"
                ),
            },
        ),
        discovery_ops={
            "capabilities.list": "capabilities-list",
            "protocol.describe": "protocol-describe",
            "knowledge.search": "knowledge-list",
            "knowledge.get": "knowledge-get",
            "context.build": "context-build",
            "health.check": "health-check",
            "evals.list": "evals-list",
            "evals.describe": "evals-describe",
            "evals.run": "evals-run",
            "evals.result": "evals-result",
            "verification.plan": "verify-plan",
            "verification.run": "verify-run",
            # rules.* — the-forge is the control plane and owns no domain
            # rule catalog; those ops stay unmapped (absent = honestly
            # unavailable, §6.6 — never invent a rules surface).
        },
        resources={
            "skills-bundle": {
                "kind": "bundled",
                "location": "theforge/host_assets/skills",
                "optional": False,
            },
            "agents-bundle": {
                "kind": "bundled",
                "location": "theforge/host_assets/agents",
                "optional": False,
            },
            "knowledge-bundle": {
                "kind": "bundled",
                "location": "theforge/forge_knowledge",
                "optional": True,
            },
            "install-ledger": {
                "kind": "referenced",
                "location": ".forge/install/install-ledger.json",
                "optional": True,
            },
        },
        mutating_verbs=(
            "install apply",
            "install uninstall",
            "install update",
            "install repair",
            "install auto",
            "provider install",
        ),
        requires_approval=(
            "install apply",
            "install uninstall",
            "install update",
            "provider install",
        ),
        offline_available=True,
        health={
            "status": "healthy" if providers_ and agent_ids else "degraded",
            "checks": checks,
        },
        components=ctx.options or None,
        recorded_by="theforge",
    )


# Legacy markers from previous installkit generations
# (`the-forge:managed:begin`); `install_docs` strips them while converging
# AGENTS.md/CLAUDE.md to the `forge:<tag>` contract (lf-0036).
_LEGACY_DOC_TAGS: tuple[str, ...] = ("the-forge:managed",)
_CONSUMER_DOCS: tuple[str, ...] = ("AGENTS.md", "CLAUDE.md", "AGENT_PROTOCOL.md")


def _drop_stale_doc_entries(ctx: kit.InstallContext) -> None:
    """Drop ledger entries for the consumer docs: they are owned by the
    forge_context docs layer now (managed `forge:*` blocks), not by a
    whole-file hash — user content outside the markers is not drift."""
    ledger = kit.Ledger.load(ctx.state_dir)
    changed = False
    for name in _CONSUMER_DOCS:
        if ledger.get(name) is not None:
            ledger.drop(name)
            changed = True
    if changed:
        ledger.save()


def _register_context(ctx: kit.InstallContext, receipt: dict[str, Any]) -> None:
    """Write `.forge/context/` — capability manifest + registry entry +
    ROUTING.md + the consumer docs — as ONE transaction (install-2.0
    §9.2: preflight → lock → plan → conflicts → backup → write → verify
    → commit, rollback on failure). A context failure is a named BLOCKED
    check on the receipt, never a silent skip.
    ``scope=user`` targets ``~``: ``~/.forge/`` is account-level state;
    workspace context is never written there — otherwise the registry at
    ``~`` would list this forge with no matching workspace semantics
    (sibling forges skip user scope the same way)."""
    if ctx.scope == "user":
        return
    try:
        manifest = _context_manifest(ctx)
        out = fctx.install_transaction(
            ctx.root, manifest, owner=FORGE_ID, legacy_tags=_LEGACY_DOC_TAGS
        )
        cap = ctx.root / ".forge" / "context" / "capabilities" / f"{FORGE_ID}.json"
        if cap.is_file():
            rel = cap.relative_to(ctx.root).as_posix()
            ledger = kit.Ledger.load(ctx.state_dir)
            ledger.record(
                rel,
                cap.read_bytes(),
                "state",
                "created" if ledger.get(rel) is None else "updated",
            )
            ledger.save()
        receipt.setdefault("checks", []).append(
            {
                "id": "context-registry",
                "status": "PASS",
                "detail": f".forge/context {out['status']} ({len(out['written'])} writes)",
            }
        )
        docs = out["docs"]
        receipt.setdefault("checks", []).append(
            {
                "id": "consumer-docs",
                "status": "PASS",
                "detail": (
                    f"{docs['status']}: {len(docs['written'])} written, {len(docs['kept'])} kept"
                ),
            }
        )
    except fctx.ContextError as exc:
        receipt.setdefault("checks", []).append(
            {"id": "context-registry", "status": "BLOCKED", "detail": f"{exc.kind}: {exc.detail}"}
        )
        # A BLOCKED check on a mandatory component must not exit 0 — the
        # assets landed but the install-2.0 contract (registry + docs)
        # failed, so the receipt reports it.
        receipt["status"] = "failed"


def _unregister_context(root: Path, receipt: dict[str, Any]) -> None:
    """Remove our own context manifest + registry entry + consumer-doc
    blocks on uninstall — ONE transaction (§9.2). Only owned artifacts:
    our capability file, our registry entry, our `forge:*` blocks."""
    try:
        out = fctx.uninstall_transaction(
            root, FORGE_ID, owner=FORGE_ID, legacy_tags=_LEGACY_DOC_TAGS
        )
        receipt.setdefault("checks", []).append(
            {
                "id": "context-registry",
                "status": "PASS",
                "detail": f".forge/context {out['status']}",
            }
        )
        docs = out["docs"]
        receipt.setdefault("checks", []).append(
            {
                "id": "consumer-docs",
                "status": "PASS",
                "detail": f"{docs['status']}: {len(docs['written'])} changed",
            }
        )
    except fctx.ContextError as exc:
        receipt.setdefault("checks", []).append(
            {"id": "context-registry", "status": "BLOCKED", "detail": f"{exc.kind}: {exc.detail}"}
        )
        receipt["status"] = "failed"


def _docs_leftovers(root: Path) -> bool:
    """True when the target still carries forge_context residue: a context
    dir, our managed block, the shared ecosystem block, the managed
    protocol sentinel, or a legacy marker. Reading is lock-free — only a
    hit justifies the write path."""
    if (root / fctx.CONTEXT_DIR).exists():
        return True
    needles = (
        f"forge:{FORGE_ID}:",
        f"{fctx.DOC_TAG_ECOSYSTEM}:",
        fctx.PROTOCOL_SENTINEL,
        *_LEGACY_DOC_TAGS,
    )
    for name in _CONSUMER_DOCS:
        path = root / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if any(n in text for n in needles):
            return True
    return False


def _context_registry_truth(root: Path | None) -> bool:
    """Whether `.forge/context/registry.json` lists this forge.

    install-2.0 moved consumer docs out of the install ledger into the
    context registry; an install that manages ONLY docs (minimal profile)
    leaves the kit ledger empty while being fully installed. The registry
    entry is the authoritative "installed here" signal in that case."""
    if root is None:
        return False
    reg = fctx.load_registry(Path(root).resolve())
    if not reg:
        return False
    return any(e.get("forge_id") == FORGE_ID for e in reg.get("forges", []))


def status(*, scope: str = "project", root: Path | None = None) -> dict[str, Any]:
    ctx = _ctx(scope, root, (), "recommended", True)
    doc = kit.status(ctx)
    if doc.get("status") == "unverified" and _context_registry_truth(ctx.root):
        # Empty ledger + registry entry = docs-only install — report the
        # truth instead of a false NOT_INSTALLED.
        doc["status"] = "healthy"
        doc["context_registered"] = True
    doc["lifecycle"] = lifecycle.health_block(doc)
    return doc


def doctor(*, scope: str = "project", root: Path | None = None) -> dict[str, Any]:
    ctx = _ctx(scope, root, (), "recommended", True)
    doc = kit.doctor(ctx)
    if doc.get("status") == "unverified" and _context_registry_truth(ctx.root):
        doc["status"] = "healthy"
        for c in doc.get("checks", []):
            if c.get("id") == "ledger":
                c["status"] = "NOT_APPLICABLE"
                c["detail"] = (
                    "0 managed entries — consumer docs owned by "
                    ".forge/context registry (docs-only install)"
                )
        doc.setdefault("checks", []).append(
            {
                "id": "context-registry",
                "status": "PASS",
                "detail": f"{FORGE_ID} present in .forge/context/registry.json",
            }
        )
    doc["lifecycle"] = lifecycle.health_block(doc)
    return doc


def repair(
    *, scope: str = "project", root: Path | None = None, dry_run: bool = False
) -> dict[str, Any]:
    ctx = _ctx(scope, root, render.HOSTS, "full", dry_run)
    if dry_run:
        doc = kit.status(ctx)
        doc["lifecycle"] = lifecycle.health_block(doc)
        return doc
    with kit.acquire_lock(ctx.state_dir) as lock:
        r = kit.repair(ctx)
        # Context registry (§9.2 recovery): redo a stranded transaction
        # journal, reclaim a stale context lock and rebuild registry +
        # ROUTING.md from the capability manifests on disk. Only when a
        # context dir already exists — repair never creates residue on a
        # workspace that never had one.
        if fctx.context_dir(ctx.root).exists():
            try:
                out_ctx = fctx.repair_context(ctx.root)
                r["repaired"].extend(f"context:{w}" for w in out_ctx["written"])
                rec = out_ctx.get("recovered")
                detail = (
                    f"{out_ctx['status']} ({len(out_ctx['written'])} writes)"
                    + (f"; recovered {rec['op']}:{rec['forge_id']}" if rec else "")
                    + ("; stale lock reclaimed" if out_ctx.get("lock_recovered") else "")
                )
                r.setdefault("checks", []).append(
                    {"id": "context-registry", "status": "PASS", "detail": detail}
                )
            except fctx.ContextError as exc:
                r["skipped"].append(f"context:{exc.kind}")
                r.setdefault("checks", []).append(
                    {
                        "id": "context-registry",
                        "status": "BLOCKED",
                        "detail": f"{exc.kind}: {exc.detail}",
                    }
                )
        # Consumer docs: re-assert `forge:*` blocks from the manifests under
        # `.forge/context/`; a named refusal lands as a BLOCKED check.
        try:
            out_docs = fctx.repair_docs(ctx.root, legacy_tags=_LEGACY_DOC_TAGS)
            r["repaired"].extend(f"docs:{w}" for w in out_docs["written"])
            r.setdefault("checks", []).append(
                {
                    "id": "consumer-docs",
                    "status": "PASS",
                    "detail": (f"{out_docs['status']} ({len(out_docs['written'])} writes)"),
                }
            )
        except fctx.ContextError as exc:
            r["skipped"].append(f"docs:{exc.kind}")
            r.setdefault("checks", []).append(
                {"id": "consumer-docs", "status": "BLOCKED", "detail": f"{exc.kind}: {exc.detail}"}
            )
        if lock.recovered:
            r.setdefault("checks", []).append(
                {
                    "id": "lock",
                    "status": "PASS",
                    "detail": "stale lock reclaimed (interrupted install recovered)",
                }
            )
        r["lifecycle"] = lifecycle.receipt_block(r)
        return r


def uninstall(
    *, scope: str = "project", root: Path | None = None, purge: bool = False, dry_run: bool = False
) -> dict[str, Any]:
    ctx = _ctx(scope, root, (), "recommended", dry_run)
    if not ctx.state_dir.exists() or dry_run:
        if not dry_run:
            # Nothing installed: idempotent no-op that writes no state —
            # unless context/doc leftovers remain (state dir gone but the
            # registry entry or `forge:*` blocks linger). Both ops are
            # lock-acquiring writers, so they only run when residue exists.
            r = _receipt(
                "uninstall",
                [{"id": "uninstall", "status": "PASS", "detail": "0 removed, 0 kept"}],
                "completed",
            ) | {"removed": [], "kept": [], "scope": scope, "target_root": str(ctx.root)}
            if _docs_leftovers(ctx.root):
                _unregister_context(ctx.root, r)
                r["lifecycle"] = lifecycle.receipt_block(r)
            return r
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
        # Só roda a camada de contexto quando há resíduo — num root sem
        # `.forge/context` o unregister criaria registry/ROUTING num
        # uninstall (scope=user incluso). O gate cobre registros legados
        # <=0.6.1 em `~`: a entrada existe exatamente quando há resíduo.
        if _docs_leftovers(ctx.root):
            _unregister_context(ctx.root, r)
            if not purge:
                # kit.uninstall persistiu o receipt antes do unregister —
                # regrava para que o arquivo reflita checks/status finais.
                r["lifecycle"] = lifecycle.receipt_block(r)
                kit._write_receipt(ctx.state_dir, r)
        r["lifecycle"] = lifecycle.receipt_block(r)
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
        if to and "@" in spec:
            # Qualquer referencia direta PEP 508 (`name @ <url>` — http,
            # https OU file:// wheelhouse): `--to` trocaria a origem para
            # PyPI em silencio. "@" so aparece em direct reference — sem
            # falso positivo em extras/markers.
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
    doc = providers.sync(
        kit.installed_forges(),
        root=root,
        forge=forge,
        approved=yes,
        dry_run=dry_run,
    )
    doc["lifecycle"] = lifecycle.receipt_block(doc)
    return doc


# Delegation argv — built ONLY from the manifest's declared install
# surface, never fabricated. ``install_command`` templates resolve the
# placeholder set below; anything else is an undeclared placeholder.
_DELEGATION_PLACEHOLDERS = ("python", "checkout", "home", "install_root")
_INSTALL_VERBS = frozenset({"install", "apply"})
_APPROVAL_FLAGS = frozenset({"--yes", "-y", "--dry-run"})
_CTRL_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_SHELL_META = re.compile(r"[;&|><`$]")


def _check_manifest_arg(raw: Any, fid: str) -> str:
    """One manifest-declared argv token — refuses unsafe/invalid content
    before it can reach exec."""
    if not isinstance(raw, str) or not raw:
        raise kit.InstallError(
            kit.E_UNSUPPORTED, f"{fid}: delegation argv entries must be non-empty strings"
        )
    if _CTRL_CHARS.search(raw):
        raise kit.InstallError(
            kit.E_UNSAFE, f"{fid}: delegation argv has control characters: {raw!r}"
        )
    if _SHELL_META.search(raw):
        raise kit.InstallError(kit.E_UNSAFE, f"{fid}: delegation argv has shell syntax: {raw!r}")
    return raw


def _resolve_install_template(manifest: dict[str, Any]) -> list[str]:
    """``install_command`` template → resolved argv prefix.

    ``{python}`` → the forge's registered venv interpreter (this process's
    interpreter when the venv is gone), ``{checkout}``/``{home}`` → the
    registered source path, ``{install_root}`` → the registered install
    root. Any other ``{name}`` is an undeclared placeholder — refused."""
    fid = str(manifest.get("forge_id") or "?")
    tpl = manifest.get("install_command")
    if not isinstance(tpl, list) or not tpl:
        raise kit.InstallError(
            kit.E_UNSUPPORTED, f"{fid}: install_command must be a non-empty argv list"
        )
    py = providers.manifest_python(manifest)
    checkout = str((manifest.get("source") or {}).get("path") or ".")
    replacements = {
        "python": py or sys.executable,
        "checkout": checkout,
        "home": checkout,
        "install_root": str(manifest.get("install_root") or ""),
    }
    argv: list[str] = []
    for raw in tpl:
        raw = _check_manifest_arg(raw, fid)
        arg = raw
        for name in _DELEGATION_PLACEHOLDERS:
            arg = arg.replace("{" + name + "}", replacements[name])
        if "{" in arg or "}" in arg:
            raise kit.InstallError(
                kit.E_UNSUPPORTED,
                f"{fid}: install_command has undeclared placeholder: {raw!r}",
            )
        argv.append(arg)
    # Bare argv[0] (e.g. ``["data-sentinel", "install", "--yes"]``) is a
    # logical name — resolve it through the registered launcher chain
    # (env var → cli.shim → cli.name), same as a plain ``cli`` delegation.
    if argv and not (Path(argv[0]).is_absolute() or os.sep in argv[0]):
        resolved = providers.manifest_cli(manifest)
        if resolved:
            argv[0] = resolved
    return argv


def _delegated_cmd(
    manifest: dict[str, Any],
    scope: str,
    target: Path,
    dry_run: bool,
    *,
    host: str = "all",
    profile: str = "recommended",
    components: tuple[str, ...] | None = None,
    gateway_profile: str | None = None,
) -> list[str]:
    """Argv for delegating ``install`` to a sibling forge — built from the
    manifest's DECLARED install surface, never fabricated:

    - ``install_command``: the forge's own installer entry (argv template).
      When the template already carries the install/apply verb — or bakes
      flags like ``--yes`` — the orchestrator never appends a duplicate.
    - ``cli``: the ``forge/* v1`` contract CLI — ``<cli> install`` accepts
      the standard flag family.
    - neither → ``E_UNSUPPORTED``: no honest argv exists.

    ``--scope``/``--root`` are the delegation request itself — always
    appended. ``--host``/``--profile``/``--components``/``--gateway-profile``
    and the approval flag are appended only when the template did not
    already declare them. When the manifest declares an ``install``
    surface (install-2.1) with a ``flags`` list, ONLY declared flags may
    be sent — a request flag the surface does not declare makes the
    request unhonorable (``E_UNSUPPORTED``; the caller marks the forge
    ``unsupported-capability`` rather than widening silently). Absent
    ``install`` keeps the v1 default: the standard flag family.
    Raises ``InstallError`` on invalid manifests — callers mark the forge,
    never exec a bad argv.
    """
    fid = str(manifest.get("forge_id") or "?")
    missing = _missing_capabilities(
        manifest,
        dry_run=dry_run,
        components=components,
        gateway_profile=gateway_profile,
    )
    if missing:
        raise kit.InstallError(
            kit.E_UNSUPPORTED,
            f"{fid}: declared install surface lacks {missing} — request cannot be honored as asked",
        )
    if manifest.get("install_command") is not None:
        argv = _resolve_install_template(manifest)
    else:
        cli = providers.manifest_cli(manifest)
        if not cli:
            raise kit.InstallError(
                kit.E_UNSUPPORTED,
                f"{fid}: manifest declares no cli/install_command — delegation unsupported",
            )
        argv = [_check_manifest_arg(cli, fid)]
    declared = set(argv)
    if not (declared & _INSTALL_VERBS):
        argv.append("install")
        declared.add("install")
    argv += ["--scope", scope, "--root", str(target)]
    if "--host" not in declared:
        argv += ["--host", host]
    if "--profile" not in declared:
        argv += ["--profile", profile]
    if components is not None and "--components" not in declared:
        argv += ["--components", ",".join(components)]
    if gateway_profile is not None and "--gateway-profile" not in declared:
        argv += ["--gateway-profile", gateway_profile]
    if dry_run:
        if "--dry-run" not in declared:
            argv.append("--dry-run")
    elif not (declared & _APPROVAL_FLAGS):
        argv.append(_declared_approval(manifest))
    for arg in argv:
        if not arg or _CTRL_CHARS.search(arg):
            raise kit.InstallError(
                kit.E_UNSAFE, f"{fid}: delegation argv failed validation: {arg!r}"
            )
    return argv


# Flags the orchestrator sends for an install request — the standard v1
# family. ``--scope``/``--root`` are the request itself and are always
# required; the rest are request capabilities a declared surface must list.
_REQUEST_FLAGS = (
    "--scope",
    "--root",
    "--host",
    "--profile",
    "--components",
    "--gateway-profile",
    "--yes",
    "--dry-run",
)


def _declared_surface(manifest: dict[str, Any]) -> dict[str, Any] | None:
    surf = manifest.get("install")
    return surf if isinstance(surf, dict) else None


def _declared_approval(manifest: dict[str, Any]) -> str:
    """The approval flag the forge's gate honors — declared ``install.
    approval`` wins, ``--yes`` is the v1 default."""
    surf = _declared_surface(manifest)
    if surf is not None:
        flag = surf.get("approval")
        if isinstance(flag, str) and flag.startswith("-"):
            return flag
    return "--yes"


def _missing_capabilities(
    manifest: dict[str, Any],
    *,
    dry_run: bool,
    components: tuple[str, ...] | None,
    gateway_profile: str | None,
) -> list[str]:
    """Request flags the manifest's declared ``install.flags`` does not
    list. Absent surface = v1 default family (nothing missing)."""
    surf = _declared_surface(manifest)
    if surf is None:
        return []
    flags = surf.get("flags")
    if not isinstance(flags, list):
        return []
    allowed = set(str(f) for f in flags)
    needed = ["--scope", "--root", "--host", "--profile"]
    if components is not None:
        needed.append("--components")
    if gateway_profile is not None:
        needed.append("--gateway-profile")
    # The approval flag is whatever the forge's gate honors — declared
    # ``install.approval`` (default --yes), or --dry-run for plan mode.
    needed.append("--dry-run" if dry_run else _declared_approval(manifest))
    return [f for f in needed if f not in allowed]


def _exe_resolvable(exe: str) -> bool:
    """``argv[0]`` must resolve before we exec — PATH names via
    ``shutil.which``, path-like entries must exist on disk."""
    if Path(exe).is_absolute() or os.sep in exe:
        return Path(exe).exists()
    return shutil.which(exe) is not None


def _valid_child_receipt(doc: Any, fid: str) -> bool:
    return (
        isinstance(doc, dict)
        and doc.get("schema") == kit.SCHEMA_RECEIPT
        and doc.get("forge_id") == fid
        and doc.get("operation") == "install"
    )


def _receipt_from_stdout(text: str, fid: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        doc = json.loads(text)
    except json.JSONDecodeError:
        doc = None
    if isinstance(doc, dict) and _valid_child_receipt(doc, fid):
        return doc
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            doc = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(doc, dict) and _valid_child_receipt(doc, fid):
            return doc
    return None


def _receipt_dirs(target: Path) -> list[Path]:
    """Candidate receipts dirs a child install may have written — the
    ``.<state>/receipts`` convention, including nested ``.<state>/install/``."""
    dirs: list[Path] = []
    try:
        hidden = sorted(p for p in target.glob(".*") if p.is_dir() and not p.is_symlink())
    except OSError:
        return dirs
    for d in hidden:
        for cand in (d / kit.RECEIPTS_DIR, d / "install" / kit.RECEIPTS_DIR):
            if cand.is_dir():
                dirs.append(cand)
    return dirs


def _child_install_receipt(
    fid: str, target: Path, stdout: str, since: float
) -> dict[str, Any] | None:
    """The delegated child's ``forge/InstallReceipt/v1`` — stdout JSON
    first, then the newest receipt file under ``<target>/.<state>/receipts``
    written after ``since``. A returncode of 0 without a receipt is NOT
    evidence of success."""
    doc = _receipt_from_stdout(stdout, fid)
    if doc is not None:
        return doc
    newest: tuple[float, dict[str, Any]] | None = None
    for rdir in _receipt_dirs(target):
        try:
            files = sorted(rdir.glob("*.json"))
        except OSError:
            continue
        for path in files:
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            if mtime < since - 1.0:
                continue
            doc = kit._load_json(path, None)
            if _valid_child_receipt(doc, fid) and (newest is None or mtime > newest[0]):
                newest = (mtime, doc)
    return newest[1] if newest else None


def _delegation_verdict(returncode: int, receipt: dict[str, Any] | None) -> tuple[str, str]:
    """(forge status, check status) — only a valid child receipt reporting
    ``completed`` + ``PASS`` counts as success; rc==0 alone is unverified."""
    if returncode != 0:
        return "failed", "FAIL"
    if receipt is None:
        return "unverified", "UNVERIFIED"
    status = str(receipt.get("status") or "")
    verification = str((receipt.get("verification") or {}).get("status") or "")
    if status == "completed" and verification == "PASS":
        return "completed", "PASS"
    if status in ("completed", "planned"):
        return "unverified", "UNVERIFIED"
    return "failed", "FAIL"


# --------------------------------------------------------------------------
# install-2.1 — the consolidated workspace plan
# (forge/WorkspaceInstallation/v2, ADR-0065)
#
# ``install auto`` plans EVERY registered forge before any write: the
# in-process kit.plan() for this forge, the child's own ``--dry-run``
# receipt for siblings. The consolidated doc orders the family (declared
# depends_on → topological; undeclared → stable default, honestly noted),
# classifies each forge's operation (closed vocabulary), detects
# cross-forge managed-path claims and records the per-forge ownership
# inventory. Apply honors the plan — the loser of a conflicting path is
# skipped, never last-writer-wins.
# --------------------------------------------------------------------------

_PLAN_TIMEOUT_S = 120

# Stable ordering base when depends_on is undeclared — the control plane
# lays down shared surfaces first, then services, then content forges.
_KIND_RANK = {"control-tool": 0, "service": 1, "content": 2}

# Managed-asset kinds whose path collisions are real conflicts. ``mcp``
# (managed keys inside .mcp.json) and ``marker`` (managed blocks inside
# user docs) are namespaced per forge — never path conflicts.
_CONFLICT_KINDS = frozenset({"skill", "agent", "knowledge", "rules", "evals", "config", "state"})

# Bare-string plan claims that are NOT whole-file conflicts: ``.mcp.json``
# holds per-forge managed keys and the marker docs hold per-forge managed
# blocks — both are namespaced inside the shared file by design.
_MANAGED_DOC_PATHS = frozenset({".mcp.json", "CLAUDE.md", "AGENTS.md", "AGENT_PROTOCOL.md"})


def _install_order(manifests: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """Install order over declared ``depends_on`` — deterministic Kahn on a
    (installation_kind, forge_id) base order. Undeclared dependencies and
    broken cycles become honest notes, never guesses."""
    notes: list[str] = []
    base = sorted(
        manifests,
        key=lambda m: (
            _KIND_RANK.get(str(m.get("installation_kind") or "content"), 2),
            str(m.get("forge_id") or ""),
        ),
    )
    by_id = {str(m.get("forge_id") or ""): m for m in base}
    position = {fid: i for i, fid in enumerate(by_id)}
    declared: dict[str, list[str]] = {}
    unknown: list[str] = []
    for fid, m in by_id.items():
        deps = m.get("depends_on")
        ds = [d for d in deps if isinstance(d, str)] if isinstance(deps, list) else []
        declared[fid] = [d for d in ds if d in by_id and d != fid]
        unknown.extend(d for d in ds if d not in by_id)
    if not any(declared.values()):
        notes.append(
            "no forge declares install dependencies — stable default order "
            "(control-tool → service → content, then forge_id)"
        )
    if unknown:
        notes.append(
            f"depends_on names unregistered forges {sorted(set(unknown))} — ignored for ordering"
        )
    remaining: dict[str, list[str]] = {fid: list(ds) for fid, ds in declared.items()}
    order: list[dict[str, Any]] = []
    while remaining:
        ready = sorted(
            (fid for fid, ds in remaining.items() if not ds),
            key=lambda f: position[f],
        )
        if not ready:
            fid = sorted(remaining, key=lambda f: position[f])[0]
            notes.append(
                f"dependency cycle broken at {fid} — depends_on must be "
                "fixed by the declaring forges; stable order resumed"
            )
            ready = [fid]
            remaining[fid] = []
        for fid in ready:
            order.append(by_id[fid])
            remaining.pop(fid, None)
            for ds in remaining.values():
                if fid in ds:
                    ds.remove(fid)
    return order, notes


def _collect_forge_plan(
    manifest: dict[str, Any],
    *,
    scope: str,
    target: Path,
    host: str,
    profile: str,
    components: tuple[str, ...] | None,
    gateway_profile: str | None,
) -> dict[str, Any]:
    """One forge's plan evidence for the consolidated workspace plan —
    ``kit.plan()`` in-process for this forge, the child's own ``--dry-run``
    InstallReceipt for siblings. When evidence cannot be obtained the entry
    says so (``unsupported``/``unavailable``) — paths are never fabricated."""
    fid = str(manifest.get("forge_id") or "?")
    entry: dict[str, Any] = {"forge_id": fid, "paths": {}}
    if fid == FORGE_ID:
        ctx = _ctx(
            scope,
            target,
            _hosts(host),
            profile,
            True,
            components=components,
            gateway_profile=gateway_profile,
        )
        entry["plan"] = kit.plan(ctx)
    else:
        try:
            cmd = _delegated_cmd(
                manifest,
                scope,
                target,
                True,
                host=host,
                profile=profile,
                components=components,
                gateway_profile=gateway_profile,
            )
        except kit.InstallError as exc:
            entry["unsupported"] = str(exc)
            return entry
        entry["cmd"] = cmd
        if not _exe_resolvable(cmd[0]):
            entry["unavailable"] = f"{cmd[0]} nao resolvido"
            return entry
        import subprocess

        try:
            proc = subprocess.run(  # plan delegation — the child's --dry-run
                cmd,
                capture_output=True,
                text=True,
                timeout=_PLAN_TIMEOUT_S,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            entry["unavailable"] = f"plan delegation failed: {exc}"
            return entry
        receipt = _receipt_from_stdout(proc.stdout or "", fid)
        if receipt is None:
            entry["unavailable"] = (
                "child --dry-run emitted no forge/InstallReceipt/v1 — plan evidence unavailable"
            )
            return entry
        entry["plan"] = receipt
    entry["paths"] = _plan_path_claims(entry["plan"])
    return entry


def _plan_path_claims(plan_doc: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Whole-file path claims from a child plan receipt — both receipt
    shapes: structured entries (dicts with ``kind``/``sha256``, claimed
    only for conflict kinds) and bare-string lists (claimed except
    managed-key/marker docs, which are namespaced inside shared files)."""
    doc = plan_doc or {}
    marker_docs = {
        m["file"]
        for m in doc.get("managed_markers") or []
        if isinstance(m, dict) and isinstance(m.get("file"), str)
    }
    non_conflicting = _MANAGED_DOC_PATHS | marker_docs
    paths: dict[str, dict[str, Any]] = {}
    for key in ("planned_files", "managed_files"):
        for f in doc.get(key) or []:
            if isinstance(f, str):
                if f not in non_conflicting:
                    paths.setdefault(f, {"sha256": None, "kind": "file"})
                continue
            if not isinstance(f, dict) or not isinstance(f.get("path"), str):
                continue
            if f.get("kind") not in _CONFLICT_KINDS or f.get("action") == "skipped":
                continue
            paths[f["path"]] = {"sha256": f.get("sha256"), "kind": f.get("kind")}
    return paths


def _path_conflicts(
    plans: dict[str, dict[str, Any]],
    order: list[str],
    target: Path,
) -> list[dict[str, Any]]:
    """Cross-forge managed-path claims — two forges planning the same
    whole-file asset is a conflict. Winner: the single claimant whose
    planned bytes already sit at the path (incumbent), else the first
    forge in install order. One row per (path, loser)."""
    claims: dict[str, list[str]] = {}
    for fid in order:
        for rel in plans.get(fid, {}).get("paths") or {}:
            claims.setdefault(rel, []).append(fid)
    out: list[dict[str, Any]] = []
    for rel in sorted(claims):
        claimants = claims[rel]
        if len(claimants) < 2:
            continue
        disk_sha = None
        path = target / rel
        if path.is_file():
            try:
                disk_sha = kit._sha_file(path)
            except OSError:
                disk_sha = None
        incumbents = (
            [f for f in claimants if plans[f]["paths"].get(rel, {}).get("sha256") == disk_sha]
            if disk_sha
            else []
        )
        winner = incumbents[0] if len(incumbents) == 1 else claimants[0]
        detail = (
            "incumbent wins — planned bytes already at the path"
            if len(incumbents) == 1
            else "first in install order wins"
        )
        if disk_sha is None:
            detail += "; path absent on disk"
        elif not incumbents:
            detail += (
                "; path exists with foreign content — the engine's "
                "foreign-file rule still applies at apply time"
            )
        for loser in (f for f in claimants if f != winner):
            out.append(
                {
                    "path": rel,
                    "claimants": list(claimants),
                    "winner": winner,
                    "loser": loser,
                    "resolution": None,
                    "detail": detail,
                }
            )
    return out


def _classify_forge(
    manifest: dict[str, Any],
    entry: dict[str, Any] | None,
    result_status: str | None,
    lost: list[str],
    target: Path,
) -> tuple[str | None, str]:  # (PlanClassification | None, detail)
    """Closed plan vocabulary — ``new|updated|reused|preserved|conflict|
    unsupported-capability``. ``None`` = honestly unclassified (no plan
    evidence); the detail always says why."""
    fid = str(manifest.get("forge_id") or "?")
    if lost:
        return "conflict", f"loses {len(lost)} managed path(s) to other forge(s): {lost}"
    entry = entry or {}
    if entry.get("unsupported"):
        return "unsupported-capability", str(entry["unsupported"])
    if result_status == "refused" or result_status is None:
        return "preserved", "not delegated in this run — existing install untouched"
    paths = entry.get("paths") or {}
    if not paths:
        detail = entry.get("unavailable")
        if detail:
            return None, str(detail)
        return "reused", "no managed paths planned — nothing to change"
    # Kind-aware diff: a planned path missing on disk is a create; matching
    # sha is reuse; a differing sha is an update.
    states = {"create": 0, "reused": 0, "updated": 0}
    for rel, info in paths.items():
        p = target / rel
        if not p.is_file():
            states["create"] += 1
            continue
        try:
            same = kit._sha_file(p) == info.get("sha256")
        except OSError:
            same = False
        states["reused" if same else "updated"] += 1
    if states["updated"]:
        return "updated", f"{states['updated']} managed path(s) would change"
    if states["reused"]:
        return "reused", f"{states['reused']} path(s) already converge"
    # every path absent: fresh for this target — unless install evidence
    # (mcp key or managed marker block) says the forge already manages it.
    if _member_state(target, fid):
        return "reused", "install evidence at target; managed paths not in plan"
    return "new", f"{states['create']} managed path(s) to create"


def _member_state(member: Path, fid: str) -> str | None:
    """Precedence evidence at a project root — the forge's own ``.mcp.json``
    key or ``<fid>:managed`` marker block means a project-scope install
    already owns the target."""
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


def _result_verification(status: str | None) -> VerificationState:
    """Apply-status → verification state for the consolidated doc — the
    closed ``forge/*`` check vocabulary, never a guess."""
    table: dict[str, VerificationState] = {
        "completed": "PASS",
        "planned": "UNVERIFIED",
        "refused": "UNVERIFIED",
        "unverified": "UNVERIFIED",
        "blocked": "BLOCKED",
        "unsupported": "BLOCKED",
        "failed": "FAIL",
    }
    return table.get(status or "", "UNVERIFIED")


def _owned_files(receipt: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Managed-file entries the receipt proves the forge owns — never
    entries the engine flagged user-owned/skipped/adopted."""
    out: list[dict[str, Any]] = []
    for f in (receipt or {}).get("managed_files", []):
        if not isinstance(f, dict) or not isinstance(f.get("path"), str):
            continue
        note = str(f.get("note") or "")
        if f.get("action") in ("skipped",) or "user-owned" in note or "skipped" in note:
            continue
        out.append(f)
    return out


def _surface_doc(manifest: dict[str, Any]) -> dict[str, Any]:
    surf = _declared_surface(manifest) or {}
    return {
        "operations": [str(o) for o in surf.get("operations") or []],
        "flags": [str(f) for f in surf.get("flags") or []],
        "hosts": [str(h) for h in surf.get("hosts") or []],
        "scopes": [str(s) for s in surf.get("scopes") or []],
        "profiles": [str(p) for p in surf.get("profiles") or []],
        "approval": str(surf.get("approval") or "--yes"),
    }


def _security_doc(manifest: dict[str, Any]) -> dict[str, Any]:
    sec = manifest.get("security")
    if not isinstance(sec, dict):
        sec = (_declared_surface(manifest) or {}).get("security")
    sec = sec if isinstance(sec, dict) else {}
    return {
        "requires_network": sec.get("requires_network"),
        "requires_credentials": sec.get("requires_credentials"),
        "spawn_allowed": sec.get("spawn_allowed"),
        "notes": sec.get("notes"),
    }


def _resource_kind(file_kind: str | None) -> str:
    return {
        "mcp": "managed-key",
        "marker": "managed-block",
    }.get(str(file_kind or ""), "managed-file")


def _installation_doc(
    *,
    scope: str,
    target: Path,
    ordered: list[dict[str, Any]],
    plans: dict[str, dict[str, Any]],
    results: list[dict[str, Any]],
    receipts: dict[str, dict[str, Any]],
    conflicts: list[dict[str, Any]],
    order_notes: list[str],
    members: list[str],
) -> dict[str, Any]:
    """The consolidated ``forge/WorkspaceInstallation/v2`` document —
    plan view, apply record and ownership inventory in one shape."""
    from typing import cast

    from theforge.contracts.base import to_dict
    from theforge.contracts.workspace_installation import (
        INSTALLATION_KINDS,
        OWNERSHIP_POLICIES,
        OWNERSHIP_SOURCES,
        PLAN_CLASSIFICATIONS,
        ForgeInstallation,
        InstallationKind,
        InstallResource,
        InstallSecurity,
        InstallSurface,
        OwnershipPolicy,
        OwnershipSource,
        PathConflict,
        PlanClassification,
        WorkspaceInstallation,
    )

    result_by_fid = {str(r.get("forge_id")): r for r in results}
    lost_by_fid: dict[str, list[str]] = {}
    for c in conflicts:
        lost_by_fid.setdefault(str(c["loser"]), []).append(str(c["path"]))

    forges: list[ForgeInstallation] = []
    for manifest in ordered:
        fid = str(manifest.get("forge_id") or "?")
        entry = plans.get(fid) or {}
        row = result_by_fid.get(fid) or {}
        status = row.get("status")
        cls, detail = _classify_forge(manifest, entry, status, lost_by_fid.get(fid, []), target)
        # Ownership evidence: the applied InstallReceipt proves managed
        # paths (``managed_files``); in plan-only mode the planned paths
        # are what WOULD be owned — provenance recorded, never invented.
        receipt = receipts.get(fid)
        owned_files = _owned_files(receipt)
        ownership_source = "receipt" if owned_files else None
        if not owned_files:
            plan = entry.get("plan")
            if isinstance(plan, dict):
                owned_files = [
                    f
                    for f in plan.get("planned_files", [])
                    if isinstance(f, dict)
                    and isinstance(f.get("path"), str)
                    and f.get("action") != "skipped"
                    and f.get("path") not in set(lost_by_fid.get(fid, []))
                ]
                if owned_files:
                    ownership_source = "plan"
        excluded = set(lost_by_fid.get(fid, []))
        owned = sorted(f["path"] for f in owned_files if f.get("path") not in excluded)
        surf_raw = manifest.get("install")
        surf = surf_raw if isinstance(surf_raw, dict) else {}
        raw_policy = surf.get("update_policy")
        policy: OwnershipPolicy = (
            cast(OwnershipPolicy, raw_policy)
            if isinstance(raw_policy, str) and raw_policy in OWNERSHIP_POLICIES
            else "forge-owned"
        )
        raw_kind = str(manifest.get("installation_kind") or "content")
        kind = cast(InstallationKind, raw_kind if raw_kind in INSTALLATION_KINDS else "content")
        src = (
            cast(OwnershipSource, ownership_source)
            if ownership_source in OWNERSHIP_SOURCES
            else None
        )
        cls_t = cast(PlanClassification, cls) if cls in PLAN_CLASSIFICATIONS else None
        resources = [
            InstallResource(
                id=f"{fid}:{f['path']}",
                kind=_resource_kind(f.get("kind")),
                location=str(f["path"]),
                sha256=(f.get("sha256") if isinstance(f.get("sha256"), str) else None),
                owner=fid,
                policy=policy,
            )
            for f in owned_files
            if f.get("path") not in excluded
        ]
        forges.append(
            ForgeInstallation(
                forge_id=fid,
                installation_kind=kind,
                version=(
                    manifest.get("version") if isinstance(manifest.get("version"), str) else None
                ),
                cli=providers.manifest_cli(manifest),
                install_command=[str(a) for a in (manifest.get("install_command") or [])],
                depends_on=[
                    str(d) for d in (manifest.get("depends_on") or []) if isinstance(d, str)
                ],
                surface=InstallSurface(**_surface_doc(manifest)),
                resources=resources,
                owned_paths=owned,
                ownership=policy,
                ownership_source=src,
                security=InstallSecurity(**_security_doc(manifest)),
                verification=_result_verification(status),
                classification=cls_t,
                classification_detail=detail,
            )
        )
    ver_states = [f.verification for f in forges]
    aggregate: VerificationState = (
        "FAIL"
        if any(v == "FAIL" for v in ver_states)
        else "PASS"
        if ver_states and all(v in ("PASS", "NOT_APPLICABLE") for v in ver_states)
        else "UNVERIFIED"
    )
    notes = list(order_notes)
    doc = WorkspaceInstallation(
        workspace_root=str(target),
        created_at=kit._utc_now(),
        updated_at=kit._utc_now(),
        scope=scope,
        order=[f.forge_id for f in forges],
        order_note="; ".join(order_notes) if order_notes else None,
        forges=forges,
        conflicts=[
            PathConflict(
                path=str(c["path"]),
                claimants=[str(x) for x in c["claimants"]],
                winner=str(c["winner"]),
                loser=str(c["loser"]),
                resolution=c.get("resolution"),
                detail=str(c.get("detail") or ""),
            )
            for c in conflicts
        ],
        members=members,
        notes=notes,
        verification=aggregate,
    )
    return to_dict(doc)


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
        blocked_receipt: dict[str, Any] = {
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
        blocked_receipt["lifecycle"] = lifecycle.receipt_block(blocked_receipt)
        return blocked_receipt
    # ------------------------------------------------------------------
    # Phase 1 — consolidated plan (install-2.1): every forge is planned
    # BEFORE any write. Sibling plans come from the child's own
    # ``--dry-run`` receipt; this forge plans in-process. Without the
    # approval gate no delegation happens at all — no plan collection,
    # no writes (the plan itself is part of the gated surface).
    # ------------------------------------------------------------------
    approved = bool(yes or dry_run)
    ordered, order_notes = _install_order(found)
    order_ids = [str(m.get("forge_id") or "?") for m in ordered]
    plans: dict[str, dict[str, Any]] = {}
    if approved:
        for manifest in ordered:
            fid = str(manifest.get("forge_id") or "?")
            plans[fid] = _collect_forge_plan(
                manifest,
                scope=scope,
                target=target,
                host=host,
                profile=profile,
                components=components,
                gateway_profile=gateway_profile,
            )
    conflicts = _path_conflicts(plans, order_ids, target)
    exclusions: dict[str, list[str]] = {}
    for c in conflicts:
        exclusions.setdefault(str(c["loser"]), []).append(str(c["path"]))

    # ------------------------------------------------------------------
    # Phase 2 — apply in install order, honoring the consolidated plan.
    # ------------------------------------------------------------------
    receipts: dict[str, dict[str, Any]] = {}
    for manifest in ordered:
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
                    exclude=tuple(sorted(exclusions.get(fid, []))),
                )
                if approved
                else {"status": "refused", "detail": "sem --yes"}
            )
            if isinstance(out, dict) and out.get("schema") == kit.SCHEMA_RECEIPT:
                receipts[fid] = out
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
        if not approved:
            results.append({"forge_id": fid, "status": "refused", "detail": "sem --yes"})
            checks.append(
                {"id": f"forge:{fid}", "status": "BLOCKED", "detail": "approval gate — sem --yes"}
            )
            continue
        unsupported = (plans.get(fid) or {}).get("unsupported")
        if unsupported:
            results.append({"forge_id": fid, "status": "unsupported", "detail": unsupported})
            checks.append({"id": f"forge:{fid}", "status": "BLOCKED", "detail": unsupported})
            continue
        try:
            cmd = _delegated_cmd(
                manifest,
                scope,
                target,
                dry_run,
                host=host,
                profile=profile,
                components=components,
                gateway_profile=gateway_profile,
            )
        except kit.InstallError as exc:
            results.append({"forge_id": fid, "status": "unsupported", "detail": str(exc)})
            checks.append({"id": f"forge:{fid}", "status": "BLOCKED", "detail": str(exc)})
            continue
        exe = cmd[0]
        if not _exe_resolvable(exe):
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

        started = time.time()
        proc = subprocess.run(  # delegation to the forge's own governed CLI
            cmd, capture_output=True, text=True, timeout=600, check=False
        )
        child_rcpt = _child_install_receipt(fid, target, proc.stdout, started)
        if child_rcpt is not None:
            receipts[fid] = child_rcpt
        verdict, check_status = _delegation_verdict(proc.returncode, child_rcpt)
        row: dict[str, Any] = {
            "forge_id": fid,
            "status": verdict,
            "returncode": proc.returncode,
        }
        if child_rcpt and child_rcpt.get("receipt_id"):
            row["receipt_id"] = child_rcpt["receipt_id"]
        results.append(row)
        checks.append(
            {
                "id": f"forge:{fid}",
                "status": check_status,
                "detail": (proc.stdout or proc.stderr)[-200:],
            }
        )

    # ------------------------------------------------------------------
    # Phase 3 — resolve conflicts from observed evidence (apply mode).
    # The loser's own engine skips foreign-owned paths too, but the
    # resolution is recorded from the receipt, never assumed.
    # ------------------------------------------------------------------
    for c in conflicts:
        loser_rcpt = receipts.get(str(c["loser"]))
        if dry_run:
            c["resolution"] = None
            continue
        entry_kind = next(
            (
                f
                for f in (loser_rcpt or {}).get("managed_files", [])
                if isinstance(f, dict) and f.get("path") == c["path"]
            ),
            None,
        )
        if entry_kind is None:
            c["resolution"] = (
                "skipped" if loser_rcpt is not None else "unverified — no loser receipt"
            )
        elif entry_kind.get("action") in ("created", "updated"):
            c["resolution"] = "overwritten — loser wrote anyway (plan violation)"
            checks.append(
                {
                    "id": "cross-forge-conflicts",
                    "status": "FAIL",
                    "detail": (
                        f"{c['loser']} overwrote {c['path']} claimed by "
                        f"{c['winner']} — last-writer-wins is forbidden"
                    ),
                }
            )
        else:
            c["resolution"] = "skipped"

    if conflicts:
        checks.append(
            {
                "id": "consolidated-plan",
                "status": "PASS" if not dry_run else "UNVERIFIED",
                "detail": (
                    f"{len(conflicts)} cross-forge path conflict(s): "
                    + "; ".join(f"{c['path']} {c['loser']}!={c['winner']}" for c in conflicts)
                ),
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
    member_entries: list[str] = []
    installation = _installation_doc(
        scope=scope,
        target=target,
        ordered=ordered,
        plans=plans,
        results=results,
        receipts=receipts,
        conflicts=conflicts,
        order_notes=order_notes,
        members=[],  # filled below once workspace discovery ran
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
        "installation": installation,
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
    receipt["lifecycle"] = lifecycle.receipt_block(receipt)
    if scope == "workspace":
        receipt["workspace"] = _workspace_report(
            target,
            results,
            ordered,
            members=members,
            approved=yes,
            dry_run=dry_run,
            host=host,
            profile=profile,
            components=components,
            gateway_profile=gateway_profile,
            installation=installation,
        )
        member_entries = [str(m.get("path")) for m in receipt["workspace"].get("members", [])]
        if member_entries:
            installation["members"] = member_entries
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
    gateway_profile: str | None = None,
    installation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Member discovery + precedence + the ``forge/WorkspaceInstall/v1``
    manifest for ``install auto --scope workspace``.

    Members = independent project roots under the root — ``.git`` or a
    project manifest marker, never assumed to be a monorepo. A member
    already project-installed for a
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
            if not (approved or dry_run):
                member_results.append(
                    {"member": rel, "forge_id": fid, "status": "refused", "detail": "approval gate"}
                )
                continue
            try:
                cmd = _delegated_cmd(
                    manifest,
                    "project",
                    member_dir,
                    dry_run,
                    host=host,
                    profile=profile,
                    components=components,
                    gateway_profile=gateway_profile,
                )
            except kit.InstallError as exc:
                member_results.append(
                    {
                        "member": rel,
                        "forge_id": fid,
                        "status": "unsupported",
                        "detail": str(exc),
                    }
                )
                continue
            if not _exe_resolvable(cmd[0]):
                member_results.append(
                    {
                        "member": rel,
                        "forge_id": fid,
                        "status": "blocked",
                        "detail": f"{cmd[0]} nao resolvido",
                    }
                )
                continue
            if dry_run:
                member_results.append(
                    {"member": rel, "forge_id": fid, "status": "planned", "detail": " ".join(cmd)}
                )
                continue
            import subprocess

            started = time.time()
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=False)
            receipt = _child_install_receipt(fid, member_dir, proc.stdout, started)
            verdict, _check_status = _delegation_verdict(proc.returncode, receipt)
            member_results.append(
                {
                    "member": rel,
                    "forge_id": fid,
                    "status": verdict,
                    "receipt_id": (receipt or {}).get("receipt_id") or f"{rel}/{fid}",
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
    if installation is not None:
        # The consolidated cross-forge ownership inventory (install-2.1,
        # forge/WorkspaceInstallation/v2) — persisted under the v1
        # manifest's ``installation`` block, extended not replaced.
        manifest["installation"] = installation
    state = ws_root / ".forge"
    if not dry_run and (done or projects or conflicts):
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
    doc = {
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
    doc["lifecycle"] = lifecycle.receipt_block(doc)
    return doc


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
