"""Forge Lab — federated benchmark collector (ADR-0060 option B, spec cyc9-01).

Discovery: each installed forge declares a ``lab`` object in ``forge.json``::

    "lab": {
      "command": ["{python}", "-m", "forge_doctor_api", "lab",
                  "--mode", "{mode}", "--result-out", "{receipt}"],
      "receipt": ".forge/lab-result.json",
      "modes": ["A"],
      "suite": "doctor-api-core",
      "timeout_s": 600
    }

``lab: false`` is the honest "no lab" declaration; absence is
``undeclared``. The collector never invents a lab and never evaluates
domain metrics — it invokes the declared argv with §9.11 guardrails,
validates the emitted ``forge/BenchmarkResult/v1`` receipt and writes
the federated report under ``docs/programs/ecosystem-2026/benchmarks/``.

Guardrails (prompt §9.11): argv allowlist (declared template only, never
a shell), per-lab timeout (default 600 s, hard cap 3600), repeats cap 10,
receipt path confined inside the checkout, sanitized environment (no
credentials propagate), output redacted+truncated, mode C refuses without
``--allow-external`` and marks the receipt ``external``, sequential or
bounded-parallel execution, safe interrupt with partial honest report.

Interpreter resolution (cyc11.2 P1-005): the ``{python}`` template binds
to the specialist's interpreter — picking one without its optional extras
produces unnecessary SKIPPED verdicts. Resolution follows a fixed
authority order; the first existing, spec-compatible interpreter wins:

1. ``explicit`` — ``theforge lab collect --python PATH`` (operator-
   authorized; a missing path is rejected and recorded, never silent).
2. ``managed-receipt`` — the forge-cli registry receipt
   ``~/.forge-cli/forges/<forge>/install.json`` → ``venv`` (or the
   interpreter sibling of ``bin``). An unreadable/invalid receipt skips
   the level and is recorded as a warning, never fatal.
3. ``manifest`` — the ``~/.forge/installations`` manifest
   (``<FORGE>_PYTHON`` variable → ``python.executable`` → ``venv``),
   resolved by ``manifest_python``.
4. ``specialist-env`` — a repo-local ``.venv`` inside the checkout.
5. ``fallback`` — ``sys.executable``: the collector's own interpreter,
   always last and always documented as such.

When the manifest (or the checkout's ``forge.json``, for repo targets)
declares ``python.satisfies`` / ``"python": ">=3.11"`` and/or ``extras``
(importable optional packages), each candidate is validated before
selection — via ``pyvenv.cfg`` / ``sys.version_info`` when readable,
via one bounded read-only ``-c`` probe otherwise (version and missing
extras in a single spawn). A candidate that cannot be validated is
rejected with its precise reason; when every candidate is rejected the
lab is BLOCKED — it never runs on an unproven interpreter, and an
interpreter without the declared extras is never silently chosen.

Honest outcome states (PASS / FAIL / SKIPPED / BLOCKED / ERROR) are
derived from ``status`` + ``reason`` — SKIPPED is never mapped to PASS
or FAIL, and every skip carries its precise reason (extra missing is
reported by the lab receipt; interpreter/refusal causes by the
collector's ``reason`` field).
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from theforge.contracts.base import ContractError
from theforge.contracts.benchmark import (
    RESULT_SCHEMA,
    BenchmarkResult,
    LabMode,
    dump_result,
    load_result,
)
from theforge.contracts.types import Producer
from theforge.install.providers import manifest_python
from theforge.lab_stats import scenario_metrics, summarize
from theforge.security.redact import redact_text

LAB_MODES = ("A", "B", "C")
DEFAULT_TIMEOUT_S = 600
MAX_TIMEOUT_S = 3600
MAX_REPEATS = 10
MAX_JOBS = 4
MAX_OUTPUT_CHARS = 4096
DEFAULT_REPORT_DIR = "docs/programs/ecosystem-2026/benchmarks"

_TEMPLATE_TOKENS = ("{python}", "{checkout}", "{receipt}", "{mode}", "{run_index}")
_SAFE_ENV_KEYS = (
    "PATH",
    "HOME",
    "USERPROFILE",
    "LANG",
    "LC_ALL",
    "TZ",
    "SystemRoot",
    "SystemDrive",
    "WINDIR",
    "TEMP",
    "TMP",
    "PATHEXT",
    "COMSPEC",
)


class LabError(Exception):
    """Guardrail or contract violation inside the lab coordinator."""


@dataclass(frozen=True, kw_only=True)
class LabDecl:
    """A forge's declared lab (``forge.json`` ``lab`` object)."""

    forge_id: str
    checkout: Path
    command: list[str]
    receipt: str
    modes: tuple[str, ...]
    suite: str | None
    timeout_s: int
    python: str
    raw: dict[str, Any]


