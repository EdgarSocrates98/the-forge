"""Run store: one directory per run, redacted JSON artifacts, hashes over what is on disk."""

import json
import re
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from theforge.contracts import to_dict
from theforge.contracts.canonical import sha256_of
from theforge.errors import PersistenceError
from theforge.security.redact import redact

RUN_ID = re.compile(r"^\d{8}T\d{6}Z-[0-9a-f]{8}$")
ARTIFACTS = ("task", "routing", "context", "result", "receipt")


def new_run_id() -> str:
    return f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(4)}"


class RunStore:
    def __init__(self, forge_dir: Path) -> None:
        self.runs_dir = forge_dir / "runs"

    def run_dir(self, run_id: str) -> Path:
        if not RUN_ID.match(run_id):
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

    def write(self, run_id: str, name: str, contract: Any) -> str:
        if name not in ARTIFACTS:
            raise ValueError(f"unknown run artifact {name!r}")
        data = redact(to_dict(contract))
        path = self.run_dir(run_id) / f"{name}.json"
        tmp = path.with_suffix(".json.tmp")
        try:
            tmp.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False),
                           encoding="utf-8")
            tmp.replace(path)
        except OSError as exc:
            raise PersistenceError(f"cannot write {path}: {exc}") from exc
        return sha256_of(data)

    def read(self, run_id: str, name: str) -> dict[str, Any]:
        data = self.read_optional(run_id, name)
        if data is None:
            raise LookupError(f"run {run_id} has no {name}")
        return data

    def read_optional(self, run_id: str, name: str) -> dict[str, Any] | None:
        path = self.run_dir(run_id) / f"{name}.json"
        if not path.is_file():
            return None
        loaded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return loaded

    def list_runs(self) -> list[str]:
        if not self.runs_dir.is_dir():
            return []
        return sorted(p.name for p in self.runs_dir.iterdir() if RUN_ID.match(p.name))
