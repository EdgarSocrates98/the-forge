"""Evals & verification surface (install-2.0 cycle 5, lf-0038 §7).

The classified catalog of the-forge's own eval suites (§7.1), the thin
adapters behind the §7.2 conceptual ops — ``evals.list``, ``evals.describe``,
``evals.run``, ``evals.result``, ``verification.plan``, ``verification.run`` —
and the §7.4 plan → run → evidence flow.

Design rules (§7.3, never negotiated):

- The catalog is *declared metadata*: ids, kinds, argv templates, triggers,
  environment markers. Suite payloads never inline expected answers — a
  holdout corpus is referenced by path plus sha256, never by content.
- ``evals run`` executes only declared argv templates: subprocess with a
  sanitized environment (``safe_env``), a bounded timeout and bounded output.
  A suite that declares inputs refuses to run until every placeholder is
  filled — missing inputs are a named refusal, not a skip-and-pass.
- ``environment`` marks *simulated* vs *real* surfaces; a simulated run is
  evidence, never real-environment proof, and receipts say so.
- Baselines and file inputs are hash-recorded in every receipt, so tampering
  is visible.
- Failures and inconclusive runs are explicit verdicts — the flow never
  upgrades an inconclusive outcome to a pass.

Stdlib-only. Deterministic. ``evals plan``/``verify plan`` never execute.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal

from theforge.contracts.canonical import utc_now
from theforge.errors import UsageError
from theforge.security.env import safe_env

RECEIPT_SCHEMA: Final = "theforge/EvalRunReceipt/v1"
PLAN_SCHEMA: Final = "theforge/VerificationPlan/v1"
EVALS_DIR: Final = ".forge/evals"

EvalKind = Literal["developer", "runtime-decision", "output-verification", "host-conformance"]
Environment = Literal["real", "simulated"]
Verdict = Literal["pass", "fail", "inconclusive", "blocked"]

# Risk floors for ``verify plan`` (§7.4): the risk of the change sets the
# minimum sweep — micro/low run only impacted suites, medium adds every
# developer eval, high runs the whole catalog.
RISK_LEVELS: Final = ("micro", "low", "medium", "high")


@dataclass(frozen=True, kw_only=True)
class EvalSuite:
    """One declared eval suite. ``argv`` placeholders: ``{python}`` (the
    running interpreter), ``{root}`` (workspace root) and one ``{name}`` per
    declared input — a suite never runs with an unfilled placeholder."""

    id: str
    kind: EvalKind
    description: str
    argv: tuple[str, ...]
    environment: Environment
    triggers: tuple[str, ...] = ()
    inputs: tuple[str, ...] = ()
    timeout_s: int = 600
    destructive: bool = False
    # Paths that carry authoritative comparisons (baselines) or sealed answers
    # (holdouts). Referenced, never inlined — receipts record their sha256.
    baselines: tuple[str, ...] = ()
    holdouts: tuple[str, ...] = ()


def _catalog() -> tuple[EvalSuite, ...]:
    return (
        EvalSuite(
            id="unit-tests",
            kind="developer",
            description="core pytest suite — skills, agents, routing, economy internals",
            argv=("{python}", "-m", "pytest", "tests", "-q"),
            environment="real",
            triggers=("src/**", "tests/**", "pyproject.toml"),
            timeout_s=900,
        ),
        EvalSuite(
            id="cli-smoke",
            kind="developer",
            description="installed CLI answers --version — proves the entry point, not the suite",
            argv=("{python}", "-m", "theforge", "--version"),
            environment="real",
            triggers=("src/theforge/cli/**", "src/theforge/__main__.py", "pyproject.toml"),
            timeout_s=60,
        ),
        EvalSuite(
            id="forgecontext-contract",
            kind="developer",
            description="forge/context/v1 engine: vendored parity, manifest validation, docs layer",
            argv=(
                "{python}", "-m", "pytest",
                "tests/test_forgecontext.py", "tests/test_installkit_schemas.py", "-q",
            ),
            environment="real",
            triggers=(
                "scripts/installkit/**",
                "src/theforge/_forgecontext.py",
                "docs/portable-installation/**",
                "src/theforge/install/**",
            ),
        ),
        EvalSuite(
            id="agent-assets",
            kind="developer",
            description="agent specs + host mirrors parity (AgentSpec/v1, canonical protocol refs)",
            argv=(
                "{python}", "-m", "pytest",
                "tests/test_agent_registry.py", "tests/test_agentic_parity.py", "-q",
            ),
            environment="real",
            triggers=("agentic/**", ".codex/agents/**", "src/theforge/agents.py"),
        ),
        EvalSuite(
            id="lab-collect",
            kind="runtime-decision",
            description=(
                "federated lab collection, mode A (offline fixtures) — operational "
                "measurement across installed forges; simulated, not a live-environment proof"
            ),
            argv=("{python}", "-m", "theforge", "lab", "collect", "--mode", "A"),
            environment="simulated",
            triggers=("forge.json", "labs/**", "scripts/lab/**"),
        ),
        EvalSuite(
            id="lab-gate",
            kind="runtime-decision",
            description="regression gate: current BenchmarkResult receipts vs a recorded baseline",
            argv=(
                "{python}", "-m", "theforge", "lab", "gate",
                "--results", "{results}", "--baseline", "{baseline}",
            ),
            environment="real",
            triggers=(),
            inputs=("results", "baseline"),
        ),
        EvalSuite(
            id="replay-verify",
            kind="output-verification",
            description="re-verify a past run's recorded inputs — integrity divergences exit 6",
            argv=("{python}", "-m", "theforge", "replay", "{run_id}", "--mode", "verify"),
            environment="real",
            triggers=(),
            inputs=("run_id",),
        ),
        EvalSuite(
            id="provider-conformance",
            kind="host-conformance",
            description=(
                "Forge Protocol conformance battery against a real provider argv "
                "(describe/health/execute/handoff/malformed-protocol)"
            ),
            argv=("{python}", "-m", "theforge", "provider", "check", "--", "{argv}"),
            environment="real",
            triggers=("src/theforge/protocol/**", "src/theforge/conformance.py"),
            inputs=("argv",),
        ),
    )


SUITES: tuple[EvalSuite, ...] = _catalog()


# --------------------------------------------------------------------------
# §7.1 — classified inventory (agent-facing: metadata only, never answers)
# --------------------------------------------------------------------------


def _suite_by_id(suite_id: str) -> EvalSuite:
    for suite in SUITES:
        if suite.id == suite_id:
            return suite
    raise UsageError(
        f"unknown eval suite {suite_id!r} — declared: {', '.join(s.id for s in SUITES)}"
    )


def catalog() -> list[dict[str, Any]]:
    """The §7.1 inventory: every declared suite with its kind. Metadata only —
    no case content, no expected answers, no holdout payloads."""
    return [
        {
            "id": s.id,
            "kind": s.kind,
            "description": s.description,
            "environment": s.environment,
            "inputs": list(s.inputs),
            "destructive": s.destructive,
            "command": [str(a) for a in s.argv],
        }
        for s in SUITES
    ]


def manifest_suites(root: Path | None = None) -> list[dict[str, Any]]:
    """``forge/context/v1`` ``eval_suites`` entries (id + kind + command)."""
    out: list[dict[str, Any]] = []
    for s in SUITES:
        entry: dict[str, Any] = {
            "id": s.id,
            "kind": s.kind,
            "command": ["theforge", "evals", "run", s.id],
        }
        out.append(entry)
    return out


def _file_digest(root: Path, rel: str) -> dict[str, Any] | None:
    path = root / rel
    if not path.is_file():
        return None
    return {
        "path": rel,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
    }


def describe(suite_id: str, *, root: Path | None = None) -> dict[str, Any]:
    """One suite's metadata. Baselines/holdouts surface as path + sha256 +
    count — contents are never returned (§7.3)."""
    suite = _suite_by_id(suite_id)
    base = root or Path.cwd()
    doc: dict[str, Any] = {
        "id": suite.id,
        "kind": suite.kind,
        "description": suite.description,
        "environment": suite.environment,
        "command": [str(a) for a in suite.argv],
        "inputs": [
            {"name": name, "required": True} for name in suite.inputs
        ],
        "triggers": list(suite.triggers),
        "timeout_s": suite.timeout_s,
        "destructive": suite.destructive,
        "proof_note": (
            "simulated evidence — not a real-environment proof"
            if suite.environment == "simulated"
            else "executes the real declared surface"
        ),
    }
    for key, paths in (("baselines", suite.baselines), ("holdouts", suite.holdouts)):
        entries = [d for d in (_file_digest(base, p) for p in paths) if d is not None]
        doc[key] = {
            "count": len(paths),
            "resolved": entries,
            "content": "sealed — never inlined into agent-facing output",
        }
    return doc


# --------------------------------------------------------------------------
# §7.4 — verification plan (never executes)
# --------------------------------------------------------------------------


def _matches(triggers: Sequence[str], changed: Sequence[str]) -> bool:
    for pattern in triggers:
        for path in changed:
            if fnmatch.fnmatch(path, pattern):
                return True
    return False


def plan(
    changed: Sequence[str],
    *,
    risk: str = "low",
    authorized: Sequence[str] = (),
) -> dict[str, Any]:
    """§7.4 steps 1–2: select applicable verifications, emit the plan.

    ``authorized`` names input values the caller supplies at run time
    (``name=value``); a selected suite whose inputs are not all authorized is
    planned but flagged ``blocked`` — it cannot run and says why.
    """
    if risk not in RISK_LEVELS:
        raise UsageError(f"risk {risk!r} is not one of {', '.join(RISK_LEVELS)}")
    changed_n = sorted({Path(c).as_posix().removeprefix("./") for c in changed})
    provided = {item.split("=", 1)[0] for item in authorized}
    selected: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    reasons = [f"risk {risk} sets the sweep floor"]
    for suite in SUITES:
        matched = _matches(suite.triggers, changed_n)
        if risk in ("micro", "low") and not matched:
            skipped.append({"suite": suite.id, "reason": "not impacted by the changed set"})
            continue
        if risk == "medium" and not (matched or suite.kind == "developer"):
            skipped.append(
                {"suite": suite.id, "reason": "medium sweep = impacted + developer evals"}
            )
            continue
        missing = [name for name in suite.inputs if name not in provided]
        selected.append(
            {
                "suite": suite.id,
                "kind": suite.kind,
                "environment": suite.environment,
                "argv": list(suite.argv),
                "reason": "impacted by the changed set" if matched else "risk sweep includes it",
                "missing_inputs": missing,
                "status": "blocked" if missing or suite.destructive else "authorized",
            }
        )
    if not selected:
        selected = [
            {
                "suite": s.id,
                "kind": s.kind,
                "environment": s.environment,
                "argv": list(s.argv),
                "reason": "empty impact selection escalates to the full sweep",
                "missing_inputs": [n for n in s.inputs if n not in provided],
                "status": "blocked" if [n for n in s.inputs if n not in provided] else "authorized",
            }
            for s in SUITES
        ]
        reasons.append("no impacted suite: escalated to the full catalog")
    return {
        "schema": PLAN_SCHEMA,
        "risk": risk,
        "changed": changed_n,
        "reasons": reasons,
        "selected": selected,
        "skipped": skipped,
        "note": "plan only — `theforge verify run --plan <file>` executes the authorized set",
    }


# --------------------------------------------------------------------------
# §7.4 — run + evidence (steps 3–6)
# --------------------------------------------------------------------------


_MAX_OUT: Final = 128 * 1024


def _receipt_id(prefix: str) -> str:
    stamp = utc_now()
    compact = stamp.replace(":", "").replace("-", "").split(".")[0].replace("T", "-")
    return f"{prefix}-{compact}-{hashlib.sha256(stamp.encode()).hexdigest()[:8]}"


def _evals_dir(root: Path) -> Path:
    d = root / EVALS_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_json(root: Path, name: str, doc: Mapping[str, Any]) -> Path:
    path = _evals_dir(root) / f"{name}.json"
    path.write_text(
        json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return path


def _resolve_argv(suite: EvalSuite, root: Path, inputs: Mapping[str, str]) -> list[str]:
    import shlex

    out: list[str] = []
    for arg in suite.argv:
        arg = arg.replace("{python}", sys.executable).replace("{root}", str(root))
        # A whole-arg placeholder expands to tokens (a provider argv may be
        # several words); an embedded one substitutes inline.
        whole = next(
            (name for name in inputs if arg == "{" + name + "}"), None
        )
        if whole is not None:
            out.extend(shlex.split(inputs[whole]))
            continue
        for name in inputs:
            arg = arg.replace("{" + name + "}", inputs[name])
        out.append(arg)
    return out


def run_suite(
    root: Path,
    suite_id: str,
    *,
    inputs: Mapping[str, str] | None = None,
    timeout_s: int | None = None,
) -> dict[str, Any]:
    """Execute one declared suite; write and return the receipt (§7.4 steps 3–5).

    Verdicts: ``pass`` (exit 0), ``fail`` (non-zero exit), ``inconclusive``
    (timeout or missing receipt semantics), ``blocked`` (missing inputs or a
    destructive suite — never executed). A blocked/inconclusive suite is
    explicit, never a silent skip.
    """
    suite = _suite_by_id(suite_id)
    inputs = dict(inputs or {})
    missing = [name for name in suite.inputs if name not in inputs]
    receipt_id = _receipt_id(f"eval-{suite.id}")
    base: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "receipt_id": receipt_id,
        "suite": suite.id,
        "kind": suite.kind,
        "environment": suite.environment,
        "simulated_proof": suite.environment == "simulated",
        "recorded_at": utc_now(),
        "inputs_recorded": {
            name: {"path": value, "sha256": hashlib.sha256(Path(value).read_bytes()).hexdigest()}
            for name, value in sorted(inputs.items())
            if Path(value).is_file()
        },
        "evidence": [],
    }
    if missing:
        base["verdict"] = "blocked"
        base["evidence"].append(f"missing required inputs: {', '.join(missing)}")
        base["unresolved"] = [f"input:{name}" for name in missing]
        _write_json(root, receipt_id, base)
        return base
    if suite.destructive:
        base["verdict"] = "blocked"
        base["evidence"].append("suite is declared destructive — evals never run it")
        base["unresolved"] = ["destructive:true"]
        _write_json(root, receipt_id, base)
        return base

    argv = _resolve_argv(suite, root, inputs)
    timeout = min(timeout_s or suite.timeout_s, suite.timeout_s)
    try:
        proc = subprocess.run(
            argv,
            cwd=root,
            env=safe_env(),
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        base["verdict"] = "inconclusive"
        base["argv"] = argv
        base["evidence"].append(f"timeout after {timeout}s — inconclusive, never a pass")
        base["unresolved"] = [f"timeout:{timeout}s"]
        _write_json(root, receipt_id, base)
        return base
    except OSError as exc:
        base["verdict"] = "inconclusive"
        base["argv"] = argv
        base["evidence"].append(f"spawn failed: {exc}")
        base["unresolved"] = ["spawn-failed"]
        _write_json(root, receipt_id, base)
        return base

    stdout = proc.stdout[:_MAX_OUT].decode("utf-8", "replace")
    stderr = proc.stderr[:_MAX_OUT].decode("utf-8", "replace")
    verdict: Verdict = "pass" if proc.returncode == 0 else "fail"
    base.update(
        {
            "verdict": verdict,
            "argv": argv,
            "exit_code": proc.returncode,
            "stdout_sha256": hashlib.sha256(proc.stdout).hexdigest(),
            "stdout_tail": stdout.splitlines()[-20:],
            "stderr_tail": stderr.splitlines()[-20:],
        }
    )
    base["evidence"].append(f"exit {proc.returncode} from declared argv")
    if suite.environment == "simulated":
        base["evidence"].append(
            "environment=simulated: offline fixture evidence, not a real-environment proof"
        )
    _write_json(root, receipt_id, base)
    return base


def run_plan(
    root: Path,
    plan_doc: Mapping[str, Any],
    *,
    inputs: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Execute a ``verify plan`` document: authorized suites run, blocked ones
    report their reason; evidence is a persisted run receipt (§7.4 steps 3–6)."""
    if plan_doc.get("schema") != PLAN_SCHEMA:
        raise UsageError(f"plan document schema is not {PLAN_SCHEMA}")
    inputs = dict(inputs or {})
    run_id = _receipt_id("verify-run")
    results: list[dict[str, Any]] = []
    counts = {"pass": 0, "fail": 0, "inconclusive": 0, "blocked": 0}
    for entry in plan_doc.get("selected", []):
        suite_id = str(entry.get("suite", ""))
        merged = dict(inputs)
        receipt = run_suite(root, suite_id, inputs=merged)
        counts[receipt["verdict"]] += 1
        results.append(
            {
                "suite": suite_id,
                "verdict": receipt["verdict"],
                "receipt_id": receipt["receipt_id"],
                "environment": receipt["environment"],
            }
        )
    verdict: Verdict
    if counts["fail"]:
        verdict = "fail"
    elif counts["inconclusive"] or counts["blocked"] or not results:
        verdict = "inconclusive"
    else:
        verdict = "pass"
    doc: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "receipt_id": run_id,
        "kind": "verification-run",
        "plan_risk": plan_doc.get("risk"),
        "changed": list(plan_doc.get("changed", [])),
        "recorded_at": utc_now(),
        "verdict": verdict,
        "counts": counts,
        "results": results,
        "evidence": [
            f"{counts[v]} {v}" for v in ("pass", "fail", "inconclusive", "blocked") if counts[v]
        ]
        or ["no suite executed"],
        "conclusion": (
            "conclusion proportional to evidence: "
            + (
                "all authorized verifications passed"
                if verdict == "pass"
                else "failures present — see per-suite receipts"
                if verdict == "fail"
                else "inconclusive/blocked suites remain — conclusion is NOT a pass"
            )
        ),
    }
    _write_json(root, run_id, doc)
    return doc


