"""AdapterShell: the Forge Protocol v1 envelope and op dispatch shared by the adapters.

This file is copied byte for byte into every adapter package (a test enforces it): edit one
copy and copy it over. Stdlib-only, Python >= 3.10, and it never imports ``theforge``.

``serve`` reads the op from the last argument and the adapter options before it
(``--replay <dir>``, ``--assume-specialist-version <v>``), the request from stdin, and always
exits 0 with a response that echoes ``op`` and ``request_id`` and carries the adapter's
``producer``. Unknown op, unsupported protocol (outside ``describe``) and an undeclared
capability or action are ``refused``; an invalid request and any unexpected exception are a
structured ``error`` (the exception type only: never a traceback nor the message).

Execute helpers: ``stage_context`` copies to ``<cwd>/stage/`` only the ContextPack files that
are inside the workspace root and match their sha256 (anything else is a limitation);
``evidence_hash`` applies the common ``Evidence.hash`` rule; ``no_input`` answers an action whose
required input is absent without calling the specialist; ``finalize`` builds the
``ExecutionResult`` (schema, producer, UTC ``created_at``) and, above ``INLINE_LIMIT``, keeps
the findings that fit and spills the complete native output to the artifact
``native/full-output.json`` in the execute cwd (the result becomes ``partial``).

Native processes: ``run_native`` runs the specialist without a shell, in the given cwd, with
the environment received from the core plus the adapter's explicit adjustments (credential-
shaped names are always dropped), capped stdout/stderr and a timeout (``native_timeout``: 85%
of the profile's execute timeout). The whole process tree is killed when the run ends (Job
Object on Windows, process group on POSIX); an overrun raises ``NativeTimeout``, answered as
the structured error ``ADAPTER-NATIVE-TIMEOUT``.

Workdir cleanup: after the response of an ``execute`` is built, whatever its outcome (``ok``,
``partial``, ``refused``, ``error``, a timeout, an unexpected exception), ``respond`` reduces
the cwd to the result's ``artifacts[]`` paths with ``cleanup_workdir``: ``stage/`` and every
other file or directory the execute left there are removed. Links (symlinks, junctions) are
removed, never followed; artifact paths that are not contained relative POSIX paths keep
nothing. Entries that existed before the execute started are never touched (the core always
hands a fresh, empty work dir). A removal failure is the limitation
``workdir cleanup incomplete: <path>``, never an error; a declared artifact the cleanup had
to remove (behind a link) is ``workdir cleanup removed artifact: <path>`` and an ``ok``
result becomes ``partial``. ``describe`` and ``health`` are not
cleaned (the core removes their temporary cwd).
"""

from __future__ import annotations

import contextlib
import fnmatch
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import threading
from collections.abc import Callable, Collection, Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import IO, Any, BinaryIO

PROTOCOL = "forge/v1"
UNKNOWN_REQUEST_ID = "unknown"
OPTION_REPLAY = "--replay"
OPTION_ASSUME_VERSION = "--assume-specialist-version"

OP_UNSUPPORTED = "ADAPTER-OP-UNSUPPORTED"
PROTOCOL_UNSUPPORTED = "ADAPTER-PROTOCOL-UNSUPPORTED"
REQUEST_INVALID = "ADAPTER-REQUEST-INVALID"
CAPABILITY_UNSUPPORTED = "ADAPTER-CAPABILITY-UNSUPPORTED"
ACTION_UNSUPPORTED = "ADAPTER-ACTION-UNSUPPORTED"
INTERNAL = "ADAPTER-INTERNAL"
OUTPUT_TOO_LARGE = "ADAPTER-OUTPUT-TOO-LARGE"
NATIVE_TIMEOUT = "ADAPTER-NATIVE-TIMEOUT"

# The core's execute timeout per budget profile (task.budget_profile); a native call gets
# NATIVE_TIMEOUT_SHARE of it so the adapter still answers before the core gives up.
EXECUTE_TIMEOUTS = {"economy": 60.0, "balanced": 180.0, "max": 600.0}
NATIVE_TIMEOUT_SHARE = 0.85
# Bytes kept from a native process's stdout/stderr (the rest is read and discarded).
NATIVE_STDOUT_CAP = 64 * 1024 * 1024
NATIVE_STDERR_CAP = 1024 * 1024
_READ_CHUNK = 64 * 1024
_REAP_SECONDS = 5.0
# Credential-shaped names never reach a native process (same rules as the core's provider
# environment, applied again here to what the core sent and to the adapter's adjustments).
CREDENTIAL_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"^AWS_",
        r"(^|_)TOKEN(_|$)",
        r"SECRET",
        r"PASS(WORD|WD)",
        r"API_?KEY",
        r"ACCESS_?KEY",
        r"CREDENTIAL",
        r"^SSH_AUTH_SOCK$",
        r"^(AZURE|ARM|GH|CLOUDSDK|ACTIONS)_",
        r"^(KUBECONFIG|DOCKER_CONFIG|NETRC)$",
        r"_PROXY$",
    )
)
_URL_USERINFO = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^/?#\s@]+@")

# Serialized ExecutionResult bytes returned inline: half the core transport's 8 MiB stdout cap.
INLINE_LIMIT = 4 * 1024 * 1024
SPILL_PATH = "native/full-output.json"

RESULT_SCHEMA = "theforge/ExecutionResult/v1"
STAGE_DIR = "stage"
SKIP_NOT_FOUND = "file not found"
SKIP_OUTSIDE = "outside workspace root"
SKIP_SYMLINK = "symlink resolves outside workspace root"
SKIP_MISMATCH = "sha256 mismatch"
SKIP_LINE_RANGE = "line-range items not supported by this adapter"
SKIP_MALFORMED = "malformed context item"
SKIP_SIZE = "size mismatch"
# Read cap for an item without a valid declared ``bytes`` (the ContextPack always has one).
MAX_UNSIZED_BYTES = 64 * 1024 * 1024
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_DRIVE_RE = re.compile(r"^[A-Za-z]:")
_NATIVE_HASH_PREFIX = "sha256:"

