"""Verify that every Forge bare CLI can be cancelled safely from a real TTY.

This complements ``cli_tty_smoke.py``: it starts each command without flags,
captures the home screen, sends the documented ``q`` cancel key and requires
the process to leave the terminal without reaching a confirmation step.
It is a discoverability/cancellation gate, not a mutating install test.
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
    from winpty import PtyProcess  # type: ignore[import-not-found]
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "pywinpty is required; run `uv run --with pywinpty "
        "python scripts/cli_tty_cancel_smoke.py`"
    ) from exc


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
ANSI_ESCAPE = re.compile(r"\x1b(?:\][^\x07]*(?:\x07|\x1b\\)|\[[0-?]*[ -/]*[@-~]|[@-_])")


@dataclass(frozen=True)
class Case:
    repo: str
    argv: tuple[str, ...]
    cancel: str = "q"


CASES: tuple[Case, ...] = (
    Case("api-forge", ("uv", "run", "apiforge")),
    Case("code-atlas-forge", ("uv", "run", "code-atlas")),
    Case("data-sentinel-forge", ("uv", "run", "data-sentinel")),
    Case("forge-agent-bridge", ("uv", "run", "forge-bridge")),
    Case("forge-cli", ("node", "dist/index.js"), "\x1b"),
    Case("forge-doctor-api", ("uv", "run", "forge-doctor-api")),
    Case("forge-doctor-data", ("uv", "run", "forge-doctor-data")),
    Case("forge-lens", ("uv", "run", "forge-lens")),
    Case("forge-portal", ("node", "tools/portal-cli.mjs"), "q\r"),
    Case("platform-forge", ("uv", "run", "platformforge")),
    Case("product-forge", ("uv", "run", "productforge")),
    Case("spark-forge-aws", ("uv", "run", "sparkforge-aws")),
    Case("spark-forge-azure", ("uv", "run", "sparkforge-azure")),
    Case("the-forge", ("uv", "run", "theforge")),
)


def _environment() -> dict[str, str]:
    markers = ("ACCESS_KEY", "API_KEY", "PASSWORD", "PRIVATE_KEY", "SECRET", "TOKEN")
    return {
        key: value
        for key, value in os.environ.items()
        if not any(marker in key.upper() for marker in markers)
        and key.upper() not in {"VIRTUAL_ENV"}
    }


def _read(process: PtyProcess, seconds: float) -> str:
    deadline = time.monotonic() + seconds
    chunks: list[str] = []
    while time.monotonic() < deadline and process.isalive():
        try:
            value = process.read(4096)
        except (TimeoutError, EOFError, OSError):
            continue
        if value:
            chunks.append(value)
        else:
            time.sleep(0.05)
    return "".join(chunks)


def _visible(text: str) -> bool:
    plain = ANSI_ESCAPE.sub("", text)
    plain = "".join(char for char in plain if char.isprintable() or char in "\r\n\t")
    return bool(plain.strip())


def run_case(case: Case, seconds: float) -> dict[str, Any]:
    cwd = WORKSPACE / case.repo
    row: dict[str, Any] = {"repo": case.repo, "command": " ".join(case.argv), "cwd": str(cwd)}
    if not cwd.is_dir():
        row.update({"status": "FAIL", "reason": "repository missing"})
        return row
    process: PtyProcess | None = None
    try:
        process = PtyProcess.spawn(
            list(case.argv), cwd=str(cwd), env=_environment(), dimensions=(30, 120)
        )
        process.fileobj.settimeout(0.1)
        output = _read(process, seconds)
        visible = _visible(output)
        if process.isalive():
            process.write(case.cancel)
        deadline = time.monotonic() + 2.0
        while process.isalive() and time.monotonic() < deadline:
            _read(process, 0.1)
        cancelled = not process.isalive()
        if process.isalive():
            process.terminate(force=True)
        row.update(
            {
                "status": "PASS" if visible and cancelled else "FAIL",
                "tty": True,
                "visible_home": visible,
                "cancelled_before_mutation": cancelled,
                "exit_code": process.exitstatus,
                "first_screen": output[:500],
            }
        )
        if not visible:
            row["reason"] = "empty visible TTY surface"
        elif not cancelled:
            row["reason"] = "q did not exit within cancellation timeout"
    except (OSError, RuntimeError) as exc:
        row.update({"status": "FAIL", "reason": f"pty spawn failed: {exc}"})
    finally:
        if process is not None and process.isalive():
            process.terminate(force=True)
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    # A cold ``uv run`` may resolve a project environment before the first
    # screen. Keep the default aligned with cli_tty_smoke so a clean machine
    # does not turn startup latency into a false cancellation failure.
    parser.add_argument("--seconds", type=float, default=6.0)
    args = parser.parse_args()
    if args.seconds <= 0:
        parser.error("--seconds must be positive")
    checks = [run_case(case, args.seconds) for case in CASES]
    result = {
        "schema": "forge/cli-tty-cancel-smoke/v1",
        "repository_count": len(CASES),
        "checks": checks,
        "status": "PASS" if all(row["status"] == "PASS" for row in checks) else "FAIL",
    }
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
