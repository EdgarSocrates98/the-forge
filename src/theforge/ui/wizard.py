"""Guided installation wizard (Experience Program §1.2).

Drives the *real* install service — every choice maps to an actual
``install()`` call; the review step is the real dry-run plan, and the
apply step is the governed ``--yes`` path. Nothing here writes files
itself.

Flow: env check → scope → profile → hosts → review (dry-run plan) →
confirm → apply → doctor → finish. Any step can be cancelled (Esc/q)
without side effects; nothing is written before the explicit confirm.
"""

from __future__ import annotations

import importlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from theforge.ui import i18n
from theforge.ui.kit import (
    NonInteractive,
    UIContext,
    _c,
    confirm,
    dashboard,
    multi_select,
    select,
)

_ALL_HOSTS = ("claude", "devin", "codex", "copilot")
_PROFILES = ("recommended", "minimal", "full")  # service contract names
_PROFILE_LABELS = {
    "recommended": "Balanced (Recommended)",
    "minimal": "Economy",
    "full": "Full",
}
_GATEWAY_PROFILES = ("economy", "balanced", "deep")
_GATEWAY_LABELS = {
    "economy": "Economy (lowest context cost)",
    "balanced": "Balanced (recommended)",
    "deep": "Deep (maximum verification)",
}
_SCOPE_LABELS = {
    "project": "Current repository",
    "workspace": "Entire workspace",
    "user": "My user account",
}


def _has_vcs_root(start: Path) -> bool:
    """Return whether current directory belongs to a supported project root."""
    return any(
        (candidate / ".git").exists()
        or ((candidate / "forge.json").is_file() and (candidate / "pyproject.toml").is_file())
        for candidate in (start, *start.parents)
    )


def _scope_choices(ctx: UIContext) -> list[str]:
    """Hide repository-only choice when operator is in a fresh directory."""
    scopes = ["project", "workspace", "user"]
    if not _has_vcs_root(Path.cwd()):
        print(
            _c(
                ctx,
                "33",
                "  No repository detected; choose Entire workspace to use this directory "
                "or My user account.",
            )
        )
        scopes.remove("project")
    return scopes


def env_check_rows() -> list[tuple[str, str]]:
    """Real environment evidence: python, git, host binaries."""
    v = sys.version_info
    rows = [("Python", f"{v.major}.{v.minor}.{v.micro}")]
    rows.append(("Git", "OK" if shutil.which("git") else "missing"))
    for h in _ALL_HOSTS:
        rows.append((h.capitalize(), "Available" if shutil.which(h) else "not detected"))
    return rows


def _banner(ctx: UIContext, forge_name: str) -> None:
    print()
    print(_c(ctx, "1", f" {forge_name.upper()}"))
    print(_c(ctx, "2", " " + ("─" if ctx.unicode else "-") * max(10, len(forge_name) + 4)))
    print(f"  {i18n.t('env_detected', ctx.language)}:")