CLEANUP_INCOMPLETE = "workdir cleanup incomplete: "
CLEANUP_REMOVED = "workdir cleanup removed artifact: "
# Failed removals reported one by one; the rest are counted in a single limitation.
CLEANUP_REPORT_LIMIT = 20
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400  # Windows: symlinks, junctions and other links


@dataclass(frozen=True)
class AdapterOptions:
    """Adapter flags given before the op."""

    replay: Path | None = None
    assume_specialist_version: str | None = None


@dataclass(frozen=True)
class Request:
    """A validated request envelope (``op`` equals the op given in argv)."""

    op: str
    request_id: str
    protocol: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class Reply:
    """What a handler answers; ``serve`` wraps it in the response envelope."""

    status: str
    payload: dict[str, Any] = field(default_factory=dict)
    error: dict[str, Any] | None = None
    limitations: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)


OpHandler = Callable[[Request, Path], Reply]
HandlerFactory = Callable[[AdapterOptions], OpHandler]


class _Invalid(Exception):
    """Invalid request or invocation: answered with ``ADAPTER-REQUEST-INVALID``."""

    def __init__(self, detail: str, field_name: str, request_id: str = UNKNOWN_REQUEST_ID):
        super().__init__(detail)
        self.detail = detail
        self.field_name = field_name
        self.request_id = request_id


def _error(code: str, detail: str, field_name: str | None, unlock: str | None) -> dict[str, Any]:
    return {"code": code, "detail": detail, "field": field_name, "unlock": unlock}


def refuse(code: str, detail: str, *, field: str | None = None, unlock: str | None = None) -> Reply:
    """A ``refused`` reply with a structured error."""
    return Reply(status="refused", error=_error(code, detail, field, unlock))


def fail(code: str, detail: str, *, field: str | None = None, unlock: str | None = None) -> Reply:
    """An ``error`` reply with a structured error."""
    return Reply(status="error", error=_error(code, detail, field, unlock))


@dataclass(frozen=True)
class StagedInput:
    """What ``stage_context`` copied: staged path -> verified sha256, and why items were skipped."""

    root: Path
    files: Mapping[str, str] = field(default_factory=dict)
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResultDraft:
    """An adapter result before ``finalize`` adds schema, producer and ``created_at``.

    Evidence without ``producer`` gets the adapter's. ``partial`` makes the result partial.
    """

    provider_id: str
    version: str
    findings: Sequence[Mapping[str, Any]] = ()
    evidence: Sequence[Mapping[str, Any]] = ()
    artifacts: Sequence[Mapping[str, Any]] = ()
    limitations: Sequence[str] = ()
    unknowns: Sequence[str] = ()
    partial: bool = False
    # The provider-native run receipt pointer ({ref, sha256}), when the
    # specialist wrote one the run can drill into. Never its contents.
    provider_receipt: Mapping[str, str] | None = None
    # The provider's internal economy summary (ProviderEconomyReceipt fields),
    # when it keeps its own accounting; per-metric status, never hidden zeros.
    provider_economy: Mapping[str, Any] | None = None
    # The native trace pointer ({ref, summary, critical_path}), when the
    # specialist records internal traces; expansion stays on-demand.
    native_trace: Mapping[str, Any] | None = None
    # The complete native output, written to the spill artifact when the result is above
    # INLINE_LIMIT: bytes as is, anything else as JSON; None spills the complete result.
    native_output: object = None


def _skipped(path: str, reason: str) -> str:
    return f"context file '{path}' skipped: {reason}"


def _skip_unsized() -> str:
    return f"no declared size and file exceeds {MAX_UNSIZED_BYTES} bytes"


def _lexically_contained(path: str) -> bool:
    """A non-empty relative POSIX path without traversal, drive letter or backslash."""
    if not path or "\x00" in path or "\\" in path or path.startswith("/"):
        return False
    if _DRIVE_RE.match(path):
        return False
    parts = path.split("/")
    return ".." not in parts and not all(part in ("", ".") for part in parts)


def _verify(item: object, root: Path | None) -> tuple[str, bytes | None, str | None]:
    """(path, verified bytes, None) or (path, None, skip reason) for one ContextPack item."""
    if not isinstance(item, Mapping) or not isinstance(item.get("path"), str):
        path = item.get("path") if isinstance(item, Mapping) else None
        return str(path), None, SKIP_MALFORMED
    path = item["path"]
    # The sha256 of a line-range item covers the range only: it is never compared with the
    # whole file, so it cannot be reported as a mismatch.
    if item.get("lines") is not None:
        return path, None, SKIP_LINE_RANGE
    if root is None or not _lexically_contained(path):
        return path, None, SKIP_OUTSIDE
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root):  # lexically contained: only a symlink escapes
        return path, None, SKIP_SYMLINK
    raw_size = item.get("bytes")
    declared = (
        raw_size
        if isinstance(raw_size, int) and not isinstance(raw_size, bool) and raw_size >= 0
        else None
    )
    sized = declared is not None
    # Never read more than the declared size (or MAX_UNSIZED_BYTES without one), plus one
    # byte to notice a file that grew between stat and read.
    limit: int = MAX_UNSIZED_BYTES if declared is None else declared
    try:
        if not resolved.is_file():
            return path, None, SKIP_NOT_FOUND
        size = resolved.stat().st_size
        if size > limit or (sized and size != declared):
            return path, None, (SKIP_SIZE if sized else _skip_unsized())
        with resolved.open("rb") as fh:
            data = fh.read(limit + 1)
    except OSError:
        return path, None, SKIP_NOT_FOUND
    if len(data) > limit or (sized and len(data) != declared):
        return path, None, (SKIP_SIZE if sized else _skip_unsized())
    if hashlib.sha256(data).hexdigest() != item.get("sha256"):
        return path, None, SKIP_MISMATCH
    return path, data, None


