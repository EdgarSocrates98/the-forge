"""Workspace state directory `.forge/`: layout, init and lookup."""

import shutil
from pathlib import Path

from theforge.errors import PersistenceError, UsageError

FORGE_DIR_NAME = ".forge"
SUBDIRS = ("config", "runs", "cache")
LEGACY_REGISTRY_DIR = "registry"
GITIGNORE = (
    "# Managed by The Forge: only config/ is committable.\n*\n!.gitignore\n!config/\n!config/**\n"
)
PROVIDERS_TEMPLATE = """\
# Providers declared by this workspace. Each entry: id, argv (list).
# Entries here are ALWAYS 'unverified': they are never executed unless you pass
# --allow-unverified, or you copy the entry into your user providers.toml
# (%APPDATA%/theforge/providers.toml, ~/.config/theforge/providers.toml or
# $THEFORGE_CONFIG_DIR/providers.toml), which is the only file that grants trust.
# "{python}" in argv is replaced by the interpreter running The Forge.
#
# [[providers]]
# id = "my-forge"
# argv = ["my-forge-cli", "protocol"]
"""
WORKSPACE_MARKER = "forge.workspace.yaml"
WORKSPACE_MARKER_BODY = """\
# Managed by The Forge — the workspace identity marker (install-2.1,
# ADR-0065). The portable installkit recognizes this file: `install auto`
# / `setup --scope workspace` resolves this directory as the workspace
# root and discovers member project roots on disk (.git, forge.json,
# pyproject.toml, package.json). Delete it to unmark this directory.
forge_workspace: true
"""


def find_forge_dir(root: Path) -> Path | None:
    candidate = root / FORGE_DIR_NAME
    return candidate if candidate.is_dir() else None


def require_forge_dir(root: Path) -> Path:
    forge_dir = find_forge_dir(root)
    if forge_dir is None:
        raise UsageError(f"{root} is not initialized; run `theforge init`")
    return forge_dir


def init_workspace(root: Path, warnings: list[str] | None = None) -> list[str]:
    """Create `.forge/`; removes the legacy in-workspace registry cache (warning appended)."""
    forge_dir = root / FORGE_DIR_NAME
    created: list[str] = []
    warning = remove_legacy_cache(forge_dir / LEGACY_REGISTRY_DIR)
    if warning and warnings is not None:
        warnings.append(warning)
    try:
        for directory in (forge_dir, *(forge_dir / sub for sub in SUBDIRS)):
            if not directory.exists():
                directory.mkdir(parents=True)
                created.append(directory.relative_to(root).as_posix())
        files = (
            (forge_dir / ".gitignore", GITIGNORE),
            (forge_dir / "config" / "providers.toml", PROVIDERS_TEMPLATE),
        )
        for path, content in files:
            if not path.exists():
                path.write_text(content, encoding="utf-8")
                created.append(path.relative_to(root).as_posix())
        marker = root / WORKSPACE_MARKER
        if not marker.exists():
            marker.write_text(WORKSPACE_MARKER_BODY, encoding="utf-8")
            created.append(WORKSPACE_MARKER)
    except OSError as exc:
        raise PersistenceError(f"cannot initialize {forge_dir}: {exc}") from exc
    return created


def remove_legacy_cache(legacy: Path) -> str | None:
    """Delete the Cycle 1 in-workspace cache dir; returns a warning when something was removed."""
    try:
        if legacy.is_symlink() or legacy.is_file():
            legacy.unlink()
        elif legacy.is_dir():
            shutil.rmtree(legacy)
        else:
            return None
    except OSError as exc:
        return f"cannot remove legacy registry cache {legacy}: {exc}"
    return (
        f"removed legacy registry cache {legacy}; the cache now lives in the user cache directory"
    )
