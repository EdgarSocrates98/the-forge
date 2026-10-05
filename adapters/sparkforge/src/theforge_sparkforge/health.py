"""Health of the Spark Forge adapter: no network, no credentials, never the native ``doctor``.

Four checks build the ``HealthReport`` payload (``{status, checks: [{name, ok, detail}]}``):

1. ``interpreter``: Python >= 3.10;
2. ``dispatcher``: ``sparkforge.adapters.tools`` is importable, found with ``find_spec`` and
   never imported (importing the tool surface costs seconds);
3. ``specialist-version``: the Spark Forge version (``sparkforge.__version__``, a light import;
   ``--assume-specialist-version`` replaces it) inside ``SUPPORTED_SPECIALIST``;
4. ``snapshot``: the packaged ``native_catalog.json`` is present and readable.

(1), (2) or (4) failing -> ``unavailable``; only (3) failing -> ``degraded`` with the version
found and the supported window; else ``ok``. With ``--replay`` the interpreter and the native
probes come from the scenario's ``environment.json`` and ``health.json``.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from dataclasses import dataclass
from importlib.metadata import version as metadata_version
from typing import Any

from theforge_sparkforge.backend import INSTALL_HINT, MIN_PYTHON

DISPATCHER = "sparkforge.adapters.tools"
DISTRIBUTION = "sparkforge-aws"
_SEMVER = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")
_CLAUSE = re.compile(r"(>=|<=|==|!=|>|<)\s*(\S+)")
_PYTHON = re.compile(r"(\d+)\.(\d+)(?:\.\d+)?")


@dataclass(frozen=True)
class Observation:
    """What health saw of the native side: interpreter, dispatcher and installed version.

    ``interpreter`` names where it was seen (this interpreter or the recorded one).
    """

    interpreter: str
    python: str
    dispatcher: bool
    specialist_version: str | None


def _parse(version: str) -> tuple[int, int, int] | None:
    match = _SEMVER.fullmatch(version)
    return None if match is None else (int(match[1]), int(match[2]), int(match[3]))


def in_window(version: str, window: str) -> bool:
    """Whether the SemVer ``version`` (``X.Y.Z``) satisfies every clause of ``window``
    (``>=0.5.0,<0.6.0``). Anything that is not a plain ``X.Y.Z`` is outside the window."""
    found = _parse(version)
    if found is None:
        return False
    for clause in window.split(","):
        match = _CLAUSE.fullmatch(clause.strip())
        bound = None if match is None else _parse(match[2])
        if match is None or bound is None:
            return False
        op = match[1]
        holds = {">=": found >= bound, "<=": found <= bound, ">": found > bound,
                 "<": found < bound, "==": found == bound, "!=": found != bound}[op]
        if not holds:
            return False
    return True


def _installed_version() -> str | None:
    """``sparkforge.__version__`` (``sparkforge/__init__`` is light), else the distribution
    metadata of ``sparkforge-aws``; None when neither answers."""
    try:
        import sparkforge
        version = getattr(sparkforge, "__version__", None)
        if isinstance(version, str):
            return version
    except Exception:  # noqa: BLE001 - any failure of the specialist falls back to metadata
        pass
    try:
        return metadata_version(DISTRIBUTION)
    except Exception:  # noqa: BLE001 - unreadable metadata: no version, never internal
        return None


def observe_live() -> Observation:
    """The native side of this interpreter, without importing the dispatcher."""
    try:
        dispatcher = importlib.util.find_spec(DISPATCHER) is not None
    except (ImportError, ValueError):
        dispatcher = False
    python = ".".join(str(part) for part in sys.version_info[:3])  # no pre-release suffix
    return Observation(interpreter=f"{sys.executable}", python=python,
                       dispatcher=dispatcher,
                       specialist_version=_installed_version() if dispatcher else None)


def _python_ok(python: str) -> bool:
    match = _PYTHON.fullmatch(python)
    return match is not None and (int(match[1]), int(match[2])) >= MIN_PYTHON


def _check(name: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "ok": ok, "detail": detail}


def report(observation: Observation, *, window: str, assumed: str | None,
           snapshot_problem: str | None) -> dict[str, Any]:
    """The ``HealthReport`` payload of an observation."""
    where = f"{observation.interpreter} (Python {observation.python})"
    floor = f"{MIN_PYTHON[0]}.{MIN_PYTHON[1]}"
    python_ok = _python_ok(observation.python)
    interpreter = _check(
        "interpreter", python_ok,
        f"{where}" if python_ok else f"{where}; the Spark Forge needs Python >= {floor}")
    dispatcher = _check(
        "dispatcher", observation.dispatcher,
        f"{DISPATCHER} is importable with {where} (found, not imported)"
        if observation.dispatcher else
        f"sparkforge is not importable with {where}: {DISPATCHER} not found; "
        f"{INSTALL_HINT} in that interpreter")
    version = assumed if assumed is not None else observation.specialist_version
    if version is None:
        detail = f"found no sparkforge version, supported {window}"
        version_ok = False
    else:
        version_ok = in_window(version, window)
        detail = f"found {version}, supported {window}"
        if assumed is not None:
            installed = observation.specialist_version or "unknown"
            detail += f" (assumed by --assume-specialist-version; installed {installed})"
    specialist = _check("specialist-version", version_ok, detail)
    snapshot = _check("snapshot", snapshot_problem is None,
                      "native_catalog.json is present and readable"
                      if snapshot_problem is None else snapshot_problem)
    if not (python_ok and observation.dispatcher and snapshot_problem is None):
        status = "unavailable"
    elif not version_ok:
        status = "degraded"
    else:
        status = "ok"
    return {"status": status, "checks": [interpreter, dispatcher, specialist, snapshot]}
