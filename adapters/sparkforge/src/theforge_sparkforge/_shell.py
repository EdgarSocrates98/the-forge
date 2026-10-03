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
``ExecutionResult`` (schema, producer, UTC ``created_at``).
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

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


def _error(code: str, detail: str, field_name: str | None, unlock: str | None
           ) -> dict[str, Any]:
    return {"code": code, "detail": detail, "field": field_name, "unlock": unlock}


def refuse(code: str, detail: str, *, field: str | None = None,
           unlock: str | None = None) -> Reply:
    """A ``refused`` reply with a structured error."""
    return Reply(status="refused", error=_error(code, detail, field, unlock))


def fail(code: str, detail: str, *, field: str | None = None,
         unlock: str | None = None) -> Reply:
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
    declared = (raw_size if isinstance(raw_size, int) and not isinstance(raw_size, bool)
                and raw_size >= 0 else None)
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
    root = (Path(raw_root).resolve()
            if isinstance(raw_root, str) and raw_root and Path(raw_root).is_absolute()
            else None)
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
        value = value[len(_NATIVE_HASH_PREFIX):]
    if _SHA256_RE.fullmatch(value) is None or value != verified:
        return None
    return verified


def _matches(path: str, pattern: str) -> bool:
    return (fnmatch.fnmatchcase(path, pattern)
            or fnmatch.fnmatchcase(PurePosixPath(path).name, pattern))


def select_inputs(stage: StagedInput, required: Mapping[str, Sequence[str]]
                  ) -> dict[str, list[str]]:
    """Input name -> staged paths (sorted) matching any of its globs (path or file name)."""
    return {name: [path for path in sorted(stage.files)
                   if any(_matches(path, glob) for glob in globs)]
            for name, globs in required.items()}


def no_input(stage: StagedInput, required: Mapping[str, Sequence[str]], *,
             provider_id: str, version: str) -> ResultDraft | None:
    """A partial draft without findings when a required input has no staged file, else None.

    Decided before the specialist (or a replay recording) is consulted.
    """
    selected = select_inputs(stage, required)
    missing = [name for name in required if not selected[name]]
    if not missing:
        return None
    limitations = [*stage.limitations,
                   *(f"no input: expected {', '.join(required[name])}" for name in missing)]
    return ResultDraft(provider_id=provider_id, version=version, limitations=limitations,
                       unknowns=[f"input:{name}" for name in missing], partial=True)


def utc_now() -> str:
    """The current time as an ISO-8601 UTC timestamp (``Z`` suffix)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def finalize(result: ResultDraft, cwd: Path) -> Reply:
    """The ``ExecutionResult`` reply for ``result`` (schema, producer, UTC ``created_at``).

    ``cwd`` is the execute working directory, where output above the inline limit spills.
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
    return Reply(status=status, payload=payload, limitations=list(result.limitations),
                 unknowns=list(result.unknowns))


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
    return AdapterOptions(replay=None if replay is None else Path(replay),
                          assume_specialist_version=values.get(OPTION_ASSUME_VERSION))


def parse_request(raw: bytes, op: str) -> Request:
    """Decode and validate the request envelope read from stdin."""
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):  # RecursionError: deep nesting
        raise _Invalid("request is not a UTF-8 JSON document", "request") from None
    if not isinstance(data, dict):
        raise _Invalid("request must be a JSON object", "request")
    request_id = data.get("request_id")
    if not isinstance(request_id, str) or not request_id:
        raise _Invalid("request_id must be a non-empty string", "request_id")
    if data.get("kind") != "Request":
        raise _Invalid("kind must be 'Request'", "kind", request_id)
    if data.get("op") != op:
        raise _Invalid(f"request op {data.get('op')!r} differs from invoked op {op!r}", "op",
                       request_id)
    protocol = data.get("protocol")
    if not isinstance(protocol, str):
        raise _Invalid("protocol must be a string", "protocol", request_id)
    payload = data.get("payload", {})
    if not isinstance(payload, dict):
        raise _Invalid("payload must be a JSON object", "payload", request_id)
    return Request(op=op, request_id=request_id, protocol=protocol, payload=payload)


