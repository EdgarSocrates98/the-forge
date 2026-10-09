"""``health`` without network, without credentials and without running Forge Doctor Data.

Four local checks, in order: (1) the interpreter is Python >= 3.11;
(2) ``forge_doctor_data`` is importable; (3) its version (``forge_doctor_data.__version__``,
or ``--assume-specialist-version``) is inside ``SUPPORTED_SPECIALIST`` (release candidates
compare below their release: ``1.0.0rc1`` < ``1.0.0``); (4) ``boundary``: the public boundary
module the adapter drives (``forge_doctor_data.core.forger``) is found with ``find_spec``,
never imported. (1)/(2) failing make the report ``unavailable`` and stop there; (3) out of
the window makes it ``degraded``; (4) missing makes it ``unavailable``.

The native ``forge-doctor-data doctor`` is deliberately not run: the adapter only needs the
boundary and the conformance seam, both pure-Python and offline. With ``--replay <dir>`` the
specialist is never consulted: (1)-(3) read ``environment.json`` and (4) the scenario's
``health.json`` (``{provenance, boundary}``).
"""

from __future__ import annotations

import importlib
import importlib.util
import re
import sys
from collections.abc import Mapping, Sequence
from typing import Any

from theforge_doctordata import REQUIRED_PYTHON, SUPPORTED_SPECIALIST
from theforge_doctordata._shell import AdapterOptions, Reply, fail
from theforge_doctordata.backend import (
    ENVIRONMENT_FILE,
    HEALTH_FILE,
    REQUIRED,
    ReplayError,
    read_environment,
    read_health,
)

# The public boundary module the adapter drives (``accept_request``).
BOUNDARY_MODULE = "forge_doctor_data.core.forger"
_FINAL = 1_000_000  # a release compares above every rc of the same X.Y.Z
_VERSION = re.compile(
    r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:(?:rc|\.rc|rc\.|-rc)\.?(0|[1-9][0-9]*))?",
    re.ASCII,
)
_CLAUSE = re.compile(r"(>=|<=|==|>|<)\s*(\S+)")

Check = dict[str, Any]


def _check(name: str, ok: bool, detail: str) -> Check:
    return {"name": name, "ok": ok, "detail": detail}


def _parse(version: str) -> tuple[int, int, int, int] | None:
    """``X.Y.Z[rcN]`` as a comparable tuple; rc < the release of the same X.Y.Z."""
    match = _VERSION.fullmatch(version.strip())
    if match is None:
        return None
    rc = int(match.group(4)) if match.group(4) is not None else _FINAL
    return int(match.group(1)), int(match.group(2)), int(match.group(3)), rc


def in_window(version: str, window: str) -> bool | None:
    """Whether ``version`` satisfies ``window`` (comma-separated ``>=``, ``<``, ``<=``, ``>``,
    ``==`` clauses over ``X.Y.Z[rcN]``); None when ``version`` does not parse. A malformed
    ``window`` is a ``ValueError`` (a bug in the adapter, not in the environment)."""
    clauses = []
    for raw in window.split(","):
        match = _CLAUSE.fullmatch(raw.strip())
        bound = _parse(match.group(2)) if match else None
        if match is None or bound is None:
            raise ValueError(f"unsupported version window clause {raw!r}")
        clauses.append((match.group(1), bound))
    found = _parse(version)
    if found is None:
        return None
    compare = {
        ">=": found.__ge__,
        "<=": found.__le__,
        "==": found.__eq__,
        ">": found.__gt__,
        "<": found.__lt__,
    }
    return all(compare[op](bound) for op, bound in clauses)


def boundary_found() -> bool:
    """Whether the boundary module is found in this interpreter, without importing it."""
    try:
        return importlib.util.find_spec(BOUNDARY_MODULE) is not None
    except (ImportError, ValueError):
        return False


def _boundary_check(found: bool, where: str) -> Check:
    if found:
        return _check("boundary", True, f"{BOUNDARY_MODULE} found with {where} (not imported)")
    return _check(
        "boundary",
        False,
        f"{BOUNDARY_MODULE}, the public boundary the adapter drives, is not "
        f"importable with {where}; reinstall forge-doctor-data "
        f"{SUPPORTED_SPECIALIST} in this interpreter",
    )


