"""Command handlers: gather data, render (text or JSON), return the exit code."""

import argparse
import dataclasses
import json
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Final, cast

from theforge.adaptive import build_context_roi, recommend_context_budget
from theforge.cli import render
from theforge.context import scan_workspace
from theforge.contracts import CapabilityRequirement, to_dict
from theforge.contracts.base import ContractError, from_dict
from theforge.contracts.codes import Codes, family_of
from theforge.contracts.types import BudgetProfile
from theforge.environment import run_doctor
from theforge.errors import UsageError
from theforge.explain import build_explain_report
from theforge.forger import AskRequest, Forger, PlanCommand, PlanExecutor
from theforge.forger.replay import replay
from theforge.intel import load_decisions
from theforge.metrics import load_performance
from theforge.negotiation import negotiate_all
from theforge.observations import build_global_receipt, load_observations
from theforge.profiles import profile_for
from theforge.registry import (
    Registry,
    RegistryRecord,
    check_health,
    load_source_specs,
    local_document,
    read_sources,
)
from theforge.routing.signals import normalize_tokens
from theforge.runs import RunStore
from theforge.security.redact import redact
from theforge.state import find_forge_dir, init_workspace, require_forge_dir
from theforge.workspace import describe_workspace

EXIT_BY_STATUS = {"ok": 0, "partial": 0, "planned": 0, "ambiguous": 3, "no_route": 3,
                  "refused": 4, "provider_failure": 4}
EXIT_INTEGRITY: Final = 6  # integrity divergence: explain, replay --mode render|verify

PROVIDER_CODE = "provider code"  # family label of a native provider code (13.3)


def error_family(code: str) -> str:
    """Family of a taxonomy code, or ``PROVIDER_CODE`` for a native provider code."""
    return family_of(code) or PROVIDER_CODE


def print_debug(diagnostic: dict[str, Any]) -> None:
    """The redacted diagnostic as ``theforge: debug:`` lines on stderr (13.5)."""
    for line in render.diagnostic(diagnostic):
        print(f"theforge: debug: {line}", file=sys.stderr)


def _integrity_exit(divergences: int) -> int:
    """Exit 6 with one governed stderr line when artifacts diverge (``PERSIST_DIVERGENCE``
    classifies the divergence, 13.4); 0 otherwise. Stdout is left untouched."""
    if not divergences:
        return 0
    code = Codes.PERSIST_DIVERGENCE
    print(f"theforge: integrity divergence: {divergences} artifact(s) diverge "
          f"{render.code_suffix(code, error_family(code))}", file=sys.stderr)
    return EXIT_INTEGRITY


def _root(args: argparse.Namespace) -> Path:
    root = Path(args.root).resolve()
    if not root.is_dir():
        raise UsageError(f"workspace root {root} is not a directory")
    return root


def _no_traceback(value: Any) -> Any:
    """``value`` with every raw traceback in its strings collapsed (13.4): JSON output too
    never shows one (e.g. a provider's stderr tail in an error detail)."""
    if isinstance(value, str):
        return render.collapse_traceback(value)
    if isinstance(value, dict):
        return {key: _no_traceback(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_no_traceback(item) for item in value]
    return value


def _emit(args: argparse.Namespace, data: dict[str, Any],
          text: Callable[[dict[str, Any]], str]) -> None:
    if args.json:
        print(json.dumps(_no_traceback(data), indent=2, sort_keys=True, ensure_ascii=False))
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
    declared_by: dict[str, set[str]] = {}
    for record in records:
        for cap in record.manifest.capabilities if record.manifest else []:
            declared_by.setdefault(cap.id, set()).add(record.entry.id)
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
                "aliases": list(cap.aliases), "deprecated": cap.deprecated,
                "replaced_by": cap.replaced_by, "declared_by": sorted(declared_by[cap.id]),
            })
    return sorted(rows, key=lambda row: (row["id"], row["provider"]))


