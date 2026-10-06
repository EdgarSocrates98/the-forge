"""Minimal standalone Forge Protocol v1 provider driven by a manifest file (stdlib only).

argv: fixture_forge.py [--unhealthy] MANIFEST_JSON OP

``--unhealthy`` makes the health op report ``unavailable`` (fallback scenarios).

The manifest file may carry test-only ``estimate``, ``proposal`` and ``decision``
keys (never part of the described manifest): when the manifest declares the ``plan``
op, that op answers ``estimate`` normally and ``proposal`` when the request carries
``purpose="proposal"``. ``execute`` echoes the number of handoff items it received as
one extra evidence (only when the request carries a handoff), and a ``decision``
key ``{"claim": ..., "subject": ...}`` adds a referee-style evidence with
``id="decision"`` (the debate convention). A ``findings`` list replaces the
default ``f1`` finding (missing ``evidence_ids`` are wired to the emitted
evidence). A ``flaky: <int>`` key makes the
first N ``execute`` calls exit 3 (a retryable FORGE-PROTO-EXIT): the count lives
in ``<workspace_root>/.forge/flaky-<id>.count`` so it survives across attempts.
When the manifest declares the ``verify`` op, that op answers the test-only
``verdict`` key (default ``{"status": "passed"}``), or the envelope status of
``verify_status`` (``refused``/``error``) when the key is set.
When the manifest declares the ``resolve`` op, that op answers the test-only
``resolution`` key (a RoutingProposal), or the envelope status of
``resolve_status`` when the key is set.
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
    decision = manifest.pop("decision", None)  # test-only referee decision evidence
    flaky = manifest.pop("flaky", 0)  # test-only: exit 3 on the first N executes
    cite = bool(manifest.pop("cite", False))  # test-only: e1 cites context file 1
    findings = manifest.pop("findings", None)  # test-only: replace f1 findings
    verdict = manifest.pop("verdict", {"status": "passed"})  # test-only VerifyVerdict
    verify_status = manifest.pop("verify_status", "ok")  # test-only envelope status
    resolution = manifest.pop("resolution", None)  # test-only RoutingProposal
    resolve_status = manifest.pop("resolve_status", "ok")  # test-only envelope status
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
    if op == "verify" and "verify" in manifest["ops"]:
        if verify_status != "ok":
            return reply(verify_status,
                         error=err("FIXTURE-VERIFY", f"verifier {verify_status}"))
        return reply("ok", verdict)
    if op == "resolve" and "resolve" in manifest["ops"]:
        if resolve_status != "ok":
            return reply(resolve_status,
                         error=err("FIXTURE-RESOLVE", f"resolver {resolve_status}"))
        return reply("ok", resolution if resolution is not None else {})
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
        first = {"id": "e1", "epistemic": "observed", "subject": cap,
                 "claim": f"received {len(files)} context files", "producer": producer}
        if cite and files:  # test-only: the evidence cites a sent file (context ROI)
            first["location"] = {"path": files[0]}
        evidence = [first]
        handoff = payload.get("handoff")
        if isinstance(handoff, dict):
            evidence.append({"id": "e2", "epistemic": "observed", "subject": "handoff",
                             "claim": f"received {len(handoff.get('items') or [])} "
                                      "handoff items",
                             "producer": producer})
        if isinstance(decision, dict):  # referee convention: id="decision", claim=node
            evidence.append({"id": "decision", "epistemic": "confirmed",
                             "subject": str(decision.get("subject") or "fixture decision"),
                             "claim": str(decision.get("claim") or ""),
                             "producer": producer})
        if op == "execute" and flaky:
            root = Path((payload.get("task") or {}).get("workspace_root") or ".")
            marker = Path(root) / ".forge" / f"flaky-{manifest['id']}.count"
            seen = int(marker.read_text(encoding="utf-8")) if marker.exists() else 0
            if seen < int(flaky):  # transient failure: retryable exit, no reply
                marker.write_text(str(seen + 1), encoding="utf-8")
                return 3
        declared = (findings if isinstance(findings, list)
                    else [{"id": "f1", "title": f"{manifest['id']} handled "
                                                f"{cap}:{payload.get('action')}",
                           "severity": "info"}])
        return reply("ok", {
            "schema": "theforge/ExecutionResult/v1", "producer": producer,
            "created_at": "1970-01-01T00:00:00.000000Z", "status": "ok",
            "findings": [{**f, "evidence_ids": f.get("evidence_ids")
                              or [e["id"] for e in evidence]}
                         for f in declared],
            "evidence": evidence,
        })
    return reply("refused", error=err("FIXTURE-OP-UNSUPPORTED", op, "op"))


if __name__ == "__main__":
    raise SystemExit(main())
