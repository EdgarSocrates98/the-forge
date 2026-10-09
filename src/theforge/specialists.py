"""Specialist control-plane view (FASE 1+10): lifecycle per forge.

Composes the honest lifecycle state from real sources, highest first:

1. installations registry (``~/.forge/installations/<id>.json``) → at
   least INSTALLED; a runnable ``--version`` promotes to CONFIGURED;
   a provider-registry entry promotes to REGISTERED; a passing health
   probe promotes to HEALTHY.
2. workspace checkouts carrying ``forge.json`` → DISCOVERED /
   INSTALLABLE (bootstrap present).
3. nothing → UNKNOWN / NOT_INSTALLED (declared catalog forges only).

Never infers HEALTHY from file presence alone.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from theforge import _installkit as kit
from theforge.contracts.base import from_dict
from theforge.contracts.specialist import AgenticManifest, SpecialistLifecycle


def catalog_ids(workspace_root: Path | None = None) -> list[str]:
    """The specialist catalog, data-driven — never a code literal.

    Sources (union, sorted):
    1. ``~/.forge/installations/*.json`` — registered installations.
    2. bundled ``forge-knowledge/*.json`` packages — bootstrap metadata.
    3. workspace checkouts declaring ``forge.json`` ids.

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

    for forge_id in catalog_ids(workspace_root):
        manifest_doc = kit._load_json(install_dir / f"{forge_id}.json", None)
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
    if view.cli and shutil.which(view.cli):
        cli_argv = [view.cli]
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