def stage_context(payload: Mapping[str, Any], cwd: Path) -> StagedInput:
    """Copy to ``<cwd>/stage/`` the ContextPack files inside the root with a matching sha256.

    The bytes written are the ones hashed (never re-read). Missing, outside the root, a
    symlink escaping it, a sha256 mismatch or a line-range item: not copied, a limitation.
    """
    stage = cwd / STAGE_DIR
    stage.mkdir(parents=True, exist_ok=True)
    stage_root = stage.resolve()
    if not stage_root.is_relative_to(cwd.resolve()):
        raise RuntimeError("stage directory escapes the working directory")
    context = payload.get("context")
    items = context.get("files") if isinstance(context, Mapping) else None
    if not isinstance(context, Mapping) or not isinstance(items, list):
        return StagedInput(root=stage)
    raw_root = context.get("root")
    root = (
        Path(raw_root).resolve()
        if isinstance(raw_root, str) and raw_root and Path(raw_root).is_absolute()
        else None
    )
    files: dict[str, str] = {}
    limitations: list[str] = []
    for item in items:
        path, data, reason = _verify(item, root)
        if reason is not None or data is None:
            limitations.append(_skipped(path, reason or SKIP_MALFORMED))
            continue
        if path in files:
            continue
        target = (stage / path).resolve()
        if not target.is_relative_to(stage_root):
            limitations.append(_skipped(path, SKIP_OUTSIDE))
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        files[path] = hashlib.sha256(data).hexdigest()
    return StagedInput(root=stage, files=files, limitations=tuple(limitations))


def evidence_hash(path: str | None, native_hash: object, stage: StagedInput) -> str | None:
    """The common ``Evidence.hash`` rule.

    The verified sha256 of the file staged at ``path`` when the native hash (optionally
    ``sha256:``-prefixed, lowercase hex) is equal to it; ``None`` when the native hash is
    missing, malformed or different, or when ``path`` was not staged.
    """
    verified = None if path is None else stage.files.get(path)
    if verified is None or not isinstance(native_hash, str):
        return None
    value = native_hash
    if value.startswith(_NATIVE_HASH_PREFIX):
        value = value[len(_NATIVE_HASH_PREFIX) :]
    if _SHA256_RE.fullmatch(value) is None or value != verified:
        return None
    return verified


def _matches(path: str, pattern: str) -> bool:
    return fnmatch.fnmatchcase(path, pattern) or fnmatch.fnmatchcase(
        PurePosixPath(path).name, pattern
    )


def select_inputs(
    stage: StagedInput, required: Mapping[str, Sequence[str]]
) -> dict[str, list[str]]:
    """Input name -> staged paths (sorted) matching any of its globs (path or file name)."""
    return {
        name: [path for path in sorted(stage.files) if any(_matches(path, glob) for glob in globs)]
        for name, globs in required.items()
    }


def no_input(
    stage: StagedInput, required: Mapping[str, Sequence[str]], *, provider_id: str, version: str
) -> ResultDraft | None:
    """A partial draft without findings when a required input has no staged file, else None.

    Decided before the specialist (or a replay recording) is consulted.
    """
    selected = select_inputs(stage, required)
    missing = [name for name in required if not selected[name]]
    if not missing:
        return None
    limitations = [
        *stage.limitations,
        *(f"no input: expected {', '.join(required[name])}" for name in missing),
    ]
    return ResultDraft(
        provider_id=provider_id,
        version=version,
        limitations=limitations,
        unknowns=[f"input:{name}" for name in missing],
        partial=True,
    )


def utc_now() -> str:
    """The current time as an ISO-8601 UTC timestamp (``Z`` suffix)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _dumps(value: object) -> bytes:
    """``value`` as the response serializes it (compact, sorted keys, UTF-8)."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def inline_size(payload: Mapping[str, Any]) -> int:
    """Bytes of a result payload once serialized in the response."""
    return len(_dumps(payload))


def _truncation(kept: int, total: int) -> str:
    return (
        f"output truncated: {kept} of {total} findings inline; "
        f"full native output in artifact {SPILL_PATH}"
    )


def _truncated(payload: Mapping[str, Any], kept: int, spill: Mapping[str, str]) -> dict[str, Any]:
    """``payload`` with its first ``kept`` findings, the evidence they reference (native
    order), the spill artifact, ``partial`` status and the truncation limitation."""
    findings = payload["findings"][:kept]
    referenced = {ref for finding in findings for ref in finding.get("evidence_ids") or ()}
    return {
        **payload,
        "status": "partial",
        "findings": findings,
        "evidence": [item for item in payload["evidence"] if item.get("id") in referenced],
        "artifacts": [*payload["artifacts"], dict(spill)],
        "limitations": [*payload["limitations"], _truncation(kept, len(payload["findings"]))],
    }


def _spill(result: ResultDraft, payload: Mapping[str, Any], cwd: Path) -> Reply:
    """Keep the most findings (native order) that fit in INLINE_LIMIT and write the complete
    native output to ``<cwd>/native/full-output.json``, declared as an artifact."""
    native = result.native_output
    data = (
        bytes(native)
        if isinstance(native, (bytes, bytearray))
        else _dumps(payload if native is None else native)
    )
    # The artifact entry has a fixed size (path and a 64-hex sha256), so the hash is
    # computed before deciding what fits and the file is written only once it does.
    spill = {"path": SPILL_PATH, "sha256": hashlib.sha256(data).hexdigest()}
    total = len(payload["findings"])
    if inline_size(_truncated(payload, 0, spill)) > INLINE_LIMIT:
        return fail(OUTPUT_TOO_LARGE, f"result exceeds {INLINE_LIMIT} bytes even without findings")
    low, high = 0, total  # the size grows with the findings kept: largest prefix that fits
    while low < high:
        middle = (low + high + 1) // 2
        if inline_size(_truncated(payload, middle, spill)) <= INLINE_LIMIT:
            low = middle
        else:
            high = middle - 1
    target = (cwd / SPILL_PATH).resolve()
    if not target.is_relative_to(cwd.resolve()):
        raise RuntimeError("spill path escapes the working directory")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    truncated = _truncated(payload, low, spill)
    return Reply(
        status="partial",
        payload=truncated,
        limitations=list(truncated["limitations"]),
        unknowns=list(truncated["unknowns"]),
    )


