"""``python -m theforge_sparkforge_azure.record``: rewrite ``native_surface.json``.

Runs in the specialist's interpreter (``sparkforge_azure`` importable): it records the
*public seam* surface the adapter relies on — which boundary callables exist, their public
signatures, the agent-facing ``adapters.tools`` table and the declared
``SPECIALIST_DOMAINS``. ``describe`` declares a capability only for a seam the snapshot
marks present, so a drifted specialist degrades to manifest limitations instead of a
runtime surprise.

``--check`` compares the packaged snapshot with a fresh capture and classifies the
drift as ``none``, ``additive`` (exit 0) or ``breaking`` (exit 1).
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from theforge_sparkforge_azure.catalog import (
    SNAPSHOT_PATH,
    native_fingerprint,
    validate_snapshot,
)

_SEAMS = (
    ("sdd_check", "sparkforge_azure.sdd.checks", "check"),
    ("sdd_status", "sparkforge_azure.sdd.status", "status"),
    ("access_diagnose", "sparkforge_azure.azure.pipeline", "run_case"),
    ("fabric_diagnose", "sparkforge_azure.fabric.pipeline", "run_fabric_case"),
    ("doctor_run", "sparkforge_azure.doctor", "run"),
)


def _seam(name: str, module_name: str, callable_name: str) -> dict[str, Any]:
    """One seam record: module/callable presence plus its public signature surface."""
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
    if not callable(target):
        return record
    record["present"] = True
    try:
        record["parameters"] = sorted(inspect.signature(target).parameters)
    except (TypeError, ValueError):
        record["parameters"] = []
    return record


def capture() -> dict[str, Any]:
    """The native surface snapshot of THIS interpreter's sparkforge_azure."""
    import sparkforge_azure

    seams = [_seam(name, module, callable_name) for name, module, callable_name in _SEAMS]
    try:
        from sparkforge_azure.adapters.tools import TOOLS

        tools = sorted(str(t) for t in TOOLS)
    except Exception:
        tools = []
    try:
        from sparkforge_azure.agentmanifest.model import SPECIALIST_DOMAINS

        domains = sorted(str(d) for d in SPECIALIST_DOMAINS)
    except Exception:
        domains = []
    return {
        "specialist_version": str(getattr(sparkforge_azure, "__version__", "")),
        "recorded_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "provenance": "recorded",
        "tools": tools,
        "specialist_domains": domains,
        "seams": seams,
    }


def classify_drift(
    packaged: dict[str, Any],
    fresh: dict[str, Any],
) -> tuple[str, list[str]]:
    """``none`` | ``additive`` | ``breaking`` drift of ``fresh`` over ``packaged``.

    A seam that disappeared, turned absent or changed its signature, a dropped tool or a
    removed specialist domain is breaking; a new seam, tool or domain, or a bare
    specialist-version bump is a compatible additive drift.
    """
    old = {str(s["name"]): s for s in packaged.get("seams", [])}
    new = {str(s["name"]): s for s in fresh.get("seams", [])}
    breaking = [f"seam removed: {name}" for name in sorted(set(old) - set(new))]
    breaking += [
        f"seam changed: {name}: {old[name]} -> {new[name]}"
        for name in sorted(set(old) & set(new))
        if old[name] != new[name]
    ]
    for list_key, label in (("tools", "tool"), ("specialist_domains", "domain")):
        old_items = set(packaged.get(list_key, []))
        new_items = set(fresh.get(list_key, []))
        breaking += [f"{label} removed: {item}" for item in sorted(old_items - new_items)]
    notes = [f"seam added: {name}" for name in sorted(set(new) - set(old))]
    for list_key, label in (("tools", "tool"), ("specialist_domains", "domain")):
        notes += [
            f"{label} added: {item}"
            for item in sorted(set(fresh.get(list_key, [])) - set(packaged.get(list_key, [])))
        ]
    if packaged.get("specialist_version") != fresh.get("specialist_version"):
        notes.append(
            f"specialist version {packaged.get('specialist_version')} -> "
            f"{fresh.get('specialist_version')}"
        )
    if breaking:
        return "breaking", [*breaking, *notes]
    return ("additive" if notes else "none"), notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m theforge_sparkforge_azure.record")
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
