"""Re-record ``native_catalog.json`` (and a replay ``environment.json``) from the installed
Spark Forge: ``python -m theforge_sparkforge.record [--output PATH] [--environment DIR]``.

Run it in the Spark Forge's own interpreter. It is the only module that imports
``sparkforge.adapters.tools.TOOLS``: describe reads the recorded snapshot instead (importing the
tool surface costs seconds). The snapshot keeps, per tool, its MCP annotations and its required
arguments, plus the origin ``specialist_version``. The output is deterministic: sorted keys and
lists, LF endings, and ``recorded_at`` (UTC date) only changes when the recorded surface does.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from theforge_sparkforge.backend import live_unavailable_reason

SNAPSHOT_PATH = Path(__file__).with_name("native_catalog.json")
ENVIRONMENT_FILE = "environment.json"


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _tool_entry(spec: Mapping[str, Any]) -> dict[str, Any]:
    annotations = spec.get("annotations")
    schema = spec.get("inputSchema")
    required = schema.get("required") if isinstance(schema, Mapping) else None
    return {
        "annotations": dict(annotations) if isinstance(annotations, Mapping) else {},
        "required": sorted(str(name) for name in required) if isinstance(required, list) else [],
    }


def build_snapshot(tools: Mapping[str, Mapping[str, Any]], specialist_version: str, *,
                   today: str | None = None, previous: Mapping[str, Any] | None = None
                   ) -> dict[str, Any]:
    """The snapshot of ``tools`` (``TOOLS`` of the Spark Forge): annotations and required
    arguments per tool. ``recorded_at`` is kept from ``previous`` when nothing else changed."""
    surface = {name: _tool_entry(spec) for name, spec in sorted(tools.items())}
    recorded_at = today or _today()
    if (previous is not None and previous.get("tools") == surface
            and previous.get("specialist_version") == specialist_version
            and isinstance(previous.get("recorded_at"), str)):
        recorded_at = previous["recorded_at"]
    return {"recorded_at": recorded_at, "specialist_version": specialist_version,
            "tools": surface}


def render(data: Mapping[str, Any]) -> str:
    """Canonical text of a recorded JSON file: sorted keys, 2-space indent, final LF."""
    return json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def environment() -> dict[str, Any]:
    """The replay ``environment.json`` of this interpreter (``{python, specialist_version}``)."""
    import sparkforge  # the specialist's public version; light import

    return {"python": platform.python_version(),
            "specialist_version": str(sparkforge.__version__)}


def _read(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _write(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(render(data))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m theforge_sparkforge.record",
        description="Re-record the Spark Forge tool snapshot from the installed specialist.")
    parser.add_argument("--output", type=Path, default=SNAPSHOT_PATH,
                        help="snapshot file to write (default: the packaged native_catalog.json)")
    parser.add_argument("--environment", type=Path, default=None, metavar="DIR",
                        help="also write DIR/environment.json for a replay scenario")
    args = parser.parse_args(argv)
    reason = live_unavailable_reason()
    if reason is not None:
        print(f"record: {reason}", file=sys.stderr)
        return 2
    import sparkforge
    from sparkforge.adapters.tools import TOOLS

    snapshot = build_snapshot(TOOLS, str(sparkforge.__version__), previous=_read(args.output))
    _write(args.output, snapshot)
    print(f"record: {len(snapshot['tools'])} tools of sparkforge "
          f"{snapshot['specialist_version']} -> {args.output}")
    if args.environment is not None:
        target = args.environment / ENVIRONMENT_FILE
        _write(target, environment())
        print(f"record: environment -> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
