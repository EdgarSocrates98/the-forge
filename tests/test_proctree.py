"""ProcTree: isolated spawn and whole-tree kill (requirement 2.5)."""

import contextlib
import os
import sys
import textwrap
import threading
from pathlib import Path

import pytest

from helpers import force_kill, pid_alive, wait_gone
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


def _readline(sp: SpawnedProcess, timeout: float = 30.0) -> bytes:
    assert sp.proc.stdout is not None
    stdout = sp.proc.stdout
    out: list[bytes] = []
    reader = threading.Thread(target=lambda: out.append(stdout.readline()), daemon=True)
    reader.start()
    reader.join(timeout)
    assert out, "provider did not report its grandchild PID in time"
    return out[0]


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
        assert pid_alive(grandchild)
        kill_tree(sp, grace_seconds=1.0)
        assert sp.proc.poll() is not None
        assert wait_gone(grandchild), f"grandchild {grandchild} survived kill_tree"
    finally:
        kill_tree(sp, grace_seconds=0.5)
        close(sp)
        _close_pipes(sp)
        if grandchild and pid_alive(grandchild):
            force_kill(grandchild)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Job Object fallback")
def test_kill_tree_falls_back_to_taskkill_when_job_termination_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from theforge.protocol import proctree

    class _FailingTerminate:
        def __init__(self, real: object) -> None:
            self._real = real

        def __getattr__(self, name: str) -> object:
            return getattr(self._real, name)

        @staticmethod
        def TerminateJobObject(handle: object, code: int) -> int:  # noqa: N802
            return 0

    script = tmp_path / "tree_provider.py"
    script.write_text(_TREE_PROVIDER, encoding="utf-8")
    sp = spawn([sys.executable, str(script)], cwd=tmp_path, env=dict(os.environ))
    grandchild = 0
    try:
        grandchild = int(_readline(sp).strip())
        with monkeypatch.context() as patch:
            patch.setattr(proctree, "_kernel32", _FailingTerminate(proctree._kernel32))
            kill_tree(sp, grace_seconds=1.0)
        assert sp.proc.poll() is not None
        assert wait_gone(grandchild), f"grandchild {grandchild} survived the taskkill fallback"
    finally:
        kill_tree(sp, grace_seconds=0.5)
        close(sp)
        _close_pipes(sp)
        if grandchild and pid_alive(grandchild):
            force_kill(grandchild)


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