def _warn_deprecated(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        if not row["deprecated"]:
            continue
        replacement = (f"replaced_by '{row['replaced_by']}'" if row["replaced_by"]
                       else "no replacement declared")
        print(f"theforge: warning: capability '{row['id']}' ({row['provider']}) "
              f"is deprecated; {replacement}", file=sys.stderr)


def cmd_init(args: argparse.Namespace) -> int:
    root = _root(args)
    warnings: list[str] = []
    created = init_workspace(root, warnings)
    for warning in warnings:
        print(f"theforge: warning: {warning}", file=sys.stderr)
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
    cached = Registry(forge_dir).cached_ids() if forge_dir else []
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


def cmd_registry_sources(args: argparse.Namespace) -> int:
    """Registry sources (cycle 4, wave C): the local installed registry is the
    authoritative source; configured sources are untrusted metadata only."""
    forge_dir = find_forge_dir(_root(args))
    warnings: list[str] = []
    specs = load_source_specs(forge_dir, warnings=warnings)
    for warning in warnings:
        print(f"theforge: warning: {warning}", file=sys.stderr)
    registry = Registry(forge_dir)
    local = local_document(registry.records())
    _warn(registry)
    sources = [{
        "id": read.spec.id, "kind": read.spec.kind, "enabled": read.spec.enabled,
        "status": read.status, "detail": read.detail,
        "entries": len(read.document.entries) if read.document else None,
        "registry": read.document.registry.id if read.document else None,
        "freshness": read.freshness, "from_cache": read.from_cache,
        "retrieved_at": read.retrieved_at, "etag": read.etag,
        "body_sha256": read.body_sha256,
    } for read in read_sources(specs)]
    _emit(args, {"local_entries": len(local.entries), "sources": sources},
          render.registry_sources)
    return 0


def cmd_economy_report(args: argparse.Namespace) -> int:
    """Global economy receipt (cycle 4, wave G): aggregates the recorded
    execution observations into a per-axis view — observed, unresolved,
    conflict — plus per-key history maturity. Read-only, offline."""
    root = _root(args)
    observations, obs_warning = load_observations(root)
    performance, perf_warning = load_performance(root)
    receipt = build_global_receipt(observations, performance)
    data = to_dict(receipt)
    data["limitations"] += [w for w in (obs_warning, perf_warning) if w]

    # Context ROI is a read-only advisory view over the same observation stream.
    # It is scoped by provider/capability/surface/task-family and never changes
    # routing or budgets. Rows are bounded to keep a long-lived workspace report
    # compact; JSON clients can inspect the exact contract payloads.
    keys = sorted({
        (
            item.provider,
            item.capability,
            item.surface_fingerprint,
            item.task_family,
        )
        for item in observations
        if item.surface_fingerprint is not None
    }, key=lambda key: tuple("" if part is None else part for part in key))
    max_roi_rows = 128
    roi_rows: list[dict[str, Any]] = []
    for provider, capability, surface, family in keys[:max_roi_rows]:
        assert surface is not None
        roi = build_context_roi(
            observations,
            provider=provider,
            capability=capability,
            surface_fingerprint=surface,
            task_family=family,
        )
        comparable = [
            item
            for item in observations
            if item.provider == provider
            and item.capability == capability
            and item.surface_fingerprint == surface
            and (family is None or item.task_family == family)
        ]
        latest = max(comparable, key=lambda item: item.created_at) if comparable else None
        recommendation = None
        if latest is not None and latest.profile in ("economy", "balanced", "max"):
            recommendation = recommend_context_budget(
                roi,
                current_budget_bytes=profile_for(cast(BudgetProfile, latest.profile)).budget_bytes,
            )
        roi_rows.append({
            "roi": to_dict(roi),
            "recommendation": to_dict(recommendation) if recommendation else None,
        })
    if len(keys) > max_roi_rows:
        data["limitations"].append(
            f"context ROI rows truncated: {len(keys)} groups, showing {max_roi_rows}"
        )
    data["context_roi"] = roi_rows
    _emit(args, data, render.economy_report)
    return 0


def cmd_capabilities_list(args: argparse.Namespace) -> int:
    registry = Registry(find_forge_dir(_root(args)))
    rows = _capability_rows(registry.records(), args.provider)
    _warn(registry)
    _warn_deprecated(rows)
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
                                                    *row["keywords"], *row["aliases"]])))
    ]
    _warn(registry)
    _warn_deprecated(rows)
    _emit(args, {"query": args.query, "capabilities": rows}, render.capabilities)
    return 0