def finalize(result: ResultDraft, cwd: Path) -> Reply:
    """The ``ExecutionResult`` reply for ``result`` (schema, producer, UTC ``created_at``).

    Up to ``INLINE_LIMIT`` serialized bytes the result is returned as built. Above it, the
    findings that fit are kept in native order with the evidence they reference, the complete
    native output is written to ``<cwd>/native/full-output.json`` (an artifact with its
    sha256) and the result is ``partial`` with the truncation limitation. A result that does
    not fit even without findings is a structured error, never an oversized response.
    """
    producer = {"id": result.provider_id, "version": result.version}
    status = "partial" if result.partial else "ok"
    evidence: list[dict[str, Any]] = []
    for item in result.evidence:
        entry = dict(item)
        entry.setdefault("producer", dict(producer))
        evidence.append(entry)
    payload: dict[str, Any] = {
        "schema": RESULT_SCHEMA,
        "producer": producer,
        "created_at": utc_now(),
        "status": status,
        "findings": [dict(finding) for finding in result.findings],
        "evidence": evidence,
        "artifacts": [dict(artifact) for artifact in result.artifacts],
        "limitations": list(result.limitations),
        "unknowns": list(result.unknowns),
    }
    if result.provider_receipt is not None:
        payload["provider_receipt"] = dict(result.provider_receipt)
    if result.provider_economy is not None:
        payload["provider_economy"] = dict(result.provider_economy)
    if result.native_trace is not None:
        payload["native_trace"] = dict(result.native_trace)
    if inline_size(payload) > INLINE_LIMIT:
        return _spill(result, payload, cwd)
    return Reply(
        status=status,
        payload=payload,
        limitations=list(result.limitations),
        unknowns=list(result.unknowns),
    )


def native_timeout(payload: Mapping[str, Any]) -> float:
    """Seconds a native call may run: ``NATIVE_TIMEOUT_SHARE`` of the execute timeout of
    ``task.budget_profile``. A missing or unknown profile gets the shortest one, so a native
    call never outlives the core's own timeout."""
    task = payload.get("task")
    profile = task.get("budget_profile") if isinstance(task, Mapping) else None
    seconds = EXECUTE_TIMEOUTS.get(profile) if isinstance(profile, str) else None
    if seconds is None:
        seconds = min(EXECUTE_TIMEOUTS.values())
    return seconds * NATIVE_TIMEOUT_SHARE


def is_credential_name(name: str) -> bool:
    """True for a credential-shaped environment variable name (case-insensitive)."""
    return any(pattern.search(name) for pattern in CREDENTIAL_PATTERNS)


def _env_allowed(name: str, value: str) -> bool:
    return not is_credential_name(name) and _URL_USERINFO.search(value) is None


def native_env(
    adjustments: Mapping[str, str], base: Mapping[str, str] | None = None
) -> dict[str, str]:
    """The environment of a native process: ``base`` (the environment received from the
    core, ``os.environ`` by default) with the adapter's ``adjustments`` applied (names
    compared case-insensitively). Credential-shaped names and values carrying URL userinfo
    are dropped from both, so an adjustment can never add a credential."""
    source = os.environ if base is None else base
    adjusted = {name.upper() for name in adjustments}
    env = {
        name: value
        for name, value in source.items()
        if name.upper() not in adjusted and _env_allowed(name, value)
    }
    env.update({name: value for name, value in adjustments.items() if _env_allowed(name, value)})
    return env


@dataclass(frozen=True)
class NativeOutcome:
    """A finished native process: exit code and capped outputs."""

    returncode: int
    stdout: bytes
    stderr: bytes
    stdout_truncated: bool = False
    stderr_truncated: bool = False


class NativeTimeout(Exception):
    """A native process outlived its timeout (it was stopped with all its children)."""

    def __init__(self, timeout: float):
        super().__init__(f"native process exceeded {timeout:g} s")
        self.timeout = timeout

    def reply(self) -> Reply:
        """The structured ``ADAPTER-NATIVE-TIMEOUT`` error."""
        return fail(
            NATIVE_TIMEOUT,
            f"native process exceeded {self.timeout:g} s and was stopped with its child processes",
            unlock="retry with a larger budget profile (economy < balanced < max)",
        )


class _CappedReader:
    """Drains a pipe in a thread, keeping at most ``cap`` bytes (the rest is discarded)."""

    def __init__(self, stream: IO[bytes], cap: int):
        self.stream = stream
        self.data = bytearray()
        self.truncated = False
        self._cap = max(cap, 0)
        self._thread = threading.Thread(target=self._drain, daemon=True)
        self._thread.start()

    def _drain(self) -> None:
        # The thread is the only user of the pipe, so it closes it itself on EOF: closing it
        # from another thread while a read is blocked could deadlock on the buffer lock or
        # hand a reused descriptor to the next read.
        try:
            with contextlib.suppress(OSError, ValueError):
                while True:
                    chunk = self.stream.read(_READ_CHUNK)
                    if not chunk:
                        return
                    room = self._cap - len(self.data)
                    if len(chunk) > room:
                        self.truncated = True
                    if room > 0:
                        self.data += chunk[:room]
        finally:
            with contextlib.suppress(OSError):
                self.stream.close()

    def finish(self, timeout: float) -> None:
        """Wait up to ``timeout`` for EOF. A reader still blocked (a process outside the
        killed tree holds the pipe) closes the pipe itself when that process lets go."""
        self._thread.join(timeout)


