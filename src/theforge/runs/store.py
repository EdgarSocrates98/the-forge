"""Run store: one directory per run, redacted JSON artifacts, hashes over what is on disk."""

import json
import os
import re
import secrets
import stat
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, TypeVar

from theforge.contracts import (
    ContextPack,
    EconomyRollup,
    ExecutionReceipt,
    ExecutionResult,
    RiskAssessment,
    RoutingDecision,
    RunTelemetry,
    TaskSpec,
    from_dict,
    to_dict,
)
from theforge.contracts.budget import RunBudget
from theforge.contracts.canonical import sha256_of
from theforge.contracts.capability_graph import CapabilityGraph
from theforge.contracts.codes import Codes
from theforge.contracts.complexity import ComplexityAssessment
from theforge.contracts.diagnostic import Diagnostic
from theforge.contracts.graph import WorkspaceGraph
from theforge.contracts.handoff import Handoff
from theforge.contracts.installation import InstallationPlan
from theforge.contracts.integrity import validate_receipt
from theforge.contracts.plan import (
    DecisionRecord,
    ExecutionPlan,
    PlanResult,
    PlanState,
    SemanticPlanProposal,
)
from theforge.contracts.resolve import RoutingProposal
from theforge.contracts.verification import VerificationResult
from theforge.contracts.workspace import WorkspaceDescriptor
from theforge.errors import PersistenceError
from theforge.security.redact import redact

T = TypeVar("T")

RUN_ID = re.compile(r"^\d{8}T\d{6}Z-[0-9a-f]{8}$")
# Run order. Every artifact but task/receipt is optional: a run only writes the ones of its
# kind, and runs written before an artifact existed stay readable (read_optional returns
# None). context-r1/context-r2 are negotiation rounds; workspace-descriptor, plan,
# installation, plan-result and graph belong to plan runs; handoff to plan node runs;
# verification and diagnostic (--debug) to any run. ``workspace-descriptor`` is the
# multi-repo WorkspaceDescriptor, distinct from the ContextPack workspace summary.
ARTIFACTS = ("task", "workspace-descriptor", "routing", "plan", "installation", "risk",
             "handoff", "context", "context-r1", "context-r2", "result", "plan-state",
             "plan-result", "graph", "capability-graph", "semantic-proposal",
             "routing-proposal", "decision", "economy",
             "verification", "telemetry", "diagnostic", "complexity", "budget",
             "receipt")
ARTIFACT_TYPES: Final[dict[str, type]] = {
    "task": TaskSpec,
    "workspace-descriptor": WorkspaceDescriptor,
    "routing": RoutingDecision,
    "plan": ExecutionPlan,
    "complexity": ComplexityAssessment,
    "budget": RunBudget,
    "capability-graph": CapabilityGraph,
    "semantic-proposal": SemanticPlanProposal,
    "routing-proposal": RoutingProposal,
    "installation": InstallationPlan,
    "risk": RiskAssessment,
    "handoff": Handoff,
    "context": ContextPack,
    "context-r1": ContextPack,
    "context-r2": ContextPack,
    "result": ExecutionResult,
    "plan-state": PlanState,
    "plan-result": PlanResult,
    "decision": DecisionRecord,
    "economy": EconomyRollup,
    "graph": WorkspaceGraph,
    "verification": VerificationResult,
    "telemetry": RunTelemetry,
    "diagnostic": Diagnostic,
    "receipt": ExecutionReceipt,
}


def new_run_id() -> str:
    return f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(4)}"


def _replace(tmp: Path, path: Path) -> None:
    """``tmp.replace(path)`` with a bounded retry: Windows AV/indexers can
    briefly hold a lock on a freshly written file, turning the atomic
    replace into a transient ``PermissionError``. Retries stay under ~300 ms
    and only cover ``PermissionError`` — any persistent failure raises."""
    for attempt in range(6):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            if attempt == 5:
                raise
            time.sleep(0.01 * (1 << attempt))


