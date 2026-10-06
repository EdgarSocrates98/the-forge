"""Environment contract of the real-Forge integration tests (``THEFORGE_REAL_*``).

Only this test harness reads the variables below, to build the ``argv`` registered in the
isolated user ``providers.toml`` of a test. They never reach a provider: the entry carries only
``id``/``argv``/``trust`` and the core's environment allowlist is unchanged. The variables are
``THEFORGE_REAL_{SPARKFORGE,APIFORGE,DOCTORDATA,DOCTORAPI}_PYTHON``.

Per Forge, in this order, each with an explicit reason: the variable is set, it names an
existing interpreter (absolute path), and ``<python> -c "import <adapter>, <specialist>"``
exits 0 within ``IMPORT_TIMEOUT``. A missing prerequisite skips the Forge's integration tests,
unless ``THEFORGE_REAL_PROVIDERS_REQUIRED=1``, in which case it fails them.
See ``docs/real-providers.md``.
"""

import json
import os
import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from theforge.security.env import safe_env

SPARK_PYTHON_VAR = "THEFORGE_REAL_SPARKFORGE_PYTHON"
API_PYTHON_VAR = "THEFORGE_REAL_APIFORGE_PYTHON"
DOCTORDATA_PYTHON_VAR = "THEFORGE_REAL_DOCTORDATA_PYTHON"
DOCTORAPI_PYTHON_VAR = "THEFORGE_REAL_DOCTORAPI_PYTHON"
REQUIRED_VAR = "THEFORGE_REAL_PROVIDERS_REQUIRED"
IMPORT_TIMEOUT = 60.0
DOC = "docs/real-providers.md"
# python, python3, python3.12, python.exe, python3.12.exe (case-insensitive).
_INTERPRETER_NAME = re.compile(r"python(3(\.\d+)?)?(\.exe)?", re.IGNORECASE)

# probe(python, modules) -> None when ``import <modules>`` works, else the failure reason.
ImportProbe = Callable[[Path, Sequence[str]], "str | None"]


@dataclass(frozen=True)
class ForgeSpec:
    name: str
    label: str
    provider_id: str
    variable: str
    adapter_module: str
    specialist_module: str
    needs: str
    # The adapter's unavailability code; default derived from the provider id.
    unavailable_code: str = ""
    # Other module names the same specialist answers to (the upstream
    # sparkforge -> sparkforge_aws rename kept the 0.5.x line: an install may
    # expose either name, and both are valid).
    specialist_alternatives: tuple[str, ...] = ()


FORGES: dict[str, ForgeSpec] = {
    "spark": ForgeSpec("spark", "Spark Forge", "spark-forge", SPARK_PYTHON_VAR,
                       "theforge_sparkforge", "sparkforge_aws.adapters.tools",
                       "Spark Forge needs an interpreter with sparkforge-aws and "
                       "theforge-sparkforge-adapter",
                       specialist_alternatives=("sparkforge.adapters.tools",)),
    "api": ForgeSpec("api", "API Forge", "api-forge", API_PYTHON_VAR,
                     "theforge_apiforge", "apiforge",
                     "API Forge needs Python 3.12"),
    "doctordata": ForgeSpec("doctordata", "Forge Doctor Data", "forge-doctor-data",
                            DOCTORDATA_PYTHON_VAR, "theforge_doctordata",
                            "forge_doctor_data",
                            "Forge Doctor Data needs an interpreter with "
                            "forge-doctor-data and theforge-doctordata-adapter",
                            "DOCTORDATA-ADAPTER-UNAVAILABLE"),
    "doctorapi": ForgeSpec("doctorapi", "Forge Doctor API", "forge-doctor-api",
                           DOCTORAPI_PYTHON_VAR, "theforge_doctorapi",
                           "forge_doctor_api",
                           "Forge Doctor API needs an interpreter with "
                           "forge-doctor-api and theforge-doctorapi-adapter",
                           "DOCTORAPI-ADAPTER-UNAVAILABLE"),
}


@dataclass(frozen=True)
class RealForge:
    provider_id: str
    python: Path
    adapter_module: str
    specialist_module: str

    def argv(self, *options: str) -> list[str]:
        return [str(self.python), "-m", self.adapter_module, *options]

    def entry(self, *options: str, trust: str = "trusted") -> dict[str, Any]:
        """A user ``providers.toml`` entry: ``id``/``argv``/``trust`` only, never an env."""
        return {"id": self.provider_id, "argv": self.argv(*options), "trust": trust}


