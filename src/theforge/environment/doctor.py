"""`theforge doctor`: host, workspace and provider readiness. Read-only, offline."""

import os
import platform
import shutil
import sys
import tempfile
from collections.abc import Iterator, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from theforge.environment.guidance import block_for
from theforge.environment.layers import group_layers
from theforge.errors import PersistenceError, UsageError
from theforge.meta import VERSION
from theforge.protocol import SubprocessTransport, TransportFactory
from theforge.registry import Registry, check_health

REPORT_SCHEMA = "theforge/EnvironmentReport/v0"
ACCOUNT_ENV_SUFFIXES = ("HOME", "INSTALL_ROOT", "VENV", "PYTHON", "CLI")
_SECRET_NAME_HINTS = (
    ".env",
    ".pem",
    ".key",
    "credential",
    "secret",
    "id_rsa",
    "token",
)
_SCAN_BOUND = 4_096  # file-name scans in the doctor stay bounded (§14.7)
_HOST_SKILL_DIRS = (".claude/skills", ".agents/skills", ".devin/skills", ".github/skills")
_HOST_AGENT_DIRS = (".claude/agents", ".agents/agents", ".devin/agents", ".codex/agents")
_RECEIPTS_DIR = ".forge/install/receipts"
_INSTALL_STATE = ".forge/install"


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
    # --- cycle 16.1 §10.1: the remaining named layers ---------------------
    checks.extend(_layer_checks(root, environment))
    layer_rows = group_layers([asdict(c) for c in checks])
    # §10.2 — PROBLEMA/CAUSA PROVÁVEL/AÇÃO/ESTADO on every failing check.
    out_checks: list[dict[str, Any]] = []
    for c in checks:
        row = asdict(c)
        if c.status == "fail":
            row["guidance"] = block_for(c.name, c.status, c.detail)
        out_checks.append(row)
    return {
        "schema": REPORT_SCHEMA,
        "forge_version": VERSION,
        "root": str(root),
        "checks": out_checks,
        "layers": layer_rows,
        "account_environment": account_environment,
        "healthy": all(c.status != "fail" for c in checks),
    }


# ---------------------------------------------------------------------------
# §10.1 layer checks — bounded, read-only, offline. Each check is a measured
# observation (file counts, parsed configs), never a guessed state.
# ---------------------------------------------------------------------------


def _iter_names(base: Path, budget: list[int]) -> Iterator[Path]:
    """Bounded symlink-free file walk — yields paths while budget remains."""
    if not base.is_dir() or base.is_symlink():
        return
    stack = [base]
    while stack and budget[0] > 0:
        current = stack.pop()
        try:
            entries = sorted(current.iterdir(), key=lambda e: e.name)
        except OSError:
            continue
        for entry in entries:
            if budget[0] <= 0:
                return
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir():
                    stack.append(entry)
                    continue
                if entry.is_file():
                    budget[0] -= 1
                    yield entry
            except OSError:
                continue


def _count_under(root: Path, dirs: tuple[str, ...], budget: list[int]) -> tuple[int, int]:
    """``(files, dirs_present)`` under each dir in ``dirs`` relative to root."""
    files, present = 0, 0
    for rel in dirs:
        base = root / rel
        if base.is_dir() and not base.is_symlink():
            present += 1
            for _ in _iter_names(base, budget):
                files += 1
    return files, present


def _count_matching(root: Path, dirs: tuple[str, ...], part: str, budget: list[int]) -> int:
    """Count files whose path contains a ``part`` component (e.g. 'evals')."""
    total = 0
    for rel in dirs:
        base = root / rel
        for path in _iter_names(base, budget):
            if part in path.relative_to(root).parts:
                total += 1
    return total