def _reap(proc: subprocess.Popen[bytes]) -> None:
    with contextlib.suppress(subprocess.TimeoutExpired):
        proc.wait(timeout=_REAP_SECONDS)


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _CREATE_SUSPENDED = 0x00000004
    _JOB_EXTENDED_LIMIT_INFORMATION = 9
    _JOB_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
    _PROCESS_ACCESS = 0x0001 | 0x0100 | 0x0800  # terminate, set quota, suspend/resume

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
            (name, ctypes.c_uint64)
            for name in (
                "ReadOperationCount",
                "WriteOperationCount",
                "OtherOperationCount",
                "ReadTransferCount",
                "WriteTransferCount",
                "OtherTransferCount",
            )
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
        info.BasicLimitInformation.LimitFlags = _JOB_LIMIT_KILL_ON_JOB_CLOSE
        if not _kernel32.SetInformationJobObject(
            job, _JOB_EXTENDED_LIMIT_INFORMATION, ctypes.byref(info), ctypes.sizeof(info)
        ):
            _kernel32.CloseHandle(job)
            return None
        return job

    def _release(job: int | None) -> None:
        if job:
            _kernel32.CloseHandle(job)  # KILL_ON_JOB_CLOSE ends anything still in the job

    def _spawn(
        argv: Sequence[str], cwd: Path, env: Mapping[str, str]
    ) -> tuple[subprocess.Popen[bytes], int | None]:
        """Start suspended, join a kill-on-close Job Object, then resume: children the
        native process starts are in the job before it runs any code."""
        job = _create_job()
        try:
            proc = subprocess.Popen(
                list(argv),
                cwd=cwd,
                env=dict(env),
                shell=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=_CREATE_SUSPENDED,
            )
        except BaseException:
            _release(job)
            raise
        handle: int | None = _kernel32.OpenProcess(_PROCESS_ACCESS, False, proc.pid)
        if not handle:
            proc.kill()
            _reap(proc)
            _release(job)
            raise OSError("cannot open the native process")
        try:
            if job and not _kernel32.AssignProcessToJobObject(job, handle):
                _release(job)
                job = None
            if _ntdll.NtResumeProcess(handle) < 0:
                proc.kill()
                _reap(proc)
                _release(job)
                raise OSError("cannot resume the native process")
        finally:
            _kernel32.CloseHandle(handle)
        return proc, job

    def _kill_tree(proc: subprocess.Popen[bytes], job: int | None) -> None:
        terminated = bool(job) and bool(_kernel32.TerminateJobObject(job, 1))
        if not terminated and proc.poll() is None:
            # Fallback without a job: recursive kill by PID while the root still exists.
            with contextlib.suppress(OSError, subprocess.SubprocessError):
                subprocess.run(
                    ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=_REAP_SECONDS,
                    check=False,
                )
        if proc.poll() is None:
            with contextlib.suppress(OSError):
                proc.kill()
        _reap(proc)

    def _terminate_guard(
        active: list[subprocess.Popen[bytes]],
    ) -> contextlib.AbstractContextManager[None]:
        # The native job is nested in the core's job: when the core ends the adapter's job,
        # the native tree goes with it.
        return contextlib.nullcontext()

