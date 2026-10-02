"""Workspace state directory `.forge/`: layout, init and lookup."""

from pathlib import Path

from theforge.errors import PersistenceError, UsageError

FORGE_DIR_NAME = ".forge"
SUBDIRS = ("config", "registry", "runs", "cache")
GITIGNORE = (
    "# Managed by The Forge: only config/ is committable.\n"
    "*\n!.gitignore\n!config/\n!config/**\n"
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


def find_forge_dir(root: Path) -> Path | None:
    candidate = root / FORGE_DIR_NAME
    return candidate if candidate.is_dir() else None


def require_forge_dir(root: Path) -> Path:
    forge_dir = find_forge_dir(root)
    if forge_dir is None:
        raise UsageError(f"{root} is not initialized; run `theforge init`")
    return forge_dir


def init_workspace(root: Path) -> list[str]:
    forge_dir = root / FORGE_DIR_NAME
    created: list[str] = []
    try:
        for directory in (forge_dir, *(forge_dir / sub for sub in SUBDIRS)):
            if not directory.exists():
                directory.mkdir(parents=True)
                created.append(directory.relative_to(root).as_posix())
        files = ((forge_dir / ".gitignore", GITIGNORE),
                 (forge_dir / "config" / "providers.toml", PROVIDERS_TEMPLATE))
        for path, content in files:
            if not path.exists():
                path.write_text(content, encoding="utf-8")
                created.append(path.relative_to(root).as_posix())
    except OSError as exc:
        raise PersistenceError(f"cannot initialize {forge_dir}: {exc}") from exc
    return created
