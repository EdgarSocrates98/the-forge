"""Run store: one directory per run, redacted JSON artifacts, hashes over what is on disk."""

import json
import re
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, TypeVar

from theforge.contracts import (
    ContextPack,
    ExecutionReceipt,
    ExecutionResult,
    RiskAssessment,
    RoutingDecision,
    RunTelemetry,
    TaskSpec,
    from_dict,
    to_dict,
)
from theforge.contracts.canonical import sha256_of
from theforge.contracts.integrity import validate_receipt
from theforge.errors import PersistenceError
from theforge.security.redact import redact

T = TypeVar("T")

RUN_ID = re.compile(r"^\d{8}T\d{6}Z-[0-9a-f]{8}$")
# Run order. context-r1/context-r2 (negotiation rounds) and telemetry are optional: runs
# written before they existed stay readable (read_optional returns None).
ARTIFACTS = ("task", "routing", "risk", "context", "context-r1", "context-r2", "result",
             "telemetry", "receipt")
ARTIFACT_TYPES: Final[dict[str, type]] = {
    "task": TaskSpec,
    "routing": RoutingDecision,
    "risk": RiskAssessment,
    "context": ContextPack,
    "context-r1": ContextPack,
    "context-r2": ContextPack,
    "result": ExecutionResult,
    "telemetry": RunTelemetry,
    "receipt": ExecutionReceipt,
}


def new_run_id() -> str:
    return f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(4)}"


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
        return directory

    def _artifact_path(self, run_id: str, name: str) -> Path:
        if name not in ARTIFACTS:
            raise ValueError(f"unknown run artifact {name!r}")
        return self.run_dir(run_id) / f"{name}.json"

    def write(self, run_id: str, name: str, contract: Any) -> str:
        """Redact, persist atomically and return the sha256 of the on-disk content.

        A receipt is validated before it is written (1.8): its ``result_sha256`` must equal
        the hash of the result already persisted in this run, recomputed from disk exactly
        as this method computes it. An invalid receipt raises ``IntegrityError`` and nothing
        is written.
        """
        path = self._artifact_path(run_id, name)
        if name == "receipt":
            if not isinstance(contract, ExecutionReceipt):
                raise TypeError(f"receipt artifact must be an ExecutionReceipt, "
                                f"got {type(contract).__name__}")
            validate_receipt(contract, result_sha256=self.persisted_sha256(run_id, "result"))
        data = redact(to_dict(contract))
        text = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)
        tmp = path.with_suffix(".json.tmp")
        try:
            tmp.write_text(text, encoding="utf-8")
            tmp.replace(path)
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
        path = self._artifact_path(run_id, name)
        if not path.is_file():
            return None
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:  # JSON/Unicode decode errors are ValueErrors
            raise PersistenceError(f"cannot read {path}: {exc}") from exc
        if not isinstance(loaded, dict):
            raise PersistenceError(f"cannot read {path}: expected a JSON object")
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
