"""``python -m theforge_doctorapi.record``: rewrite ``native_surface.json``.

Runs in the specialist's interpreter (``forge_doctor_api`` importable): it records the
*public seam* surface the adapter relies on - the spec-070 boundary methods, the §26
protocol version, the strict model parses used by ``api.verify``. ``describe`` declares a
capability only for a seam the snapshot marks present, so a drifted specialist degrades
to manifest limitations instead of a runtime surprise.

``--check`` compares the packaged snapshot with a fresh capture and classifies the
drift as ``none``, ``additive`` (exit 0) or ``breaking`` (exit 1).
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

from theforge_doctorapi.catalog import (
    SNAPSHOT_PATH,
    native_fingerprint,
    validate_snapshot,
)

_SEAMS = (
    ("doctor_boundary", "forge_doctor_api.handoff.boundary", "DoctorBoundary"),
    ("request_builder", "forge_doctor_api.handoff.protocol", "build_request"),
    ("handoff_parse", "forge_doctor_api.handoff.model", "ApiHandoffBundle"),
    ("manifest", "forge_doctor_api.contracts.adapters", "report_manifest"),
)


def _seam(name: str, module_name: str, callable_name: str) -> dict[str, Any]:
    """One seam record: module/callable presence plus its public members."""
    record: dict[str, Any] = {
        "name": name,
        "module": module_name,
        "callable": callable_name,
        "present": False,
    }
    try:
        module = importlib.import_module(module_name)
    except Exception:
        return record
    target = getattr(module, callable_name, None)
    if target is None:
        return record
    record["present"] = True
    if name == "doctor_boundary":
        record["methods"] = sorted(
            m
            for m in ("handle", "envelope", "endpoint_dict", "capabilities", "summarize")
            if callable(getattr(target, m, None))
        )
    else:
        try:
            record["parameters"] = sorted(inspect.signature(target).parameters)
        except (TypeError, ValueError):
            record["parameters"] = []
    return record


def capture() -> dict[str, Any]:
    """The native surface snapshot of THIS interpreter's forge_doctor_api."""
    import forge_doctor_api

    seams = [_seam(name, module, callable_name) for name, module, callable_name in _SEAMS]
    try:
        from forge_doctor_api.handoff.protocol import PROTOCOL_VERSION

        protocol_version = int(PROTOCOL_VERSION)
    except Exception:
        protocol_version = 0
    return {
        "specialist_version": str(getattr(forge_doctor_api, "__version__", "")),
        "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "provenance": "recorded",
        "protocol_version": protocol_version,
        "seams": seams,
    }


def classify_drift(
    packaged: dict[str, Any],
    fresh: dict[str, Any],
) -> tuple[str, list[str]]:
    """``none`` | ``additive`` | ``breaking`` drift of ``fresh`` over ``packaged``.

    A seam that disappeared, turned absent or changed its signature, a dropped request
    kind or a ``contract_version`` bump is breaking; a new seam, a new request kind or
    a bare specialist-version bump is a compatible additive drift.
    """
    old = {str(s["name"]): s for s in packaged.get("seams", [])}
    new = {str(s["name"]): s for s in fresh.get("seams", [])}
    breaking = [f"seam removed: {name}" for name in sorted(set(old) - set(new))]
    breaking += [
        f"seam changed: {name}: {old[name]} -> {new[name]}"
        for name in sorted(set(old) & set(new))
        if old[name] != new[name]
    ]
    old_kinds = set(packaged.get("request_kinds", []))
    new_kinds = set(fresh.get("request_kinds", []))
    breaking += [f"request kind removed: {kind}" for kind in sorted(old_kinds - new_kinds)]
    for key in sorted(set(packaged) | set(fresh)):
        if key in {"seams", "request_kinds", "specialist_version", "recorded_at", "provenance"}:
            continue
        if packaged.get(key) != fresh.get(key):
            breaking.append(f"{key} {packaged.get(key)} -> {fresh.get(key)}")
    notes = [f"seam added: {name}" for name in sorted(set(new) - set(old))]
    notes += [f"request kind added: {kind}" for kind in sorted(new_kinds - old_kinds)]
    if packaged.get("specialist_version") != fresh.get("specialist_version"):
        notes.append(
            f"specialist version {packaged.get('specialist_version')} -> "
            f"{fresh.get('specialist_version')}"
        )
    if breaking:
        return "breaking", [*breaking, *notes]
    return ("additive" if notes else "none"), notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m theforge_doctorapi.record")
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not write; classify drift over the packaged snapshot "
        "(none|additive|breaking; exit 1 on breaking)",
    )
    parser.add_argument(
        "--out", default=None, help="write the snapshot to this path instead of the packaged one"
    )
    parser.add_argument(
        "--recorded-at", default=None, help="override the recorded_at timestamp (e.g. 'live')"
    )
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
        status, lines = classify_drift(packaged, fresh)
        print(f"surface drift: {status}")
        for line in lines:
            print(f"  {line}")
        if status != "none":
            print(
                f"packaged {native_fingerprint(packaged)[:12]} != live "
                f"{native_fingerprint(fresh)[:12]}"
            )
        return 1 if status == "breaking" else 0
    validate_snapshot(fresh)
    target = Path(args.out) if args.out else SNAPSHOT_PATH
    target.write_text(
        json.dumps(fresh, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"recorded native surface {fresh['specialist_version']} -> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
