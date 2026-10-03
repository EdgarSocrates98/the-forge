"""Entry point: ``python -m theforge_apiforge [options] <op>``, request on stdin, reply on stdout.

The common shell (``_shell.py``) owns the Forge Protocol v1 envelope, the adapter options and
the protocol, capability and action gates. Until the API Forge integration lands, the
describe/health/execute handlers refuse with a well-formed response (exit 0); with no
capability declared, every execute is refused by the shell as an undeclared capability.
"""

from __future__ import annotations

from pathlib import Path

from theforge_apiforge import PROVIDER_ID, VERSION
from theforge_apiforge._shell import (
    OP_UNSUPPORTED,
    AdapterOptions,
    HandlerFactory,
    OpHandler,
    Reply,
    Request,
    refuse,
    serve,
)


def _not_implemented(options: AdapterOptions) -> OpHandler:
    def handle(request: Request, cwd: Path) -> Reply:
        reply = refuse(OP_UNSUPPORTED,
                       f"op {request.op!r} is not implemented by {PROVIDER_ID} {VERSION} yet",
                       field="op")
        return Reply(status=reply.status, error=reply.error,
                     limitations=["adapter skeleton: no op is implemented yet"])
    return handle


HANDLERS: dict[str, HandlerFactory] = {
    "describe": _not_implemented,
    "health": _not_implemented,
    "execute": _not_implemented,
}


def main() -> int:
    return serve(provider_id=PROVIDER_ID, version=VERSION, handlers=HANDLERS)


if __name__ == "__main__":
    raise SystemExit(main())
