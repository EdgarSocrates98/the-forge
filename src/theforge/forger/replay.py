"""Replay: re-render, re-verify and re-execute a persisted run (requirement 14.5-14.9).

- ``render`` rebuilds the ``ExplainReport`` from the persisted artifacts only: no provider
  starts and the workspace is never read (14.6).
- ``verify`` recomputes the run's hashes (``explain.hashcheck``) and re-hashes the context
  items it recorded (``context`` and ``context-r*``, of the node runs too for a plan)
  against the workspace now, through the Wave C ``context.verify.reverify``; nothing is
  written and no provider starts (14.7). A context item that changed is a divergence
  ``workspace/<path>`` (``<node_run>/workspace/<path>`` for a plan node); the CLI exits 6
  when there is at least one divergence.
- ``execute`` re-runs a single-provider run (``kind="run"``, not a plan node) with its
  original parameters, the provider pinned and ``replay_of`` linking the new run to the
  original, which is never touched (14.8); the results are compared without volatile
  fields. It is refused with ``ReplayRefused`` before any provider process starts (14.9):
  plans and plan nodes with ``Codes.REPLAY_UNSUPPORTED``; runs ``non_reproducible`` or
  ``unknown``, with changed context, or whose provider changed identity (registration,
  executable fingerprint) or version with ``Codes.REPLAY_NOT_REPRODUCIBLE``, listing every
  reason. The current provider version comes from the registry cache only (never a
  describe): a provider without a cached description is refused as version unknown.
  The replay inputs are first checked against the hashes the receipt recorded
  (``explain.hashcheck``): a ``task``, ``routing``, ``handoff`` or context artifact
  (``context``, ``context-r*``) edited, missing or unreadable, or an unreadable receipt,
  is refused with ``Codes.REPLAY_NOT_REPRODUCIBLE`` (``integrity: <artifact> <kind>``),
  so an edited task cannot run other parameters and an edited context cannot hide a
  changed workspace. Divergences of outputs (result, telemetry, verification) are not
  inputs and do not refuse: the comparison reports them.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Literal, get_args

from theforge.context.verify import reverify
from theforge.contracts import (
    ContextPack,
    ExecutionReceipt,
    ExecutionResult,
    TaskSpec,
    to_dict,
)
from theforge.contracts.base import ContractError
from theforge.contracts.canonical import sha256_of
from theforge.contracts.codes import Codes
from theforge.contracts.explain import Divergence, ExplainReport
from theforge.contracts.plan import PlanResult
from theforge.contracts.types import Reproducibility
from theforge.errors import PersistenceError, ReplayRefused, UsageError
from theforge.explain import build_explain_report, verify_run_hashes
from theforge.forger.orchestrator import AskRequest, Forger
from theforge.registry import fingerprint
from theforge.runs import RunStore
from theforge.security.paths import resolve_inside

ReplayMode = Literal["render", "verify", "execute"]
Comparison = Literal["same", "different", "no-result"]

MODES: Final = get_args(ReplayMode)
REEXECUTABLE: Final[frozenset[Reproducibility]] = frozenset(
    {"reproducible", "partially_reproducible"})
_CONTEXT_ARTIFACTS: Final = ("context", "context-r1", "context-r2")
# Artifacts a re-execute reads or depends on: an integrity divergence refuses it (14.9).
_REPLAY_INPUTS: Final = frozenset({"receipt", "task", "routing", "handoff",
                                   *_CONTEXT_ARTIFACTS})
# Result fields compared by ``execute``; created_at and metrics are volatile (14.8).
_COMPARED: Final = ("status", "findings", "evidence", "artifacts", "limitations", "unknowns")


@dataclass(frozen=True, kw_only=True)
class ReplayReport:
    mode: ReplayMode
    run_id: str
    report: ExplainReport | None = None  # render
    divergences: list[Divergence] = field(default_factory=list)  # render (integrity), verify
    new_run: str | None = None  # execute
    comparison: Comparison | None = None  # execute


def replay(forger: Forger, store: RunStore, run_id: str, mode: str, *,
           approvals: frozenset[str] = frozenset(), allow_unverified: bool = False,
           created_at: str | None = None) -> ReplayReport:
    """Replay run ``run_id`` in ``mode`` (``render``, ``verify`` or ``execute``).

    ``approvals`` and ``allow_unverified`` come from the command line of the replay (they
    are not taken from the original run); ``created_at`` fixes the time of a re-rendered
    report. Raises ``UsageError`` for an unknown mode, ``ValueError`` for a malformed run
    id, ``LookupError`` for an unknown run and ``ReplayRefused`` for a refused re-execute.
    """
    if mode not in MODES:
        raise UsageError(f"unknown replay mode {mode!r} (expected one of: {', '.join(MODES)})")
    if not store.run_dir(run_id).is_dir():
        raise LookupError(f"unknown run {run_id}")
    if mode == "render":
        report = build_explain_report(store, run_id, created_at=created_at)
        return ReplayReport(mode="render", run_id=run_id, report=report,
                            divergences=list(report.integrity.divergences))
    if mode == "verify":
        return ReplayReport(mode="verify", run_id=run_id,
                            divergences=reverify_run(store, run_id, forger.root))
    return _reexecute(forger, store, run_id, approvals=approvals,
                      allow_unverified=allow_unverified)


def reverify_run(store: RunStore, run_id: str, root: Path) -> list[Divergence]:
    """Hash divergences of the run plus its recorded context items that changed under
    ``root`` (and those of its node runs, for a plan). Read-only; no provider starts."""
    divergences = list(verify_run_hashes(store, run_id).divergences)
    divergences += _context_divergences(store, run_id, root, "")
    for node_run in _node_runs(store, run_id):
        divergences += _context_divergences(store, node_run, root, f"{node_run}/")
    return divergences


def _read(store: RunStore, run_id: str, name: str, cls: type[Any]) -> Any:
    """The typed artifact, or None when absent, unreadable or invalid (hashcheck reports
    those as divergences)."""
    try:
        return store.read_contract(run_id, name, cls)
    except (LookupError, ValueError, PersistenceError, ContractError):
        return None


def _node_runs(store: RunStore, run_id: str) -> list[str]:
    receipt = _read(store, run_id, "receipt", ExecutionReceipt)
    if receipt is None or receipt.kind != "plan":
        return []
    result = _read(store, run_id, "plan-result", PlanResult)
    if result is None:
        return []
    return [node.run_id for node in result.nodes if node.run_id is not None]


def _changed_context(store: RunStore, run_id: str, root: Path) -> list[str]:
    """Sorted paths of the run's recorded context items whose content changed."""
    items = []
    for name in _CONTEXT_ARTIFACTS:
        pack = _read(store, run_id, name, ContextPack)
        if pack is not None:
            items.extend(pack.files)
    return sorted(reverify(root, items))


