"""Native boundary of the Spark Forge AWS adapter: the replay layout (``--replay <dir>``).

A replay directory is one complete scenario: ``environment.json`` (``{python,
specialist_version}``, which replaces the interpreter and import checks of describe and
health), ``health.json`` (``{dispatcher, specialist_version}``: the native probes of health)
and the execute recordings ``<capability>.<action>.json`` (native
output) or ``<capability>.<action>.error.json`` (native error). When both recordings exist for
an action, the error recording wins. ``tests/fixtures/native/sparkforge_aws/default/`` is the
healthy scenario used by the offline conformance; every other outcome lives in
``tests/fixtures/native/sparkforge_aws/scenarios/<name>/``. In replay the specialist is never
called and no result is invented.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from theforge_sparkforge_aws import native_pkg

ENVIRONMENT_FILE = "environment.json"
HEALTH_FILE = "health.json"
REPLAY_MISSING = "ADAPTER-REPLAY-MISSING"
REPLAY_INVALID = "ADAPTER-REPLAY-INVALID"
MIN_PYTHON = (3, 10)
INSTALL_HINT = "install sparkforge-aws >=0.5,<0.6"
_PYTHON_VERSION = re.compile(r"(\d+)\.(\d+)(?:\.\d+)?")


def live_unavailable_reason() -> str | None:
    """Why the Spark Forge AWS cannot be used from this interpreter, or None if importable.

    Uses ``find_spec`` only, via the shared resolver (``sparkforge_aws`` after the
    rename, ``sparkforge`` before it): nothing of the Spark Forge AWS is imported.
    """
    if native_pkg.dispatcher_found():
        return None
    version = f"{sys.version_info.major}.{sys.version_info.minor}"
    return (f"sparkforge-aws is not importable with {sys.executable} (Python {version}); "
            f"{INSTALL_HINT} in this interpreter")


@dataclass(frozen=True)
class Environment:
    """The recorded interpreter: Python version and Spark Forge AWS version (None: absent)."""

    python: str
    specialist_version: str | None

    def unavailable_reason(self) -> str | None:
        """Why the recorded interpreter cannot run the Spark Forge AWS, or None."""
        match = _PYTHON_VERSION.fullmatch(self.python)
        if match is None or (int(match[1]), int(match[2])) < MIN_PYTHON:
            return (f"recorded interpreter runs Python {self.python}; the Spark Forge AWS needs "
                    f"Python >= {MIN_PYTHON[0]}.{MIN_PYTHON[1]}")
        if self.specialist_version is None:
            return (f"sparkforge-aws is not importable with the recorded interpreter "
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
class HealthRecording:
    """The native probes of health recorded in ``health.json``: whether a dispatcher
    (``sparkforge_aws.adapters.tools``, or pre-rename ``sparkforge.adapters.tools``) was
    found and the Spark Forge AWS version read (None: none).

    An optional ``provenance`` string marks a recording derived by hand from a real one.
    """

    dispatcher: bool
    specialist_version: str | None


_HEALTH_KEYS = {"dispatcher", "specialist_version"}


def load_health(replay: Path) -> HealthRecording | ReplayProblem:
    """The ``health.json`` of a replay directory, or why it cannot be used."""
    path = replay / HEALTH_FILE
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return ReplayProblem(REPLAY_MISSING,
                             f"replay recording {HEALTH_FILE} not found in {replay}")
    try:
        data = json.loads(raw)
    except ValueError:
        return ReplayProblem(REPLAY_INVALID, f"{HEALTH_FILE} is not valid JSON")
    if (not isinstance(data, dict) or not set(data) >= _HEALTH_KEYS
            or not set(data) <= _HEALTH_KEYS | {"provenance"}):
        return ReplayProblem(REPLAY_INVALID,
                             f"{HEALTH_FILE} must hold dispatcher and specialist_version "
                             "(and optionally provenance)")
    dispatcher, version = data["dispatcher"], data["specialist_version"]
    if (not isinstance(dispatcher, bool) or not (version is None or isinstance(version, str))
            or not isinstance(data.get("provenance", ""), str)):
        return ReplayProblem(REPLAY_INVALID,
                             f"{HEALTH_FILE}: dispatcher must be a boolean, specialist_version "
                             "a string or null and provenance a string")
    return HealthRecording(dispatcher=dispatcher, specialist_version=version)


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