else:
    import signal

    def _release(job: int | None) -> None:
        return None

    def _spawn(
        argv: Sequence[str], cwd: Path, env: Mapping[str, str]
    ) -> tuple[subprocess.Popen[bytes], int | None]:
        """The native process leads a new session: its children share its process group."""
        proc = subprocess.Popen(
            list(argv),
            cwd=cwd,
            env=dict(env),
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        return proc, None

    def _kill_tree(proc: subprocess.Popen[bytes], job: int | None) -> None:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(proc.pid, signal.SIGKILL)  # session leader: pgid == pid
        if proc.poll() is None:
            with contextlib.suppress(OSError):
                proc.kill()
        _reap(proc)

    @contextlib.contextmanager
    def _terminate_guard(active: list[subprocess.Popen[bytes]]) -> Iterator[None]:
        """While a native process runs, SIGTERM to the adapter (the core signals the
        adapter's process group, which the native session left) first kills the native
        tree, then gets the previous disposition (default: the adapter dies of SIGTERM)."""
        if threading.current_thread() is not threading.main_thread():
            yield  # signal handlers can only be installed from the main thread
            return
        previous = signal.getsignal(signal.SIGTERM)
        if previous == signal.SIG_IGN:
            yield
            return
        restore = signal.SIG_DFL if previous is None else previous

        def on_sigterm(signum: int, frame: Any) -> None:
            for proc in active:
                _kill_tree(proc, None)
            signal.signal(signal.SIGTERM, restore)
            if callable(restore):
                restore(signum, frame)
            else:
                os.kill(os.getpid(), signal.SIGTERM)

        signal.signal(signal.SIGTERM, on_sigterm)
        try:
            yield
        finally:
            signal.signal(signal.SIGTERM, restore)


def run_native(
    argv: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    timeout: float,
    stdout_cap: int = NATIVE_STDOUT_CAP,
    stderr_cap: int = NATIVE_STDERR_CAP,
) -> NativeOutcome:
    """Run a native process without a shell in ``cwd``.

    ``env`` holds the adapter's explicit adjustments to the environment received from the
    core (``native_env``: credential-shaped names never pass). stdout/stderr are drained
    concurrently and kept up to their caps. When the process ends, or after ``timeout``
    seconds, its whole tree is killed, so no child outlives the call; an overrun raises
    ``NativeTimeout``. ``argv`` must be a non-empty list or tuple of strings (a bare string
    is a ``TypeError``, never split).
    """
    if not isinstance(argv, (list, tuple)) or not all(isinstance(a, str) for a in argv):
        raise TypeError("argv must be a list or tuple of strings")
    if not argv:
        raise ValueError("argv must not be empty")
    active: list[subprocess.Popen[bytes]] = []
    with _terminate_guard(active):
        proc, job = _spawn(argv, cwd, native_env(env))
        active.append(proc)
        if proc.stdout is None or proc.stderr is None:  # pragma: no cover - pipes requested
            raise RuntimeError("native process pipes are missing")
        out = _CappedReader(proc.stdout, stdout_cap)
        err = _CappedReader(proc.stderr, stderr_cap)
        timed_out = False
        try:
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
        finally:
            _kill_tree(proc, job)  # also ends children a finished process left behind
            _release(job)
            out.finish(_REAP_SECONDS)
            err.finish(_REAP_SECONDS)
    if timed_out:
        raise NativeTimeout(timeout)
    return NativeOutcome(
        returncode=proc.returncode,
        stdout=bytes(out.data),
        stderr=bytes(err.data),
        stdout_truncated=out.truncated,
        stderr_truncated=err.truncated,
    )


def _is_link(st: os.stat_result) -> bool:
    """A symlink or, on Windows, any reparse point (junctions included): never followed."""
    attributes = getattr(st, "st_file_attributes", 0)
    return stat.S_ISLNK(st.st_mode) or bool(attributes & _FILE_ATTRIBUTE_REPARSE_POINT)


def _remove_link(path: str) -> None:
    """Remove a link itself (its target is never touched, nor its mode changed)."""
    try:
        os.unlink(path)
    except OSError:
        os.rmdir(path)  # a directory symlink or junction on Windows: removes the link only


def _remove_file(path: str) -> None:
    """Remove a regular file, clearing a read-only flag (Windows) once if needed.

    The flag is only cleared on a file with a single link: a hard link shares its mode with
    a file that may live outside the cwd, so that removal fails (and is reported) instead.
    """
    try:
        os.unlink(path)
    except PermissionError:
        st = os.lstat(path)
        if st.st_nlink != 1 or _is_link(st):
            raise
        os.chmod(path, stat.S_IREAD | stat.S_IWRITE)
        os.unlink(path)


def _purge_dir(path: str, rel: str, st: os.stat_result, failures: list[str]) -> bool:
    mode = stat.S_IMODE(st.st_mode)
    if mode & stat.S_IRWXU != stat.S_IRWXU:  # read-only directory: its entries must go
        os.chmod(path, mode | stat.S_IRWXU)
    gone = True
    for name in sorted(os.listdir(path)):
        gone = _purge(os.path.join(path, name), f"{rel}/{name}", failures) and gone
    if not gone:
        return False  # the entry that stayed is reported, not its directory
    os.rmdir(path)
    return True


def _purge(path: str, rel: str, failures: list[str]) -> bool:
    """Remove ``path`` without following links; False (and ``rel`` reported) if it stays."""
    try:
        st = os.lstat(path)
        if _is_link(st):
            _remove_link(path)
        elif stat.S_ISDIR(st.st_mode):
            return _purge_dir(path, rel, st, failures)
        else:
            _remove_file(path)
    except FileNotFoundError:
        return True
    except OSError:
        failures.append(rel)
        return False
    return True


def _name_key(parts: Sequence[str]) -> tuple[str, ...]:
    """Path parts compared as the filesystem does (case-insensitively on Windows)."""
    return tuple(os.path.normcase(part) for part in parts)


def _contained_parts(keep: Collection[str]) -> dict[str, tuple[str, ...]]:
    """Declared path -> its parts, for contained relative POSIX paths only."""
    contained: dict[str, tuple[str, ...]] = {}
    for path in keep:
        if not isinstance(path, str) or not _lexically_contained(path):
            continue
        parts = tuple(part for part in path.split("/") if part not in ("", "."))
        if parts:
            contained[path] = parts
    return contained


def _kept_parts(contained: Mapping[str, tuple[str, ...]]) -> set[tuple[str, ...]]:
    """Name keys of the artifact paths that are kept (never under ``stage/``)."""
    stage = os.path.normcase(STAGE_DIR)
    keys = (_name_key(parts) for parts in contained.values())
    return {key for key in keys if key[0] != stage}


def _is_regular_artifact(cwd: str, parts: tuple[str, ...]) -> bool:
    """``parts`` is a regular file under real directories, with no link on the way."""
    path = cwd
    for index, part in enumerate(parts):
        path = os.path.join(path, part)
        try:
            st = os.lstat(path)
        except OSError:
            return False
        if _is_link(st):
            return False
        last = index == len(parts) - 1
        if not (stat.S_ISREG(st.st_mode) if last else stat.S_ISDIR(st.st_mode)):
            return False
    return True


def _reduce(
    directory: str,
    prefix: tuple[str, ...],
    kept: set[tuple[str, ...]],
    parents: set[tuple[str, ...]],
    preserve: Collection[str],
    failures: list[str],
) -> None:
    try:
        names = sorted(os.listdir(directory))
    except OSError:
        failures.append("/".join(prefix) or ".")
        return
    for name in names:
        rel = (*prefix, name)
        if not prefix and name in preserve:
            continue
        path = os.path.join(directory, name)
        key = _name_key(rel)
        if key in kept or key in parents:
            try:
                st = os.lstat(path)
            except FileNotFoundError:
                continue
            except OSError:
                failures.append("/".join(rel))
                continue
            if not _is_link(st):  # a link is never kept nor traversed, even at a kept path
                if key in kept:
                    continue
                if stat.S_ISDIR(st.st_mode):
                    _reduce(path, rel, kept, parents, preserve, failures)
                    continue
        _purge(path, "/".join(rel), failures)


def cleanup_workdir(
    cwd: Path, keep: Collection[str], *, preserve: Collection[str] = ()
) -> tuple[str, ...]:
    """Reduce ``cwd`` to the artifact paths in ``keep`` (and their parent directories).

    ``stage/`` and every other file, directory or link are removed; links are removed, never
    followed, and a link is never kept. A path in ``keep`` that is not a contained relative
    POSIX path keeps nothing. Top-level names in ``preserve`` are left alone. Returns the
    limitations for what could not be removed (sorted, at most ``CLEANUP_REPORT_LIMIT`` paths
    plus a count of the rest), then ``workdir cleanup removed artifact: <path>`` for each
    declared artifact that existed but is not a regular file reached without links afterwards
    (it was behind a link or under ``stage/``); never raises for a removal failure. Names are
    matched as the filesystem does (case-insensitively on Windows).
    """
    root = os.fspath(cwd)
    contained = _contained_parts(keep)
    # Declared artifacts present before the reduction (possibly through a link) must still
    # be regular files afterwards; one behind a link (or under stage/) is gone.
    present = sorted(
        path for path, parts in contained.items() if os.path.lexists(os.path.join(root, *parts))
    )
    kept = _kept_parts(contained)
    parents = {parts[:index] for parts in kept for index in range(1, len(parts))}
    failures: list[str] = []
    _reduce(root, (), kept, parents, preserve, failures)
    failures.sort()
    notes = [f"{CLEANUP_INCOMPLETE}{path}" for path in failures[:CLEANUP_REPORT_LIMIT]]
    if len(failures) > CLEANUP_REPORT_LIMIT:
        notes.append(f"{CLEANUP_INCOMPLETE}{len(failures) - CLEANUP_REPORT_LIMIT} more entries")
    notes.extend(
        f"{CLEANUP_REMOVED}{path}"
        for path in present
        if not _is_regular_artifact(root, contained[path])
    )
    return tuple(notes)


def _listing(cwd: Path) -> frozenset[str]:
    try:
        return frozenset(os.listdir(cwd))
    except OSError:
        return frozenset()


def _declared_artifacts(reply: Reply) -> list[str]:
    if reply.status not in ("ok", "partial"):
        return []
    artifacts = reply.payload.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    return [
        item["path"]
        for item in artifacts
        if isinstance(item, Mapping) and isinstance(item.get("path"), str)
    ]


def _after_execute(reply: Reply, cwd: Path, preexisting: frozenset[str]) -> Reply:
    """``reply`` once the cwd is reduced to its artifacts; a removal failure (or a cleanup
    that crashed) is a limitation of the result and of the envelope, never an error."""
    try:
        notes = cleanup_workdir(cwd, _declared_artifacts(reply), preserve=preexisting)
    except Exception:
        notes = (f"{CLEANUP_INCOMPLETE}.",)
    if not notes:
        return reply
    payload = reply.payload
    status = reply.status
    if status in ("ok", "partial") and isinstance(payload.get("limitations"), list):
        payload = {**payload, "limitations": [*payload["limitations"], *notes]}
        if any(note.startswith(CLEANUP_REMOVED) for note in notes):
            status = "partial"  # a result never claims ok with a declared artifact missing
            payload["status"] = status
    return replace(reply, status=status, payload=payload, limitations=[*reply.limitations, *notes])


def parse_options(args: Sequence[str]) -> AdapterOptions:
    """Parse the adapter flags that precede the op (each at most once, each with a value)."""
    values: dict[str, str] = {}
    index = 0
    while index < len(args):
        name = args[index]
        if name not in (OPTION_REPLAY, OPTION_ASSUME_VERSION):
            raise _Invalid(f"unknown adapter option {name!r}", "argv")
        if name in values:
            raise _Invalid(f"adapter option {name} given more than once", "argv")
        if index + 1 >= len(args) or not args[index + 1]:
            raise _Invalid(f"adapter option {name} needs a value", "argv")
        values[name] = args[index + 1]
        index += 2
    replay = values.get(OPTION_REPLAY)
    return AdapterOptions(
        replay=None if replay is None else Path(replay),
        assume_specialist_version=values.get(OPTION_ASSUME_VERSION),
    )


MAX_REQUEST_DEPTH = 256


def _nesting_exceeds(value: object, limit: int) -> bool:
    """Iterative depth check, so a deeply nested request never relies on RecursionError."""
    stack: list[tuple[object, int]] = [(value, 1)]
    while stack:
        item, depth = stack.pop()
        if isinstance(item, dict):
            children: list[object] = list(item.values())
        elif isinstance(item, list):
            children = item
        else:
            continue
        if depth > limit:
            return True
        stack.extend((child, depth + 1) for child in children)
    return False


def parse_request(raw: bytes, op: str) -> Request:
    """Decode and validate the request envelope read from stdin."""
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):  # RecursionError: deep nesting
        raise _Invalid("request is not a UTF-8 JSON document", "request") from None
    if _nesting_exceeds(data, MAX_REQUEST_DEPTH):  # Python >= 3.14 parses deep nesting fine
        raise _Invalid(f"request nests deeper than {MAX_REQUEST_DEPTH} levels", "request")
    if not isinstance(data, dict):
        raise _Invalid("request must be a JSON object", "request")
    request_id = data.get("request_id")
    if not isinstance(request_id, str) or not request_id:
        raise _Invalid("request_id must be a non-empty string", "request_id")
    if data.get("kind") != "Request":
        raise _Invalid("kind must be 'Request'", "kind", request_id)
    if data.get("op") != op:
        raise _Invalid(
            f"request op {data.get('op')!r} differs from invoked op {op!r}", "op", request_id
        )
    protocol = data.get("protocol")
    if not isinstance(protocol, str):
        raise _Invalid("protocol must be a string", "protocol", request_id)
    payload = data.get("payload", {})
    if not isinstance(payload, dict):
        raise _Invalid("payload must be a JSON object", "payload", request_id)
    return Request(op=op, request_id=request_id, protocol=protocol, payload=payload)


