"""``health`` without network and without credentials.

Four checks, in order: (1) the interpreter is Python 3.12; (2) ``apiforge`` is importable;
(3) the API Forge version (``apiforge.__version__``, or ``--assume-specialist-version``) is
inside ``SUPPORTED_SPECIALIST``; (4) the native ``apiforge doctor`` run in a fresh temporary
directory. (1)/(2) failing make the report ``unavailable`` and stop there; (3) out of the
window makes it ``degraded`` with the version and the window; the doctor state maps as
``ready -> ok``, ``degraded|unresolved -> degraded``, ``blocked -> unavailable``, except that
gaps of doctor capabilities the adapter never uses (``network``: the adapter is offline;
``mcp-stdio``: it runs the CLI) are listed as ignored and never degrade health. The worst
outcome wins.

With ``--replay <dir>`` the specialist is never consulted: (1)-(3) read ``environment.json``
and the doctor outcome is the scenario's ``health.json`` (``{provenance, exit_code, doctor}``
or ``{provenance, exit_code, stderr}``), the same shape ``run_doctor`` produces live.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import re
import shutil
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from theforge_apiforge import REQUIRED_PYTHON, SUPPORTED_SPECIALIST
from theforge_apiforge._shell import (
    AdapterOptions,
    NativeOutcome,
    NativeTimeout,
    Reply,
    fail,
    run_native,
)
from theforge_apiforge.backend import (
    ENVIRONMENT_FILE,
    REQUIRED,
    ReplayError,
    read_environment,
    read_health,
)

DOCTOR_STATES = {"ready": "ok", "degraded": "degraded", "unresolved": "degraded",
                 "blocked": "unavailable"}
# Doctor capabilities this adapter never uses: their gaps are informational, never degrade.
IGNORED_CAPABILITIES = {"network": "adapter is offline", "mcp-stdio": "adapter uses the CLI"}
# The core gives health 10 s in all; the doctor (about 3 s cold) gets most of it.
DOCTOR_TIMEOUT = 7.0
DETAIL_LIMIT = 500
CLI = "from apiforge.cli import app; app()"
_SEVERITY = {"ok": 0, "degraded": 1, "unavailable": 2}
_VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", re.ASCII)
_CLAUSE = re.compile(r"(>=|<=|==|>|<)\s*(\S+)")

Check = dict[str, Any]
Run = Callable[..., NativeOutcome]


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
    compare = {">=": found.__ge__, "<=": found.__le__, "==": found.__eq__,
               ">": found.__gt__, "<": found.__lt__}
    return all(compare[op](bound) for op, bound in clauses)


def _clip(text: str, *, tail: bool = False) -> str:
    if len(text) <= DETAIL_LIMIT:
        return text
    return "..." + text[-DETAIL_LIMIT:] if tail else text[:DETAIL_LIMIT] + "..."


def doctor_check(recording: Mapping[str, Any]) -> tuple[str, Check]:
    """(health status, ``doctor`` check) for a live or replayed doctor outcome."""
    if "timeout" in recording:
        return "degraded", _check("doctor", False,
                                  f"apiforge doctor did not finish within "
                                  f"{recording['timeout']:g} s")
    if recording.get("exit_code") != 0:
        stderr = str(recording.get("stderr") or "").strip()
        return "unavailable", _check(
            "doctor", False,
            _clip(f"apiforge doctor exited {recording.get('exit_code')}: {stderr}", tail=True))
    doctor = recording.get("doctor")
    if not isinstance(doctor, Mapping):
        return "degraded", _check("doctor", False, "apiforge doctor output not understood")
    state = doctor.get("status")
    if state not in DOCTOR_STATES:
        return "degraded", _check("doctor", False,
                                  f"unrecognized doctor status {state!r}")
    gaps = [str(gap) for gap in doctor.get("gaps") or () if str(gap)]
    relevant = [gap for gap in gaps if _gap_capability(gap) not in IGNORED_CAPABILITIES]
    ignored = [name for name in IGNORED_CAPABILITIES
               if any(_gap_capability(gap) == name for gap in gaps)]
    effective = state
    if state == "blocked" and not _blocks(doctor):
        effective = "degraded"  # only ignored capabilities are blocked
    if effective in ("degraded", "unresolved") and ignored and not relevant:
        effective = "ready"  # every gap is about a capability the adapter never uses
    detail = f"doctor status {state}" + (f": {'; '.join(relevant)}" if relevant else "")
    if ignored:
        detail += "; ignored: " + ", ".join(
            f"{name} ({IGNORED_CAPABILITIES[name]})" for name in ignored)
    return DOCTOR_STATES[effective], _check("doctor", effective == "ready", _clip(detail))


def _gap_capability(gap: str) -> str:
    return gap.split(":", 1)[0].strip()


def _blocks(doctor: Mapping[str, Any]) -> bool:
    """Whether a capability the adapter uses is blocked (no capability list: trust the
    doctor's own status)."""
    capabilities = doctor.get("capabilities")
    if not isinstance(capabilities, (list, tuple)):
        return True
    return any(isinstance(item, Mapping) and item.get("state") == "blocked"
               and item.get("capability") not in IGNORED_CAPABILITIES
               for item in capabilities)


def run_doctor(*, run: Run = run_native, timeout: float = DOCTOR_TIMEOUT) -> dict[str, Any]:
    """Run ``apiforge doctor`` in this interpreter, in a fresh temporary directory that is
    removed afterwards, offline, with the cache off and the API Forge user state inside that
    directory. The outcome has the replay ``health.json`` shape."""
    workdir = Path(tempfile.mkdtemp(prefix="theforge-apiforge-doctor-"))
    try:
        env = {"APIFORGE_CACHE": "off", "APIFORGE_NETWORK": "offline",
               "APIFORGE_HOME": str(workdir / ".apiforge")}
        argv = [sys.executable, "-c", CLI, "--output", "json", "doctor"]
        try:
            outcome = run(argv, cwd=workdir, env=env, timeout=timeout)
        except NativeTimeout as exc:
            return {"timeout": exc.timeout}
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    if outcome.returncode != 0:
        return {"exit_code": outcome.returncode,
                "stderr": outcome.stderr.decode("utf-8", "replace")}
    try:
        doctor = json.loads(outcome.stdout.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        doctor = None
    return {"exit_code": 0, "doctor": doctor if isinstance(doctor, dict) else None}


def _live_environment() -> tuple[list[Check], str | None]:
    """(python and import checks, installed API Forge version)."""
    running = f"{sys.version_info[0]}.{sys.version_info[1]}"
    if (sys.version_info[0], sys.version_info[1]) != REQUIRED_PYTHON:
        return [_check("python", False, f"API Forge requires Python {REQUIRED}; this adapter "
                                        f"runs on {running} at {sys.executable}")], None
    checks = [_check("python", True, f"Python {running} at {sys.executable}")]
    version: object = None
    if importlib.util.find_spec("apiforge") is not None:
        try:
            version = getattr(importlib.import_module("apiforge"), "__version__", None)
        except Exception:  # an installed but broken package is not importable
            version = None
    if not isinstance(version, str):
        checks.append(_check("import", False,
                             f"apiforge is not importable with {sys.executable} (Python "
                             f"{running}); install apiforge {SUPPORTED_SPECIALIST} in this "
                             "interpreter"))
        return checks, None
    checks.append(_check("import", True, f"apiforge {version} importable"))
    return checks, version


def _replay_environment(environment: Mapping[str, Any]) -> tuple[list[Check], str | None]:
    python = environment["python"]
    if ".".join(python.split(".")[:2]) != REQUIRED:
        return [_check("python", False,
                       f"API Forge requires Python {REQUIRED}; the replay environment "
                       f"({ENVIRONMENT_FILE}) records Python {python}")], None
    checks = [_check("python", True, f"Python {python} (replay {ENVIRONMENT_FILE})")]
    version = environment.get("specialist_version")
    if version is None:
        checks.append(_check("import", False,
                             f"apiforge is not importable in the replay environment "
                             f"({ENVIRONMENT_FILE}, Python {python}); install apiforge "
                             f"{SUPPORTED_SPECIALIST}"))
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


def health_reply(options: AdapterOptions, *, run: Run = run_native) -> Reply:
    """The ``health`` reply: a ``HealthReport`` payload, or an error for a bad replay."""
    try:
        if options.replay is None:
            checks, version = _live_environment()
        else:
            checks, version = _replay_environment(read_environment(options.replay))
        if version is None:
            return _report("unavailable", checks)
        assumed = options.assume_specialist_version
        version_check = _version_check(assumed or version, assumed is not None)
        recording = (run_doctor(run=run) if options.replay is None
                     else read_health(options.replay))
    except ReplayError as exc:
        return fail(exc.code, exc.detail, field="replay")
    doctor_status, doctor = doctor_check(recording)
    status = "ok" if version_check["ok"] else "degraded"
    if _SEVERITY[doctor_status] > _SEVERITY[status]:
        status = doctor_status
    return _report(status, [*checks, version_check, doctor])
