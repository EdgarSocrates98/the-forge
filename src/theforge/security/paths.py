"""Path guards: keep reads inside the workspace and away from secret files."""

from fnmatch import fnmatch
from pathlib import Path

IGNORED_DIRS = frozenset(
    {
        ".git",
        ".forge",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        "dist",
        "build",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".hypothesis",
    }
)
SECRET_PATTERNS = (
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "id_rsa*",
    "id_ed25519*",
    "*.pfx",
    "*.p12",
    "credentials*",
    ".npmrc",
    ".netrc",
    ".pgpass",
    "*.token",
    "secrets.*",
)


def is_secret_name(name: str) -> bool:
    lowered = name.lower()
    return any(fnmatch(lowered, pattern) for pattern in SECRET_PATTERNS)


def resolve_inside(root: Path, candidate: Path) -> Path | None:
    """Return the resolved path if it exists and stays inside root, else None."""
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        return None
    root_resolved = root.resolve()
    if resolved == root_resolved or resolved.is_relative_to(root_resolved):
        return resolved
    return None
