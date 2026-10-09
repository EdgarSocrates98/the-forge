"""Re-record ``native_catalog.json`` (and a replay ``environment.json`` + ``health.json``) from
the installed Spark Forge AWS: ``python -m theforge_sparkforge_aws.record [--output PATH]
[--environment DIR]``.

Run it in the Spark Forge AWS's own interpreter. It is the only module that imports the tool
surface (``sparkforge_aws.adapters.tools.TOOLS``, or pre-rename ``sparkforge.adapters.tools``,
through ``native_pkg``): describe reads the recorded snapshot instead (importing the
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

from theforge_sparkforge_aws import health
from theforge_sparkforge_aws.backend import live_unavailable_reason

SNAPSHOT_PATH = Path(__file__).with_name("native_catalog.json")
ENVIRONMENT_FILE = "environment.json"
HEALTH_FILE = "health.json"


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


def build_snapshot(
    tools: Mapping[str, Mapping[str, Any]],
    specialist_version: str,
    *,
    today: str | None = None,
    previous: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The snapshot of ``tools`` (``TOOLS`` of the Spark Forge AWS): annotations and required
    arguments per tool. ``recorded_at`` is kept from ``previous`` when nothing else changed."""
    surface = {name: _tool_entry(spec) for name, spec in sorted(tools.items())}
    recorded_at = today or _today()
    if (
        previous is not None
        and previous.get("tools") == surface
        and previous.get("specialist_version") == specialist_version
        and isinstance(previous.get("recorded_at"), str)
    ):
        recorded_at = previous["recorded_at"]
    return {"recorded_at": recorded_at, "specialist_version": specialist_version, "tools": surface}


def render(data: Mapping[str, Any]) -> str:
    """Canonical text of a recorded JSON file: sorted keys, 2-space indent, final LF."""
    return json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def environment() -> dict[str, Any]:
    """The replay ``environment.json`` of this interpreter (``{python, specialist_version}``)."""
    from theforge_sparkforge_aws.native_pkg import installed_version

    return {"python": platform.python_version(), "specialist_version": str(installed_version())}


def health_probes() -> dict[str, Any]:
    """The replay ``health.json`` of this interpreter: the native probes health makes
    (``{dispatcher, specialist_version}``), with the dispatcher found but never imported."""
    observation = health.observe_live()
    return {
        "dispatcher": observation.dispatcher,
        "specialist_version": observation.specialist_version,
    }


def _read(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def classify_drift(
    packaged: Mapping[str, Any],
    fresh: Mapping[str, Any],
) -> tuple[str, list[str]]:
    """``none`` | ``additive`` | ``breaking`` drift of ``fresh`` over ``packaged``.

    A tool that disappeared or whose recorded attributes changed (annotations or
    required arguments) is breaking; a tool that only appeared — or a bare
    specialist-version bump — is a compatible additive drift.
    """
    old = packaged.get("tools")
    new = fresh.get("tools")
    old = dict(old) if isinstance(old, Mapping) else {}
    new = dict(new) if isinstance(new, Mapping) else {}
    breaking = [f"tool removed: {name}" for name in sorted(set(old) - set(new))]
    breaking += [
        f"tool changed: {name}: {old[name]} -> {new[name]}"
        for name in sorted(set(old) & set(new))
        if old[name] != new[name]
    ]
    notes = [f"tool added: {name}" for name in sorted(set(new) - set(old))]
    if packaged.get("specialist_version") != fresh.get("specialist_version"):
        notes.append(
            f"specialist version {packaged.get('specialist_version')} -> "
            f"{fresh.get('specialist_version')}"
        )
    if breaking:
        return "breaking", [*breaking, *notes]
    return ("additive" if notes else "none"), notes


def _check(path: Path, fresh: Mapping[str, Any]) -> int:
    packaged = _read(path)
    if packaged is None:
        print(f"record --check: cannot read {path}", file=sys.stderr)
        return 1
    status, lines = classify_drift(packaged, fresh)
    print(f"surface drift: {status}")
    for line in lines:
        print(f"  {line}")
    return 1 if status == "breaking" else 0


def _write(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(render(data))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m theforge_sparkforge_aws.record",
        description="Re-record the Spark Forge AWS tool snapshot from the installed specialist.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=SNAPSHOT_PATH,
        help="snapshot file to write (default: the packaged native_catalog.json); "
        "with --check, the recorded snapshot to compare against",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not write; classify drift of the live tool surface over the "
        "recorded snapshot (none|additive|breaking; exit 1 on breaking)",
    )
    parser.add_argument(
        "--environment",
        type=Path,
        default=None,
        metavar="DIR",
        help="also write DIR/environment.json and DIR/health.json for a replay scenario",
    )
    args = parser.parse_args(argv)
    reason = live_unavailable_reason()
    if reason is not None:
        print(f"record: {reason}", file=sys.stderr)
        return 2
    from theforge_sparkforge_aws.native_pkg import import_tools, installed_version

    tools_surface, _call_tool = import_tools()
    snapshot = build_snapshot(tools_surface, str(installed_version()), previous=_read(args.output))
    if args.check:
        return _check(args.output, snapshot)
    _write(args.output, snapshot)
    print(
        f"record: {len(snapshot['tools'])} tools of sparkforge "
        f"{snapshot['specialist_version']} -> {args.output}"
    )
    if args.environment is not None:
        target = args.environment / ENVIRONMENT_FILE
        _write(target, environment())
        print(f"record: environment -> {target}")
        probes = args.environment / HEALTH_FILE
        _write(probes, health_probes())
        print(f"record: health -> {probes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