LabStatus = Literal[
    "undeclared",
    "none",
    "unsupported-mode",
    "ok",
    "exit",
    "timeout",
    "invalid",
    "blocked",
    "error",
]
LabState = Literal["PASS", "FAIL", "SKIPPED", "BLOCKED", "ERROR"]

# status → semantic state. ``invalid`` splits on ``reason``: a malformed
# declaration is BLOCKED (refused before running), evidence produced by a
# run that fails validation is FAIL.
_STATUS_TO_STATE: dict[str, LabState] = {
    "ok": "PASS",
    "undeclared": "SKIPPED",
    "none": "SKIPPED",
    "unsupported-mode": "SKIPPED",
    "blocked": "BLOCKED",
    "invalid": "FAIL",
    "exit": "FAIL",
    "timeout": "ERROR",
    "error": "ERROR",
}


@dataclass(kw_only=True)
class LabOutcome:
    """What the collector observed about one forge (ran or not).

    ``status`` is the observed wire detail; ``reason`` is the precise
    machine code behind it; ``state`` derives both into the honest
    PASS/FAIL/SKIPPED/BLOCKED/ERROR vocabulary — a SKIPPED outcome is
    never reported as PASS or FAIL.
    """

    forge_id: str
    status: LabStatus
    checkout: str
    mode: LabMode
    reason: str = ""
    interpreter: InterpreterResolution | None = None
    runs: list[BenchmarkResult] = field(default_factory=list)
    detail: str = ""
    duration_ms: int | None = None

    @property
    def state(self) -> LabState:
        if self.status == "invalid" and self.reason == "invalid-decl":
            return "BLOCKED"
        return _STATUS_TO_STATE.get(self.status, "ERROR")


@dataclass(frozen=True, kw_only=True)
class InterpreterCandidate:
    """One authority level tried during interpreter resolution."""

    source: str  # explicit|managed-receipt|manifest|specialist-env|fallback
    path: str | None
    verdict: str  # "" when accepted; precise rejection reason otherwise
    version: str | None = None