def run_wizard(
    *,
    forge_name: str,
    install_fn: Any,
    doctor_fn: Any | None = None,
    hosts_available: tuple[str, ...] = _ALL_HOSTS,
    ctx: UIContext | None = None,
    out_json: bool = False,
    family: bool = False,
    defaults: dict[str, Any] | None = None,
) -> int:
    """Interactive install wizard. Returns exit code.

    ``install_fn(**kwargs)`` is the forge's real install service
    (``host``/``scope``/``profile``/``yes``/``dry_run`` kwargs).
    ``doctor_fn`` optionally verifies post-install.

    ``defaults`` optionally carries resolved values + provenance
    (``{"field": {"value": ..., "source": ...}}``); each select/multi-select
    pre-checks the resolved choice and the review shows its source
    (``CLI|preset:<name>|workspace|detected|default``). Operator answers
    always win — a default is only the initial focus/checked state.
    """
    ctx = ctx or UIContext.detect()
    if not ctx.interactive:
        raise NonInteractive("install wizard requires a TTY")
    defaults = defaults or {}

    def _resolved(key: str) -> tuple[Any, str | None]:
        entry = defaults.get(key)
        if not isinstance(entry, dict):
            return None, None
        return entry.get("value"), entry.get("source")

    def _prov(key: str) -> str:
        src = _resolved(key)[1]
        return f" ({src})" if src else ""

    _banner(ctx, forge_name)
    env_rows = env_check_rows()
    for label, val in env_rows:
        print(f"    {label:<14} {_c(ctx, '32' if val in ('OK', 'Available') else '2', val)}")
    print()
    if family:
        print(_c(ctx, "36", "  family mode: The Forge + registered specialist forges"))
        print(_c(ctx, "2", "  one real plan, one approval, each forge keeps its own installer"))
        print()

    # --- scope ---------------------------------------------------------------
    scopes = _scope_choices(ctx)
    scope_val, _ = _resolved("scope")
    idx = select(
        i18n.t("install_scope_q", ctx.language),
        [_SCOPE_LABELS[s] for s in scopes],
        ctx=ctx,
        default=scopes.index(scope_val) if scope_val in scopes else 0,
    )
    if idx is None:
        return 130
    scope = scopes[idx]

    # --- profile -------------------------------------------------------------
    profile_val, _ = _resolved("profile")
    idx = select(
        i18n.t("install_profile_q", ctx.language),
        [_PROFILE_LABELS[p] for p in _PROFILES],
        ctx=ctx,
        default=_PROFILES.index(profile_val) if profile_val in _PROFILES else 0,
    )
    if idx is None:
        return 130
    profile = _PROFILES[idx]

    # --- execution profile --------------------------------------------------
    gateway_val, _ = _resolved("gateway_profile")
    idx = select(
        i18n.t("install_gateway_profile_q", ctx.language),
        [_GATEWAY_LABELS[p] for p in _GATEWAY_PROFILES],
        ctx=ctx,
        default=_GATEWAY_PROFILES.index(gateway_val)
        if gateway_val in _GATEWAY_PROFILES
        else _GATEWAY_PROFILES.index("balanced"),
    )
    if idx is None:
        return 130
    gateway_profile = _GATEWAY_PROFILES[idx]

    # --- optional components ---------------------------------------------------
    # The profile decides the default; the operator can narrow or extend it.
    # "graph-studio"/"tui" are runtime flags persisted to components.json —
    # skills/agents/mcp map to real asset kinds.
    _COMP_LABELS = {
        "skills": "Skills",
        "agents": "Agents",
        "mcp": "MCP",
        "tui": "TUI",
        "graph-studio": "Graph Studio",
    }
    _COMP_ORDER = ("skills", "agents", "mcp", "tui", "graph-studio")
    _COMP_DETAILS = {
        "skills": "host-discoverable skills and progressive capability guidance",
        "agents": "specialists, subagents and declared agent instructions",
        "mcp": "MCP configuration and governed server entry points",
        "tui": "the terminal command center runtime",
        "graph-studio": "federated graph views and local graph navigation",
    }
    _profile_defaults = {
        "minimal": {"mcp", "tui"},
        "recommended": {"skills", "agents", "mcp", "tui", "graph-studio"},
        "full": {"skills", "agents", "mcp", "tui", "graph-studio"},
    }
    comp_checked = _profile_defaults.get(profile, set())
    comp_val, _ = _resolved("components")
    if comp_val is not None:
        comp_checked = set(comp_val)
    print(_c(ctx, "2", "  component choices (economy loads optional knowledge/evals on demand):"))
    for component in _COMP_ORDER:
        print(f"    {component:<13} {_COMP_DETAILS[component]}")
    comp_chosen = multi_select(
        i18n.t("install_components_q", ctx.language),
        [_COMP_LABELS[c] for c in _COMP_ORDER],
        checked={i for i, c in enumerate(_COMP_ORDER) if c in comp_checked},
        ctx=ctx,
    )
    if comp_chosen is None:
        return 130
    components = tuple(sorted(_COMP_ORDER[i] for i in comp_chosen))

    # --- hosts ---------------------------------------------------------------
    host_val, _ = _resolved("hosts")
    if host_val is None:
        # No declared/resolved preference → pre-check detected binaries.
        checked_hosts = {
            i
            for i, h in enumerate(hosts_available)
            if any(h in r[0].lower() and r[1] == "Available" for r in env_rows)
        }
    elif host_val == "all":
        checked_hosts = set(range(len(hosts_available)))
    elif host_val in ("none", ""):
        checked_hosts = set()
    else:
        wanted_hosts = {h.strip() for h in str(host_val).split(",") if h.strip()}
        checked_hosts = {i for i, h in enumerate(hosts_available) if h in wanted_hosts}
    chosen = multi_select(
        i18n.t("install_hosts_q", ctx.language),
        list(hosts_available),
        checked=checked_hosts,
        ctx=ctx,
    )
    if chosen is None:
        return 130
    if not chosen:
        host_arg: str | None = None
    elif len(chosen) == len(hosts_available):
        host_arg = "all"
    else:
        host_arg = ",".join(hosts_available[i] for i in sorted(chosen))

    # --- review (real dry-run plan) ------------------------------------------
    # Contrato explícito: install_fn aceita `components` — wrappers **kw
    # encaminham sem inspeção de assinatura (GAP-002).
    kwargs: dict[str, Any] = {
        "scope": scope,
        "profile": profile,
        "gateway_profile": gateway_profile,
        "components": components,
    }
    try:
        # `none` é opt-out explícito — zero hosts escolhidos nunca vira
        # "all" (GAP-003); csv de subconjunto é contrato válido (GAP-003b).
        plan = install_fn(host=host_arg or "none", dry_run=True, **kwargs)
    except Exception as exc:
        print(_c(ctx, "31", f"plan failed: {exc}"))
        return 1

    planned = plan.get("planned") or plan.get("planned_files") or plan.get("writes") or []
    rows: list[tuple[str, str]] = [
        ("scope", scope + _prov("scope")),
        ("profile", profile + _prov("profile")),
        ("execution", gateway_profile + _prov("gateway_profile")),
        ("mode", "family" if family else "this forge"),
        ("components", ", ".join(components) or "none"),
        ("hosts", (host_arg or "none") + _prov("hosts")),
        ("managed writes", str(len(planned) if isinstance(planned, list) else planned)),
    ]
    spec_entry = defaults.get("specialists")
    if isinstance(spec_entry, dict):
        spec_sel = spec_entry.get("value")
        if spec_sel is None:
            spec_label = "all registered"
        elif spec_sel:
            spec_label = ", ".join(str(f) for f in spec_sel)
        else:
            spec_label = "none — empty selection"
        spec_src = spec_entry.get("source")
        spec_state = spec_entry.get("state")
        rows.append(
            (
                "specialists",
                spec_label
                + (f" ({spec_src})" if spec_src else "")
                + (f" — {spec_state}" if spec_state else ""),
            )
        )
    # install-2.1 — the consolidated plan on the review screen: workspace
    # root, discovered members, registered forges and the closed plan
    # categories (new/updated/reused/preserved/conflict/unsupported).
    ws = plan.get("workspace") if isinstance(plan.get("workspace"), dict) else {}
    inst = plan.get("installation") if isinstance(plan.get("installation"), dict) else {}
    if plan.get("target_root"):
        rows.append(("workspace", str(plan["target_root"])))
    members = ws.get("members") or inst.get("members") or []
    if members:
        names = [str(m.get("path")) if isinstance(m, dict) else str(m) for m in members]
        rows.append(("members", f"{len(names)}: {', '.join(names[:6])}"))
    forge_rows = [f for f in (plan.get("forges") or []) if isinstance(f, dict)]
    if forge_rows:
        fid_list = ", ".join(str(f.get("forge_id")) for f in forge_rows)
        rows.append(("forges", f"{len(forge_rows)}: {fid_list}"))
    if inst:
        counts: dict[str, int] = {}
        for f in inst.get("forges") or []:
            cls = str((f or {}).get("classification") or "?")
            counts[cls] = counts.get(cls, 0) + 1
        if counts:
            rows.append(("plan", " · ".join(f"{k} {n}" for k, n in sorted(counts.items()))))
        n_conflicts = len(inst.get("conflicts") or [])
        if n_conflicts:
            rows.append(("conflicts", str(n_conflicts)))
    dashboard(
        f"{forge_name} — {i18n.t('review', ctx.language)}",
        [("Plan", rows)],
        ctx=ctx,
    )
    # The full consolidated doc — same formatter the CLI approve path
    # prints; deterministic and identical in non-TTY/JSON modes.
    from theforge.ui.kit import format_status_doc

    sys.stdout.write(format_status_doc(plan, ctx=ctx))

    if not confirm(i18n.t("confirm_q", ctx.language), default=False, ctx=ctx):
        return 130

    # --- apply (real governed install) ---------------------------------------
    receipt = install_fn(host=host_arg or "none", yes=True, dry_run=False, **kwargs)
    status = receipt.get("status", "unknown")
    if out_json:
        print(json.dumps(receipt, indent=2, ensure_ascii=False))
    color = "32" if status == "completed" else "31"
    print(f"\n  {i18n.t('status', ctx.language)}: {_c(ctx, color, status)}")

    # --- verify --------------------------------------------------------------
    if doctor_fn is not None and status == "completed":
        health = doctor_fn(scope=scope)
        raw_health = health.get("status") or health.get("health") or "unknown"
        hstatus = raw_health
        if isinstance(raw_health, dict):
            hstatus = raw_health.get("status", "unknown")
        color = "32" if hstatus in ("healthy", "PASS") else "33"
        print(f"  {i18n.t('health', ctx.language)}: {_c(ctx, color, str(hstatus))}")

    if status == "completed":
        print("  next: theforge specialists status · theforge doctor · theforge portal")

    return 0 if status == "completed" else 1


