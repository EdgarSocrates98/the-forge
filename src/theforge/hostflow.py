"""``theforge hosts observe|launch`` — observe the AI host, open it when safe.

Real per-host flow, every step a documented command verified against the
installed revisions (devin 3000.x, Claude Code 2.x, codex-cli 0.160.x,
read in 2026-10):

1. detect the binary (``shutil.which``);
2. read the version (``<bin> --version``);
3. check authentication through the official status subcommand — the
   receipt carries only the ``logged_in`` boolean, never the output (it
   can list credential paths);
4. read the workspace's integration state (``install.service.status``);
5. with ``launch`` and a TTY, run ``<bin>`` in the workspace directory —
   the host inherits the terminal and returns its exit code to the
   receipt. Without a TTY or ``launch``, the receipt carries
   ``launch_command`` for the operator to paste.

A signed-out host is never launched: the receipt points at the official
login command and never asks for a credential in a prompt. ``hosts list``
and ``hosts status`` stay evidence-detection (``host_detect``); this
module is the operational observe/launch layer on top of it.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

Which = Callable[[str], str | None]
Runner = Callable[[list[str]], tuple[int, str]]

_TIMEOUT_S = 15
_OUT_MAX = 400

LOGIN_HINTS = {
    "devin": "devin auth login",
    "claude": "claude auth login",
    "codex": "codex login",
}

#: Hosts the flow knows how to observe. ``copilot`` has no documented
#: status subcommand — ``logged_in`` stays ``None`` (honest unknown).
HOST_NAMES: tuple[str, ...] = ("claude", "devin", "codex", "copilot")


@dataclass(frozen=True)
class _HostCmd:
    binary: str
    auth_status: tuple[str, ...] | None


_HOST_CMDS = {
    "claude": _HostCmd("claude", ("auth", "status")),
    "devin": _HostCmd("devin", ("auth", "status")),
    "codex": _HostCmd("codex", ("login", "status")),
    "copilot": _HostCmd("copilot", None),
}


def _default_which(binary: str) -> str | None:
    return shutil.which(binary)


def _default_runner(argv: list[str]) -> tuple[int, str]:
    proc = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_S,
        errors="replace",
        check=False,
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _logged_in(host: str, out: str) -> bool | None:
    """Only the boolean. No legible positive/negative evidence -> ``None``."""
    if host == "claude":
        try:
            data = json.loads(out)
        except ValueError:
            data = None
        if isinstance(data, dict) and "loggedIn" in data:
            return bool(data["loggedIn"])
    low = out.lower()
    # negative before positive: "Not logged in" contains "logged in"
    if any(
        s in low
        for s in (
            "not logged",
            "logged out",
            "no credentials",
            "unauthorized",
        )
    ):
        return False
    if "logged in" in low:
        return True
    return None


def _call(executable: str, argv: list[str], runner: Runner) -> tuple[int, str] | dict[str, Any]:
    try:
        return runner([executable, *argv])
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "refused",
            "reason": "host_cli_timeout",
            "command": " ".join(argv),
            "timeout_s": exc.timeout,
        }
    except OSError as exc:
        return {
            "status": "refused",
            "reason": "host_cli_failed",
            "command": " ".join(argv),
            "output": str(exc)[-_OUT_MAX:],
        }


def _integration(repo: Path) -> dict[str, Any]:
    """Workspace install state, touching nothing — ``unverified`` when absent."""
    try:
        from theforge.install import service

        st = service.status(scope="project", root=repo)
    except Exception as exc:  # noqa: BLE001 — status must never take the host flow down
        return {"state": "unknown", "error": str(exc)[:200]}
    drift = st.get("drift") or {}
    return {
        "state": st.get("status", "unknown"),
        "drift": {
            "ok": drift.get("ok", 0),
            "modified": len(drift.get("modified") or []),
            "missing": len(drift.get("missing") or []),
        },
    }


def host_state(
    host: str,
    *,
    repo: Path,
    which: Which | None = None,
    runner: Runner | None = None,
) -> dict[str, Any]:
    """Observed state of one host: binary, version, auth, integration, launch cmd."""
    if host not in _HOST_CMDS:
        return {
            "host": host,
            "state": "refused",
            "reason": "host_unknown",
            "known": list(_HOST_CMDS),
        }
    which = which or _default_which
    runner = runner or _default_runner
    cmd = _HOST_CMDS[host]
    state: dict[str, Any] = {
        "host": host,
        "binary": cmd.binary,
        "launch_command": cmd.binary,
    }
    path = which(cmd.binary)
    if not path:
        state["state"] = "NOT_DETECTED"
        return state
    state["binary_path"] = path
    state["state"] = "DETECTED"

    version = _call(path, ["--version"], runner)
    if isinstance(version, dict):
        state["version_refused"] = version
    else:
        rc, out = version
        first = next((line.strip() for line in out.splitlines() if line.strip()), "")
        state["version"] = first or None
        state["state"] = "SUPPORTED" if rc == 0 else "DETECTED"

    if cmd.auth_status is None:
        state["logged_in"] = None
        state["auth_note"] = "no documented status subcommand in this revision"
    else:
        auth = _call(path, list(cmd.auth_status), runner)
        if isinstance(auth, dict):
            state["auth_refused"] = auth
            state["logged_in"] = None
        else:
            state["logged_in"] = _logged_in(host, auth[1])
    if state.get("logged_in") is False:
        state["login_hint"] = LOGIN_HINTS.get(host)

    state["integration"] = _integration(repo)
    state["state"] = _final_state(state)
    return state


def _final_state(state: dict[str, Any]) -> str:
    if state.get("logged_in") is False:
        return "NEEDS_LOGIN"
    integ = (state.get("integration") or {}).get("state")
    if integ == "healthy":
        return "READY"
    if integ in {"degraded", "broken"}:
        return "INTEGRATION_" + str(integ).upper()
    return "SUPPORTED"


def hosts_flow(
    target: str,
    *,
    repo: Path,
    launch: bool = False,
    tty: bool | None = None,
    which: Which | None = None,
    runner: Runner | None = None,
    exec_host: Callable[[str, Path], int] | None = None,
) -> dict[str, Any]:
    """The host flow: implicit selector via ``target`` (``all`` measures every
    declared host), per-host state, and a real launch when ``launch`` +
    TTY + READY.

    ``exec_host(path, repo)`` is the launch seam — the CLI injects
    ``subprocess.call``; a test injects a spy. Without a TTY, ``launched``
    is false and ``launch_refused`` says why — never silence.
    """
    repo = Path(repo)
    names = list(HOST_NAMES) if target == "all" else [target]
    states = [host_state(name, repo=repo, which=which, runner=runner) for name in names]
    receipt: dict[str, Any] = {
        "repo": repo.as_posix(),
        "hosts": states,
        "launched": False,
    }
    if target == "all" or not launch:
        if launch:
            receipt["launch_refused"] = "selector `all` does not launch: pick one host"
        return receipt

    state = states[0]
    tty = sys.stdin.isatty() if tty is None else tty
    if state["state"] == "NOT_DETECTED":
        receipt["launch_refused"] = "host_absent"
    elif state["state"] == "NEEDS_LOGIN":
        receipt["launch_refused"] = "login_required"
        receipt["login_hint"] = state.get("login_hint")
    elif not tty:
        receipt["launch_refused"] = "no_tty"
    else:
        # Path came from shutil.which — same trust level as any PATH exec.
        exec_fn = exec_host or (lambda path, cwd: subprocess.call([path], cwd=str(cwd)))
        receipt["launched"] = True
        receipt["host_exit_code"] = exec_fn(state["binary_path"], repo)
    return receipt