def _declared_actions(handlers: Mapping[str, HandlerFactory], options: AdapterOptions,
                      request: Request, cwd: Path) -> dict[str, list[str]] | Reply:
    """Capability id -> actions from this adapter's own ``describe``.

    A describe that is not ``ok`` is returned as is: its error (e.g. the specialist is not
    installed) is the real reason the execute cannot run.
    """
    factory = handlers.get("describe")
    if factory is None:
        return {}
    probe = Request(op="describe", request_id=request.request_id, protocol=request.protocol,
                    payload={})
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


def _check_execute(handlers: Mapping[str, HandlerFactory], options: AdapterOptions,
                   request: Request, cwd: Path) -> Reply | None:
    declared = _declared_actions(handlers, options, request, cwd)
    if isinstance(declared, Reply):
        return declared
    capability = request.payload.get("capability")
    if not isinstance(capability, str) or capability not in declared:
        return refuse(CAPABILITY_UNSUPPORTED,
                      f"capability {capability!r} is not declared by this provider",
                      field="capability")
    action = request.payload.get("action")
    if not isinstance(action, str) or action not in declared[capability]:
        return refuse(ACTION_UNSUPPORTED,
                      f"action {action!r} is not declared for capability {capability!r}",
                      field="action")
    return None


def dispatch(op: str, options: AdapterOptions, request: Request,
             handlers: Mapping[str, HandlerFactory], cwd: Path) -> Reply:
    """Apply the protocol gates and run the op handler."""
    factory = handlers.get(op)
    if factory is None:
        return refuse(OP_UNSUPPORTED, f"op {op!r} is not supported by this provider",
                      field="op")
    if op != "describe" and request.protocol != PROTOCOL:
        return refuse(PROTOCOL_UNSUPPORTED,
                      f"protocol {request.protocol!r} is not supported; expected {PROTOCOL!r}",
                      field="protocol")
    if op == "execute":
        refusal = _check_execute(handlers, options, request, cwd)
        if refusal is not None:
            return refusal
    reply = factory(options)(request, cwd)
    if not isinstance(reply, Reply):
        raise TypeError("handler did not return a Reply")
    return reply


def envelope(*, op: str, request_id: str, provider_id: str, version: str,
             reply: Reply) -> dict[str, Any]:
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
    text = json.dumps(response, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False)
    return text.encode("utf-8")


def _internal(exc: BaseException) -> Reply:
    # Only the exception type: its message or traceback may carry paths or secrets.
    return fail(INTERNAL, type(exc).__name__)


def respond(argv: Sequence[str], raw: bytes, *, provider_id: str, version: str,
            handlers: Mapping[str, HandlerFactory], cwd: Path) -> bytes:
    """The encoded response for one invocation (never raises for handler failures)."""
    op = argv[-1] if argv else ""
    request_id = UNKNOWN_REQUEST_ID
    try:
        try:
            request = parse_request(raw, op)
            request_id = request.request_id
            options = parse_options(argv[:-1])
        except _Invalid as exc:
            request_id = exc.request_id if request_id == UNKNOWN_REQUEST_ID else request_id
            reply = fail(REQUEST_INVALID, exc.detail, field=exc.field_name)
        else:
            reply = dispatch(op, options, request, handlers, cwd)
        return _encode(envelope(op=op, request_id=request_id, provider_id=provider_id,
                                version=version, reply=reply))
    # Every failure must become a response with exit 0, including a handler that calls
    # sys.exit() or raises KeyboardInterrupt; GeneratorExit and other BaseException
    # subclasses are interpreter machinery, not handler failures, and are not caught.
    except (Exception, SystemExit, KeyboardInterrupt) as exc:
        return _encode(envelope(op=op, request_id=request_id, provider_id=provider_id,
                                version=version, reply=_internal(exc)))


def serve(*, provider_id: str, version: str, handlers: Mapping[str, HandlerFactory],
          argv: Sequence[str] | None = None, stdin: BinaryIO | None = None,
          stdout: BinaryIO | None = None) -> int:
    """Answer one Forge Protocol v1 call; always returns exit code 0."""
    args = list(sys.argv[1:] if argv is None else argv)
    source = sys.stdin.buffer if stdin is None else stdin
    sink = sys.stdout.buffer if stdout is None else stdout
    try:
        raw = source.read()
    except Exception:  # an unreadable stdin is an invalid request
        raw = b""
    sink.write(respond(args, raw, provider_id=provider_id, version=version,
                       handlers=handlers, cwd=Path.cwd()))
    sink.flush()
    return 0