def _load_requirement(path_arg: str | None) -> CapabilityRequirement | None:
    """``--requirement REQ.json``: a ``CapabilityRequirement/v1`` document, or
    ``None`` when the flag was not given."""
    if path_arg is None:
        return None
    path = Path(path_arg)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return from_dict(CapabilityRequirement, data)
    except (OSError, json.JSONDecodeError, ContractError) as exc:
        raise UsageError(f"invalid capability requirement {path}: {exc}") from exc


def cmd_capabilities_negotiate(args: argparse.Namespace) -> int:
    """``capabilities negotiate --requirement <req.json>`` — deterministic v2
    negotiation over the registered manifests (offline, cache only)."""
    requirement = _load_requirement(args.requirement)
    assert requirement is not None  # --requirement is required on this command
    registry = Registry(find_forge_dir(_root(args)))
    performance, perf_warning = load_performance(_root(args))
    results = negotiate_all(requirement, registry.records(), performance=performance)
    _warn(registry)
    if perf_warning:
        print(f"theforge: warning: {perf_warning}", file=sys.stderr)
    _emit(args, {"requirement": to_dict(requirement),
                 "results": [to_dict(r) for r in results]}, render.negotiation)
    return 0


def cmd_capabilities_discover(args: argparse.Namespace) -> int:
    """``capabilities discover`` — missing-capability UX (§26): local
    negotiation first; enabled registry sources only when needed (or
    ``--remote``). Reports candidates as metadata and stops — no install."""
    from theforge.registry.discovery import discover
    if args.requirement:
        requirement = _load_requirement(args.requirement)
    else:
        requirement = CapabilityRequirement(capability=args.capability)
    assert requirement is not None
    root = _root(args)
    registry = Registry(find_forge_dir(root))
    performance, perf_warning = load_performance(root)
    report = discover(requirement, registry.records(), forge_dir=find_forge_dir(root),
                      force_remote=args.remote, profile=args.profile,
                      performance=performance)
    _warn(registry)
    if perf_warning:
        print(f"theforge: warning: {perf_warning}", file=sys.stderr)
    _emit(args, {
        "requirement": to_dict(requirement),
        "local_state": report.local_state,
        "local_provider": report.local_provider,
        "satisfied_locally": report.satisfied_locally,
        "candidates": [to_dict(c) for c in report.candidates],
        "sources_consulted": report.sources_consulted,
        "sources_skipped": report.sources_skipped,
        "entries_scanned": report.entries_scanned,
        "entries_excluded": report.entries_excluded,
        "mcp_tooling": [to_dict(n) for n in report.mcp_tooling],
        "mcp_dependencies": [to_dict(d) for d in report.mcp_dependencies],
        "profile": report.profile,
        "registry_calls": report.registry_calls,
        "metadata_bytes": report.metadata_bytes,
        "network_ms": report.network_ms,
        "limitations": report.limitations,
        "action_taken": False,
    }, render.discovery)
    return 0


def cmd_install_plan(args: argparse.Namespace) -> int:
    """``install plan`` — deterministic InstallationPlan/v2 from a configured
    source's entry (§27-30). Plan-only: emits the document, executes nothing."""
    from theforge.registry.install_plan import build_install_plan
    result = build_install_plan(args.provider, args.version, args.source,
                                forge_dir=find_forge_dir(_root(args)),
                                approve=args.approve)
    _emit(args, {"plan": to_dict(result.plan)}, render.install_plan)
    return 0


def cmd_providers_health(args: argparse.Namespace) -> int:
    registry = Registry(find_forge_dir(_root(args)))
    rows = []
    for record in registry.records():
        outcome = check_health(record)
        rows.append({"id": record.entry.id, "trust": record.entry.trust,
                     "status": outcome.status,
                     "surface_fingerprint": outcome.surface_fingerprint,
                     "error": to_dict(outcome.error) if outcome.error else None})
    _warn(registry)
    _emit(args, {"providers": rows}, render.health)
    return 0 if all(row["status"] in ("ok", "degraded") for row in rows) else 1


