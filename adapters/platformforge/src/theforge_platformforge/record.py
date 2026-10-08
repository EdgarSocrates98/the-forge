"""``python -m theforge_platformforge.record``: rewrite ``native_surface.json``.

Runs in the specialist's interpreter (``platformforge`` importable): it records the
*public seam* surface the adapter relies on — which boundary callables exist, their public
signatures, plus the specialist's own ``capability-manifest/v3`` declaration (tools,
domains and the ``cross_forge.accepts`` vocabulary — surface evidence, never a claimed
capability). ``describe`` declares a capability only for a seam the snapshot marks
present, so a drifted specialist degrades to manifest limitations instead of a runtime
surprise.

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

from theforge_platformforge.catalog import (
    SNAPSHOT_PATH,
    native_fingerprint,
    validate_snapshot,
)

_SEAMS = (
    ("iac_analyze", "platformforge.iac.terraform", "analyze_hcl"),
    ("plan_review", "platformforge.iac.plan", "analyze_plan"),
    ("state_analyze", "platformforge.iac.plan", "analyze_state"),
    ("k8s_analyze", "platformforge.k8s.manifests", "analyze_k8s"),
    ("secrets_scan", "platformforge.security.scan", "scan_secrets"),
    ("gha_analyze", "platformforge.cicd.github_actions", "analyze_gha"),
    ("gitops_analyze", "platformforge.cicd.gitops", "analyze_gitops"),
    ("catalog_analyze", "platformforge.product.catalog", "analyze_catalog"),
    ("capability_manifest", "platformforge.forge.manifest", "capability_manifest"),
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
    """The native surface snapshot of THIS interpreter's platformforge."""
    import platformforge

    seams = [_seam(name, module, callable_name) for name, module, callable_name in _SEAMS]
    tools: list[str] = []
    domains: list[str] = []
    accepts: list[str] = []
    manifest_schema = ""
    try:
        from platformforge.forge.manifest import capability_manifest

        manifest = capability_manifest()
        manifest_schema = str(manifest.get("manifest", ""))
        raw_tools = manifest.get("tools")
        tools = (
            sorted(raw_tools)
            if isinstance(raw_tools, dict)
            else sorted(str(t) for t in raw_tools or ())
        )
        domains = sorted(str(d) for d in manifest.get("domains") or ())
        cross_forge = manifest.get("cross_forge")
        if isinstance(cross_forge, dict):
            accepts = sorted(str(a) for a in cross_forge.get("accepts") or ())
    except Exception:
        pass
    return {
        "specialist_version": str(getattr(platformforge, "__version__", "")),
        "recorded_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "provenance": "recorded",
        "manifest_schema": manifest_schema,
        "tools": tools,
        "domains": domains,
        "cross_forge_accepts": accepts,
        "seams": seams,
    }


def classify_drift(
    packaged: dict[str, Any],
    fresh: dict[str, Any],
) -> tuple[str, list[str]]:
    """``none`` | ``additive`` | ``breaking`` drift of ``fresh`` over ``packaged``.

    A seam that disappeared, turned absent or changed its signature, a dropped tool,
    domain, cross-forge acceptance or manifest schema is breaking; a new seam, tool or
    domain, or a bare specialist-version bump is a compatible additive drift.
    """
    old = {str(s["name"]): s for s in packaged.get("seams", [])}
    new = {str(s["name"]): s for s in fresh.get("seams", [])}
    breaking = [f"seam removed: {name}" for name in sorted(set(old) - set(new))]
    breaking += [
        f"seam changed: {name}: {old[name]} -> {new[name]}"
        for name in sorted(set(old) & set(new))
        if old[name] != new[name]
    ]
    for list_key, label in (
        ("tools", "tool"),
        ("domains", "domain"),
        ("cross_forge_accepts", "cross-forge accept"),
    ):
        old_items = set(packaged.get(list_key, []))
        new_items = set(fresh.get(list_key, []))
        breaking += [f"{label} removed: {item}" for item in sorted(old_items - new_items)]
    if packaged.get("manifest_schema") != fresh.get("manifest_schema"):
        breaking.append(
            f"manifest schema changed: {packaged.get('manifest_schema')!r} -> "
            f"{fresh.get('manifest_schema')!r}"
        )
    notes = [f"seam added: {name}" for name in sorted(set(new) - set(old))]
    for list_key, label in (
        ("tools", "tool"),
        ("domains", "domain"),
        ("cross_forge_accepts", "cross-forge accept"),
    ):
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
    parser = argparse.ArgumentParser(prog="python -m theforge_platformforge.record")
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