def _declared_actions(
    handlers: Mapping[str, HandlerFactory], options: AdapterOptions, request: Request, cwd: Path
) -> dict[str, list[str]] | Reply:
    """Capability id -> actions from this adapter's own ``describe``.

    A describe that is not ``ok`` is returned as is: its error (e.g. the specialist is not
    installed) is the real reason the execute cannot run.
    """
    factory = handlers.get("describe")
    if factory is None:
        return {}
    probe = Request(
        op="describe", request_id=request.request_id, protocol=request.protocol, payload={}
    )
    reply = factory(options)(probe, cwd)
    if not isinstance(reply, Reply):
        raise TypeError("handler did not return a Reply")
    if reply.status != "ok":
        return reply
    declared: dict[str, list[str]] = {}
    for capability in reply.payload.get("capabilities") or []:
        if isinstance(capability, dict) and isinstance(capability.get("id"), str):
            actions = capability.get("actions") or []
            declared[capability["id"]] = [a for a in actions if isinstance(a, str)]
    return declared


def _check_execute(
    handlers: Mapping[str, HandlerFactory], options: AdapterOptions, request: Request, cwd: Path
) -> Reply | None:
    declared = _declared_actions(handlers, options, request, cwd)
    if isinstance(declared, Reply):
        return declared
    capability = request.payload.get("capability")
    if not isinstance(capability, str) or capability not in declared:
        return refuse(
            CAPABILITY_UNSUPPORTED,
            f"capability {capability!r} is not declared by this provider",
            field="capability",
        )
    action = request.payload.get("action")
    if not isinstance(action, str) or action not in declared[capability]:
        return refuse(
            ACTION_UNSUPPORTED,
            f"action {action!r} is not declared for capability {capability!r}",
            field="action",
        )
    return None


