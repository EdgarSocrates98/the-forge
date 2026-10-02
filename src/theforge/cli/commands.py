"""Command handlers: gather data, render (text or JSON), return the exit code."""

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from theforge.cli import render
from theforge.contracts import to_dict
from theforge.environment import run_doctor
from theforge.errors import UsageError
from theforge.forger import AskRequest, Forger
from theforge.registry import Registry, RegistryRecord, check_health
from theforge.routing.signals import normalize_tokens
from theforge.runs import ARTIFACTS, RunStore
from theforge.state import find_forge_dir, init_workspace, require_forge_dir

EXIT_BY_STATUS = {"ok": 0, "partial": 0, "ambiguous": 3, "no_route": 3, "refused": 4,
                  "provider_failure": 4}


def _root(args: argparse.Namespace) -> Path:
    root = Path(args.root).resolve()
    if not root.is_dir():
        raise UsageError(f"workspace root {root} is not a directory")
    return root


def _emit(args: argparse.Namespace, data: dict[str, Any],
          text: Callable[[dict[str, Any]], str]) -> None:
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        print(text(data))


def _warn(registry: Registry) -> None:
    for warning in registry.warnings:
        print(f"theforge: warning: {warning}", file=sys.stderr)


def _summary(record: RegistryRecord) -> dict[str, Any]:
    manifest = record.manifest
    return {
        "id": record.entry.id, "trust": record.entry.trust, "source": record.entry.source,
        "state": record.state, "version": manifest.version if manifest else None,
        "protocol": record.protocol, "error": record.error,
        "capabilities": [c.id for c in manifest.capabilities] if manifest else [],
    }


def _capability_rows(records: list[RegistryRecord],
                     provider: str | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records:
        if record.manifest is None or (provider and record.entry.id != provider):
            continue
        for cap in record.manifest.capabilities:
            rows.append({
                "provider": record.entry.id, "trust": record.entry.trust, "id": cap.id,
                "actions": list(cap.actions), "default_action": cap.default_action,
                "state": cap.state, "operation_class": cap.operation_class,
                "description": cap.description, "keywords": list(cap.signals.keywords),
            })
    return sorted(rows, key=lambda row: (row["id"], row["provider"]))


def cmd_init(args: argparse.Namespace) -> int:
    root = _root(args)
    created = init_workspace(root)
    _emit(args, {"forge_dir": str(root / ".forge"), "created": created}, render.init)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    root = _root(args)
    registry = Registry(find_forge_dir(root))
    report = run_doctor(root, registry)
    _warn(registry)
    _emit(args, report, render.doctor)
    return 0 if report["healthy"] else 1


def cmd_status(args: argparse.Namespace) -> int:
    root = _root(args)
    forge_dir = find_forge_dir(root)
    runs = RunStore(forge_dir).list_runs() if forge_dir else []
    cached = sorted(p.stem for p in (forge_dir / "registry").glob("*.json")) if forge_dir else []
    data = {"root": str(root), "initialized": forge_dir is not None, "cached_providers": cached,
            "runs": len(runs), "last_run": runs[-1] if runs else None}
    _emit(args, data, render.status)
    return 0


def _list(args: argparse.Namespace, refresh: bool) -> int:
    registry = Registry(find_forge_dir(_root(args)))
    records = registry.refresh() if refresh else registry.records()
    _warn(registry)
    _emit(args, {"providers": [_summary(r) for r in records]}, render.providers)
    return 0


def cmd_registry_list(args: argparse.Namespace) -> int:
    return _list(args, refresh=False)


def cmd_registry_refresh(args: argparse.Namespace) -> int:
    return _list(args, refresh=True)


def cmd_registry_show(args: argparse.Namespace) -> int:
    registry = Registry(find_forge_dir(_root(args)))
    record = registry.get(args.provider_id)
    _warn(registry)
    data = {**_summary(record), "argv": record.entry.argv,
            "manifest": to_dict(record.manifest) if record.manifest else None,
            "manifest_sha256": record.manifest_sha256}
    _emit(args, data, render.provider_detail)
    return 0


def cmd_capabilities_list(args: argparse.Namespace) -> int:
    registry = Registry(find_forge_dir(_root(args)))
    rows = _capability_rows(registry.records(), args.provider)
    _warn(registry)
    _emit(args, {"capabilities": rows}, render.capabilities)
    return 0


def cmd_capabilities_search(args: argparse.Namespace) -> int:
    query = set(normalize_tokens(args.query))
    if not query:
        raise UsageError("empty search query")
    registry = Registry(find_forge_dir(_root(args)))
    rows = [
        row for row in _capability_rows(registry.records())
        if query <= set(normalize_tokens(" ".join([row["id"], row["description"],
                                                    *row["keywords"]])))
    ]
    _warn(registry)
    _emit(args, {"query": args.query, "capabilities": rows}, render.capabilities)
    return 0


def cmd_providers_health(args: argparse.Namespace) -> int:
    registry = Registry(find_forge_dir(_root(args)))
    rows = []
    for record in registry.records():
        outcome = check_health(record)
        rows.append({"id": record.entry.id, "trust": record.entry.trust,
                     "status": outcome.status,
                     "error": to_dict(outcome.error) if outcome.error else None})
    _warn(registry)
    _emit(args, {"providers": rows}, render.health)
    return 0 if all(row["status"] in ("ok", "degraded") for row in rows) else 1


def cmd_ask(args: argparse.Namespace) -> int:
    root = _root(args)
    forge_dir = require_forge_dir(root)
    registry = Registry(forge_dir, allow_unverified=args.allow_unverified)
    outcome = Forger(root, registry, RunStore(forge_dir)).ask(AskRequest(
        intent=args.intent, targets=args.targets or ["."], capability=args.capability,
        action=args.action, profile=args.profile, allow_unverified=args.allow_unverified,
    ))
    _warn(registry)
    data = {
        "run_id": outcome.run_id, "status": outcome.status,
        "decision": to_dict(outcome.decision),
        "result": to_dict(outcome.result) if outcome.result else None,
        "error": to_dict(outcome.error) if outcome.error else None,
    }
    _emit(args, data, render.ask)
    return EXIT_BY_STATUS[outcome.status]


def cmd_explain(args: argparse.Namespace) -> int:
    store = RunStore(require_forge_dir(_root(args)))
    try:
        run_dir = store.run_dir(args.run_id)
    except ValueError as exc:
        raise UsageError(str(exc)) from exc
    if not run_dir.is_dir():
        raise UsageError(f"unknown run {args.run_id}")
    data: dict[str, Any] = {"run_id": args.run_id}
    for name in ARTIFACTS:
        data[name] = store.read_optional(args.run_id, name)
    _emit(args, data, render.explain)
    return 0
