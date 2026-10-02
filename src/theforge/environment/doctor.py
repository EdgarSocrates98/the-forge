"""`theforge doctor`: host, workspace and provider readiness. Read-only, offline."""

import os
import platform
import shutil
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from theforge.errors import PersistenceError, UsageError
from theforge.meta import VERSION
from theforge.protocol import SubprocessTransport, TransportFactory
from theforge.registry import Registry, check_health

REPORT_SCHEMA = "theforge/EnvironmentReport/v0"


@dataclass(frozen=True, kw_only=True)
class Check:
    name: str
    status: Literal["ok", "warn", "fail"]
    detail: str


def detect_host(env: Mapping[str, str]) -> str:
    if env.get("CLAUDECODE") == "1" or "CLAUDE_CODE_ENTRYPOINT" in env:
        return "claude-code"
    if any(key.startswith("CODEX_") for key in env):
        return "codex"
    if env.get("CI"):
        return "ci"
    return "terminal"


def _writable(directory: Path) -> bool:
    try:
        with tempfile.NamedTemporaryFile(dir=directory):
            return True
    except Exception:
        return False


def run_doctor(
    root: Path, registry: Registry, *, env: Mapping[str, str] | None = None,
    transport_factory: TransportFactory = SubprocessTransport,
) -> dict[str, Any]:
    environment = os.environ if env is None else env
    git = shutil.which("git")
    checks = [
        Check(name="os", status="ok", detail=f"{platform.system()} {platform.release()}"),
        Check(name="architecture", status="ok", detail=platform.machine() or "unknown"),
        Check(name="python", status="ok" if sys.version_info >= (3, 11) else "fail",
              detail=platform.python_version()),
        Check(name="git", status="ok" if git else "warn", detail=git or "not found on PATH"),
        Check(name="host", status="ok", detail=detect_host(environment)),
    ]
    forge_dir = registry.forge_dir
    if forge_dir is None:
        checks.append(Check(name="workspace", status="warn",
                            detail=f"{root} not initialized (run `theforge init`)"))
    else:
        checks.append(Check(name="workspace", status="ok" if _writable(forge_dir) else "fail",
                            detail=str(forge_dir)))
    try:
        records = registry.records(persist=False)
    except (UsageError, PersistenceError) as exc:
        checks.append(Check(name="providers", status="fail", detail=str(exc)))
        records = []
    for warning in registry.warnings:
        checks.append(Check(name="registry", status="warn", detail=warning))
    for record in records:
        health = check_health(record, transport_factory=transport_factory)
        healthy = health.status in ("ok", "degraded")
        status: Literal["ok", "warn", "fail"] = "ok"
        if not healthy:
            status = "fail" if record.entry.trust == "builtin" else "warn"
        detail = f"{record.state}/{health.status}"
        if health.error is not None:
            detail += f" {health.error.code}"
        checks.append(Check(name=f"provider:{record.entry.id}", status=status, detail=detail))
    return {
        "schema": REPORT_SCHEMA, "forge_version": VERSION, "root": str(root),
        "checks": [asdict(c) for c in checks],
        "healthy": all(c.status != "fail" for c in checks),
    }
