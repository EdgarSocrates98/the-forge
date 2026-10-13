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
ACCOUNT_ENV_SUFFIXES = ("HOME", "INSTALL_ROOT", "VENV", "PYTHON", "CLI")


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


def _account_environment(env: Mapping[str, str]) -> list[dict[str, Any]]:
    """Inspect published account paths; absent forge variables stay non-fatal.

    Prefixes are discovered from the published contract instead of being
    catalogued here. New specialists become visible automatically.
    """
    out: list[dict[str, Any]] = []
    prefixes = sorted(
        {
            key[: -(len(suffix) + 1)]
            for key in env
            for suffix in ACCOUNT_ENV_SUFFIXES
            if key.upper().endswith(f"_{suffix}")
            and "FORGE" in key[: -(len(suffix) + 1)].upper().split("_")
        }
    )
    for prefix in prefixes:
        prefix = prefix.upper()
        forge_id = prefix.lower().replace("_", "-")
        required = {
            "HOME": "directory",
            "INSTALL_ROOT": "directory",
            "VENV": "directory",
            "PYTHON": "file",
            "CLI": "file",
        }
        present = {suffix: str(env.get(f"{prefix}_{suffix}", "")).strip() for suffix in required}
        if not any(present.values()):
            continue
        variables = []
        missing = []
        invalid = []
        for suffix, kind in required.items():
            raw = present[suffix]
            path = Path(raw).expanduser() if raw else None
            valid = bool(path and (path.is_dir() if kind == "directory" else path.is_file()))
            variables.append({"name": f"{prefix}_{suffix}", "present": bool(raw), "valid": valid})
            if not raw:
                missing.append(suffix)
            elif not valid:
                invalid.append(suffix)
        state = "invalid" if invalid else "partial" if missing else "ready"
        out.append(
            {
                "forge_id": forge_id,
                "prefix": prefix,
                "state": state,
                "variables": variables,
            }
        )
    return out


def run_doctor(
    root: Path,
    registry: Registry,
    *,
    env: Mapping[str, str] | None = None,
    transport_factory: TransportFactory = SubprocessTransport,
) -> dict[str, Any]:
    environment = os.environ if env is None else env
    git = shutil.which("git")
    checks = [
        Check(name="os", status="ok", detail=f"{platform.system()} {platform.release()}"),
        Check(name="architecture", status="ok", detail=platform.machine() or "unknown"),
        Check(
            name="python",
            status="ok" if sys.version_info >= (3, 11) else "fail",
            detail=platform.python_version(),
        ),
        Check(name="git", status="ok" if git else "warn", detail=git or "not found on PATH"),
        Check(name="host", status="ok", detail=detect_host(environment)),
    ]
    account_environment = _account_environment(environment)
    if not account_environment:
        checks.append(
            Check(
                name="account-environment",
                status="warn",
                detail="no Forge account environment published; run install.ps1 or install.sh",
            )
        )
    else:
        invalid = [row["forge_id"] for row in account_environment if row["state"] == "invalid"]
        partial = [row["forge_id"] for row in account_environment if row["state"] == "partial"]
        account_status: Literal["ok", "warn", "fail"] = (
            "fail" if invalid else "warn" if partial else "ok"
        )
        detail = (
            ", ".join(
                [
                    *(f"invalid: {forge}" for forge in invalid),
                    *(f"partial: {forge}" for forge in partial),
                ]
            )
            or f"ready: {len(account_environment)} Forge(s)"
        )
        checks.append(Check(name="account-environment", status=account_status, detail=detail))
    forge_dir = registry.forge_dir
    if forge_dir is None:
        checks.append(
            Check(
                name="workspace",
                status="warn",
                detail=f"{root} not initialized (run `theforge init`)",
            )
        )
    else:
        checks.append(
            Check(
                name="workspace",
                status="ok" if _writable(forge_dir) else "fail",
                detail=str(forge_dir),
            )
        )
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
        if health.surface_fingerprint is not None:
            detail += f" surface:{health.surface_fingerprint[:12]}"
        if health.error is not None:
            detail += f" {health.error.code}"
        checks.append(Check(name=f"provider:{record.entry.id}", status=status, detail=detail))
    return {
        "schema": REPORT_SCHEMA,
        "forge_version": VERSION,
        "root": str(root),
        "checks": [asdict(c) for c in checks],
        "account_environment": account_environment,
        "healthy": all(c.status != "fail" for c in checks),
    }
