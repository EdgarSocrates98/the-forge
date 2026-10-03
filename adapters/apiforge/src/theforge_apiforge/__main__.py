"""Entry point: ``python -m theforge_apiforge <op>``: request on stdin, response on stdout.

Installable skeleton: every op is refused with a valid Forge Protocol v1 response and exit 0
until the adapter shell and the API Forge integration are in place.
"""

import json
import sys

from theforge_apiforge import PROVIDER_ID, VERSION

PROTOCOL = "forge/v1"
NOT_IMPLEMENTED = "ADAPTER-OP-UNSUPPORTED"


def _request_id(raw: bytes) -> str:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "unknown"
    request_id = data.get("request_id") if isinstance(data, dict) else None
    return request_id if isinstance(request_id, str) and request_id else "unknown"


def refusal(op: str, raw: bytes) -> dict[str, object]:
    """The skeleton answer for any op: a well-formed ``refused`` response."""
    return {
        "protocol": PROTOCOL,
        "kind": "Response",
        "request_id": _request_id(raw),
        "op": op,
        "producer": {"id": PROVIDER_ID, "version": VERSION},
        "status": "refused",
        "payload": {},
        "error": {
            "code": NOT_IMPLEMENTED,
            "detail": f"op {op!r} is not implemented by {PROVIDER_ID} {VERSION} yet",
            "field": "op",
        },
        "limitations": ["adapter skeleton: no op is implemented yet"],
        "unknowns": [],
    }


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    op = args[-1] if args else ""
    response = refusal(op, sys.stdin.buffer.read())
    text = json.dumps(response, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    sys.stdout.buffer.write(text.encode("utf-8"))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
