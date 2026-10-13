"""Approval-gated provider registration from local Forge installation manifests.

The bootstrap registry says where a Forge lives. This module turns that local,
user-approved fact into the user provider registry without touching unmanaged
configuration. Runtime truth still comes from ``describe`` after the write.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from theforge.errors import UsageError
from theforge.knowledge import knowledge_for
from theforge.registry.config import load_entries, user_config_dir
from theforge.registry.registry import Registry

BEGIN = "# BEGIN THEFORGE MANAGED PROVIDERS"
END = "# END THEFORGE MANAGED PROVIDERS"
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_MODULE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
_PROVIDER_ID = re.compile(r"^[a-z][a-z0-9-]*$")


def _prefix(forge_id: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", forge_id.upper()).strip("_")


def _variables(manifest: dict[str, Any]) -> dict[str, str]:
    values = (manifest.get("environment") or {}).get("variables")
    if not isinstance(values, dict):
        return {}
    return {str(k): str(v) for k, v in values.items() if isinstance(v, str) and v}


def manifest_python(manifest: dict[str, Any]) -> str | None:
    """Resolve account-scoped interpreter first, then installation manifest."""
    prefix = _prefix(str(manifest.get("forge_id") or ""))
    values = _variables(manifest)
    candidates = [
        values.get(f"{prefix}_PYTHON"),
        ((manifest.get("python") or {}).get("executable")),
    ]
    venv = manifest.get("venv")
    if isinstance(venv, str) and venv:
        candidates.append(
            str(Path(venv) / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))
        )
    for raw in candidates:
        if not isinstance(raw, str) or not raw:
            continue
        path = Path(raw).expanduser()
        if path.is_file():
            return str(path.resolve())
    return None


def manifest_cli(manifest: dict[str, Any]) -> str | None:
    """Resolve account-scoped launcher before a PATH-only CLI name."""
    forge_id = str(manifest.get("forge_id") or "")
    values = _variables(manifest)
    raw = values.get(f"{_prefix(forge_id)}_CLI")
    if raw:
        return raw
    cli = manifest.get("cli")
    if isinstance(cli, dict):
        shim = cli.get("shim")
        if isinstance(shim, str) and shim:
            return shim
        name = cli.get("name")
    else:
        name = cli
    return str(name) if isinstance(name, str) and name else None


def _replace_template(value: str, replacements: dict[str, str]) -> str:
    result = value
    for key, replacement in replacements.items():
        result = result.replace("{" + key + "}", replacement)
    if "{" in result or "}" in result:
        raise UsageError(f"provider command contains unresolved placeholder: {value!r}")
    return result


def _adapter_module(forge_id: str) -> str | None:
    package = knowledge_for(forge_id)
    if package is None or not package.adapter:
        return None
    name = Path(package.adapter).name
    if not _IDENTIFIER.fullmatch(name):
        return None
    return f"theforge_{name}"


def provider_argv(manifest: dict[str, Any]) -> tuple[list[str] | None, str | None]:
    """Return a direct, shell-free Forge Protocol argv for one installation."""
    forge_id = manifest.get("forge_id")
    if not isinstance(forge_id, str) or not _PROVIDER_ID.fullmatch(forge_id):
        return None, "invalid forge id"
    if forge_id == "the-forge":
        return None, "control plane is not a specialist provider"

    provider = manifest.get("provider")
    provider = provider if isinstance(provider, dict) else {}
    raw = provider.get("argv") or manifest.get("provider_argv")
    interpreter = manifest_python(manifest)
    cli = manifest_cli(manifest) or ""
    checkout = str((manifest.get("source") or {}).get("path") or "")
    install_root = str(manifest.get("install_root") or "")
    replacements = {
        "python": interpreter or "",
        "cli": cli,
        "checkout": checkout,
        "home": checkout,
        "install_root": install_root,
    }
    if raw is None:
        module = provider.get("module") or manifest.get("provider_module")
        if not isinstance(module, str) or not _MODULE.fullmatch(module):
            module = _adapter_module(forge_id)
        if module is None:
            return None, "provider adapter metadata is unavailable"
        if interpreter is None:
            return None, "registered Python interpreter is missing"
        return [interpreter, "-m", module], None
    if not isinstance(raw, list) or not raw or not all(isinstance(item, str) for item in raw):
        return None, "provider argv must be a non-empty string list"
    if not interpreter and any("{python}" in item for item in raw):
        return None, "registered Python interpreter is missing"
    try:
        argv = [_replace_template(item, replacements) for item in raw]
    except UsageError as exc:
        return None, str(exc)
    if not argv or not argv[0]:
        return None, "provider argv executable is empty"
    executable = Path(argv[0]).expanduser()
    if executable.is_absolute() and not executable.is_file():
        return None, f"provider executable is missing: {executable}"
    return argv, None


def _managed_ids(text: str) -> set[str]:
    start = text.find(BEGIN)
    end = text.find(END)
    if start < 0 and end < 0:
        return set()
    if start < 0 or end < start:
        raise UsageError("providers.toml has an incomplete The Forge managed block")
    body = text[start : end + len(END)]
    return set(re.findall(r'^\s*id\s*=\s*"([a-z][a-z0-9-]*)"\s*$', body, re.MULTILINE))


def _remove_managed(text: str) -> str:
    start = text.find(BEGIN)
    end = text.find(END)
    if start < 0 and end < 0:
        return text
    if start < 0 or end < start:
        raise UsageError("providers.toml has an incomplete The Forge managed block")
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end + len(END))
    if line_end < 0:
        line_end = len(text)
    else:
        line_end += 1
    return text[:line_start] + text[line_end:]


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def _managed_block(entries: Iterable[tuple[str, list[str]]]) -> str:
    rows = [BEGIN]
    for forge_id, argv in entries:
        rows.extend(
            [
                "",
                "[[providers]]",
                f"id = {_toml_string(forge_id)}",
                "argv = [" + ", ".join(_toml_string(arg) for arg in argv) + "]",
                'trust = "local"',
            ]
        )
    rows.append(END)
    return "\n".join(rows)


def _replace_managed(text: str, entries: list[tuple[str, list[str]]]) -> str:
    base = _remove_managed(text).rstrip()
    if not entries:
        return (base + "\n") if base else ""
    block = _managed_block(entries)
    return (base + "\n\n" if base else "") + block + "\n"


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def sync(
    manifests: Iterable[dict[str, Any]],
    *,
    root: Path | None = None,
    forge: str | None = None,
    approved: bool = False,
    dry_run: bool = False,
    refresh: bool = True,
) -> dict[str, Any]:
    """Synchronize managed providers and re-describe them after applying.

    ``approved`` is required for any file write. Existing user-authored
    entries always win; only the marked The Forge block is replaced.
    """
    config_dir = user_config_dir()
    config_path = config_dir / "providers.toml"
    manifests = [m for m in manifests if isinstance(m, dict)]
    if forge is not None:
        manifests = [m for m in manifests if m.get("forge_id") == forge]

    try:
        current = config_path.read_text(encoding="utf-8") if config_path.is_file() else ""
        existing = load_entries(config_path, "user") if config_path.is_file() else []
        existing_ids = {entry.id for entry in existing}
        managed_ids = _managed_ids(current)
    except (OSError, UnicodeError, UsageError) as exc:
        return {
            "status": "failed",
            "path": str(config_path),
            "verification": {"status": "FAIL"},
            "entries": [],
            "error": str(exc),
        }

    candidates: list[tuple[str, list[str]]] = []
    managed_existing = {
        entry.id: (entry.id, list(entry.argv)) for entry in existing if entry.id in managed_ids
    }
    preserved_managed: dict[str, tuple[str, list[str]]] = {}
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for manifest in sorted(manifests, key=lambda item: str(item.get("forge_id", ""))):
        forge_id = str(manifest.get("forge_id") or "")
        if not forge_id or forge_id in seen or forge_id == "the-forge":
            continue
        seen.add(forge_id)
        if forge_id in existing_ids and forge_id not in managed_ids:
            rows.append({"forge_id": forge_id, "status": "preserved-user"})
            continue
        argv, reason = provider_argv(manifest)
        if argv is None:
            rows.append({"forge_id": forge_id, "status": "blocked", "detail": reason})
            if forge_id in managed_existing:
                preserved_managed[forge_id] = managed_existing[forge_id]
                rows[-1]["status"] = "blocked-preserved"
            continue
        candidates.append((forge_id, argv))
        rows.append({"forge_id": forge_id, "status": "planned", "argv": argv})

    # A scoped sync updates one Forge without deleting managed registrations for
    # other Forges. An unscoped sync intentionally removes stale managed entries.
    if forge is not None:
        for forge_id, entry in managed_existing.items():
            if forge_id not in seen:
                preserved_managed[forge_id] = entry

    desired_entries = sorted([*preserved_managed.values(), *candidates], key=lambda item: item[0])
    desired = _replace_managed(current, desired_entries)
    changed = desired != current
    if dry_run:
        return {
            "status": "planned",
            "path": str(config_path),
            "changed": changed,
            "verification": {"status": "UNVERIFIED"},
            "entries": rows,
        }
    if not approved:
        return {
            "status": "refused",
            "path": str(config_path),
            "changed": False,
            "verification": {"status": "UNVERIFIED"},
            "entries": rows,
            "detail": "provider registration requires explicit approval",
        }
    try:
        if changed:
            _atomic_write(config_path, desired)
    except OSError as exc:
        return {
            "status": "failed",
            "path": str(config_path),
            "verification": {"status": "FAIL"},
            "entries": rows,
            "error": f"cannot write providers.toml: {exc}",
        }

    records: list[dict[str, Any]] = []
    if refresh and candidates:
        forge_dir = root / ".forge" if root is not None and (root / ".forge").is_dir() else None
        registry = Registry(forge_dir, user_dir=config_dir)
        for record in registry.refresh():
            if record.entry.id in {item[0] for item in candidates}:
                records.append(
                    {
                        "forge_id": record.entry.id,
                        "state": record.state,
                        "routable": record.routable(),
                        "error": record.error,
                    }
                )
        by_id = {item["forge_id"]: item for item in records}
        for row in rows:
            if row["forge_id"] in by_id:
                status = "ready" if by_id[row["forge_id"]]["routable"] else "unavailable"
                row.update({"status": status})

    blocked = any(item["status"] in ("blocked", "blocked-preserved") for item in rows)
    if blocked:
        ready = False
    elif not candidates:
        ready = True
    elif refresh:
        ready = len(records) == len(candidates) and all(item["routable"] for item in records)
    else:
        ready = False
    return {
        "status": "completed",
        "path": str(config_path),
        "changed": changed,
        "verification": {"status": "PASS" if ready else "UNVERIFIED"},
        "entries": rows,
        "records": records,
    }


__all__ = ["manifest_cli", "manifest_python", "provider_argv", "sync"]