def _layer_checks(root: Path, environment: Mapping[str, str]) -> list[Check]:
    """The §10.1 layers the classic checks do not cover — measured only."""
    checks: list[Check] = [Check(name="version", status="ok", detail=f"theforge {VERSION}")]
    budget = [_SCAN_BOUND]

    # Lazy imports hoisted once — a broken optional reader degrades to a
    # single warn, never kills the doctor.
    kit = fctx = service = audit_mcp = load_workspace_config = None
    try:
        from theforge import _forgecontext as _fctx
        from theforge import _installkit as _kit
        from theforge.install import service as _service
        from theforge.install.mcp_audit import audit_mcp as _audit_mcp
        from theforge.workspace.config import load_workspace_config as _lwc

        kit, fctx, service, audit_mcp, load_workspace_config = (
            _kit,
            _fctx,
            _service,
            _audit_mcp,
            _lwc,
        )
    except Exception as exc:
        checks.append(Check(name="doctor-imports", status="warn", detail=f"{exc}"))

    # --- members (5) --------------------------------------------------------
    if load_workspace_config is None:
        checks.append(Check(name="members", status="warn", detail="config reader unavailable"))
    else:
        try:
            cfg = load_workspace_config(root)
        except Exception as exc:  # a reader bug must not kill the doctor
            cfg = None
            checks.append(
                Check(name="members", status="warn", detail=f"workspace config unreadable: {exc}")
            )
        if cfg is None and not any(c.name == "members" for c in checks):
            checks.append(
                Check(
                    name="members",
                    status="ok",
                    detail="no forge.workspace.yaml — single-repo workspace",
                )
            )
        elif cfg is not None:
            missing = [m for m in cfg.members if not (root / m).is_dir()]
            uninitialized = [
                m for m in cfg.members if (root / m).is_dir() and not (root / m / ".forge").exists()
            ]
            detail = f"{len(cfg.members)} member(s)"
            if missing:
                detail += f"; missing: {', '.join(missing)}"
            if uninitialized:
                detail += f"; no .forge: {', '.join(uninitialized)}"
            if cfg.warnings:
                detail += f"; config warnings: {len(cfg.warnings)}"
            checks.append(
                Check(
                    name="members",
                    status=(
                        "fail" if missing else "warn" if uninitialized or cfg.warnings else "ok"
                    ),
                    detail=detail,
                )
            )

    # --- contracts (6) — .forge/context registry validity --------------------
    caps: dict[str, Any] = {}
    if fctx is None:
        checks.append(Check(name="contracts", status="warn", detail="context reader unavailable"))
    else:
        try:
            registry_doc = fctx._load_json(fctx.registry_path(root), None)
            caps = fctx.list_capabilities(root)
            if registry_doc is None:
                checks.append(
                    Check(
                        name="contracts",
                        status="warn",
                        detail="no .forge/context/registry.json — context layer not installed",
                    )
                )
            elif not isinstance(registry_doc, dict):
                checks.append(
                    Check(name="contracts", status="fail", detail="registry.json is not an object")
                )
            else:
                problems = fctx.validate_registry(registry_doc)
                if problems:
                    checks.append(
                        Check(
                            name="contracts",
                            status="fail",
                            detail=f"registry.json: {len(problems)} validation problem(s) "
                            f"— first: {problems[0][:120]}",
                        )
                    )
                else:
                    checks.append(
                        Check(
                            name="contracts",
                            status="ok",
                            detail=(
                                f"registry valid ({len(registry_doc.get('forges') or [])} forges)"
                            ),
                        )
                    )
        except Exception as exc:  # context reader bugs degrade, never kill
            checks.append(
                Check(name="contracts", status="warn", detail=f"context audit failed: {exc}")
            )

    # --- skills (7) / agents (8) / knowledge (9) / rules (10) / evals (11) ----
    skills, skill_dirs = _count_under(root, _HOST_SKILL_DIRS, budget)
    skill_mds = sum(
        1 for d in _HOST_SKILL_DIRS for p in _iter_names(root / d, budget) if p.name == "SKILL.md"
    )
    checks.append(
        Check(
            name="skills",
            status="ok" if skill_mds else "warn",
            detail=f"{skill_mds} SKILL.md across {skill_dirs} host dir(s) ({skills} files)",
        )
    )
    agents, agent_dirs = _count_under(root, _HOST_AGENT_DIRS, budget)
    checks.append(
        Check(
            name="agents",
            status="ok" if agents else "warn",
            detail=f"{agents} agent file(s) across {agent_dirs} host dir(s)",
        )
    )
    for layer, part in (
        ("knowledge", "knowledge"),
        ("rules", "rules"),
        ("evals", "evals"),
    ):
        count = _count_matching(root, _HOST_SKILL_DIRS + _HOST_AGENT_DIRS, part, budget)
        checks.append(
            Check(
                name=layer,
                status="ok",
                detail=f"{count} file(s) under */{part}/ in installed assets",
            )
        )

    # --- mcp (12) — config audit; the startup probe is `install mcp-verify` ---
    if audit_mcp is None:
        checks.append(Check(name="mcp", status="warn", detail="mcp audit unavailable"))
    else:
        try:
            audit = audit_mcp(root)
            status_map: dict[str, Literal["ok", "warn", "fail"]] = {
                "PASS": "ok",
                "WARN": "warn",
                "FAIL": "fail",
            }
            if not audit.get("present"):
                checks.append(
                    Check(name="mcp", status="ok", detail="no .mcp.json — nothing declared")
                )
            else:
                for item in (audit.get("checks") or [])[:32]:
                    checks.append(
                        Check(
                            name=f"mcp:{item['id']}",
                            status=status_map.get(item.get("status"), "ok"),
                            detail=str(item.get("detail") or item.get("status") or ""),
                        )
                    )
            checks.append(
                Check(
                    name="mcp:probe",
                    status="ok",
                    detail="not run here (UNVERIFIED) — `install mcp-verify` is "
                    "the real startup handshake; config presence is NOT "
                    "verified startup",
                )
            )
        except Exception as exc:
            checks.append(Check(name="mcp", status="warn", detail=f"mcp audit failed: {exc}"))

    # --- secrets (14) — file NAMES only, never content -----------------------
    secrets_found: list[str] = []
    secret_budget = [budget[0]]
    for path in _iter_names(root / ".forge", secret_budget):
        if any(hint in path.name.lower() for hint in _SECRET_NAME_HINTS):
            secrets_found.append(path.relative_to(root).as_posix())
    try:
        for entry in sorted(root.iterdir(), key=lambda e: e.name):
            if entry.is_file() and any(h in entry.name.lower() for h in _SECRET_NAME_HINTS):
                secrets_found.append(entry.name)
    except OSError:
        pass
    checks.append(
        Check(
            name="secrets",
            status="warn" if secrets_found else "ok",
            detail=(
                f"{len(secrets_found)} secret-shaped filename(s): "
                + ", ".join(sorted(set(secrets_found))[:5])
                + " (names observed — content never read)"
                if secrets_found
                else "no secret-shaped filenames under .forge/ or root"
            ),
        )
    )

    # --- ownership (15) + drift (16) -----------------------------------------
    ledger_count = 0
    if kit is None or service is None:
        checks.append(Check(name="ownership", status="warn", detail="ledger reader unavailable"))
    else:
        try:
            state_dir = root / _INSTALL_STATE
            if (state_dir / kit.LEDGER_NAME).is_file():
                ledger = kit.Ledger.load(state_dir)
                ledger_count = len(ledger.entries())
                spec = service._spec()
                drift_rows = ledger.drift(root, spec, mcp_argv=service._resolved_mcp_command(spec))
                for row in drift_rows:
                    if row["status"] == "ok":
                        continue
                    checks.append(
                        Check(name=f"drift:{row['path']}", status="fail", detail=row["status"])
                    )
                checks.append(
                    Check(name="ownership", status="ok", detail=f"{ledger_count} managed entries")
                )
                if not any(c.name.startswith("drift:") for c in checks):
                    checks.append(Check(name="drift", status="ok", detail="ledger matches disk"))
            else:
                checks.append(
                    Check(
                        name="ownership",
                        status="warn",
                        detail="no install ledger at .forge/install — nothing managed",
                    )
                )
        except Exception as exc:
            checks.append(
                Check(name="ownership", status="warn", detail=f"ledger audit failed: {exc}")
            )

    # --- dependencies (17) ----------------------------------------------------
    if service is None or kit is None:
        checks.append(
            Check(name="dependencies", status="warn", detail="dependency audit unavailable")
        )
    else:
        try:
            deps = list(service._manifest().get("depends_on") or [])
            if deps:
                installed = {m.get("forge_id") for m in kit.installed_forges()}
                missing = [d for d in deps if d not in installed]
                checks.append(
                    Check(
                        name="dependencies",
                        status="fail" if missing else "ok",
                        detail=(
                            f"missing declared forges: {', '.join(missing)}"
                            if missing
                            else f"{len(deps)} declared dependency(ies) installed"
                        ),
                    )
                )
            else:
                checks.append(
                    Check(name="dependencies", status="ok", detail="no dependencies declared")
                )
        except Exception as exc:
            checks.append(
                Check(name="dependencies", status="warn", detail=f"dependency audit failed: {exc}")
            )

    # --- receipts (18) ---------------------------------------------------------
    receipts_dir = root / _RECEIPTS_DIR
    receipt_files = sorted(receipts_dir.glob("*.json")) if receipts_dir.is_dir() else []
    if not receipt_files:
        checks.append(Check(name="receipts", status="ok", detail="no receipts recorded"))
    else:
        last = receipt_files[-1]
        status: Literal["ok", "warn", "fail"] = "ok"
        detail = f"{len(receipt_files)} receipt(s); last {last.name}"
        try:
            doc = kit._load_json(last, None) if kit is not None else None
            last_status = (doc or {}).get("status")
            detail += f" status:{last_status}"
            if last_status not in ("completed", "planned", "verified"):
                status = "warn"
        except Exception:
            status = "warn"
            detail += " (unreadable)"
        checks.append(Check(name="receipts", status=status, detail=detail))

    # --- context (19) ----------------------------------------------------------
    ctx_dir = root / ".forge" / "context"
    checks.append(
        Check(
            name="context",
            status="ok" if caps or not ctx_dir.exists() else "warn",
            detail=(
                f"{len(caps)} capability manifest(s) in .forge/context"
                if caps
                else "no .forge/context layer"
                if not ctx_dir.exists()
                else ".forge/context exists but no manifests parse"
            ),
        )
    )

    # --- ci (20) --------------------------------------------------------------
    checks.append(
        Check(
            name="ci",
            status="ok",
            detail="CI environment" if environment.get("CI") else "local environment",
        )
    )
    return checks