def cmd_graph(args: argparse.Namespace) -> int:
    """``theforge graph``: the declared+observed capability graph of the registry
    and workspace (Wave B structure, Wave Q surface). Cached manifests only — no
    provider process starts, like ``workspace show`` (7.8). ``--ref`` restricts
    the listing to the edges touching that capability (``p/c`` or bare ``c``)."""
    from theforge.capability_graph import build_capability_graph

    root = _root(args)
    registry = Registry(find_forge_dir(root))
    records = registry.cached_records()
    # ``.``: the observed half of the graph (technologies -> relevant_to) needs
    # the real scan, not the empty one ``workspace show`` uses for cheapness.
    descriptor = describe_workspace(root, records, scan_workspace(root, ["."]))
    cached = {record.entry.id for record in records}
    missing = [f"provider {entry.id}: no cached manifest, its signals were not used "
               "(run `theforge registry refresh`)"
               for entry in registry.entries() if entry.id not in cached]
    graph = build_capability_graph(records, descriptor)
    data: dict[str, Any] = {**to_dict(graph), "ref": args.ref}
    if getattr(args, "mesh", False):
        from theforge.capability_graph import mesh_view
        data["mesh"] = mesh_view(graph)
    if args.ref:
        edges = [e for e in data["edges"]
                 if _cap_match(str(e.get("source", "")), args.ref)
                 or _cap_match(str(e.get("target", "")), args.ref)]
        keep = {str(e.get("source")) for e in edges} | {str(e.get("target")) for e in edges}
        data["edges"] = edges
        data["nodes"] = [n for n in data["nodes"]
                         if _cap_match(str(n.get("id", "")), args.ref)
                         or n.get("id") in keep]
    if missing:
        data["limitations"] = [*(data.get("limitations") or []), *missing]
    _warn(registry)
    _emit(args, redact(data), render.graph)
    return 0


def _cap_match(node_id: str, ref: str) -> bool:
    """``p/c`` matches exactly; bare ``c`` matches ``capability:*/c``."""
    key = node_id.removeprefix("capability:")
    return node_id.startswith("capability:") and (
        key == ref or ("/" not in ref and key.endswith(f"/{ref}")))


def cmd_provider_init(args: argparse.Namespace) -> int:
    from theforge.scaffold import init_provider

    result = init_provider(Path(args.directory), args.id, capability=args.capability)
    _emit(args, {"directory": str(result.directory),
                 "files": [str(p) for p in result.files],
                 "argv": result.argv, "provider_id": result.provider_id,
                 "capability": result.capability}, render.provider_init)
    return 0


def cmd_provider_check(args: argparse.Namespace) -> int:
    from theforge.conformance import check_provider

    argv = list(args.argv)
    if argv and argv[0] == "--":
        argv = argv[1:]
    if not argv:
        raise UsageError("provider check requires the provider argv, e.g. "
                         "`theforge provider check -- python provider.py`")
    report = check_provider(argv)
    checks = [{"id": c.id, "status": c.status, "detail": c.detail}
              for c in report.checks]
    _emit(args, {"argv": report.argv, "ok": report.ok, "checks": checks},
          render.provider_check)
    return 0 if report.ok else 1


def cmd_ask(args: argparse.Namespace) -> int:
    root = _root(args)
    forge_dir = require_forge_dir(root)
    registry = Registry(forge_dir, allow_unverified=args.allow_unverified)
    requirement = _load_requirement(args.requirement)
    capability = args.capability
    if (requirement is not None and capability is not None
            and capability != requirement.capability):
        raise UsageError(
            f"--capability {capability!r} disagrees with the requirement's "
            f"capability {requirement.capability!r}")
    outcome = Forger(root, registry, RunStore(forge_dir)).ask(AskRequest(
        intent=args.intent, targets=args.targets or ["."], capability=capability,
        action=args.action, profile=args.profile, allow_unverified=args.allow_unverified,
        approvals=frozenset(args.approvals or ()), provider=args.use,
        requirement=requirement, debug=args.debug,
    ))
    _warn(registry)
    # Redacted for display: an internal error's text is raw in memory (decision reason too).
    data: dict[str, Any] = redact({
        "run_id": outcome.run_id, "status": outcome.status,
        "decision": to_dict(outcome.decision),
        "result": to_dict(outcome.result) if outcome.result else None,
        "error": to_dict(outcome.error) if outcome.error else None,
        "error_family": error_family(outcome.error.code) if outcome.error else None,
    })
    _emit(args, data, render.ask)
    if args.debug and outcome.diagnostic is not None:
        print_debug(to_dict(outcome.diagnostic))
    return EXIT_BY_STATUS.get(outcome.status, 4)


