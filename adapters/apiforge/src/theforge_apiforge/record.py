"""Re-record ``native_matrix.json`` from the installed API Forge.

Run in the API Forge interpreter (Python 3.12 with ``apiforge``)::

    python -m theforge_apiforge.record [--out PATH] [--recorded-at TIMESTAMP]

It reads the public capability matrix through ``apiforge.capabilities.load_capabilities``
and writes ``{specialist_version, recorded_at, provenance, capabilities: [{capability_id,
state, risk, limitations}]}`` deterministically: records sorted by id, limitations sorted and
deduplicated, keys sorted, two-space indent, LF line endings. Two runs over the same API Forge
differ only in ``recorded_at``.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from theforge_apiforge.backend import live_environment_problem
from theforge_apiforge.catalog import SNAPSHOT_PATH, validate_snapshot
from theforge_apiforge.health import cli_found

RECORDED = "recorded"


def _record_entry(item: object) -> dict[str, Any]:
    limitations = getattr(item, "limitations", ()) or ()
    return {
        "capability_id": str(getattr(item, "capability_id")),  # noqa: B009
        "state": str(getattr(item, "state")),  # noqa: B009
        "risk": str(getattr(item, "risk")),  # noqa: B009
        "limitations": sorted({str(text) for text in limitations}),
    }


def build_snapshot(records: Iterable[object], *, specialist_version: str, recorded_at: str,
                   provenance: str = RECORDED) -> dict[str, Any]:
    """The snapshot of native capability records (objects with the matrix attributes)."""
    entries = sorted((_record_entry(item) for item in records),
                     key=lambda entry: entry["capability_id"])
    return validate_snapshot({
        "specialist_version": specialist_version,
        "recorded_at": recorded_at,
        "provenance": provenance,
        "capabilities": entries,
    })


def encode_snapshot(snapshot: dict[str, Any]) -> bytes:
    """The canonical bytes of a snapshot (sorted keys, indent 2, LF, trailing newline)."""
    text = json.dumps(snapshot, indent=2, sort_keys=True, ensure_ascii=False)
    return (text + "\n").encode("utf-8")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def environment() -> dict[str, Any]:
    """The replay ``environment.json`` of this interpreter (``{python,
    specialist_version}``)."""
    import apiforge  # the specialist's public version; light import

    return {"python": platform.python_version(),
            "specialist_version": str(apiforge.__version__),
            "provenance": RECORDED}


def health_probes() -> dict[str, Any]:
    """The replay ``health.json`` of this interpreter: the ``cli`` probe health makes
    (``find_spec``, never imported)."""
    import apiforge

    return {"cli": cli_found(),
            "provenance": RECORDED,
            "recorded_with": (f"apiforge {apiforge.__version__}, Python "
                              f"{platform.python_version()}, {sys.platform}: "
                              f"importlib.util.find_spec('apiforge.cli') is not None")}


def _write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encode_snapshot(data))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m theforge_apiforge.record",
                                     description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--out", type=Path, default=SNAPSHOT_PATH,
                        help="snapshot path (default: the packaged native_matrix.json)")
    parser.add_argument("--recorded-at", default=None,
                        help="timestamp to record (default: now, UTC)")
    parser.add_argument("--environment", type=Path, default=None, metavar="DIR",
                        help="also write DIR/environment.json and DIR/health.json for a "
                             "replay scenario")
    args = parser.parse_args(argv)
    problem = live_environment_problem()
    if problem is not None:
        print(f"theforge_apiforge.record: {problem}", file=sys.stderr)
        return 2
    import apiforge
    from apiforge.capabilities import load_capabilities

    snapshot = build_snapshot(load_capabilities(),
                              specialist_version=str(apiforge.__version__),
                              recorded_at=args.recorded_at or _utc_now())
    args.out.write_bytes(encode_snapshot(snapshot))
    print(f"recorded {len(snapshot['capabilities'])} capabilities from apiforge "
          f"{snapshot['specialist_version']} to {args.out}")
    if args.environment is not None:
        target = args.environment / "environment.json"
        _write(target, environment())
        print(f"recorded environment -> {target}")
        probes = args.environment / "health.json"
        _write(probes, health_probes())
        print(f"recorded health -> {probes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
