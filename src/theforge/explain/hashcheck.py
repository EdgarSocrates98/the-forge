"""HashCheck: the integrity of a persisted run, recomputed from disk (requirement 12).

The receipt is the trust anchor (documented limitation): every hash it records is compared
with the artifact as it is on disk now, using the same digest ``RunStore.write`` returned:

- ``kind="run"``: ``inputs.{task,routing,context,risk,handoff}_sha256``, the negotiation
  rounds (``context_round_sha256`` -> ``context-r1``, ``context-r2``), ``result_sha256``,
  ``telemetry_sha256``, ``verification_sha256``, and every ``result.artifacts[]`` re-hashed
  under the run's ``work/`` directory (reported as ``work/<path>``);
- ``kind="plan"``: the same inputs and telemetry plus the ``PlanRefs`` (plan, workspace
  descriptor, graph, installation, plan-result) and, for every ``NodeOutcome`` with a run,
  the node's receipt against ``receipt_sha256`` (``<run>/receipt``) and that node run
  verified in turn (its entries prefixed with ``<run>/``).

A recorded artifact that differs is ``modified``, absent is ``missing``, present but not
readable is ``unreadable``; an artifact present without a recorded hash (runs written
before that hash existed) is listed in ``unrecorded``, never a divergence. A missing or
unreadable receipt is a ``receipt`` divergence. Nothing is written and no provider starts.
"""

import os
from pathlib import Path
from typing import Final

from theforge.context.verify import current_file_sha256
from theforge.contracts import ExecutionReceipt, ExecutionResult
from theforge.contracts.base import ContractError
from theforge.contracts.explain import Divergence, IntegrityReport
from theforge.contracts.plan import PlanResult
from theforge.errors import PersistenceError
from theforge.runs import ARTIFACTS, RunStore

# Artifacts no receipt hash covers by design (the receipt itself; the --debug diagnostic).
_NOT_HASHED: Final = frozenset({"receipt", "diagnostic"})
_ROUNDS: Final = ("context-r1", "context-r2")
# A plan's node runs are verified; their own children (none by design) are not followed.
MAX_DEPTH: Final = 1


