"""The installed specialist's import name, which changed upstream: the package is
``sparkforge_aws`` after the ``sparkforge`` -> ``sparkforge_aws`` rename (same distribution
``sparkforge-aws``, same ``0.5.x`` line), and ``sparkforge`` on the pre-rename installs this
adapter already supports. Every native import goes through here, new name first.
"""

from __future__ import annotations

import importlib.util
from importlib.metadata import version as metadata_version
from typing import Any

PACKAGES = ("sparkforge_aws", "sparkforge")
DISPATCHERS = tuple(f"{package}.adapters.tools" for package in PACKAGES)
UPSTREAM_MODULES = tuple(f"{package}.adapters.upstream" for package in PACKAGES)
DISTRIBUTION = "sparkforge-aws"
# The upstream-facts intake schema is renamed with the package: pre-rename
# installs validate ``sparkforge/upstream-facts/v1``, renamed installs validate
# ``sparkforge_aws/upstream-facts/v1``. Emit whatever the installed intake
# declares — never a guess.
LEGACY_UPSTREAM_SCHEMA = "sparkforge/upstream-facts/v1"


def dispatcher_found() -> bool:
    """Whether an adapter tool surface is importable here (found, never imported)."""
    for name in DISPATCHERS:
        try:
            if importlib.util.find_spec(name) is not None:
                return True
        except (ImportError, ValueError):
            continue
    return False


def import_tools() -> tuple[Any, Any]:
    """``(TOOLS, call_tool)`` of the installed specialist, new package name first."""
    last: Exception | None = None
    for name in DISPATCHERS:
        try:
            module = __import__(name, fromlist=["TOOLS", "call_tool"])
            return module.TOOLS, module.call_tool
        except (ImportError, AttributeError) as exc:
            last = exc
    raise ImportError(
        f"no Spark Forge AWS tool surface importable ({', '.join(DISPATCHERS)})"
    ) from last


def installed_version() -> str | None:
    """The specialist version: ``__version__`` of either package (light import), else the
    ``sparkforge-aws`` distribution metadata; None when neither answers."""
    for package in PACKAGES:
        try:
            module = __import__(package)
            version = getattr(module, "__version__", None)
            if isinstance(version, str):
                return version
        except Exception:  # noqa: BLE001 - any failure of the specialist falls through
            continue
    try:
        return metadata_version(DISTRIBUTION)
    except Exception:  # noqa: BLE001 - unreadable metadata: no version, never internal
        return None


def upstream_schema() -> str:
    """The upstream-facts document schema the *installed* intake validates.

    The specialist declares it in ``adapters.upstream.UPSTREAM_SCHEMA``; the
    rename ``sparkforge`` -> ``sparkforge_aws`` renamed the document too, so a
    hardcoded name would silently emit documents the installed intake refuses.
    Falls back to the legacy name when no intake is importable.
    """
    for name in UPSTREAM_MODULES:
        try:
            module = __import__(name, fromlist=["UPSTREAM_SCHEMA"])
            schema = getattr(module, "UPSTREAM_SCHEMA", None)
            if isinstance(schema, str) and schema:
                return schema
        except Exception:  # noqa: BLE001 - any import failure falls through
            continue
    return LEGACY_UPSTREAM_SCHEMA
