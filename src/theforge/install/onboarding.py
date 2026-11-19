"""Host onboarding summary (cycle 16.1, §6.4 + §9.2).

Per-host *honest* state after a setup run — a closed vocabulary, always
derived from evidence, never asserted:

- ``not_found``            — no binary, no project config dir, no session marker.
- ``in_path``              — host binary resolvable on ``PATH``.
- ``configurable``         — a host config dir exists in the workspace
                             (``.claude/``, ``.codex/``, …) but no binary.
                             A bare directory is NEVER readiness proof.
- ``installed``            — two independent evidence classes agree
                             (binary + config dir, or a session marker).
- ``integration_written``  — this run wrote host assets and the host is
                             not installed here — they load at first launch.
- ``restart_needed``       — integration was written *this run* and the
                             host is installed — restart it to load assets.
- ``mcp_verified``         — the managed MCP server answered a real
                             JSON-RPC handshake.
- ``validated``            — a host observed running the assets
                             (``theforge hosts observe`` READY). Setup
                             never claims it — the vocabulary exists so
                             the distinction is visible.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Final

from theforge import host_detect
from theforge._installkit import _host_dirs

ONBOARDING_SCHEMA: Final = "forge/HostOnboarding/v1"

HOST_STATES: Final[tuple[str, ...]] = (
    "not_found",
    "installed",
    "in_path",
    "configurable",
    "integration_written",
    "restart_needed",
    "mcp_verified",
    "validated",
)

_NEXT_STEPS: Final = (
    "open the workspace root in the chosen host",
    "restart the host if it was already running (new assets load at startup)",
    "theforge hosts observe <host> — live state, auth, launch",
    "theforge install mcp-verify — MCP handshake check",
    "theforge doctor — workspace health",
)


def _base_state(host: str, detection: host_detect.HostDetectionResult) -> tuple[str, str]:
    """Detection-only state — what the workspace *already* evidences."""
    d = detection.for_host(host)
    if d is None:
        return "not_found", "unknown host"
    kinds = {e.kind for e in d.evidence}
    if d.running:
        return "installed", "session markers observed"
    if "binary" in kinds and "config_dir" in kinds:
        return "installed", "binary on PATH + project config dir"
    if "binary" in kinds:
        return "in_path", "binary on PATH; no project config dir"
    if "config_dir" in kinds:
        return "configurable", "project config dir exists — presence is not readiness"
    return "not_found", "no evidence"


def _assets_written(target: Path, host: str, scope: str) -> list[str]:
    """Host asset dirs that exist at the install target (observed, not assumed)."""
    written: list[str] = []
    for rel in _host_dirs(host, scope):
        path = Path(os.path.expanduser(rel)) if rel.startswith("~") else target / rel
        try:
            if path.is_dir():
                written.append(rel)
        except OSError:
            continue
    return sorted(written)


def build_onboarding(
    target: Path,
    *,
    hosts: tuple[str, ...],
    scope: str,
    dry_run: bool,
    applied: bool,
    mcp_check: dict[str, Any] | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """The ``forge/HostOnboarding/v1`` block appended to setup receipts.

    ``hosts`` = the resolved host selection (``()`` for ``--host none``);
    ``applied`` = writes actually executed this run; ``mcp_check`` = the
    real handshake result when it ran.
    """
    detection = host_detect.detect_hosts(project_root=target if target.is_dir() else None, env=env)
    mcp_passed = mcp_check is not None and mcp_check.get("status") == "PASS"
    rows: list[dict[str, Any]] = []
    for host in host_detect.KNOWN_HOSTS:
        state, detail = _base_state(host, detection)
        detected = detection.for_host(host)
        evidence = [
            {"kind": e.kind, "detail": e.detail}
            for e in (detected.evidence if detected is not None else ())
        ]
        if applied and host in hosts:
            written = _assets_written(target, host, scope)
            if written:
                installed = state in ("installed", "in_path")
                state = "restart_needed" if installed else "integration_written"
                detail = (
                    "host assets written: "
                    + ", ".join(written[:4])
                    + (" — restart the host to load them" if installed else "")
                )
                if mcp_passed:
                    state = "mcp_verified"
                    detail += "; MCP handshake verified"
            else:
                detail = "selected, but no host assets were written"
        rows.append({"host": host, "state": state, "detail": detail, "evidence": evidence})

    limitations = [
        "configured != active: assets load when the host opens the workspace",
        "'validated' requires an observed running host — see `theforge hosts observe`",
        "MCP verification covers The Forge's own server only; specialist "
        "servers are verified by their own installers",
    ]
    if dry_run:
        limitations.append("plan only — no integration was written")
    out: dict[str, Any] = {
        "schema": ONBOARDING_SCHEMA,
        "hosts": rows,
        "next_steps": list(_NEXT_STEPS),
        "limitations": limitations,
    }
    if mcp_check is not None:
        out["mcp"] = mcp_check
    return out


__all__ = ["HOST_STATES", "ONBOARDING_SCHEMA", "build_onboarding"]
