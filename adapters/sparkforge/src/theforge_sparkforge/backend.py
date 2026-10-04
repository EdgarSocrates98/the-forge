"""Native boundary of the Spark Forge adapter: the replay layout (``--replay <dir>``).

A replay directory is one complete scenario: ``environment.json`` (``{python,
specialist_version}``, which replaces the interpreter and import checks of describe and
health), ``health.json`` and the execute recordings ``<capability>.<action>.json`` (native
output) or ``<capability>.<action>.error.json`` (native error). When both recordings exist for
an action, the error recording wins. ``tests/fixtures/native/sparkforge/default/`` is the
healthy scenario used by the offline conformance; every other outcome lives in
``tests/fixtures/native/sparkforge/scenarios/<name>/``. In replay the specialist is never
called and no result is invented.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ENVIRONMENT_FILE = "environment.json"
HEALTH_FILE = "health.json"
REPLAY_MISSING = "ADAPTER-REPLAY-MISSING"
REPLAY_INVALID = "ADAPTER-REPLAY-INVALID"
MIN_PYTHON = (3, 10)
INSTALL_HINT = "install sparkforge-aws >=0.5,<0.6"
_PYTHON_VERSION = re.compile(r"(\d+)\.(\d+)(?:\.\d+)?")


def live_unavailable_reason() -> str | None:
    """Why the Spark Forge cannot be used from this interpreter, or None if importable.

    Uses ``find_spec`` only: nothing of the Spark Forge is imported.
    """
    try:
        found = importlib.util.find_spec("sparkforge") is not None
    except (ImportError, ValueError):
        found = False
    if found:
        return None
    version = f"{sys.version_info.major}.{sys.version_info.minor}"
    return (f"sparkforge is not importable with {sys.executable} (Python {version}); "
            f"{INSTALL_HINT} in this interpreter")


@dataclass(frozen=True)
class Environment:
    """The recorded interpreter: Python version and Spark Forge version (None: absent)."""

    python: str
    specialist_version: str | None

    def unavailable_reason(self) -> str | None:
        """Why the recorded interpreter cannot run the Spark Forge, or None."""
        match = _PYTHON_VERSION.fullmatch(self.python)
        if match is None or (int(match[1]), int(match[2])) < MIN_PYTHON:
            return (f"recorded interpreter runs Python {self.python}; the Spark Forge needs "
                    f"Python >= {MIN_PYTHON[0]}.{MIN_PYTHON[1]}")
        if self.specialist_version is None:
            return (f"sparkforge is not importable with the recorded interpreter "
                    f"(Python {self.python}); {INSTALL_HINT} in it")
        return None


@dataclass(frozen=True)
class ReplayProblem:
    """A replay directory that cannot answer: (code, detail)."""

    code: str
    detail: str


def load_environment(replay: Path) -> Environment | ReplayProblem:
    """The ``environment.json`` of a replay directory, or why it cannot be used."""
    path = replay / ENVIRONMENT_FILE
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return ReplayProblem(REPLAY_MISSING,
                             f"replay recording {ENVIRONMENT_FILE} not found in {replay}")
    try:
        data = json.loads(raw)
    except ValueError:
        return ReplayProblem(REPLAY_INVALID, f"{ENVIRONMENT_FILE} is not valid JSON")
    if not isinstance(data, dict) or set(data) != {"python", "specialist_version"}:
        return ReplayProblem(REPLAY_INVALID,
                             f"{ENVIRONMENT_FILE} must hold exactly python and "
                             "specialist_version")
    python, version = data["python"], data["specialist_version"]
    if not isinstance(python, str) or not (version is None or isinstance(version, str)):
        return ReplayProblem(REPLAY_INVALID,
                             f"{ENVIRONMENT_FILE}: python must be a string and "
                             "specialist_version a string or null")
    return Environment(python=python, specialist_version=version)


@dataclass(frozen=True)
class Recording:
    """The execute recording of an action: native ``output`` or native ``error``."""

    kind: str
    path: Path


def expected_recording(capability: str, action: str) -> str:
    """File name of the native output recording of ``capability``/``action``."""
    return f"{capability}.{action}.json"


def recording(replay: Path, capability: str, action: str) -> Recording | None:
    """The recording to replay for an action (the error one wins), or None when absent."""
    error = replay / f"{capability}.{action}.error.json"
    if error.is_file():
        return Recording(kind="error", path=error)
    output = replay / expected_recording(capability, action)
    if output.is_file():
        return Recording(kind="output", path=output)
    return None
