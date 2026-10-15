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
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
import os
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


@dataclass(kw_only=True)
class LabOutcome:
    """What the collector observed about one forge (ran or not)."""

    forge_id: str
    status: Literal["undeclared", "none", "unsupported-mode", "ok", "exit", "timeout", "invalid"]
    checkout: str
    mode: LabMode
    runs: list[BenchmarkResult] = field(default_factory=list)
    detail: str = ""
    duration_ms: int | None = None


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
) -> tuple[list[LabOutcome], bool]:
    """Discover declared labs and collect ``forge/BenchmarkResult/v1``
    receipts under §9.11 guardrails.

    ``manifests`` comes from the install registry; ``repos`` adds explicit
    checkouts (CI/dev) — each must carry its own ``forge.json``.
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

    targets: list[tuple[str, Path, str]] = []
    seen: set[str] = set()
    for manifest in manifests:
        fid = str(manifest.get("forge_id") or "")
        checkout = _checkout_of(manifest)
        if not fid or checkout is None or fid in seen:
            continue
        seen.add(fid)
        targets.append((fid, checkout, manifest_python(manifest) or sys.executable))
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
            targets.append((fid, repo, sys.executable))
    if forge is not None:
        targets = [t for t in targets if t[0] == forge]

    outcomes: list[LabOutcome] = []

    def work(target: tuple[str, Path, str]) -> LabOutcome:
        fid, checkout, interp = target
        out = LabOutcome(forge_id=fid, status="undeclared", checkout=str(checkout), mode=mode)
        try:
            decl = load_lab_decl(fid, checkout, interp)
        except (LabError, json.JSONDecodeError, OSError) as exc:
            out.status = "invalid"
            out.detail = str(exc)[:300]
            return out
        if decl is None:
            out.status = "undeclared"
            return out
        if decl == "none":
            out.status = "none"
            return out
        if mode not in decl.modes:
            out.status = "unsupported-mode"
            out.detail = f"declared modes {list(decl.modes)}"
            return out
        timeout = min(decl.timeout_s, timeout_s)
        decl = dataclasses.replace(decl, timeout_s=timeout)
        total_ms = 0
        for i in range(repeats):
            result, detail, ms = _run_one(decl, mode, i, external=(mode == "C"))
            total_ms += ms
            if result is None:
                out.status = (
                    "timeout"
                    if detail == "timeout"
                    else (
                        "invalid" if detail.startswith(("invalid", "receipt", "mode C")) else "exit"
                    )
                )
                out.detail = detail
                break
            out.runs.append(result)
        else:
            out.status = "ok"
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

    ran = [o for o in outcomes if o.status == "ok"]
    skipped = [o for o in outcomes if o.status in ("undeclared", "none", "unsupported-mode")]
    failed = [o for o in outcomes if o.status in ("exit", "timeout", "invalid")]
    md.write_text(
        _report_md(
            today=today,
            mode=mode,
            outcomes=outcomes,
            ran=ran,
            skipped=skipped,
            failed=failed,
            producer=producer,
            guardrails=guardrails,
            interrupted=interrupted,
        ),
        encoding="utf-8",
    )
    return {
        "report": str(md),
        "results_jsonl": str(jsonl),
        "forges": [
            {
                "forge": o.forge_id,
                "status": o.status,
                "runs": len(o.runs),
                "detail": o.detail,
                "duration_ms": o.duration_ms,
            }
            for o in outcomes
        ],
        "summary": {
            "ran": len(ran),
            "skipped": len(skipped),
            "failed": len(failed),
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
        "## Results by forge",
        "",
        "| Forge | Status | Scenarios | Detail |",
        "|---|---|---|---|",
    ]
    for o in outcomes:
        n = sum(len(r.results) for r in o.runs)
        lines.append(f"| {o.forge_id} | {o.status} | {n} | {o.detail or '—'} |")
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
        names = ", ".join(f"`{o.forge_id}` ({o.status})" for o in skipped)
        lines.append(
            f"- Did not run: {names}. Absence is not a failure — "
            "undeclared labs are honest until their cyc9-0x specs land."
        )
    if failed:
        names = ", ".join(f"`{o.forge_id}` ({o.detail or o.status})" for o in failed)
        lines.append(f"- Failed: {names}. Investigate per-forge before drawing conclusions.")
    lines.append(
        "- Mode A compares each forge against its own declared fixtures; "
        "it says nothing about absolute quality across the ecosystem."
    )
    return "\n".join(lines) + "\n"
