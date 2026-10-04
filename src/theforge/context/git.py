"""GitReader: branch, HEAD and changed files without writing to the repo or running its code.

Hardening (requirements 3.2, 3.3):
- environment: ``security.env.safe_env()`` (allowlist, no credentials, no inherited ``GIT_*``)
  plus ``GIT_OPTIONAL_LOCKS=0`` (no opportunistic index refresh, no ``index.lock``),
  ``GIT_TERMINAL_PROMPT=0``, ``GIT_PAGER=cat`` and ``LC_ALL=C``; no transport at all
  (``GIT_NO_LAZY_FETCH=1`` and ``GIT_ALLOW_PROTOCOL=none``, which overrides any repository
  ``protocol.*.allow``): a partial-clone repository could otherwise make ``status`` lazy-fetch
  through a repository-configured remote (``ext::`` command, ``core.sshCommand``…);
- every call runs as ``git -c core.fsmonitor=false …``;
- ``status`` is skipped when the local/worktree config defines a key that makes ``status`` run
  a program (fsmonitor, clean/smudge/process filters), or when git cannot report config
  scopes (< 2.26);
- ``safe.directory`` is never touched: a repository git refuses becomes a limitation;
- spawn through ``protocol.proctree`` with a single total budget and whole-tree kill.

Every failure becomes a limitation; ``read_git_state`` never raises (3.4).
"""

import contextlib
import os
import shutil
import subprocess
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO

from theforge.context.scan import MAX_FILES
from theforge.contracts import GitSummary
from theforge.protocol import proctree
from theforge.security.env import safe_env
from theforge.security.redact import redact_text

__all__ = [
    "EXECUTABLE_CONFIG_KEYS", "GIT_TIMEOUT_S", "GitRun", "GitRunner", "GitState", "git_env",
    "read_git_state", "run_git",
]

GIT_TIMEOUT_S = 5.0
EXECUTABLE_CONFIG_KEYS: tuple[str, ...] = (
    "core.fsmonitor", "filter.*.clean", "filter.*.smudge", "filter.*.process",
)
MAX_GIT_STDOUT = 64 * 1024  # rev-parse / symbolic-ref / config
MAX_STATUS_STDOUT = 8 * 1024 * 1024  # status: enough for MAX_FILES paths, then truncated
_STDERR_KEEP = 8 * 1024
_STDERR_TAIL_CHARS = 2000
_CHUNK = 65536
_GRACE_SECONDS = 2.0
_JOIN_SECONDS = 5.0
_REFUSING_SCOPES = frozenset({"local", "worktree"})
_FILTER_DRIVERS = frozenset({"clean", "smudge", "process"})
_STATE_MARKERS: tuple[tuple[str, str], ...] = (
    ("MERGE_HEAD", "merge"),
    ("rebase-merge", "rebase"),
    ("rebase-apply", "rebase"),
    ("CHERRY_PICK_HEAD", "cherry_pick"),
    ("BISECT_LOG", "bisect"),
)
_HARDENING = ("-c", "core.fsmonitor=false")


@dataclass(frozen=True, kw_only=True)
class GitRun:
    returncode: int
    stdout: bytes
    stderr_tail: str
    timed_out: bool
    truncated: bool = False  # stdout hit the cap: the tree was killed, stdout is partial


GitRunner = Callable[[Sequence[str], Path, float], GitRun]


@dataclass(frozen=True, kw_only=True)
class GitState:
    summary: GitSummary
    changed: frozenset[str]  # POSIX paths relative to the workspace root
    limitations: tuple[str, ...]


def git_env() -> dict[str, str]:
    env = safe_env()
    env.update({
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_PAGER": "cat",
        "LC_ALL": "C",
        "GIT_NO_LAZY_FETCH": "1",  # git >= 2.44: never fetch missing objects on demand
        "GIT_ALLOW_PROTOCOL": "none",  # any git: deny every transport (no remote helper runs)
    })
    return env


# --- default runner (protocol.proctree) -----------------------------------------------------

