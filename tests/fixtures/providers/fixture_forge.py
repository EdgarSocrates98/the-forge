"""Minimal standalone Forge Protocol v1 provider driven by a manifest file (stdlib only).

argv: fixture_forge.py MANIFEST_JSON OP
"""

import json
import sys
from pathlib import Path


def main() -> int:
    manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    op = sys.argv[2]
    producer = {"id": manifest["id"], "version": manifest["version"]}
    rid = "unknown"

    def reply(status, payload=None, error=None):
        sys.stdout.write(json.dumps({
            "protocol": "forge/v1", "kind": "Response", "request_id": rid,
            "op": op, "producer": producer, "status": status, "payload": payload or {},
            "error": error,
        }))
        return 0

    def err(code, detail, field=None):
        return {"code": code, "detail": detail, "field": field, "unlock": None}

    try:
        req = json.loads(sys.stdin.read())
        rid = str(req["request_id"])
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        return reply("error", error=err("FIXTURE-REQ-INVALID", str(exc)))
    if op != "describe" and req.get("protocol") != "forge/v1":
        return reply("refused", error=err("FIXTURE-PROTO-UNSUPPORTED",
                                          str(req.get("protocol")), "protocol"))
    if op == "describe":
        return reply("ok", manifest)
    if op == "health":
        return reply("ok", {"status": "ok", "checks": [{"name": "fixture", "ok": True}]})
    if op == "execute":
        payload = req.get("payload") or {}
        cap = payload.get("capability")
        if cap not in {c["id"] for c in manifest["capabilities"]}:
            return reply("refused", error=err("FIXTURE-CAP-UNSUPPORTED", str(cap), "capability"))
        capability = next(c for c in manifest["capabilities"] if c["id"] == cap)
        action = payload.get("action")
        if action not in capability.get("actions", []):
            return reply("refused", error=err("FIXTURE-ACTION-UNSUPPORTED", str(action),
                                              "action"))
        files = [f["path"] for f in (payload.get("context") or {}).get("files") or []]
        return reply("ok", {
            "schema": "theforge/ExecutionResult/v1", "producer": producer,
            "created_at": "1970-01-01T00:00:00.000000Z", "status": "ok",
            "findings": [{"id": "f1", "title": f"{manifest['id']} handled "
                                               f"{cap}:{payload.get('action')}",
                          "severity": "info", "evidence_ids": ["e1"]}],
            "evidence": [{"id": "e1", "epistemic": "observed", "subject": cap,
                          "claim": f"received {len(files)} context files",
                          "producer": producer}],
        })
    return reply("refused", error=err("FIXTURE-OP-UNSUPPORTED", op, "op"))


if __name__ == "__main__":
    raise SystemExit(main())