def _context_divergences(store: RunStore, run_id: str, root: Path,
                         prefix: str) -> list[Divergence]:
    try:
        changed = _changed_context(store, run_id, root)
    except ValueError:  # a node run id that is not a run id: no such run directory
        return []
    return [Divergence(artifact=f"{prefix}workspace/{path}",
                       kind="modified" if resolve_inside(root, root / path) else "missing")
            for path in changed]


def _refusal(forger: Forger, store: RunStore, run_id: str,
             receipt: ExecutionReceipt) -> list[str]:
    """Every reason the run cannot be re-executed (empty: eligible). Starts nothing."""
    reasons = [f"integrity: {d.artifact} {d.kind}"
               for d in verify_run_hashes(store, run_id).divergences
               if d.artifact in _REPLAY_INPUTS or d.artifact.startswith("context-r")]
    info = receipt.reproducibility
    level = info.level if info is not None else "unknown"
    if level not in REEXECUTABLE:
        detail = "; ".join(info.reasons) if info is not None and info.reasons else (
            "not recorded" if info is None else "")
        reasons.append(f"reproducibility is {level}" + (f" ({detail})" if detail else ""))
    reasons += [f"context changed: {path}"
                for path in _changed_context(store, run_id, forger.root)]
    provider = receipt.provider
    if provider is None:
        reasons.append("no provider recorded for the run")
        return reasons
    entry = next((e for e in forger.registry.entries() if e.id == provider.id), None)
    if entry is None:
        reasons.append(f"provider {provider.id} is no longer registered")
        return reasons
    cached = next((r for r in forger.registry.cached_records() if r.entry.id == provider.id),
                  None)
    current = cached.manifest.version if cached is not None and cached.manifest else None
    if current is None:
        reasons.append(f"provider {provider.id}: current version unknown (not described)")
    elif current != provider.version:
        reasons.append(f"provider {provider.id} version changed: "
                       f"{provider.version} -> {current}")
    if provider.fingerprint is None:
        reasons.append(f"provider {provider.id}: fingerprint not recorded")
    elif fingerprint(entry).digest != provider.fingerprint:
        reasons.append(f"provider {provider.id} identity changed (executable fingerprint)")
    # A recorded surface fingerprint that no longer matches means the provider's
    # declared capabilities changed in place — even at the same version (3.1).
    if provider.surface_fingerprint is not None:
        current_surface = cached.surface.surface_fingerprint \
            if cached is not None and cached.surface is not None else None
        if current_surface is None:
            reasons.append(f"provider {provider.id}: current surface unknown")
        elif current_surface != provider.surface_fingerprint:
            reasons.append(f"provider {provider.id} surface changed "
                           "(declared surface fingerprint)")
    if provider.native_surface_fingerprint is not None and cached is not None \
            and cached.surface is not None \
            and cached.surface.native_surface_fingerprint is not None \
            and cached.surface.native_surface_fingerprint \
            != provider.native_surface_fingerprint:
        reasons.append(f"provider {provider.id} native surface changed")
    return reasons