def result(root: Path, receipt_id: str) -> dict[str, Any]:
    """Read a persisted receipt by id (``evals.result``)."""
    safe = receipt_id.strip()
    if not safe or any(c in safe for c in ("/", "\\", "..")):
        raise UsageError(f"invalid receipt id {receipt_id!r}")
    path = _evals_dir(root) / f"{safe}.json"
    if not path.is_file():
        raise UsageError(f"no eval receipt {receipt_id!r} under {RESULTS_DIR_HINT}")
    doc: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return doc


def results(root: Path) -> list[dict[str, Any]]:
    """Every persisted receipt summary, newest last (``evals result`` no-arg)."""
    d = root / EVALS_DIR
    out: list[dict[str, Any]] = []
    if not d.is_dir():
        return out
    for path in sorted(d.glob("*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        out.append(
            {
                "receipt_id": path.stem,
                "suite": doc.get("suite", doc.get("kind")),
                "verdict": doc.get("verdict"),
                "environment": doc.get("environment"),
                "recorded_at": doc.get("recorded_at"),
            }
        )
    return out


RESULTS_DIR_HINT: Final = f"{EVALS_DIR}/ (run `theforge evals run <suite>` first)"


__all__ = [
    "PLAN_SCHEMA",
    "RECEIPT_SCHEMA",
    "RISK_LEVELS",
    "SUITES",
    "EvalSuite",
    "catalog",
    "describe",
    "manifest_suites",
    "plan",
    "result",
    "results",
    "run_plan",
    "run_suite",
]