def _live_environment() -> tuple[list[Check], str | None]:
    """(python and import checks, installed Forge Doctor Data version)."""
    running = f"{sys.version_info[0]}.{sys.version_info[1]}"
    if (sys.version_info[0], sys.version_info[1]) < REQUIRED_PYTHON:
        return [
            _check(
                "python",
                False,
                f"Forge Doctor Data requires Python {REQUIRED}; "
                f"this adapter runs on {running} at "
                f"{sys.executable}",
            )
        ], None
    checks = [_check("python", True, f"Python {running} at {sys.executable}")]
    version: object = None
    if importlib.util.find_spec("forge_doctor_data") is not None:
        try:
            version = getattr(importlib.import_module("forge_doctor_data"), "__version__", None)
        except Exception:  # an installed but broken package is not importable
            version = None
    if not isinstance(version, str):
        checks.append(
            _check(
                "import",
                False,
                f"forge_doctor_data is not importable with {sys.executable} "
                f"(Python {running}); install forge-doctor-data "
                f"{SUPPORTED_SPECIALIST} in this interpreter",
            )
        )
        return checks, None
    checks.append(_check("import", True, f"forge_doctor_data {version} importable"))
    return checks, version


def _replay_environment(environment: Mapping[str, Any]) -> tuple[list[Check], str | None]:
    python = environment["python"]
    parts = python.split(".")[:2]
    try:
        parsed = (int(parts[0]), int(parts[1])) >= REQUIRED_PYTHON
    except (ValueError, IndexError):
        parsed = False
    if not parsed:
        return [
            _check(
                "python",
                False,
                f"Forge Doctor Data requires Python {REQUIRED}; the replay "
                f"environment ({ENVIRONMENT_FILE}) records Python {python}",
            )
        ], None
    checks = [_check("python", True, f"Python {python} (replay {ENVIRONMENT_FILE})")]
    version = environment.get("specialist_version")
    if version is None:
        checks.append(
            _check(
                "import",
                False,
                f"forge_doctor_data is not importable in the replay "
                f"environment ({ENVIRONMENT_FILE}, Python {python}); install "
                f"forge-doctor-data {SUPPORTED_SPECIALIST}",
            )
        )
        return checks, None
    checks.append(
        _check("import", True, f"forge_doctor_data {version} (replay {ENVIRONMENT_FILE})")
    )
    return checks, version


def _version_check(found: str, assumed: bool) -> Check:
    source = " (version assumed by --assume-specialist-version)" if assumed else ""
    if in_window(found, SUPPORTED_SPECIALIST):
        return _check("version", True, f"found {found}, within {SUPPORTED_SPECIALIST}{source}")
    return _check("version", False, f"found {found}, supported {SUPPORTED_SPECIALIST}{source}")


def _report(status: str, checks: Sequence[Check]) -> Reply:
    return Reply(status="ok", payload={"status": status, "checks": list(checks)})


def health_reply(options: AdapterOptions) -> Reply:
    """The ``health`` reply: a ``HealthReport`` payload, or an error for a bad replay. Never
    runs a native process."""
    try:
        if options.replay is None:
            checks, version = _live_environment()
        else:
            checks, version = _replay_environment(read_environment(options.replay))
        if version is None:
            return _report("unavailable", checks)
        if options.replay is None:
            boundary = _boundary_check(boundary_found(), f"{sys.executable}")
        else:
            boundary = _boundary_check(
                bool(read_health(options.replay)["boundary"]),
                f"the replay interpreter ({HEALTH_FILE})",
            )
    except ReplayError as exc:
        return fail(exc.code, exc.detail, field="replay")
    assumed = options.assume_specialist_version
    version_check = _version_check(assumed or version, assumed is not None)
    status = "ok" if version_check["ok"] else "degraded"
    if not boundary["ok"]:
        status = "unavailable"
    return _report(status, [*checks, version_check, boundary])
