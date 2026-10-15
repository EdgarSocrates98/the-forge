"""The Forge's own lab (mode A — offline fixtures only).

Domain: contracts and installation integrity. Currently one scenario,
``compat-manifest-parity``: the committed ``ecosystem-compatibility.json``
must parse strict and every declared component version must match the
version actually declared in the sibling checkout's
``pyproject.toml``/``package.json`` — the same invariant the test suite
asserts, exposed as a versioned scenario the federated collector can run.

Emits ``forge/BenchmarkResult/v1`` at ``--result-out``. Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

SCENARIO_ID = "compat-manifest-parity"


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


def run(checkout: Path, receipt_path: Path, repos_root: Path) -> int:
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
    duration_ms = int((time.monotonic() - started) * 1000)

    doc = {
        "schema": "forge/BenchmarkResult/v1",
        "suite": "theforge-contracts",
        "forge": "the-forge",
        "mode": "A",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "producer": {"id": "the-forge", "version": "lab-script"},
        "external": False,
        "results": [
            {
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
                "duration_ms": duration_ms,
                "evidence_ref": "ecosystem-compatibility.json",
                "detail": detail,
            }
        ],
        "notes": ["repos_root=" + str(repos_root)],
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"lab: {SCENARIO_ID} {verdict} ({matched}/{total} components matched)")
    return 0 if verdict == "pass" else 1


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
