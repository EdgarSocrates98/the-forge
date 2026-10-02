"""ProcTree: isolated spawn and whole-tree kill (requirement 2.5)."""

import contextlib
import os
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

from theforge.protocol.proctree import SpawnedProcess, close, kill_tree, spawn

# A provider stand-in that starts a long-sleeping grandchild, reports its PID and sleeps.
_TREE_PROVIDER = textwrap.dedent(
    """
    import subprocess, sys, time
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    print(child.pid, flush=True)
    time.sleep(60)
    """
)


def _pid_alive(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        kernel32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_uint32()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _wait_gone(pid: int, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            return True
        time.sleep(0.05)
    return not _pid_alive(pid)


def _readline(sp: SpawnedProcess, timeout: float = 30.0) -> bytes:
    assert sp.proc.stdout is not None
    stdout = sp.proc.stdout
    out: list[bytes] = []
    reader = threading.Thread(target=lambda: out.append(stdout.readline()), daemon=True)
    reader.start()
    reader.join(timeout)
    assert out, "provider did not report its grandchild PID in time"
    return out[0]


def _force_kill(pid: int) -> None:
    with contextlib.suppress(OSError):
        os.kill(pid, 9 if sys.platform != "win32" else 1)


def _close_pipes(sp: SpawnedProcess) -> None:
    for stream in (sp.proc.stdin, sp.proc.stdout, sp.proc.stderr):
        if stream is not None:
            with contextlib.suppress(OSError):
                stream.close()


def test_kill_tree_terminates_grandchild(tmp_path: Path) -> None:
    script = tmp_path / "tree_provider.py"
    script.write_text(_TREE_PROVIDER, encoding="utf-8")
    sp = spawn([sys.executable, str(script)], cwd=tmp_path, env=dict(os.environ))
    grandchild = 0
    try:
        assert sp.tree_kill_supported is True
        grandchild = int(_readline(sp).strip())
        assert _pid_alive(grandchild)
        kill_tree(sp, grace_seconds=1.0)
        assert sp.proc.poll() is not None
        assert _wait_gone(grandchild), f"grandchild {grandchild} survived kill_tree"
    finally:
        kill_tree(sp, grace_seconds=0.5)
        close(sp)
        _close_pipes(sp)
        if grandchild and _pid_alive(grandchild):
            _force_kill(grandchild)


def test_kill_tree_is_idempotent_on_exited_process(tmp_path: Path) -> None:
    sp = spawn([sys.executable, "-c", "pass"], cwd=tmp_path, env=dict(os.environ))
    try:
        sp.proc.communicate(timeout=30)
        assert sp.proc.returncode == 0
        kill_tree(sp)
        kill_tree(sp)
        assert sp.proc.returncode == 0
    finally:
        close(sp)
        close(sp)


def test_spawn_passes_cwd_env_and_pipes(tmp_path: Path) -> None:
    code = (
        "import os, sys; data = sys.stdin.read(); "
        "print(os.getcwd()); print(os.environ.get('THEFORGE_PT_MARK')); print(data)"
    )
    env = dict(os.environ, THEFORGE_PT_MARK="mark-123")
    sp = spawn([sys.executable, "-c", code], cwd=tmp_path, env=env)
    try:
        out, _ = sp.proc.communicate(b"hello", timeout=30)
    finally:
        kill_tree(sp, grace_seconds=0.5)
        close(sp)
    lines = out.decode().splitlines()
    assert Path(lines[0]).resolve() == tmp_path.resolve()
    assert lines[1] == "mark-123"
    assert lines[2] == "hello"


def test_spawn_does_not_inherit_unlisted_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("THEFORGE_PT_LEAK", "leak")
    env = {k: v for k, v in os.environ.items() if k != "THEFORGE_PT_LEAK"}
    code = "import os; print(os.environ.get('THEFORGE_PT_LEAK'))"
    sp = spawn([sys.executable, "-c", code], cwd=tmp_path, env=env)
    try:
        out, _ = sp.proc.communicate(timeout=30)
    finally:
        close(sp)
    assert out.decode().strip() == "None"
