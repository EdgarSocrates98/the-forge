"""Specialist control-plane view (FASE 1+10): lifecycle per forge.

Composes the honest lifecycle state from real sources, highest first:

1. installations registry (``~/.forge/installations/<id>.json``) → at
   least INSTALLED; a runnable ``--version`` promotes to CONFIGURED;
   a provider-registry entry promotes to REGISTERED; a passing health
   probe promotes to HEALTHY.
1b. forge-cli registry (``~/.forge-cli/forges/state.json``) → same
   ladder (receipt ``venv`` + ``shim``/``bin`` probe); the canonical
   manifest wins when both exist.
2. workspace checkouts carrying ``forge.json`` → DISCOVERED /
   INSTALLABLE (bootstrap present).
3. nothing → UNKNOWN / NOT_INSTALLED (declared catalog forges only).

Never infers HEALTHY from file presence alone.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from theforge import _installkit as kit
from theforge.contracts.base import from_dict
from theforge.contracts.specialist import (
    AgenticManifest,
    DelegationEntry,
    SpecialistLifecycle,
)


def _forge_cli_state() -> dict[str, dict[str, Any]]:
    """forge-cli registry — ``~/.forge-cli/forges/state.json`` name → receipt.

    Installs feitos pelo `forge-cli install` (PyPI+venv) vivem neste
    registro separado; esta é a ponte que faz o lifecycle do The Forge
    enxergá-los. Ausente/corrompido → {} (nunca quebra a coleta).
    `FORGE_CLI_HOME` tem prioridade — o forge-cli resolve seu home por
    `FORGE_CLI_HOME || os.homedir()` (modo hermético/bench).
    """
    import os

    home = Path(os.environ["FORGE_CLI_HOME"]) if os.environ.get("FORGE_CLI_HOME") else kit._home()
    path = home / ".forge-cli" / "forges" / "state.json"
    doc = kit._load_json(path, None)
    if not isinstance(doc, dict):
        return {}
    forges = doc.get("forges")
    if not isinstance(forges, dict):
        return {}
    return {k: v for k, v in forges.items() if isinstance(v, dict)}


def catalog_ids(workspace_root: Path | None = None) -> list[str]:
    """The specialist catalog, data-driven — never a code literal.

    Sources (union, sorted):
    1. ``~/.forge/installations/*.json`` — registered installations.
    2. bundled ``forge-knowledge/*.json`` packages — bootstrap metadata.
    3. workspace checkouts declaring ``forge.json`` ids.
    4. ``~/.forge-cli/forges/state.json`` — forge-cli registry installs.

    A new specialist onboards by shipping data, not by editing core.
    """
    from theforge import knowledge

    ids: set[str] = set()
    install_dir = kit.installations_dir()
    if install_dir.is_dir():
        for path in install_dir.glob("*.json"):
            doc = kit._load_json(path, None)
            if doc and doc.get("forge_id"):
                ids.add(doc["forge_id"])
    ids.update(_forge_cli_state().keys())
    ids.update(knowledge.load_all().keys())
    if workspace_root is not None:
        for member in kit.discover_projects(workspace_root):
            spec = member / "forge.json"
            if spec.is_file():
                try:
                    fid = json.loads(spec.read_text(encoding="utf-8")).get("forge_id")
                    if fid:
                        ids.add(fid)
                except (OSError, json.JSONDecodeError):
                    continue
    return sorted(ids)


# Backwards-compatible accessor; built lazily so tests can override HOME.
def CATALOG() -> tuple[str, ...]:  # noqa: N802 — mirrors the old constant
    return tuple(catalog_ids())


_VERSION_TIMEOUT = 15


@dataclass(frozen=True, kw_only=True)
class SpecialistView:
    lifecycle: SpecialistLifecycle
    install_root: str | None = None
    cli: str | None = None
    checkout: str | None = None  # local clone found
    mcp: dict[str, Any] | None = None
    manifest: AgenticManifest | None = None
    notes: list[str] = field(default_factory=list)


def _cli_runnable(cli_argv: list[str] | None) -> bool:
    if not cli_argv:
        return False
    try:
        proc = subprocess.run(cli_argv, capture_output=True, text=True, timeout=_VERSION_TIMEOUT)
        return proc.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def load_agentic_manifest(forge_id: str, checkout: Path | None) -> AgenticManifest | None:
    """``forge.agentic.json`` in the checkout root, when declared."""
    if checkout is None:
        return None
    path = checkout / "forge.agentic.json"
    if not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return from_dict(AgenticManifest, doc)
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def _checkout_for(forge_id: str, workspace_root: Path | None) -> Path | None:
    if workspace_root is None:
        return None
    for member in kit.discover_projects(workspace_root):
        spec_path = member / "forge.json"
        if spec_path.is_file():
            try:
                if json.loads(spec_path.read_text(encoding="utf-8")).get("forge_id") == forge_id:
                    return member
            except (OSError, json.JSONDecodeError):
                continue
    return None


def collect(
    *,
    workspace_root: Path | None = None,
    registered: set[str] | None = None,
    probe_cli: bool = True,
) -> list[SpecialistView]:
    """Lifecycle view for every catalog forge, evidence only."""
    registered = registered or set()
    views: list[SpecialistView] = []
    install_dir = kit.installations_dir()
    cli_registry = _forge_cli_state()

    for forge_id in catalog_ids(workspace_root):
        manifest_doc = kit._load_json(install_dir / f"{forge_id}.json", None)
        cli_receipt = cli_registry.get(forge_id)
        checkout = _checkout_for(forge_id, workspace_root)
        notes: list[str] = []

        state = "UNKNOWN"
        install_root: str | None = None
        cli_name: str | None = None
        mcp: dict[str, Any] | None = None
        version = "unknown"

        if manifest_doc:
            state = "DISCOVERED"
            install_root = manifest_doc.get("install_root")
            version = manifest_doc.get("version", "unknown")
            mcp = manifest_doc.get("mcp")
            cli = manifest_doc.get("cli") or {}
            cli_name = cli.get("name")
            cli_ok = False
            if probe_cli:
                version_cmd = cli.get("version_cmd") or (
                    [cli_name, "--version"] if cli_name else None
                )
                cli_ok = _cli_runnable(version_cmd)
            root_ok = bool(install_root and Path(install_root).is_dir())
            if root_ok or cli_ok:
                state = "INSTALLED"
                if not root_ok:
                    notes.append("install_root missing on disk; cli on PATH is the live install")
            else:
                notes.append("install_root missing on disk and cli not runnable")
                state = "DEGRADED"
            if state == "INSTALLED" and probe_cli:
                if cli_ok:
                    state = "CONFIGURED"
                else:
                    notes.append("cli not runnable; version probe failed")
            if state == "CONFIGURED" and forge_id in registered:
                state = "REGISTERED"
            if cli_receipt is not None:
                notes.append("also installed via forge-cli registry (PyPI+venv)")
        elif cli_receipt is not None:
            # Install registry-first do forge-cli: venv isolada + receipt.
            # A escada de evidência é a mesma do manifesto canônico —
            # INSTALLED exige venv OU cli vivo; CONFIGURED exige probe.
            state = "DISCOVERED"
            install_root = cli_receipt.get("venv")
            version = cli_receipt.get("version", "unknown")
            launcher = cli_receipt.get("shim") or cli_receipt.get("bin") or ""
            cli_name = Path(launcher).stem if launcher else None
            notes.append("installed via forge-cli registry (PyPI+venv)")
            if cli_receipt.get("verify", {}).get("ok") is False:
                notes.append("install-time verify falhou no receipt do forge-cli")
            cli_ok = False
            if probe_cli:
                if shim := cli_receipt.get("shim"):
                    cli_ok = _cli_runnable([shim, "--version"])
                if not cli_ok and cli_receipt.get("bin"):
                    cli_ok = _cli_runnable([cli_receipt["bin"], "--version"])
            root_ok = bool(install_root and Path(install_root).is_dir())
            if root_ok or cli_ok:
                state = "INSTALLED"
                if not root_ok:
                    notes.append("venv missing on disk; launcher still runnable")
            else:
                state = "DEGRADED"
                notes.append("venv missing on disk and launcher not runnable")
            if state == "INSTALLED" and probe_cli:
                if cli_ok:
                    state = "CONFIGURED"
                else:
                    notes.append("launcher not runnable; version probe failed")
            if state == "CONFIGURED" and forge_id in registered:
                state = "REGISTERED"
        elif checkout is not None:
            state = "DISCOVERED"
            bootstrap = (checkout / "setup.sh").is_file() or (checkout / "setup.ps1").is_file()
            if bootstrap:
                state = "INSTALLABLE"
                notes.append("local checkout with bootstrap; not installed")
            else:
                notes.append("local checkout without setup script")
        else:
            state = "NOT_INSTALLED"
            notes.append("no installation record and no local checkout")

        lifecycle = SpecialistLifecycle(
            provider=forge_id,
            version=version,
            installation_state=state,
            activation_state="HOST_ACTIVATION_PENDING",
            evidence=notes,
        )
        views.append(
            SpecialistView(
                lifecycle=lifecycle,
                install_root=install_root,
                cli=cli_name,
                checkout=str(checkout) if checkout else None,
                mcp=mcp,
                manifest=load_agentic_manifest(forge_id, checkout),
                notes=notes,
            )
        )
    return views


def _checkout_cli_argv(manifest: AgenticManifest, checkout: str | None) -> list[str] | None:
    """``python -c "from <mod> import <fn>; <fn>()"`` run from a checkout."""
    if not manifest.cli_entry or not checkout or ":" not in manifest.cli_entry:
        return None
    module, _, fn = manifest.cli_entry.partition(":")
    checkout_path = Path(checkout)
    # package root: src/ layout or flat
    pkg_root = (
        checkout_path / "src"
        if (checkout_path / "src" / module.split(".")[0]).is_dir()
        else checkout_path
    )
    return [
        _sys_executable(),
        "-c",
        f"import sys; sys.path.insert(0, {str(pkg_root)!r}); from {module} import {fn}; {fn}()",
    ]


def _sys_executable() -> str:
    import sys

    return sys.executable


def resolve_command(
    template: list[str],
    *,
    view: SpecialistView,
    target: str = ".",
) -> list[str] | None:
    """Resolve a workflow command template to a runnable argv, or None.

    ``{cli}`` prefers the installed launcher (probed); falls back to the
    checkout's ``cli_entry`` when the clone imports cleanly.
    """
    import shutil

    manifest = view.manifest
    cli_argv: list[str] | None = None
    if view.cli:
        installed_cli = shutil.which(view.cli)
        if installed_cli:
            # Keep the resolved launcher path. On Windows ``which`` may find
            # a .cmd/.exe sibling while subprocess cannot resolve bare names
            # consistently across shells and Python spawn modes.
            cli_argv = [installed_cli]
    elif manifest is not None:
        cli_argv = _checkout_cli_argv(manifest, view.checkout)

    out: list[str] = []
    for token in template:
        if token == "{cli}":
            if cli_argv is None:
                return None
            out.extend(cli_argv)
        elif token == "{python}":
            out.append(_sys_executable())
        elif token == "{checkout}":
            if not view.checkout:
                return None
            out.append(view.checkout)
        elif token == "{target}":
            out.append(target)
        else:
            out.append(token)
    return out


def to_rows(views: list[SpecialistView]) -> list[dict[str, Any]]:
    return [
        {
            "provider": v.lifecycle.provider,
            "state": v.lifecycle.installation_state,
            "version": v.lifecycle.version,
            "cli": v.cli,
            "checkout": v.checkout,
            "mcp": bool(v.mcp and v.mcp.get("command")),
            "agentic_manifest": v.manifest is not None,
            "notes": v.notes,
        }
        for v in views
    ]


_STOPWORDS = frozenset(
    [
        "a",
        "o",
        "as",
        "os",
        "um",
        "uma",
        "de",
        "do",
        "da",
        "em",
        "no",
        "na",
        "para",
        "por",
        "com",
        "sem",
        "e",
        "ou",
        "que",
        "the",
        "an",
        "and",
        "or",
        "for",
        "to",
        "in",
        "on",
        "at",
        "is",
        "it",
        "my",
        "me",
        "run",
        "execute",
        "make",
        "create",
    ]
)


def _intent_tokens(intent: str) -> list[str]:
    import re

    return [
        t for t in re.findall(r"[a-z0-9_-]+", intent.lower()) if t not in _STOPWORDS and len(t) > 1
    ]


def _wf_text(wf: DelegationEntry) -> str:
    return f"{wf.id} {wf.description}".lower()


def select_workflow(workflows: Sequence[DelegationEntry], intent: str) -> DelegationEntry | str:
    """Contextual pick among a manifest's workflows — deterministic, never
    a blind ``workflows[0]`` (GAP-004).

    Um só workflow → ele mesmo. Match exato de `id` nos tokens → esse
    workflow. Caso contrário, score por overlap de tokens do intent com
    `id`+`description`; vitória clara → vencedor, empate/zero → a literal
    ``"ambiguous"`` (nunca um chute — a chamada decide como resolver:
    `--workflow <id>` na CLI, menu `select` na TUI).
    """
    if len(workflows) == 1:
        return workflows[0]
    tokens = _intent_tokens(intent)
    if tokens:
        exact = [w for w in workflows if w.id.lower() in tokens]
        if len(exact) == 1:
            return exact[0]
    scored = sorted(
        (
            (sum(2 if t in w.id.lower() else 1 for t in tokens if t in _wf_text(w)), w)
            for w in workflows
        ),
        key=lambda s: -s[0],
    )
    if not scored or scored[0][0] == 0:
        return "ambiguous"
    if len(scored) > 1 and scored[0][0] == scored[1][0]:
        return "ambiguous"
    return scored[0][1]
