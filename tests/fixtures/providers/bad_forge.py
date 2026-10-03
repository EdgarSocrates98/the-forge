"""Misbehaving Forge Protocol provider for failure-mode tests (stdlib only).

argv: bad_forge.py MODE [PROVIDER_ID] OP
"""

import json
import os
import subprocess
import sys
import time

RESULT = {
    "schema": "theforge/ExecutionResult/v1",
    "created_at": "1970-01-01T00:00:00.000000Z",
    "status": "ok",
}


# Modes whose capability declares a non-read_only operation class (execute answers normally).
OPERATION_CLASSES = {"mutating": "local_mutation", "destructive": "destructive"}


GOOD_HASH = "0" * 64


def _evidence(eid, producer, **extra):
    return dict({"id": eid, "epistemic": "observed", "subject": "s", "claim": "c",
                 "producer": producer}, **extra)


def _finding(fid, *evidence_ids):
    return {"id": fid, "title": "t", "evidence_ids": list(evidence_ids)}


# Execute modes whose result is structurally valid but breaks a relational invariant
# (or, for bad-hash, the SHA-256 format): extra ExecutionResult fields per mode.
INTEGRITY_MODES = {
    "dup-evidence": lambda p: {"evidence": [_evidence("e1", p), _evidence("e1", p)]},
    "dup-finding": lambda p: {"evidence": [_evidence("e1", p)],
                              "findings": [_finding("f1", "e1"), _finding("f1", "e1")]},
    "dangling-ref": lambda p: {"evidence": [_evidence("e1", p)],
                               "findings": [_finding("f1", "e1", "e-missing")]},
    "artifact-absolute": lambda p: {"artifacts": [{"path": "/etc/passwd",
                                                   "sha256": GOOD_HASH}]},
    "artifact-traversal": lambda p: {"artifacts": [{"path": "out/../../escape.txt",
                                                    "sha256": GOOD_HASH}]},
    "bad-hash": lambda p: {"evidence": [_evidence("e1", p, hash="ABC123")]},
    "bad-artifact-hash": lambda p: {"artifacts": [{"path": "out/report.txt",
                                                   "sha256": "F" * 64}]},
    "bad-timestamp": lambda p: {"created_at": "yesterday"},
}


# Manifest protocol lists: malformed spellings only (no common major -> incompatible) or
# duplicated valid ones (collapse -> forge/v1).
MANIFEST_PROTOCOLS = {
    "malformed-protocols": ["FORGE/V1", " forge/v1", "forge/v01", "forge/v1.0", "forge/v١"],
    "duplicate-protocols": ["forge/v1", "forge/v2", "forge/v1", "forge/v2"],
}

# Over the manifest limits of theforge.contracts.types (MAX_CAPABILITIES=256, MAX_KEYWORDS=64).
SPAM_CAPABILITIES = 300
SPAM_KEYWORDS = 100


def capability(cap_id, file_globs=(), operation_class="read_only", keywords=("bad",)):
    return {
        "id": cap_id, "actions": ["run"], "default_action": "run",
        "state": "supported", "operation_class": operation_class,
        "signals": {"keywords": list(keywords), "file_globs": list(file_globs),
                    "dependencies": []},
    }


def env_lines():
    """Every environment variable name the provider received, as ``env:NAME`` lines."""
    return [f"env:{name}" for name in sorted(os.environ)]