class _Check:
    def __init__(self, store: RunStore) -> None:
        self.store = store
        self.checked: list[str] = []
        self.divergences: list[Divergence] = []
        self.unrecorded: list[str] = []

    def persisted(self, run_id: str, name: str) -> tuple[str | None, bool]:
        """(on-disk hash or None, whether the artifact file is present)."""
        try:
            digest = self.store.persisted_sha256(run_id, name)
        except PersistenceError:
            return None, True
        return digest, digest is not None

    def compare(self, label: str, expected: str, actual: str | None, present: bool) -> None:
        self.checked.append(label)
        if actual is None:
            self.divergences.append(Divergence(
                artifact=label, kind="unreadable" if present else "missing",
                expected=expected))
        elif actual != expected:
            self.divergences.append(Divergence(artifact=label, kind="modified",
                                               expected=expected, actual=actual))

    def receipt(self, run_id: str, prefix: str) -> ExecutionReceipt | None:
        label = f"{prefix}receipt"
        try:
            return self.store.read_contract(run_id, "receipt", ExecutionReceipt)
        except LookupError:
            self.divergences.append(Divergence(artifact=label, kind="missing"))
        except (PersistenceError, ContractError):
            self.divergences.append(Divergence(artifact=label, kind="unreadable"))
        return None

    def run(self, run_id: str, prefix: str, depth: int) -> None:
        receipt = self.receipt(run_id, prefix)
        if receipt is None:
            return
        for name, expected in _recorded(receipt).items():
            label = f"{prefix}{name}"
            actual, present = self.persisted(run_id, name)
            if expected is not None:
                self.compare(label, expected, actual, present)
            elif present:
                self.unrecorded.append(label)
        for extra, expected in enumerate(receipt.inputs.context_round_sha256[len(_ROUNDS):],
                                         start=len(_ROUNDS) + 1):
            self.compare(f"{prefix}context-r{extra}", expected, None, False)
        if receipt.result_sha256 is not None:
            self.work_artifacts(run_id, prefix)
        if receipt.kind == "plan":
            self.nodes(run_id, prefix, depth)

    def work_artifacts(self, run_id: str, prefix: str) -> None:
        try:
            result = self.store.read_contract(run_id, "result", ExecutionResult)
        except (LookupError, PersistenceError, ContractError):
            return  # already a divergence of ``result``; its artifacts cannot be known
        work = Path(os.path.normpath(self.store.work_dir(run_id)))
        for artifact in result.artifacts:
            actual = current_file_sha256(work, artifact.path)
            # Presence is probed only for a path lexically under work/: a declared path that
            # escapes (``..``, absolute, other drive) is ``missing`` and never stats outside.
            lexical = Path(os.path.normpath(work / artifact.path))
            present = lexical.is_relative_to(work) and os.path.lexists(lexical)
            self.compare(f"{prefix}work/{artifact.path}", artifact.sha256, actual, present)

    def nodes(self, run_id: str, prefix: str, depth: int) -> None:
        try:
            result = self.store.read_contract(run_id, "plan-result", PlanResult)
        except (LookupError, PersistenceError, ContractError):
            return  # absent (plan not executed) or already a divergence of ``plan-result``
        for outcome in result.nodes:
            child = outcome.run_id
            if child is None or outcome.receipt_sha256 is None:
                continue
            label = f"{prefix}{child}/receipt"
            try:
                actual, present = self.persisted(child, "receipt")
            except ValueError:  # not a run id: there is no such run directory
                actual, present = None, False
            self.compare(label, outcome.receipt_sha256, actual, present)
            if actual is not None and depth < MAX_DEPTH:
                self.run(child, f"{prefix}{child}/", depth + 1)


def _recorded(receipt: ExecutionReceipt) -> dict[str, str | None]:
    """Each hashable run artifact (in run order) with the hash the receipt recorded."""
    inputs, refs = receipt.inputs, receipt.plan
    rounds = inputs.context_round_sha256
    hashes: dict[str, str | None] = {
        "task": inputs.task_sha256,
        "routing": inputs.routing_sha256,
        "context": inputs.context_sha256,
        "risk": inputs.risk_sha256,
        "handoff": inputs.handoff_sha256,
        "complexity": inputs.complexity_sha256,
        "budget": inputs.budget_sha256,
        "result": receipt.result_sha256,
        "telemetry": receipt.telemetry_sha256,
        "verification": receipt.verification_sha256,
        "plan": refs.plan_sha256 if refs else None,
        "workspace-descriptor": refs.workspace_descriptor_sha256 if refs else None,
        "graph": refs.graph_sha256 if refs else None,
        "capability-graph": refs.capability_graph_sha256 if refs else None,
        "semantic-proposal": refs.semantic_proposal_sha256 if refs else None,
        "installation": refs.installation_sha256 if refs else None,
        "plan-result": refs.plan_result_sha256 if refs else None,
        "plan-state": refs.plan_state_sha256 if refs else None,
        "decision": refs.decision_sha256 if refs else None,
    }
    for index, name in enumerate(_ROUNDS):
        hashes[name] = rounds[index] if index < len(rounds) else None
    return {name: hashes[name] for name in ARTIFACTS if name not in _NOT_HASHED}


def verify_run_hashes(store: RunStore, run_id: str, *, depth: int = 0) -> IntegrityReport:
    """Integrity of run ``run_id`` (and, for a plan, of its node runs); read-only.

    ``depth`` is the nesting level of ``run_id`` (0 for the run asked about); node runs
    are followed only while it is below ``MAX_DEPTH``.
    """
    check = _Check(store)
    check.run(run_id, "", depth)
    return IntegrityReport(checked=check.checked, divergences=check.divergences,
                           unrecorded=check.unrecorded)