def run_git(
    argv: Sequence[str], cwd: Path, timeout: float, *, max_stdout: int = MAX_STATUS_STDOUT,
) -> GitRun:
    """Run ``argv`` with the hardened env; kill the whole tree on timeout or oversize.

    Raises ``OSError`` only when the process cannot be started.
    """
    sp = proctree.spawn(argv, cwd=cwd, env=git_env())
    proc = sp.proc
    out = bytearray()
    err = bytearray()
    oversize = threading.Event()
    threads: list[threading.Thread] = []
    timed_out = False
    try:
        if proc.stdin is not None:
            with contextlib.suppress(OSError):
                proc.stdin.close()
        if proc.stdout is None or proc.stderr is None:
            raise OSError("git pipes unavailable")

        def pump_out(stream: IO[bytes]) -> None:
            with _owned(stream):
                while chunk := _read_chunk(stream):
                    room = max_stdout - len(out)
                    if len(chunk) > room:
                        out.extend(chunk[:room])
                        oversize.set()  # stop reading; the main thread kills the tree
                        return
                    out.extend(chunk)

        def pump_err(stream: IO[bytes]) -> None:
            with _owned(stream):
                while chunk := _read_chunk(stream):
                    err.extend(chunk)
                    if len(err) > _STDERR_KEEP:
                        del err[: len(err) - _STDERR_KEEP]

        threads = [
            threading.Thread(target=pump_out, args=(proc.stdout,), daemon=True),
            threading.Thread(target=pump_err, args=(proc.stderr,), daemon=True),
        ]
        for thread in threads:
            thread.start()
        deadline = time.monotonic() + max(timeout, 0.0)
        while not oversize.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                break
            if _wait_slice(proc, min(remaining, 0.05)):
                break
    finally:
        # Every exit path: end the whole tree (git may spawn helpers) and release the job.
        proctree.kill_tree(sp, grace_seconds=_GRACE_SECONDS)
        proctree.close(sp)
        deadline = time.monotonic() + _JOIN_SECONDS
        for thread in threads:
            thread.join(timeout=max(deadline - time.monotonic(), 0.0))
    stderr = redact_text(bytes(err).decode("utf-8", "replace")).strip()[-_STDERR_TAIL_CHARS:]
    returncode = proc.returncode if proc.returncode is not None else -1
    return GitRun(returncode=returncode, stdout=bytes(out), stderr_tail=stderr,
                  timed_out=timed_out, truncated=oversize.is_set())


def _wait_slice(proc: subprocess.Popen[bytes], seconds: float) -> bool:
    try:
        proc.wait(timeout=seconds)
    except subprocess.TimeoutExpired:
        return False
    return True


def _read_chunk(stream: IO[bytes]) -> bytes:
    try:
        return os.read(stream.fileno(), _CHUNK)
    except (OSError, ValueError):
        return b""


@contextlib.contextmanager
def _owned(stream: IO[bytes]) -> Iterator[None]:
    try:
        yield
    finally:
        with contextlib.suppress(OSError):
            stream.close()


def _default_runner(argv: Sequence[str], cwd: Path, timeout: float) -> GitRun:
    cap = MAX_STATUS_STDOUT if "status" in argv[3:4] else MAX_GIT_STDOUT
    return run_git(argv, cwd, timeout, max_stdout=cap)


# --- query ----------------------------------------------------------------------------------

class _Stop(Exception):
    """Ends the query with a limitation (internal control flow)."""

    def __init__(self, limitation: str) -> None:
        super().__init__(limitation)
        self.limitation = limitation


class _Session:
    def __init__(self, exe: str, root: Path, runner: GitRunner, timeout_s: float) -> None:
        self.exe = exe
        self.root = root
        self.runner = runner
        self.timeout_s = timeout_s
        self.deadline = time.monotonic() + timeout_s

    def timeout_limitation(self) -> str:
        return f"git: timed out after {self.timeout_s:g}s"

    def run(self, *args: str) -> GitRun:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise _Stop(self.timeout_limitation())
        result = self.runner([self.exe, *_HARDENING, *args], self.root, remaining)
        if result.timed_out:
            raise _Stop(self.timeout_limitation())
        return result


def read_git_state(
    root: Path, *, executable: str | None = None, runner: GitRunner | None = None,
    timeout_s: float = GIT_TIMEOUT_S,
) -> GitState:
    try:
        exe = executable if executable is not None else shutil.which("git")
        if exe is None:
            return _unavailable("git: not available")
        session = _Session(exe, root, runner or _default_runner, timeout_s)
        return _query(session)
    except _Stop as stop:
        return _unavailable(stop.limitation)
    except OSError:
        return _unavailable("git: not available")
    except Exception as exc:  # 3.4: never raise; any failure is a limitation
        return _unavailable(f"git: failed ({type(exc).__name__})")


def _unavailable(limitation: str) -> GitState:
    return GitState(summary=GitSummary(available=False), changed=frozenset(),
                    limitations=(limitation,))


def _query(s: _Session) -> GitState:
    toplevel, git_dir = _locate(s)
    limitations: list[str] = []
    branch: str | None = None
    head: str | None = None
    states: list[str] = []
    dirty: bool | None = None
    changed: frozenset[str] = frozenset()
    try:
        ref = s.run("symbolic-ref", "-q", "--short", "HEAD")
        if ref.returncode == 0:
            branch = _decode(ref.stdout).strip() or None
        verify = s.run("rev-parse", "--verify", "-q", "HEAD")
        if verify.returncode == 0:
            head = _decode(verify.stdout).strip() or None
        else:
            states.append("no_commits")
        states.extend(_repo_states(git_dir))
        refusal = _config_refusal(s)
        if refusal is not None:
            limitations.append(refusal)
        else:
            dirty, changed, extra = _status(s, toplevel)
            limitations.extend(extra)
    except _Stop as stop:
        limitations.append(stop.limitation)
    summary = GitSummary(
        available=True, branch=branch, head=head,
        detached=branch is None and head is not None,
        dirty=dirty, changed_files=None if dirty is None else len(changed),
        state=states,
    )
    return GitState(summary=summary, changed=changed, limitations=tuple(limitations))


