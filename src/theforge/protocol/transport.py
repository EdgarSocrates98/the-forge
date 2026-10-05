"""Subprocess transport for Forge Protocol v1: `<argv> <op>`, JSON over stdin/stdout."""

import contextlib
import json
import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import IO, Any, Protocol

from theforge.contracts import (
    PROTOCOL_V1,
    ContractError,
    Request,
    Response,
    from_dict,
    new_request_id,
    to_dict,
)
from theforge.contracts.canonical import canonical_json
from theforge.contracts.codes import Codes
from theforge.protocol import proctree
from theforge.security.env import safe_env
from theforge.security.redact import redact_text

MAX_STDOUT_BYTES = 8 * 1024 * 1024
MAX_STDERR_BYTES = 64 * 1024
_STDERR_TAIL_CHARS = 500
_POLL_SECONDS = 0.1
_GRACE_SECONDS = 2.0
_JOIN_SECONDS = 5.0


class TransportError(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


class ProviderTransport(Protocol):
    def call(
        self, op: str, payload: dict[str, Any], *, timeout: float,
        cwd: Path | None = None, check_protocol: bool = True,
    ) -> Response: ...


TransportFactory = Callable[[Sequence[str]], ProviderTransport]


class SubprocessTransport:
    def __init__(
        self, argv: Sequence[str], *, protocol: str = PROTOCOL_V1,
        max_stdout: int = MAX_STDOUT_BYTES,
    ) -> None:
        if not argv:
            raise ValueError("provider argv must not be empty")
        self.argv = list(argv)
        self.protocol = protocol
        self.max_stdout = max_stdout

    def call(
        self, op: str, payload: dict[str, Any], *, timeout: float,
        cwd: Path | None = None, check_protocol: bool = True,
    ) -> Response:
        request = Request(protocol=self.protocol, op=op, request_id=new_request_id(),
                          payload=payload)
        stdout = self._run(op, canonical_json(to_dict(request)).encode("utf-8"), timeout, cwd)
        try:
            data = json.loads(stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TransportError(Codes.PROTO_NOT_JSON, f"{op}: stdout is not JSON ({exc})") \
                from exc
        except (ValueError, RecursionError) as exc:
            # Integer literals past the int-digit limit or nesting past the recursion limit:
            # valid-looking JSON that cannot be decoded safely. The payload is not echoed.
            raise TransportError(
                Codes.PROTO_NOT_JSON,
                f"{op}: stdout JSON cannot be decoded ({type(exc).__name__}: "
                "integer too long or nesting too deep)",
            ) from exc
        try:
            response = from_dict(Response, data)
        except ContractError as exc:
            raise TransportError(Codes.PROTO_SCHEMA, f"{op}: {exc}") from exc
        if response.request_id != request.request_id:
            raise TransportError(
                Codes.PROTO_MISMATCH,
                f"{op}: response request_id {response.request_id!r} "
                f"!= {request.request_id!r}",
            )
        if response.op is not None and response.op != op:
            raise TransportError(
                Codes.PROTO_OP_MISMATCH, f"{op}: response op {response.op!r} != {op!r}")
        if check_protocol and response.protocol != self.protocol:
            raise TransportError(
                Codes.PROTO_VERSION,
                f"{op}: response protocol {response.protocol!r} != {self.protocol!r}",
            )
        return response

    def _run(self, op: str, stdin_bytes: bytes, timeout: float, cwd: Path | None) -> bytes:
        try:
            sp = proctree.spawn([*self.argv, op], cwd=cwd if cwd is not None else Path.cwd(),
                                env=safe_env())
        except OSError as exc:
            raise TransportError(Codes.PROTO_SPAWN, f"cannot start {self.argv[0]!r}: {exc}") \
                from exc
        proc = sp.proc
        out = bytearray()
        err = _StderrTail(MAX_STDERR_BYTES)
        oversize = threading.Event()
        pairs: list[tuple[IO[bytes], threading.Thread]] = []
        try:
            if proc.stdin is None or proc.stdout is None or proc.stderr is None:
                raise TransportError(Codes.PROTO_SPAWN, "provider pipes unavailable")

            def pump_out(stream: IO[bytes]) -> None:
                with proctree.owned(stream):
                    while chunk := proctree.read_chunk(stream):
                        if len(out) + len(chunk) > self.max_stdout:
                            oversize.set()  # stop reading; the main thread kills the tree
                            return
                        out.extend(chunk)

            def pump_err(stream: IO[bytes]) -> None:
                with proctree.owned(stream):
                    while chunk := proctree.read_chunk(stream):
                        err.feed(chunk)

            def feed_in(stream: IO[bytes]) -> None:
                try:
                    stream.write(stdin_bytes)
                    stream.close()
                except OSError:
                    pass

            # Each pipe is owned by the only thread that uses it and closed by that thread:
            # closing a pipe under a pending read blocks (Windows) or races fd reuse (POSIX),
            # and the thread's reference keeps garbage collection from closing it early.
            pairs = [
                (proc.stdout, threading.Thread(target=pump_out, args=(proc.stdout,),
                                               daemon=True)),
                (proc.stderr, threading.Thread(target=pump_err, args=(proc.stderr,),
                                               daemon=True)),
                (proc.stdin, threading.Thread(target=feed_in, args=(proc.stdin,), daemon=True)),
            ]
            for _, thread in pairs:
                thread.start()
            deadline = time.monotonic() + timeout
            while not oversize.is_set():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TransportError(
                        Codes.PROTO_TIMEOUT, f"{op}: no response within {timeout:g}s")
                if proctree.wait_slice(proc, min(remaining, _POLL_SECONDS)):
                    break
            if oversize.is_set():
                raise TransportError(
                    Codes.PROTO_OVERSIZE, f"{op}: stdout exceeded {self.max_stdout} bytes")
            # The root exited: end descendants that may still hold the pipes, then drain.
            _end_tree(sp)
            proctree.join_threads((t for _, t in pairs), _JOIN_SECONDS)
            if oversize.is_set():  # the last chunks may arrive after the root exited
                raise TransportError(
                    Codes.PROTO_OVERSIZE, f"{op}: stdout exceeded {self.max_stdout} bytes")
            if proc.returncode != 0:
                raise TransportError(
                    Codes.PROTO_EXIT,
                    f"{op}: exit code {proc.returncode}; stderr: {err.redacted_tail()}")
            return bytes(out)
        finally:
            # Any exit path (timeout, oversize, KeyboardInterrupt, errors): end the whole tree.
            _end_tree(sp)
            proctree.join_threads((t for _, t in pairs), _JOIN_SECONDS)
            for pipe, thread in pairs:
                if not thread.is_alive():
                    with contextlib.suppress(OSError):
                        pipe.close()


def _end_tree(sp: proctree.SpawnedProcess) -> None:
    """Idempotent: kill the whole tree (even if the root already exited), release the job."""
    proctree.kill_tree(sp, grace_seconds=_GRACE_SECONDS)
    proctree.close(sp)


class _StderrTail:
    """Keeps only the most recent ``limit`` bytes of provider stderr (never persisted raw)."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.buf = bytearray()
        self.truncated = False
        self._lock = threading.Lock()

    def feed(self, chunk: bytes) -> None:
        with self._lock:
            self.buf.extend(chunk)
            excess = len(self.buf) - self.limit
            if excess > 0:
                del self.buf[:excess]
                self.truncated = True

    def redacted_tail(self, chars: int = _STDERR_TAIL_CHARS) -> str:
        with self._lock:
            raw, truncated = bytes(self.buf), self.truncated
        text = raw.decode("utf-8", errors="replace")
        if truncated:
            # The cut may split a secret: drop the partial first line before redaction.
            _, newline, rest = text.partition("\n")
            text = rest if newline else ""
        tail = redact_text(text).strip()[-chars:]
        return f"[truncated] {tail}" if truncated else tail
