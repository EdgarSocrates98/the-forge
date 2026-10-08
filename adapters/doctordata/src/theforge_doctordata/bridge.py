"""Native bridge: runs the Forge Doctor Data public boundary in a child process.

Invoked as ``python -m theforge_doctordata.bridge <command> ...`` by ``execute`` (never in
replay). It is the only adapter module that imports ``forge_doctor_data``; it runs in the
specialist's interpreter with the adapter's scrubbed environment, writes one JSON document
on stdout and uses ``FDD-*`` exit lines on stderr for structured failures:

- ``scan --target <dir> [--bounded '{...}']``: ``accept_request`` (spec 267/§5) with
  ``{"kind": "scan", "path": <dir>, "options": {"bounded": <limits>}}`` → the
  ``forge-contracts/1`` ``HandoffBundle`` dict.
- ``conformance --file <json>``: ``check_conformance`` (the ``contracts conformance`` seam
  documented for Forge tools) → the verdict dict.

Errors: ``FDD-REQUEST-INVALID`` (exit 2) for a malformed request or unreadable input,
``FDD-NATIVE-FAILURE`` (exit 1) for anything else — the detail is the exception type and
message, never a traceback.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REQUEST_INVALID = "FDD-REQUEST-INVALID"
NATIVE_FAILURE = "FDD-NATIVE-FAILURE"
# Keys ``HandoffBundle.bounded`` accepts; anything else is refused before the boundary runs.
BOUNDED_KEYS = ("findings", "entities", "relationships", "capabilities", "plans", "unknowns")


def _fail(code: str, detail: str, exit_code: int) -> int:
    print(f"{code}: {detail}", file=sys.stderr)
    return exit_code


def _scan(
    target: str,
    bounded: dict[str, Any] | None,
    delta_baseline: str | None = None,
    delta_changed: list[str] | None = None,
) -> dict[str, Any]:
    from forge_doctor_data.core.forger import ForgerRequestError, accept_request

    if bounded:
        unknown = sorted(set(bounded) - set(BOUNDED_KEYS))
        if unknown:
            raise _BridgeRefuse(f"unknown bounded keys {unknown} (valid: {BOUNDED_KEYS})")
    limits = {key: int(value) for key, value in (bounded or {}).items()}
    if delta_baseline is None and delta_changed is None:
        try:
            bundle = accept_request(
                {"kind": "scan", "path": target, "options": {"bounded": limits} if limits else {}}
            )
        except ForgerRequestError as exc:
            raise _BridgeRefuse(str(exc)) from exc
        plain: dict[str, Any] = bundle.to_dict()
        return plain
    # delta/v1: one scan — the report is needed to snapshot the current state.
    # ``accept_request`` cannot hand it back, so the delta path replicates its
    # normalize tail (bounded + x-forge-data extension) over the same seams.
    from forge_doctor_data.contracts import HandoffBundle
    from forge_doctor_data.core.handoff import build_handoff_bundle
    from forge_doctor_data.core.service import ScanRequest, ScanService

    outcome = ScanService().run(ScanRequest(path=Path(target)))
    bundle = HandoffBundle.from_dict(build_handoff_bundle(outcome.report, outcome.ctx))
    if limits:
        bundle = bundle.bounded(**{k: limits.get(k) for k in BOUNDED_KEYS})
    bundle.extensions["x-forge-data"] = {
        "request_kind": "scan",
        "bounded": bool(limits),
        **({"limits": dict(sorted(limits.items()))} if limits else {}),
    }
    document: dict[str, Any] = bundle.to_dict()
    document["delta"] = _scan_delta(
        Path(target), delta_baseline or "", delta_changed or [], outcome
    )
    return document


def _scan_delta(
    root: Path,
    ref: str,
    changed: list[str],
    outcome: Any,
) -> dict[str, Any]:
    """The ``delta`` section of a scan document: ``diff_snapshots`` of the resolved
    baseline against a freshly recorded snapshot — never a fabricated one.

    The baseline lives in the specialist's own store (``.forge-doctor-data/history``),
    staged with the workspace; the current snapshot is recorded inside the stage, so
    the real workspace's history stays the specialist's to write.
    """
    from forge_doctor_data.core.history import (
        HistoryError,
        diff_snapshots,
        list_snapshots,
        load_snapshot,
        record_snapshot,
        resolve_snapshot,
    )

    delta: dict[str, Any] = {"changed_files": sorted(changed)}
    prev = None
    try:
        if ref:
            prev = load_snapshot(resolve_snapshot(root, ref))
        else:
            snaps = list_snapshots(root)
            if snaps:
                prev = load_snapshot(snaps[-1])
        delta["baseline_ref"] = prev.name if prev is not None else ref or "latest"
        if prev is None:
            delta["unresolved"] = (
                "no baseline snapshot under .forge-doctor-data/history in the staged "
                "workspace; the full scan was reported"
            )
    except HistoryError as exc:
        delta["baseline_ref"] = ref or "latest"
        delta["unresolved"] = f"baseline unresolved: {exc}"
    try:
        current = load_snapshot(record_snapshot(outcome.report, root, outcome.ctx))
    except Exception as exc:  # noqa: BLE001 - snapshotting never masks the scan
        delta["unresolved"] = f"current snapshot failed to record: {exc}"
        return delta
    if prev is not None:
        diff = diff_snapshots(prev, current)
        delta.update(
            {
                "older": diff.older,
                "newer": diff.newer,
                "new_findings": list(diff.new_findings),
                "resolved_findings": list(diff.resolved_findings),
                "entities_added": list(diff.entities_added),
                "entities_removed": list(diff.entities_removed),
                "capability_transitions": list(diff.capability_transitions),
                "drift_added": list(diff.drift_added),
                "drift_resolved": list(diff.drift_resolved),
            }
        )
    return delta


def _conformance(path: str) -> dict[str, Any]:
    from forge_doctor_data.core.conformance import check_conformance

    try:
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise _BridgeRefuse(f"cannot read conformance payload {path!r}: {exc}") from exc
    result: dict[str, Any] = check_conformance(payload, None).to_dict()
    return result


class _BridgeRefuse(Exception):
    """A refused bridge call: reported as ``FDD-REQUEST-INVALID`` (exit 2)."""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m theforge_doctordata.bridge")
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan", help="accept_request kind=scan -> HandoffBundle JSON")
    scan.add_argument("--target", required=True)
    scan.add_argument(
        "--bounded", default=None, help="JSON object of HandoffBundle.bounded() limits"
    )
    scan.add_argument(
        "--delta-baseline",
        default=None,
        help="history snapshot ref the delta diffs against (''/unset with changed-files = newest)",
    )
    scan.add_argument(
        "--delta-changed-files",
        default=None,
        help="JSON array of workspace-relative changed paths (hint)",
    )
    conf = sub.add_parser("conformance", help="check_conformance of a JSON file")
    conf.add_argument("--file", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "scan":
            bounded = None
            if args.bounded is not None:
                bounded = json.loads(args.bounded)
                if not isinstance(bounded, dict):
                    raise _BridgeRefuse("--bounded must be a JSON object")
            changed = None
            if args.delta_changed_files is not None:
                changed = json.loads(args.delta_changed_files)
                if not isinstance(changed, list) or not all(isinstance(p, str) for p in changed):
                    raise _BridgeRefuse("--delta-changed-files must be a JSON array of strings")
            document = _scan(args.target, bounded, args.delta_baseline, changed)
        else:
            document = _conformance(args.file)
    except _BridgeRefuse as exc:
        return _fail(REQUEST_INVALID, str(exc), 2)
    except Exception as exc:  # noqa: BLE001 - the adapter maps the type+message only
        return _fail(NATIVE_FAILURE, f"{type(exc).__name__}: {exc}", 1)
    blob = json.dumps(document, sort_keys=True, ensure_ascii=False).encode("utf-8") + b"\n"
    sys.stdout.buffer.write(blob)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
