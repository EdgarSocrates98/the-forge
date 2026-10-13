"""The native boundary: the live interpreter checks and the replay scenario that replaces them.

Live, Forge Doctor API must run in this same interpreter, which must be Python >= 3.11 with
``forge_doctor_api`` importable. With ``--replay <dir>`` the specialist is never consulted:
the interpreter and importability checks read the scenario's ``environment.json``
(``{python, specialist_version}``), so a replay runs on any Python >= 3.10 without the
Doctor installed.

Replay layout (one complete scenario per directory): ``tests/fixtures/native/doctorapi/
default/`` is the healthy scenario and every other outcome lives in ``scenarios/<name>/``.
A scenario holds ``environment.json``, ``health.json`` and, per executed action,
``<capability>.<action>.json`` (bridge document) or ``<capability>.<action>.error.json``
(native failure); when both exist the error recording prevails.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from theforge_doctorapi import REQUIRED_PYTHON, SUPPORTED_SPECIALIST

UNAVAILABLE = "DOCTORAPI-ADAPTER-UNAVAILABLE"
REPLAY_MISSING = "ADAPTER-REPLAY-MISSING"
REPLAY_INVALID = "ADAPTER-REPLAY-INVALID"
ENVIRONMENT_FILE = "environment.json"
HEALTH_FILE = "health.json"
SPECIALIST_MODULE = "forge_doctor_api"
REQUIRED = f"{REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]}+"
UNLOCK = (
    f"run the adapter with a Python {REQUIRED} interpreter that has "
    f"forge-doctor-api {SUPPORTED_SPECIALIST} installed (see docs/real-providers.md)"
)

FindSpec = Callable[[str], object]


class ReplayError(Exception):
    """A replay scenario file is missing (``REPLAY_MISSING``) or malformed."""

    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def live_environment_problem(
    version_info: Sequence[int] | None = None,
    executable: str | None = None,
    find_spec: FindSpec | None = None,
) -> str | None:
    """Why Forge Doctor API cannot run in this interpreter, or None when it can."""
    running = (
        (sys.version_info[0], sys.version_info[1])
        if version_info is None
        else (version_info[0], version_info[1])
    )
    executable = sys.executable if executable is None else executable
    find_spec = importlib.util.find_spec if find_spec is None else find_spec
    found = f"{running[0]}.{running[1]}"
    if running < REQUIRED_PYTHON:
        return (
            f"Forge Doctor API requires Python {REQUIRED}; this adapter runs on "
            f"{found} at {executable}"
        )
    if find_spec(SPECIALIST_MODULE) is None:
        return (
            f"{SPECIALIST_MODULE} is not importable with {executable} (Python {found}); "
            f"install forge-doctor-api {SUPPORTED_SPECIALIST} in this interpreter"
        )
    return None


def read_environment(directory: Path) -> dict[str, Any]:
    """The scenario's ``environment.json``; ``ReplayError`` when absent or malformed."""
    path = directory / ENVIRONMENT_FILE
    if not path.is_file():
        raise ReplayError(
            REPLAY_MISSING, f"replay recording {ENVIRONMENT_FILE} not found in {directory}"
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        data = None
    if (
        not isinstance(data, dict)
        or not isinstance(data.get("python"), str)
        or not (
            data.get("specialist_version") is None
            or isinstance(data.get("specialist_version"), str)
        )
    ):
        raise ReplayError(
            REPLAY_INVALID,
            f"replay recording {ENVIRONMENT_FILE} in {directory} must be an "
            "object with a string 'python' and a string or null "
            "'specialist_version'",
        )
    return data


def read_health(directory: Path) -> dict[str, Any]:
    """The scenario's ``health.json``: ``{boundary: <bool>}`` (plus ``provenance``), whether
    the boundary module the adapter drives was found in the recorded interpreter;
    ``ReplayError`` when absent or malformed."""
    path = directory / HEALTH_FILE
    if not path.is_file():
        raise ReplayError(
            REPLAY_MISSING, f"replay recording {HEALTH_FILE} not found in {directory}"
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, RecursionError):
        data = None
    if not isinstance(data, dict) or type(data.get("boundary")) is not bool:
        raise ReplayError(
            REPLAY_INVALID,
            f"replay recording {HEALTH_FILE} in {directory} must be an object "
            "with a boolean 'boundary' (whether the boundary module was "
            "found)",
        )
    return data


def _at_least(python: str) -> bool:
    parts = python.split(".")[:2]
    try:
        version = (int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        return False
    return version >= REQUIRED_PYTHON


def replay_environment_problem(environment: dict[str, Any]) -> str | None:
    """The live checks, answered from a recorded ``environment.json``."""
    python = environment["python"]
    if not _at_least(python):
        return (
            f"Forge Doctor API requires Python {REQUIRED}; the replay environment "
            f"({ENVIRONMENT_FILE}) records Python {python}"
        )
    if environment.get("specialist_version") is None:
        return (
            f"{SPECIALIST_MODULE} is not importable in the replay environment "
            f"({ENVIRONMENT_FILE}, Python {python}); install forge-doctor-api "
            f"{SUPPORTED_SPECIALIST}"
        )
    return None


class ReplayBackend:
    """Recorded native outputs of one replay scenario."""

    def __init__(self, directory: Path):
        self.directory = directory

    def expected(self, capability: str, action: str) -> str:
        """The native-output recording an action needs (named in ``ADAPTER-REPLAY-MISSING``)."""
        return f"{capability}.{action}.json"

    def recording(self, capability: str, action: str) -> tuple[str, Path] | None:
        """``("error", path)`` or ``("native", path)``; the error recording prevails."""
        error = self.directory / f"{capability}.{action}.error.json"
        if error.is_file():
            return "error", error
        native = self.directory / self.expected(capability, action)
        if native.is_file():
            return "native", native
        return None
