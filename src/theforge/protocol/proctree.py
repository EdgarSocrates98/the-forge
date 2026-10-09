"""Isolated provider spawn and whole-tree termination (stdlib only).

POSIX: the provider leads a new session (``start_new_session=True``) and ``kill_tree`` signals
the whole process group: SIGTERM, a grace period, then SIGKILL.

Windows: the provider starts suspended, is assigned to a Job Object configured with
``JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`` (no breakaway allowed) and only then resumed, so even
launchers that immediately spawn the real interpreter cannot leave the job. ``kill_tree`` uses
``TerminateJobObject`` (``taskkill /T /F`` if that call fails). If the job cannot be created or
assigned, the process is resumed anyway and ``taskkill /T /F`` is the fallback;
``tree_kill_supported`` is then False (orphans whose parent already exited can escape it:
documented limitation).

Known limitation (POSIX): a descendant that deliberately leaves the group (new ``setsid``,
daemonization) is not reached.
"""

import contextlib
import os
import subprocess
import sys
import threading
import time
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO

__all__ = [
    "SpawnedProcess",
    "close",
    "join_threads",
    "kill_tree",
    "owned",
    "read_chunk",
    "spawn",
    "wait_slice",
]

_REAP_SECONDS = 5.0
_CHUNK = 1 << 16


@dataclass
class SpawnedProcess:
    proc: subprocess.Popen[bytes]
    tree_kill_supported: bool  # False -> recorded limitation (fallback kill only)
    job_handle: int | None = field(default=None, repr=False)  # Windows Job Object handle


def _reap(proc: subprocess.Popen[bytes], timeout: float) -> None:
    with contextlib.suppress(subprocess.TimeoutExpired):
        proc.wait(timeout=timeout)


# --- shared pipe helpers (single owner; used by transport.py and context/git.py) --------


def read_chunk(stream: IO[bytes]) -> bytes:
    """Return whatever is available (up to a chunk) without waiting for a full chunk."""
    try:
        return os.read(stream.fileno(), _CHUNK)
    except (OSError, ValueError):
        return b""


@contextlib.contextmanager
def owned(stream: IO[bytes]) -> Iterator[None]:
    """Close ``stream`` when the owning pump thread is done with it."""
    try:
        yield
    finally:
        with contextlib.suppress(OSError):
            stream.close()


def wait_slice(proc: subprocess.Popen[bytes], seconds: float) -> bool:
    """Wait up to ``seconds`` for the process root; True when it has exited."""
    try:
        proc.wait(timeout=seconds)
    except subprocess.TimeoutExpired:
        return False
    return True