def _locate(s: _Session) -> tuple[Path, Path]:
    run = s.run("rev-parse", "--show-toplevel", "--absolute-git-dir")
    if run.returncode != 0:
        raise _Stop(_classify_failure(run, "rev-parse"))
    lines = _decode(run.stdout).splitlines()
    if len(lines) < 2 or not lines[0] or not lines[1]:
        raise _Stop("git: rev-parse failed (unexpected output)")
    return Path(lines[0]), Path(lines[1])


def _classify_failure(run: GitRun, what: str) -> str:
    stderr = run.stderr_tail.lower()
    if "dubious ownership" in stderr:
        return "git: repository not trusted by git (safe.directory)"
    if "not a git repository" in stderr:
        return "git: not a repository"
    if "must be run in a work tree" in stderr:
        return "git: not a work tree"
    return f"git: {what} failed (exit {run.returncode})"


def _repo_states(git_dir: Path) -> list[str]:
    found: list[str] = []
    for name, state in _STATE_MARKERS:
        if os.path.lexists(git_dir / name) and state not in found:
            found.append(state)
    return found


def _config_refusal(s: _Session) -> str | None:
    run = s.run("config", "--list", "--show-scope", "--includes", "-z")
    if run.returncode != 0:
        stderr = run.stderr_tail.lower()
        if "show-scope" in stderr or "unknown option" in stderr:
            return "git: version too old for safe status"
        return f"git: status skipped: cannot inspect repository config (exit {run.returncode})"
    if run.truncated or len(run.stdout) >= MAX_GIT_STDOUT:
        return "git: status skipped: repository config too large to inspect"
    tokens = run.stdout.split(b"\x00")
    for i in range(0, len(tokens) - 1, 2):
        scope = _decode(tokens[i])
        key = _decode(tokens[i + 1]).split("\n", 1)[0]
        if scope in _REFUSING_SCOPES and _is_executable_key(key):
            return f"git: status skipped: repository config defines {key}"
    return None


def _is_executable_key(key: str) -> bool:
    lowered = key.lower()
    if lowered == "core.fsmonitor":
        return True
    section, _, rest = lowered.partition(".")
    if section != "filter" or "." not in rest:
        return False
    return rest.rsplit(".", 1)[1] in _FILTER_DRIVERS


def _status(s: _Session, toplevel: Path) -> tuple[bool | None, frozenset[str], list[str]]:
    run = s.run("status", "--porcelain=v1", "-z", "--untracked-files=all",
                "--ignore-submodules=all", "--no-renames")
    limitations: list[str] = []
    if run.truncated:
        limitations.append("git: changed files truncated (status output too large)")
        data = run.stdout[: run.stdout.rfind(b"\x00") + 1]
    elif run.returncode != 0:
        return None, frozenset(), [_classify_failure(run, "status")]
    else:
        data = run.stdout
    prefix = _root_prefix(s.root, toplevel)
    entries = 0
    changed: set[str] = set()
    for entry in data.split(b"\x00"):
        if len(entry) < 4 or entry[2:3] != b" ":
            continue
        entries += 1
        path = _decode(entry[3:])
        if path.endswith("/"):  # nested repository / directory entry: not a file
            continue
        rel = _relative_to_root(path, prefix)
        if rel is None:
            continue
        if len(changed) >= MAX_FILES:
            limitations.append(f"git: changed files truncated at {MAX_FILES}")
            break
        changed.add(rel)
    return entries > 0, frozenset(changed), limitations


def _root_prefix(root: Path, toplevel: Path) -> tuple[str, ...] | None:
    """Parts of the workspace root below the toplevel; None if the root is not inside it."""
    root_parts = root.resolve().parts
    top_parts = toplevel.resolve().parts
    norm = os.path.normcase
    if len(root_parts) < len(top_parts) or any(
            norm(a) != norm(b) for a, b in zip(root_parts, top_parts, strict=False)):
        return None
    return root_parts[len(top_parts):]


def _relative_to_root(path: str, prefix: tuple[str, ...] | None) -> str | None:
    if prefix is None:
        return None
    parts = path.split("/")
    if len(parts) <= len(prefix):
        return None
    norm = os.path.normcase
    if any(norm(a) != norm(b) for a, b in zip(parts, prefix, strict=False)):
        return None
    return "/".join(parts[len(prefix):])


def _decode(raw: bytes) -> str:
    return raw.decode("utf-8", "surrogateescape")
