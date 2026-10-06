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
from typing import Any

REQUEST_INVALID = "FDD-REQUEST-INVALID"
NATIVE_FAILURE = "FDD-NATIVE-FAILURE"
# Keys ``HandoffBundle.bounded`` accepts; anything else is refused before the boundary runs.
BOUNDED_KEYS = ("findings", "entities", "relationships", "capabilities", "plans", "unknowns")


def _fail(code: str, detail: str, exit_code: int) -> int:
    print(f"{code}: {detail}", file=sys.stderr)
    return exit_code


def _scan(target: str, bounded: dict[str, Any] | None) -> dict[str, Any]:
    from forge_doctor_data.core.forger import ForgerRequestError, accept_request

    options: dict[str, Any] = {}
    if bounded:
        unknown = sorted(set(bounded) - set(BOUNDED_KEYS))
        if unknown:
            raise _BridgeRefuse(f"unknown bounded keys {unknown} (valid: {BOUNDED_KEYS})")
        options["bounded"] = {key: int(value) for key, value in bounded.items()}
    try:
        bundle = accept_request({"kind": "scan", "path": target, "options": options})
    except ForgerRequestError as exc:
        raise _BridgeRefuse(str(exc)) from exc
    document: dict[str, Any] = bundle.to_dict()
    return document


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
    scan.add_argument("--bounded", default=None,
                      help="JSON object of HandoffBundle.bounded() limits")
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
            document = _scan(args.target, bounded)
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
