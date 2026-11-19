"""``.mcp.json`` config audit (cycle 16.1, FRENTE E §9.3).

Shared-config hygiene the kit writes but nothing verified until now:

- **namespacing** — ``_forge_managed.<tag>`` must point at keys that
  actually exist; a key claimed by two tags is a conflict, not a guess;
- **duplicates** — two ``mcpServers`` entries with identical argv are a
  defect (a host may launch both), reported, never silently tolerated;
- **PATH-dependence** — a bare command name resolves through PATH at
  launch time, which is exactly the ambiguity the install resolves away
  with an absolute interpreter/shim path. Bare commands are reported per
  server (``path_dependent: true``); a command that does not resolve at
  all fails.

Config-only by default: the audit never spawns the declared server — a
real startup probe is ``install mcp-verify`` (kit.mcp_verify). When the
probe cannot run the state is ``UNVERIFIED``, never success-by-config.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Final

MAX_SERVERS: Final = 64
MAX_DOC_BYTES: Final = 256 * 1024


def _command_kind(command: str) -> str:
    """Launch classification: ``absolute`` (fully qualified), ``explicit-path``
    (contains a separator — cwd-bound, not PATH-bound), ``path-dependent``
    (bare name — resolves through PATH at launch), ``missing``."""
    if not command:
        return "missing"
    if Path(command).is_absolute():
        return "absolute"
    if "/" in command or "\\" in command:
        return "explicit-path"
    return "path-dependent"


def audit_mcp(root: Path, *, spec: Any | None = None) -> dict[str, Any]:
    """Audit ``<root>/.mcp.json`` — namespacing, duplicates, launch kind.

    ``spec`` (a ``kit.ForgeSpec`` or ``None``) supplies the forge's own
    managed server name for a richer verdict; the audit is generic
    without it. Pure read — bounded, offline, deterministic.
    """
    root = Path(root)
    checks: list[dict[str, Any]] = []
    servers: dict[str, dict[str, Any]] = {}
    managed_claims: dict[str, list[str]] = {}  # key -> claiming tags
    mcp_file = root / ".mcp.json"

    if not mcp_file.is_file():
        return {
            "file": ".mcp.json",
            "present": False,
            "checks": [
                {
                    "id": "mcp-config",
                    "status": "NOT_APPLICABLE",
                    "detail": ".mcp.json absent — nothing to audit",
                }
            ],
            "servers": {},
        }

    try:
        if mcp_file.stat().st_size > MAX_DOC_BYTES:
            raise ValueError("exceeds audit bound")
        doc = json.loads(mcp_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return {
            "file": ".mcp.json",
            "present": True,
            "checks": [
                {
                    "id": "mcp-config",
                    "status": "FAIL",
                    "detail": f".mcp.json unreadable: {exc}",
                    "repairable": True,
                }
            ],
            "servers": {},
        }
    checks.append({"id": "mcp-config", "status": "PASS", "detail": "parses"})

    raw_servers = doc.get("mcpServers")
    if raw_servers is not None and not isinstance(raw_servers, dict):
        checks.append(
            {"id": "mcp-servers", "status": "FAIL", "detail": "mcpServers is not an object"}
        )
        raw_servers = {}
    for name, cfg in (raw_servers or {}).items():
        if len(servers) >= MAX_SERVERS:
            checks.append(
                {
                    "id": "mcp-servers",
                    "status": "FAIL",
                    "detail": f"more than {MAX_SERVERS} servers — audit bound exceeded",
                }
            )
            break
        cfg = cfg if isinstance(cfg, dict) else {}
        raw_command = cfg.get("command")
        command = raw_command if isinstance(raw_command, str) else ""
        raw_args = cfg.get("args")
        args: list[str] = [str(a) for a in raw_args] if isinstance(raw_args, list) else []
        argv = [command, *args] if command else []
        kind = _command_kind(command)
        resolved: str | None = None
        resolves = True
        if kind == "path-dependent":
            resolved = shutil.which(command)
            resolves = resolved is not None
        elif kind == "explicit-path":
            resolves = (root / command).exists() or Path(command).exists()
        elif kind == "absolute":
            resolves = Path(command).exists()
        servers[name] = {
            "argv": argv,
            "command_kind": kind,
            "resolves": resolves,
            "resolved_to": resolved,
        }

    # --- namespacing: _forge_managed claims ↔ real keys ------------------
    managed = doc.get("_forge_managed")
    managed_map: dict[str, list[str]] = {}
    if isinstance(managed, dict):
        for tag, keys in managed.items():
            if isinstance(keys, list):
                for key in keys:
                    managed_map.setdefault(str(key), []).append(str(tag))
    for key, tags in sorted(managed_map.items()):
        if len(tags) > 1:
            checks.append(
                {
                    "id": f"mcp-namespace:{key}",
                    "status": "FAIL",
                    "detail": f"{key!r} claimed by multiple forge tags {tags} — "
                    "namespace conflict, repair must reconcile",
                    "repairable": True,
                }
            )
        elif key.startswith("mcpServers."):
            server_key = key[len("mcpServers.") :]
            if server_key not in servers:
                checks.append(
                    {
                        "id": f"mcp-namespace:{key}",
                        "status": "FAIL",
                        "detail": f"{key!r} managed by {tags[0]!r} but the server entry is missing",
                        "repairable": True,
                    }
                )
            else:
                managed_claims.setdefault(server_key, []).append(tags[0])

    # --- duplicates: identical argv under two keys ------------------------
    seen: dict[tuple[str, ...], str] = {}
    duplicates = False
    for name, srv in sorted(servers.items()):
        argv_key = tuple(str(a) for a in srv["argv"])
        if not argv_key:
            continue
        prior = seen.get(argv_key)
        if prior is not None:
            duplicates = True
            checks.append(
                {
                    "id": f"mcp-duplicate:{name}",
                    "status": "FAIL",
                    "detail": f"duplicate server — {name!r} launches the same "
                    f"argv as {prior!r}; a host would spawn both",
                    "repairable": False,
                }
            )
        else:
            seen[argv_key] = name
    if servers:
        checks.append(
            {
                "id": "mcp-duplicates",
                "status": "FAIL" if duplicates else "PASS",
                "detail": (
                    "duplicate argv detected"
                    if duplicates
                    else f"{len(servers)} server(s), argv-unique"
                ),
            }
        )

    # --- PATH-dependence per server ---------------------------------------
    for name, srv in sorted(servers.items()):
        kind = srv["command_kind"]
        if kind == "missing":
            checks.append(
                {
                    "id": f"mcp-launch:{name}",
                    "status": "FAIL",
                    "detail": "no command declared",
                }
            )
        elif kind in ("path-dependent", "explicit-path") and not srv["resolves"]:
            checks.append(
                {
                    "id": f"mcp-launch:{name}",
                    "status": "FAIL",
                    "detail": f"command {srv['argv'][0]!r} does not resolve "
                    f"({kind}) — the host cannot launch it",
                }
            )
        elif kind == "path-dependent":
            checks.append(
                {
                    "id": f"mcp-launch:{name}",
                    "status": "WARN",
                    "detail": f"command {srv['argv'][0]!r} resolves via PATH "
                    f"({srv['resolved_to']}) — launch is environment-dependent; "
                    "an absolute interpreter/shim path is the managed form",
                }
            )
        elif kind == "absolute" and not srv["resolves"]:
            checks.append(
                {
                    "id": f"mcp-launch:{name}",
                    "status": "FAIL",
                    "detail": f"absolute command {srv['argv'][0]!r} does not exist "
                    "on this machine — reinstall/repair refreshes the entry",
                    "repairable": True,
                }
            )

    own = getattr(spec, "mcp_server_name", None) if spec is not None else None
    own_entry = servers.get(own) if isinstance(own, str) else None
    if isinstance(own, str):
        checks.append(
            {
                "id": "mcp-own-entry",
                "status": "PASS"
                if own_entry and own_entry["command_kind"] == "absolute"
                else "FAIL"
                if own_entry is not None
                else "UNVERIFIED",
                "detail": (
                    f"{own!r} uses an absolute launch path"
                    if own_entry and own_entry["command_kind"] == "absolute"
                    else f"{own!r} is PATH-dependent — reinstall/repair writes the resolved argv"
                    if own_entry is not None
                    else f"{own!r} not present in .mcp.json"
                ),
                "repairable": own_entry is not None and own_entry["command_kind"] != "absolute",
            }
        )

    return {
        "file": ".mcp.json",
        "present": True,
        "checks": checks,
        "servers": {
            name: {
                "command_kind": srv["command_kind"],
                "resolves": srv["resolves"],
                "argv": srv["argv"],
                "managed_by": managed_claims.get(name) or None,
            }
            for name, srv in sorted(servers.items())
        },
    }


__all__ = ["audit_mcp"]
