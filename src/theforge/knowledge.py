"""Forge Knowledge Layer (agentic prompt §5-7): bootstrap knowledge per specialist.

``forge-knowledge/<provider>.json`` files ship with the repository and answer
the questions that exist *before* a specialist is installed: what it is for,
how to recognize a task for it, how to install it, how to verify the install
and who verifies its output. Runtime reality — capabilities, health, surface
fingerprint — always comes from the live ``describe``/registry, never from
these files (§7).

The layer is data-first: no provider imports, no network, stdlib only.
"""

from __future__ import annotations

import json
from pathlib import Path

from theforge.contracts import from_dict
from theforge.contracts.knowledge import ForgeKnowledge
from theforge.errors import PersistenceError, UsageError

__all__ = ["DEFAULT_KNOWLEDGE_DIR", "families", "knowledge_for", "load_all", "load_package"]

DEFAULT_KNOWLEDGE_DIR = Path(__file__).resolve().parents[2] / "forge-knowledge"


def load_package(path: Path) -> ForgeKnowledge:
    """Load and validate one knowledge package; contract violations raise."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise PersistenceError(f"forge knowledge: cannot read {path}: {exc}") from exc
    # Strict: knowledge packages are authored core data, not provider output —
    # a smuggled field is malformed input, never forward compatibility (§76).
    package = from_dict(ForgeKnowledge, data, "$", strict=True)
    if package.id != path.stem:
        raise UsageError(
            f"forge knowledge: file {path.name} must be named after its provider id {package.id!r}"
        )
    return package


def load_all(directory: Path | None = None) -> dict[str, ForgeKnowledge]:
    """All knowledge packages in ``directory`` (default: repo ``forge-knowledge/``),
    keyed by provider id. An absent directory means an empty ecosystem — honest,
    not an error."""
    root = directory if directory is not None else DEFAULT_KNOWLEDGE_DIR
    if not root.is_dir():
        return {}
    packages: dict[str, ForgeKnowledge] = {}
    for path in sorted(root.glob("*.json")):
        package = load_package(path)
        packages[package.id] = package
    return packages


def knowledge_for(provider: str, directory: Path | None = None) -> ForgeKnowledge | None:
    """The bootstrap package for one provider id, or None if unknown."""
    return load_all(directory).get(provider)


def families(packages: dict[str, ForgeKnowledge]) -> dict[str, list[str]]:
    """Family → member provider ids (§36): the family model is metadata on the
    knowledge package, not a new abstraction."""
    out: dict[str, list[str]] = {}
    for package in packages.values():
        out.setdefault(package.family, []).append(package.id)
    return {family: sorted(ids) for family, ids in sorted(out.items())}