class ForgeUnavailable(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def missing_variable_reason(name: str) -> str:
    spec = FORGES[name]
    return f"{spec.variable} not set ({spec.needs}; see {DOC})"


def probe_imports(python: Path, modules: Sequence[str], *,
                  run: Callable[..., Any] = subprocess.run,
                  timeout: float = IMPORT_TIMEOUT) -> str | None:
    """Run ``import <modules>`` in ``python`` with the core's credential-free environment."""
    statement = f"import {', '.join(modules)}"
    try:
        proc = run([str(python), "-c", statement], capture_output=True, text=True,
                   timeout=timeout, env=safe_env(), stdin=subprocess.DEVNULL, check=False)
    except subprocess.TimeoutExpired:
        return f"`{statement}` did not finish in {timeout:g} s"
    except OSError as exc:
        return f"`{statement}` could not start: {exc}"
    if proc.returncode == 0:
        return None
    lines = [line.strip() for line in (proc.stderr or "").splitlines() if line.strip()]
    detail = f": {lines[-1]}" if lines else ""
    return f"`{statement}` exited {proc.returncode}{detail}"


def validate_interpreter(variable: str, value: str) -> Path:
    """The interpreter named by ``variable=value``, normalized once, or ``ForgeUnavailable``.

    Lexical normalization only (no ``resolve``): a POSIX venv's ``bin/python`` is a symlink to
    the base interpreter, and following it would drop the venv's site-packages.
    """
    python = Path(value).expanduser()
    if not python.is_absolute():
        raise ForgeUnavailable(
            f"{variable}={value} is not an absolute path to an interpreter (see {DOC})")
    python = Path(os.path.normpath(python))
    if not _INTERPRETER_NAME.fullmatch(python.name):
        raise ForgeUnavailable(
            f"{variable}={value} does not name a Python interpreter "
            f"(expected python, python3, python3.x, optionally .exe; see {DOC})")
    if not python.exists():
        raise ForgeUnavailable(f"{variable}={value} does not exist (see {DOC})")
    if not python.is_file():
        raise ForgeUnavailable(f"{variable}={value} is not a file (see {DOC})")
    return python


def check_forge(name: str, environ: Mapping[str, str] | None = None, *,
                probe: ImportProbe = probe_imports) -> RealForge:
    """The configured real Forge ``name``, or ``ForgeUnavailable`` with the first failed check."""
    spec = FORGES[name]
    env = os.environ if environ is None else environ
    value = env.get(spec.variable, "").strip()
    if not value:
        raise ForgeUnavailable(missing_variable_reason(name))
    python = validate_interpreter(spec.variable, value)
    names = (spec.specialist_module, *spec.specialist_alternatives)
    failure: str | None = None
    for module in names:
        failure = probe(python, (spec.adapter_module, module))
        if failure is None:
            break
    if failure is not None:
        raise ForgeUnavailable(
            f"{spec.label} not importable with {python}: {failure} "
            f"(set {spec.variable} to an interpreter with both installed; see {DOC})")
    return RealForge(spec.provider_id, python, spec.adapter_module, spec.specialist_module)


def is_required(environ: Mapping[str, str] | None = None) -> bool:
    env = os.environ if environ is None else environ
    return env.get(REQUIRED_VAR, "").strip() == "1"


def require_forge(name: str, environ: Mapping[str, str] | None = None, *,
                  probe: ImportProbe = probe_imports) -> RealForge:
    """``check_forge`` for a test: skip with the reason, or fail it in required mode."""
    try:
        return check_forge(name, environ, probe=probe)
    except ForgeUnavailable as exc:
        if is_required(environ):
            pytest.fail(f"{REQUIRED_VAR}=1: {exc.reason}", pytrace=False)
        pytest.skip(exc.reason)


def register(config_dir: Path, *entries: dict[str, Any]) -> list[dict[str, Any]]:
    """Write ``entries`` as the user ``providers.toml`` in the test's isolated ``config_dir``.

    Each entry is ``id``/``argv``/``trust`` only: nothing of this contract reaches a provider.
    """
    listed = [{"id": e["id"], "argv": list(e["argv"]), "trust": e.get("trust", "trusted")}
              for e in entries]
    lines: list[str] = []
    for entry in listed:
        lines += ["[[providers]]", f"id = {json.dumps(entry['id'])}",
                  f"argv = {json.dumps(entry['argv'])}", f"trust = {json.dumps(entry['trust'])}",
                  ""]
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "providers.toml").write_text("\n".join(lines), encoding="utf-8")
    return listed


# --- shared helpers of the real-provider tests (drift checks and native calls) -------------

NATIVE_TIMEOUT = 300.0
_HEX_TAIL = re.compile(r"(?P<prefix>.*?)(?P<hex>[0-9a-f]{6,})")
ID_KEYS = {"id", "fact_id", "finding_id", "case_id"}


def run_native(argv: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """A command in a specialist interpreter with the core's credential-free environment."""
    proc = subprocess.run(argv, cwd=cwd, env=safe_env(), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=NATIVE_TIMEOUT,
                          stdin=subprocess.DEVNULL, check=False)
    assert proc.returncode == 0, (argv, proc.stdout, proc.stderr)
    return proc


def left_in(directory: Path) -> set[str]:
    """The relative POSIX paths of everything left inside ``directory``."""
    return {path.relative_to(directory).as_posix() for path in directory.rglob("*")}


def id_shape(value: str) -> str:
    """The format of a native id: its prefix and the length of its hex tail
    (``f_2d3af1`` -> ``f_<hex6>``, ``fact:4019d1fcb4d4726e`` -> ``fact:<hex16>``)."""
    match = _HEX_TAIL.fullmatch(value)
    if match is None:
        return re.sub(r"\d", "9", value)
    return f"{match['prefix']}<hex{len(match['hex'])}>"


def id_shapes(document: Any) -> set[str]:
    """``key=shape`` of every native id in ``document`` (id fields and evidence references)."""
    shapes: set[str] = set()
    if isinstance(document, dict):
        for key, value in document.items():
            if key in ID_KEYS and isinstance(value, str):
                shapes.add(f"{key}={id_shape(value)}")
            elif key == "evidence" and isinstance(value, list):
                shapes |= {f"evidence={id_shape(v)}" for v in value if isinstance(v, str)}
            else:
                shapes |= id_shapes(value)
    elif isinstance(document, list):
        for item in document:
            shapes |= id_shapes(item)
    return shapes


def top_keys(document: Any) -> list[str]:
    """The sorted top-level keys of a JSON object (or its type name when it is not one)."""
    return sorted(document) if isinstance(document, dict) else [type(document).__name__]
