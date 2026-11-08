"""Run a bounded, side-effect-free TTY smoke across the Forge CLI train.

The source contract and ``--version/--help`` smoke do not prove that a CLI
actually sees both terminal streams.  On Windows this gate uses winpty through
the optional ``pywinpty`` package, starts each default surface, captures the
first screen and interrupts before confirmation.  It is intentionally not an
installation test: no selection is accepted and no mutation is authorized.

Run with ``uv run --with pywinpty python scripts/cli_tty_smoke.py``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from winpty import PtyProcess
except ImportError as exc:  # pragma: no cover - exercised by the CLI itself
    raise SystemExit(
        "pywinpty is required; run `uv run --with pywinpty "
        "python scripts/cli_tty_smoke.py`"
    ) from exc


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
ANSI_ESCAPE = re.compile(r"\x1b(?:\][^\x07]*(?:\x07|\x1b\\)|\[[0-?]*[ -/]*[@-~]|[@-_])")


@dataclass(frozen=True)
class Case:
    repo: str
    argv: tuple[str, ...]


CASES: tuple[Case, ...] = (
    Case("api-forge", ("uv", "run", "apiforge")),
    Case("code-atlas-forge", ("uv", "run", "code-atlas")),
    Case("data-sentinel-forge", ("uv", "run", "data-sentinel")),
    Case("forge-agent-bridge", ("uv", "run", "forge-bridge")),
    Case("forge-cli", ("node", "dist/index.js")),
    Case("forge-doctor-api", ("uv", "run", "forge-doctor-api")),
    Case("forge-doctor-data", ("uv", "run", "forge-doctor-data")),
    Case("forge-lens", ("uv", "run", "forge-lens")),
    Case("forge-portal", ("node", "tools/portal-cli.mjs")),
    Case("platform-forge", ("uv", "run", "platformforge")),
    Case("product-forge", ("uv", "run", "productforge")),
    Case("spark-forge-aws", ("uv", "run", "sparkforge-aws")),
    Case("spark-forge-azure", ("uv", "run", "sparkforge-azure")),
    Case("the-forge", ("uv", "run", "theforge")),
)


def _scrubbed_environment() -> dict[str, str]:
    secret_markers = ("ACCESS_KEY", "API_KEY", "PASSWORD", "PRIVATE_KEY", "SECRET", "TOKEN")
    return {
        key: value
        for key, value in os.environ.items()
        if not any(marker in key.upper() for marker in secret_markers)
        and key.upper() not in {"VIRTUAL_ENV"}
    }


def _capture(process: PtyProcess, seconds: float) -> str:
    deadline = time.monotonic() + seconds
    chunks: list[str] = []
    while time.monotonic() < deadline and process.isalive():
        try:
            value = process.read(4096)
        except TimeoutError:
            # ``PtyProcess.read`` uses a socket-backed reader and blocks by
            # default.  A short timeout keeps the capture window bounded even
            # when the child has not emitted another frame yet.
            continue
        except (EOFError, OSError):
            break
        if value:
            chunks.append(value)
        else:
            time.sleep(0.05)
    return "".join(chunks)


def _has_visible_surface(output: str) -> bool:
    """Return true only when the PTY emitted human-visible content."""
    visible = ANSI_ESCAPE.sub("", output)
    visible = "".join(char for char in visible if char.isprintable() or char in "\r\n\t")
    return bool(visible.strip())


def run_case(case: Case, seconds: float) -> dict[str, Any]:
    cwd = WORKSPACE / case.repo
    row: dict[str, Any] = {
        "repo": case.repo,
        "command": " ".join(case.argv),
        "cwd": str(cwd),
    }
    if not cwd.is_dir():
        row.update({"status": "FAIL", "reason": "repository missing"})
        return row
    process: PtyProcess | None = None
    try:
        process = PtyProcess.spawn(
            list(case.argv),
            cwd=str(cwd),
            env=_scrubbed_environment(),
            dimensions=(30, 120),
        )
        # pywinpty's public ``read`` method is blocking.  Keep each poll
        # interruptible so one silent child cannot stall the complete matrix.
        process.fileobj.settimeout(0.1)
        output = _capture(process, seconds)
        alive_before_interrupt = process.isalive()
        if alive_before_interrupt:
            process.sendintr()
            _capture(process, 1.0)
        if process.isalive():
            process.terminate(force=True)
        row.update(
            {
                "status": "PASS" if _has_visible_surface(output) else "FAIL",
                "tty": True,
                "first_screen": output[:500],
                "interrupted_before_mutation": alive_before_interrupt,
                "exit_code": process.exitstatus,
            }
        )
        if not _has_visible_surface(output):
            row["reason"] = "empty visible TTY surface"
    except (OSError, RuntimeError) as exc:
        row.update({"status": "FAIL", "reason": f"pty spawn failed: {exc}"})
    finally:
        if process is not None and process.isalive():
            process.terminate(force=True)
    return row


def collect(seconds: float) -> dict[str, Any]:
    checks = [run_case(case, seconds) for case in CASES]
    return {
        "schema": "forge/cli-tty-runtime-smoke/v1",
        "repository_count": len(CASES),
        "checks": checks,
        "status": "PASS" if all(row["status"] == "PASS" for row in checks) else "FAIL",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seconds", type=float, default=1.5, help="capture window per CLI")
    args = parser.parse_args()
    if args.seconds <= 0:
        parser.error("--seconds must be positive")
    result = collect(args.seconds)
    # The gate is often run from a legacy Windows console.  ASCII JSON keeps
    # the evidence serializable even when a captured UI contains box-drawing
    # or accented characters and stdout is still cp1252.
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