def _reexecute(forger: Forger, store: RunStore, run_id: str, *,
               approvals: frozenset[str], allow_unverified: bool) -> ReplayReport:
    receipt = _read(store, run_id, "receipt", ExecutionReceipt)
    task = _read(store, run_id, "task", TaskSpec)
    if receipt is None or task is None:
        missing = [name for name, value in (("receipt", receipt), ("task", task))
                   if value is None]
        raise ReplayRefused(tuple(f"{name} not readable" for name in missing))
    if receipt.kind == "plan":
        raise ReplayRefused(("re-execute of a plan run is not supported",),
                            code=Codes.REPLAY_UNSUPPORTED)
    if receipt.parent_run is not None or receipt.plan_node is not None:
        raise ReplayRefused(
            (f"re-execute of a plan node run is not supported (plan {receipt.parent_run})",),
            code=Codes.REPLAY_UNSUPPORTED)
    reasons = _refusal(forger, store, run_id, receipt)
    if reasons or receipt.provider is None:  # eligibility requires a recorded provider
        raise ReplayRefused(tuple(reasons))
    outcome = forger.ask(AskRequest(
        intent=task.intent, targets=list(task.targets), capability=task.requested_capability,
        action=task.requested_action, profile=task.budget_profile,
        allow_unverified=allow_unverified, approvals=approvals,
        provider=receipt.provider.id, replay_of=run_id))
    return ReplayReport(mode="execute", run_id=run_id, new_run=outcome.run_id,
                        comparison=_compare(store, run_id, outcome.run_id))


def result_fingerprint(result: ExecutionResult) -> str:
    """sha256 of the result without volatile fields (``created_at``, ``metrics``...)."""
    data = to_dict(result)
    return sha256_of({name: data[name] for name in _COMPARED})


def _compare(store: RunStore, original: str, new: str) -> Comparison:
    """Both results as persisted (same redaction on both sides)."""
    before = _read(store, original, "result", ExecutionResult)
    after = _read(store, new, "result", ExecutionResult)
    if before is None or after is None:
        return "no-result"
    return "same" if result_fingerprint(before) == result_fingerprint(after) else "different"