@contextmanager
def _run_lookup() -> Iterator[None]:
    """A malformed (ValueError) or unknown (LookupError) run id is a usage error (exit 2)."""
    try:
        yield
    except (ValueError, LookupError) as exc:
        raise UsageError(str(exc)) from exc


def cmd_explain(args: argparse.Namespace) -> int:
    store = RunStore(require_forge_dir(_root(args)))
    with _run_lookup():
        report = build_explain_report(store, args.run_id)
    _emit(args, to_dict(report), render.explain_report)
    return _integrity_exit(len(report.integrity.divergences))


def cmd_plan(args: argparse.Namespace) -> int:
    root = _root(args)
    forge_dir = require_forge_dir(root)
    registry = Registry(forge_dir, allow_unverified=args.allow_unverified)
    store = RunStore(forge_dir)
    outcome = PlanExecutor(Forger(root, registry, store)).run(PlanCommand(
        intent=args.intent, targets=args.targets or ["."], profile=args.profile,
        plan_file=Path(args.plan_file) if args.plan_file else None, execute=args.execute,
        approvals=frozenset(args.approvals or ()), allow_unverified=args.allow_unverified,
        requirement=_load_requirement(args.requirement), debug=args.debug,
    ))
    _warn(registry)
    # Redacted for display: an internal error's text is raw in memory.
    data: dict[str, Any] = redact({
        "run_id": outcome.run_id, "status": outcome.status,
        "plan": to_dict(outcome.plan) if outcome.plan else None,
        "result": to_dict(outcome.result) if outcome.result else None,
        "installation": store.read_optional(outcome.run_id, "installation"),
        "decision": store.read_optional(outcome.run_id, "decision"),
        "economy": store.read_optional(outcome.run_id, "economy"),
        "semantic_proposal": store.read_optional(outcome.run_id, "semantic-proposal"),
        "routing_proposal": store.read_optional(outcome.run_id, "routing-proposal"),
        "capability_graph": store.read_optional(outcome.run_id, "capability-graph"),
        "complexity": store.read_optional(outcome.run_id, "complexity"),
        "budget": store.read_optional(outcome.run_id, "budget"),
        "error": to_dict(outcome.error) if outcome.error else None,
        "error_family": error_family(outcome.error.code) if outcome.error else None,
    })
    _emit(args, data, render.plan)
    if args.debug and outcome.diagnostic is not None:
        print_debug(to_dict(outcome.diagnostic))
    return EXIT_BY_STATUS.get(outcome.status, 4)


def cmd_resume(args: argparse.Namespace) -> int:
    """``theforge resume RUN``: continue a plan run, reusing the nodes whose
    recorded inputs still verify (F1/F2). The prior task and plan persist
    verbatim — identical hashes are the integrity proof."""
    root = _root(args)
    forge_dir = require_forge_dir(root)
    registry = Registry(forge_dir, allow_unverified=args.allow_unverified)
    store = RunStore(forge_dir)
    with _run_lookup():
        if not store.run_dir(args.run_id).is_dir():
            raise LookupError(f"unknown run {args.run_id}")
        task = store.read_optional(args.run_id, "task")
        if task is None or store.read_optional(args.run_id, "plan") is None:
            raise UsageError(f"run {args.run_id} has no resumable plan")
    profile = task.get("budget_profile")
    outcome = PlanExecutor(Forger(root, registry, store)).run(PlanCommand(
        intent=str(task.get("intent") or ""),
        targets=list(task.get("targets") or ["."]),
        profile=profile if profile in ("auto", "economy", "balanced", "max") else "auto",
        execute=True, resume_run=args.run_id,
        approvals=frozenset(args.approvals or ()), allow_unverified=args.allow_unverified,
        debug=args.debug,
    ))
    _warn(registry)
    data: dict[str, Any] = redact({
        "run_id": outcome.run_id, "status": outcome.status,
        "resumed_from": args.run_id,
        "plan": to_dict(outcome.plan) if outcome.plan else None,
        "result": to_dict(outcome.result) if outcome.result else None,
        "installation": store.read_optional(outcome.run_id, "installation"),
        "decision": store.read_optional(outcome.run_id, "decision"),
        "economy": store.read_optional(outcome.run_id, "economy"),
        "semantic_proposal": store.read_optional(outcome.run_id, "semantic-proposal"),
        "routing_proposal": store.read_optional(outcome.run_id, "routing-proposal"),
        "capability_graph": store.read_optional(outcome.run_id, "capability-graph"),
        "complexity": store.read_optional(outcome.run_id, "complexity"),
        "budget": store.read_optional(outcome.run_id, "budget"),
        "error": to_dict(outcome.error) if outcome.error else None,
        "error_family": error_family(outcome.error.code) if outcome.error else None,
    })
    _emit(args, data, render.plan)
    if args.debug and outcome.diagnostic is not None:
        print_debug(to_dict(outcome.diagnostic))
    return EXIT_BY_STATUS.get(outcome.status, 4)


