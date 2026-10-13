"""Entry point: python -m theforge.providers.echo <op>"""

import sys

from theforge.contracts.canonical import canonical_json
from theforge.providers.echo.provider import handle


def main() -> int:
    op = sys.argv[1] if len(sys.argv) > 1 else ""
    response = handle(op, sys.stdin.buffer.read())
    sys.stdout.buffer.write(canonical_json(response).encode("utf-8"))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
