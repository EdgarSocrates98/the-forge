"""Minimal standalone Forge Protocol v1 provider driven by a manifest file (stdlib only).

argv: fixture_forge.py [--unhealthy] MANIFEST_JSON OP

``--unhealthy`` makes the health op report ``unavailable`` (fallback scenarios).

The manifest file may carry test-only ``estimate`` and ``proposal`` keys (never part
of the described manifest): when the manifest declares the ``plan`` op, that op
answers ``estimate`` normally and ``proposal`` when the request carries
``purpose="proposal"``. ``execute`` echoes the number of handoff items it received as
one extra evidence (only when the request carries a handoff).
"""

import json
import sys
from pathlib import Path


def main() -> int:
    args = sys.argv[1:]
    unhealthy = args[0] == "--unhealthy"
    if unhealthy:
        args = args[1:]
    manifest = json.loads(Path(args[0]).read_text(encoding="utf-8"))
    estimate = manifest.pop("estimate", {})  # test-only key, not part of the manifest
    proposal = manifest.pop("proposal", None)  # test-only SemanticPlanProposal
    op = args[1]
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
        if unhealthy:
            return reply("ok", {"status": "unavailable",
                                "checks": [{"name": "fixture", "ok": False,
                                            "detail": "backend down"}]})
        return reply("ok", {"status": "ok", "checks": [{"name": "fixture", "ok": True}]})
    if op == "execute" or (op == "plan" and "plan" in manifest["ops"]):
        payload = req.get("payload") or {}
        cap = payload.get("capability")
        if cap not in {c["id"] for c in manifest["capabilities"]}:
            return reply("refused", error=err("FIXTURE-CAP-UNSUPPORTED", str(cap), "capability"))
        capability = next(c for c in manifest["capabilities"] if c["id"] == cap)
        action = payload.get("action")
        if action not in capability.get("actions", []):
            return reply("refused", error=err("FIXTURE-ACTION-UNSUPPORTED", str(action),
                                              "action"))
        if op == "plan":
            if payload.get("purpose") == "proposal":
                return reply("ok", proposal if proposal is not None else {})
            return reply("ok", estimate)
        files = [f["path"] for f in (payload.get("context") or {}).get("files") or []]
        evidence = [{"id": "e1", "epistemic": "observed", "subject": cap,
                     "claim": f"received {len(files)} context files", "producer": producer}]
        handoff = payload.get("handoff")
        if isinstance(handoff, dict):
            evidence.append({"id": "e2", "epistemic": "observed", "subject": "handoff",
                             "claim": f"received {len(handoff.get('items') or [])} "
                                      "handoff items",
                             "producer": producer})
        return reply("ok", {
            "schema": "theforge/ExecutionResult/v1", "producer": producer,
            "created_at": "1970-01-01T00:00:00.000000Z", "status": "ok",
            "findings": [{"id": "f1", "title": f"{manifest['id']} handled "
                                               f"{cap}:{payload.get('action')}",
                          "severity": "info", "evidence_ids": [e["id"] for e in evidence]}],
            "evidence": evidence,
        })
    return reply("refused", error=err("FIXTURE-OP-UNSUPPORTED", op, "op"))


if __name__ == "__main__":
    raise SystemExit(main())