@dataclass(frozen=True, kw_only=True)
class InterpreterResolution:
    """Which interpreter won, at which level, and who was rejected."""

    python: str | None
    source: str  # winning level, or "none"
    spec: str | None = None
    version: str | None = None
    extras: tuple[str, ...] = ()
    rejected: tuple[InterpreterCandidate, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def resolved(self) -> bool:
        return self.python is not None

    def detail(self) -> str:
        """One-line audit of a failed resolution — precise reasons."""
        parts = [f"{c.source}: {c.verdict}" for c in self.rejected]
        if self.spec:
            parts.append(f"spec requires {self.spec!r}")
        parts += self.warnings
        return "; ".join(parts)


# --------------------------------------------------------------------------
# interpreter resolution (cyc11.2 P1-005)
# --------------------------------------------------------------------------

_SPEC_CLAUSE_RE = re.compile(r"^\s*(>=|<=|==|!=|>|<)\s*(\d+(?:\.\d+){0,2})\s*$")
_VERSION_PROBE_S = 15
_VERSION_PROBE_ARGV = (
    "-c",
    "import sys;print('.'.join(map(str, sys.version_info[:3])))",
)


def _version_tuple(text: str) -> tuple[int, ...] | None:
    parts = text.strip().split(".")
    if not 1 <= len(parts) <= 3 or not all(p.isdigit() for p in parts):
        return None
    return tuple(int(p) for p in parts)


def _cmp_version(a: tuple[int, ...], b: tuple[int, ...]) -> int:
    n = max(len(a), len(b))
    a += (0,) * (n - len(a))
    b += (0,) * (n - len(b))
    return (a > b) - (a < b)


def _version_satisfies(version: tuple[int, ...], spec: str) -> bool | None:
    """Evaluate a `>=3.11`-style spec — ``None`` when the spec is
    unparseable (an unevaluable constraint is unverified, never waived)."""
    clauses = [c for c in spec.split(",") if c.strip()]
    if not clauses:
        return None
    for clause in clauses:
        m = _SPEC_CLAUSE_RE.match(clause)
        if m is None:
            return None
        want = _version_tuple(m.group(2))
        if want is None:
            return None
        cmp = _cmp_version(version, want)
        op = m.group(1)
        if op == ">=" and cmp < 0:
            return False
        if op == "<=" and cmp > 0:
            return False
        if op == ">" and cmp <= 0:
            return False
        if op == "<" and cmp >= 0:
            return False
        if op == "==" and cmp != 0:
            return False
        if op == "!=" and cmp == 0:
            return False
    return True


def _fmt_version(version: tuple[int, ...]) -> str:
    return ".".join(str(p) for p in version)


def _pyvenv_cfg_version(python: Path) -> tuple[int, ...] | None:
    """Venv interpreter version without spawning — ``pyvenv.cfg`` sits
    beside ``bin/`` (or ``Scripts/``) and records the creation version."""
    cfg = python.parent.parent / "pyvenv.cfg"
    try:
        for line in cfg.read_text(encoding="utf-8", errors="replace").splitlines():
            key, _, value = line.partition("=")
            if key.strip() == "version":
                return _version_tuple(value.strip())
    except OSError:
        pass
    return None


def _interpreter_version(path: str, *, probe: bool = True) -> tuple[int, ...] | None:
    """Best-effort version of a candidate interpreter.

    Free paths first (``sys.executable`` identity, ``pyvenv.cfg``), then
    one bounded read-only ``-c`` probe when ``probe``. ``None`` means the
    version is undeterminable — with a declared spec that is unproven,
    never assumed.
    """
    venv_version = _pyvenv_cfg_version(Path(path))
    if venv_version is not None:
        # the env's own declaration wins over the resolved binary —
        # a venv python may share the collector's executable yet declare
        # a different creation version in pyvenv.cfg
        return venv_version
    try:
        if Path(path).resolve() == Path(sys.executable).resolve():
            return tuple(sys.version_info[:3])
    except OSError:
        pass
    if not probe:
        return None
    try:
        proc = subprocess.run(
            [path, *_VERSION_PROBE_ARGV],
            capture_output=True,
            text=True,
            timeout=_VERSION_PROBE_S,
            check=False,
        )
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return _version_tuple(proc.stdout.strip())


def _venv_python_in(venv: Path) -> Path | None:
    exe = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    return exe if exe.is_file() else None


_EXTRAS_PROBE_SRC = (
    "import sys,json,importlib.util;"
    "print(json.dumps({'v':list(sys.version_info[:3]),"
    "'m':[m for m in sys.argv[1:] if importlib.util.find_spec(m) is None]}))"
)


def _probe_interpreter(
    path: str, extras: tuple[str, ...]
) -> tuple[tuple[int, ...] | None, tuple[str, ...] | None]:
    """One bounded read-only probe answering ``(version, missing_extras)``.

    ``(None, None)`` means the interpreter cannot run or report — a
    declared spec or extras requirement is then unproven, never assumed.
    """
    try:
        proc = subprocess.run(
            [path, "-c", _EXTRAS_PROBE_SRC, *extras],
            capture_output=True,
            text=True,
            timeout=_VERSION_PROBE_S,
            check=False,
        )
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None, None
    if proc.returncode != 0:
        return None, None
    try:
        doc = json.loads(proc.stdout.strip())
    except json.JSONDecodeError:
        return None, None
    if not isinstance(doc, dict):
        return None, None
    raw_v, raw_m = doc.get("v"), doc.get("m")
    version = (
        tuple(raw_v) if isinstance(raw_v, list) and all(isinstance(p, int) for p in raw_v) else None
    )
    missing = tuple(m for m in raw_m if isinstance(m, str)) if isinstance(raw_m, list) else None
    return version, missing


def _checkout_requirements(checkout: Path) -> tuple[str | None, tuple[str, ...]]:
    """``(python spec, extras)`` declared by the checkout's own
    ``forge.json`` — a repo target has no install manifest; its
    declaration is the document the manifest was generated from
    (``"python": ">=3.11"``, ``"extras": ["mcp"]``)."""
    doc_path = checkout / "forge.json"
    if not doc_path.is_file():
        return None, ()
    try:
        doc = json.loads(doc_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None, ()
    if not isinstance(doc, dict):
        return None, ()
    spec = _python_spec_of(doc)
    extras = _extras_of(doc)
    return spec, extras


def _python_spec_of(doc: dict[str, Any]) -> str | None:
    """Python requirement from a manifest/forge doc — tolerates both the
    install manifest's ``python.satisfies`` object and forge.json's bare
    ``"python": ">=3.11"`` string."""
    raw_py = doc.get("python")
    raw: object = raw_py.get("satisfies") if isinstance(raw_py, dict) else raw_py
    return raw.strip() if isinstance(raw, str) and raw.strip() else None


def _extras_of(doc: dict[str, Any]) -> tuple[str, ...]:
    raw_ex = doc.get("extras")
    if not isinstance(raw_ex, list):
        return ()
    return tuple(e.strip() for e in raw_ex if isinstance(e, str) and e.strip())


def _managed_receipt_home(home: Path | None) -> Path:
    """forge-cli state home — ``FORGE_CLI_HOME`` is the tool's own
    documented override; the ``home`` parameter is the test seam."""
    override = os.environ.get("FORGE_CLI_HOME", "").strip()
    if override:
        return Path(override).expanduser()
    return home if home is not None else Path.home()


def _managed_receipt_python(forge_id: str, home: Path) -> tuple[str | None, str | None]:
    """Interpreter recorded by the forge-cli managed install receipt —
    ``<home>/.forge-cli/forges/<forge>/install.json`` ``venv`` (or the
    interpreter sibling of ``bin``). Returns ``(path, warning)``."""
    receipt = home / ".forge-cli" / "forges" / forge_id / "install.json"
    if not receipt.is_file():
        return None, None
    try:
        doc = json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, f"managed receipt {receipt} unreadable: {exc}"
    if not isinstance(doc, dict):
        return None, f"managed receipt {receipt} is not an object"
    venv = doc.get("venv")
    if isinstance(venv, str) and venv:
        py = _venv_python_in(Path(venv).expanduser())
        if py is not None:
            return str(py), None
        return None, f"managed receipt venv {venv!r} has no interpreter"
    bin_path = doc.get("bin")
    if isinstance(bin_path, str) and bin_path:
        exe = Path(bin_path).expanduser().parent / ("python.exe" if os.name == "nt" else "python")
        if exe.is_file():
            return str(exe), None
    return None, f"managed receipt {receipt} declares no usable interpreter"


def _specialist_env_python(checkout: Path) -> str | None:
    """Repo-local specialist environment — the forge's own ``.venv``
    inside the checkout (the only local env a ``forge.json`` implies)."""
    py = _venv_python_in(checkout / ".venv")
    return str(py) if py is not None else None


def resolve_interpreter(
    *,
    forge_id: str,
    checkout: Path,
    manifest: dict[str, Any] | None = None,
    explicit: str | None = None,
    home: Path | None = None,
    validate: bool = True,
) -> InterpreterResolution:
    """Fixed-order interpreter resolution (module docstring authority list).

    ``explicit`` is the operator-authorized override (``--python``);
    ``validate`` enables version probing — ``lab list`` passes ``False``
    (inspect-only, never spawns). A declared ``python.satisfies`` spec is
    enforced per candidate before selection.
    """
    checkout_spec, checkout_extras = _checkout_requirements(checkout)
    spec = (_python_spec_of(manifest) if manifest is not None else None) or checkout_spec
    extras = (_extras_of(manifest) if manifest is not None else ()) or checkout_extras

    warnings: list[str] = []
    ordered: list[tuple[str, str | None, str]] = []
    if explicit:
        p = Path(explicit).expanduser()
        ordered.append(
            (
                "explicit",
                str(p) if p.is_file() else None,
                f"explicit interpreter {explicit!r} is not a file",
            )
        )
    receipt_py, receipt_warn = _managed_receipt_python(forge_id, _managed_receipt_home(home))
    if receipt_warn:
        warnings.append(receipt_warn)
    ordered.append(("managed-receipt", receipt_py, "no managed-receipt interpreter"))
    if manifest is not None:
        ordered.append(("manifest", manifest_python(manifest), "manifest declares no interpreter"))
    ordered.append(
        (
            "specialist-env",
            _specialist_env_python(checkout),
            "no .venv interpreter in checkout",
        )
    )
    ordered.append(("fallback", sys.executable, ""))

    rejected: list[InterpreterCandidate] = []
    unparseable_warned = False
    for source, path, missing_note in ordered:
        if path is None:
            rejected.append(InterpreterCandidate(source=source, path=None, verdict=missing_note))
            continue
        missing: tuple[str, ...] = ()
        if validate and extras:
            # one probe answers version + importable extras together
            version, probed_missing = _probe_interpreter(path, extras)
            if probed_missing is None:
                version = _interpreter_version(path, probe=False)
                version_s = _fmt_version(version) if version is not None else None
                rejected.append(
                    InterpreterCandidate(
                        source=source,
                        path=path,
                        version=version_s,
                        verdict=(
                            "interpreter cannot run or report — declared extras "
                            f"{list(extras)} unproven"
                        ),
                    )
                )
                continue
            missing = probed_missing
        else:
            version = _interpreter_version(path, probe=validate)
        version_s = _fmt_version(version) if version is not None else None
        if validate and spec:
            if version is None:
                rejected.append(
                    InterpreterCandidate(
                        source=source,
                        path=path,
                        version=None,
                        verdict=f"version undeterminable — cannot validate {spec!r}",
                    )
                )
                continue
            verdict = _version_satisfies(version, spec)
            if verdict is None:
                if not unparseable_warned:
                    warnings.append(f"unparseable python spec {spec!r} — compatibility unverified")
                    unparseable_warned = True
            elif not verdict:
                rejected.append(
                    InterpreterCandidate(
                        source=source,
                        path=path,
                        version=version_s,
                        verdict=f"python {version_s} does not satisfy {spec!r}",
                    )
                )
                continue
        if missing:
            rejected.append(
                InterpreterCandidate(
                    source=source,
                    path=path,
                    version=version_s,
                    verdict=(f"missing extras {sorted(missing)} — declared {list(extras)}"),
                )
            )
            continue
        return InterpreterResolution(
            python=path,
            source=source,
            spec=spec,
            version=version_s,
            extras=extras,
            rejected=tuple(rejected),
            warnings=tuple(warnings),
        )
    return InterpreterResolution(
        python=None,
        source="none",
        spec=spec,
        extras=extras,
        rejected=tuple(rejected),
        warnings=tuple(warnings),
    )


def _interpreter_doc(resolution: InterpreterResolution | None) -> dict[str, Any] | None:
    if resolution is None:
        return None
    return {
        "python": resolution.python,
        "source": resolution.source,
        "spec": resolution.spec,
        "version": resolution.version,
        "extras": list(resolution.extras),
        "rejected": [
            {
                "source": c.source,
                "path": c.path,
                "version": c.version,
                "verdict": c.verdict,
            }
            for c in resolution.rejected
        ],
        "warnings": list(resolution.warnings),
    }


def _checkout_of(manifest: dict[str, Any]) -> Path | None:
    raw = (manifest.get("source") or {}).get("path")
    if not isinstance(raw, str) or not raw:
        return None
    path = Path(raw).expanduser()
    return path if path.is_dir() else None


def _safe_env(mode: LabMode) -> dict[str, str]:
    """Minimal inherited environment — credentials and API keys never
    propagate to a lab subprocess (§9.11 sanitization)."""
    env = {k: v for k, v in os.environ.items() if k in _SAFE_ENV_KEYS}
    env["FORGE_LAB_MODE"] = mode
    env["FORGE_LAB_SANDBOX"] = "1"
    # recursion guard: a lab that is itself a participant of a multi-forge
    # scenario must know it runs nested (labs propagate it explicitly)
    if os.environ.get("FORGE_LAB_NESTED"):
        env["FORGE_LAB_NESTED"] = "1"
    return env


def load_lab_decl(forge_id: str, checkout: Path, python: str) -> LabDecl | Literal["none"] | None:
    """Read the forge's ``forge.json`` lab declaration.

    ``None`` = ``lab`` absent (undeclared); ``"none"`` = ``lab: false``
    (declared no lab — honest until its spec lands); raises ``LabError``
    on a malformed declaration — broken is never silently "no lab".
    """
    doc_path = checkout / "forge.json"
    if not doc_path.is_file():
        return None
    doc = json.loads(doc_path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise LabError(f"{forge_id}: forge.json is not an object")
    lab = doc.get("lab")
    if lab is None:
        return None
    if lab is False:
        return "none"
    if not isinstance(lab, dict):
        raise LabError(f"{forge_id}: forge.json 'lab' must be an object or false")
    command = lab.get("command")
    if not isinstance(command, list) or not command or not all(isinstance(a, str) for a in command):
        raise LabError(f"{forge_id}: lab.command must be an argv list of strings")
    for token in (a for a in command if a.startswith("{")):
        if not any(token.startswith(t) for t in _TEMPLATE_TOKENS) and token not in _TEMPLATE_TOKENS:
            raise LabError(f"{forge_id}: lab.command token {token!r} is not a known template")
    receipt = lab.get("receipt")
    if not isinstance(receipt, str) or not receipt:
        raise LabError(f"{forge_id}: lab.receipt is required")
    receipt_path = (checkout / receipt).resolve()
    if not receipt_path.is_relative_to(checkout.resolve()):
        raise LabError(f"{forge_id}: lab.receipt escapes the checkout: {receipt!r}")
    modes = lab.get("modes", ["A"])
    if not isinstance(modes, list) or not modes or any(m not in LAB_MODES for m in modes):
        raise LabError(f"{forge_id}: lab.modes must be a non-empty subset of {LAB_MODES}")
    timeout_s = lab.get("timeout_s", DEFAULT_TIMEOUT_S)
    if not isinstance(timeout_s, int) or isinstance(timeout_s, bool) or timeout_s < 1:
        raise LabError(f"{forge_id}: lab.timeout_s must be a positive integer")
    suite = lab.get("suite")
    if suite is not None and not isinstance(suite, str):
        raise LabError(f"{forge_id}: lab.suite must be a string id")
    return LabDecl(
        forge_id=forge_id,
        checkout=checkout,
        command=list(command),
        receipt=receipt,
        modes=tuple(modes),
        suite=suite,
        timeout_s=min(timeout_s, MAX_TIMEOUT_S),
        python=python,
        raw=lab,
    )


def _resolve_argv(decl: LabDecl, mode: LabMode, receipt: Path, run_index: int) -> list[str]:
    argv = [
        token.replace("{python}", decl.python)
        .replace("{checkout}", str(decl.checkout))
        .replace("{receipt}", str(receipt))
        .replace("{mode}", mode)
        .replace("{run_index}", str(run_index))
        for token in decl.command
    ]
    return argv


def _run_one(
    decl: LabDecl,
    mode: LabMode,
    run_index: int,
    *,
    external: bool,
) -> tuple[BenchmarkResult | None, str, int]:
    """Invoke the declared lab once under the guardrails.

    Returns ``(result, detail, duration_ms)``; ``result`` is ``None`` when
    the subprocess failed before emitting a receipt.
    """
    receipt = decl.checkout / decl.receipt
    if run_index:
        receipt = receipt.with_name(f"{receipt.stem}-{run_index}{receipt.suffix}")
    argv = _resolve_argv(decl, mode, receipt, run_index)
    started = datetime.now(tz=UTC)
    try:
        proc = subprocess.run(
            argv,
            cwd=decl.checkout,
            env=_safe_env(mode),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=decl.timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None, "timeout", int(decl.timeout_s * 1000)
    except (OSError, ValueError) as exc:
        return None, f"spawn failed: {redact_text(str(exc))[:200]}", 0
    duration_ms = int((datetime.now(tz=UTC) - started).total_seconds() * 1000)
    if proc.returncode != 0:
        tail = redact_text((proc.stderr or proc.stdout or "")[-MAX_OUTPUT_CHARS:])
        return None, f"exit:{proc.returncode} {tail.strip()[:300]}", duration_ms
    if not receipt.is_file():
        return None, f"exit:0 but receipt {decl.receipt!r} missing", duration_ms
    try:
        result = load_result(receipt)
    except (ContractError, json.JSONDecodeError, OSError) as exc:
        return None, f"invalid receipt: {str(exc)[:300]}", duration_ms
    if result.forge != decl.forge_id:
        return None, f"receipt forge {result.forge!r} != {decl.forge_id!r}", duration_ms
    if result.mode != mode:
        return None, f"receipt mode {result.mode!r} != requested {mode!r}", duration_ms
    if external and not result.external:
        return None, "mode C run did not mark external=true", duration_ms
    return result, "", duration_ms


def collect(
    *,
    manifests: list[dict[str, Any]],
    mode: LabMode = "A",
    forge: str | None = None,
    repos: tuple[Path, ...] = (),
    timeout_s: int = DEFAULT_TIMEOUT_S,
    repeats: int = 1,
    jobs: int = 1,
    allow_external: bool = False,
    python: str | None = None,
    home: Path | None = None,
) -> tuple[list[LabOutcome], bool]:
    """Discover declared labs and collect ``forge/BenchmarkResult/v1``
    receipts under §9.11 guardrails.

    ``manifests`` comes from the install registry; ``repos`` adds explicit
    checkouts (CI/dev) — each must carry its own ``forge.json``.
    ``python`` is the operator-authorized interpreter override
    (``--python``); ``home`` is the forge-cli state home seam (defaults to
    ``FORGE_CLI_HOME``/``Path.home()`` — see ``resolve_interpreter``).
    """
    if mode not in LAB_MODES:
        raise LabError(f"lab mode {mode!r} not in {LAB_MODES}")
    if not 1 <= repeats <= MAX_REPEATS:
        raise LabError(f"repeats must be within 1..{MAX_REPEATS}")
    if not 1 <= jobs <= MAX_JOBS:
        raise LabError(f"jobs must be within 1..{MAX_JOBS}")
    if not 1 <= timeout_s <= MAX_TIMEOUT_S:
        raise LabError(f"timeout must be within 1..{MAX_TIMEOUT_S}s")
    if mode == "C" and not allow_external:
        raise LabError("mode C runs real external resources — explicit --allow-external required")

    targets: list[tuple[str, Path, dict[str, Any] | None]] = []
    seen: set[str] = set()
    for manifest in manifests:
        fid = str(manifest.get("forge_id") or "")
        checkout = _checkout_of(manifest)
        if not fid or checkout is None or fid in seen:
            continue
        seen.add(fid)
        targets.append((fid, checkout, manifest))
    for repo in repos:
        repo = repo.resolve()
        decl_doc = repo / "forge.json"
        fid = repo.name
        if decl_doc.is_file():
            with contextlib.suppress(json.JSONDecodeError):
                fid = str(
                    json.loads(decl_doc.read_text(encoding="utf-8")).get("forge_id") or repo.name
                )
        if fid not in seen:
            seen.add(fid)
            targets.append((fid, repo, None))
    if forge is not None:
        targets = [t for t in targets if t[0] == forge]

    outcomes: list[LabOutcome] = []

    def work(target: tuple[str, Path, dict[str, Any] | None]) -> LabOutcome:
        fid, checkout, manifest = target
        out = LabOutcome(forge_id=fid, status="undeclared", checkout=str(checkout), mode=mode)
        resolution = resolve_interpreter(
            forge_id=fid,
            checkout=checkout,
            manifest=manifest,
            explicit=python,
            home=home,
            validate=True,
        )
        out.interpreter = resolution
        try:
            decl = load_lab_decl(fid, checkout, resolution.python or sys.executable)
        except (LabError, json.JSONDecodeError, OSError) as exc:
            out.status = "invalid"
            out.reason = "invalid-decl"
            out.detail = str(exc)[:300]
            return out
        if decl is None:
            out.status = "undeclared"
            out.reason = "undeclared"
            return out
        if decl == "none":
            out.status = "none"
            out.reason = "declared-none"
            return out
        if mode not in decl.modes:
            out.status = "unsupported-mode"
            out.reason = "unsupported-mode"
            out.detail = f"declared modes {list(decl.modes)}"
            return out
        if resolution.python is None:
            out.status = "blocked"
            out.reason = "no-interpreter"
            out.detail = resolution.detail()[:300]
            return out
        timeout = min(decl.timeout_s, timeout_s)
        decl = dataclasses.replace(decl, timeout_s=timeout)
        total_ms = 0
        for i in range(repeats):
            result, detail, ms = _run_one(decl, mode, i, external=(mode == "C"))
            total_ms += ms
            if result is None:
                if detail == "timeout":
                    out.status, out.reason = "timeout", "timeout"
                elif detail.startswith("spawn failed"):
                    out.status, out.reason = "error", "spawn-failed"
                elif detail.startswith("exit:0") and "receipt" in detail:
                    out.status, out.reason = "invalid", "missing-receipt"
                elif detail.startswith(("invalid", "receipt", "mode C")):
                    out.status, out.reason = "invalid", "invalid-receipt"
                else:
                    out.status, out.reason = "exit", "exit"
                out.detail = detail
                break
            out.runs.append(result)
        else:
            out.status = "ok"
            out.reason = "ok"
        out.duration_ms = total_ms
        return out

    interrupted = False
    if jobs == 1:
        try:
            for t in targets:
                outcomes.append(work(t))
        except KeyboardInterrupt:
            interrupted = True
    else:
        try:
            with ThreadPoolExecutor(max_workers=jobs) as pool:
                outcomes = list(pool.map(work, targets))
        except KeyboardInterrupt:
            interrupted = True
    # deterministic order regardless of scheduling
    outcomes.sort(key=lambda o: o.forge_id)
    return outcomes, interrupted


def report_dir(root: Path, out: Path | None = None) -> Path:
    return out if out is not None else root / DEFAULT_REPORT_DIR


def write_report(
    *,
    root: Path,
    mode: LabMode,
    outcomes: list[LabOutcome],
    producer: Producer,
    out: Path | None = None,
    guardrails: dict[str, Any],
    interrupted: bool = False,
) -> dict[str, Any]:
    """Persist ``results-<date>-<mode>.jsonl`` + ``<date>-<mode>.md``."""
    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    directory = report_dir(root, out)
    directory.mkdir(parents=True, exist_ok=True)
    jsonl = directory / f"results-{today}-{mode}.jsonl"
    md = directory / f"{today}-{mode}.md"

    lines: list[str] = []
    for outcome in outcomes:
        for run in outcome.runs:
            lines.append(json.dumps(dump_result(run), sort_keys=True, ensure_ascii=False))
    jsonl.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    ran = [o for o in outcomes if o.state == "PASS"]
    skipped = [o for o in outcomes if o.state == "SKIPPED"]
    blocked = [o for o in outcomes if o.state == "BLOCKED"]
    failed = [o for o in outcomes if o.state in ("FAIL", "ERROR")]
    md.write_text(
        _report_md(
            today=today,
            mode=mode,
            outcomes=outcomes,
            ran=ran,
            skipped=skipped,
            blocked=blocked,
            failed=failed,
            producer=producer,
            guardrails=guardrails,
            interrupted=interrupted,
        ),
        encoding="utf-8",
    )
    states: dict[str, int] = {}
    for o in outcomes:
        states[o.state] = states.get(o.state, 0) + 1
    return {
        "report": str(md),
        "results_jsonl": str(jsonl),
        "forges": [
            {
                "forge": o.forge_id,
                "status": o.status,
                "state": o.state,
                "reason": o.reason,
                "interpreter": _interpreter_doc(o.interpreter),
                "runs": len(o.runs),
                "detail": o.detail,
                "duration_ms": o.duration_ms,
            }
            for o in outcomes
        ],
        "summary": {
            "ran": len(ran),
            "skipped": len(skipped),
            "blocked": len(blocked),
            "failed": len(failed),
            "states": states,
            "scenarios": sum(len(r.results) for o in ran for r in o.runs),
            "interrupted": interrupted,
        },
    }


def _report_md(
    *,
    today: str,
    mode: LabMode,
    outcomes: list[LabOutcome],
    ran: list[LabOutcome],
    skipped: list[LabOutcome],
    blocked: list[LabOutcome],
    failed: list[LabOutcome],
    producer: Producer,
    guardrails: dict[str, Any],
    interrupted: bool,
) -> str:
    lines = [
        f"# Benchmark report — {today} (mode {mode})",
        "",
        f"- Producer: `{producer.id} {producer.version}`",
        f"- Contract: `{RESULT_SCHEMA}` (receipts validated strict)",
        f"- Guardrails: {json.dumps(guardrails, sort_keys=True)}",
    ]
    if interrupted:
        lines.append("- **INTERRUPTED** — partial results; no conclusions")
    lines += [
        "",
        "## Methodology",
        "",
        "Each forge declares its lab in `forge.json` (`lab` object). The",
        "collector invokes the declared argv with a sanitized environment,",
        "per-lab timeout, argv allowlist and receipt confinement; engines",
        "stay in the specialists (ADR-0060). Metrics compare **per",
        "scenario, never across domains** — name→(value,unit) maps are",
        "not commensurable between forges.",
        "",
        "The `{python}` template resolves per forge in fixed order:",
        "`--python` → forge-cli managed receipt venv → install manifest →",
        "checkout `.venv` → the collector's own interpreter (documented",
        "fallback). A declared `python.satisfies` is validated per",
        "candidate; when nothing qualifies the lab is BLOCKED, never run",
        "on an unproven interpreter. States are honest: PASS / FAIL /",
        "SKIPPED / BLOCKED / ERROR — SKIPPED is never mapped to PASS.",
        "",
        "## Results by forge",
        "",
        "| Forge | State | Status | Scenarios | Detail |",
        "|---|---|---|---|---|",
    ]
    for o in outcomes:
        n = sum(len(r.results) for r in o.runs)
        lines.append(f"| {o.forge_id} | {o.state} | {o.status} | {n} | {o.detail or '—'} |")
    for o in ran:
        for run in o.runs:
            lines += [
                "",
                f"### {o.forge_id} — suite `{run.suite}`",
                "",
                "| Scenario | Verdict | Metrics |",
                "|---|---|---|",
            ]
            for r in run.results:
                metrics = (
                    ", ".join(
                        f"{k}={v.value}{(' ' + v.unit) if v.unit else ''}"
                        if v.measured
                        else f"{k}={v.state}"
                        for k, v in sorted(r.metrics.items())
                    )
                    or "—"
                )
                judge = f" judge={r.judge.model}" if r.judge else ""
                lines.append(f"| {r.scenario_id} | {r.verdict} | {metrics}{judge} |")
        if len(o.runs) > 1:
            lines += ["", f"#### {o.forge_id} — dispersion over {len(o.runs)} runs", ""]
            lines += [
                "| Scenario | Metric | n | median | spread (min–max) |",
                "|---|---|---|---|---|",
            ]
            scenario_ids = sorted({r.scenario_id for run in o.runs for r in run.results})
            for sid in scenario_ids:
                for name, ms in sorted(scenario_metrics(o.runs, sid).items()):
                    smry = summarize(name, ms)
                    if smry.median is None:
                        state = "/".join(f"{k}×{v}" for k, v in sorted(smry.states.items()))
                        lines.append(f"| {sid} | {name} | {smry.n} | — | {state} |")
                    else:
                        rng = (
                            f"{smry.min}–{smry.max}"
                            if smry.min is not None and smry.min != smry.max
                            else f"±{smry.mad}"
                        )
                        lines.append(f"| {sid} | {name} | {smry.n} | {smry.median} | {rng} |")
    lines += ["", "## Limitations", ""]
    if skipped:
        names = ", ".join(f"`{o.forge_id}` ({o.reason or o.status})" for o in skipped)
        lines.append(
            f"- Did not run: {names}. Absence is not a failure — "
            "undeclared labs are honest until their cyc9-0x specs land."
        )
    if blocked:
        names = ", ".join(f"`{o.forge_id}` ({o.detail or o.reason or o.status})" for o in blocked)
        lines.append(
            f"- Blocked: {names}. A guardrail refused the run — fix the "
            "declaration or the interpreter, never report as skipped or pass."
        )
    if failed:
        names = ", ".join(f"`{o.forge_id}` ({o.detail or o.status})" for o in failed)
        lines.append(f"- Failed: {names}. Investigate per-forge before drawing conclusions.")
    lines.append(
        "- Mode A compares each forge against its own declared fixtures; "
        "it says nothing about absolute quality across the ecosystem."
    )
    return "\n".join(lines) + "\n"
