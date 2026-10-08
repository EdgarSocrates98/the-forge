"""Native bridge: runs the Spark Forge Azure public seams in a child process.

Invoked as ``python -m theforge_sparkforge_azure.bridge <command> ...`` by ``execute``
(never in replay). It is the only adapter module that imports ``sparkforge_azure``; it runs
in the specialist's interpreter with the adapter's scrubbed environment, writes one JSON
document on stdout and uses ``SFA-*`` exit lines on stderr for structured failures:

- ``sdd-check --repo <dir> [--root docs/sdd]``: ``sdd.checks.check`` → the gate verdict dict.
- ``sdd-status --repo <dir> [--root docs/sdd]``: ``sdd.status.status`` → the phase report.
- ``access-diagnose --bundle <dir> [--profile balanced]``: ``azure.pipeline.run_case``.
- ``fabric-diagnose --bundle <dir> [--profile balanced]``: ``fabric.pipeline.run_fabric_case``.
- ``doctor``: ``doctor.run()`` → the specialist's own environment/capability report.

Errors: ``SFA-REQUEST-INVALID`` (exit 2) for a malformed request or unreadable input,
``SFA-NATIVE-FAILURE`` (exit 1) for anything else — the detail is the exception type and
message, never a traceback.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

REQUEST_INVALID = "SFA-REQUEST-INVALID"
NATIVE_FAILURE = "SFA-NATIVE-FAILURE"
PROFILES = ("minimal", "balanced", "strict")


def _fail(code: str, detail: str, exit_code: int) -> int:
    print(f"{code}: {detail}", file=sys.stderr)
    return exit_code


def _sdd_check(repo: str, root: str, feature: str | None) -> dict[str, Any]:
    from sparkforge_azure.sdd.checks import check

    result: dict[str, Any] = check(repo, root=root, feature=feature)
    return result


def _sdd_status(repo: str, root: str) -> dict[str, Any]:
    from sparkforge_azure.sdd.status import status

    result: dict[str, Any] = status(repo, root=root)
    return result


def _access_diagnose(bundle: str, profile: str, *, fabric: bool) -> dict[str, Any]:
    if profile not in PROFILES:
        raise _BridgeRefuse(f"profile must be one of {PROFILES} (got {profile!r})")
    if fabric:
        from sparkforge_azure.fabric.pipeline import run_fabric_case

        result = run_fabric_case(bundle, profile=profile)
    else:
        from sparkforge_azure.azure.pipeline import run_case

        result = run_case(bundle, profile=profile)
    if not isinstance(result, dict):
        raise _BridgeRefuse(f"native seam returned {type(result).__name__}, not a dict")
    return result


def _doctor() -> dict[str, Any]:
    from sparkforge_azure.doctor import run

    result: dict[str, Any] = run()
    return result


class _BridgeRefuse(Exception):
    """A refused bridge call: reported as ``SFA-REQUEST-INVALID`` (exit 2)."""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m theforge_sparkforge_azure.bridge")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("sdd-check", help="sdd.checks.check over a staged docs/sdd tree")
    check.add_argument("--repo", required=True)
    check.add_argument("--root", default="docs/sdd")
    check.add_argument("--feature", default=None)
    status = sub.add_parser("sdd-status", help="sdd.status.status over a staged docs/sdd tree")
    status.add_argument("--repo", required=True)
    status.add_argument("--root", default="docs/sdd")
    diag = sub.add_parser(
        "access-diagnose", help="azure.pipeline.run_case over a staged case bundle"
    )
    diag.add_argument("--bundle", required=True)
    diag.add_argument("--profile", default="balanced")
    fab = sub.add_parser(
        "fabric-diagnose", help="fabric.pipeline.run_fabric_case over a staged case bundle"
    )
    fab.add_argument("--bundle", required=True)
    fab.add_argument("--profile", default="balanced")
    sub.add_parser("doctor", help="doctor.run() environment report")
    args = parser.parse_args(argv)
    try:
        if args.command == "sdd-check":
            document = _sdd_check(args.repo, args.root, args.feature)
        elif args.command == "sdd-status":
            document = _sdd_status(args.repo, args.root)
        elif args.command == "access-diagnose":
            document = _access_diagnose(args.bundle, args.profile, fabric=False)
        elif args.command == "fabric-diagnose":
            document = _access_diagnose(args.bundle, args.profile, fabric=True)
        else:
            document = _doctor()
    except _BridgeRefuse as exc:
        return _fail(REQUEST_INVALID, str(exc), 2)
    except Exception as exc:  # noqa: BLE001 - the adapter maps the type+message only
        return _fail(NATIVE_FAILURE, f"{type(exc).__name__}: {exc}", 1)
    blob = json.dumps(document, sort_keys=True, ensure_ascii=False).encode("utf-8") + b"\n"
    sys.stdout.buffer.write(blob)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
