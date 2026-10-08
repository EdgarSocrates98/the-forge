"""Native bridge: runs the Platform Forge public seams in a child process.

Invoked as ``python -m theforge_platformforge.bridge <command> ...`` by ``execute``
(never in replay). It is the only adapter module that imports ``platformforge``; it runs
in the specialist's interpreter with the adapter's scrubbed environment, writes one JSON
document on stdout and uses ``PF-*`` exit lines on stderr for structured failures:

- ``analyze --domain <dom> --repo <dir>``: the offline tree analyzers — ``iac`` →
  ``iac.terraform.analyze_hcl``, ``plan`` → ``iac.plan.analyze_plan``, ``state`` →
  ``iac.plan.analyze_state``, ``k8s`` → ``k8s.manifests.analyze_k8s``, ``secrets`` →
  ``security.scan.scan_secrets``, ``gha`` → ``cicd.github_actions.analyze_gha``,
  ``gitops`` → ``cicd.gitops.analyze_gitops``, ``catalog`` →
  ``product.catalog.analyze_catalog``.
- ``manifest``: ``forge.manifest.capability_manifest()`` → the capability-manifest/v3
  declaration of the installed specialist.

Errors: ``PF-REQUEST-INVALID`` (exit 2) for a malformed request or unknown domain,
``PF-NATIVE-FAILURE`` (exit 1) for anything else — the detail is the exception type and
message, never a traceback.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from typing import Any

REQUEST_INVALID = "PF-REQUEST-INVALID"
NATIVE_FAILURE = "PF-NATIVE-FAILURE"

Analyzer = Callable[[str], dict[str, Any]]


def _analyzers() -> dict[str, Analyzer]:
    """Domain -> public analyzer seam (imported lazily, only inside the bridge)."""
    from platformforge.cicd.github_actions import analyze_gha
    from platformforge.cicd.gitops import analyze_gitops
    from platformforge.iac.plan import analyze_plan, analyze_state
    from platformforge.iac.terraform import analyze_hcl
    from platformforge.k8s.manifests import analyze_k8s
    from platformforge.product.catalog import analyze_catalog
    from platformforge.security.scan import scan_secrets

    return {
        "iac": analyze_hcl,
        "plan": analyze_plan,
        "state": analyze_state,
        "k8s": analyze_k8s,
        "secrets": scan_secrets,
        "gha": analyze_gha,
        "gitops": analyze_gitops,
        "catalog": analyze_catalog,
    }


class _BridgeRefuse(Exception):
    """A refused bridge call: reported as ``PF-REQUEST-INVALID`` (exit 2)."""


def _fail(code: str, detail: str, exit_code: int) -> int:
    print(f"{code}: {detail}", file=sys.stderr)
    return exit_code


def _analyze(domain: str, repo: str) -> dict[str, Any]:
    analyzers = _analyzers()
    analyzer = analyzers.get(domain)
    if analyzer is None:
        raise _BridgeRefuse(
            f"unknown analyze domain {domain!r} (expected one of {sorted(analyzers)})"
        )
    result = analyzer(repo)
    if not isinstance(result, dict):
        raise _BridgeRefuse(f"native seam returned {type(result).__name__}, not a dict")
    return result


def _manifest() -> dict[str, Any]:
    from platformforge.forge.manifest import capability_manifest

    result = capability_manifest()
    if not isinstance(result, dict):
        raise _BridgeRefuse(f"capability_manifest returned {type(result).__name__}")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m theforge_platformforge.bridge")
    sub = parser.add_subparsers(dest="command", required=True)
    analyze = sub.add_parser("analyze", help="domain analyzer over a staged tree")
    analyze.add_argument("--domain", required=True)
    analyze.add_argument("--repo", required=True)
    sub.add_parser("manifest", help="forge.manifest.capability_manifest()")
    args = parser.parse_args(argv)
    try:
        document = (
            _analyze(args.domain, args.repo)
            if args.command == "analyze"
            else _manifest()
        )
    except _BridgeRefuse as exc:
        return _fail(REQUEST_INVALID, str(exc), 2)
    except Exception as exc:  # noqa: BLE001 - the adapter maps the type+message only
        return _fail(NATIVE_FAILURE, f"{type(exc).__name__}: {exc}", 1)
    blob = (
        json.dumps(document, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
        + b"\n"
    )
    sys.stdout.buffer.write(blob)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
