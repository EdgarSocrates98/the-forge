"""Misbehaving Forge Protocol provider for failure-mode tests (stdlib only).

argv: bad_forge.py MODE [PROVIDER_ID] OP
"""

import json
import os
import sys
import time

RESULT = {
    "schema": "theforge/ExecutionResult/v1",
    "created_at": "1970-01-01T00:00:00.000000Z",
    "status": "ok",
}


def main() -> int:
    mode, op = sys.argv[1], sys.argv[-1]
    pid = sys.argv[2] if len(sys.argv) > 3 else "bad-forge"
    producer = {"id": pid, "version": "0.0.1"}
    if mode == "no-read" and op == "execute":
        time.sleep(30)
        return 0
    raw = sys.stdin.read()
    try:
        rid = json.loads(raw).get("request_id", "unknown")
    except (json.JSONDecodeError, AttributeError):
        rid = "unknown"
    proto = "forge/v9" if mode == "wrong-major" else "forge/v1"

    def reply(status, payload=None, error=None, request_id=None):
        sys.stdout.write(json.dumps({
            "protocol": proto, "kind": "Response", "request_id": request_id or rid,
            "producer": producer, "status": status, "payload": payload or {}, "error": error,
        }))
        return 0

    if op == "describe":
        if mode == "describe-crash":
            sys.stderr.write("describe failed\n")
            return 3
        cap_id = "Bad Id" if mode == "invalid-manifest" else "bad.thing"
        return reply("ok", {
            "schema": "theforge/ForgeManifest/v1", "id": pid, "version": "0.0.1",
            "protocols": [proto], "ops": ["describe", "health", "execute"],
            "domains": ["test"],
            "capabilities": [{
                "id": cap_id, "actions": ["run"], "default_action": "run",
                "state": "supported", "operation_class": "read_only",
                "signals": {"keywords": ["bad"], "file_globs": [], "dependencies": []},
            }],
        })
    if op == "health":
        if mode == "unhealthy":
            return reply("ok", {"status": "unavailable",
                                "checks": [{"name": "backend", "ok": False,
                                            "detail": "backend down"}]})
        return reply("ok", {"status": "ok", "checks": []})
    if op == "execute":
        if mode == "timeout":
            time.sleep(30)
        if mode == "crash":
            sys.stderr.write("boom token=supersecretvalue123\n")
            return 3
        if mode == "garbage":
            sys.stdout.write("this is not json")
            return 0
        if mode == "oversize":
            sys.stdout.write("x" * (9 * 1024 * 1024))
            return 0
        if mode == "mismatch":
            return reply("ok", dict(RESULT, producer=producer), request_id="nope")
        if mode == "bad-envelope":
            sys.stdout.write(json.dumps({"protocol": "forge/v1", "kind": "Response",
                                         "request_id": rid, "status": "ok"}))
            return 0
        if mode == "refuse":
            return reply("refused", error={"code": "BAD-REFUSED", "detail": "refused on purpose",
                                           "field": "capability",
                                           "unlock": "try another capability"})
        if mode == "bad-result":
            return reply("ok", {"status": "weird"})
        if mode == "env-probe":
            return reply("ok", {"env": sorted(os.environ)})
        if mode == "cwd-probe":
            return reply("ok", {"cwd": os.getcwd()})
        return reply("ok", dict(RESULT, producer=producer))
    return reply("refused", error={"code": "BAD-OP", "detail": op, "field": "op",
                                   "unlock": None})


if __name__ == "__main__":
    raise SystemExit(main())
