"""Test handler set for the adapters' common shell (real-provider-integration 3.1).

argv: shell_forge.py [adapter options] OP. Loads ``_shell.py`` straight from the Spark Forge AWS
adapter sources (both copies are byte-identical, checked by the tests), so it runs on any
Python >= 3.10 without installing anything. ``test.echo``/``test.boom`` and their actions are
declared only here, for the shell tests. ``--assume-specialist-version describe-refuses`` makes
describe refuse; ``boom`` makes health raise. ``test.stage``/``analyze`` stages the context, needs
a ``*.py`` input and stands in for a specialist by reading the replay recording
``<replay>/test.stage.analyze.json`` (``{"facts": [{"id", "path", "sha256"?, "pad"?}]}``):
``pad`` grows the fact's claim by that many bytes; ``"split": true`` makes one finding per fact
(otherwise a single finding references every fact). The recording is the native output.
``test.native`` runs real native processes through ``run_native``: ``sleep`` outlives the
timeout (``payload.native_timeout`` seconds, else the profile's share), ``env`` reports the
environment and cwd the native process saw, with an adapter adjustment that adds a credential.
``test.cleanup`` (3.5) stages the context and leaves native-looking state in the cwd (a ledger,
a ``.apiforge/`` cache, a read-only file, an undeclared case file next to the declared
artifact ``case/findings.json``), then ends with the outcome named by the action: ``ok``,
``partial``, ``spill`` (a result above the inline limit), ``refused``, ``error``, ``raise``,
``exit`` or ``timeout`` (a native process that also writes to the cwd outlives
``payload.native_timeout``). ``--assume-specialist-version writes`` makes describe and health
write a file to their cwd (the shell must not clean it).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import stat
import sys
from pathlib import Path

SHELL = (Path(__file__).resolve().parents[3] / "adapters" / "sparkforge_aws" / "src"
         / "theforge_sparkforge_aws" / "_shell.py")
_spec = importlib.util.spec_from_file_location("adapter_shell_under_test", SHELL)
assert _spec is not None and _spec.loader is not None
shell = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = shell
_spec.loader.exec_module(shell)

PROVIDER_ID = "shell-test-forge"
VERSION = "9.8.7"
MANIFEST = {
    "id": PROVIDER_ID,
    "version": VERSION,
    "protocols": ["forge/v1"],
    "ops": ["describe", "health", "execute"],
    "capabilities": [
        {"id": "test.echo", "actions": ["run", "unserializable"]},
        {"id": "test.boom", "actions": ["run", "exit", "interrupt"]},
        {"id": "test.stage", "actions": ["analyze"]},
        {"id": "test.native", "actions": ["sleep", "env"]},
        {"id": "test.cleanup",
         "actions": ["ok", "partial", "spill", "refused", "error", "raise", "exit", "timeout"]},
    ],
}


def describe(options):
    def handle(request, cwd):
        if options.assume_specialist_version == "describe-refuses":
            return shell.refuse("SHELL-TEST-UNAVAILABLE", "specialist missing (test)",
                                unlock="install it")
        if options.assume_specialist_version == "writes":
            (cwd / "describe.out").write_bytes(b"describe")
        return shell.Reply(status="ok", payload=dict(MANIFEST))
    return handle


def health(options):
    def handle(request, cwd):
        if options.assume_specialist_version == "boom":
            raise RuntimeError("s3cr3t health failure")
        if options.assume_specialist_version == "writes":
            (cwd / "health.out").write_bytes(b"health")
        replay = None if options.replay is None else str(options.replay)
        return shell.Reply(status="ok", payload={
            "status": "ok", "checks": [],
            "options": {"replay": replay,
                        "assume_specialist_version": options.assume_specialist_version}})
    return handle


STAGE_INPUTS = {"script": ["*.py"]}


def analyze(options, request, cwd):
    stage = shell.stage_context(request.payload, cwd)
    draft = shell.no_input(stage, STAGE_INPUTS, provider_id=PROVIDER_ID, version=VERSION)
    if draft is not None:
        return shell.finalize(draft, cwd)
    recording = None if options.replay is None else options.replay / "test.stage.analyze.json"
    if recording is None or not recording.is_file():
        return shell.fail("ADAPTER-REPLAY-MISSING", "test.stage.analyze.json")
    native = json.loads(recording.read_text(encoding="utf-8"))
    facts = native["facts"]
    evidence = [{"id": fact["id"], "epistemic": "observed", "subject": "test.fact",
                 "claim": f"fact {fact['id']}" + "x" * fact.get("pad", 0),
                 "location": {"path": fact["path"], "line": 1},
                 "hash": shell.evidence_hash(fact["path"], fact.get("sha256"), stage)}
                for fact in facts]
    if native.get("split"):
        findings = [{"id": f"TEST-{item['id']}#1", "title": f"TEST-{item['id']}: fact",
                     "severity": "info", "evidence_ids": [item["id"]]} for item in evidence]
    else:
        findings = [{"id": "TEST-1#1", "title": "TEST-1: facts", "severity": "info",
                     "evidence_ids": [item["id"] for item in evidence]}]
    return shell.finalize(shell.ResultDraft(
        provider_id=PROVIDER_ID, version=VERSION, findings=findings, evidence=evidence,
        limitations=list(stage.limitations), native_output=native), cwd)


NATIVE_SLEEP = "import time; time.sleep(30)"
NATIVE_ENV = "import json, os; print(json.dumps({'env': dict(os.environ), 'cwd': os.getcwd()}))"
NATIVE_ADJUSTMENTS = {"APIFORGE_CACHE": "off", "FIXTURE_API_KEY": "s3cr3t-adjustment"}


def native(request, cwd):
    timeout = request.payload.get("native_timeout")
    timeout = shell.native_timeout(request.payload) if timeout is None else float(timeout)
    if request.payload["action"] == "sleep":
        shell.run_native([sys.executable, "-c", NATIVE_SLEEP], cwd=cwd, env={},
                         timeout=timeout)
        return shell.Reply(status="ok", payload={"slept": True})
    outcome = shell.run_native([sys.executable, "-c", NATIVE_ENV], cwd=cwd,
                               env=NATIVE_ADJUSTMENTS, timeout=timeout)
    return shell.Reply(status="ok", payload={"native": json.loads(outcome.stdout),
                                             "returncode": outcome.returncode})


CLEANUP_ARTIFACT = "case/findings.json"
CLEANUP_CASE = b'{"findings": []}\n'
NATIVE_WRITE_SLEEP = ("import pathlib, time; pathlib.Path('native-tmp').mkdir(); "
                      "pathlib.Path('native-tmp', 'part.bin').write_bytes(b'x'); time.sleep(30)")


def _leave_native_state(cwd):
    (cwd / "traces.db").write_bytes(b"ledger")
    (cwd / ".apiforge").mkdir(exist_ok=True)
    (cwd / ".apiforge" / "economy.jsonl").write_bytes(b"{}\n")
    (cwd / "case").mkdir(exist_ok=True)
    (cwd / "case" / "facts.json").write_bytes(b"[]\n")
    (cwd / CLEANUP_ARTIFACT).write_bytes(CLEANUP_CASE)
    (cwd / "native").mkdir(exist_ok=True)
    (cwd / "native" / "scratch.txt").write_bytes(b"scratch")
    readonly = cwd / "case" / "readonly.txt"
    readonly.write_bytes(b"read-only")
    os.chmod(readonly, stat.S_IREAD)


def cleanup(request, cwd):
    action = request.payload["action"]
    stage = shell.stage_context(request.payload, cwd)
    _leave_native_state(cwd)
    if action == "timeout":
        shell.run_native([sys.executable, "-c", NATIVE_WRITE_SLEEP], cwd=cwd, env={},
                         timeout=float(request.payload.get("native_timeout", 1.5)))
    if action == "refused":
        return shell.refuse("SHELL-TEST-NATIVE-REFUSED", "native refusal (test)")
    if action == "error":
        return shell.fail("SHELL-TEST-NATIVE-ERROR", "native error (test)")
    if action == "raise":
        raise RuntimeError("s3cr3t cleanup failure")
    if action == "exit":
        raise SystemExit(3)
    evidence = [{"id": "e1", "epistemic": "observed", "subject": "test.fact", "claim": "c",
                 "location": {"path": "jobs/a.py", "line": 1}, "hash": None}]
    findings = [{"id": "TEST-1#1", "title": "TEST-1: f", "severity": "info",
                 "evidence_ids": ["e1"]}]
    if action == "spill":
        evidence.append({**evidence[0], "id": "e2", "claim": "x" * (5 * 1024 * 1024)})
        findings.append({**findings[0], "id": "TEST-2#1", "evidence_ids": ["e2"]})
    artifacts = [{"path": CLEANUP_ARTIFACT,
                  "sha256": hashlib.sha256(CLEANUP_CASE).hexdigest()}]
    return shell.finalize(shell.ResultDraft(
        provider_id=PROVIDER_ID, version=VERSION, findings=findings, evidence=evidence,
        artifacts=artifacts, limitations=list(stage.limitations),
        partial=action == "partial", native_output={"native": action}), cwd)


def execute(options):
    def handle(request, cwd):
        capability = request.payload["capability"]
        action = request.payload["action"]
        if capability == "test.stage":
            return analyze(options, request, cwd)
        if capability == "test.native":
            return native(request, cwd)
        if capability == "test.cleanup":
            return cleanup(request, cwd)
        if capability == "test.boom" and action == "exit":
            raise SystemExit(2)
        if capability == "test.boom" and action == "interrupt":
            raise KeyboardInterrupt("s3cr3t interrupt")
        if capability == "test.boom":
            raise RuntimeError("s3cr3t execute failure")
        if action == "unserializable":
            return shell.Reply(status="ok", payload={"value": object()})
        return shell.Reply(status="ok", payload={"handled": {
            "capability": capability, "action": action, "request_id": request.request_id}})
    return handle


if __name__ == "__main__":
    raise SystemExit(shell.serve(provider_id=PROVIDER_ID, version=VERSION, handlers={
        "describe": describe, "health": health, "execute": execute}))
