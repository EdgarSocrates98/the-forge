"""Native bridge: runs the Forge Doctor API public boundary in a child process.

Invoked as ``python -m theforge_doctorapi.bridge <command> ...`` by ``execute`` (never in
replay). It is the only adapter module that imports ``forge_doctor_api``; it runs in the
specialist's interpreter with the adapter's scrubbed environment, writes one JSON document
on stdout and uses ``FDA-*`` exit lines on stderr for structured failures:

- ``diagnose --target <dir>``: builds a ``ForgeRequest`` (§26, ``build_request``) over a
  ``ProjectContext.from_root`` and runs the spec-070 ``DoctorBoundary`` twice - once for
  the bounded ``ApiHandoffBundle`` (``handle``) and once for the endpoint projections
  (``endpoint_dict``: typed ``ForgeHandoff`` envelope + capabilities +
  ``forge-contracts/1`` ``diagnostic-manifest``). The two scans are deterministic; the
  emitted document asserts the bundle's ``handoff_id`` equals the envelope's - a live
  drift check, not decoration.
- ``verify --file <json>``: strict-parse a Doctor API document -
  ``ApiHandoffBundle.from_dict`` (Model strictness: unknown fields rejected) when the
  payload has handoff-bundle keys, ``ForgeHandoff.parse`` when it has envelope keys; a
  v2 bundle is also integrity-checked (``handoff_id == body_sha256()``). Emits a
  ``{valid, kind, errors, integrity}`` verdict.

Errors: ``FDA-REQUEST-INVALID`` (exit 2) for a malformed target/payload,
``FDA-NATIVE-FAILURE`` (exit 1) for anything else - the detail is the exception type and
message, never a traceback.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REQUEST_INVALID = "FDA-REQUEST-INVALID"
NATIVE_FAILURE = "FDA-NATIVE-FAILURE"
INTEGRITY_MISMATCH = "mismatch"
BUNDLE_KEYS = {"operations", "findings", "breaking_changes", "handoff_version"}
ENVELOPE_KEYS = {"handoff_id", "bundle_ref", "refs"}


def _fail(code: str, detail: str, exit_code: int) -> int:
    print(f"{code}: {detail}", file=sys.stderr)
    return exit_code


class _BridgeRefuse(Exception):
    """A refused bridge call: reported as ``FDA-REQUEST-INVALID`` (exit 2)."""


def _diagnose(target: str) -> dict[str, Any]:
    from forge_doctor_api.core.context import ProjectContext
    from forge_doctor_api.handoff.boundary import DoctorBoundary
    from forge_doctor_api.handoff.protocol import build_request

    root = Path(target)
    if not root.is_dir():
        raise _BridgeRefuse(f"target {target!r} is not a directory")
    context = ProjectContext.from_root(root)
    boundary = DoctorBoundary(context=context)
    request = build_request(target=str(root))
    bundle = boundary.handle(request)
    endpoint = boundary.endpoint_dict(request)
    envelope = endpoint.get("handoff") or {}
    if bundle.handoff_id and envelope.get("handoff_id") != bundle.handoff_id:
        raise _BridgeRefuse(
            "boundary emitted divergent identities: bundle handoff_id "
            f"{bundle.handoff_id!r} != envelope handoff_id "
            f"{envelope.get('handoff_id')!r}")
    return {
        "bundle": bundle.to_dict(),
        "handoff": envelope,
        "capabilities": endpoint.get("capabilities") or [],
        "manifest": endpoint.get("manifest") or {},
    }


def _verify(path: str) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise _BridgeRefuse(f"cannot read payload {path!r}: {exc}") from exc
    if not isinstance(payload, dict):
        raise _BridgeRefuse("payload must be a JSON object")
    keys = set(payload)
    errors: list[str] = []
    integrity = "not-applicable"
    if keys & BUNDLE_KEYS:
        from forge_doctor_api.handoff.model import ApiHandoffBundle

        kind = "api-handoff-bundle"
        try:
            bundle = ApiHandoffBundle.from_dict(payload)
        except Exception as exc:  # noqa: BLE001 - strict-parse errors become verdicts
            bundle = None
            errors.append(f"{type(exc).__name__}: {exc}")
        if bundle is not None and bundle.handoff_version == 2:
            integrity = "ok" if bundle.handoff_id == bundle.body_sha256() \
                else INTEGRITY_MISMATCH
            if integrity == INTEGRITY_MISMATCH:
                errors.append("handoff_id does not equal the recomputed body sha256")
    elif keys & ENVELOPE_KEYS:
        from forge_doctor_api.handoff.protocol import ForgeHandoff, ProtocolError

        kind = "forge-handoff"
        try:
            ForgeHandoff.parse(payload)
        except ProtocolError as exc:
            errors.append(str(exc))
    else:
        kind = None
        errors.append("payload is neither an ApiHandoffBundle (needs one of "
                      f"{sorted(BUNDLE_KEYS)}) nor a ForgeHandoff envelope (needs one of "
                      f"{sorted(ENVELOPE_KEYS)})")
    return {"valid": not errors, "kind": kind, "errors": sorted(errors),
            "integrity": integrity}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m theforge_doctorapi.bridge")
    sub = parser.add_subparsers(dest="command", required=True)
    diag = sub.add_parser("diagnose", help="DoctorBoundary handle + endpoint_dict")
    diag.add_argument("--target", required=True)
    ver = sub.add_parser("verify", help="strict-parse + integrity check of a document")
    ver.add_argument("--file", required=True)
    args = parser.parse_args(argv)
    try:
        document = _diagnose(args.target) if args.command == "diagnose" else _verify(args.file)
    except _BridgeRefuse as exc:
        return _fail(REQUEST_INVALID, str(exc), 2)
    except Exception as exc:  # noqa: BLE001 - the adapter maps the type+message only
        return _fail(NATIVE_FAILURE, f"{type(exc).__name__}: {exc}", 1)
    blob = json.dumps(document, sort_keys=True, ensure_ascii=False).encode("utf-8") + b"\n"
    sys.stdout.buffer.write(blob)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
