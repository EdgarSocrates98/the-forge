"""Opt-in feedback bundle (cyc10-03, §10.12).

Produces a LOCAL, user-inspected bundle the user may choose to attach to a
GitHub issue. No telemetry: nothing is sent anywhere; the file is written
next to the workspace and its contents are printed for review first.
"""

from __future__ import annotations

import json
import platform
import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str]) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return (out.stdout + out.stderr).strip()[:4000]
    except Exception as exc:  # honest: report the failure, never fake output
        return f"unavailable: {exc}"


def main() -> int:
    bundle = {
        "schema": "forge/FeedbackBundle/v1",
        "os": platform.platform(),
        "python": platform.python_version(),
        "theforge_version": _run([sys.executable, "-m", "theforge", "--version"]),
        "doctor": _run([sys.executable, "-m", "theforge", "doctor"]),
        "user_notes": "<descreva o problema ou feedback aqui>",
    }
    path = Path("feedback-bundle.json")
    path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False))
    print(path.read_text())
    print(f"\nwrote {path} — revise e anexe numa issue do GitHub (opt-in).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