def dispatch(
    op: str,
    options: AdapterOptions,
    request: Request,
    handlers: Mapping[str, HandlerFactory],
    cwd: Path,
) -> Reply:
    """Apply the protocol gates and run the op handler."""
    factory = handlers.get(op)
    if factory is None:
        return refuse(OP_UNSUPPORTED, f"op {op!r} is not supported by this provider", field="op")
    if op != "describe" and request.protocol != PROTOCOL:
        return refuse(
            PROTOCOL_UNSUPPORTED,
            f"protocol {request.protocol!r} is not supported; expected {PROTOCOL!r}",
            field="protocol",
        )
    if op == "execute":
        refusal = _check_execute(handlers, options, request, cwd)
        if refusal is not None:
            return refusal
    reply = factory(options)(request, cwd)
    if not isinstance(reply, Reply):
        raise TypeError("handler did not return a Reply")
    return reply


def envelope(
    *, op: str, request_id: str, provider_id: str, version: str, reply: Reply
) -> dict[str, Any]:
    """The response envelope for ``reply``."""
    return {
        "protocol": PROTOCOL,
        "kind": "Response",
        "request_id": request_id,
        "op": op,
        "producer": {"id": provider_id, "version": version},
        "status": reply.status,
        "payload": reply.payload,
        "error": reply.error,
        "limitations": list(reply.limitations),
        "unknowns": list(reply.unknowns),
    }


def _encode(response: dict[str, Any]) -> bytes:
    return _dumps(response)


def _internal(exc: BaseException) -> Reply:
    # Only the exception type: its message or traceback may carry paths or secrets.
    return fail(INTERNAL, type(exc).__name__)


def _reply_for(
    argv: Sequence[str], raw: bytes, op: str, handlers: Mapping[str, HandlerFactory], cwd: Path
) -> tuple[str, Reply]:
    """(request id, reply) for one invocation; never raises for handler failures."""
    request_id = UNKNOWN_REQUEST_ID
    try:
        try:
            request = parse_request(raw, op)
            request_id = request.request_id
            options = parse_options(argv[:-1])
        except _Invalid as exc:
            request_id = exc.request_id if request_id == UNKNOWN_REQUEST_ID else request_id
            return request_id, fail(REQUEST_INVALID, exc.detail, field=exc.field_name)
        try:
            return request_id, dispatch(op, options, request, handlers, cwd)
        except NativeTimeout as exc:
            return request_id, exc.reply()
    # Every failure must become a response with exit 0, including a handler that calls
    # sys.exit() or raises KeyboardInterrupt; GeneratorExit and other BaseException
    # subclasses are interpreter machinery, not handler failures, and are not caught.
    except (Exception, SystemExit, KeyboardInterrupt) as exc:
        return request_id, _internal(exc)


def respond(
    argv: Sequence[str],
    raw: bytes,
    *,
    provider_id: str,
    version: str,
    handlers: Mapping[str, HandlerFactory],
    cwd: Path,
) -> bytes:
    """The encoded response for one invocation (never raises for handler failures).

    After an ``execute``, whatever its outcome, the cwd is reduced to the artifacts of the
    reply actually sent (entries that predate the call are left alone).
    """
    op = argv[-1] if argv else ""
    preexisting = _listing(cwd) if op == "execute" else None
    request_id, reply = _reply_for(argv, raw, op, handlers, cwd)

    def encode(answer: Reply) -> bytes:
        return _encode(
            envelope(
                op=op, request_id=request_id, provider_id=provider_id, version=version, reply=answer
            )
        )

    body: bytes | None
    try:
        body = encode(reply)
    except (Exception, SystemExit, KeyboardInterrupt) as exc:
        reply, body = _internal(exc), None  # an unencodable reply keeps no artifact
    if preexisting is not None:
        cleaned = _after_execute(reply, cwd, preexisting)
        if cleaned is not reply:
            reply, body = cleaned, None
    return encode(reply) if body is None else body


def serve(
    *,
    provider_id: str,
    version: str,
    handlers: Mapping[str, HandlerFactory],
    argv: Sequence[str] | None = None,
    stdin: BinaryIO | None = None,
    stdout: BinaryIO | None = None,
) -> int:
    """Answer one Forge Protocol v1 call; always returns exit code 0."""
    args = list(sys.argv[1:] if argv is None else argv)
    source = sys.stdin.buffer if stdin is None else stdin
    sink = sys.stdout.buffer if stdout is None else stdout
    try:
        raw = source.read()
    except Exception:  # an unreadable stdin is an invalid request
        raw = b""
    sink.write(
        respond(
            args, raw, provider_id=provider_id, version=version, handlers=handlers, cwd=Path.cwd()
        )
    )
    sink.flush()
    return 0