def main() -> int:
    mode, op = sys.argv[1], sys.argv[-1]
    pid = sys.argv[2] if len(sys.argv) > 3 else "bad-forge"
    producer = {"id": pid, "version": "0.0.1"}
    impostor = {"id": "someone-else", "version": "0.0.1"}
    if mode == "no-read" and op == "execute":
        time.sleep(30)
        return 0
    raw = sys.stdin.read()
    try:
        rid = json.loads(raw).get("request_id", "unknown")
    except (json.JSONDecodeError, AttributeError):
        rid = "unknown"
    proto = "forge/v9" if mode == "wrong-major" else "forge/v1"

    def reply(status, payload=None, error=None, request_id=None, reply_op=op, who=None):
        envelope = {
            "protocol": proto, "request_id": request_id or rid,
            # wrong-kind answers execute with a Request envelope
            "kind": "Request" if mode == "wrong-kind" and op == "execute" else "Response",
            "op": reply_op, "producer": who or producer, "status": status,
            "payload": payload or {},
            "error": error,
        }
        if mode == "no-op":
            del envelope["op"]  # Protocol v1 providers may omit op
        sys.stdout.write(json.dumps(envelope))
        return 0

    if op == "describe":
        if mode == "describe-crash":
            sys.stderr.write("describe failed\n")
            return 3
        cap_id = "Bad Id" if mode == "invalid-manifest" else "bad.thing"
        capabilities = [capability(
            cap_id, operation_class=OPERATION_CLASSES.get(mode, "read_only"),
            # wide-glob: a glob without any literal character matches (almost) every file
            file_globs=["?*"] if mode == "wide-glob" else (),
            keywords=[f"bad{i}" for i in range(SPAM_KEYWORDS)] if mode == "keyword-spam"
            else ("bad",))]
        if mode == "capability-spam":
            capabilities += [capability(f"bad.spam{i}", keywords=["run", "it"])
                             for i in range(SPAM_CAPABILITIES)]
        if mode == "describe-catch-all-glob":
            capabilities.append(capability("bad.greedy", ["**/*"]))
        if mode == "describe-only-catch-all-glob":
            capabilities = [capability("bad.greedy", ["*"])]
        if mode == "describe-too-many-capabilities":
            capabilities = [capability(f"bad.c{i}") for i in range(257)]
        return reply("ok", {
            "schema": "theforge/ForgeManifest/v1", "id": pid, "version": "0.0.1",
            "protocols": MANIFEST_PROTOCOLS.get(mode, [proto]),
            "ops": ["describe", "health"] if mode == "no-execute-op"
            else ["describe", "health", "execute"],
            "domains": ["test"], "capabilities": capabilities,
            # describe-cwd-probe reports the working directory it was started in
            "limitations": [f"cwd={os.getcwd()}"] if mode == "describe-cwd-probe"
            else env_lines() if mode == "env-probe-full" else [],
        }, who=impostor if mode == "describe-wrong-producer" else None)
    if op == "health":
        if mode == "health-wrong-producer":
            return reply("ok", {"status": "ok", "checks": []}, who=impostor)
        if mode == "health-cwd-probe":
            return reply("ok", {"status": "ok",
                                "checks": [{"name": "cwd", "ok": True, "detail": os.getcwd()}]})
        if mode == "env-probe-full":
            return reply("ok", {"status": "ok",
                                "checks": [{"name": line, "ok": True} for line in env_lines()]})
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
        if mode in ("spawn-grandchild-timeout", "exit-leave-grandchild"):
            # Leave a long-sleeping grandchild behind (it inherits stdout/stderr) and publish
            # its PID in cwd; then either hang or answer correctly and exit 0.
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
            with open("grandchild.pid.tmp", "w", encoding="utf-8") as fh:
                fh.write(str(child.pid))
            os.replace("grandchild.pid.tmp", "grandchild.pid")
            if mode == "exit-leave-grandchild":
                reply("ok", dict(RESULT, producer=producer))
                sys.stdout.flush()
                os._exit(0)  # do not wait for the child
            time.sleep(30)
        if mode in ("stderr-flood", "stderr-flood-crash"):
            line = "noise token=supersecretvalue123 " + "y" * 60 + "\n"
            sys.stderr.write(line * (256 * 1024 // len(line) + 1))
            sys.stderr.write("final failure detail password=hunter2secret\n")
            sys.stderr.flush()
            if mode == "stderr-flood-crash":
                return 3
        if mode == "wrong-op":
            return reply("ok", dict(RESULT, producer=producer), reply_op="health")
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
        if mode == "env-probe-full":  # valid result; received variable names as limitations
            return reply("ok", dict(RESULT, producer=producer, limitations=env_lines()))
        if mode == "unknown-status":  # Response.status outside ok|partial|refused|error
            return reply("done", dict(RESULT, producer=producer))
        if mode == "cwd-probe":
            return reply("ok", {"cwd": os.getcwd()})
        if mode == "wrong-producer":
            return reply("ok", dict(RESULT, producer={"id": "someone-else", "version": "0.0.1"}))
        if mode == "wrong-version-producer":  # right id, version differs from the manifest
            return reply("ok", dict(RESULT, producer={"id": pid, "version": "9.9.9"}))
        if mode in INTEGRITY_MODES:
            return reply("ok", dict(RESULT, producer=producer, **INTEGRITY_MODES[mode](producer)))
        return reply("ok", dict(RESULT, producer=producer))
    return reply("refused", error={"code": "BAD-OP", "detail": op, "field": "op",
                                   "unlock": None})


if __name__ == "__main__":
    raise SystemExit(main())