def join_threads(threads: Iterable[threading.Thread], join_seconds: float) -> None:
    """Join all pump threads within one shared bound (never longer than ``join_seconds``)."""
    deadline = time.monotonic() + join_seconds
    for thread in threads:
        thread.join(timeout=max(deadline - time.monotonic(), 0.0))


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _CREATE_SUSPENDED = 0x00000004
    _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS = 9
    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
    _PROCESS_TERMINATE = 0x0001
    _PROCESS_SET_QUOTA = 0x0100
    _PROCESS_SUSPEND_RESUME = 0x0800

    class _BasicLimit(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _IoCounters(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_uint64),
            ("WriteOperationCount", ctypes.c_uint64),
            ("OtherOperationCount", ctypes.c_uint64),
            ("ReadTransferCount", ctypes.c_uint64),
            ("WriteTransferCount", ctypes.c_uint64),
            ("OtherTransferCount", ctypes.c_uint64),
        ]

    class _ExtendedLimit(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _BasicLimit),
            ("IoInfo", _IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _ntdll = ctypes.WinDLL("ntdll")

    _kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    _kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    _kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    _kernel32.SetInformationJobObject.restype = wintypes.BOOL
    _kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    _kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    _kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    _kernel32.TerminateJobObject.restype = wintypes.BOOL
    _kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL
    _ntdll.NtResumeProcess.argtypes = [wintypes.HANDLE]
    _ntdll.NtResumeProcess.restype = ctypes.c_long

    def _create_job() -> int | None:
        job: int | None = _kernel32.CreateJobObjectW(None, None)
        if not job:
            return None
        info = _ExtendedLimit()
        info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        ok = _kernel32.SetInformationJobObject(
            job,
            _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS,
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        if not ok:
            _kernel32.CloseHandle(job)
            return None
        return job

    def _open_process(pid: int) -> int | None:
        access = _PROCESS_TERMINATE | _PROCESS_SET_QUOTA | _PROCESS_SUSPEND_RESUME
        handle: int | None = _kernel32.OpenProcess(access, False, pid)
        return handle or None

    def _resume(handle: int) -> bool:
        status: int = _ntdll.NtResumeProcess(handle)
        return status >= 0  # NT_SUCCESS

    def spawn(argv: Sequence[str], *, cwd: Path, env: Mapping[str, str]) -> SpawnedProcess:
        job = _create_job()
        try:
            proc = subprocess.Popen(
                list(argv),
                cwd=cwd,
                env=dict(env),
                shell=False,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=_CREATE_SUSPENDED,
            )
        except BaseException:
            if job:
                _kernel32.CloseHandle(job)
            raise
        handle = _open_process(proc.pid)
        if handle is None:
            error = ctypes.get_last_error()  # capture before other calls overwrite it
            # Cannot resume a suspended process we cannot open: do not leave it hanging.
            proc.kill()
            _reap(proc, _REAP_SECONDS)
            if job:
                _kernel32.CloseHandle(job)
            raise OSError(error, "cannot open spawned provider process")
        try:
            assigned = bool(job) and bool(_kernel32.AssignProcessToJobObject(job, handle))
            if not assigned and job:
                _kernel32.CloseHandle(job)
                job = None
            if not _resume(handle):
                proc.kill()
                _reap(proc, _REAP_SECONDS)
                if job:
                    _kernel32.CloseHandle(job)
                raise OSError("cannot resume spawned provider process")
        finally:
            _kernel32.CloseHandle(handle)
        return SpawnedProcess(proc=proc, tree_kill_supported=job is not None, job_handle=job)

    def kill_tree(sp: SpawnedProcess, *, grace_seconds: float = 2.0) -> None:
        proc = sp.proc
        terminated = sp.job_handle is not None and bool(
            _kernel32.TerminateJobObject(sp.job_handle, 1)
        )
        if not terminated and proc.poll() is None:
            # Fallback: recursive kill by PID while the root still exists (PID not reusable).
            with contextlib.suppress(OSError, subprocess.SubprocessError):
                subprocess.run(
                    ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=max(grace_seconds, 1.0) + 5.0,
                    check=False,
                )
        _reap(proc, max(grace_seconds, 0.0))
        if proc.poll() is None:
            with contextlib.suppress(OSError):
                proc.kill()
            _reap(proc, _REAP_SECONDS)

    def close(sp: SpawnedProcess) -> None:
        job, sp.job_handle = sp.job_handle, None
        if job is not None:
            _kernel32.CloseHandle(job)  # KILL_ON_JOB_CLOSE ends anything still in the job

else:
    import os
    import signal

    def spawn(argv: Sequence[str], *, cwd: Path, env: Mapping[str, str]) -> SpawnedProcess:
        proc = subprocess.Popen(
            list(argv),
            cwd=cwd,
            env=dict(env),
            shell=False,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        return SpawnedProcess(proc=proc, tree_kill_supported=True)

    def _signal_group(pgid: int, sig: int) -> bool:
        """Send ``sig`` to the group; False when the group no longer exists."""
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True  # e.g. only zombies left on some platforms
        return True

    def kill_tree(sp: SpawnedProcess, *, grace_seconds: float = 2.0) -> None:
        proc = sp.proc
        pgid = proc.pid  # session leader: pgid == pid
        if _signal_group(pgid, signal.SIGTERM):
            deadline = time.monotonic() + max(grace_seconds, 0.0)
            while time.monotonic() < deadline:
                proc.poll()  # reap the leader so a zombie does not keep the group alive
                if not _signal_group(pgid, 0):
                    break
                time.sleep(0.05)
            _signal_group(pgid, signal.SIGKILL)
        _reap(proc, _REAP_SECONDS)

    def close(sp: SpawnedProcess) -> None:
        sp.job_handle = None