_PROV_LABELS = {
    "flag": "CLI",
    "forge.workspace.yaml": "workspace",
    "default": "default",
}


def _prov_label(source: object) -> str:
    """Map ``resolve`` provenance to the display vocabulary."""
    text = str(source or "default")
    if text.startswith("preset:"):
        return text
    return _PROV_LABELS.get(text, text)


def run_setup_wizard(
    *,
    root: Any = None,
    ctx: UIContext | None = None,
    out_json: bool = False,
) -> int:
    """Family onboarding over the same real plan/approval/apply wizard.

    Resolves ``forge.workspace.yaml`` (+ detection when the declared
    specialists mode is ``recommended``) BEFORE asking — the wizard
    pre-checks the resolved value for each field and the review prints its
    provenance. The approved plan takes the same ``install_auto`` kwargs
    route as ``theforge setup`` (``forge=``, ``setup=``, ``detection=``),
    so declarative and wizard plans are identical for equal inputs.
    """
    try:
        service = importlib.import_module("theforge.install.service")
        options = importlib.import_module("theforge.install.options")
        workspace = importlib.import_module("theforge.workspace")
        kit = importlib.import_module("theforge._installkit")
    except ModuleNotFoundError as exc:
        if exc.name == "theforge" or (exc.name or "").startswith("theforge."):
            print(
                "family onboarding unavailable: install The Forge separately; "
                "native Forge commands remain available"
            )
            return 2
        raise

    base = Path(root) if root else Path.cwd()
    config = workspace.load_workspace_config(base)
    # Recommended needs the detection pass + the live registry; resolve the
    # mode first (pure) so detection runs exactly when the CLI would run it
    # — identical ``install_auto`` kwargs ⇒ identical plan.
    detection: dict[str, Any] | None = None
    registered: list[str] = []
    pre = options.resolve(
        preset=None,
        profile=None,
        gateway_profile=None,
        host=None,
        forge=None,
        config=config,
    )
    if pre.specialists_mode == "recommended":
        detection = workspace.detect_workspace(base)
        registered = sorted(
            str(m.get("forge_id") or "") for m in kit.installed_forges()
        )
    try:
        wiz = options.wizard_defaults(
            config=config,
            detection=detection,
            registered=registered,
        )
    except Exception as exc:  # same refusal surface as the CLI resolver
        print(f"setup resolution failed: {exc}", file=sys.stderr)
        return 2
    for warning in wiz.resolution.warnings:
        print(f"theforge: warning: {warning}", file=sys.stderr)

    res_doc = wiz.doc.get("resolution") or {}

    def _field_src(name: str) -> str:
        entry = res_doc.get(name) or {}
        return _prov_label(entry.get("source"))

    spec_doc = wiz.doc.get("specialists") or {}
    if wiz.resolution.specialists_mode == "recommended":
        spec_src = "detected"
    else:
        spec_src = _prov_label(spec_doc.get("source"))
    if wiz.empty_state is not None:
        print(
            _c(
                ctx or UIContext.detect(),
                "33",
                f"  note: specialists resolved to an empty selection "
                f"({wiz.empty_state}) — the plan will explain the next step",
            )
        )

    defaults: dict[str, Any] = {
        "scope": {"value": "project", "source": "default"},
        "profile": {"value": wiz.resolution.profile, "source": _field_src("profile")},
        "gateway_profile": {
            "value": wiz.resolution.gateway_profile,
            "source": _field_src("gateway-profile"),
        },
        "hosts": {"value": wiz.resolution.host, "source": _field_src("host")},
        "specialists": {
            "value": wiz.forges,
            "source": spec_src,
            "state": wiz.empty_state,
        },
    }

    return run_wizard(
        forge_name="the-forge family",
        install_fn=lambda **kw: service.install_auto(
            root=root,
            forge=wiz.forges,
            members=(),
            setup=wiz.doc,
            detection=detection,
            **kw,
        ),
        doctor_fn=lambda **kw: service.doctor(root=root, **kw),
        ctx=ctx,
        out_json=out_json,
        family=True,
        defaults=defaults,
    )
