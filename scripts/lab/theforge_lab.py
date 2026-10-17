"""The Forge's own lab (mode A — offline fixtures only).

Domain: contracts and installation integrity. Scenarios:

- ``compat-manifest-parity``: the committed ``ecosystem-compatibility.json``
  must parse strict and every declared component version must match the
  version actually declared in the sibling checkout's
  ``pyproject.toml``/``package.json``.
- multi-forge scenarios from ``labs/multiforge/*.json``
  (``forge/MultiForgeScenario/v1``, cyc9-03): participants resolved via
  sibling checkouts, declared labs invoked through the real collector —
  Mode-C metrics measured when execution happens, ``not_applicable``
  when it cannot (§9.5 semantics, never zero).

Emits ``forge/BenchmarkResult/v1`` at ``--result-out``. Stdlib only.
Nested collection is guarded by ``FORGE_LAB_NESTED`` — when the-forge is
itself a participant, the nested run executes only the compat scenario.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

SCENARIO_ID = "compat-manifest-parity"
MULTIFORGE_DIR = "labs/multiforge"


def _declared_version(repo: Path, component: str) -> str | None:
    pyproject = repo / "pyproject.toml"
    if pyproject.is_file():
        text = pyproject.read_text(encoding="utf-8")
        in_project = False
        for line in text.splitlines():
            if line.strip().startswith("["):
                in_project = line.strip() == "[project]"
                continue
            if in_project and line.strip().startswith("version"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    pkg = repo / "package.json"
    if pkg.is_file():
        try:
            return str(json.loads(pkg.read_text(encoding="utf-8"))["version"])
        except (json.JSONDecodeError, KeyError):
            return None
    return None


def _repos_root(checkout: Path, override: str | None) -> Path:
    if override:
        return Path(override).resolve()
    return checkout.resolve().parent


def _compat_scenario(checkout: Path, repos_root: Path) -> dict[str, Any]:
    started = time.monotonic()
    manifest_path = checkout / "ecosystem-compatibility.json"
    detail = ""
    matched = total = 0
    try:
        sys.path.insert(0, str(checkout / "src"))
        from theforge.install.compatibility import load_manifest

        manifest = load_manifest(manifest_path)
        total = len(manifest.components)
        for comp in manifest.components:
            repo_dir = repos_root / comp.component
            declared = _declared_version(repo_dir, comp.component)
            if declared == comp.version:
                matched += 1
        verdict = "pass" if matched == total else "fail"
    except Exception as exc:  # noqa: BLE001 - scenario reports, never crashes
        verdict, detail = "error", f"{type(exc).__name__}: {exc}"
    return {
        "scenario_id": SCENARIO_ID,
        "verdict": verdict,
        "metrics": {
            "components_total": {"value": total},
            "components_matched": {"value": matched},
            "precision": {
                "value": round(matched / total, 4) if total else 0.0,
                "unit": "ratio",
            },
        },
        "duration_ms": int((time.monotonic() - started) * 1000),
        "evidence_ref": "ecosystem-compatibility.json",
        "detail": detail,
    }


def _multiforge_scenario(checkout: Path, repos_root: Path, sc_path: Path) -> dict[str, Any]:
    """Execute one MultiForgeScenario: resolve participants, invoke their
    declared labs through the real collector, measure Mode-C metrics."""
    started = time.monotonic()
    detail = ""
    metrics: dict[str, dict[str, Any]] = {}
    try:
        sys.path.insert(0, str(checkout / "src"))
        from theforge import lab as forgeslab
        from theforge.contracts.benchmark import dump_result, load_multiforge_scenario

        sc = load_multiforge_scenario(sc_path)
        expected = sc.expected or {}
        checkouts = {fid: repos_root / fid for fid in sc.participants}
        present = {fid: p for fid, p in checkouts.items() if (p / "forge.json").is_file()}
        metrics["participants_declared"] = {"value": len(sc.participants)}
        metrics["participants_present"] = {"value": len(present)}

        decl_states: dict[str, str] = {}
        for fid, path in sorted(present.items()):
            try:
                decl = forgeslab.load_lab_decl(fid, path, sys.executable)
                decl_states[fid] = (
                    "declared"
                    if decl not in (None, "none")
                    else ("none" if decl == "none" else "undeclared")
                )
            except Exception:  # noqa: BLE001 - broken decl is a state, not a crash
                decl_states[fid] = "invalid"
        for fid in sorted(set(sc.participants) - set(present)):
            decl_states[fid] = "missing"

        # invoke declared labs of resolvable participants via the real
        # collector — never re-implemented here
        outcomes: list[Any] = []  # LabOutcome — imported under sys.path
        runnable = [p for fid, p in sorted(present.items()) if decl_states[fid] == "declared"]
        if runnable:
            os.environ["FORGE_LAB_NESTED"] = "1"
            try:
                outcomes, _interrupted = forgeslab.collect(
                    manifests=[],
                    repos=tuple(runnable),
                    mode="A",
                    timeout_s=90,
                    repeats=1,
                    jobs=1,
                )
            finally:
                os.environ.pop("FORGE_LAB_NESTED", None)

        ok = [o for o in outcomes if o.state == "PASS"]
        failed = [o for o in outcomes if o.state in ("FAIL", "ERROR", "BLOCKED")]
        receipts = [r for o in ok for r in o.runs]
        metrics["labs_invoked"] = {"value": len(ok)}
        metrics["handoffs"] = {"value": len(ok)}
        metrics["routing_failures"] = {"value": len(failed)}
        metrics["re_executions"] = {"value": 0}
        metrics["receipt_integrity"] = (
            {"value": round(len(receipts) / len(ok), 4), "unit": "ratio"}
            if ok
            else {"state": "not_applicable"}
        )
        metrics["transported_context_bytes"] = (
            {"value": sum(len(json.dumps(dump_result(r))) for r in receipts), "unit": "bytes"}
            if ok
            else {"state": "not_applicable"}
        )
        metrics["duplication_ratio"] = {"state": "not_applicable"}
        metrics["cost_usd"] = {"state": "not_applicable"}

        # verdict: expectation violations fail; unexercisable composition
        # skips honestly; met expectations pass
        fail_reasons = []
        skip_reasons = []
        if not runnable:
            skip_reasons.append("no declared labs among participants — composition not exercisable")
        if expected.get("participants_present") and len(present) < len(sc.participants):
            missing = sorted(set(sc.participants) - set(present))
            skip_reasons.append(f"participants missing: {', '.join(missing)}")
        for fid in expected.get("labs_declared", []):
            state = decl_states.get(fid, "missing")
            if state == "invalid":
                fail_reasons.append(f"{fid}: lab declaration invalid")
            elif state in ("undeclared", "missing"):
                skip_reasons.append(f"{fid}: lab {state} (pending emitter)")
            elif state == "none":
                skip_reasons.append(f"{fid}: lab declared none by design")
        if failed:
            fail_reasons.append(
                "lab failures: " + ", ".join(f"{o.forge_id}={o.status}" for o in failed)
            )
        if len(ok) < int(expected.get("min_labs_ok", 0)) and runnable:
            fail_reasons.append(f"labs ok {len(ok)} < min_labs_ok {expected.get('min_labs_ok')}")
        if fail_reasons:
            verdict, detail = "fail", "; ".join(fail_reasons)
        elif skip_reasons:
            verdict, detail = "skipped", "; ".join(skip_reasons)
        else:
            verdict = "pass"
            detail = f"{len(ok)}/{len(runnable)} declared labs ok"
    except Exception as exc:  # noqa: BLE001 - scenario reports, never crashes
        verdict, detail = "error", f"{type(exc).__name__}: {exc}"
    return {
        "scenario_id": sc_path.stem,
        "verdict": verdict,
        "metrics": metrics,
        "duration_ms": int((time.monotonic() - started) * 1000),
        "evidence_ref": str(sc_path.relative_to(checkout))
        if sc_path.is_relative_to(checkout)
        else sc_path.name,
        "detail": detail,
    }


def run(checkout: Path, receipt_path: Path, repos_root: Path) -> int:
    results = [_compat_scenario(checkout, repos_root)]
    if not os.environ.get("FORGE_LAB_NESTED"):
        # nested runs (the-forge as a participant of another scenario)
        # execute only the compat scenario — recursion is a defect, not depth
        mdir = checkout / MULTIFORGE_DIR
        if mdir.is_dir():
            for sc_path in sorted(mdir.glob("*.json")):
                if sc_path.name == "suite.json":
                    continue
                results.append(_multiforge_scenario(checkout, repos_root, sc_path))

    doc = {
        "schema": "forge/BenchmarkResult/v1",
        "suite": "theforge-lab",
        "forge": "the-forge",
        "mode": "A",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "producer": {"id": "the-forge", "version": "lab-script"},
        "external": False,
        "results": results,
        "notes": ["repos_root=" + str(repos_root)],
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    for r in results:
        print(f"lab: {r['scenario_id']} {r['verdict']} {r['detail']}")
    # exit 0 whenever the engine ran and the receipt was written — scenario
    # fail verdicts are honest data inside the receipt, not runner failure
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--checkout", default=".")
    p.add_argument("--repos-root", default=None)
    p.add_argument("--mode", default="A", choices=["A", "B", "C"])
    p.add_argument("--result-out", required=True)
    args = p.parse_args()
    if args.mode != "A":
        print(f"lab: mode {args.mode} unsupported — this lab is mode A only", file=sys.stderr)
        return 2
    return run(
        Path(args.checkout).resolve(),
        Path(args.result_out),
        _repos_root(Path(args.checkout), args.repos_root),
    )


if __name__ == "__main__":
    raise SystemExit(main())