class RunStore:
    def __init__(self, forge_dir: Path) -> None:
        self.runs_dir = forge_dir / "runs"

    def run_dir(self, run_id: str) -> Path:
        if not RUN_ID.fullmatch(run_id):
            raise ValueError(f"invalid run id {run_id!r}")
        return self.runs_dir / run_id

    def work_dir(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "work"

    def create(self, run_id: str) -> Path:
        directory = self.run_dir(run_id)
        try:
            (directory / "work").mkdir(parents=True)
        except OSError as exc:
            raise PersistenceError(f"cannot create run directory {directory}: {exc}") from exc
        self._contained(directory)
        return directory

    def _artifact_path(self, run_id: str, name: str) -> Path:
        if name not in ARTIFACTS:
            raise ValueError(f"unknown run artifact {name!r}")
        return self.run_dir(run_id) / f"{name}.json"

    def _contained(self, path: Path) -> Path:
        """``path`` when it resolves inside ``runs_dir``; ``PERSIST_READ`` otherwise.

        ``realpath`` resolves every intermediate link, so a symlinked run directory whose
        target leaves the runs directory is caught even though the artifact file itself is
        a regular file.
        """
        base = Path(os.path.realpath(self.runs_dir))
        real = Path(os.path.realpath(path))
        if real != base and base not in real.parents:
            raise PersistenceError(f"{path} resolves outside the runs directory",
                                   code=Codes.PERSIST_READ)
        return path

    def _artifact_file(self, run_id: str, name: str) -> Path | None:
        """The artifact path when it is a regular file physically inside the run dir.

        ``None`` means absent. ``lstat`` never follows the last component, so a symbolic
        artifact (valid, broken or pointing at another run) is never read: it raises a
        controlled ``PERSIST_READ``, as does a directory or any non-regular entry.
        """
        path = self._artifact_path(run_id, name)
        try:
            st = path.lstat()
        except OSError:
            return None
        if not stat.S_ISREG(st.st_mode):
            raise PersistenceError(
                f"cannot read {path}: artifact {name!r} is not a regular file",
                code=Codes.PERSIST_READ)
        return self._contained(path)

    @staticmethod
    def _read_bytes(path: Path) -> bytes:
        """Bytes of a regular artifact file.

        Where ``O_NOFOLLOW`` exists the open itself refuses a link swapped in after the
        ``lstat`` check; on platforms without it (Windows) the pre-checks stand and the
        residual race is a documented limitation (no OS sandbox).
        """
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
        try:
            fd = os.open(path, flags)
        except OSError as exc:
            raise PersistenceError(f"cannot read {path}: {exc}",
                                   code=Codes.PERSIST_READ) from exc
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise PersistenceError(f"cannot read {path}: not a regular file",
                                       code=Codes.PERSIST_READ)
            with os.fdopen(fd, "rb") as fh:
                fd = -1
                return fh.read()
        finally:
            if fd != -1:
                os.close(fd)

    def write(self, run_id: str, name: str, contract: Any) -> str:
        """Redact, persist atomically and return the sha256 of the on-disk content.

        A receipt is validated before it is written (1.8): its ``result_sha256`` must equal
        the hash of the result already persisted in this run, recomputed from disk exactly
        as this method computes it; a plan receipt's plan-result and telemetry hashes must
        equal those of the persisted ``plan-result`` and ``telemetry``. An invalid receipt
        raises ``IntegrityError`` and nothing is written.
        """
        path = self._artifact_path(run_id, name)
        if name == "receipt":
            if not isinstance(contract, ExecutionReceipt):
                raise TypeError(f"receipt artifact must be an ExecutionReceipt, "
                                f"got {type(contract).__name__}")
            plan_kind = contract.kind == "plan"
            validate_receipt(
                contract, result_sha256=self.persisted_sha256(run_id, "result"),
                plan_result_sha256=(self.persisted_sha256(run_id, "plan-result")
                                    if plan_kind else None),
                telemetry_sha256=(self.persisted_sha256(run_id, "telemetry")
                                  if plan_kind else None))
        data = redact(to_dict(contract))
        text = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)
        tmp = path.with_suffix(".json.tmp")
        try:
            st = path.lstat()
        except OSError:
            pass  # absent is fine; the write creates it
        else:
            if not stat.S_ISREG(st.st_mode):
                raise PersistenceError(f"cannot write {path}: artifact {name!r} exists and "
                                       f"is not a regular file", code=Codes.PERSIST_WRITE)
        self._contained(path)
        try:
            tmp.write_text(text, encoding="utf-8")
            _replace(tmp, path)
        except OSError as exc:
            raise PersistenceError(f"cannot write {path}: {exc}") from exc
        return sha256_of(json.loads(text))

    def persisted_sha256(self, run_id: str, name: str) -> str | None:
        """Hash of an artifact as it is on disk (same digest ``write`` returned), or None."""
        data = self.read_optional(run_id, name)
        return None if data is None else sha256_of(data)

    def read(self, run_id: str, name: str) -> dict[str, Any]:
        data = self.read_optional(run_id, name)
        if data is None:
            raise LookupError(f"run {run_id} has no {name}")
        return data

    def read_optional(self, run_id: str, name: str) -> dict[str, Any] | None:
        path = self._artifact_file(run_id, name)
        if path is None:
            return None
        try:
            loaded = json.loads(self._read_bytes(path).decode("utf-8"))
        except PersistenceError:
            raise
        except ValueError as exc:  # JSON/Unicode decode errors are ValueErrors
            raise PersistenceError(f"cannot read {path}: {exc}",
                                   code=Codes.PERSIST_READ) from exc
        if not isinstance(loaded, dict):
            raise PersistenceError(f"cannot read {path}: expected a JSON object",
                                   code=Codes.PERSIST_READ)
        return loaded

    def read_contract(self, run_id: str, name: str, cls: type[T]) -> T:
        """Strict typed read of an artifact the core wrote (unknown keys are rejected).

        Missing optional fields (e.g. Cycle-1 runs) take their defaults. An absent artifact
        raises ``LookupError``; an absent ``risk`` means "not recorded (pre-Cycle-2 run)".
        """
        expected = ARTIFACT_TYPES.get(name)
        if expected is None:
            raise ValueError(f"unknown run artifact {name!r}")
        if cls is not expected:
            raise ValueError(f"artifact {name!r} is {expected.__name__}, not {cls.__name__}")
        return from_dict(cls, self.read(run_id, name), f"$.{name}", strict=True)

    def list_runs(self) -> list[str]:
        if not self.runs_dir.is_dir():
            return []
        return sorted(p.name for p in self.runs_dir.iterdir() if RUN_ID.fullmatch(p.name))
