"""``health`` without network, without credentials and without running the API Forge.

Four local checks, in order: (1) the interpreter is Python 3.12; (2) ``apiforge`` is
importable; (3) the API Forge version (``apiforge.__version__``, or
``--assume-specialist-version``) is inside ``SUPPORTED_SPECIALIST``; (4) ``cli``: the CLI entry
point the adapter runs (``apiforge.cli``) is found with ``find_spec``, never imported.
(1)/(2) failing make the report ``unavailable`` and stop there; (3) out of the window makes it
``degraded`` with the version and the window; (4) missing makes it ``unavailable``. The worst
outcome wins.

The native ``apiforge doctor`` is deliberately not run: it sits behind the full CLI import
(about 440 modules and 270 pydantic models, 3 to 17 s measured, against the core's 10 s health
budget), while its own probes (writable state root, packaged assets, ``git``/``apiforge-mcp`` on
PATH, network mode) answer nothing the adapter depends on in a fresh temporary directory. A
broken CLI dependency therefore surfaces in ``execute`` (native error, with the doctor as the
unlock), not in ``health``.

With ``--replay <dir>`` the specialist is never consulted: (1)-(3) read ``environment.json``
and (4) the scenario's ``health.json`` (``{provenance, cli}``).
"""

from __future__ import annotations

import importlib
import importlib.util
import re
import sys
from collections.abc import Mapping, Sequence
from typing import Any

from theforge_apiforge import REQUIRED_PYTHON, SUPPORTED_SPECIALIST
from theforge_apiforge._shell import AdapterOptions, Reply, fail
from theforge_apiforge.backend import (
    ENVIRONMENT_FILE,
    HEALTH_FILE,
    REQUIRED,
    ReplayError,
    read_environment,
    read_health,
)

# The CLI entry point the adapter runs in a child process (``execute``).
CLI_MODULE = "apiforge.cli"
CLI = f"from {CLI_MODULE} import app; app()"
_VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", re.ASCII)
_CLAUSE = re.compile(r"(>=|<=|==|>|<)\s*(\S+)")

Check = dict[str, Any]


def _check(name: str, ok: bool, detail: str) -> Check:
    return {"name": name, "ok": ok, "detail": detail}


def _parse(version: str) -> tuple[int, int, int] | None:
    match = _VERSION.fullmatch(version)
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def in_window(version: str, window: str) -> bool | None:
    """Whether ``version`` (``X.Y.Z``) satisfies ``window`` (comma-separated ``>=``, ``<``,
    ``<=``, ``>``, ``==`` clauses); None when ``version`` is not ``X.Y.Z``. A malformed
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


def cli_found() -> bool:
    """Whether ``apiforge.cli`` is found in this interpreter, without importing it (its import
    pulls in the whole API Forge and costs seconds)."""
    try:
        return importlib.util.find_spec(CLI_MODULE) is not None
    except (ImportError, ValueError):
        return False


def _cli_check(found: bool, where: str) -> Check:
    if found:
        return _check(
            "cli",
            True,
            f"{CLI_MODULE} found with {where} (not imported; the native doctor is not run)",
        )
    return _check(
        "cli",
        False,
        f"{CLI_MODULE}, the CLI entry point the adapter runs, is not "
        f"importable with {where}; reinstall apiforge "
        f"{SUPPORTED_SPECIALIST} in this interpreter",
    )


def _live_environment() -> tuple[list[Check], str | None]:
    """(python and import checks, installed API Forge version)."""
    running = f"{sys.version_info[0]}.{sys.version_info[1]}"
    if (sys.version_info[0], sys.version_info[1]) != REQUIRED_PYTHON:
        return [
            _check(
                "python",
                False,
                f"API Forge requires Python {REQUIRED}; this adapter "
                f"runs on {running} at {sys.executable}",
            )
        ], None
    checks = [_check("python", True, f"Python {running} at {sys.executable}")]
    version: object = None
    if importlib.util.find_spec("apiforge") is not None:
        try:
            version = getattr(importlib.import_module("apiforge"), "__version__", None)
        except Exception:  # an installed but broken package is not importable
            version = None
    if not isinstance(version, str):
        checks.append(
            _check(
                "import",
                False,
                f"apiforge is not importable with {sys.executable} (Python "
                f"{running}); install apiforge {SUPPORTED_SPECIALIST} in this "
                "interpreter",
            )
        )
        return checks, None
    checks.append(_check("import", True, f"apiforge {version} importable"))
    return checks, version


def _replay_environment(environment: Mapping[str, Any]) -> tuple[list[Check], str | None]:
    python = environment["python"]
    if ".".join(python.split(".")[:2]) != REQUIRED:
        return [
            _check(
                "python",
                False,
                f"API Forge requires Python {REQUIRED}; the replay environment "
                f"({ENVIRONMENT_FILE}) records Python {python}",
            )
        ], None
    checks = [_check("python", True, f"Python {python} (replay {ENVIRONMENT_FILE})")]
    version = environment.get("specialist_version")
    if version is None:
        checks.append(
            _check(
                "import",
                False,
                f"apiforge is not importable in the replay environment "
                f"({ENVIRONMENT_FILE}, Python {python}); install apiforge "
                f"{SUPPORTED_SPECIALIST}",
            )
        )
        return checks, None
    checks.append(_check("import", True, f"apiforge {version} (replay {ENVIRONMENT_FILE})"))
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
            cli = _cli_check(cli_found(), f"{sys.executable}")
        else:
            cli = _cli_check(
                bool(read_health(options.replay)["cli"]), f"the replay interpreter ({HEALTH_FILE})"
            )
    except ReplayError as exc:
        return fail(exc.code, exc.detail, field="replay")
    assumed = options.assume_specialist_version
    version_check = _version_check(assumed or version, assumed is not None)
    status = "ok" if version_check["ok"] else "degraded"
    if not cli["ok"]:
        status = "unavailable"
    return _report(status, [*checks, version_check, cli])
