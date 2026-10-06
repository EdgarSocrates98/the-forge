"""``python -m theforge_doctordata.record``: rewrite ``native_surface.json``.

Runs in the specialist's interpreter (``forge_doctor_data`` importable): it records the
*public seam* surface the adapter relies on - not the engine's internals: which boundary
callables exist, which request kinds ``accept_request`` accepts, the emitted bundle's top
level fields and the ``forge-contracts`` version. ``describe`` declares a capability only
for a seam the snapshot marks present, so a drifted specialist degrades to manifest
limitations instead of a runtime surprise.

``--check`` compares the packaged snapshot with a fresh capture and reports drift.
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from theforge_doctordata.catalog import (
    SNAPSHOT_PATH,
    native_fingerprint,
    validate_snapshot,
)

_SEAMS = (
    ("accept_request", "forge_doctor_data.core.forger", "accept_request"),
    ("check_conformance", "forge_doctor_data.core.conformance", "check_conformance"),
)


def _seam(name: str, module_name: str, callable_name: str) -> dict[str, Any]:
    """One seam record: module/callable presence plus its public signature surface."""
    record: dict[str, Any] = {"name": name, "module": module_name,
                              "callable": callable_name, "present": False}
    try:
        module = importlib.import_module(module_name)
    except Exception:
        return record
    target = getattr(module, callable_name, None)
    if not callable(target):
        return record
    record["present"] = True
    try:
        record["parameters"] = sorted(inspect.signature(target).parameters)
    except (TypeError, ValueError):
        record["parameters"] = []
    return record


def capture() -> dict[str, Any]:
    """The native surface snapshot of THIS interpreter's forge_doctor_data."""
    import forge_doctor_data

    seams = [_seam(name, module, callable_name)
             for name, module, callable_name in _SEAMS]
    # The request kinds accept_request documents publicly.
    try:
        from forge_doctor_data.core.forger import REQUEST_KINDS
        request_kinds = sorted(str(k) for k in REQUEST_KINDS)
    except Exception:
        request_kinds = []
    try:
        from forge_doctor_data.contracts.version import CURRENT
        contract_version = str(CURRENT)
    except Exception:
        contract_version = "forge-contracts/1"
    return {
        "specialist_version": str(getattr(forge_doctor_data, "__version__", "")),
        "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "provenance": "recorded",
        "contract_version": contract_version,
        "request_kinds": request_kinds,
        "seams": seams,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m theforge_doctordata.record")
    parser.add_argument("--check", action="store_true",
                        help="do not write; exit 1 when the packaged snapshot drifts")
    parser.add_argument("--out", default=None,
                        help="write the snapshot to this path instead of the packaged one")
    parser.add_argument("--recorded-at", default=None,
                        help="override the recorded_at timestamp (e.g. 'live')")
    args = parser.parse_args(argv)
    fresh = capture()
    if args.recorded_at is not None:
        fresh["recorded_at"] = args.recorded_at
    if args.check:
        try:
            packaged = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"cannot read {SNAPSHOT_PATH.name}: {exc}", file=sys.stderr)
            return 1
        drift = native_fingerprint(packaged) != native_fingerprint(fresh)
        if drift:
            print(f"native surface drifted: packaged "
                  f"{native_fingerprint(packaged)[:12]} != live "
                  f"{native_fingerprint(fresh)[:12]}", file=sys.stderr)
            return 1
        print("native surface unchanged")
        return 0
    validate_snapshot(fresh)
    target = Path(args.out) if args.out else SNAPSHOT_PATH
    target.write_text(
        json.dumps(fresh, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8", newline="\n")
    print(f"recorded native surface {fresh['specialist_version']} -> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