def cmd_workspace_show(args: argparse.Namespace) -> int:
    """The workspace descriptor from the registry cache only: no provider process starts
    (7.8). A configured provider without a cached manifest is a limitation."""
    root = _root(args)
    registry = Registry(find_forge_dir(root))
    records = registry.cached_records()
    cached = {record.entry.id for record in records}
    descriptor = describe_workspace(root, records, scan_workspace(root, []))
    missing = [f"provider {entry.id}: no cached manifest, its signals were not used "
               "(run `theforge registry refresh`)"
               for entry in registry.entries() if entry.id not in cached]
    descriptor = dataclasses.replace(
        descriptor, limitations=[*descriptor.limitations, *missing])
    _warn(registry)
    _emit(args, redact(to_dict(descriptor)), render.workspace)
    return 0


def cmd_decisions(args: argparse.Namespace) -> int:
    """The project's reusable-decision memory (Wave I): reads
    ``.forge/intel/decisions.json`` only — no provider process starts. A missing
    memory is an empty memory, not an error; a malformed one is reported."""
    root = _root(args)
    memory, warning = load_decisions(root)
    data: dict[str, Any] = (to_dict(memory) if memory is not None
                            else {"entries": []})
    if warning is not None:
        data["limitations"] = [warning]
    _emit(args, redact(data), render.decisions)
    return 0


def cmd_trace(args: argparse.Namespace) -> int:
    """``theforge trace RUN``: what happened — the run's span tree from its
    ``telemetry`` artifact (Wave J). Distinct from ``explain``, which answers
    *why* it happened. Read-only: no provider process starts; a run without a
    telemetry artifact reports so instead of failing."""
    store = RunStore(require_forge_dir(_root(args)))
    with _run_lookup():
        if not store.run_dir(args.run_id).is_dir():
            raise LookupError(f"unknown run {args.run_id}")
        telemetry = store.read_optional(args.run_id, "telemetry")
        receipt = store.read_optional(args.run_id, "receipt")
    data: dict[str, Any] = {
        "run_id": args.run_id,
        "status": (receipt or {}).get("status"),
        "kind": (receipt or {}).get("kind"),
        "spans": (telemetry or {}).get("spans") or [],
        "limitations": [] if telemetry is not None else ["no telemetry recorded"],
    }
    _emit(args, redact(data), render.trace)
    return 0


def cmd_replay(args: argparse.Namespace) -> int:
    root = _root(args)
    forge_dir = require_forge_dir(root)
    registry = Registry(forge_dir, allow_unverified=args.allow_unverified)
    store = RunStore(forge_dir)
    with _run_lookup():
        report = replay(Forger(root, registry, store), store, args.run_id, args.mode,
                        approvals=frozenset(args.approvals or ()),
                        allow_unverified=args.allow_unverified)
    _warn(registry)
    data: dict[str, Any] = to_dict(report)
    if report.mode == "execute":
        receipt = store.read_optional(report.new_run, "receipt") if report.new_run else None
        status = receipt.get("status") if receipt else None
        data["new_status"] = status
        _emit(args, redact(data), render.replay)
        return EXIT_BY_STATUS.get(status, 4) if isinstance(status, str) else 4
    _emit(args, redact(data), render.replay)
    return _integrity_exit(len(report.divergences))
