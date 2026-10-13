"""The native boundary: the live interpreter checks and the replay scenario that replaces them.

Live, the API Forge must run in this same interpreter, which must be Python 3.12 with
``apiforge`` importable. With ``--replay <dir>`` the specialist is never consulted: the
interpreter and importability checks read the scenario's ``environment.json``
(``{python, specialist_version}``), so a replay runs on any Python >= 3.10 without the API
Forge installed.

Replay layout (one complete scenario per directory): ``tests/fixtures/native/apiforge/
default/`` is the healthy scenario and every other outcome lives in ``scenarios/<name>/``.
A scenario holds ``environment.json``, ``health.json`` and, per executed action,
``<capability>.<action>.json`` (native output) or ``<capability>.<action>.error.json`` (native
failure); when both exist the error recording prevails.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from theforge_apiforge import REQUIRED_PYTHON, SUPPORTED_SPECIALIST

UNAVAILABLE = "APIFORGE-ADAPTER-UNAVAILABLE"
REPLAY_MISSING = "ADAPTER-REPLAY-MISSING"
REPLAY_INVALID = "ADAPTER-REPLAY-INVALID"
ENVIRONMENT_FILE = "environment.json"
HEALTH_FILE = "health.json"
REQUIRED = f"{REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]}"
UNLOCK = (
    f"run the adapter with a Python {REQUIRED} interpreter that has apiforge "
    f"{SUPPORTED_SPECIALIST} installed (see docs/real-providers.md)"
)

FindSpec = Callable[[str], object]


class ReplayError(Exception):
    """A replay scenario file is missing (``REPLAY_MISSING``) or malformed."""

    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _version(parts: Sequence[int]) -> str:
    return ".".join(str(part) for part in parts[:2])


def live_environment_problem(
    version_info: Sequence[int] | None = None,
    executable: str | None = None,
    find_spec: FindSpec | None = None,
) -> str | None:
    """Why the API Forge cannot run in this interpreter, or None when it can."""
    running = (
        (sys.version_info[0], sys.version_info[1])
        if version_info is None
        else (version_info[0], version_info[1])
    )
    executable = sys.executable if executable is None else executable
    find_spec = importlib.util.find_spec if find_spec is None else find_spec
    found = _version(running)
    if running != REQUIRED_PYTHON:
        return f"API Forge requires Python {REQUIRED}; this adapter runs on {found} at {executable}"
    if find_spec("apiforge") is None:
        return (
            f"apiforge is not importable with {executable} (Python {found}); "
            f"install apiforge {SUPPORTED_SPECIALIST} in this interpreter"
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
    """The scenario's ``health.json``: ``{cli: <bool>}`` (plus ``provenance``), whether the
    CLI entry point ``apiforge.cli`` was found in the recorded interpreter; ``ReplayError``
    when absent or malformed."""
    path = directory / HEALTH_FILE
    if not path.is_file():
        raise ReplayError(
            REPLAY_MISSING, f"replay recording {HEALTH_FILE} not found in {directory}"
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, RecursionError):
        data = None
    if not isinstance(data, dict) or type(data.get("cli")) is not bool:
        raise ReplayError(
            REPLAY_INVALID,
            f"replay recording {HEALTH_FILE} in {directory} must be an object "
            "with a boolean 'cli' (whether apiforge.cli was found)",
        )
    return data


def replay_environment_problem(environment: dict[str, Any]) -> str | None:
    """The live checks, answered from a recorded ``environment.json``."""
    python = environment["python"]
    found = ".".join(python.split(".")[:2])
    if found != REQUIRED:
        return (
            f"API Forge requires Python {REQUIRED}; the replay environment "
            f"({ENVIRONMENT_FILE}) records Python {python}"
        )
    if environment.get("specialist_version") is None:
        return (
            f"apiforge is not importable in the replay environment ({ENVIRONMENT_FILE}, "
            f"Python {python}); install apiforge {SUPPORTED_SPECIALIST}"
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
