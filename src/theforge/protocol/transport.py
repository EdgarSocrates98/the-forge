"""Subprocess transport for Forge Protocol v1: `<argv> <op>`, JSON over stdin/stdout."""

import contextlib
import json
import subprocess
import threading
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
from theforge.security.env import safe_env
from theforge.security.redact import redact_text

MAX_STDOUT_BYTES = 8 * 1024 * 1024
MAX_STDERR_BYTES = 64 * 1024
_CHUNK = 65536


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
            raise TransportError("FORGE-PROTO-NOT-JSON", f"{op}: stdout is not JSON ({exc})") \
                from exc
        try:
            response = from_dict(Response, data)
        except ContractError as exc:
            raise TransportError("FORGE-PROTO-SCHEMA", f"{op}: {exc}") from exc
        if response.request_id != request.request_id:
            raise TransportError(
                "FORGE-PROTO-MISMATCH",
                f"{op}: response request_id {response.request_id!r} "
                f"!= {request.request_id!r}",
            )
        if check_protocol and response.protocol != self.protocol:
            raise TransportError(
                "FORGE-PROTO-VERSION",
                f"{op}: response protocol {response.protocol!r} != {self.protocol!r}",
            )
        return response

    def _run(self, op: str, stdin_bytes: bytes, timeout: float, cwd: Path | None) -> bytes:
        try:
            proc = subprocess.Popen(
                [*self.argv, op], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, cwd=cwd, env=safe_env(), shell=False,
            )
        except OSError as exc:
            raise TransportError("FORGE-PROTO-SPAWN", f"cannot start {self.argv[0]!r}: {exc}") \
                from exc
        if proc.stdin is None or proc.stdout is None or proc.stderr is None:
            proc.kill()
            raise TransportError("FORGE-PROTO-SPAWN", "provider pipes unavailable")
        out = bytearray()
        err = bytearray()
        oversize = threading.Event()

        def pump_out(stream: IO[bytes]) -> None:
            while chunk := stream.read(_CHUNK):
                if len(out) + len(chunk) > self.max_stdout:
                    oversize.set()
                    proc.kill()
                    return
                out.extend(chunk)

        def pump_err(stream: IO[bytes]) -> None:
            while chunk := stream.read(_CHUNK):
                room = MAX_STDERR_BYTES - len(err)
                if room > 0:
                    err.extend(chunk[:room])

        def feed_in(stream: IO[bytes]) -> None:
            try:
                stream.write(stdin_bytes)
                stream.close()
            except OSError:
                pass

        threads = [
            threading.Thread(target=pump_out, args=(proc.stdout,), daemon=True),
            threading.Thread(target=pump_err, args=(proc.stderr,), daemon=True),
            threading.Thread(target=feed_in, args=(proc.stdin,), daemon=True),
        ]
        try:
            for thread in threads:
                thread.start()
            try:
                returncode = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired as exc:
                proc.kill()
                proc.wait()
                for thread in threads:
                    thread.join(timeout=5)
                raise TransportError(
                    "FORGE-PROTO-TIMEOUT", f"{op}: no response within {timeout:g}s") from exc
            for thread in threads:
                thread.join(timeout=5)
            if oversize.is_set():
                raise TransportError(
                    "FORGE-PROTO-OVERSIZE", f"{op}: stdout exceeded {self.max_stdout} bytes")
            if returncode != 0:
                tail = redact_text(err.decode("utf-8", errors="replace").strip())[-500:]
                raise TransportError(
                    "FORGE-PROTO-EXIT", f"{op}: exit code {returncode}; stderr: {tail}")
            return bytes(out)
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait()
            for pipe in (proc.stdin, proc.stdout, proc.stderr):
                with contextlib.suppress(OSError):
                    pipe.close()
