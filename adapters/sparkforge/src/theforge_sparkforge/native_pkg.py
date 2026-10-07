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
DISTRIBUTION = "sparkforge-aws"


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
        f"no Spark Forge tool surface importable ({', '.join(DISPATCHERS)})") from last


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
