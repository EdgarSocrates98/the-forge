"""Local gate battery: one command for "am I green?".

Runs the same checks the release checklist and CI expect, in order, and
stops at the first failure (fix-forward; a later gate adds nothing until
the earlier one is clean). Stdlib only — invokes the repo's own tools as
subprocesses so each gate reports exactly what it would report standalone.

    python scripts/check_gates.py            # fast gates (lint/types/assets)
    python scripts/check_gates.py --pytest   # + default pytest selection
    python scripts/check_gates.py --list     # print gates, run nothing
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PY = sys.executable


def _schema_parity() -> tuple[int, str]:
    """Regenerate schemas then diff — identical bytes mean no mutation."""
    regen = subprocess.run(
        [PY, "-m", "theforge.contracts.schema", "schemas"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    if regen.returncode != 0:
        return regen.returncode, regen.stderr or regen.stdout
    diff = subprocess.run(
        ["git", "diff", "--exit-code", "--", "schemas"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    return diff.returncode, diff.stdout or "schemas/ regenerated cleanly"


def _cmd(*args: str) -> list[str]:
    return [PY, *args]


Step = list[str] | Callable[[], tuple[int, str]]

GATES: list[tuple[str, Step]] = [
    ("ruff check", _cmd("-m", "ruff", "check", ".")),
    ("ruff format", _cmd("-m", "ruff", "format", "--check", ".")),
    ("mypy", _cmd("-m", "mypy")),
    ("schema parity", _schema_parity),
    ("render_skills --check", _cmd("scripts/agentic/render_skills.py", "--check")),
    ("render_agents --check", _cmd("scripts/agentic/render_agents.py", "--check")),
    ("agentic audit", _cmd("scripts/agentic/audit_assets.py")),
    ("zero runtime deps", _cmd("scripts/ci/check_zero_deps.py")),
]

SLOW_GATES: list[tuple[str, Step]] = [
    ("pytest (default)", _cmd("-m", "pytest")),
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--pytest", action="store_true", help="also run the default pytest selection"
    )
    parser.add_argument("--list", action="store_true", help="list gates without running")
    args = parser.parse_args(argv)

    if shutil.which("git") is None:
        print("check_gates: git is required (schema parity gate)", file=sys.stderr)
        return 2

    gates = GATES + (SLOW_GATES if args.pytest else [])
    if args.list:
        for name, _ in gates:
            print(f"  {name}")
        return 0

    for name, step in gates:
        print(f"* {name} ... ", end="", flush=True)
        if callable(step):
            code, output = step()
        else:
            run = subprocess.run(step, cwd=REPO, capture_output=True, text=True)
            code, output = run.returncode, (run.stdout + run.stderr).strip()
        if code == 0:
            print("green")
        else:
            print(f"FAILED (exit {code})")
            print("-" * 60)
            print(output or "(no output)")
            return 1
    print(f"all {len(gates)} gates green")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
