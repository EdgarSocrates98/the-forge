"""AdapterShell: the Forge Protocol v1 envelope and op dispatch shared by the adapters.

This file is copied byte for byte into every adapter package (a test enforces it): edit one
copy and copy it over. Stdlib-only, Python >= 3.10, and it never imports ``theforge``.

``serve`` reads the op from the last argument and the adapter options before it
(``--replay <dir>``, ``--assume-specialist-version <v>``), the request from stdin, and always
exits 0 with a response that echoes ``op`` and ``request_id`` and carries the adapter's
``producer``. Unknown op, unsupported protocol (outside ``describe``) and an undeclared
capability or action are ``refused``; an invalid request and any unexpected exception are a
structured ``error`` (the exception type only: never a traceback nor the message).
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
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
